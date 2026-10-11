import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trailear.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            started_at TEXT,
            ended_at TEXT,
            lat REAL,
            lon REAL,
            summary_text TEXT
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS detections (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            timestamp TEXT,
            species_common TEXT,
            species_scientific TEXT,
            confidence REAL,
            lat REAL,
            lon REAL
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS species_info (
            scientific_name TEXT PRIMARY KEY,
            short_description TEXT
        )
        """
    )
    conn.commit()
    conn.close()