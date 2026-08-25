"""wasserdb - SQLite-Datenhaltung fuer den Wasserverbrauch (LJ18A3)."""

import os
import sqlite3

from .schema import SCHEMA_STATEMENTS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "data")
DB_PFAD = os.path.join(DATA_DIR, "wasserverbrauch.db")
ROHDATEN_AUFBEWAHRUNG_TAGE = 14


def get_connection():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PFAD, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    try:
        for statement in SCHEMA_STATEMENTS:
            conn.execute(statement)
        conn.commit()
    finally:
        conn.close()
