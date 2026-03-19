import json
import os
import tempfile

import pytest

from bodn.storage import (
    DEFAULT_SETTINGS,
    load_settings,
    save_settings,
    load_sessions,
    save_session,
    sessions_today,
    SETTINGS_PATH,
    SESSIONS_PATH,
)
import bodn.storage as storage_mod


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path, monkeypatch):
    """Redirect storage paths to a temp directory."""
    settings_path = str(tmp_path / "settings.json")
    sessions_path = str(tmp_path / "sessions.json")
    monkeypatch.setattr(storage_mod, "SETTINGS_PATH", settings_path)
    monkeypatch.setattr(storage_mod, "SESSIONS_PATH", sessions_path)
    return tmp_path


class TestSettings:
    def test_defaults_when_no_file(self):
        settings = load_settings()
        assert settings == DEFAULT_SETTINGS

    def test_save_and_load_round_trip(self):
        custom = dict(DEFAULT_SETTINGS, max_session_min=10, lockdown=True)
        save_settings(custom)
        loaded = load_settings()
        assert loaded["max_session_min"] == 10
        assert loaded["lockdown"] is True

    def test_missing_keys_get_defaults(self):
        """If saved file has fewer keys, defaults fill in."""
        save_settings({"max_session_min": 5})
        loaded = load_settings()
        assert loaded["max_session_min"] == 5
        assert loaded["break_min"] == DEFAULT_SETTINGS["break_min"]

    def test_corrupt_file_returns_defaults(self, tmp_data_dir):
        path = str(tmp_data_dir / "settings.json")
        with open(path, "w") as f:
            f.write("NOT JSON{{{")
        settings = load_settings()
        assert settings == DEFAULT_SETTINGS


class TestSessions:
    def test_empty_when_no_file(self):
        assert load_sessions() == []

    def test_save_and_load_session(self):
        session = {"date": "2026-03-19", "start": 1000, "duration": 600}
        save_session(session)
        loaded = load_sessions()
        assert len(loaded) == 1
        assert loaded[0]["date"] == "2026-03-19"

    def test_multiple_sessions_accumulate(self):
        for i in range(3):
            save_session({"date": "2026-03-19", "start": 1000 + i * 1000, "duration": 600})
        assert len(load_sessions()) == 3

    def test_ring_buffer_prunes_old_dates(self):
        """Only keep MAX_SESSION_DAYS days of history."""
        for day in range(10):
            save_session({"date": f"2026-03-{day + 1:02d}", "start": 0, "duration": 600})
        sessions = load_sessions()
        dates = set(s["date"] for s in sessions)
        assert len(dates) <= 7

    def test_sessions_today_filters(self):
        save_session({"date": "2026-03-19", "start": 1000, "duration": 600})
        save_session({"date": "2026-03-18", "start": 500, "duration": 600})
        save_session({"date": "2026-03-19", "start": 2000, "duration": 600})
        today = sessions_today("2026-03-19")
        assert len(today) == 2


class TestAtomicWrite:
    def test_tmp_file_cleaned_up(self, tmp_data_dir):
        save_settings({"test": True})
        tmp_file = str(tmp_data_dir / "settings.json.tmp")
        assert not os.path.exists(tmp_file)
