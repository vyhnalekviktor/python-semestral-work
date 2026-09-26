"""Module for simulation-specific data models and combat phases."""
from typing import NamedTuple
import logging

from ..models import Weapon


class OperativeState(NamedTuple):
    """Light class to use in simulation instead of Operative."""
    name: str
    wounds: int
    ap_left: int
    x: float
    y: float
    order: str  # conceal / engage
    is_active: bool


class NodeState(NamedTuple):
    """State of each node used in simulation."""
    active_operative: str
    phase: str  # positioning / terminal (if he can move or not)
    operatives: tuple[OperativeState, ...]
    prev_moves: tuple[str, ...]  # f.e. ['move 6"', 'shoot: bolter for 4 wounds', 'capture'] etc.


class CombatPhase:
    """Common class for all combat phases"""

    def __init__(self, attacker: OperativeState, defender: OperativeState, weapon: Weapon):
        """initialize values"""
        self.attacker = attacker
        self.defender = defender
        self.weapon = weapon

        self.dmg_dealt = 0.0
        self.dmg_received = 0.0
        self.wounds_attacker = self.attacker.wounds
        self.wounds_defender = self.defender.wounds

        self.hit_prob = 0.0
        self.crit_prob = 0.0
        self.save_prob = 0.0
        self.is_kill = False
        self.is_dead = False
        self.ap_reduction = 0

        self.is_resolved = False

    def check_kill_death(self):
        """Check if active killed or is killed."""
        if self.dmg_dealt >= self.defender.wounds:
            self.is_kill = True
        if self.dmg_received >= self.attacker.wounds:
            self.is_dead = True

    def get_summary(self):
        """returns brief summary of the phase for GUI / further evaluation"""
        return {
            "attacker": self.attacker.name,
            "defender": self.defender.name,
            "dmg_dealt": round(self.dmg_dealt, 2),
            "dmg_received": round(self.dmg_received, 2),
            "wounds_attacker": self.wounds_attacker,
            "wounds_defender": self.wounds_defender,
            "weapon": self.weapon.name,
            "hit_prob": round(self.hit_prob, 2),
            "crit_prob": round(self.crit_prob, 2),
            "save_prob": round(self.save_prob, 2),
            "ap_reduction": self.ap_reduction,
            "is_kill": self.is_kill
        }

    def get_info_for_idx(self):
        """Get summary for index calculation"""
        return {
            "ev": self.dmg_dealt,
            "hit_prob": self.hit_prob,
            "crit_prob": self.crit_prob,
            "received": self.dmg_received,
            "kill": self.is_kill
        }

    def simulate(self):
        """Simulate combat phase. must be implemented by subclass"""
        raise NotImplementedError("Subclass must implement this method")


class ShootPhase(CombatPhase):
    """Shooting phase class, used for shooting resolution and evaluation"""

    def __init__(self, attacker: OperativeState, defender: OperativeState, weapon: Weapon, *, cover: bool,
                 has_moved: bool = False):
        super().__init__(attacker, defender, weapon)
        self.cover = cover
        self.has_moved = has_moved

    def simulate(self):
        """Simulate shooting phase. deterministic approach."""
        # pre attack effects: check for heavy effect (just in case)
        if self.has_moved:
            for effect in self.weapon.pre_att_effects:
                if effect.startswith("heavy"):
                    self.is_resolved = True
                    return True

        # Attacker dice pool -------------------------------------------------------------------------------------------

        critical_threshold = 6
        for effect in self.weapon.mid_effects:
            if effect.startswith("lethal"):
                critical_threshold = int(effect.split("_")[1])
                break

        # basic combinatorics formulas for one dice
        p_crit = (6 - critical_threshold + 1) / 6.0
        p_hit = (critical_threshold - self.weapon.hit) / 6.0
        p_miss = (self.weapon.hit - 1) / 6.0

        atk_count = self.weapon.atk

        # edge case probabilities
        p_no_crit = (p_hit + p_miss) ** atk_count
        p_no_hit = p_miss ** atk_count
        p_only_hit = p_hit ** atk_count
        p_no_miss = (p_crit + p_hit) ** atk_count

        exp_crits = self.weapon.atk * p_crit
        exp_hits = self.weapon.atk * p_hit
        exp_miss = self.weapon.atk * p_miss

        # attacker dice pool effects
        for effect in self.weapon.mid_effects:
            if effect.startswith("severe"):
                severe_chance = p_no_crit - p_no_hit  # when i dont hit critical, but hit normal hit
                exp_crits += severe_chance
                exp_hits -= severe_chance

            elif effect.startswith("punishing"):
                # at least one miss && one crit
                punish_chance = 1.0 - p_no_crit - p_no_miss + p_only_hit
                exp_hits += punish_chance
                exp_miss -= punish_chance

        # Defender dice pool -------------------------------------------------------------------------------------------
        has_cover = self.cover
        def_dice = 3
        devastating_wounds = 0  # special effects for sniper

        for effect in self.weapon.mid_effects:
            if effect.startswith("saturate"):
                has_cover = False
            elif effect.startswith("devastating"):
                # deal dmg for every crit, which cannot be blocked
                dev_val = int(effect.split("_")[-1])
                devastating_wounds += (exp_crits * dev_val)
            elif effect.startswith("piercing"):
                # splits into ["piercing", "crits", "1"] or ["piercing", "1"]
                parts = effect.split("_")
                pierce_val = int(parts[-1])
                if "crits" in effect:
                    pierce_val = min(exp_crits, pierce_val)
                def_dice = max(0, def_dice - pierce_val)

        guaranteed_def = 0
        save_threshold = 3
        if has_cover and def_dice > 0:
            def_dice -= 1
            guaranteed_def = 1

        p_save = (6 - save_threshold + 1) / 6.0
        exp_save = (def_dice * p_save) + guaranteed_def

        if any(effect.startswith("shock") for effect in self.weapon.mid_effects):
            exp_save = max(0, exp_save - exp_crits)

        # save into class stats
        self.save_prob = exp_save
        self.hit_prob = exp_hits
        self.crit_prob = exp_crits

        # Damage resolution --------------------------------------------------------------------------------------------

        # block 2 normal hits or one crit ????
        if (self.weapon.crit / 2.0) > self.weapon.dmg:
            # crits are more than twice worse than normal hits, prioritize saving them
            saves_for_crits = min(exp_save, exp_crits * 2.0)
            remaining_crits = exp_crits - (saves_for_crits / 2.0)
            # other saves block normal hits
            remaining_saves = exp_save - saves_for_crits
            remaining_hits = max(0, exp_hits - remaining_saves)

        else:  # block normal hits first
            used_on_hits = min(exp_save, exp_hits)
            remaining_hits = exp_hits - used_on_hits
            # block the crits with the rest of dice
            remaining_saves = exp_save - used_on_hits
            remaining_crits = max(0, exp_crits - (remaining_saves / 2.0))

        self.dmg_dealt = (remaining_crits * self.weapon.crit) + (remaining_hits * self.weapon.dmg) + devastating_wounds
        logging.debug("ShootPhase: %s vs %s with %s -> EV Dealt: %.2f (Crits: %.2f, Hits: %.2f, Saves: %.2f)",
                      self.attacker.name, self.defender.name, self.weapon.name, self.dmg_dealt, exp_crits, exp_hits, exp_save)

        # After effects ------------------------------------------------------------------------------------------------
        for effect in self.weapon.post_def_effects:
            if effect.startswith("stun"):
                if exp_crits >= 0.5:
                    self.ap_reduction += 1
            elif effect.startswith("hot"):
                bad_sum = 0
                for roll in range(1, self.weapon.hit):
                    bad_sum += roll * 2
                self.dmg_received = bad_sum / 6.0
            elif effect.startswith("limited"):
                self.weapon.used = True

        self.check_kill_death()
        self.is_resolved = True
        return True


class FightPhase(CombatPhase):
    """Fighting phase class, used for fighting resolution and evaluation"""

    def __init__(self, attacker: OperativeState, defender: OperativeState, weapon_att: Weapon, weapon_def: Weapon):
        """init"""
        super().__init__(attacker, defender, weapon_att)
        self.weapon_defender = weapon_def

    def generate_dice_pool(self, weapon) -> dict:
        """Generate dice expected values of dice pool for operative."""
        atk_count = weapon.atk

        crit_thresh = 6
        for eff in weapon.mid_effects:
            if eff.startswith("lethal"):
                crit_thresh = int(eff.split("_")[1])
                break

        p_crit = (6 - crit_thresh + 1) / 6.0
        p_hit = (crit_thresh - weapon.hit) / 6.0
        p_miss = (weapon.hit - 1) / 6.00

        p_no_crit = (p_hit + p_miss) ** atk_count
        p_no_hit = p_miss ** atk_count
        p_no_miss = (p_crit + p_hit) ** atk_count
        p_only_hit = p_hit ** atk_count

        exp_crits = atk_count * p_crit
        exp_hits = atk_count * p_hit
        exp_miss = atk_count * p_miss

        for eff in weapon.mid_effects:
            if eff.startswith("severe"):
                chance = p_no_crit - p_no_hit
                exp_crits += chance
                exp_hits -= chance
            elif eff.startswith("punishing"):
                chance = 1.0 - p_no_crit - p_no_miss + p_only_hit
                exp_hits += chance
                exp_miss -= chance

        return {
            'crits': exp_crits,
            'hits': exp_hits,
            'dmg': weapon.dmg,
            'crit_dmg': weapon.crit,
            'weapon': weapon
        }

    def simulate(self):
        """Simulate fighting phase. deterministic approach"""
        attacker_dice = self.generate_dice_pool(self.weapon)
        defender_dice = self.generate_dice_pool(self.weapon_defender)

        att_w = self.attacker.wounds
        def_w = self.defender.wounds

        attacker_turn = True
        att_shock_used = False
        def_shock_used = False

        att_crits = attacker_dice['crits']
        att_hits = attacker_dice['hits']
        def_crits = defender_dice['crits']
        def_hits = defender_dice['hits']

        # Pre Combat ---------------------------------------------------------------------------------------------------
        for effect in self.weapon.mid_effects:
            if effect.startswith('devastating'):
                dmg = int(effect.split('_')[1]) * att_crits
                def_w -= dmg
                self.dmg_dealt += dmg

        for effect in self.weapon_defender.mid_effects:
            if effect.startswith('devastating'):
                dmg = int(effect.split('_')[1]) * def_crits
                att_w -= dmg
                self.dmg_received += dmg

        # main fight loop
        while (att_crits >= 0.01 or att_hits >= 0.01) and (def_crits >= 0.01 or def_hits >= 0.01):
            if attacker_turn:
                has_crit = att_crits >= 0.01
                # use crit or basic if not any crit left
                spend = min(1.0, att_crits) if has_crit else min(1.0, att_hits)
                # want to maximalize dmg
                future_dmg = ((att_crits - spend) * attacker_dice['crit_dmg'] + att_hits * attacker_dice[
                    'dmg']) if has_crit \
                    else (att_crits * attacker_dice['crit_dmg'] + (att_hits - spend) * attacker_dice['dmg'])
                # able to kill defender or not
                needs_to_strike = def_w > 0 and (future_dmg < def_w or (def_crits < 0.01 and def_hits < 0.01))

                if needs_to_strike:
                    # strike
                    dmg = spend * (attacker_dice['crit_dmg'] if has_crit else attacker_dice['dmg'])
                    def_w -= dmg
                    self.dmg_dealt += dmg

                    # shock attacker
                    if not att_shock_used and any(eff.startswith("shock") for eff in self.weapon.mid_effects):
                        discard = min(1.0, def_hits)
                        def_hits -= discard
                        att_shock_used = True
                else:
                    # block
                    def_is_brutal = any(eff.startswith("brutal") for eff in self.weapon_defender.mid_effects)
                    can_parry = not (def_is_brutal and not has_crit)  # Brutal ignores normal hits for parrying

                    if can_parry and has_crit and def_crits >= 0.01:
                        def_crits -= spend
                    elif can_parry and def_hits >= 0.01:
                        def_hits -= spend
                    else:
                        # nothing to block (or prevented by Brutal) -> strike
                        dmg = spend * (attacker_dice['crit_dmg'] if has_crit else attacker_dice['dmg'])
                        def_w -= dmg
                        self.dmg_dealt += dmg

                # count it in
                if has_crit:
                    att_crits -= spend
                else:
                    att_hits -= spend

                if def_w <= 0:
                    break
                attacker_turn = False

            else:  # defender is active
                has_crit = def_crits >= 0.01
                spend = min(1.0, def_crits) if has_crit else min(1.0, def_hits)

                # defender blocks when he knows he survives
                incoming_dmg = (att_crits * attacker_dice['crit_dmg']) + (att_hits * attacker_dice['dmg'])
                is_dead_anyway = (def_w - incoming_dmg) <= 0

                can_parry_crit = has_crit and att_crits >= 0.01
                can_parry_hit = att_hits >= 0.01

                # brutal effect from attacker
                att_is_brutal = any(eff.startswith("brutal") for eff in self.weapon.mid_effects)
                if att_is_brutal and not has_crit:
                    can_parry_crit = False
                    can_parry_hit = False

                if not is_dead_anyway and (can_parry_crit or can_parry_hit):
                    # parry
                    if can_parry_crit:
                        att_crits -= spend
                    elif can_parry_hit:
                        att_hits -= spend
                    else:
                        att_hits -= spend
                else:
                    # Strike - will be dead anyway
                    dmg = spend * (defender_dice['crit_dmg'] if has_crit else defender_dice['dmg'])
                    att_w -= dmg
                    self.dmg_received += dmg

                    # shock defender
                    if not def_shock_used and any(eff.startswith("shock") for eff in self.weapon_defender.mid_effects):
                        discard = min(1.0, att_hits)
                        att_hits -= discard
                        def_shock_used = True

                # calc it in
                if has_crit:
                    def_crits -= spend
                else:
                    def_hits -= spend

                if att_w <= 0:
                    break
                attacker_turn = True

        # Resolve remaining uncontested dice
        while att_crits >= 0.01 or att_hits >= 0.01:
            has_crit = att_crits >= 0.01
            spend = min(1.0, att_crits) if has_crit else min(1.0, att_hits)
            dmg = spend * (attacker_dice['crit_dmg'] if has_crit else attacker_dice['dmg'])
            def_w -= dmg
            self.dmg_dealt += dmg

            if has_crit:
                att_crits -= spend
            else:
                att_hits -= spend
            if def_w <= 0:
                break

        while def_crits >= 0.01 or def_hits >= 0.01:
            has_crit = def_crits >= 0.01
            spend = min(1.0, def_crits) if has_crit else min(1.0, def_hits)
            dmg = spend * (defender_dice['crit_dmg'] if has_crit else defender_dice['dmg'])
            att_w -= dmg
            self.dmg_received += dmg

            if has_crit:
                def_crits -= spend
            else:
                def_hits -= spend
            if att_w <= 0:
                break

        # Post combat --------------------------------------------------------------------------------------------------
        if any(eff.startswith("stun") for eff in self.weapon.post_def_effects):
            if self.dmg_dealt > 0:
                self.ap_reduction = 1

        # Defender stun processing could theoretically reduce active operative's AP,
        # but typical KT logic limits active AP reduction tracking to the active unit's phase.
        if any(eff.startswith("stun") for eff in self.weapon_defender.post_def_effects):
            if self.dmg_received > 0:
                self.ap_reduction = max(0, self.ap_reduction - 1)  # Note: depends on how you handle AP in NodeState

        self.wounds_attacker = max(0, round(att_w, 1))
        self.wounds_defender = max(0, round(def_w, 1))
        self.check_kill_death()
        self.is_resolved = True
        return True
