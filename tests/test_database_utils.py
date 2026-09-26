# @generated [all] Gemini-3 2026-04-05: only given collab notebook from courses and my script, prompt: test it!!
# pylint: disable=redefined-outer-name, protected-access
"""Test my database utilities"""
import os
import sqlite3
import pytest
from flexmock import flexmock
from app.src import database_utils



@pytest.fixture
def mock_db(tmp_path, monkeypatch):
    """Fixture to redirect DATASHEETS to a temporary file for testing."""
    test_db_path = tmp_path / "test_datasheets.db"
    # Monkeypatch the constant in the module
    monkeypatch.setattr(database_utils, "DATASHEETS", test_db_path)
    return test_db_path

def test_init_db(mock_db):
    """Test that init_db creates an empty file."""
    assert database_utils.init_db() is True
    assert os.path.exists(mock_db)
    # Second call should return False as it already exists
    assert database_utils.init_db() is False

def test_create_db(mock_db):
    """Test that create_db creates tables."""
    # Note: create_db calls import_from_json at the end,
    # which might fail if army.json isn't found or is invalid.
    # We'll mock import_from_json to focus on table creation.
    flexmock(database_utils).should_receive("import_from_json").once()

    database_utils.create_db()

    conn = sqlite3.connect(mock_db)
    cursor = conn.cursor()

    # Check if tables exist for one team
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='space_marines_operatives'")
    assert cursor.fetchone() is not None
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='space_marines_weapons'")
    assert cursor.fetchone() is not None

    conn.close()

def test_get_operative_not_found():
    """Test get_operative when database or operative doesn't exist."""
    # 1. Database doesn't exist yet
    assert database_utils.get_operative("NonExistent", "space_marines") is None

    # 2. Database exists but operative doesn't
    database_utils.init_db()
    database_utils.create_db() # this creates tables
    assert database_utils.get_operative("NonExistent", "space_marines") is None

def test_get_operative_success(mock_db):
    """Test successful retrieval of an operative."""
    database_utils.create_db()

    conn = sqlite3.connect(mock_db)
    cursor = conn.cursor()
    # Manually insert a mock operative
    cursor.execute("""
        INSERT INTO space_marines_operatives (name, team, apl, move, save, wounds, weapons, abilities)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, ("test_op", "space_marines", 3, 6, 3, 12, '["Bolter"]', '[]'))
    conn.commit()
    conn.close()

    result = database_utils.get_operative("test_op", "space_marines")
    assert result is not None
    assert result[1] == "test_op"
    assert result[3] == 3

def test_get_weapon_success(mock_db):
    """Test successful retrieval of a weapon."""
    database_utils.create_db()

    conn = sqlite3.connect(mock_db)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO space_marines_weapons (name, ranged_type, atk, hit, dmg, crit, range, special_effects, operatives)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("test_weapon", 1, 4, 3, 3, 4, 6, '[]', '["test_op"]'))
    conn.commit()
    conn.close()

    result = database_utils.get_weapon("test_weapon", "space_marines")
    assert result is not None
    assert result[1] == "test_weapon"
    assert result[3] == 4

def test_clear_db(mock_db):
    """Test clearing the database."""
    database_utils.create_db()

    conn = sqlite3.connect(mock_db)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO space_marines_operatives (name, team, apl, move, save, wounds, weapons, abilities) VALUES (?,?,?,?,?,?,?,?)",
                   ("dummy", "sm", 1, 1, 1, 1, "[]", "[]"))
    conn.commit()
    conn.close()

    database_utils.clear_db(operatives=True)

    conn = sqlite3.connect(mock_db)
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM space_marines_operatives")
    assert cursor.fetchone()[0] == 0
    conn.close()
