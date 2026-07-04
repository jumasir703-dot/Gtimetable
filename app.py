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
    teachers = db.fetch_all("SELECT * FROM teachers ORDER BY name")
    selected_id = request.args.get("teacher_id", type=int)
    all_subjects = db.fetch_all(
        """SELECT sub.id, sub.name, g.name as grade_name FROM subjects sub
           JOIN grades g ON sub.grade_id = g.id ORDER BY g.id, sub.name"""
    )
    assigned_ids = set()
    if selected_id:
        assigned_ids = {r["subject_id"] for r in db.fetch_all(
            "SELECT subject_id FROM teacher_subjects WHERE teacher_id=?", (selected_id,))}
    return render_template(
        "teachers.html", teachers=teachers, selected_id=selected_id,
        all_subjects=all_subjects, assigned_ids=assigned_ids,
    )


@app.route("/teachers/add", methods=["POST"])
def add_teacher():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    if not name:
        flash("Enter a teacher name.", "error")
        return redirect(url_for("teachers_page"))
    db.execute("INSERT INTO teachers (name, email) VALUES (?, ?)", (name, email))
    return redirect(url_for("teachers_page"))


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
    return render_template("rules.html", settings=settings)


@app.route("/rules/save", methods=["POST"])
def save_rules():
    # Checkbox: present in form data only when checked.
    avoid_same_day = "1" if request.form.get("avoid_same_day_repeat") else "0"
    db.set_generation_setting("avoid_same_day_repeat", avoid_same_day)
    flash("Scheduling rules updated.", "success")
    return redirect(url_for("rules_page"))


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

    periods = db.fetch_all("SELECT DISTINCT period_number, start_time, end_time FROM periods ORDER BY period_number")
    days = db.DAYS

    entries = {}
    if stream_id:
        rows = db.fetch_all(
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
        for r in rows:
            entries[(r["day"], r["period_number"])] = r

    return render_template(
        "builder.html", streams=streams, stream_id=stream_id,
        periods=periods, days=days, entries=entries,
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
def _grid_data(mode, target):
    days = db.DAYS
    periods = db.fetch_all("SELECT DISTINCT period_number, start_time, end_time FROM periods ORDER BY period_number")
    period_numbers = [(p["period_number"], p["start_time"], p["end_time"]) for p in periods]

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

    return title, days, period_numbers, cells


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
    title, days, period_numbers, cells = data

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Period", "Time"] + days)
    for pnum, s, e in period_numbers:
        row = [f"P{pnum}", f"{s}-{e}"] + [cells.get((d, pnum), "") for d in days]
        writer.writerow(row)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={title.replace(' ', '_')}.csv"},
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
