# @generated "partially" Gemini CLI: Mostly written by myself, but with some AI assistance for minor issues.
# pylint: disable=redefined-outer-name, protected-access
"""test my MAIN classes for game state, operatives and weapons"""
import json
import pytest
from app.src.models import Operative, Weapon, GameState

def test_operative_init_and_tuple():
    """Test Operative initialization and to_tuple method."""
    op = Operative(
        name="Intercessor",
        team="space_marines",
        apl=3,
        move=6,
        save=3,
        wounds=14,
        weapons=["Bolter"],
        abilities=["Angel of Death"],
        pos_x=10,
        pos_y=20,
        order="engage"
    )

    assert op.name == "Intercessor"
    assert op.team == "space_marines"
    assert op.center.x == 10
    assert op.center.y == 20
    assert op.order == "engage"

    expected_tuple = (
        "Intercessor", "space_marines", 3, 6, 3, 14,
        json.dumps(["Bolter"]), json.dumps(["Angel of Death"])
    )
    assert op.to_tuple() == expected_tuple

def test_operative_update_position():
    """Test Operative update_position method."""
    op = Operative("Op", "team", 2, 6, 4, 10, [], [])
    op.update_position(5, 5)
    assert op.center.x == 5
    assert op.center.y == 5
    assert op.base.centroid.x == pytest.approx(5)
    assert op.base.centroid.y == pytest.approx(5)

@pytest.mark.parametrize(
    "effects, expected_pre, expected_mid, expected_post",
    [
        (["Heavy", "Piercing 1", "Stun"], ["Heavy"], ["Piercing 1"], ["Stun"]),
        (["Silent", "Lethal 5+"], ["Silent"], ["Lethal 5+"], []),
        (["Hot", "Brutal"], [], ["Brutal"], ["Hot"]),
    ]
)
def test_weapon_organize_effects_success(effects, expected_pre, expected_mid, expected_post):
    """Test successful organization of weapon effects."""
    weapon = Weapon("Bolter", True, 4, 3, 3, 4, 0, effects, ["Intercessor"])
    assert weapon.organize_effects() is True
    assert weapon.pre_att_effects == expected_pre
    assert weapon.mid_effects == expected_mid
    assert weapon.post_def_effects == expected_post

def test_weapon_organize_effects_failure():
    """Test organization failure with unknown effect."""
    weapon = Weapon("Mystery", True, 4, 3, 3, 4, 0, ["UnknownEffect"], ["Op"])
    assert weapon.organize_effects() is False

def test_weapon_to_tuple():
    """Test Weapon to_tuple method."""
    weapon = Weapon("Sword", False, 4, 3, 3, 4, 0, ["Lethal 5+"], ["Intercessor"])
    expected_tuple = (
        "Sword", False, 4, 3, 3, 4, 0,
        json.dumps(["Lethal 5+"]), json.dumps(["Intercessor"])
    )
    assert weapon.to_tuple() == expected_tuple

def test_gamestate_load_obstacles():
    """Test parsing of obstacle data into shapely boxes."""
    obs_data = [{"x": 10, "y": 10, "w": 5, "h": 5}]
    obstacles = GameState.load_obstacles(obs_data)
    assert len(obstacles) == 1
    assert obstacles[0].bounds == (10.0, 10.0, 15.0, 15.0)
    assert obstacles[0].area == 25.0

def test_gamestate_load_objectives():
    """Test parsing of objective data into buffered points."""
    obj_data = [{"x": 5, "y": 5}]
    objectives = GameState.load_objectives(obj_data)
    assert len(objectives) == 1
    # Point(5,5).buffer(0.63)
    assert objectives[0].centroid.x == pytest.approx(5.0)
    assert objectives[0].area > 1.2  # pi * r^2

def test_gamestate_invalid_json():
    """Test GameState handling of malformed JSON."""
    with pytest.raises(Exception):
        # Should fail if critical keys are missing
        GameState({"simulation_context": {}})

def test_operative_invalid_wounds():
    """Test Operative with 0 or negative wounds (terminal state)."""
    op = Operative("DeadOp", "sm", 3, 6, 3, 0, [], [])
    assert op.is_alive is True # Still initialized, but wounds are 0
    # In simulation it would be handled by wounds check
