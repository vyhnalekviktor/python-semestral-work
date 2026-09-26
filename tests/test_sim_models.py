# @generated "partially" Gemini CLI: Mostly written by myself, but with some AI assistance for minor issues.
 # pylint: disable=redefined-outer-name, protected-access
"""test my simulator classes"""
import pytest
from app.src.simulator.sim_models import ShootPhase, FightPhase, OperativeState
from app.src.models import Weapon

@pytest.fixture
def attacker():
    """attacker fixture"""
    return OperativeState("Attacker", 15, 3, 0, 0, "engage", True)

@pytest.fixture
def defender():
    """defender fixture"""
    return OperativeState("Defender", 14, 3, 10, 10, "engage", False)

def test_shoot_phase_basic(attacker, defender):
    """Test basic shooting without special effects."""
    # 4 atk, hit 3+, dmg 3, crit 4
    weapon = Weapon("Bolter", True, 4, 3, 3, 4, 100, [], ["Attacker"])
    weapon.organize_effects()

    phase = ShootPhase(attacker, defender, weapon, cover=False)
    assert phase.simulate() is True
    # hit_prob: 3/6 = 0.5, crit_prob: 1/6 = 0.166...
    # with 4 atk: exp_hits = 2.0, exp_crits = 0.66...
    # defender has 3 dice, save 3+ (4/6 = 0.66...) -> exp_save = 2.0
    # Logic: blocks hits first. exp_save(2.0) blocks exp_hits(2.0).
    # Remaining: 0.66 crits. Dmg = 0.66 * 4 = 2.66...
    assert phase.dmg_dealt == pytest.approx(2.66, rel=1e-2)
    assert phase.is_kill is False

def test_shoot_phase_heavy_moved(attacker, defender):
    """Test that heavy weapon fails if moved."""
    weapon = Weapon("Heavy Bolter", True, 5, 3, 4, 5, 100, ["heavy"], ["Attacker"])
    weapon.organize_effects()

    # has_moved = True
    phase = ShootPhase(attacker, defender, weapon, cover=False, has_moved=True)
    phase.simulate()
    assert phase.is_resolved is True
    assert phase.dmg_dealt == 0

def test_shoot_phase_lethal_and_piercing(attacker, defender):
    """Test lethal and piercing effects."""
    # lethal_5 (crits on 5+), piercing_1 (reduces def dice by 1)
    weapon = Weapon("Plasma", True, 4, 3, 4, 5, 100, ["lethal_5", "piercing_1"], ["Attacker"])
    weapon.organize_effects()

    phase = ShootPhase(attacker, defender, weapon, cover=False)
    phase.simulate()
    # atk 4. hit 5+ (crit) = 2/6, hit 3-4 (normal) = 2/6.
    # exp_crits = 4 * (1/3) = 1.33
    # exp_hits = 4 * (1/3) = 1.33
    # def_dice = 3 - 1 = 2. save 3+ (2/3). exp_save = 2 * (2/3) = 1.33
    # Logic: block hits first. exp_save(1.33) blocks exp_hits(1.33).
    # Remaining: 1.33 crits. Dmg = 1.33 * 5 = 6.66...
    assert phase.dmg_dealt == pytest.approx(6.66, rel=1e-2)

def test_fight_phase_basic(attacker, defender):
    """Test basic melee fight."""
    # att: 4 atk, 3 hit, 3/4 dmg
    w_att = Weapon("Fists", False, 4, 3, 3, 4, 1, [], ["Attacker"])
    w_att.organize_effects()
    # def: 4 atk, 3 hit, 3/4 dmg
    w_def = Weapon("Fists", False, 4, 3, 3, 4, 1, [], ["Defender"])
    w_def.organize_effects()

    phase = FightPhase(attacker, defender, w_att, w_def)
    assert phase.simulate() is True
    # Deterministic fight logic is complex, but with equal stats and no effects,
    # attacker should deal damage first and survive.
    assert phase.dmg_dealt > 0
    assert phase.is_resolved is True

def test_shoot_phase_devastating_wounds(attacker, defender):
    """Test devastating wounds effect (crits deal unblockable damage)."""
    # exp_crits will be 1/6 * 6 = 1.0. devastating_3 should add 3 dmg.
    weapon = Weapon("Sniper", True, 6, 3, 3, 4, 100, ["devastating_3"], ["Attacker"])
    weapon.organize_effects()

    phase = ShootPhase(attacker, defender, weapon, cover=False)
    phase.simulate()
    # Exp crits: 1.0. Exp hits: 3.0. Exp save: 2.0.
    # Logic: block 2 hits with 2 saves. 1 hit remains.
    # Dmg = 1.0 * 4 (crit) + 1.0 * 3 (hit) + 1.0 * 3 (devastating) = 10.0
    assert phase.dmg_dealt == pytest.approx(10.0)

def test_shoot_phase_severe_and_punishing(attacker, defender):
    """Test severe (hits become crits if no crits rolled) and punishing (misses become hits if crit rolled)."""
    # severe: p_no_crit - p_no_hit shifted to crits
    weapon = Weapon("Special", True, 4, 3, 3, 4, 100, ["severe", "punishing"], ["Attacker"])
    weapon.organize_effects()

    phase = ShootPhase(attacker, defender, weapon, cover=False)
    phase.simulate()
    assert phase.is_resolved is True
    assert phase.dmg_dealt > 0

def test_shoot_phase_stun_and_hot(attacker, defender):
    """Test stun (AP reduction) and hot (self damage)."""
    weapon = Weapon("Plasma", True, 4, 3, 5, 6, 100, ["stun", "hot"], ["Attacker"])
    weapon.organize_effects()

    phase = ShootPhase(attacker, defender, weapon, cover=False)
    phase.simulate()
    # hot deals dmg for every roll < hit (3) -> 1, 2. Exp dmg = (1*2 + 2*2)/6 = 1.0
    assert phase.dmg_received == pytest.approx(1.0)
    # stun reduces AP if crits >= 0.5. Exp crits = 4 * 1/6 = 0.66.
    assert phase.ap_reduction == 1

def test_fight_phase_shock_and_stun(attacker, defender):
    """Test shock (removes enemy hit) and stun in melee."""
    w_att = Weapon("Shock Bat", False, 4, 3, 3, 4, 1, ["shock", "stun"], ["Attacker"])
    w_att.organize_effects()
    w_def = Weapon("Fists", False, 4, 3, 3, 4, 1, [], ["Defender"])
    w_def.organize_effects()

    phase = FightPhase(attacker, defender, w_att, w_def)
    phase.simulate()
    assert phase.ap_reduction > 0
    assert phase.is_resolved is True
