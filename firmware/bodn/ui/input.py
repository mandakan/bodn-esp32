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
        self.enc_btn_held = [False] * n_enc
        self.enc_btn_pressed = [False] * n_enc

        self._prev_btn = [False] * n_btn
        self._prev_enc_pos = [0] * n_enc
        self._prev_enc_btn = [False] * n_enc

    def scan(self):
        """Read all inputs. Call once per frame."""
        now = self._time_ms()

        # Cache self.* as locals to avoid repeated dict lookups
        buttons = self._buttons
        btn_deb = self._btn_deb
        btn_held = self.btn_held
        btn_just_pressed = self.btn_just_pressed
        btn_just_released = self.btn_just_released
        prev_btn = self._prev_btn

        # Buttons
        for i, btn in enumerate(buttons):
            prev = prev_btn[i]
            cur = btn_deb[i].update(btn.value(), now)
            btn_held[i] = cur
            btn_just_pressed[i] = cur and not prev
            btn_just_released[i] = not cur and prev
            prev_btn[i] = cur

        # Toggle switches (no debounce — physical latching)
        sw = self.sw
        for i, switch in enumerate(self._switches):
            sw[i] = switch.value() == 0

        # Encoders
        encoders = self._encoders
        enc_pos = self.enc_pos
        enc_delta = self.enc_delta
        prev_enc_pos = self._prev_enc_pos
        enc_btn_held = self.enc_btn_held
        enc_btn_pressed = self.enc_btn_pressed
        prev_enc_btn = self._prev_enc_btn
        enc_btn_deb = self._enc_btn_deb

        for i, enc in enumerate(encoders):
            pos = enc.value
            enc_pos[i] = pos
            enc_delta[i] = pos - prev_enc_pos[i]
            prev_enc_pos[i] = pos

            p_btn = prev_enc_btn[i]
            cur_btn = enc_btn_deb[i].update(enc.sw.value(), now)
            enc_btn_held[i] = cur_btn
            enc_btn_pressed[i] = cur_btn and not p_btn
            prev_enc_btn[i] = cur_btn

    def any_btn_pressed(self):
        """Return True if any button was just pressed this frame."""
        return any(self.btn_just_pressed)

    def first_btn_pressed(self):
        """Return index of the first just-pressed button, or -1."""
        for i, p in enumerate(self.btn_just_pressed):
            if p:
                return i
        return -1
