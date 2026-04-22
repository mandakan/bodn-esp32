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
    "sessions_enabled": True,
    "mode_limits": {},
    "audio_enabled": True,
    "volume": 10,
    "debug_input": False,
    "language": "sv",
    "sleep_timeout_s": 300,
    "tz_offset": 1,
    "ftp_enabled": True,
    "ftp_user": "bodn",
    "ftp_pass": "bodn",
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
    """Save settings dict to flash.

    Keys starting with ``_`` are runtime-only (hardware handles, mode list,
    idle tracker, …) and never persisted.
    """
    persistable = {k: v for k, v in settings.items() if not k.startswith("_")}
    _atomic_write(SETTINGS_PATH, persistable)


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
    """Return sessions for a given date string (YYYY-MM-DD)."""
    sessions = load_sessions()
    return [s for s in sessions if s.get("date") == date_str]


def compute_stats(sessions):
    """Compute usage statistics from a list of session records.

    Returns a dict with aggregated stats for display in the web UI.
    """
    if not sessions:
        return {
            "total_days": 0,
            "total_sessions": 0,
            "total_play_min": 0,
            "avg_session_min": 0,
            "avg_sessions_per_day": 0,
            "avg_daily_play_min": 0,
            "mode_breakdown": {},
            "daily_totals": [],
            "suggestions": {},
        }

    total_sessions = len(sessions)
    total_play_s = sum(s.get("duration_s", 0) for s in sessions)

    # Group by date
    by_date = {}
    for s in sessions:
        d = s.get("date", "")
        if d not in by_date:
            by_date[d] = []
        by_date[d].append(s)

    total_days = max(1, len(by_date))
    avg_session_s = total_play_s / max(1, total_sessions)
    avg_sessions_per_day = total_sessions / total_days
    avg_daily_play_s = total_play_s / total_days

    # Mode breakdown
    mode_play = {}
    for s in sessions:
        mode = s.get("mode", "free_play")
        mode_play[mode] = mode_play.get(mode, 0) + s.get("duration_s", 0)
    mode_breakdown = {}
    for mode, secs in mode_play.items():
        mode_breakdown[mode] = round(secs / 60, 1)

    # Daily totals (for chart)
    daily_totals = []
    for d in sorted(by_date.keys()):
        day_s = sum(s.get("duration_s", 0) for s in by_date[d])
        daily_totals.append(
            {"date": d, "play_min": round(day_s / 60, 1), "sessions": len(by_date[d])}
        )

    # Suggestions
    suggestions = _compute_suggestions(
        avg_session_s, avg_sessions_per_day, avg_daily_play_s
    )

    return {
        "total_days": total_days,
        "total_sessions": total_sessions,
        "total_play_min": round(total_play_s / 60, 1),
        "avg_session_min": round(avg_session_s / 60, 1),
        "avg_sessions_per_day": round(avg_sessions_per_day, 1),
        "avg_daily_play_min": round(avg_daily_play_s / 60, 1),
        "mode_breakdown": mode_breakdown,
        "daily_totals": daily_totals,
        "suggestions": suggestions,
    }


def _compute_suggestions(avg_session_s, avg_sessions_per_day, avg_daily_play_s):
    """Suggest limits based on usage patterns. Conservative for a 4-year-old."""
    avg_session_min = avg_session_s / 60

    # Round average session up to nearest 5 min, minimum 5
    suggested_session = max(5, ((int(avg_session_min) + 4) // 5) * 5)

    # Round average sessions/day up, minimum 1
    suggested_max_sessions = max(1, int(avg_sessions_per_day + 0.9))

    # Flag if daily play exceeds 60 min
    avg_daily_min = avg_daily_play_s / 60
    note = None
    if avg_daily_min > 60:
        note = (
            "Average daily play time is {:.0f} min. Consider shorter sessions.".format(
                avg_daily_min
            )
        )

    return {
        "max_session_min": suggested_session,
        "max_sessions_day": suggested_max_sessions,
        "note": note,
    }
