"""Tests for bodn.power.IdleTracker (pure logic)."""

from bodn.power import IdleTracker


class TestIdleTracker:
    def test_starts_awake(self):
        t = IdleTracker(timeout_s=10, time_fn=lambda: 0)
        assert not t.sleeping
        assert not t.tick()

    def test_sleeps_after_timeout(self):
        now = [0]
        t = IdleTracker(timeout_s=10, time_fn=lambda: now[0])
        now[0] = 10
        assert t.tick() is True
        assert t.sleeping

    def test_poke_resets_timer(self):
        now = [0]
        t = IdleTracker(timeout_s=10, time_fn=lambda: now[0])
        now[0] = 8
        t.poke()
        now[0] = 15
        assert not t.tick()  # only 7s since poke
        now[0] = 18
        assert t.tick()  # 10s since poke

    def test_disabled_when_zero(self):
        now = [0]
        t = IdleTracker(timeout_s=0, time_fn=lambda: now[0])
        now[0] = 9999
        assert not t.tick()
        assert not t.sleeping

    def test_wake_resets(self):
        now = [0]
        t = IdleTracker(timeout_s=5, time_fn=lambda: now[0])
        now[0] = 5
        t.tick()
        assert t.sleeping
        now[0] = 6
        t.wake()
        assert not t.sleeping
        now[0] = 10
        assert not t.tick()  # only 4s since wake
        now[0] = 11
        assert t.tick()  # 5s since wake

    def test_tick_returns_true_only_once(self):
        now = [0]
        t = IdleTracker(timeout_s=5, time_fn=lambda: now[0])
        now[0] = 5
        assert t.tick() is True
        assert t.tick() is False  # already sleeping

    def test_seconds_until_sleep(self):
        now = [0]
        t = IdleTracker(timeout_s=10, time_fn=lambda: now[0])
        assert t.seconds_until_sleep() == 10
        now[0] = 3
        assert t.seconds_until_sleep() == 7

    def test_seconds_until_sleep_disabled(self):
        t = IdleTracker(timeout_s=0, time_fn=lambda: 0)
        assert t.seconds_until_sleep() == 0

    def test_timeout_setter(self):
        t = IdleTracker(timeout_s=10, time_fn=lambda: 0)
        t.timeout_s = 20
        assert t.timeout_s == 20

    def test_timeout_setter_clamps_negative(self):
        t = IdleTracker(timeout_s=10, time_fn=lambda: 0)
        t.timeout_s = -5
        assert t.timeout_s == 0
