"""SQLite database setup and connection management."""

import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.environ.get("COACH_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "coach.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS rides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    filename TEXT UNIQUE NOT NULL,
    sport TEXT,
    sub_sport TEXT,
    duration_s REAL,
    distance_m REAL,
    avg_power INTEGER,
    normalized_power INTEGER,
    max_power INTEGER,
    avg_hr INTEGER,
    max_hr INTEGER,
    avg_cadence INTEGER,
    total_ascent INTEGER,
    total_descent INTEGER,
    total_calories INTEGER,
    tss REAL,
    intensity_factor REAL,
    ftp INTEGER,
    total_work_kj REAL,
    training_effect REAL,
    variability_index REAL,
    best_1min_power INTEGER,
    best_5min_power INTEGER,
    best_20min_power INTEGER,
    best_60min_power INTEGER,
    weight REAL,
    start_lat REAL,
    start_lon REAL
);

CREATE TABLE IF NOT EXISTS ride_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ride_id INTEGER NOT NULL,
    timestamp TEXT,
    power INTEGER,
    heart_rate INTEGER,
    cadence INTEGER,
    speed REAL,
    altitude REAL,
    distance REAL,
    lat REAL,
    lon REAL,
    temperature REAL,
    FOREIGN KEY (ride_id) REFERENCES rides(id)
);

CREATE TABLE IF NOT EXISTS planned_workouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    name TEXT,
    sport TEXT,
    total_duration_s REAL,
    workout_xml TEXT
);

CREATE TABLE IF NOT EXISTS daily_metrics (
    date TEXT PRIMARY KEY,
    total_tss REAL,
    ctl REAL,
    atl REAL,
    tsb REAL,
    weight REAL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS athlete_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    type TEXT NOT NULL,
    value REAL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS power_bests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ride_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    duration_s INTEGER NOT NULL,
    power REAL NOT NULL,
    FOREIGN KEY (ride_id) REFERENCES rides(id)
);

CREATE TABLE IF NOT EXISTS periodization_phases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    focus TEXT,
    hours_per_week_low REAL,
    hours_per_week_high REAL,
    tss_target_low REAL,
    tss_target_high REAL
);

CREATE INDEX IF NOT EXISTS idx_rides_date ON rides(date);
CREATE INDEX IF NOT EXISTS idx_ride_records_ride_id ON ride_records(ride_id);
CREATE INDEX IF NOT EXISTS idx_daily_metrics_date ON daily_metrics(date);
CREATE INDEX IF NOT EXISTS idx_power_bests_date ON power_bests(date);
CREATE INDEX IF NOT EXISTS idx_power_bests_duration ON power_bests(duration_s);
"""


def get_db_path():
    return os.path.abspath(DB_PATH)


def init_db(db_path=None):
    path = db_path or get_db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    return path


def get_connection(db_path=None):
    path = db_path or get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db(db_path=None):
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
