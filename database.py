"""
database.py
Data layer for the School Timetable Manager (Render free-plan version).

Backend selection is automatic, based on environment:

- If DATABASE_URL is set (Render's free PostgreSQL sets this for you
  automatically when the database is linked in render.yaml), we use
  Postgres. This is what makes data survive on Render's FREE plan,
  since free web services have no persistent disk but a free Postgres
  database is available.
- Otherwise (e.g. running locally with no database configured) we fall
  back to a local SQLite file, so local development still needs zero
  setup.

Every other module (app.py) is unaware of this split: it always calls
fetch_all() / fetch_one() / execute() with '?' placeholders, exactly as
before. This module translates that into the right SQL dialect.

Curriculum model implemented:
- Grade 10  -> Kenyan CBC / CBE Senior School (pathway-based: STEM,
               Social Sciences, Arts & Sports Science)
- Form 3    -> legacy 8-4-4 curriculum
- Form 4    -> legacy 8-4-4 curriculum
- Form 1 and Form 2 (8-4-4) do NOT exist; Form 2 has been replaced by
  Grade 10 under CBC.

Note on Render's free Postgres plan: the free database expires 30 days
after creation (14-day grace period to upgrade before deletion), has no
backups, and is capped at 1GB. See README.md for what that means for you.
"""

import os
import re

DATABASE_URL = os.environ.get("DATABASE_URL")
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras
else:
    import sqlite3

DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "timetable.db"),
)

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


# --------------------------------------------------------------------------
# Connection / query translation helpers
# --------------------------------------------------------------------------
def get_connection():
    if USE_POSTGRES:
        url = DATABASE_URL
        if url.startswith("postgres://"):
            # Render (and Heroku-style) URLs use the old "postgres://" scheme;
            # psycopg2 wants "postgresql://".
            url = "postgresql://" + url[len("postgres://"):]
        conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
        return conn
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn


def _adapt(query):
    """Translate SQLite-style '?' placeholders to psycopg2 '%s' on Postgres."""
    if USE_POSTGRES:
        return query.replace("?", "%s")
    return query


# Tables that use a composite primary key instead of an auto-incrementing
# 'id' column. INSERTs into these must never get 'RETURNING id' appended
# under Postgres, since that column doesn't exist there.
TABLES_WITHOUT_ID = {"teacher_subjects", "generation_settings"}

_INSERT_TABLE_RE = re.compile(r"^\s*INSERT\s+INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)


def _insert_table_name(query):
    """Extract the target table name from an INSERT query, or None."""
    m = _INSERT_TABLE_RE.match(query)
    return m.group(1).lower() if m else None


def _wants_returning_id(query):
    """Whether it's safe/appropriate to append RETURNING id to this INSERT."""
    table = _insert_table_name(query)
    return table is not None and table not in TABLES_WITHOUT_ID


def _insert_and_get_id(cur, query, params=()):
    """Run an INSERT and return the new row's id, for either backend."""
    query = _adapt(query)
    if USE_POSTGRES:
        if "RETURNING" not in query.upper() and _wants_returning_id(query):
            query = query.rstrip().rstrip(";") + " RETURNING id"
        cur.execute(query, params)
        if "RETURNING" in query.upper():
            return cur.fetchone()["id"]
        return None
    else:
        cur.execute(query, params)
        return cur.lastrowid


# --------------------------------------------------------------------------
# Schema (one flavor per backend — Postgres needs SERIAL instead of
# SQLite's INTEGER PRIMARY KEY AUTOINCREMENT)
# --------------------------------------------------------------------------
SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS grades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    curriculum TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pathways (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS streams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grade_id INTEGER NOT NULL REFERENCES grades(id) ON DELETE CASCADE,
    pathway_id INTEGER REFERENCES pathways(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    UNIQUE(grade_id, pathway_id, name)
);

CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code TEXT,
    category TEXT NOT NULL,
    grade_id INTEGER REFERENCES grades(id) ON DELETE CASCADE,
    pathway_id INTEGER REFERENCES pathways(id) ON DELETE SET NULL,
    periods_per_week INTEGER DEFAULT 5,
    UNIQUE(name, grade_id, pathway_id)
);

CREATE TABLE IF NOT EXISTS teachers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT
);

CREATE TABLE IF NOT EXISTS teacher_subjects (
    teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    PRIMARY KEY (teacher_id, subject_id)
);

CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    capacity INTEGER
);

CREATE TABLE IF NOT EXISTS periods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,
    period_number INTEGER NOT NULL,
    start_time TEXT,
    end_time TEXT,
    is_break INTEGER DEFAULT 0,
    label TEXT,
    UNIQUE(day, period_number)
);

CREATE TABLE IF NOT EXISTS timetable_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stream_id INTEGER NOT NULL REFERENCES streams(id) ON DELETE CASCADE,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    teacher_id INTEGER REFERENCES teachers(id) ON DELETE SET NULL,
    room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL,
    period_id INTEGER NOT NULL REFERENCES periods(id) ON DELETE CASCADE,
    UNIQUE(stream_id, period_id)
);

CREATE TABLE IF NOT EXISTS generation_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

SCHEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS grades (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    curriculum TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pathways (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS streams (
    id SERIAL PRIMARY KEY,
    grade_id INTEGER NOT NULL REFERENCES grades(id) ON DELETE CASCADE,
    pathway_id INTEGER REFERENCES pathways(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    UNIQUE(grade_id, pathway_id, name)
);

CREATE TABLE IF NOT EXISTS subjects (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    code TEXT,
    category TEXT NOT NULL,
    grade_id INTEGER REFERENCES grades(id) ON DELETE CASCADE,
    pathway_id INTEGER REFERENCES pathways(id) ON DELETE SET NULL,
    periods_per_week INTEGER DEFAULT 5,
    UNIQUE(name, grade_id, pathway_id)
);

CREATE TABLE IF NOT EXISTS teachers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT
);

CREATE TABLE IF NOT EXISTS teacher_subjects (
    teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    PRIMARY KEY (teacher_id, subject_id)
);

CREATE TABLE IF NOT EXISTS rooms (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    capacity INTEGER
);

CREATE TABLE IF NOT EXISTS periods (
    id SERIAL PRIMARY KEY,
    day TEXT NOT NULL,
    period_number INTEGER NOT NULL,
    start_time TEXT,
    end_time TEXT,
    is_break INTEGER DEFAULT 0,
    label TEXT,
    UNIQUE(day, period_number)
);

CREATE TABLE IF NOT EXISTS timetable_entries (
    id SERIAL PRIMARY KEY,
    stream_id INTEGER NOT NULL REFERENCES streams(id) ON DELETE CASCADE,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    teacher_id INTEGER REFERENCES teachers(id) ON DELETE SET NULL,
    room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL,
    period_id INTEGER NOT NULL REFERENCES periods(id) ON DELETE CASCADE,
    UNIQUE(stream_id, period_id)
);

CREATE TABLE IF NOT EXISTS generation_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


# --------------------------------------------------------------------------
# Init / seed
# --------------------------------------------------------------------------
def init_db():
    """Create the schema and seed default data if the DB doesn't exist yet."""
    if USE_POSTGRES:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT to_regclass('public.grades') AS reg")
        row = cur.fetchone()
        first_run = row["reg"] is None
        cur.execute(SCHEMA_POSTGRES)
        conn.commit()
        _migrate_schema(conn)
        if first_run:
            seed_data(conn)
        conn.close()
    else:
        first_run = not os.path.exists(DB_PATH)
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = get_connection()
        conn.executescript(SCHEMA_SQLITE)
        conn.commit()
        _migrate_schema(conn)
        if first_run:
            seed_data(conn)
        conn.close()


def _migrate_schema(conn):
    """Apply small additive schema changes to databases that already existed
    before this column/table was introduced. Safe to run on every startup:
    each change is only applied if it isn't already present."""
    cur = conn.cursor()
    if USE_POSTGRES:
        cur.execute("ALTER TABLE subjects ADD COLUMN IF NOT EXISTS periods_per_week INTEGER DEFAULT 5")
    else:
        cur.execute("PRAGMA table_info(subjects)")
        cols = {row["name"] for row in cur.fetchall()}
        if "periods_per_week" not in cols:
            cur.execute("ALTER TABLE subjects ADD COLUMN periods_per_week INTEGER DEFAULT 5")
    conn.commit()


def seed_data(conn):
    cur = conn.cursor()

    grade10_id = _insert_and_get_id(cur, "INSERT INTO grades (name, curriculum) VALUES (?, ?)", ("Grade 10", "CBC"))
    form3_id = _insert_and_get_id(cur, "INSERT INTO grades (name, curriculum) VALUES (?, ?)", ("Form 3", "8-4-4"))
    form4_id = _insert_and_get_id(cur, "INSERT INTO grades (name, curriculum) VALUES (?, ?)", ("Form 4", "8-4-4"))

    pathway_names = ["STEM", "Social Sciences", "Arts & Sports Science"]
    pathway_ids = {}
    for p in pathway_names:
        pathway_ids[p] = _insert_and_get_id(cur, "INSERT INTO pathways (name) VALUES (?)", (p,))

    for p in pathway_names:
        cur.execute(
            _adapt("INSERT INTO streams (grade_id, pathway_id, name) VALUES (?, ?, ?)"),
            (grade10_id, pathway_ids[p], f"Grade 10 {p}"),
        )
    cur.execute(_adapt("INSERT INTO streams (grade_id, pathway_id, name) VALUES (?, NULL, 'Form 3 East')"), (form3_id,))
    cur.execute(_adapt("INSERT INTO streams (grade_id, pathway_id, name) VALUES (?, NULL, 'Form 3 West')"), (form3_id,))
    cur.execute(_adapt("INSERT INTO streams (grade_id, pathway_id, name) VALUES (?, NULL, 'Form 4 East')"), (form4_id,))
    cur.execute(_adapt("INSERT INTO streams (grade_id, pathway_id, name) VALUES (?, NULL, 'Form 4 West')"), (form4_id,))

    core_subjects = [
        "English", "Kiswahili / KSL", "Mathematics",
        "Community Service Learning", "Physical Education", "ICT",
    ]
    for s in core_subjects:
        cur.execute(
            _adapt("INSERT INTO subjects (name, category, grade_id, pathway_id) VALUES (?, 'core', ?, NULL)"),
            (s, grade10_id),
        )

    pathway_subjects = {
        "STEM": [
            "Biology", "Chemistry", "Physics", "Computer Studies",
            "Agriculture", "Home Science", "General Science",
            "Advanced Mathematics", "Building Construction",
            "Electrical Technology", "Power Mechanics", "Woodwork",
        ],
        "Social Sciences": [
            "History & Citizenship", "Geography", "CRE/IRE/HRE",
            "Business Studies", "Literature in English",
            "Fasihi ya Kiswahili", "French", "German", "Arabic",
        ],
        "Arts & Sports Science": [
            "Fine Art", "Theatre & Film", "Music", "Sports Science",
        ],
    }
    for pathway, subs in pathway_subjects.items():
        for s in subs:
            cur.execute(
                _adapt("INSERT INTO subjects (name, category, grade_id, pathway_id) VALUES (?, 'pathway', ?, ?)"),
                (s, grade10_id, pathway_ids[pathway]),
            )

    legacy_subjects = [
        "English", "Kiswahili", "Mathematics", "Biology", "Chemistry",
        "Physics", "History & Government", "Geography", "CRE",
        "Business Studies", "Agriculture", "Computer Studies",
        "French", "Home Science", "Art & Design",
    ]
    for grade_id in (form3_id, form4_id):
        for s in legacy_subjects:
            cur.execute(
                _adapt("INSERT INTO subjects (name, category, grade_id, pathway_id) VALUES (?, 'general', ?, NULL)"),
                (s, grade_id),
            )

    start_hour, start_min = 8, 0
    lesson_len = 40
    break_after = 4
    for day in DAYS:
        minutes = start_hour * 60 + start_min
        for p in range(1, 9):
            s_h, s_m = divmod(minutes, 60)
            e_min = minutes + lesson_len
            e_h, e_m = divmod(e_min, 60)
            cur.execute(
                _adapt(
                    "INSERT INTO periods (day, period_number, start_time, end_time, is_break, label) "
                    "VALUES (?, ?, ?, ?, 0, ?)"
                ),
                (day, p, f"{s_h:02d}:{s_m:02d}", f"{e_h:02d}:{e_m:02d}", f"Lesson {p}"),
            )
            minutes = e_min
            if p == break_after:
                minutes += 20

    for name, cap in [("Room 1", 45), ("Room 2", 45), ("Lab 1", 30), ("Lab 2", 30)]:
        cur.execute(_adapt("INSERT INTO rooms (name, capacity) VALUES (?, ?)"), (name, cap))

    conn.commit()


# --------------------------------------------------------------------------
# Public query helpers (used throughout app.py — unchanged call signatures)
# --------------------------------------------------------------------------
def fetch_all(query, params=()):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(_adapt(query), params)
    rows = cur.fetchall()
    conn.close()
    return rows


def fetch_one(query, params=()):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(_adapt(query), params)
    row = cur.fetchone()
    conn.close()
    return row


def execute(query, params=()):
    conn = get_connection()
    cur = conn.cursor()
    q = _adapt(query)
    if (
        USE_POSTGRES
        and q.strip().upper().startswith("INSERT")
        and "RETURNING" not in q.upper()
        and _wants_returning_id(q)
    ):
        q = q.rstrip().rstrip(";") + " RETURNING id"
        cur.execute(q, params)
        row = cur.fetchone()
        last_id = row["id"] if row else None
    else:
        cur.execute(q, params)
        last_id = cur.lastrowid if not USE_POSTGRES else None
    conn.commit()
    conn.close()
    return last_id


# --------------------------------------------------------------------------
# Generation settings (scheduling rules toggles)
# --------------------------------------------------------------------------
DEFAULT_GENERATION_SETTINGS = {
    "avoid_same_day_repeat": "1",  # "1" = avoid scheduling a subject twice on the same day
}


def get_generation_settings():
    """Return all scheduling-rule settings as a dict of str->str, filled in
    with defaults for any key that hasn't been saved yet."""
    rows = fetch_all("SELECT key, value FROM generation_settings")
    settings = dict(DEFAULT_GENERATION_SETTINGS)
    for r in rows:
        settings[r["key"]] = r["value"]
    return settings


def set_generation_setting(key, value):
    if USE_POSTGRES:
        execute(
            "INSERT INTO generation_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (key, value),
        )
    else:
        execute(
            "INSERT INTO generation_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
