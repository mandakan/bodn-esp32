# bodn/storage.py — load/save JSON settings and session history on flash

import os

try:
    import json
except ImportError:
    import ujson as json

SETTINGS_PATH = "/data/settings.json"
SESSIONS_PATH = "/data/sessions.json"

DEFAULT_SETTINGS = {
    "max_session_min": 20,
    "max_sessions_day": 5,
    "break_min": 15,
    "lockdown": False,
    "quiet_start": None,
    "quiet_end": None,
    "wifi_ssid": "",
    "wifi_pass": "",
    "wifi_mode": "ap",
    "ui_pin": "",
    "ota_token": "",
}

# Keep 7 days of session history
MAX_SESSION_DAYS = 7


def _ensure_dir(path):
    """Create parent directory if it doesn't exist."""
    parts = path.rsplit("/", 1)
    if len(parts) == 2 and parts[0]:
        try:
            os.mkdir(parts[0])
        except OSError:
            pass  # already exists


def _atomic_write(path, data):
    """Write JSON atomically: write to .tmp then rename."""
    _ensure_dir(path)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    try:
        os.remove(path)
    except OSError:
        pass
    os.rename(tmp, path)


def load_settings():
    """Load settings from flash, returning defaults for missing keys."""
    settings = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH, "r") as f:
            stored = json.load(f)
        settings.update(stored)
    except (OSError, ValueError):
        pass
    return settings


def save_settings(settings):
    """Save settings dict to flash."""
    _atomic_write(SETTINGS_PATH, settings)


def load_sessions():
    """Load session history from flash. Returns list of session dicts."""
    try:
        with open(SESSIONS_PATH, "r") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def save_session(session):
    """Append a session record and prune entries older than MAX_SESSION_DAYS days."""
    sessions = load_sessions()
    sessions.append(session)
    # Prune: keep only sessions from the last MAX_SESSION_DAYS days
    if sessions and "date" in session:
        # Keep last MAX_SESSION_DAYS unique dates
        dates = sorted(set(s.get("date", "") for s in sessions), reverse=True)
        keep_dates = set(dates[:MAX_SESSION_DAYS])
        sessions = [s for s in sessions if s.get("date", "") in keep_dates]
    _atomic_write(SESSIONS_PATH, sessions)


def sessions_today(date_str):
    """Count sessions for a given date string (YYYY-MM-DD)."""
    sessions = load_sessions()
    return [s for s in sessions if s.get("date") == date_str]
