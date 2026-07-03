# School Timetable Manager — Web version (Flask, for Render)

The same timetable-building tool as before, now as a web app you can deploy
on [Render](https://render.com) so anyone at the school can use it from a
browser, no installs needed.

## Curriculum structure

- **Form 1** removed completely.
- **Form 2** replaced by **Grade 10** under the Kenyan CBC / CBE Senior
  School structure (STEM / Social Sciences / Arts & Sports Science
  pathways), pre-loaded with the current core + pathway subjects.
- **Form 3** and **Form 4** stay on the legacy 8-4-4 curriculum, pre-loaded
  with the standard subject list.

You can edit any of this from the app itself once it's running.

## Features

- Grades & Streams, Subjects, Teachers, Rooms — full add/delete management
- **Timetable Builder** — click-to-edit weekly grid per stream, with live
  conflict detection (warns if a teacher or room is already booked
  elsewhere in that period, lets you override or cancel)
- **View / Export** — view any stream's or teacher's timetable, export to
  CSV

## Tech stack

Flask (Python), server-rendered pages with a bit of JavaScript for the
interactive timetable grid (no build step, no npm needed). The data layer
talks to **SQLite locally** and **PostgreSQL on Render** — see below.

## How this is structured for Render's free plan

Render's free web services have an *ephemeral* filesystem, so a SQLite
file would get wiped on every restart/redeploy, and free web services
can't attach a persistent disk at all (only paid plans support that).

Instead of paying for a disk, this app pairs the free web service with
Render's **free PostgreSQL database**, a separate free resource Render
offers. `render.yaml` provisions both and wires them together
automatically — you don't need to touch any connection strings by hand.

`database.py` picks its backend automatically:
- **Locally:** no `DATABASE_URL` is set, so it uses a SQLite file
  (`timetable.db`) — zero setup for local dev.
- **On Render:** `render.yaml` injects `DATABASE_URL` from the linked
  Postgres database, so the app switches to Postgres automatically. Every
  other file (routes, templates) is unaware of the difference.

**The tradeoff to know about, so it doesn't surprise you:** Render's free
Postgres database **expires 30 days after creation**. You get a 14-day
grace period to upgrade to a paid instance (from $6/month) before Render
deletes the database and its data. Render emails you as the deadline
approaches. Free Postgres also has no backups and is capped at 1GB
storage / 256MB RAM — comfortable for this app's data, but plan to
upgrade before day 30 if you want the timetable to keep existing.
The free web service itself also spins down after 15 minutes of
inactivity; the next visit wakes it up in 30-60 seconds.

If a school intends to actually rely on this long-term, budget for
Render's ~$6-7/month Postgres tier before the 30-day mark — everything
else in this setup (the web service) can stay on the free plan.

## How to deploy on Render

1. **Put this folder in a GitHub repo.** Create a new repo, add these
   files, commit, and push. (Render deploys from a Git repository — it
   doesn't accept a raw folder upload.)
2. In the [Render dashboard](https://dashboard.render.com), click
   **New +** → **Blueprint**, and point it at your repo. Render reads
   `render.yaml` and sets up both the free web service and the free
   Postgres database automatically, including linking `DATABASE_URL`
   between them.
3. Click **Apply** / **Deploy**. The first deploy takes a couple of
   minutes. Once it's live, Render gives you a public URL like
   `https://school-timetable.onrender.com`.
4. Visit that URL — the app creates its schema and seed data in the
   Postgres database automatically on first run.
5. Put a reminder on your calendar for ~25 days out, so you can upgrade
   the database before the free 30-day window closes if you want to keep
   using it.

### Manual setup (without the Blueprint)

If you'd rather set it up by hand instead of using `render.yaml`:

1. New + → **PostgreSQL** → free plan → create it, then copy its
   **Internal Database URL** from the database's page.
2. New + → **Web Service** → connect your repo.
3. **Runtime:** Python 3
4. **Plan:** Free
5. **Build command:** `pip install -r requirements.txt`
6. **Start command:** `gunicorn app:app --bind 0.0.0.0:$PORT`
7. Add an environment variable `DATABASE_URL` set to the Internal
   Database URL you copied in step 1.

## Running it locally first (optional but recommended)

```
pip install -r requirements.txt
python app.py
```
Then open http://localhost:5000 in your browser. No `DATABASE_URL` means
it creates `timetable.db` in this folder automatically — no Postgres
needed for local dev.

If you want to test against Postgres locally too, set `DATABASE_URL`
before running (e.g. to a local Postgres instance, or to your Render
database's *External* connection string) and `python app.py` will use
that instead.

## Files

- `app.py` — Flask routes and application logic
- `database.py` — schema, seed data, and data-access helpers; auto-selects
  SQLite (local) or PostgreSQL (on Render) based on `DATABASE_URL`
- `templates/` — HTML pages (Jinja2)
- `static/style.css` — styling
- `requirements.txt` — Python dependencies (Flask, gunicorn, psycopg2)
- `render.yaml` — Render Blueprint config: free web service + free
  Postgres database, linked together (see persistence note above)
- `.gitignore` — keeps the local database and caches out of Git
