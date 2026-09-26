"""important classes common for many .py files"""
import json
import logging

import shapely
from shapely.geometry import Point
from shapely.strtree import STRtree

from app.src.database_utils import get_operative, get_weapon

# config for debug messages & logs
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

SM = "space_marines"
DG = "death_guard"
BASE_SIZE = 0.63


class GameState:
    """Greatest class of them all"""

    def __init__(self, json_data):
        """Constructor of class GameState"""
        # data in json should be valid. the script sending them should check it
        if isinstance(json_data, str):
            json_data = json.loads(json_data)

        self.active_faction = json_data["simulation_context"]["active_faction"]
        self.active_operative = json_data["simulation_context"]["active_operative_name"]
        self.user_goal = json_data["simulation_context"]["user_goal"].lower()  # CAPTURE, KILL, DAMAGE, SURVIVE, FLEE?

        self.obstacles = self.load_obstacles(json_data["map"]["obstacles"])
        self.objectives = self.load_objectives(json_data["map"]["objectives"])
        self.obstacle_tree = STRtree(self.obstacles) if self.obstacles else None

        self.operatives = self.load_operatives(json_data["operatives"])
        status = self.load_weapons()

        if self.operatives is None or status is False:
            logging.error("Could not load operatives and weapons")

    @staticmethod
    def load_obstacles(obstacles_data) -> list:
        """Parses obstacles and return list of Shapely Polygons"""
        obstacles = []
        for obs in obstacles_data:
            # [x,y] is bottom left corner
            minx = obs["x"]
            miny = obs["y"]
            maxx = obs["w"] + minx
            maxy = obs["h"] + miny

            obstacle_2d = shapely.box(minx, miny, maxx, maxy)
            obstacles.append(obstacle_2d)
        return obstacles

    @staticmethod
    def load_objectives(objectives_data) -> list:
        """Parses data and saves objective circles"""
        objectives = []
        for obj in objectives_data:
            objective_circle = Point(obj["x"], obj["y"]).buffer(BASE_SIZE)
            objectives.append(objective_circle)
        return objectives

    @staticmethod
    def load_operatives(operatives_data) -> dict | None:
        """Fills up team dictionary with operative instances"""
        operatives = {SM: [], DG: []}
        for team, operative in operatives_data.items():
            if team not in operatives:
                logging.error("Could not find team %s", team)
                return None
            for _, data in operative.items():

                from_db = get_operative(operative_name=data["type"], team=team)
                if from_db is None:
                    logging.error("Could not find operative %s", data["type"])
                    return None

                operative_instance = Operative(
                    name=from_db[1],
                    team=from_db[2],
                    apl=from_db[3],
                    move=from_db[4],
                    save=from_db[5],
                    wounds=data.get("wounds", from_db[6]),
                    weapons=json.loads(from_db[7]),
                    abilities=json.loads(from_db[8]),
                    pos_x=data["x"],
                    pos_y=data["y"],
                    order=data.get("order", "engage")
                )
                operatives[team].append(operative_instance)
        return operatives

    def load_weapons(self) -> bool:
        """Fills up Operative objects weapons list with Weapon class objects"""
        for team, op_list in self.operatives.items():
            if team not in [SM, DG]:
                logging.error("Could not find team %s", team)
                return False
            for operative in op_list:
                weapon_class_objects = []  # want to fill operative class with those
                for w in operative.get_weapons():
                    from_db = get_weapon(weapon_name=w, team=team)
                    if from_db is None:
                        logging.error("Could not find weapon %s", w)
                        return False

                    weapon_instance = Weapon(
                        name=from_db[1],
                        ranged_type=from_db[2],
                        atk=from_db[3],
                        hit=from_db[4],
                        dmg=from_db[5],
                        crit=from_db[6],
                        max_range=from_db[7],
                        special_effects=json.loads(from_db[8]),
                        operatives=json.loads(from_db[9])
                    )

                    weapon_class_objects.append(weapon_instance)
                    if not weapon_instance.organize_effects(): # sort effects into categories
                        return False

                operative.weapons = weapon_class_objects  # replace string with actual objects

        return True


class Operative:
    """Main operative class"""
    def __init__(self, name, team, apl, move, save, wounds, weapons, abilities, *, pos_x=0, pos_y=0, order=None):
        self.name = name
        self.team = team
        self.apl = apl
        self.move = move
        self.save = save
        self.wounds = wounds
        # json lists
        self.weapons = weapons
        self.abilities = abilities

        # in-game attributes
        self.order = order
        self.center = Point(pos_x, pos_y)
        self.base = self.center.buffer(BASE_SIZE)
        self.is_alive = True

    def to_tuple(self):
        """return tuple for db creation"""
        return (self.name, self.team, self.apl, self.move, self.save, self.wounds, json.dumps(self.weapons),
                json.dumps(self.abilities))

    def get_weapons(self):
        """Return weapons list"""
        return self.weapons

    def update_position(self, new_x, new_y):
        """Operative is moving"""
        self.center = Point(new_x, new_y)
        self.base = self.center.buffer(BASE_SIZE)


class Weapon:
    """Class used for weapon stats, todo write full docstring"""
    def __init__(self, name, ranged_type, atk, hit, dmg, crit, max_range, special_effects, operatives):
        self.name = name
        self.ranged_type = ranged_type
        self.atk = atk
        self.hit = hit
        self.dmg = dmg
        self.crit = crit
        self.range = max_range
        # lists
        self.special_effects = special_effects
        self.operatives = operatives

        # empty lists
        self.pre_att_effects = []
        self.mid_effects = []
        self.post_def_effects = []

    def to_tuple(self):
        """return tuple for db creation"""
        return (self.name, self.ranged_type, self.atk, self.hit, self.dmg, self.crit, self.range,
                json.dumps(self.special_effects), json.dumps(self.operatives))

    def organize_effects(self):
        """Organize types of effects into timing categories"""
        # all taken from rulebook
        all_pre_att = ('heavy', 'blast', 'torrent', 'silent')
        all_mid = ('piercing', 'brutal', 'lethal', 'saturate', 'devastating', 'severe', 'punishing', 'shock')
        all_post_def = ('stun', 'hot', 'limited')

        for effect in self.special_effects:
            clean_effect = effect.lower().strip()
            if clean_effect.startswith(all_pre_att):
                self.pre_att_effects.append(effect)
            elif clean_effect.startswith(all_mid):
                self.mid_effects.append(effect)
            elif clean_effect.startswith(all_post_def):
                self.post_def_effects.append(effect)
            else:
                logging.error("Weapon: organize_effects(): effect %s not found in rulebook..", clean_effect)
                return False
        return True
