import pytest

from bodn.session import (
    SessionManager,
    IDLE,
    PLAYING,
    WARN_5,
    WARN_2,
    WINDDOWN,
    SLEEPING,
    COOLDOWN,
    LOCKDOWN,
)
from bodn.storage import DEFAULT_SETTINGS


def make_session(settings=None, start_time=0):
    """Create a SessionManager with controllable time."""
    _now = [start_time]
    _date = ["2026-03-19"]

    def get_time():
        return _now[0]

    def get_date():
        return _date[0]

    s = DEFAULT_SETTINGS.copy()
    if settings:
        s.update(settings)

    mgr = SessionManager(s, get_time, get_date)
    return mgr, _now, _date


class TestBasicFlow:
    def test_starts_idle(self):
        mgr, _, _ = make_session()
        assert mgr.state == IDLE

    def test_wake_starts_playing(self):
        mgr, now, _ = make_session()
        assert mgr.try_wake()
        assert mgr.state == PLAYING

    def test_time_remaining(self):
        mgr, now, _ = make_session({"max_session_min": 10})
        mgr.try_wake()
        now[0] = 120  # 2 minutes in
        assert mgr.time_remaining_s == 480  # 8 minutes left

    def test_full_session_flow(self):
        """IDLE → PLAYING → WARN_5 → WARN_2 → WINDDOWN → SLEEPING → COOLDOWN → IDLE"""
        mgr, now, _ = make_session({"max_session_min": 10, "break_min": 1})
        mgr.try_wake()
        assert mgr.state == PLAYING

        # Advance to 5-min warning (5 min remaining = 300s from end)
        now[0] = 300  # 5 min in, 5 min left
        mgr.tick()
        assert mgr.state == WARN_5

        # Advance to 2-min warning
        now[0] = 480  # 8 min in, 2 min left
        mgr.tick()
        assert mgr.state == WARN_2

        # Session expires
        now[0] = 600  # 10 min in
        mgr.tick()
        assert mgr.state == WINDDOWN

        # Wind-down lasts 30s
        now[0] = 630
        mgr.tick()
        assert mgr.state == SLEEPING

        # Sleeping transitions to cooldown
        mgr.tick()
        assert mgr.state == COOLDOWN

        # Cooldown for break_min (1 min)
        now[0] = 690  # 60s after sleep start
        mgr.tick()
        assert mgr.state == IDLE

    def test_sessions_today_increments(self):
        mgr, now, _ = make_session({"max_session_min": 1, "break_min": 0})
        mgr.try_wake()
        now[0] = 60  # session expires
        mgr.tick()  # → WINDDOWN
        now[0] = 90
        mgr.tick()  # → SLEEPING
        assert mgr.sessions_today == 1


class TestLimits:
    def test_max_sessions_blocks_wake(self):
        mgr, now, _ = make_session({"max_session_min": 1, "max_sessions_day": 2, "break_min": 0})
        for i in range(2):
            assert mgr.try_wake()
            now[0] += 60
            mgr.tick()  # WINDDOWN
            now[0] += 30
            mgr.tick()  # SLEEPING
            mgr.tick()  # COOLDOWN
            now[0] += 1
            mgr.tick()  # IDLE (break_min=0)

        assert mgr.sessions_today == 2
        assert not mgr.try_wake()

    def test_sessions_remaining(self):
        mgr, _, _ = make_session({"max_sessions_day": 3})
        assert mgr.sessions_remaining == 3


class TestLockdown:
    def test_lockdown_overrides_playing(self):
        mgr, now, _ = make_session()
        mgr.try_wake()
        mgr.settings["lockdown"] = True
        mgr.tick()
        assert mgr.state == LOCKDOWN

    def test_lockdown_blocks_wake(self):
        mgr, _, _ = make_session()
        mgr.settings["lockdown"] = True
        assert not mgr.try_wake()

    def test_lockdown_cleared_goes_idle(self):
        mgr, _, _ = make_session()
        mgr.settings["lockdown"] = True
        mgr.tick()
        assert mgr.state == LOCKDOWN
        mgr.settings["lockdown"] = False
        mgr.tick()
        assert mgr.state == IDLE


class TestQuietHours:
    def test_quiet_hours_triggers_sleep(self):
        # quiet_start=21:00, quiet_end=07:00, time = 22:00 (79200s into day)
        mgr, now, _ = make_session({"quiet_start": "21:00", "quiet_end": "07:00"})
        now[0] = 79200  # 22:00
        mgr.try_wake()  # should fail — quiet hours
        # Actually try_wake checks quiet hours
        assert not mgr.try_wake()

    def test_quiet_hours_same_day(self):
        mgr, now, _ = make_session({"quiet_start": "13:00", "quiet_end": "15:00"})
        now[0] = 50400  # 14:00
        assert not mgr.try_wake()

    def test_outside_quiet_hours_ok(self):
        mgr, now, _ = make_session({"quiet_start": "21:00", "quiet_end": "07:00"})
        now[0] = 36000  # 10:00
        assert mgr.try_wake()


class TestDayRollover:
    def test_new_day_resets_count(self):
        mgr, now, date = make_session({"max_session_min": 1, "max_sessions_day": 1, "break_min": 0})
        mgr.try_wake()
        now[0] = 60
        mgr.tick()  # WINDDOWN
        now[0] = 90
        mgr.tick()  # SLEEPING
        mgr.tick()  # COOLDOWN
        now[0] = 91
        mgr.tick()  # IDLE
        assert mgr.sessions_today == 1
        assert not mgr.try_wake()

        # New day
        date[0] = "2026-03-20"
        mgr.tick()
        assert mgr.sessions_today == 0
        assert mgr.try_wake()


class TestSettingsChangeMidSession:
    def test_shorter_limit_ends_session_early(self):
        mgr, now, _ = make_session({"max_session_min": 20})
        mgr.try_wake()
        now[0] = 300  # 5 min in
        mgr.settings["max_session_min"] = 5  # now limit is 5 min = 300s
        mgr.tick()
        assert mgr.state == WINDDOWN

    def test_lockdown_mid_session(self):
        mgr, now, _ = make_session()
        mgr.try_wake()
        now[0] = 60
        mgr.settings["lockdown"] = True
        mgr.tick()
        assert mgr.state == LOCKDOWN


class TestForceSleep:
    def test_force_sleep_from_playing(self):
        mgr, _, _ = make_session()
        mgr.try_wake()
        mgr.force_sleep()
        assert mgr.state == SLEEPING
        assert mgr.sessions_today == 1
