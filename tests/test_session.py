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
    MODE_FREE_PLAY,
    MODE_SOUND_MIXER,
)
from bodn.storage import DEFAULT_SETTINGS


def make_session(settings=None, start_time=0, on_session_end=None):
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

    mgr = SessionManager(s, get_time, get_date, on_session_end=on_session_end)
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

        now[0] = 300
        mgr.tick()
        assert mgr.state == WARN_5

        now[0] = 480
        mgr.tick()
        assert mgr.state == WARN_2

        now[0] = 600
        mgr.tick()
        assert mgr.state == WINDDOWN

        now[0] = 630
        mgr.tick()
        assert mgr.state == SLEEPING

        mgr.tick()
        assert mgr.state == COOLDOWN

        now[0] = 690
        mgr.tick()
        assert mgr.state == IDLE

    def test_sessions_today_increments(self):
        mgr, now, _ = make_session({"max_session_min": 1, "break_min": 0})
        mgr.try_wake()
        now[0] = 60
        mgr.tick()  # WINDDOWN
        now[0] = 90
        mgr.tick()  # SLEEPING
        assert mgr.sessions_today == 1


class TestLimits:
    def test_max_sessions_blocks_wake(self):
        mgr, now, _ = make_session(
            {"max_session_min": 1, "max_sessions_day": 2, "break_min": 0}
        )
        for i in range(2):
            assert mgr.try_wake()
            now[0] += 60
            mgr.tick()  # WINDDOWN
            now[0] += 30
            mgr.tick()  # SLEEPING
            mgr.tick()  # COOLDOWN
            now[0] += 1
            mgr.tick()  # IDLE

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
        mgr, now, _ = make_session({"quiet_start": "21:00", "quiet_end": "07:00"})
        now[0] = 79200
        assert not mgr.try_wake()

    def test_quiet_hours_same_day(self):
        mgr, now, _ = make_session({"quiet_start": "13:00", "quiet_end": "15:00"})
        now[0] = 50400
        assert not mgr.try_wake()

    def test_outside_quiet_hours_ok(self):
        mgr, now, _ = make_session({"quiet_start": "21:00", "quiet_end": "07:00"})
        now[0] = 36000
        assert mgr.try_wake()


class TestDayRollover:
    def test_new_day_resets_count(self):
        mgr, now, date = make_session(
            {"max_session_min": 1, "max_sessions_day": 1, "break_min": 0}
        )
        mgr.try_wake()
        now[0] = 60
        mgr.tick()
        now[0] = 90
        mgr.tick()
        mgr.tick()
        now[0] = 91
        mgr.tick()
        assert mgr.sessions_today == 1
        assert not mgr.try_wake()

        date[0] = "2026-03-20"
        mgr.tick()
        assert mgr.sessions_today == 0
        assert mgr.try_wake()


class TestSettingsChangeMidSession:
    def test_shorter_limit_ends_session_early(self):
        mgr, now, _ = make_session({"max_session_min": 20})
        mgr.try_wake()
        now[0] = 300
        mgr.settings["max_session_min"] = 5
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


class TestCooldownRemaining:
    def test_zero_when_idle(self):
        mgr, _, _ = make_session()
        assert mgr.cooldown_remaining_s == 0

    def test_zero_while_playing(self):
        mgr, _, _ = make_session()
        mgr.try_wake()
        assert mgr.cooldown_remaining_s == 0

    def test_counts_down_during_cooldown(self):
        mgr, now, _ = make_session({"max_session_min": 1, "break_min": 2})
        mgr.try_wake()
        now[0] = 60
        mgr.tick()  # WINDDOWN
        now[0] = 90
        mgr.tick()  # SLEEPING
        mgr.tick()  # COOLDOWN
        assert mgr.state == COOLDOWN
        assert mgr.cooldown_remaining_s == 120  # 2 min break
        now[0] = 150
        assert mgr.cooldown_remaining_s == 60
        now[0] = 210
        assert mgr.cooldown_remaining_s == 0

    def test_includes_winddown_grace(self):
        mgr, now, _ = make_session({"max_session_min": 1, "break_min": 2})
        mgr.try_wake()
        now[0] = 60
        mgr.tick()  # WINDDOWN (sleep_start = 60)
        assert mgr.state == WINDDOWN
        # 30s winddown + 120s break = 150s until IDLE
        assert mgr.cooldown_remaining_s == 150
        now[0] = 75
        assert mgr.cooldown_remaining_s == 135  # 15s winddown left + 120

    def test_zero_when_sessions_disabled(self):
        mgr, _, _ = make_session({"sessions_enabled": False})
        assert mgr.cooldown_remaining_s == 0


class TestResumeNow:
    def test_resume_from_cooldown(self):
        mgr, now, _ = make_session({"max_session_min": 1, "break_min": 5})
        mgr.try_wake()
        now[0] = 60
        mgr.tick()  # WINDDOWN
        now[0] = 90
        mgr.tick()  # SLEEPING
        mgr.tick()  # COOLDOWN
        assert mgr.state == COOLDOWN
        assert mgr.resume_now() is True
        assert mgr.state == IDLE
        assert mgr.try_wake()

    def test_resume_from_winddown_records_session(self):
        records = []
        mgr, now, _ = make_session(
            {"max_session_min": 1, "break_min": 5},
            on_session_end=lambda r: records.append(r),
        )
        mgr.try_wake()
        now[0] = 60
        mgr.tick()  # WINDDOWN
        assert mgr.state == WINDDOWN
        assert mgr.resume_now() is True
        assert mgr.state == IDLE
        assert len(records) == 1
        assert records[0]["end_reason"] == "normal"
        assert mgr.sessions_today == 1

    def test_resume_is_noop_while_playing(self):
        mgr, _, _ = make_session()
        mgr.try_wake()
        assert mgr.resume_now() is False
        assert mgr.state == PLAYING

    def test_resume_is_noop_while_idle(self):
        mgr, _, _ = make_session()
        assert mgr.resume_now() is False
        assert mgr.state == IDLE


class TestModeLimits:
    def test_default_mode_is_free_play(self):
        mgr, _, _ = make_session()
        assert mgr.mode == MODE_FREE_PLAY

    def test_wake_with_mode(self):
        mgr, _, _ = make_session()
        mgr.try_wake(mode=MODE_SOUND_MIXER)
        assert mgr.mode == MODE_SOUND_MIXER

    def test_per_mode_limit_shorter(self):
        mgr, now, _ = make_session(
            {
                "max_session_min": 20,
                "mode_limits": {"sound_mixer": 5},
            }
        )
        mgr.try_wake(mode=MODE_SOUND_MIXER)
        assert mgr.time_remaining_s == 300  # 5 min

    def test_per_mode_limit_falls_back_to_global(self):
        mgr, now, _ = make_session(
            {
                "max_session_min": 10,
                "mode_limits": {"sound_mixer": 5},
            }
        )
        mgr.try_wake(mode=MODE_FREE_PLAY)
        assert mgr.time_remaining_s == 600  # 10 min (global)

    def test_per_mode_limit_zero_is_unlimited(self):
        mgr, now, _ = make_session(
            {
                "max_session_min": 10,
                "mode_limits": {"free_play": 0},
            }
        )
        mgr.try_wake(mode=MODE_FREE_PLAY)
        assert mgr.time_remaining_s == 9999  # unlimited

    def test_unlimited_mode_never_warns(self):
        mgr, now, _ = make_session(
            {
                "max_session_min": 10,
                "mode_limits": {"free_play": 0},
            }
        )
        mgr.try_wake(mode=MODE_FREE_PLAY)
        now[0] = 3600  # 1 hour in
        mgr.tick()
        assert mgr.state == PLAYING  # still playing, no warning

    def test_set_mode_changes_limit(self):
        mgr, now, _ = make_session(
            {
                "max_session_min": 20,
                "mode_limits": {"sound_mixer": 3},
            }
        )
        mgr.try_wake()
        assert mgr.time_remaining_s == 1200  # 20 min global
        mgr.set_mode(MODE_SOUND_MIXER)
        assert mgr.time_remaining_s == 180  # 3 min


class TestSessionCallback:
    def test_callback_fires_on_normal_end(self):
        records = []
        mgr, now, _ = make_session(
            {"max_session_min": 1, "break_min": 0},
            on_session_end=lambda r: records.append(r),
        )
        mgr.try_wake()
        now[0] = 60
        mgr.tick()  # WINDDOWN
        now[0] = 90
        mgr.tick()  # SLEEPING — callback fires here
        assert len(records) == 1
        assert records[0]["end_reason"] == "normal"
        assert records[0]["mode"] == MODE_FREE_PLAY
        assert records[0]["date"] == "2026-03-19"
        assert records[0]["duration_s"] == 90

    def test_callback_fires_on_force_sleep(self):
        records = []
        mgr, now, _ = make_session(
            on_session_end=lambda r: records.append(r),
        )
        mgr.try_wake()
        now[0] = 120
        mgr.force_sleep()
        assert len(records) == 1
        assert records[0]["end_reason"] == "force_sleep"
        assert records[0]["duration_s"] == 120

    def test_callback_includes_mode(self):
        records = []
        mgr, now, _ = make_session(
            {"max_session_min": 1},
            on_session_end=lambda r: records.append(r),
        )
        mgr.try_wake(mode=MODE_SOUND_MIXER)
        now[0] = 60
        mgr.tick()  # WINDDOWN
        now[0] = 90
        mgr.tick()  # SLEEPING
        assert records[0]["mode"] == MODE_SOUND_MIXER

    def test_no_callback_if_none(self):
        """No crash when on_session_end is not set."""
        mgr, now, _ = make_session({"max_session_min": 1})
        mgr.try_wake()
        now[0] = 60
        mgr.tick()
        now[0] = 90
        mgr.tick()
        assert mgr.sessions_today == 1

    def test_callback_has_start_time(self):
        records = []
        mgr, now, _ = make_session(
            {"max_session_min": 1},
            start_time=3600,  # 01:00:00
            on_session_end=lambda r: records.append(r),
        )
        mgr.try_wake()
        now[0] = 3660
        mgr.tick()
        now[0] = 3690
        mgr.tick()
        assert records[0]["start_time"] == "01:00"
