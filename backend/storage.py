from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent / "macrofx.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    series TEXT NOT NULL,
    country TEXT,
    currency TEXT,
    timestamp TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT,
    frequency TEXT,
    release_timestamp TEXT,
    previous_value REAL,
    revision INTEGER DEFAULT 0,
    url TEXT,
    UNIQUE(source, series, timestamp)
);
CREATE INDEX IF NOT EXISTS idx_obs_series_date ON observations(series, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_obs_currency_date ON observations(currency, timestamp DESC);
"""

def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)

def upsert_observations(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    sql = """INSERT INTO observations
        (source,series,country,currency,timestamp,value,unit,frequency,release_timestamp,previous_value,revision,url)
        VALUES (:source,:series,:country,:currency,:timestamp,:value,:unit,:frequency,:release_timestamp,:previous_value,:revision,:url)
        ON CONFLICT(source,series,timestamp) DO UPDATE SET
          value=excluded.value, previous_value=excluded.previous_value,
          revision=excluded.revision, release_timestamp=excluded.release_timestamp,
          unit=excluded.unit, frequency=excluded.frequency, url=excluded.url
    """
    with connect() as conn:
        conn.executemany(sql, rows)
        return conn.total_changes

def latest(series: str, limit: int = 24) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM observations WHERE series=? ORDER BY timestamp DESC LIMIT ?", (series, limit)).fetchall()
    return [dict(r) for r in rows]
