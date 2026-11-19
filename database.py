import json
import os
import sqlite3

DB_PATH = os.getenv("DATABASE_PATH", "jaxons_security.sqlite3")


def connect():
    return sqlite3.connect(DB_PATH)


def init_db():
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS settings (
            guild_id INTEGER, key TEXT, value TEXT,
            PRIMARY KEY (guild_id, key)
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER, title TEXT, detail TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")


def get_setting(guild_id, key, default=None):
    with connect() as db:
        row = db.execute(
            "SELECT value FROM settings WHERE guild_id=? AND key=?",
            (guild_id, key)
        ).fetchone()
    return json.loads(row[0]) if row else default


def set_setting(guild_id, key, value):
    with connect() as db:
        db.execute(
            """INSERT INTO settings(guild_id,key,value) VALUES(?,?,?)
            ON CONFLICT(guild_id,key) DO UPDATE SET value=excluded.value""",
            (guild_id, key, json.dumps(value))
        )


def add_incident(guild_id, title, detail):
    with connect() as db:
        db.execute(
            "INSERT INTO incidents(guild_id,title,detail) VALUES(?,?,?)",
            (guild_id, title, detail)
        )


def recent_incidents(guild_id, limit=5):
    with connect() as db:
        return db.execute(
            "SELECT title,detail,created_at FROM incidents WHERE guild_id=? ORDER BY id DESC LIMIT ?",
            (guild_id, limit)
        ).fetchall()
