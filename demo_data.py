"""
Static demo dataset shown on "View Demo".

This is intentionally NOT stored in the real School/Teacher/Leave tables.
It exists only so a brand-new user can see what a finished timetable looks
like before they set up their own school. Nothing here is ever written to
the database, and nothing a demo visitor does can affect a real school.
"""

DEMO_SCHOOL_NAME = "Kebirigo Senior School (Demo)"

DEMO_TEACHERS = [
    {"name": "J. Nyaboke", "subject": "Mathematics", "max_lessons_per_week": 24},
    {"name": "P. Omondi", "subject": "English", "max_lessons_per_week": 22},
    {"name": "S. Chebet", "subject": "Chemistry", "max_lessons_per_week": 20},
    {"name": "D. Mwangi", "subject": "History", "max_lessons_per_week": 18},
]

DEMO_LEAVE_TYPES = [
    {"name": "Sick Leave", "max_days_per_term": 5},
    {"name": "Compassionate Leave", "max_days_per_term": 3},
    {"name": "Official Duty", "max_days_per_term": 10},
]

# A trimmed sample grid: day -> list of (period_label, subject, teacher)
DEMO_TIMETABLE = {
    "Monday": [
        ("P1", "Mathematics", "J. Nyaboke"),
        ("P2", "English", "P. Omondi"),
        ("P3", "Chemistry", "S. Chebet"),
        ("P4", "History", "D. Mwangi"),
    ],
    "Tuesday": [
        ("P1", "English", "P. Omondi"),
        ("P2", "Mathematics", "J. Nyaboke"),
        ("P3", "History", "D. Mwangi"),
        ("P4", "Chemistry", "S. Chebet"),
    ],
    "Wednesday": [
        ("P1", "Chemistry", "S. Chebet"),
        ("P2", "History", "D. Mwangi"),
        ("P3", "Mathematics", "J. Nyaboke"),
        ("P4", "English", "P. Omondi"),
    ],
}
