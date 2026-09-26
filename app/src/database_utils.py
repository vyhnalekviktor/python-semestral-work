"""Functions to create, populate, clear and delete datasheets for my operators & weapons.
Mostly would use it to generate datasheets DB."""
import json
import sqlite3
import os
import logging
from pathlib import Path


TEAMS = ["space_marines", "death_guard"]

CURRENT_DIR = Path(__file__).resolve().parent
DATASHEETS = CURRENT_DIR /  "datasheets.db"
ARMY_PATH = CURRENT_DIR / "army.json"

# config for debug messages & logs
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def init_db():
    """Create empty database. Call it manually at initialization or if deleted."""
    try:
        path = DATASHEETS
        if os.path.exists(path):
            logging.warning("init_db(): database already exists.")
            return False
        conn = sqlite3.connect(path)
        conn.close()
    except sqlite3.Error as e:
        logging.error("init_db(): %s.", e)

    logging.info("init_db(): empty database created successfully.")
    return True
def create_db():
    """Create DB, if not exists: add tables and add columns."""
    init_db()

    conn = sqlite3.connect(DATASHEETS)
    cursor = conn.cursor()

    for team in TEAMS:
        # create operative tables with columns (col weapons is in json str)
        sql_query = f"""CREATE TABLE IF NOT EXISTS {team}_operatives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            team TEXT NOT NULL,
            apl INTEGER NOT NULL,
            move INTEGER NOT NULL,
            save INTEGER NOT NULL,
            wounds INTEGER NOT NULL,
            weapons TEXT NOT NULL,
            abilities TEXT NOT NULL
            );"""

        try:
            cursor.execute(sql_query)
            conn.commit()
        except sqlite3.Error as e:
            logging.error("create_db(): %s, while creating %s operatives table.", e, team)

    for team in TEAMS:
        # create weapons tables with columns (col operatives + special_effect are json str)
        sql_query = f"""CREATE TABLE IF NOT EXISTS {team}_weapons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            ranged_type BOOLEAN NOT NULL,
            atk INTEGER NOT NULL,
            hit INTEGER NOT NULL,
            dmg INTEGER NOT NULL,
            crit INTEGER NOT NULL,
            range INTEGER NOT NULL,
            special_effects TEXT NOT NULL,
            operatives TEXT NOT NULL
            );"""
        try:
            cursor.execute(sql_query)
            conn.commit()
        except sqlite3.Error as e:
            logging.error("create_db(): %s, while creating %s weapons table.", e, team)

    conn.close()
    logging.info("create_db() ran successfully.")

    import_from_json(ARMY_PATH)

def import_from_json(file):
    """Import all operative and weapon data from json file."""
    # pylint: disable=import-outside-toplevel
    from app.src.models import Operative, Weapon
    if not (os.path.exists(file) and os.path.exists(DATASHEETS)):
        logging.error("import_from_json(): file does not exist.")
        return

    # Clear existing data to prevent duplicates
    clear_db(operatives=True, weapons=True)

    try:
        with open(file, "r", encoding="utf-8") as json_file:
            data = json.load(json_file)

        conn = sqlite3.connect(DATASHEETS)
        cursor = conn.cursor()

        for team in TEAMS:
            # coding in json
            ops_key = f"{team}_ops"
            weapon_key = f"{team}_weapons"

            if ops_key in data:
                # @generated [all] Gemini 3 : parse json to Operative object -> into tuple for sql (only next line)
                ops_to_db = [Operative(**item).to_tuple() for item in data[ops_key]]

                # ? to keep db safe
                sql_query = f"""INSERT INTO {team}_operatives(
                    name, team, apl, move, save, wounds, weapons, abilities)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?)"""

                cursor.executemany(sql_query, ops_to_db)
            else:
                logging.error("import_from_json(): %s operatives not valid in json", team)

            if weapon_key in data:
                # written by me similarly to AI generated
                weapons_to_db = [Weapon(**item).to_tuple() for item in data[weapon_key]]

                # ? to keep db safe
                sql_query = f"""INSERT INTO {team}_weapons(
                    name, ranged_type, atk, hit, dmg, crit, range, special_effects, operatives)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)"""
                # time efficient way
                cursor.executemany(sql_query, weapons_to_db)
            else:
                logging.error("import_from_json(): %s weapons not valid in json", team)

        conn.commit()
        conn.close()
        logging.info("import_from_json(): successfully completed.")

    except json.JSONDecodeError as e:
        logging.error("import_from_json(): %s.", e)
    except sqlite3.Error as e:
        logging.error("import_from_json(): %s.", e)

def remove_db():
    """Remove database file. use with caution!"""
    try:
        os.remove(DATASHEETS)
        logging.info("remove_db(): successfully removed database.")
    except FileNotFoundError:
        logging.error("remove_db(): database does not exist.")

def clear_db(operatives = False, weapons =  False):
    """Clear database file. Result are empty tables. Choose in arguments what to clear."""
    conn = sqlite3.connect(DATASHEETS)
    cursor = conn.cursor()
    do = []
    if operatives:
        do.append("operatives")
    if weapons:
        do.append("weapons")
    try:
        for category in do:
            for team in TEAMS:
                cursor.execute(f"DELETE FROM {team}_{category}")
                # null the id autoincrement
                cursor.execute("DELETE FROM sqlite_sequence WHERE name=?", (f"{team}_{category}",))
                conn.commit()
                logging.info("clear_db(): successfully removed %s %s table.", team, category)
    except sqlite3.Error as e:
        logging.error("clear_db(): %s.", e)
        return

    conn.close()
    logging.info("clear_db() ran successfully.")

def duplicate_db(src_path = DATASHEETS):
    """Duplicate database safely using sqlite3 built-in function."""
    dest_path = "../copy_of_datasheets.db"
    if not os.path.exists(src_path):
        logging.error("duplicate_db(): source path does not exist.")
        return
    try:
        src_conn = sqlite3.connect(src_path)
        dest_conn = sqlite3.connect(dest_path)

        with dest_conn:
            src_conn.backup(dest_conn)

        dest_conn.close()
        src_conn.close()
        logging.info("duplicate_db(): successfully duplicated database to %s.", dest_path)
    except sqlite3.Error as e:
        logging.error("duplicate_db(): %s.", e)

def get_operative(operative_name: str, team: str) -> tuple | None:
    """Get operative from database. Returns tuple similar to DB columns"""
    if not os.path.exists(DATASHEETS):
        logging.error("get_operative(): database does not exist.")
        return None
    operative_name = operative_name.lower()
    team = team.lower()
    conn = sqlite3.connect(DATASHEETS)
    cursor = conn.cursor()

    sql_query = f"SELECT * FROM {team}_operatives WHERE name=?"
    cursor.execute(sql_query, (operative_name,))
    result = cursor.fetchone()
    conn.close()

    if result is None or None in result:
        logging.error("get_operative(): %s operative not found or incomplete.", operative_name)
        return None

    logging.info("get_operative(): %s operative found.", operative_name)
    return result

def get_weapon(weapon_name: str, team: str) -> tuple | None:
    """Get weapon from database. Returns tuple similar to DB columns"""
    if not os.path.exists(DATASHEETS):
        logging.error("get_operative(): database does not exist.")
        return None

    weapon_name = weapon_name.lower()
    team = team.lower()
    conn = sqlite3.connect(DATASHEETS)
    cursor = conn.cursor()

    sql_query = f"SELECT * FROM {team}_weapons WHERE name=?"
    cursor.execute(sql_query, (weapon_name,))
    result = cursor.fetchone()
    conn.close()

    if result is None or None in result:
        logging.error("get_weapon(): %s weapon not found or incomplete.", weapon_name)
        return None

    logging.info("get_weapon(): %s weapon found.", weapon_name)
    return result

def get_all_operatives(team: str) -> list:
    """Get all operatives for a specific team from the database."""
    if not os.path.exists(DATASHEETS):
        logging.error("get_all_operatives(): database does not exist.")
        return []
    team = team.lower()
    if team not in TEAMS:
        logging.error("get_all_operatives(): invalid team %s", team)
        return []
    conn = sqlite3.connect(DATASHEETS)
    cursor = conn.cursor()
    sql_query = f"SELECT * FROM {team}_operatives"
    cursor.execute(sql_query)
    results = cursor.fetchall()
    conn.close()
    return results
