"""
run_desktop.py — offline desktop launcher for Testy Timetables.

This is the PyInstaller entry point. It does three things app.py itself
doesn't need to worry about when run normally with `flask run` / gunicorn:

1. Points the SQLite database at a writable, persistent folder in the
   user's home directory (~/GTimetableData) instead of the folder the
   app happens to be unpacked into. PyInstaller's --onefile mode
   extracts the app to a temporary folder that's wiped after every run,
   so if we didn't do this, all data would vanish each time the program
   closed.
2. Forces DATABASE_URL to stay unset, so database.py always falls back
   to its local SQLite path — no Postgres, no network, fully offline.
3. Starts the Flask dev server on localhost only (not 0.0.0.0) with
   debug/reloader off (those don't play well with a frozen executable)
   and opens the user's default browser to it automatically.
"""

import os
import sys
import threading
import time
import traceback
import webbrowser

# --- 1 & 2: decide where the database lives, before app/database import it ---
if getattr(sys, "frozen", False):
    # Running as a PyInstaller-built executable.
    DATA_DIR = os.path.join(os.path.expanduser("~"), "GTimetableData")
else:
    # Running as a normal script (e.g. `python run_desktop.py` for testing).
    DATA_DIR = os.path.dirname(os.path.abspath(__file__))

os.makedirs(DATA_DIR, exist_ok=True)
os.environ.setdefault("DB_PATH", os.path.join(DATA_DIR, "timetable.db"))
os.environ.pop("DATABASE_URL", None)  # never talk to Postgres offline


def _log(message):
    """print() can crash a windowed (no-console) build on Windows, since
    sys.stdout is None in that mode. This writes to both the console when
    one exists, and always to a log file, so problems are never invisible."""
    if sys.stdout is not None:
        try:
            print(message)
        except Exception:
            pass
    try:
        with open(os.path.join(DATA_DIR, "app.log"), "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except Exception:
        pass


# Now it's safe to import the app (this is what actually creates the DB).
from app import app  # noqa: E402


@app.context_processor
def _inject_desktop_mode():
    # Tells base.html not to register the PWA service worker (and to
    # unregister any copy a previous run already installed). That service
    # worker is meant for the web-hosted version; in the desktop build its
    # network fetch() gets blocked by Windows/Chrome whenever wifi is off
    # -- even though it's only talking to our own local server -- which
    # was making the app incorrectly show its "offline" page.
    return {"desktop_mode": True}


HOST = "127.0.0.1"
PORT = 5000


def _open_browser():
    time.sleep(1.2)  # give the server a moment to bind the port
    webbrowser.open(f"http://{HOST}:{PORT}/")


if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    _log(f"Testy Timetables is running at http://{HOST}:{PORT}/")
    _log(f"Your data is stored at: {os.environ['DB_PATH']}")
    try:
        app.run(host=HOST, port=PORT, debug=False, use_reloader=False, threaded=True)
    except Exception:
        _log("CRASHED:\n" + traceback.format_exc())
        raise
