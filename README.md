# Testy Timetables — Onboarding Wizard

A one-time setup flow for brand-new schools: language choice, teachers,
leave policy, and scheduling rules — plus a welcome screen with a read-only
demo and tutorials. Fires **once per school**, not once per user, so
existing schools are never interrupted or reset.

## What's in this folder

```
migrations/0001_add_onboarding_fields.sql   Adds onboarding columns to your School table
onboarding/__init__.py                       Blueprint definition
onboarding/routes.py                         Wizard routes (welcome → teachers → leave → rules → complete)
onboarding/demo_data.py                      Static demo dataset (never touches real DB rows)
templates/onboarding/_base.html              Shared layout + progress rail
templates/onboarding/welcome.html            Salutation, language picker, demo/tutorial links
templates/onboarding/teachers.html           Step 1
templates/onboarding/leave.html              Step 2
templates/onboarding/rules.html              Step 3 (onboarding-scoped, separate from your existing rules.html)
templates/onboarding/complete.html           Step 4
templates/onboarding/demo.html               Read-only demo timetable
static/css/onboarding.css                    Design system for all of the above
static/js/onboarding.js                      Row add/remove + smooth scroll
```

## 1. Run the migration

In the Render console (or via `psql`) against your production database:

```bash
psql $DATABASE_URL -f migrations/0001_add_onboarding_fields.sql
```

This adds `language`, `onboarding_completed`, `onboarding_step`,
`onboarding_started_at`, `onboarding_completed_at` to your `schools` table,
and marks any school that already has teachers as already onboarded — so
nobody currently using the app gets dropped into the wizard.

## 2. Fix the three imports in `onboarding/routes.py`

```python
from app import db
from models import School, Teacher, LeaveType
```

Point these at wherever your `db = SQLAlchemy()` instance and your actual
model classes live. If your models use different field names (e.g.
`full_name` instead of `name`), adjust the `Teacher(...)` / `LeaveType(...)`
constructor calls in `routes.py` to match.

## 3. Register the blueprint

In your main app file:

```python
from onboarding import onboarding_bp
app.register_blueprint(onboarding_bp)
```

## 4. Guard your existing routes

Add this to your app so any school that hasn't finished setup gets sent to
the wizard instead of the real dashboard — this is what makes it a
"new person starts with a clean slate" experience:

```python
ONBOARDING_ENDPOINTS = {"onboarding.welcome", "onboarding.teachers",
                         "onboarding.leave", "onboarding.rules",
                         "onboarding.complete", "onboarding.demo",
                         "static", "login", "logout"}

@app.before_request
def enforce_onboarding():
    if current_user.is_authenticated:
        school = current_user.school
        if not school.onboarding_completed and request.endpoint not in ONBOARDING_ENDPOINTS:
            return redirect(url_for("onboarding.welcome"))
```

## 5. Make sure new schools start clean

Wherever you currently create a `School` row (signup, admin-creates-school,
etc.), do not copy any teachers/leave types/rules from another school or a
template. `onboarding_completed` defaults to `False`, which is all that's
needed — the wizard and the before_request guard do the rest.

```python
school = School(name=request.form["name"])  # onboarding_completed defaults False
db.session.add(school)
db.session.commit()
return redirect(url_for("onboarding.welcome"))
```

## 6. Swap the dashboard redirect

In `onboarding/routes.py`, the `complete()` view redirects to
`url_for("dashboard")` — change `"dashboard"` to whatever your real
post-setup landing endpoint is named.

## Design notes

The setup rail on the left is a small timetable grid — each setup step is a
"period" (P1, P2, P3...) that lights up as it's completed, echoing the
product's own core object instead of a generic progress bar. Colors and
type (Zilla Slab / Inter / IBM Plex Mono) live entirely in
`onboarding.css` as CSS variables, so re-theming later is a one-file change.

## Notes on the demo

`/onboarding/demo` is intentionally **not authenticated** and reads only
from `onboarding/demo_data.py` — a plain Python file, not the database. A
visitor can open it, look around, and close it without any risk of writing
to or reading a real school's data.
