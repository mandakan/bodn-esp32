# bodn/ui/input.py — unified input state with debouncing

from bodn.debounce import Debouncer


class InputState:
    """Wraps buttons, switches and encoders into a single scannable state.

    Args:
        buttons: list of 8 Pin objects (active-low).
        switches: list of 4 Pin objects (latching toggles, active-low).
        encoders: list of 3 Encoder objects (each has .value, .sw).
        time_ms_fn: callable returning current time in ms.
    """

    def __init__(self, buttons, switches, encoders, time_ms_fn):
        self._buttons = buttons
        self._switches = switches
        self._encoders = encoders
        self._time_ms = time_ms_fn

        self._btn_deb = [Debouncer(delay_ms=30) for _ in range(len(buttons))]
        self._enc_btn_deb = [Debouncer(delay_ms=30) for _ in range(len(encoders))]

        n_btn = len(buttons)
        n_enc = len(encoders)

        # Public state (updated by scan)
        self.btn_held = [False] * n_btn
        self.btn_just_pressed = [False] * n_btn
        self.btn_just_released = [False] * n_btn
        self.sw = [False] * len(switches)
        self.enc_pos = [0] * n_enc
        self.enc_delta = [0] * n_enc
        self.enc_btn_pressed = [False] * n_enc

        self._prev_btn = [False] * n_btn
        self._prev_enc_pos = [0] * n_enc
        self._prev_enc_btn = [False] * n_enc

    def scan(self):
        """Read all inputs. Call once per frame."""
        now = self._time_ms()

        # Buttons
        for i, btn in enumerate(self._buttons):
            prev = self._prev_btn[i]
            cur = self._btn_deb[i].update(btn.value(), now)
            self.btn_held[i] = cur
            self.btn_just_pressed[i] = cur and not prev
            self.btn_just_released[i] = not cur and prev
            self._prev_btn[i] = cur

        # Toggle switches (no debounce — physical latching)
        for i, sw in enumerate(self._switches):
            self.sw[i] = sw.value() == 0

        # Encoders
        for i, enc in enumerate(self._encoders):
            pos = enc.value
            self.enc_pos[i] = pos
            self.enc_delta[i] = pos - self._prev_enc_pos[i]
            self._prev_enc_pos[i] = pos

            prev_btn = self._prev_enc_btn[i]
            cur_btn = self._enc_btn_deb[i].update(enc.sw.value(), now)
            self.enc_btn_pressed[i] = cur_btn and not prev_btn
            self._prev_enc_btn[i] = cur_btn

    def any_btn_pressed(self):
        """Return True if any button was just pressed this frame."""
        return any(self.btn_just_pressed)

    def first_btn_pressed(self):
        """Return index of the first just-pressed button, or -1."""
        for i, p in enumerate(self.btn_just_pressed):
            if p:
                return i
        return -1
