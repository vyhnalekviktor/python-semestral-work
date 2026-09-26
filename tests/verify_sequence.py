"""Module for testing right AP usage: move -> capture -> shoot"""
from shapely import Point
from app.src.models import Operative, Weapon
from app.src.simulator.simulation import SimulationEngine


def test_move_capture_shoot_sequence():
    """just do it"""
    # Setup for 3AP model
    op = Operative(
        name="Intercessor",
        team="space_marines",
        apl=3,
        move=6,
        save=3,
        wounds=12,
        weapons=[],
        abilities=[],
        pos_x=0,
        pos_y=0,
        order="Engage"
    )
    # Give him a weapon
    op.weapons = [
        Weapon(name="Bolter", ranged_type="long", atk=4, hit=3, dmg=3, crit=4, max_range=0, special_effects=[],
               operatives=[])
    ]
    enemy = Operative(
        name="Enemy",
        team="death_guard",
        apl=2,
        move=6,
        save=3,
        wounds=12,
        weapons=[],
        abilities=[],
        pos_x=5,
        pos_y=0,
        order="Engage"
    )
    # Objective at (2, 0)
    obj = Point(2, 0).buffer(0.63)

    class MockGameState:
        """mock game state class"""

        def __init__(self, op, enemy, obj):
            self.active_faction = "space_marines"
            self.active_operative = "Intercessor"
            self.user_goal = "capture"  # Goal is capture, but should be able to shoot too
            self.operatives = {"space_marines": [op], "death_guard": [enemy]}
            self.objectives = [obj]
            self.obstacles = []
            self.obstacle_tree = None

    gs = MockGameState(op, enemy, obj)
    engine = SimulationEngine(gs)

    # Run simulation with enough depth
    # Depth 1: Move
    # Depth 2: Capture
    # Depth 3: Shoot
    # Depth 4: End
    engine.time_limit = 2.0
    results = engine.run()

    # Check sequences
    found_ideal = False
    for res in results:
        seq = res['sequence']
        print(f"Sequence: {seq}")
        if any("Move" in s for s in seq) and any("Capture" in s for s in seq) and any("Shoot" in s for s in seq):
            found_ideal = True
            break

    assert found_ideal, "Sequence Move -> Capture -> Shoot not found in results!"
