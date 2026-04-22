import os

import pytest

from bodn.storage import (
    DEFAULT_SETTINGS,
    load_settings,
    save_settings,
    load_sessions,
    save_session,
    sessions_today,
    compute_stats,
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

    def test_underscore_keys_are_not_persisted(self):
        """Runtime-only keys (e.g. _idle_tracker, _pwm, _all_modes) must
        not reach flash — they often hold non-serializable objects."""

        class _Opaque:
            pass

        settings = dict(DEFAULT_SETTINGS)
        settings["_idle_tracker"] = _Opaque()
        settings["_pwm"] = _Opaque()
        settings["_all_modes"] = ["demo", "simon"]
        settings["max_session_min"] = 17
        save_settings(settings)
        loaded = load_settings()
        assert "_idle_tracker" not in loaded
        assert "_pwm" not in loaded
        assert "_all_modes" not in loaded
        assert loaded["max_session_min"] == 17


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
            save_session(
                {"date": "2026-03-19", "start": 1000 + i * 1000, "duration": 600}
            )
        assert len(load_sessions()) == 3

    def test_ring_buffer_prunes_old_dates(self):
        """Only keep MAX_SESSION_DAYS days of history."""
        for day in range(10):
            save_session(
                {"date": f"2026-03-{day + 1:02d}", "start": 0, "duration": 600}
            )
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


class TestModeLimits:
    def test_default_has_empty_mode_limits(self):
        settings = load_settings()
        assert settings["mode_limits"] == {}

    def test_save_and_load_mode_limits(self):
        settings = dict(DEFAULT_SETTINGS)
        settings["mode_limits"] = {"sound_mixer": 5, "recorder": 10}
        save_settings(settings)
        loaded = load_settings()
        assert loaded["mode_limits"]["sound_mixer"] == 5
        assert loaded["mode_limits"]["recorder"] == 10


class TestComputeStats:
    def test_empty_sessions(self):
        stats = compute_stats([])
        assert stats["total_sessions"] == 0
        assert stats["total_play_min"] == 0
        assert stats["suggestions"] == {}

    def test_basic_stats(self):
        sessions = [
            {"date": "2026-03-19", "duration_s": 600, "mode": "free_play"},
            {"date": "2026-03-19", "duration_s": 900, "mode": "sound_mixer"},
            {"date": "2026-03-20", "duration_s": 1200, "mode": "free_play"},
        ]
        stats = compute_stats(sessions)
        assert stats["total_sessions"] == 3
        assert stats["total_play_min"] == 45.0  # (600+900+1200)/60
        assert stats["total_days"] == 2
        assert stats["avg_sessions_per_day"] == 1.5
        assert stats["mode_breakdown"]["free_play"] == 30.0
        assert stats["mode_breakdown"]["sound_mixer"] == 15.0

    def test_daily_totals(self):
        sessions = [
            {"date": "2026-03-19", "duration_s": 600, "mode": "free_play"},
            {"date": "2026-03-19", "duration_s": 600, "mode": "free_play"},
            {"date": "2026-03-20", "duration_s": 300, "mode": "free_play"},
        ]
        stats = compute_stats(sessions)
        daily = stats["daily_totals"]
        assert len(daily) == 2
        assert daily[0]["date"] == "2026-03-19"
        assert daily[0]["play_min"] == 20.0
        assert daily[0]["sessions"] == 2

    def test_suggestions_round_up(self):
        sessions = [
            {"date": "2026-03-19", "duration_s": 720, "mode": "free_play"},  # 12 min
            {"date": "2026-03-20", "duration_s": 480, "mode": "free_play"},  # 8 min
        ]
        stats = compute_stats(sessions)
        # avg session = 10 min → suggest 10
        assert stats["suggestions"]["max_session_min"] == 10
        assert stats["suggestions"]["max_sessions_day"] == 1

    def test_suggestions_high_usage_note(self):
        sessions = [
            {"date": "2026-03-19", "duration_s": 3600, "mode": "free_play"},  # 60 min
            {"date": "2026-03-19", "duration_s": 600, "mode": "free_play"},  # 10 min
        ]
        stats = compute_stats(sessions)
        assert stats["suggestions"]["note"] is not None
        assert "70 min" in stats["suggestions"]["note"]

    def test_suggestions_minimum_values(self):
        sessions = [
            {"date": "2026-03-19", "duration_s": 60, "mode": "free_play"},  # 1 min
        ]
        stats = compute_stats(sessions)
        assert stats["suggestions"]["max_session_min"] >= 5  # minimum 5
        assert stats["suggestions"]["max_sessions_day"] >= 1
