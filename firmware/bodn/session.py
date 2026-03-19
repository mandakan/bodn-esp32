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


class SessionManager:
    """Manages play session timing and limits.

    Pure logic — inject get_time (returns epoch seconds) and
    get_date (returns "YYYY-MM-DD" string) for testability.
    """

    def __init__(self, settings, get_time, get_date):
        self.settings = settings
        self._get_time = get_time
        self._get_date = get_date
        self.state = IDLE
        self._session_start = 0
        self._sleep_start = 0
        self._sessions_today = 0
        self._today = ""

    @property
    def time_remaining_s(self):
        """Seconds remaining in current session, or 0 if not playing."""
        if self.state not in (PLAYING, WARN_5, WARN_2):
            return 0
        elapsed = self._get_time() - self._session_start
        limit = self.settings["max_session_min"] * 60
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
        # quiet_start/end are "HH:MM" strings
        now_s = self._get_time()
        # Extract hour:minute from epoch — caller provides localtime-aware get_time
        h = (now_s % 86400) // 3600
        m = (now_s % 3600) // 60
        now_hm = "{:02d}:{:02d}".format(h, m)
        if qs <= qe:
            return qs <= now_hm < qe
        else:
            # Wraps midnight: e.g. 21:00 → 07:00
            return now_hm >= qs or now_hm < qe

    def tick(self):
        """Call every frame. Returns current state string."""
        self._reset_day_if_needed()

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
            # 30-second wind-down animation, then sleep
            if now - self._sleep_start >= 30:
                self.state = SLEEPING
                self._sleep_start = now
                self._sessions_today += 1

        elif self.state == SLEEPING:
            # Transition to cooldown immediately — sleeping is a brief visual state
            self.state = COOLDOWN
            self._sleep_start = now

        elif self.state == COOLDOWN:
            break_s = self.settings["break_min"] * 60
            if now - self._sleep_start >= break_s:
                self.state = IDLE

        return self.state

    def try_wake(self):
        """Attempt to start a new session. Returns True if allowed."""
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
        return True

    def force_sleep(self):
        """Immediately end current session (for lockdown toggle)."""
        if self.state in (PLAYING, WARN_5, WARN_2):
            self._sessions_today += 1
        self.state = SLEEPING
        self._sleep_start = self._get_time()
