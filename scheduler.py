"""
scheduler.py
Automatic timetable generator for the School Timetable Manager.

Design decisions (per Testy's answers):
- periods_per_week is set per-subject on the Subjects page (not a global
  default), so it's read straight off the subjects table.
- If a subject has no teacher assigned yet, it is skipped entirely (its
  slots are left empty) rather than scheduled with a blank teacher.
- Whether to avoid repeating a subject twice on the same day for a stream
  is a toggle in the Scheduling Rules settings (generation_settings table),
  not hardcoded, so it can be flipped from the /rules page.

Algorithm: greedy with day-spread preference, teacher-conflict checking
across the whole school, and light load-balancing when a subject has more
than one qualified teacher. It's not a full constraint solver — if the
data is very tight (e.g. only one teacher for a subject and their periods
are already full elsewhere), some slots may go unfilled. Those are
reported back so you know what to fix manually (add another teacher,
free up a period, etc.) rather than silently failing.
"""

from collections import defaultdict

import database as db


def _get_available_periods():
    """All non-break periods, ordered by day then period number."""
    return db.fetch_all(
        "SELECT id, day, period_number FROM periods WHERE is_break=0 "
        "ORDER BY period_number, day"
    )


def _teachers_for_subject(subject_id):
    rows = db.fetch_all(
        "SELECT teacher_id FROM teacher_subjects WHERE subject_id=?",
        (subject_id,),
    )
    return [r["teacher_id"] for r in rows]


def generate_timetable(stream_ids=None, overwrite=False):
    """
    Fill in timetable_entries automatically.

    stream_ids: list of stream ids to generate for, or None for all streams.
    overwrite:  if True, clears each targeted stream's existing entries
                first. If False, only fills currently-empty slots and
                leaves any manual entries you've already made untouched.

    Returns a list of per-stream report dicts:
        {"stream": name, "scheduled": int, "skipped": [str, ...]}
    """
    settings = db.get_generation_settings()
    avoid_same_day = settings.get("avoid_same_day_repeat", "1") == "1"

    if stream_ids:
        streams = [db.fetch_one("SELECT * FROM streams WHERE id=?", (sid,)) for sid in stream_ids]
        streams = [s for s in streams if s]
    else:
        streams = db.fetch_all("SELECT * FROM streams ORDER BY grade_id, name")

    all_periods = _get_available_periods()

    # teacher_busy tracks every (teacher_id, period_id) already booked
    # anywhere in the school, so we never double-book a teacher across
    # different streams.
    teacher_busy = set()
    for e in db.fetch_all("SELECT teacher_id, period_id FROM timetable_entries"):
        if e["teacher_id"]:
            teacher_busy.add((e["teacher_id"], e["period_id"]))

    report = []

    for stream in streams:
        stream_id = stream["id"]

        if overwrite:
            old = db.fetch_all(
                "SELECT teacher_id, period_id FROM timetable_entries WHERE stream_id=?",
                (stream_id,),
            )
            db.execute("DELETE FROM timetable_entries WHERE stream_id=?", (stream_id,))
            for o in old:
                if o["teacher_id"]:
                    teacher_busy.discard((o["teacher_id"], o["period_id"]))

        filled_period_ids = {
            r["period_id"]
            for r in db.fetch_all("SELECT period_id FROM timetable_entries WHERE stream_id=?", (stream_id,))
        }
        available = [p for p in all_periods if p["id"] not in filled_period_ids]

        subjects = db.fetch_all(
            "SELECT * FROM subjects WHERE grade_id=? AND (pathway_id IS NULL OR pathway_id=?) "
            "ORDER BY periods_per_week DESC",
            (stream["grade_id"], stream["pathway_id"]),
        )

        teacher_load = defaultdict(int)
        subject_days_used = defaultdict(set)
        stream_report = {"stream": stream["name"], "scheduled": 0, "skipped": []}

        for subject in subjects:
            needed = subject["periods_per_week"] or 5
            teachers = _teachers_for_subject(subject["id"])
            if not teachers:
                stream_report["skipped"].append(f"{subject['name']}: no teacher assigned, skipped")
                continue

            placed = _place_subject(
                subject, teachers, needed, available, teacher_busy, teacher_load,
                subject_days_used, stream_id, avoid_same_day=avoid_same_day,
            )
            if placed < needed:
                # relax the same-day rule as a second pass, if that's what's blocking us
                more = _place_subject(
                    subject, teachers, needed - placed, available, teacher_busy,
                    teacher_load, subject_days_used, stream_id, avoid_same_day=False,
                )
                placed += more

            stream_report["scheduled"] += placed
            if placed < needed:
                stream_report["skipped"].append(
                    f"{subject['name']}: only {placed}/{needed} periods placed "
                    f"(no free teacher/slot left)"
                )

        report.append(stream_report)

    return report


def _place_subject(subject, teachers, needed, available, teacher_busy, teacher_load,
                    subject_days_used, stream_id, avoid_same_day):
    """Try to place up to `needed` periods for a subject into `available`
    slots (mutated in place as slots get used). Returns how many were placed."""
    placed = 0
    for p in list(available):
        if placed >= needed:
            break
        if avoid_same_day and p["day"] in subject_days_used[subject["id"]]:
            continue

        chosen_teacher = None
        for t in sorted(teachers, key=lambda tid: teacher_load[tid]):
            if (t, p["id"]) not in teacher_busy:
                chosen_teacher = t
                break
        if chosen_teacher is None:
            continue

        db.execute(
            "INSERT INTO timetable_entries (stream_id, subject_id, teacher_id, room_id, period_id) "
            "VALUES (?, ?, ?, NULL, ?)",
            (stream_id, subject["id"], chosen_teacher, p["id"]),
        )
        teacher_busy.add((chosen_teacher, p["id"]))
        teacher_load[chosen_teacher] += 1
        subject_days_used[subject["id"]].add(p["day"])
        available.remove(p)
        placed += 1

    return placed
