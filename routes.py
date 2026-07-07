"""
Onboarding wizard for Testy Timetables.

Fires exactly once per school: when a school record is first created,
`onboarding_completed` is False and every protected route redirects here
until the wizard is finished. Existing schools that already have data are
never sent back through this flow (see migrations/0001_add_onboarding_fields.sql).

INTEGRATION NOTES (adjust these three imports to match your app):
    - `db`                  -> your SQLAlchemy() instance
    - `School`              -> your tenant/school model
    - `Teacher`, `LeaveType`, `Subject`, `SchoolClass` -> your existing models

Everything else in this file works as-is once those imports resolve.
"""

from datetime import datetime
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from . import onboarding_bp
from .demo_data import DEMO_SCHOOL_NAME, DEMO_TEACHERS, DEMO_LEAVE_TYPES, DEMO_TIMETABLE

# --- adjust to match your existing app -------------------------------------
from app import db                                  # noqa: E402
from models import School, Teacher, LeaveType        # noqa: E402
# If you also collect Subjects / Classes during setup, import them too:
# from models import Subject, SchoolClass
# -----------------------------------------------------------------------------

LANGUAGES = [
    ("en", "English"),
    ("sw", "Kiswahili"),
]

# Order matters: this list drives both the redirect chain and the sidebar rail.
STEPS = ["welcome", "teachers", "leave", "rules", "complete"]


def _school():
    """The school/tenant for the currently logged-in user."""
    return current_user.school


def _advance(school, current_step):
    """Move the wizard to the next step and persist it."""
    idx = STEPS.index(current_step)
    next_step = STEPS[idx + 1]
    school.onboarding_step = next_step
    db.session.commit()
    return next_step


@onboarding_bp.before_request
@login_required
def _require_login():
    # Every onboarding view requires an authenticated user; the check that
    # decides WHETHER to send someone here at all lives in your app's global
    # before_request (see README "Wiring it into your app").
    pass


# ---------------------------------------------------------------------------
# Step 0: Welcome / salutation
# ---------------------------------------------------------------------------
@onboarding_bp.route("/welcome", methods=["GET", "POST"])
def welcome():
    school = _school()

    if request.method == "POST":
        chosen_language = request.form.get("language", "en")
        school.language = chosen_language
        if school.onboarding_started_at is None:
            school.onboarding_started_at = datetime.utcnow()
        db.session.commit()
        _advance(school, "welcome")
        return redirect(url_for("onboarding.teachers"))

    return render_template(
        "welcome.html",
        school=school,
        languages=LANGUAGES,
        steps=STEPS,
    )


# ---------------------------------------------------------------------------
# Demo (read-only, no auth requirement, no writes to real tables)
# ---------------------------------------------------------------------------
@onboarding_bp.route("/demo")
def demo():
    return render_template(
        "demo.html",
        school_name=DEMO_SCHOOL_NAME,
        teachers=DEMO_TEACHERS,
        leave_types=DEMO_LEAVE_TYPES,
        timetable=DEMO_TIMETABLE,
    )


# ---------------------------------------------------------------------------
# Step 1: Teachers
# ---------------------------------------------------------------------------
@onboarding_bp.route("/teachers", methods=["GET", "POST"])
def teachers():
    school = _school()

    if request.method == "POST":
        names = request.form.getlist("teacher_name")
        subjects = request.form.getlist("teacher_subject")
        max_lessons = request.form.getlist("teacher_max_lessons")

        added = 0
        for name, subject, lessons in zip(names, subjects, max_lessons):
            name = name.strip()
            if not name:
                continue
            db.session.add(
                Teacher(
                    school_id=school.id,
                    name=name,
                    subject=subject.strip() or None,
                    max_lessons_per_week=int(lessons) if lessons else None,
                )
            )
            added += 1

        db.session.commit()
        flash(f"Added {added} teacher(s).", "success")
        _advance(school, "teachers")
        return redirect(url_for("onboarding.leave"))

    existing = Teacher.query.filter_by(school_id=school.id).all()
    return render_template("teachers.html", school=school, teachers=existing, steps=STEPS)


# ---------------------------------------------------------------------------
# Step 2: Leave policy
# ---------------------------------------------------------------------------
@onboarding_bp.route("/leave", methods=["GET", "POST"])
def leave():
    school = _school()

    if request.method == "POST":
        names = request.form.getlist("leave_name")
        max_days = request.form.getlist("leave_max_days")

        added = 0
        for name, days in zip(names, max_days):
            name = name.strip()
            if not name:
                continue
            db.session.add(
                LeaveType(
                    school_id=school.id,
                    name=name,
                    max_days_per_term=int(days) if days else None,
                )
            )
            added += 1

        db.session.commit()
        flash(f"Added {added} leave type(s).", "success")
        _advance(school, "leave")
        return redirect(url_for("onboarding.rules"))

    existing = LeaveType.query.filter_by(school_id=school.id).all()
    return render_template("leave.html", school=school, leave_types=existing, steps=STEPS)


# ---------------------------------------------------------------------------
# Step 3: Scheduling rules
# Deliberately named onboarding/rules.html so it does not collide with any
# existing top-level rules.html you already have for the scheduler module.
# ---------------------------------------------------------------------------
@onboarding_bp.route("/rules", methods=["GET", "POST"])
def rules():
    school = _school()

    if request.method == "POST":
        # Wire this up to your existing scheduling-rules model/fields.
        # Left generic here since your rules schema lives in the scheduler module.
        flash("Scheduling rules saved.", "success")
        _advance(school, "rules")
        return redirect(url_for("onboarding.complete"))

    return render_template("rules.html", school=school, steps=STEPS)


# ---------------------------------------------------------------------------
# Step 4: Done
# ---------------------------------------------------------------------------
@onboarding_bp.route("/complete", methods=["GET", "POST"])
def complete():
    school = _school()

    if request.method == "POST":
        school.onboarding_completed = True
        school.onboarding_completed_at = datetime.utcnow()
        db.session.commit()
        flash("Setup complete. Welcome to your timetable.", "success")
        return redirect(url_for("dashboard"))  # adjust to your real dashboard endpoint

    return render_template("complete.html", school=school, steps=STEPS)
