"""Module containing the simulation engine for tactical evaluation."""
# @generated [all] Gemini CLI 3.0 2026-05/04: based on notes.ipynb, my testing, advice about rules and my code, but gemini completely rewrote it. 
import time
import random
import logging
import math
from typing import List, Dict, Any, Tuple, Optional

from shapely import Point, LineString
from app.src.models import GameState
from app.src.simulator.sim_models import NodeState, OperativeState, ShootPhase, FightPhase

# config for debug messages & logs
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

DELAY = 0.5  # margin for safety
BEAM_WIDTH = 200  # Top N nodes to keep in beam search
BASE_SIZE = 0.63


class SimulationEngine:
    """Engine responsible for running the beam search simulation."""

    def __init__(self, game_state: GameState):
        self.static_state = game_state
        self.time_limit = 20 - DELAY
        self.beam_width = BEAM_WIDTH
        self.transposition_table = {}

        # Optimized lookups
        self.static_ops_by_name = {
            op.name: op for team in self.static_state.operatives.values() for op in team
        }

        # Krok 0: Zobrist Hashing initialization
        self.zobrist_keys = self._init_zobrist()

    def _init_zobrist(self) -> Dict[str, Any]:
        """Initialize random 64-bit keys for all state components."""
        keys = {
            "names": {},
            "wounds": [random.getrandbits(64) for _ in range(31)],  # up to 30 wounds
            "pos_x": {},
            "pos_y": {},
            "phases": {"positioning": random.getrandbits(64), "terminal": random.getrandbits(64)},
            "is_active": [random.getrandbits(64), random.getrandbits(64)],
            "has_moved": [random.getrandbits(64), random.getrandbits(64)],
            "has_shot": [random.getrandbits(64), random.getrandbits(64)],
            "has_captured": [random.getrandbits(64), random.getrandbits(64)]
        }

        for op_name in self.static_ops_by_name:
            keys["names"][op_name] = random.getrandbits(64)

        return keys

    def hash_node(self, node: NodeState) -> int:
        """Krok 0: Zobrist Hashing & Transposition Tables."""
        h = self.zobrist_keys["phases"].get(node.phase, 0)

        for op in node.operatives:
            h ^= self.zobrist_keys["names"].get(op.name, 0)
            w = min(30, max(0, int(op.wounds)))
            h ^= self.zobrist_keys["wounds"][w]

            x_disc, y_disc = int(op.x * 10), int(op.y * 10)
            if x_disc not in self.zobrist_keys["pos_x"]:
                self.zobrist_keys["pos_x"][x_disc] = random.getrandbits(64)
            if y_disc not in self.zobrist_keys["pos_y"]:
                self.zobrist_keys["pos_y"][y_disc] = random.getrandbits(64)

            h ^= self.zobrist_keys["pos_x"][x_disc]
            h ^= self.zobrist_keys["pos_y"][y_disc]
            h ^= self.zobrist_keys["is_active"][1 if op.is_active else 0]

        has_moved = any("Move" in m for m in node.prev_moves)
        h ^= self.zobrist_keys["has_moved"][1 if has_moved else 0]
        has_shot = any("Shoot" in m or "Fight" in m for m in node.prev_moves)
        h ^= self.zobrist_keys["has_shot"][1 if has_shot else 0]
        has_captured = "Capture" in node.prev_moves
        h ^= self.zobrist_keys["has_captured"][1 if has_captured else 0]
        return h

    def _generate_target_points(self, node: NodeState) -> List[Tuple[float, float]]:
        """Step 1: Goal-Oriented State Space Discretization."""
        points = set()
        active_op_state = next(op for op in node.operatives if op.is_active)
        active_pos = Point(active_op_state.x, active_op_state.y)

        static_op = self.static_ops_by_name[active_op_state.name]
        has_moved = any("Move" in m for m in node.prev_moves)
        if has_moved:
            return [(active_op_state.x, active_op_state.y)]

        # Move + Dash logic for 2+ AP models
        max_dist = static_op.move + (3.0 if active_op_state.ap_left >= 2 else 0.0)
        goal = self.static_state.user_goal.lower()

        if goal == "capture":
            for obj in self.static_state.objectives:
                if active_pos.distance(obj) <= max_dist + 2.0:
                    cx, cy = obj.centroid.x, obj.centroid.y
                    points.update([(cx, cy), (cx + 0.5, cy), (cx - 0.5, cy), (cx, cy + 0.5), (cx, cy - 0.5)])

        if goal != "kill":
            for obs in self.static_state.obstacles:
                minx, miny, maxx, maxy = obs.bounds
                offset = BASE_SIZE + 0.1
                corners = [(minx - offset, miny - offset), (minx - offset, maxy + offset),
                           (maxx + offset, miny - offset), (maxx + offset, maxy + offset)]
                for cx, cy in corners:
                    if active_pos.distance(Point(cx, cy)) <= max_dist:
                        points.add((cx, cy))

        enemy_faction = "death_guard" if self.static_state.active_faction == "space_marines" else "space_marines"
        enemies = [op for op in node.operatives if
                   op.name in [e.name for e in self.static_state.operatives[enemy_faction]] and op.wounds > 0]

        for enemy in enemies:
            enemy_pos = Point(enemy.x, enemy.y)
            if active_pos.distance(enemy_pos) <= max_dist + 3.0:
                ex, ey = enemy.x, enemy.y
                points.update([(ex + 1.5, ey), (ex - 1.5, ey), (ex, ey + 1.5), (ex, ey - 1.5)])

        for angle in range(0, 360, 45):
            rad = math.radians(angle)
            for d in [static_op.move, max_dist]:
                if d > 0:
                    points.add((active_op_state.x + math.cos(rad) * d, active_op_state.y + math.sin(rad) * d))

        valid_points = []
        for px, py in points:
            pt = Point(px, py)
            if active_pos.distance(pt) > max_dist:
                continue

            buffered_pt = pt.buffer(BASE_SIZE - 0.01)
            if self.static_state.obstacle_tree is not None:
                if any(self.static_state.obstacles[idx].intersects(buffered_pt) for idx in
                       self.static_state.obstacle_tree.query(buffered_pt)):
                    continue
            valid_points.append((px, py))

        if not valid_points:
            valid_points.append((active_op_state.x, active_op_state.y))
        return valid_points

    def _is_path_clear(self, start: Point, end: Point) -> bool:
        """Check if the 'thick' path (base width) is blocked by obstacles."""
        dist = start.distance(end)
        if dist < 0.05:
            return True
        if self.static_state.obstacle_tree is None:
            return True

        ray = LineString([start, end])
        # Use full BASE_SIZE minus tiny margin to prevent clipping
        thick_ray = ray.buffer(BASE_SIZE - 0.01, cap_style='flat')
        potential_obs = [self.static_state.obstacles[idx] for idx in self.static_state.obstacle_tree.query(thick_ray)]
        return not any(obs.intersects(thick_ray) for obs in potential_obs)

    def _has_line_of_sight(self, start: Point, end: Point) -> bool:
        """Check for LOS using a simple thin line, with a tiny safety offset."""
        if self.static_state.obstacle_tree is None:
            return True
        dist = start.distance(end)
        if dist < 0.05:
            return True

        # Tiny offset just to avoid float precision issues at start/end points
        dx = (end.x - start.x) / dist
        dy = (end.y - start.y) / dist
        s_point = Point(start.x + dx * 0.01, start.y + dy * 0.01)
        e_point = Point(end.x - dx * 0.01, end.y - dy * 0.01)

        ray = LineString([s_point, e_point])
        # Direct intersection check on all potential obstacles
        for idx in self.static_state.obstacle_tree.query(ray):
            if self.static_state.obstacles[idx].intersects(ray):
                return False
        return True

    def _generate_moves(self, node: NodeState) -> List[NodeState]:
        """Step 1: Expansion - Generate possible positions."""
        active_op = next(op for op in node.operatives if op.is_active)
        if active_op.ap_left <= 0:
            return [node]

        # Rule: No movement allowed after an attack (Shoot/Fight)
        has_attacked = any("Shoot" in m or "Fight" in m for m in node.prev_moves)
        if has_attacked:
            return [node]

        target_points = self._generate_target_points(node)
        start_pt = Point(active_op.x, active_op.y)
        static_op = self.static_ops_by_name[active_op.name]
        new_nodes = []

        for px, py in target_points:
            end_pt = Point(px, py)
            dist = start_pt.distance(end_pt)
            is_stay = dist < 0.05

            # AP Cost calculation
            ap_cost = 0
            if not is_stay:
                ap_cost = 1
                if dist > static_op.move + 0.01:
                    ap_cost = 2

            if active_op.ap_left < ap_cost:
                continue

            if not is_stay and not self._is_path_clear(start_pt, end_pt):
                continue

            # Collision with other operatives
            collision = any(end_pt.distance(Point(o.x, o.y)) < (BASE_SIZE * 2.0)
                            for o in node.operatives if o.name != active_op.name and o.wounds > 0)

            if not collision:
                new_ops = tuple(
                    op._replace(x=px, y=py, ap_left=op.ap_left - ap_cost) if op.name == active_op.name else op for op in
                    node.operatives)
                new_moves = node.prev_moves
                if not is_stay:
                    move_type = "Move" if ap_cost == 1 else "Move+Dash"
                    new_moves += (f"{move_type} to ({px:.1f}, {py:.1f})",)

                new_nodes.append(NodeState(
                    active_operative=node.active_operative,
                    phase="positioning",
                    operatives=new_ops,
                    prev_moves=new_moves
                ))

        # Ensure root-like stay node is present if not already added (cost 0)
        if not any(abs(n.operatives[0].x - active_op.x) < 0.05 and abs(n.operatives[0].y - active_op.y) < 0.05 for n in
                   new_nodes):
            new_nodes.append(node)

        return new_nodes

    def _heuristic_beam_search(self, moves: List[NodeState], width: int) -> List[NodeState]:
        """Krok 2: Heuristic Beam Search."""
        if len(moves) <= width:
            return moves
        scored = sorted([(self._calc_positional_heuristic(m), m) for m in moves], key=lambda x: x[0], reverse=True)
        return [m for s, m in scored[:width]]

    def _calc_positional_heuristic(self, node: NodeState) -> float:
        """Fast geometric evaluation for beam search."""
        score = 0.0
        active_op = next(op for op in node.operatives if op.is_active)
        active_pos = Point(active_op.x, active_op.y)
        goal = self.static_state.user_goal.lower()

        if goal == "capture":
            min_obj_dist = min((active_pos.distance(obj) for obj in self.static_state.objectives), default=100.0)
            score += max(0.0, 100.0 - (min_obj_dist ** 2)) * 10.0
        elif goal in ["kill", "damage"]:
            enemy_faction = "death_guard" if self.static_state.active_faction == "space_marines" else "space_marines"
            enemies = [op for op in node.operatives if
                       op.name in [e.name for e in self.static_state.operatives[enemy_faction]] and op.wounds > 0]
            if enemies:
                min_enemy_dist = min(active_pos.distance(Point(e.x, e.y)) for e in enemies)
                if min_enemy_dist <= 6.0:
                    score += 1000.0
                elif min_enemy_dist <= 12.0:
                    score += 500.0

        in_cover = self._check_cover_heuristic(active_op)
        if in_cover:
            score += 500.0 if goal == "survive" else 100.0
        elif goal == "survive":
            score -= 1000.0

        if goal == "survive":
            enemy_faction = "death_guard" if self.static_state.active_faction == "space_marines" else "space_marines"
            enemies = [op for op in node.operatives if
                       op.name in [e.name for e in self.static_state.operatives[enemy_faction]] and op.wounds > 0]
            if enemies:
                min_enemy_dist = min(active_pos.distance(Point(e.x, e.y)) for e in enemies)
                score += min_enemy_dist * 500.0

        threat = self._adversarial_lookahead(node)
        score -= threat * (200.0 if goal == "survive" else 20.0)

        return score

    def _generate_terminal_actions(self, node: NodeState) -> List[NodeState]:
        """Generate legal actions from current position."""
        actions = []
        active_op = next(op for op in node.operatives if op.is_active)

        actions.append(node._replace(phase="terminal", prev_moves=node.prev_moves + ("End Activation",)))
        if active_op.ap_left <= 0:
            return actions

        active_pos = Point(active_op.x, active_op.y)
        static_op = self.static_ops_by_name[active_op.name]

        # 1. Mission Actions (Capture)
        has_attacked = any("Shoot" in m or "Fight" in m for m in node.prev_moves)
        has_captured = "Capture" in node.prev_moves
        if not has_attacked and not has_captured:
            for obj in self.static_state.objectives:
                if active_pos.distance(obj) <= 1.0:
                    new_ops = tuple(
                        op._replace(ap_left=op.ap_left - 1) if op.is_active else op for op in node.operatives)
                    actions.append(node._replace(phase="positioning", operatives=new_ops,
                                                 prev_moves=node.prev_moves + ("Capture",)))
                    break

        # 2. Attacks (Strict KT constraints)
        enemy_faction = "death_guard" if self.static_state.active_faction == "space_marines" else "space_marines"
        enemies = [op for op in node.operatives if
                   op.name in [e.name for e in self.static_state.operatives[enemy_faction]] and op.wounds > 0]

        # Rule: Operative cannot Shoot and Fight in the same activation
        has_shot_actions = [m for m in node.prev_moves if "Shoot" in m]
        has_fought_actions = [m for m in node.prev_moves if "Fight" in m]

        # Target restriction: Only one enemy can be targeted per activation
        prev_targets = [m.split(":")[1] for m in node.prev_moves if ":" in m and ("Shoot" in m or "Fight" in m)]
        first_target = prev_targets[0] if prev_targets else None

        # Multi-attack abilities
        can_shoot_twice = any(a.lower().replace(" ", "_") == "bolter_discipline" for a in static_op.abilities)
        can_fight_twice = any(a.lower().replace(" ", "_") == "shock_assault" for a in static_op.abilities)

        for enemy in enemies:
            # If we already targeted someone else, we can't target this enemy
            if first_target and enemy.name != first_target:
                continue

            enemy_pos = Point(enemy.x, enemy.y)
            dist = active_pos.distance(enemy_pos)
            is_in_engagement = dist <= 1.5

            for weapon in static_op.weapons:
                # FIGHT logic
                if weapon.ranged_type == "short" and is_in_engagement and not has_shot_actions:
                    # Allowed if never fought before, or if has Shock Assault and fought once
                    if len(has_fought_actions) == 0 or (len(has_fought_actions) == 1 and can_fight_twice):
                        fight_node = node._replace(prev_moves=node.prev_moves + (f"Fight:{enemy.name}:{weapon.name}",))
                        actions.extend(self._resolve_combat_outcomes(fight_node))

                # SHOOT logic
                elif weapon.ranged_type == "long" and not is_in_engagement and not has_fought_actions:
                    # Allowed if never shot before, or if has Bolter Discipline and shot once
                    if len(has_shot_actions) == 0 or (len(has_shot_actions) == 1 and can_shoot_twice):
                        if (weapon.range == 0 or dist <= weapon.range) and self._has_line_of_sight(active_pos,
                                                                                                   enemy_pos):
                            shoot_node = node._replace(
                                prev_moves=node.prev_moves + (f"Shoot:{enemy.name}:{weapon.name}",))
                            actions.extend(self._resolve_combat_outcomes(shoot_node))

        return actions

    def _resolve_combat_outcomes(self, node: NodeState) -> List[NodeState]:
        """Apply combat results."""
        last_action = node.prev_moves[-1]
        parts = last_action.split(":")
        action_type, enemy_name, weapon_name = parts[0], parts[1], parts[2]

        active_op = next(op for op in node.operatives if op.is_active)
        target_op = next(op for op in node.operatives if op.name == enemy_name)
        static_active = self.static_ops_by_name[active_op.name]
        weapon = next(w for w in static_active.weapons if w.name == weapon_name)

        if action_type == "Shoot":
            phase = ShootPhase(active_op, target_op, weapon, cover=self._check_cover_heuristic(target_op),
                               has_moved="Move" in str(node.prev_moves))
        else:
            static_target = self.static_ops_by_name[target_op.name]
            def_weapon = next((w for w in static_target.weapons if w.ranged_type == "short"), weapon)
            phase = FightPhase(active_op, target_op, weapon, def_weapon)

        phase.simulate()
        new_ops = []
        for op in node.operatives:
            if op.name == active_op.name:
                new_ops.append(op._replace(wounds=max(0, round(op.wounds - phase.dmg_received, 1)),
                                           ap_left=max(0, op.ap_left - 1)))
            elif op.name == target_op.name:
                new_ops.append(op._replace(wounds=max(0, round(op.wounds - phase.dmg_dealt, 1))))
            else:
                new_ops.append(op)

        return [node._replace(operatives=tuple(new_ops), phase="positioning")]

    def _check_cover_heuristic(self, target: OperativeState) -> bool:
        """Check if target is near an obstacle."""
        if self.static_state.obstacle_tree is None:
            return False
        pt = Point(target.x, target.y)
        buffered = pt.buffer(BASE_SIZE + 0.1)
        return any(self.static_state.obstacles[idx].intersects(buffered) for idx in
                   self.static_state.obstacle_tree.query(buffered))

    def _adversarial_lookahead(self, node: NodeState) -> float:
        """Fast 1-ply threat estimation."""
        active_op = next(op for op in node.operatives if op.is_active)
        if active_op.wounds <= 0:
            return 0.0

        enemy_faction = "death_guard" if self.static_state.active_faction == "space_marines" else "space_marines"
        enemies = [op for op in node.operatives if
                   op.name in [e.name for e in self.static_state.operatives[enemy_faction]] and op.wounds > 0]

        max_threat = 0.0
        active_pos = Point(active_op.x, active_op.y)
        for enemy in enemies:
            static_enemy = self.static_ops_by_name[enemy.name]
            dist = active_pos.distance(Point(enemy.x, enemy.y))
            if dist > static_enemy.move + 12.0:
                continue

            for w in static_enemy.weapons:
                w_dmg = (w.atk * (w.dmg + w.crit)) / 2.0
                if w.ranged_type == "short" and dist <= static_enemy.move + 2.0:
                    max_threat = max(max_threat, w_dmg)
                elif w.ranged_type == "long" and (w.range == 0 or dist <= w.range + static_enemy.move):
                    if self._has_line_of_sight(Point(enemy.x, enemy.y), active_pos):
                        max_threat = max(max_threat, w_dmg)
        return max_threat

    def run(self) -> List[Dict[str, Any]]:
        """Iterative Deepening with proper beam search recursion."""
        start_time = time.time()
        self.transposition_table = {}
        depth = 1
        best_results = []
        root = self._create_root_node()

        # In initial branches, try to force Move before Action to satisfy tests/logic
        initial_moves = self._generate_moves(root)
        initial_branches = []
        for m in initial_moves:
            initial_branches.extend(self._generate_terminal_actions(m))

        # Sort so that actual Moves come first if scores are tied
        initial_branches.sort(key=lambda n: (self._evaluate_node(n), any("Move" in m for m in n.prev_moves)),
                              reverse=True)
        # for b in initial_branches[:10]:
        #     logging.debug(f"Branch: {b.prev_moves}, score: {self._evaluate_node(b)}")

        while (time.time() - start_time) < self.time_limit and depth <= 4:
            current_depth_results = []
            for child in initial_branches:
                if (time.time() - start_time) > self.time_limit:
                    break
                res = self._search(child, depth - 1, start_time)
                if res:
                    current_depth_results.append(res)

            if current_depth_results:
                current_depth_results.sort(key=lambda x: x['score'], reverse=True)
                best_results = current_depth_results[:6]
                logging.info("Depth %d completed, best score: %.2f", depth, best_results[0]['score'])
            depth += 1

        return self._format_output(best_results)

    def _search(self, node: NodeState, depth: int, start_time: float) -> Optional[Dict[str, Any]]:
        """Recursive Beam Search."""
        node_hash = self.hash_node(node)
        if node_hash in self.transposition_table and self.transposition_table[node_hash]['depth'] >= depth:
            return self.transposition_table[node_hash]['value']

        if (time.time() - start_time) > self.time_limit:
            return None

        if self._is_terminal(node) or depth <= 0:
            res = {'score': self._evaluate_node(node), 'sequence': list(node.prev_moves), 'final_node': node}
            self.transposition_table[node_hash] = {'depth': depth, 'value': res}
            return res

        branches = []
        for move_node in self._generate_moves(node):
            gen_actions = self._generate_terminal_actions(move_node)
            branches.extend(gen_actions)

        beam = self._heuristic_beam_search(branches, self.beam_width)
        best_res = {'score': -float('inf'), 'sequence': [], 'final_node': None}
        for child in beam:
            res = self._search(child, depth - 1, start_time)
            if res and res['score'] > best_res['score']:
                best_res = res

        if best_res['final_node'] is None:
            best_res = {'score': self._evaluate_node(node), 'sequence': list(node.prev_moves), 'final_node': node}

        self.transposition_table[node_hash] = {'depth': depth, 'value': best_res}
        return best_res

    def _evaluate_node(self, node: NodeState) -> float:
        """Step 6: MCDA Evaluation."""
        active_op = next(op for op in node.operatives if op.name == node.active_operative)
        if active_op.wounds <= 0:
            return -100000.0

        static_active = self.static_ops_by_name[active_op.name]
        goal = self.static_state.user_goal.lower()
        hp_ratio = active_op.wounds / static_active.wounds

        enemy_faction = "death_guard" if self.static_state.active_faction == "space_marines" else "space_marines"
        enemies_in_node = [next(o for o in node.operatives if o.name == e.name) for e in
                           self.static_state.operatives[enemy_faction]]

        total_dmg_dealt = 0.0
        kill_reward = 0.0
        for static_e, op_in_node in zip(self.static_state.operatives[enemy_faction], enemies_in_node):
            dmg = static_e.wounds - op_in_node.wounds
            total_dmg_dealt += dmg
            if op_in_node.wounds <= 0:
                kill_reward += 100000.0  # Large bonus for confirming a kill

        pos_score = self._calc_positional_heuristic(node)
        action_bonus = 0.0
        if "Capture" in str(node.prev_moves):
            action_bonus += 20000.0 if goal == "capture" else 1000.0
        # if "Capture" in str(node.prev_moves):
        #     logging.debug(f"Node {node.prev_moves} has action_bonus {action_bonus}")
        if any(a in str(node.prev_moves) for a in ["Shoot", "Fight"]):
            action_bonus += 5000.0 if goal in ["kill", "damage"] else 500.0

        if goal == "kill":
            # Priorities: Killing > Damage > HP Ratio > Position
            score = kill_reward + (total_dmg_dealt * 1000.0) + (hp_ratio * 5000.0) + pos_score + action_bonus
        elif goal == "survive":
            score = (hp_ratio * 50000.0) + (pos_score * 10.0) - (total_dmg_dealt * 10.0) + action_bonus
        elif goal == "capture":
            score = (pos_score * 100.0) + (total_dmg_dealt * 100.0) + action_bonus
        else:
            score = total_dmg_dealt * 500.0 + pos_score + action_bonus

        return score

    def _is_terminal(self, node: NodeState) -> bool:
        """Check if activation ends."""
        active_op = next(op for op in node.operatives if op.name == node.active_operative)
        return active_op.wounds <= 0 or active_op.ap_left <= 0 or node.phase == "terminal"

    def _format_output(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format final output."""
        formatted = []
        for i, res in enumerate(results):
            active_op = next(op for op in res['final_node'].operatives if op.name == self.static_state.active_operative)
            formatted.append({
                'rank': i + 1,
                'score': round(res['score'], 2),
                'sequence': res['sequence'],
                'final_position': {'x': round(active_op.x, 2), 'y': round(active_op.y, 2)},
                'final_node': res['final_node'],
                'operatives': [{'name': o.name, 'wounds': round(o.wounds, 1)} for o in res['final_node'].operatives]
            })
        return formatted

    def _create_root_node(self) -> NodeState:
        """Create root node."""
        ops = []
        for team in self.static_state.operatives.values():
            for op in team:
                ops.append(OperativeState(
                    name=op.name, wounds=op.wounds, ap_left=op.apl,
                    x=op.center.x, y=op.center.y, order=op.order,
                    is_active=(op.name == self.static_state.active_operative)
                ))
        return NodeState(active_operative=self.static_state.active_operative, phase="positioning",
                         operatives=tuple(ops), prev_moves=tuple())
