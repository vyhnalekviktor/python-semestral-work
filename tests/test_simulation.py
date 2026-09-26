# @generated "partially" Gemini CLI: Mostly written by myself, but with some AI assistance for minor issues.
# pylint: disable=redefined-outer-name, protected-access
"""basic tests for simulation.py"""
import time
import pytest
from shapely.geometry import Point
from flexmock import flexmock
from app.src.simulator.simulation import SimulationEngine
from app.src.models import GameState
from app.src.simulator.sim_models import NodeState, OperativeState

@pytest.fixture
def mock_game_state():
    """create a small game state instance"""
    json_mock = {
        "simulation_context": {
            "active_faction": "space_marines",
            "active_operative_name": "Intercessor",
            "user_goal": "KILL"
        },
        "map": {
            "obstacles": [{"x": 10, "y": 10, "w": 2, "h": 2}],
            "objectives": [{"x": 5, "y": 5}]
        },
        "operatives": {
            "space_marines": {
                "0": {"type": "intercessor", "x": 0, "y": 0, "order": "engage"}
            },
            "death_guard": {
                "0": {"type": "plague_marine", "x": 8, "y": 8, "order": "engage"}
            }
        }
    }

    # Create mock weapon with all required attributes
    # Note: using strings for ranged_type as simulation engine expects
    mock_weapon = flexmock(
        name="Bolter", ranged_type="long", range=100, atk=4, hit=3, dmg=3, crit=4, used=False,
        pre_att_effects=[], mid_effects=[], post_def_effects=[]
    )

    # Mock database calls that GameState.__init__ makes
    flexmock(GameState).should_receive("load_operatives").and_return({
        "space_marines": [flexmock(name="Intercessor", wounds=14, apl=3, move=6, center=Point(0,0), order="engage", weapons=[mock_weapon], abilities=[])],
        "death_guard": [flexmock(name="Plague Marine", wounds=14, apl=3, move=5, center=Point(8,8), order="engage", weapons=[mock_weapon], abilities=[])]
    })
    flexmock(GameState).should_receive("load_weapons").and_return(True)

    gs = GameState(json_mock)
    # Manually set some things for easier testing
    gs.user_goal = "kill"
    return gs

def test_engine_init(mock_game_state):
    """does it even start?"""
    engine = SimulationEngine(mock_game_state)
    assert engine.beam_width == 200
    assert engine.time_limit > 0

def test_calc_positional_heuristic_kill(mock_game_state):
    """check calculating of score"""
    engine = SimulationEngine(mock_game_state)

    # Node 1: Close to enemy (at 8,8)
    node1 = NodeState(
        "Intercessor", "positioning",
        (OperativeState("Intercessor", 14, 2, 7, 7, "engage", True),
         OperativeState("Plague Marine", 14, 3, 8, 8, "engage", False)),
        ()
    )

    # Node 2: Far from enemy
    node2 = NodeState(
        "Intercessor", "positioning",
        (OperativeState("Intercessor", 14, 2, 0, 0, "engage", True),
         OperativeState("Plague Marine", 14, 3, 8, 8, "engage", False)),
        ()
    )

    score1 = engine._calc_positional_heuristic(node1)
    score2 = engine._calc_positional_heuristic(node2)

    # In KILL goal, being close to enemy (dist=1.4) should be better than far (dist=11.3)
    assert score1 > score2

def test_check_cover_heuristic(mock_game_state):
    """does calculation for cover work?"""
    engine = SimulationEngine(mock_game_state)
    # Obstacle is at (10,10) size 2x2. Box(10,10,12,12)

    # Near obstacle
    op_near = OperativeState("Op", 10, 3, 9.5, 9.5, "engage", True)
    assert engine._check_cover_heuristic(op_near) is True

    # Far from obstacle
    op_far = OperativeState("Op", 10, 3, 0, 0, "engage", True)
    assert engine._check_cover_heuristic(op_far) is False

def test_zobrist_hashing_consistency(mock_game_state):
    """basic basic tests for hashing"""
    engine = SimulationEngine(mock_game_state)
    root = engine._create_root_node()
    h1 = engine.hash_node(root)
    h2 = engine.hash_node(root)
    assert h1 == h2

    # change something
    op_moved = root.operatives[0]._replace(x=10.0)
    node_moved = root._replace(operatives=(op_moved,) + root.operatives[1:])
    h3 = engine.hash_node(node_moved)
    assert h1 != h3

def test_generate_target_points_capture(mock_game_state):
    """does the system want to capture while capturing?"""
    mock_game_state.user_goal = "capture"
    engine = SimulationEngine(mock_game_state)
    root = engine._create_root_node()
    points = engine._generate_target_points(root)
    # should contain objective points (5,5) or nearby
    assert any(abs(p[0]-5) <= 1 and abs(p[1]-5) <= 1 for p in points)

def test_full_simulation_run(mock_game_state):
    """full work test. if ti finishes, not if it is right."""
    engine = SimulationEngine(mock_game_state)
    # speed up for test
    engine.time_limit = 0.5
    results = engine.run()

    assert isinstance(results, list)
    assert len(results) > 0
    assert "rank" in results[0]
    assert "sequence" in results[0]
    # first action should be a move
    assert results[0]["sequence"][0].startswith("Move")

def test_scenario_guaranteed_kill(mock_game_state):
    """Scenario: Attacker is very close to a weak enemy. Expected: Attack sequence."""
    mock_game_state.user_goal = "kill"
    engine = SimulationEngine(mock_game_state)

    # Force state: active is already in position, but still in positioning phase
    root = engine._create_root_node()
    new_ops = list(root.operatives)
    # active op at 7.5, 7.5 (close to enemy)
    new_ops[0] = new_ops[0]._replace(x=7.5, y=7.5, ap_left=3)
    # enemy op at 8.0, 8.0 with 1 HP
    new_ops[1] = new_ops[1]._replace(x=8.0, y=8.0, wounds=1)

    # In our engine, action phase (Shoot/Fight) only happens AFTER a Move
    # OR if we manually trigger _generate_terminal_actions on the positioning node.
    node = root._replace(operatives=tuple(new_ops), phase="positioning")

    # Let's see if the engine finds a sequence ending in an attack
    engine.time_limit = 1.0
    res = engine._search(node, 3, time.time()) # Depth 3: Move -> Action -> Resolve

    sequence = str(res['sequence'])
    # Should either stay put and shoot, or move slightly and shoot
    assert "Shoot" in sequence or "Fight" in sequence or "End Activation" in sequence
    # If the score is higher for killing, it will pick that branch.
    assert res['score'] > 0

def test_scenario_survival_priority(mock_game_state):
    """Scenario: Goal is SURVIVE, threat is nearby. Expected: Move away or into cover."""
    mock_game_state.user_goal = "survive"
    engine = SimulationEngine(mock_game_state)

    # Obstacle is at (10,10, 12,12)
    # Active is at 5,5 (far from cover)
    # Enemy is at 5.5, 5.5 (big threat)
    root = engine._create_root_node()
    new_ops = list(root.operatives)
    new_ops[0] = new_ops[0]._replace(x=5, y=5, ap_left=2)
    new_ops[1] = new_ops[1]._replace(x=5.5, y=5.5, wounds=14)
    node = root._replace(operatives=tuple(new_ops), phase="positioning")

    # Score for initial position (no cover, enemy close)
    score_initial = engine._calc_positional_heuristic(node)

    # Find a node where we moved to cover (near 10,10)
    op_moved = new_ops[0]._replace(x=9.5, y=9.5)
    node_moved = node._replace(operatives=(op_moved, new_ops[1]))
    score_moved = engine._calc_positional_heuristic(node_moved)

    # In SURVIVE goal, being in cover/further should be better
    assert score_moved > score_initial

def test_scenario_damage(mock_game_state):
    """Scenario: Goal is DAMAGE, enemy is in range. Expected: High score for dealing damage."""
    mock_game_state.user_goal = "damage"
    engine = SimulationEngine(mock_game_state)

    # node 1: Enemy at full health, no actions taken
    node1 = NodeState(
        "Intercessor", "positioning",
        (OperativeState("Intercessor", 14, 2, 7, 7, "engage", True),
         OperativeState("Plague Marine", 14, 3, 8, 8, "engage", False)),
        ()
    )

    # node 2: Enemy took damage (wounds reduced to 5) after a simulated attack
    node2 = NodeState(
        "Intercessor", "terminal",
        (OperativeState("Intercessor", 14, 1, 7, 7, "engage", True),
         OperativeState("Plague Marine", 5, 3, 8, 8, "engage", False)),
        ("Shoot:Plague Marine:Bolter",)
    )

    score1 = engine._evaluate_node(node1)
    score2 = engine._evaluate_node(node2)

    # DAMAGE goal, a state where the enemy has fewer wounds and an attack occurred should score significantly higher
    assert score2 > score1

def test_scenario_capture(mock_game_state):
    """Scenario: Goal is CAPTURE, active op is near objective. Expected: Score increases when closer to objective."""
    mock_game_state.user_goal = "capture"
    engine = SimulationEngine(mock_game_state)
    # objective is at (5, 5)
    # node 1: Active op is far from objective (at 0, 0)
    node1 = NodeState(
        "Intercessor", "positioning",
        (OperativeState("Intercessor", 14, 2, 0, 0, "engage", True),
         OperativeState("Plague Marine", 14, 3, 8, 8, "engage", False)),
        ()
    )

    # node 2: Active op is on the objective (at 5, 5)
    node2 = NodeState(
        "Intercessor", "positioning",
        (OperativeState("Intercessor", 14, 2, 5, 5, "engage", True),
         OperativeState("Plague Marine", 14, 3, 8, 8, "engage", False)),
        ()
    )

    score1 = engine._calc_positional_heuristic(node1)
    score2 = engine._calc_positional_heuristic(node2)

    # in CAPTURE goal, being on/near the objective should score higher
    assert score2 > score1

def test_adversarial_lookahead(mock_game_state):
    """Scenario: Active op is within range of enemy threat. Expected: Positive threat score."""
    engine = SimulationEngine(mock_game_state)

    # Identify the actual names used in the mock_game_state
    active_name = mock_game_state.active_operative
    enemy_team = "death_guard" if mock_game_state.active_faction == "space_marines" else "space_marines"
    enemy_name = mock_game_state.operatives[enemy_team][0].name

    # active op at (5, 5)
    # enemy at (6, 6) - very close, definitely a threat
    node_dangerous = NodeState(
        active_name, "terminal",
        (OperativeState(active_name, 14, 0, 5, 5, "engage", True),
         OperativeState(enemy_name, 14, 3, 6, 6, "engage", False)),
        ("End Activation",)
    )

    # enemy at (25, 25) - far away, should not be a threat
    node_safe = NodeState(
        active_name, "terminal",
        (OperativeState(active_name, 14, 0, 5, 5, "engage", True),
         OperativeState(enemy_name, 14, 3, 25, 25, "engage", False)),
        ("End Activation",)
    )

    threat_high = engine._adversarial_lookahead(node_dangerous)
    threat_none = engine._adversarial_lookahead(node_safe)

    assert threat_high > 0
    assert threat_none == 0
