# bodn/session.py — pure-logic session state machine (no hardware imports)

# States
IDLE = "IDLE"
PLAYING = "PLAYING"
WARN_5 = "WARN_5"
WARN_2 = "WARN_2"
WINDDOWN = "WINDDOWN"
SLEEPING = "SLEEPING"
COOLDOWN = "COOLDOWN"
LOCKDOWN = "LOCKDOWN"

# Known play modes (new modes added here as Milestone 3 progresses)
MODE_FREE_PLAY = "free_play"
MODE_SOUND_MIXER = "sound_mixer"
MODE_RECORDER = "recorder"
MODE_SEQUENCER = "sequencer"
ALL_MODES = [MODE_FREE_PLAY, MODE_SOUND_MIXER, MODE_RECORDER, MODE_SEQUENCER]


class SessionManager:
    """Manages play session timing and limits.

    Pure logic — inject get_time (returns epoch seconds) and
    get_date (returns "YYYY-MM-DD" string) for testability.
    Optional on_session_end callback receives a session record dict.
    """

    def __init__(self, settings, get_time, get_date, on_session_end=None):
        self.settings = settings
        self._get_time = get_time
        self._get_date = get_date
        self._on_session_end = on_session_end
        self.state = IDLE
        self._session_start = 0
        self._sleep_start = 0
        self._sessions_today = 0
        self._today = ""
        self._mode = MODE_FREE_PLAY
        self._end_reason = ""

    @property
    def mode(self):
        return self._mode

    def set_mode(self, mode):
        """Set the current play mode. Affects per-mode time limits."""
        self._mode = mode

    def _session_limit_s(self):
        """Return session limit in seconds for the current mode."""
        mode_limits = self.settings.get("mode_limits", {})
        mode_limit = mode_limits.get(self._mode)
        if mode_limit is not None:
            if mode_limit == 0:
                return 0  # unlimited
            return mode_limit * 60
        return self.settings["max_session_min"] * 60

    @property
    def time_remaining_s(self):
        """Seconds remaining in current session, or 0 if not playing."""
        if not self.settings.get("sessions_enabled", True):
            return 9999  # unlimited
        if self.state not in (PLAYING, WARN_5, WARN_2):
            return 0
        limit = self._session_limit_s()
        if limit == 0:
            return 9999  # unlimited — always plenty of time
        elapsed = self._get_time() - self._session_start
        return max(0, limit - elapsed)

    @property
    def sessions_today(self):
        return self._sessions_today

    @property
    def sessions_remaining(self):
        return max(0, self.settings["max_sessions_day"] - self._sessions_today)

    def _reset_day_if_needed(self):
        today = self._get_date()
        if today != self._today:
            self._today = today
            self._sessions_today = 0

    def _in_quiet_hours(self):
        qs = self.settings.get("quiet_start")
        qe = self.settings.get("quiet_end")
        if qs is None or qe is None:
            return False
        now_s = self._get_time()
        h = (now_s % 86400) // 3600
        m = (now_s % 3600) // 60
        now_hm = "{:02d}:{:02d}".format(h, m)
        if qs <= qe:
            return qs <= now_hm < qe
        else:
            return now_hm >= qs or now_hm < qe

    def _record_session(self, reason):
        """Record a completed session via the callback."""
        self._sessions_today += 1
        if self._on_session_end:
            now = self._get_time()
            duration_s = now - self._session_start
            # Format start time as HH:MM
            start_h = (self._session_start % 86400) // 3600
            start_m = (self._session_start % 3600) // 60
            record = {
                "date": self._get_date(),
                "start_time": "{:02d}:{:02d}".format(start_h, start_m),
                "duration_s": duration_s,
                "duration_min": round(duration_s / 60, 1),
                "mode": self._mode,
                "end_reason": reason,
            }
            self._on_session_end(record)

    def tick(self):
        """Call every frame. Returns current state string."""
        self._reset_day_if_needed()

        # Session controls disabled — stay in PLAYING, skip all limits
        if not self.settings.get("sessions_enabled", True):
            if self.state != PLAYING:
                self.state = PLAYING
                self._session_start = self._get_time()
            return self.state

        # Lockdown overrides everything
        if self.settings.get("lockdown"):
            self.state = LOCKDOWN
            return self.state

        # If we were in lockdown but it was cleared, go idle
        if self.state == LOCKDOWN:
            self.state = IDLE
            return self.state

        # Quiet hours check
        if self._in_quiet_hours() and self.state in (IDLE, PLAYING, WARN_5, WARN_2):
            self.state = SLEEPING
            self._sleep_start = self._get_time()
            return self.state

        now = self._get_time()

        if self.state == IDLE:
            pass  # waiting for try_wake()

        elif self.state == PLAYING:
            remaining = self.time_remaining_s
            if remaining <= 0:
                self.state = WINDDOWN
                self._sleep_start = now
            elif remaining <= 120:
                self.state = WARN_2
            elif remaining <= 300:
                self.state = WARN_5

        elif self.state == WARN_5:
            remaining = self.time_remaining_s
            if remaining <= 0:
                self.state = WINDDOWN
                self._sleep_start = now
            elif remaining <= 120:
                self.state = WARN_2

        elif self.state == WARN_2:
            remaining = self.time_remaining_s
            if remaining <= 0:
                self.state = WINDDOWN
                self._sleep_start = now

        elif self.state == WINDDOWN:
            if now - self._sleep_start >= 30:
                self.state = SLEEPING
                self._sleep_start = now
                self._record_session("normal")

        elif self.state == SLEEPING:
            self.state = COOLDOWN
            self._sleep_start = now

        elif self.state == COOLDOWN:
            break_s = self.settings["break_min"] * 60
            if now - self._sleep_start >= break_s:
                self.state = IDLE

        return self.state

    def try_wake(self, mode=None):
        """Attempt to start a new session. Returns True if allowed."""
        # Session controls disabled — always allow
        if not self.settings.get("sessions_enabled", True):
            self.state = PLAYING
            self._session_start = self._get_time()
            self._mode = mode or MODE_FREE_PLAY
            return True

        self._reset_day_if_needed()

        if self.settings.get("lockdown"):
            return False

        if self._in_quiet_hours():
            return False

        if self.state not in (IDLE,):
            return False

        if self._sessions_today >= self.settings["max_sessions_day"]:
            return False

        self.state = PLAYING
        self._session_start = self._get_time()
        self._mode = mode or MODE_FREE_PLAY
        return True

    def force_sleep(self):
        """Immediately end current session (for lockdown toggle)."""
        if self.state in (PLAYING, WARN_5, WARN_2):
            self._record_session("force_sleep")
        self.state = SLEEPING
        self._sleep_start = self._get_time()
