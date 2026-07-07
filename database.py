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

CREATE TABLE IF NOT EXISTS subject_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    rule_type TEXT NOT NULL,
    value INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS day_structure (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    start_time TEXT NOT NULL DEFAULT '08:00',
    lesson_minutes INTEGER NOT NULL DEFAULT 40,
    periods_per_day INTEGER NOT NULL DEFAULT 8
);

CREATE TABLE IF NOT EXISTS breaks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    after_period INTEGER NOT NULL,
    duration_minutes INTEGER NOT NULL,
    label TEXT
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

CREATE TABLE IF NOT EXISTS subject_rules (
    id SERIAL PRIMARY KEY,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    rule_type TEXT NOT NULL,
    value INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS day_structure (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    start_time TEXT NOT NULL DEFAULT '08:00',
    lesson_minutes INTEGER NOT NULL DEFAULT 40,
    periods_per_day INTEGER NOT NULL DEFAULT 8
);

CREATE TABLE IF NOT EXISTS breaks (
    id SERIAL PRIMARY KEY,
    after_period INTEGER NOT NULL,
    duration_minutes INTEGER NOT NULL,
    label TEXT
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

    # Seed day_structure/breaks defaults for databases that already existed
    # before this feature, matching the values their periods were originally
    # generated with (08:00 start, 40-min lessons, 20-min break after period
    # 4, 8 periods/day) — so the Day Structure page shows what they already
    # effectively have, rather than blanks, until they choose to change it.
    cur.execute("SELECT COUNT(*) AS c FROM day_structure")
    if cur.fetchone()["c"] == 0:
        cur.execute(
            _adapt("INSERT INTO day_structure (id, start_time, lesson_minutes, periods_per_day) VALUES (1, ?, ?, ?)"),
            ("08:00", 40, 8),
        )
    cur.execute("SELECT COUNT(*) AS c FROM breaks")
    if cur.fetchone()["c"] == 0:
        cur.execute(
            _adapt("INSERT INTO breaks (after_period, duration_minutes, label) VALUES (?, ?, ?)"),
            (4, 20, "Break"),
        )
    conn.commit()


def _regenerate_periods(cur):
    """
    Recompute start_time/end_time (and insert/remove rows as needed) for
    every day's periods, based on the day_structure + breaks settings.

    Existing period rows are UPDATEd in place whenever their period_number
    still exists in the new structure, so their id (and therefore any
    timetable_entries pointing at them) stays valid — only the times/label
    change. Rows are only inserted (new period_number) or deleted (old
    period_number beyond the new periods_per_day) when the day actually
    grew or shrank; deleting cascades to remove any timetable_entries that
    were sitting in a period that no longer exists.
    """
    cur.execute("SELECT start_time, lesson_minutes, periods_per_day FROM day_structure WHERE id=1")
    ds = cur.fetchone()
    if not ds:
        return
    start_time, lesson_minutes, periods_per_day = ds["start_time"], ds["lesson_minutes"], ds["periods_per_day"]
    start_hour, start_min = (int(x) for x in start_time.split(":"))

    cur.execute("SELECT after_period, duration_minutes FROM breaks ORDER BY after_period")
    break_map = {}
    for row in cur.fetchall():
        break_map[row["after_period"]] = break_map.get(row["after_period"], 0) + row["duration_minutes"]

    for day in DAYS:
        cur.execute(_adapt("SELECT period_number FROM periods WHERE day=?"), (day,))
        existing_numbers = {row["period_number"] for row in cur.fetchall()}

        for num in existing_numbers:
            if num > periods_per_day:
                cur.execute(_adapt("DELETE FROM periods WHERE day=? AND period_number=?"), (day, num))

        minutes = start_hour * 60 + start_min
        for p in range(1, periods_per_day + 1):
            s_h, s_m = divmod(minutes, 60)
            e_min = minutes + lesson_minutes
            e_h, e_m = divmod(e_min, 60)
            start_str, end_str = f"{s_h:02d}:{s_m:02d}", f"{e_h:02d}:{e_m:02d}"
            if p in existing_numbers:
                cur.execute(
                    _adapt("UPDATE periods SET start_time=?, end_time=?, label=? WHERE day=? AND period_number=?"),
                    (start_str, end_str, f"Lesson {p}", day, p),
                )
            else:
                cur.execute(
                    _adapt(
                        "INSERT INTO periods (day, period_number, start_time, end_time, is_break, label) "
                        "VALUES (?, ?, ?, ?, 0, ?)"
                    ),
                    (day, p, start_str, end_str, f"Lesson {p}"),
                )
            minutes = e_min
            if p in break_map:
                minutes += break_map[p]


def regenerate_periods():
    """Public entry point: open a connection, apply the current
    day_structure/breaks settings to every period, commit, close."""
    conn = get_connection()
    cur = conn.cursor()
    _regenerate_periods(cur)
    conn.commit()
    conn.close()


def get_day_structure():
    row = fetch_one("SELECT start_time, lesson_minutes, periods_per_day FROM day_structure WHERE id=1")
    if row:
        return dict(row)
    return {"start_time": "08:00", "lesson_minutes": 40, "periods_per_day": 8}


def set_day_structure(start_time, lesson_minutes, periods_per_day):
    if USE_POSTGRES:
        execute(
            "INSERT INTO day_structure (id, start_time, lesson_minutes, periods_per_day) "
            "VALUES (1, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET "
            "start_time = EXCLUDED.start_time, lesson_minutes = EXCLUDED.lesson_minutes, "
            "periods_per_day = EXCLUDED.periods_per_day",
            (start_time, lesson_minutes, periods_per_day),
        )
    else:
        execute(
            "INSERT INTO day_structure (id, start_time, lesson_minutes, periods_per_day) "
            "VALUES (1, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET "
            "start_time = excluded.start_time, lesson_minutes = excluded.lesson_minutes, "
            "periods_per_day = excluded.periods_per_day",
            (start_time, lesson_minutes, periods_per_day),
        )


def list_breaks():
    return fetch_all("SELECT * FROM breaks ORDER BY after_period")


def get_break_rows():
    """Display-only rows describing where each break sits in the day and
    what time range it covers, e.g. for showing a 'Break' row on the
    generated timetable between period 4 and period 5.

    Breaks aren't stored in the `periods` table (the scheduler only ever
    deals with real lesson periods), so this recomputes each break's
    start/end time the same way `_regenerate_periods` lays out the day:
    walking period 1..N, adding lesson_minutes each period, and adding the
    break's duration right after its `after_period`. Since every day uses
    the same day_structure, one pass covers all days (Mon-Fri identical).

    Returns a list of dicts sorted by after_period:
        {"after_period": int, "label": str, "start_time": "HH:MM", "end_time": "HH:MM"}
    """
    ds = get_day_structure()
    start_hour, start_min = (int(x) for x in ds["start_time"].split(":"))

    break_map = {}
    for b in list_breaks():
        entry = break_map.setdefault(b["after_period"], {"duration": 0, "label": b["label"]})
        entry["duration"] += b["duration_minutes"]
        if b["label"]:
            entry["label"] = b["label"]

    rows = []
    minutes = start_hour * 60 + start_min
    for p in range(1, ds["periods_per_day"] + 1):
        minutes += ds["lesson_minutes"]  # end of period p
        if p in break_map:
            info = break_map[p]
            b_start_h, b_start_m = divmod(minutes, 60)
            b_end_min = minutes + info["duration"]
            b_end_h, b_end_m = divmod(b_end_min, 60)
            rows.append({
                "after_period": p,
                "label": info["label"] or "Break",
                "start_time": f"{b_start_h:02d}:{b_start_m:02d}",
                "end_time": f"{b_end_h:02d}:{b_end_m:02d}",
            })
            minutes = b_end_min
    return rows


def replace_breaks(break_list):
    """break_list: list of (after_period, duration_minutes, label) tuples.
    Wipes and re-inserts, since breaks are always edited as a whole set
    from the Day Structure page rather than one at a time."""
    execute("DELETE FROM breaks")
    for after_period, duration_minutes, label in break_list:
        execute(
            "INSERT INTO breaks (after_period, duration_minutes, label) VALUES (?, ?, ?)",
            (after_period, duration_minutes, label),
        )


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

    for name, cap in [("Room 1", 45), ("Room 2", 45), ("Lab 1", 30), ("Lab 2", 30)]:
        cur.execute(_adapt("INSERT INTO rooms (name, capacity) VALUES (?, ?)"), (name, cap))

    conn.commit()
    _regenerate_periods(cur)
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
    "vary_period_slot": "1",       # "1" = avoid a subject always landing in the same period number every day
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


# --------------------------------------------------------------------------
# Subject scheduling rules (double lessons, "not after period X", etc.)
# --------------------------------------------------------------------------
VALID_RULE_TYPES = {"double_lesson", "not_after_period"}


def list_subject_rules():
    """All subject rules with the subject's name attached, for display."""
    return fetch_all(
        "SELECT sr.id, sr.subject_id, sr.rule_type, sr.value, s.name AS subject_name "
        "FROM subject_rules sr JOIN subjects s ON sr.subject_id = s.id "
        "ORDER BY s.name, sr.rule_type"
    )


def get_subject_rules(subject_id):
    """Return {'not_after_period': int or None, 'double_lesson_count': int} for one subject."""
    rows = fetch_all("SELECT rule_type, value FROM subject_rules WHERE subject_id=?", (subject_id,))
    result = {"not_after_period": None, "double_lesson_count": 0}
    for r in rows:
        if r["rule_type"] == "not_after_period":
            # if more than one such rule exists, the strictest (smallest) wins
            if result["not_after_period"] is None or r["value"] < result["not_after_period"]:
                result["not_after_period"] = r["value"]
        elif r["rule_type"] == "double_lesson":
            result["double_lesson_count"] += r["value"]
    return result


def add_subject_rule(subject_id, rule_type, value):
    if rule_type not in VALID_RULE_TYPES:
        raise ValueError(f"Unknown rule_type: {rule_type}")
    execute(
        "INSERT INTO subject_rules (subject_id, rule_type, value) VALUES (?, ?, ?)",
        (subject_id, rule_type, value),
    )


def delete_subject_rule(rule_id):
    execute("DELETE FROM subject_rules WHERE id=?", (rule_id,))
