"""
app.py — School Timetable Manager (Flask web version for Render)

Structure:
  - Grade 10 : Kenyan CBC / CBE Senior School (pathway-based)
  - Form 3   : legacy 8-4-4 curriculum
  - Form 4   : legacy 8-4-4 curriculum
  (Form 1 removed; Form 2 replaced by Grade 10.)
"""

import csv
import io
import os

from flask import (
    Flask, render_template, request, redirect, url_for,
    jsonify, Response, flash
)

import database as db
import scheduler

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

with app.app_context():
    db.init_db()


# --------------------------------------------------------------------------
# Home
# --------------------------------------------------------------------------
@app.route("/")
def home():
    return redirect(url_for("grades_page"))


# --------------------------------------------------------------------------
# Grades & Streams
# --------------------------------------------------------------------------
@app.route("/grades")
def grades_page():
    grades = db.fetch_all("SELECT * FROM grades ORDER BY id")
    selected_id = request.args.get("grade_id", type=int) or (grades[0]["id"] if grades else None)
    streams = []
    if selected_id:
        streams = db.fetch_all(
            """SELECT s.id, s.name, p.name as pathway_name FROM streams s
               LEFT JOIN pathways p ON s.pathway_id = p.id
               WHERE s.grade_id = ? ORDER BY s.name""",
            (selected_id,),
        )
    pathways = db.fetch_all("SELECT * FROM pathways ORDER BY name")
    selected_grade = db.fetch_one("SELECT * FROM grades WHERE id=?", (selected_id,)) if selected_id else None
    return render_template(
        "grades.html", grades=grades, streams=streams, pathways=pathways,
        selected_id=selected_id, selected_grade=selected_grade,
    )


@app.route("/streams/add", methods=["POST"])
def add_stream():
    grade_id = request.form.get("grade_id", type=int)
    name = request.form.get("name", "").strip()
    pathway_name = request.form.get("pathway", "")
    if not grade_id or not name:
        flash("Enter a stream name.", "error")
        return redirect(url_for("grades_page", grade_id=grade_id))
    grade = db.fetch_one("SELECT curriculum FROM grades WHERE id=?", (grade_id,))
    pathway_id = None
    if grade and grade["curriculum"] == "CBC" and pathway_name and pathway_name != "(none)":
        prow = db.fetch_one("SELECT id FROM pathways WHERE name=?", (pathway_name,))
        pathway_id = prow["id"] if prow else None
    try:
        db.execute(
            "INSERT INTO streams (grade_id, pathway_id, name) VALUES (?, ?, ?)",
            (grade_id, pathway_id, name),
        )
    except Exception as e:
        flash(f"Could not add stream: {e}", "error")
    return redirect(url_for("grades_page", grade_id=grade_id))


@app.route("/streams/<int:stream_id>/delete", methods=["POST"])
def delete_stream(stream_id):
    grade_id = request.form.get("grade_id", type=int)
    db.execute("DELETE FROM streams WHERE id=?", (stream_id,))
    return redirect(url_for("grades_page", grade_id=grade_id))


# --------------------------------------------------------------------------
# Subjects
# --------------------------------------------------------------------------
@app.route("/subjects")
def subjects_page():
    grade_filter = request.args.get("grade", "(all)")
    grades = db.fetch_all("SELECT * FROM grades ORDER BY id")
    pathways = db.fetch_all("SELECT * FROM pathways ORDER BY name")

    query = """SELECT sub.id, sub.name, sub.category, sub.periods_per_week,
                      g.name as grade_name, p.name as pathway_name
               FROM subjects sub
               JOIN grades g ON sub.grade_id = g.id
               LEFT JOIN pathways p ON sub.pathway_id = p.id"""
    params = ()
    if grade_filter and grade_filter != "(all)":
        query += " WHERE g.name = ?"
        params = (grade_filter,)
    query += " ORDER BY g.id, sub.category, sub.name"
    subjects = db.fetch_all(query, params)

    return render_template(
        "subjects.html", grades=grades, pathways=pathways, subjects=subjects,
        grade_filter=grade_filter,
    )


@app.route("/subjects/add", methods=["POST"])
def add_subject():
    name = request.form.get("name", "").strip()
    grade_name = request.form.get("grade", "")
    category = request.form.get("category", "general")
    pathway_name = request.form.get("pathway", "")
    periods_per_week = request.form.get("periods_per_week", type=int) or 5
    if not name or not grade_name:
        flash("Enter a subject name and choose a grade.", "error")
        return redirect(url_for("subjects_page"))
    grow = db.fetch_one("SELECT id, curriculum FROM grades WHERE name=?", (grade_name,))
    if not grow:
        return redirect(url_for("subjects_page"))
    pathway_id = None
    if grow["curriculum"] == "CBC" and pathway_name and pathway_name != "(none)":
        prow = db.fetch_one("SELECT id FROM pathways WHERE name=?", (pathway_name,))
        pathway_id = prow["id"] if prow else None
    try:
        db.execute(
            "INSERT INTO subjects (name, category, grade_id, pathway_id, periods_per_week) VALUES (?, ?, ?, ?, ?)",
            (name, category, grow["id"], pathway_id, periods_per_week),
        )
    except Exception as e:
        flash(f"Could not add subject: {e}", "error")
    return redirect(url_for("subjects_page", grade=grade_name))


@app.route("/subjects/<int:subject_id>/periods", methods=["POST"])
def update_subject_periods(subject_id):
    grade_filter = request.form.get("grade_filter", "(all)")
    periods_per_week = request.form.get("periods_per_week", type=int)
    if periods_per_week is None or periods_per_week < 1:
        flash("Periods per week must be a positive number.", "error")
        return redirect(url_for("subjects_page", grade=grade_filter))
    db.execute(
        "UPDATE subjects SET periods_per_week=? WHERE id=?",
        (periods_per_week, subject_id),
    )
    return redirect(url_for("subjects_page", grade=grade_filter))


@app.route("/subjects/<int:subject_id>/delete", methods=["POST"])
def delete_subject(subject_id):
    grade_filter = request.form.get("grade_filter", "(all)")
    db.execute("DELETE FROM subjects WHERE id=?", (subject_id,))
    return redirect(url_for("subjects_page", grade=grade_filter))


# --------------------------------------------------------------------------
# Teachers
# --------------------------------------------------------------------------
@app.route("/teachers")
def teachers_page():
    teachers = db.fetch_all(
        "SELECT * FROM teachers ORDER BY CASE WHEN rank IS NULL THEN 1 ELSE 0 END, rank, name"
    )
    selected_id = request.args.get("teacher_id", type=int)
    all_subjects = db.fetch_all(
        """SELECT sub.id, sub.name, g.name as grade_name FROM subjects sub
           JOIN grades g ON sub.grade_id = g.id ORDER BY g.id, sub.name"""
    )
    assigned_ids = set()
    if selected_id:
        assigned_ids = {r["subject_id"] for r in db.fetch_all(
            "SELECT subject_id FROM teacher_subjects WHERE teacher_id=?", (selected_id,))}
    selected_teacher = next((t for t in teachers if t["id"] == selected_id), None)
    return render_template(
        "teachers.html", teachers=teachers, selected_id=selected_id,
        all_subjects=all_subjects, assigned_ids=assigned_ids, selected_teacher=selected_teacher,
    )


@app.route("/teachers/add", methods=["POST"])
def add_teacher():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    rank = request.form.get("rank", type=int)
    if not name:
        flash("Enter a teacher name.", "error")
        return redirect(url_for("teachers_page"))
    db.execute("INSERT INTO teachers (name, email, rank) VALUES (?, ?, ?)", (name, email, rank))
    return redirect(url_for("teachers_page"))


@app.route("/teachers/<int:teacher_id>/update", methods=["POST"])
def update_teacher(teacher_id):
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    rank = request.form.get("rank", type=int)
    if not name:
        flash("Enter a teacher name.", "error")
        return redirect(url_for("teachers_page", teacher_id=teacher_id))
    db.execute(
        "UPDATE teachers SET name=?, email=?, rank=? WHERE id=?",
        (name, email, rank, teacher_id),
    )
    flash("Teacher details updated.", "success")
    return redirect(url_for("teachers_page", teacher_id=teacher_id))


@app.route("/teachers/<int:teacher_id>/delete", methods=["POST"])
def delete_teacher(teacher_id):
    db.execute("DELETE FROM teachers WHERE id=?", (teacher_id,))
    return redirect(url_for("teachers_page"))


@app.route("/teachers/<int:teacher_id>/subjects", methods=["POST"])
def save_teacher_subjects(teacher_id):
    chosen_ids = request.form.getlist("subject_ids", type=int)
    db.execute("DELETE FROM teacher_subjects WHERE teacher_id=?", (teacher_id,))
    for sid in chosen_ids:
        db.execute("INSERT INTO teacher_subjects (teacher_id, subject_id) VALUES (?, ?)", (teacher_id, sid))
    flash("Subject assignments updated.", "success")
    return redirect(url_for("teachers_page", teacher_id=teacher_id))


# --------------------------------------------------------------------------
# Rooms
# --------------------------------------------------------------------------
@app.route("/rooms")
def rooms_page():
    rooms = db.fetch_all("SELECT * FROM rooms ORDER BY name")
    return render_template("rooms.html", rooms=rooms)


@app.route("/rooms/add", methods=["POST"])
def add_room():
    name = request.form.get("name", "").strip()
    capacity = request.form.get("capacity", "").strip() or None
    if not name:
        flash("Enter a room name.", "error")
        return redirect(url_for("rooms_page"))
    try:
        db.execute("INSERT INTO rooms (name, capacity) VALUES (?, ?)", (name, capacity))
    except Exception as e:
        flash(f"Could not add room: {e}", "error")
    return redirect(url_for("rooms_page"))


@app.route("/rooms/<int:room_id>/delete", methods=["POST"])
def delete_room(room_id):
    db.execute("DELETE FROM rooms WHERE id=?", (room_id,))
    return redirect(url_for("rooms_page"))


# --------------------------------------------------------------------------
# Scheduling Rules (auto-generation settings)
# --------------------------------------------------------------------------
@app.route("/rules")
def rules_page():
    settings = db.get_generation_settings()
    subjects = db.fetch_all(
        "SELECT sub.id, sub.name, g.name AS grade_name FROM subjects sub "
        "JOIN grades g ON sub.grade_id = g.id ORDER BY g.name, sub.name"
    )
    subject_rules = db.list_subject_rules()
    # periods 1..8 for the "not after period" dropdown (matches the seeded day length)
    max_period = db.fetch_one("SELECT MAX(period_number) AS m FROM periods WHERE is_break=0")
    period_options = list(range(1, (max_period["m"] or 8) + 1))
    return render_template(
        "rules.html", settings=settings, subjects=subjects,
        subject_rules=subject_rules, period_options=period_options,
    )


@app.route("/rules/save", methods=["POST"])
def save_rules():
    # Checkbox: present in form data only when checked.
    avoid_same_day = "1" if request.form.get("avoid_same_day_repeat") else "0"
    vary_period = "1" if request.form.get("vary_period_slot") else "0"
    db.set_generation_setting("avoid_same_day_repeat", avoid_same_day)
    db.set_generation_setting("vary_period_slot", vary_period)
    flash("Scheduling rules updated.", "success")
    return redirect(url_for("rules_page"))


@app.route("/rules/subject_rule/add", methods=["POST"])
def add_subject_rule():
    subject_id = request.form.get("subject_id", type=int)
    rule_type = request.form.get("rule_type", "")
    value = request.form.get("value", type=int)

    if not subject_id or rule_type not in db.VALID_RULE_TYPES or not value or value < 1:
        flash("Choose a subject, rule type, and a valid positive number.", "error")
        return redirect(url_for("rules_page"))

    db.add_subject_rule(subject_id, rule_type, value)
    flash("Rule added.", "success")
    return redirect(url_for("rules_page"))


@app.route("/rules/subject_rule/<int:rule_id>/delete", methods=["POST"])
def delete_subject_rule(rule_id):
    db.delete_subject_rule(rule_id)
    flash("Rule removed.", "success")
    return redirect(url_for("rules_page"))


# --------------------------------------------------------------------------
# Day Structure (start time, lesson length, breaks)
# --------------------------------------------------------------------------
@app.route("/day-structure")
def day_structure_page():
    ds = db.get_day_structure()
    breaks = db.list_breaks()
    return render_template("day_structure.html", ds=ds, breaks=breaks)


@app.route("/day-structure/save", methods=["POST"])
def save_day_structure():
    start_time = request.form.get("start_time", "08:00")
    lesson_minutes = request.form.get("lesson_minutes", type=int)
    periods_per_day = request.form.get("periods_per_day", type=int)

    if not lesson_minutes or lesson_minutes < 10 or not periods_per_day or periods_per_day < 1:
        flash("Enter a valid lesson length and number of periods per day.", "error")
        return redirect(url_for("day_structure_page"))

    after_periods = request.form.getlist("after_period[]")
    durations = request.form.getlist("duration[]")
    labels = request.form.getlist("label[]")

    break_list = []
    shrinking_removes_break_rows = False
    for ap_raw, dur_raw, label in zip(after_periods, durations, labels):
        if not ap_raw or not dur_raw:
            continue
        ap, dur = int(ap_raw), int(dur_raw)
        if ap < 1 or ap >= periods_per_day:
            # a break "after period N" only makes sense if N is before the
            # last period of the (possibly just-shrunk) day
            shrinking_removes_break_rows = True
            continue
        if dur < 1:
            continue
        break_list.append((ap, dur, label.strip() or "Break"))

    old_periods_per_day = db.get_day_structure()["periods_per_day"]
    removed_periods = old_periods_per_day > periods_per_day

    db.set_day_structure(start_time, lesson_minutes, periods_per_day)
    db.replace_breaks(break_list)
    db.regenerate_periods()

    flash("Day structure updated — periods and break times have been regenerated.", "success")
    if removed_periods:
        flash(
            f"You reduced periods/day from {old_periods_per_day} to {periods_per_day}: "
            f"any timetable entries in the removed periods were cleared. Re-run "
            f"Auto-Generate or fill those slots manually.",
            "error",
        )
    if shrinking_removes_break_rows:
        flash("One or more breaks were dropped because their period no longer fits in the day.", "error")
    return redirect(url_for("day_structure_page"))


# --------------------------------------------------------------------------
# Timetable Builder
# --------------------------------------------------------------------------
@app.route("/builder")
def builder_page():
    streams = db.fetch_all(
        """SELECT s.id, s.name, g.name as grade_name FROM streams s
           JOIN grades g ON s.grade_id = g.id ORDER BY g.id, s.name"""
    )
    stream_id = request.args.get("stream_id", type=int) or (streams[0]["id"] if streams else None)

    periods = db.fetch_all("SELECT DISTINCT period_number, start_time, end_time FROM periods WHERE is_break=0 ORDER BY period_number")
    days = db.DAYS
    display_rows = _rows_with_breaks(periods)

    entries = {}
    if stream_id:
        entry_rows = db.fetch_all(
            """SELECT te.id, sub.name as subject_name, t.name as teacher_name,
                      rm.name as room_name, p.day, p.period_number
               FROM timetable_entries te
               JOIN periods p ON te.period_id = p.id
               JOIN subjects sub ON te.subject_id = sub.id
               LEFT JOIN teachers t ON te.teacher_id = t.id
               LEFT JOIN rooms rm ON te.room_id = rm.id
               WHERE te.stream_id = ?""",
            (stream_id,),
        )
        for r in entry_rows:
            entries[(r["day"], r["period_number"])] = r

    return render_template(
        "builder.html", streams=streams, stream_id=stream_id,
        rows=display_rows, days=days, entries=entries,
    )


@app.route("/builder/generate", methods=["POST"])
def generate_timetable():
    scope = request.form.get("scope", "stream")  # "stream" or "all"
    overwrite = request.form.get("overwrite") == "1"
    stream_id = request.form.get("stream_id", type=int)

    stream_ids = None if scope == "all" else ([stream_id] if stream_id else [])

    report = scheduler.generate_timetable(stream_ids=stream_ids, overwrite=overwrite)

    total_scheduled = sum(r["scheduled"] for r in report)
    total_skipped = sum(len(r["skipped"]) for r in report)
    flash(f"Auto-generated {total_scheduled} periods across {len(report)} stream(s).", "success")
    if total_skipped:
        details = " | ".join(
            f"{r['stream']}: " + "; ".join(r["skipped"])
            for r in report if r["skipped"]
        )
        flash(f"{total_skipped} slot(s) left unfilled — {details}", "error")

    return redirect(url_for("builder_page", stream_id=stream_id))


@app.route("/api/cell")
def api_get_cell():
    """Returns subject/teacher/room options + any existing entry for a cell."""
    stream_id = request.args.get("stream_id", type=int)
    day = request.args.get("day")
    period_number = request.args.get("period_number", type=int)

    stream = db.fetch_one("SELECT * FROM streams WHERE id=?", (stream_id,))
    period = db.fetch_one("SELECT * FROM periods WHERE day=? AND period_number=?", (day, period_number))
    if not stream or not period:
        return jsonify({"error": "not found"}), 404

    subjects = db.fetch_all(
        "SELECT id, name FROM subjects WHERE grade_id=? AND (pathway_id IS NULL OR pathway_id=?) ORDER BY name",
        (stream["grade_id"], stream["pathway_id"]),
    )
    teachers = db.fetch_all("SELECT id, name FROM teachers ORDER BY name")
    rooms = db.fetch_all("SELECT id, name FROM rooms ORDER BY name")
    existing = db.fetch_one(
        "SELECT * FROM timetable_entries WHERE stream_id=? AND period_id=?",
        (stream_id, period["id"]),
    )

    return jsonify({
        "subjects": [dict(s) for s in subjects],
        "teachers": [dict(t) for t in teachers],
        "rooms": [dict(r) for r in rooms],
        "existing": dict(existing) if existing else None,
        "period_id": period["id"],
        "period_label": f"{day} — Period {period_number} ({period['start_time']}-{period['end_time']})",
    })


@app.route("/api/cell/save", methods=["POST"])
def api_save_cell():
    data = request.get_json()
    stream_id = data.get("stream_id")
    period_id = data.get("period_id")
    subject_id = data.get("subject_id")
    teacher_id = data.get("teacher_id") or None
    room_id = data.get("room_id") or None
    force = data.get("force", False)

    if not subject_id:
        return jsonify({"error": "Choose a subject."}), 400

    conflicts = []
    if teacher_id:
        clash = db.fetch_one(
            "SELECT te.id FROM timetable_entries te WHERE te.teacher_id=? AND te.period_id=? AND te.stream_id != ?",
            (teacher_id, period_id, stream_id),
        )
        if clash:
            conflicts.append("This teacher is already teaching another stream in this period.")
    if room_id:
        clash = db.fetch_one(
            "SELECT te.id FROM timetable_entries te WHERE te.room_id=? AND te.period_id=? AND te.stream_id != ?",
            (room_id, period_id, stream_id),
        )
        if clash:
            conflicts.append("This room is already booked by another stream in this period.")

    if conflicts and not force:
        return jsonify({"conflicts": conflicts})

    existing = db.fetch_one(
        "SELECT * FROM timetable_entries WHERE stream_id=? AND period_id=?", (stream_id, period_id)
    )
    if existing:
        db.execute(
            "UPDATE timetable_entries SET subject_id=?, teacher_id=?, room_id=? WHERE id=?",
            (subject_id, teacher_id, room_id, existing["id"]),
        )
    else:
        db.execute(
            "INSERT INTO timetable_entries (stream_id, subject_id, teacher_id, room_id, period_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (stream_id, subject_id, teacher_id, room_id, period_id),
        )
    return jsonify({"ok": True})


@app.route("/api/cell/clear", methods=["POST"])
def api_clear_cell():
    data = request.get_json()
    stream_id = data.get("stream_id")
    period_id = data.get("period_id")
    db.execute(
        "DELETE FROM timetable_entries WHERE stream_id=? AND period_id=?",
        (stream_id, period_id),
    )
    return jsonify({"ok": True})


# --------------------------------------------------------------------------
# View / Export
# --------------------------------------------------------------------------
def _rows_with_breaks(periods):
    """Interleave lesson periods with break marker rows, in day order.
    `periods` is a list of period rows (period_number, start_time, end_time).
    Returns a list of dicts, each either:
      {"type": "lesson", "period_number": n, "start_time": s, "end_time": e}
      {"type": "break", "label": lbl, "start_time": s, "end_time": e}
    """
    break_by_after = {b["after_period"]: b for b in db.get_break_rows()}
    rows = []
    for p in periods:
        rows.append({
            "type": "lesson",
            "period_number": p["period_number"],
            "start_time": p["start_time"],
            "end_time": p["end_time"],
        })
        b = break_by_after.get(p["period_number"])
        if b:
            rows.append({
                "type": "break",
                "label": b["label"],
                "start_time": b["start_time"],
                "end_time": b["end_time"],
            })
    return rows


def _grid_data(mode, target):
    days = db.DAYS
    periods = db.fetch_all("SELECT DISTINCT period_number, start_time, end_time FROM periods WHERE is_break=0 ORDER BY period_number")
    display_rows = _rows_with_breaks(periods)

    if mode == "stream":
        stream = db.fetch_one("SELECT * FROM streams WHERE id=?", (target,))
        if not stream:
            return None
        rows = db.fetch_all(
            """SELECT p.day, p.period_number, sub.name as subject_name,
                      t.name as teacher_name, rm.name as room_name
               FROM timetable_entries te
               JOIN periods p ON te.period_id = p.id
               JOIN subjects sub ON te.subject_id = sub.id
               LEFT JOIN teachers t ON te.teacher_id = t.id
               LEFT JOIN rooms rm ON te.room_id = rm.id
               WHERE te.stream_id = ?""",
            (stream["id"],),
        )
        cells = {(r["day"], r["period_number"]): f"{r['subject_name']} ({r['teacher_name'] or '-'}, {r['room_name'] or '-'})" for r in rows}
        title = f"Timetable for {stream['name']}"
    else:
        teacher = db.fetch_one("SELECT * FROM teachers WHERE id=?", (target,))
        if not teacher:
            return None
        rows = db.fetch_all(
            """SELECT p.day, p.period_number, sub.name as subject_name,
                      st.name as stream_name, rm.name as room_name
               FROM timetable_entries te
               JOIN periods p ON te.period_id = p.id
               JOIN subjects sub ON te.subject_id = sub.id
               JOIN streams st ON te.stream_id = st.id
               LEFT JOIN rooms rm ON te.room_id = rm.id
               WHERE te.teacher_id = ?""",
            (teacher["id"],),
        )
        cells = {(r["day"], r["period_number"]): f"{r['subject_name']} - {r['stream_name']} ({r['room_name'] or '-'})" for r in rows}
        title = f"Timetable for {teacher['name']}"

    return title, days, display_rows, cells


@app.route("/view")
def view_page():
    streams = db.fetch_all(
        """SELECT s.id, s.name, g.name as grade_name FROM streams s
           JOIN grades g ON s.grade_id = g.id ORDER BY g.id, s.name"""
    )
    teachers = db.fetch_all("SELECT id, name FROM teachers ORDER BY name")

    mode = request.args.get("mode", "stream")
    target = request.args.get("target", type=int)

    grid = None
    if target:
        grid = _grid_data(mode, target)

    return render_template(
        "view.html", streams=streams, teachers=teachers, mode=mode, target=target, grid=grid,
    )


@app.route("/export.csv")
def export_csv():
    mode = request.args.get("mode", "stream")
    target = request.args.get("target", type=int)
    data = _grid_data(mode, target)
    if not data:
        return "Nothing to export", 400
    title, days, display_rows, cells = data

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Period", "Time"] + days)
    for r in display_rows:
        if r["type"] == "break":
            row = [r["label"], f"{r['start_time']}-{r['end_time']}"] + [""] * len(days)
        else:
            pnum = r["period_number"]
            row = [f"P{pnum}", f"{r['start_time']}-{r['end_time']}"] + [cells.get((d, pnum), "") for d in days]
        writer.writerow(row)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={title.replace(' ', '_')}.csv"},
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
