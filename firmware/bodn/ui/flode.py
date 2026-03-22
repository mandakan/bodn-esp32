# bodn/ui/flode.py — Flöde game screen (flow alignment puzzle)

from micropython import const
from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.widgets import draw_centered
from bodn.ui.pause import PauseMenu
from bodn.ui.input import BrightnessControl, EncoderAccumulator
from bodn.i18n import t
from bodn.flode_rules import FlodeEngine, PLAYING, COMPLETE, CELEBRATE
from bodn.patterns import N_LEDS, zone_fill, zone_pulse, zone_clear, ZONE_LID_RING
from bodn.ui.catface import CURIOUS, HAPPY

ENC_A = const(1)  # config.ENC_A — select segment
ENC_B = const(2)  # config.ENC_B — shift segment

# Layout constants
_MARGIN_LEFT = const(20)  # space for source indicator
_MARGIN_RIGHT = const(20)  # space for target indicator
_MARGIN_TOP = const(10)
_MARGIN_BOTTOM = const(10)
_SEG_GAP = const(4)  # pixel gap between segment columns

# Animation
_ANIM_STEPS = const(5)  # frames for snap animation (~150ms at 30ms/tick)

# Easing lookup: ease-out quadratic, scaled to 0..256
# t_i = i / _ANIM_STEPS, eased = 1 - (1 - t_i)^2, scaled to 0..256
_EASE_LUT = (
    0,
    90,  # step 0→1: fast start
    166,  # step 1→2
    224,  # step 2→3
    250,  # step 3→4
    256,  # step 4→5: fully settled
)

# Flow colors (RGB tuples for theme.rgb)
_FLOW_COLOR = (0, 180, 255)  # bright cyan-blue stream
_WALL_COLOR = (60, 60, 80)  # dark blue-grey walls
_WALL_SELECTED = (100, 100, 140)  # lighter when selected
_GAP_COLOR = (20, 20, 30)  # darker gap background
_SOURCE_COLOR = (0, 220, 255)  # source indicator


class FlodeScreen(Screen):
    """Flöde — align gaps to let the flow pass through!

    Encoder A selects segment (left/right, wraps).
    Encoder B shifts the selected segment up/down.
    Hold nav encoder to pause.
    """

    def __init__(
        self,
        np,
        overlay,
        audio=None,
        settings=None,
        secondary_screen=None,
        on_exit=None,
    ):
        self._np = np
        self._overlay = overlay
        self._audio = audio
        self._secondary = secondary_screen
        self._on_exit = on_exit
        self._settings = settings
        self._manager = None
        self._pause = PauseMenu(settings=settings)
        self._dirty = True
        self._leds_dirty = True

        # Game engine — use a simple RNG based on frame counter
        self._seed = 0

        def _rand(n):
            # Simple LCG
            self._seed = (self._seed * 1103515245 + 12345) & 0x7FFFFFFF
            return self._seed % n

        self._engine = FlodeEngine(rand_fn=_rand)

        # Brightness and encoder accumulators
        self._brightness = BrightnessControl()
        self._select_acc = EncoderAccumulator(
            detents_per_unit=2, fast_threshold=300, fast_multiplier=2
        )
        self._shift_acc = EncoderAccumulator(
            detents_per_unit=3, fast_threshold=400, fast_multiplier=2
        )

        # Animation state per segment: (start_y, target_y, step)
        # step >= _ANIM_STEPS means animation done
        self._anim = []

        # Cached layout (computed once per level)
        self._seg_x = []  # x position per segment
        self._seg_w = 0  # width per segment
        self._gap_h = 0  # gap height in pixels
        self._snap_ys = []  # y coordinate per snap position
        self._flow_y = 0  # y center of flow line (target position)
        self._usable_y0 = 0
        self._usable_h = 0

    def enter(self, manager):
        self._manager = manager
        self._pause.set_manager(manager)
        self._brightness.reset()
        # Seed RNG from a somewhat unpredictable source
        import time

        self._seed = time.ticks_ms() & 0x7FFFFFFF
        self._engine.start_level(1)
        self._compute_layout(manager.theme)
        self._init_anim()
        self._dirty = True
        self._leds_dirty = True
        if self._secondary:
            self._secondary.set_emotion(CURIOUS)

    def exit(self):
        # Clear LEDs
        np = self._np
        for i in range(N_LEDS):
            np[i] = (0, 0, 0)
        np.write()
        if self._on_exit:
            self._on_exit()

    def needs_redraw(self):
        return self._dirty or self._pause.needs_render

    def _compute_layout(self, theme):
        """Pre-compute pixel positions for the current level."""
        eng = self._engine
        w = theme.width
        h = theme.height

        usable_w = w - _MARGIN_LEFT - _MARGIN_RIGHT
        n = eng.num_segments
        total_gaps = max(0, n - 1) * _SEG_GAP
        seg_w = (usable_w - total_gaps) // n

        self._seg_w = seg_w
        self._seg_x = []
        for i in range(n):
            self._seg_x.append(_MARGIN_LEFT + i * (seg_w + _SEG_GAP))

        # Vertical layout
        self._usable_y0 = _MARGIN_TOP
        self._usable_h = h - _MARGIN_TOP - _MARGIN_BOTTOM

        # Gap height — generous for few positions, tighter for many
        n_pos = eng.num_positions
        self._gap_h = self._usable_h // (n_pos + 1)

        # Snap positions: center y of gap at each position
        # Evenly distributed within usable area
        gap_h = self._gap_h
        avail = self._usable_h - gap_h
        self._snap_ys = []
        for i in range(n_pos):
            if n_pos > 1:
                cy = self._usable_y0 + gap_h // 2 + i * avail // (n_pos - 1)
            else:
                cy = self._usable_y0 + self._usable_h // 2
            self._snap_ys.append(cy)

        self._flow_y = self._snap_ys[eng.target]

    def _init_anim(self):
        """Initialize animation state — all segments at their positions, no animation."""
        eng = self._engine
        self._anim = []
        for i in range(eng.num_segments):
            y = self._snap_ys[eng.positions[i]]
            self._anim.append([y, y, _ANIM_STEPS])  # [current, target, step]

    def _start_anim(self, seg_idx):
        """Start snap animation for a segment."""
        anim = self._anim[seg_idx]
        # Current visual position (may be mid-animation)
        current_y = self._anim_current_y(seg_idx)
        target_y = self._snap_ys[self._engine.positions[seg_idx]]
        anim[0] = current_y
        anim[1] = target_y
        anim[2] = 0

    def _anim_current_y(self, seg_idx):
        """Get the current visual y center for a segment (with easing)."""
        anim = self._anim[seg_idx]
        step = anim[2]
        if step >= _ANIM_STEPS:
            return anim[1]  # at target
        # Ease-out interpolation
        t_scaled = _EASE_LUT[step]
        start = anim[0]
        end = anim[1]
        return start + (end - start) * t_scaled // 256

    def _tick_anim(self):
        """Advance all animations by one step. Returns True if any active."""
        any_active = False
        for anim in self._anim:
            if anim[2] < _ANIM_STEPS:
                anim[2] += 1
                any_active = True
        return any_active

    def update(self, inp, frame):
        # Pause menu
        result = self._pause.update(inp, frame)
        if result == "quit" and self._manager:
            self._manager.pop()
            return
        elif result == "resume":
            self._dirty = True
        if self._pause.is_open or self._pause.is_holding:
            return

        eng = self._engine

        # Celebration state
        if eng.state == CELEBRATE:
            if eng.update_celebration():
                # Celebration done — advance or restart
                if eng.has_next_level():
                    eng.start_level(eng.level + 1)
                    self._compute_layout(self._manager.theme)
                    self._init_anim()
                    self._select_acc.reset()
                    self._shift_acc.reset()
                    if self._secondary:
                        self._secondary.set_emotion(CURIOUS)
                else:
                    # Max level — restart from 1
                    eng.start_level(1)
                    self._compute_layout(self._manager.theme)
                    self._init_anim()
                    self._select_acc.reset()
                    self._shift_acc.reset()
                self._leds_dirty = True
            self._dirty = True
            return

        # Completion — trigger celebration
        if eng.state == COMPLETE:
            eng.start_celebration()
            self._dirty = True
            self._leds_dirty = True
            if self._secondary:
                self._secondary.set_emotion(HAPPY)
            if self._audio:
                self._audio.tone(880, 200, channel=1)
            return

        # --- PLAYING state ---
        # Select encoder (ENC_A)
        delta_a = inp.enc_delta[ENC_A]
        vel_a = inp.enc_velocity[ENC_A]
        units_a = self._select_acc.update(delta_a, vel_a)
        if units_a != 0:
            if eng.select_delta(units_a):
                self._dirty = True
                if self._audio:
                    self._audio.boop()

        # Shift encoder (ENC_B)
        delta_b = inp.enc_delta[ENC_B]
        vel_b = inp.enc_velocity[ENC_B]
        units_b = self._shift_acc.update(delta_b, vel_b)
        if units_b != 0:
            if eng.shift(units_b):
                self._start_anim(eng.selected)
                self._dirty = True
                self._leds_dirty = True
                if self._audio:
                    self._audio.boop()

        # Tick animations
        if self._tick_anim():
            self._dirty = True

        # Update brightness from encoder A (velocity-aware)
        prev_bri = self._brightness.value
        self._brightness.update(inp.enc_delta[ENC_A], inp.enc_velocity[ENC_A])
        if self._brightness.value != prev_bri:
            self._leds_dirty = True

        # Update LEDs on state change
        if self._leds_dirty:
            self._leds_dirty = False
            self._update_leds(frame)

    def _update_leds(self, frame):
        """Write LED state based on game state."""
        np = self._np
        eng = self._engine
        brightness = self._brightness.value
        lid_bright = min(brightness, config.NEOPIXEL_LID_BRIGHTNESS)

        if eng.state == CELEBRATE:
            zone_pulse(ZONE_LID_RING, frame, 3, (0, 255, 100), lid_bright)
        elif eng.state == PLAYING:
            # Show flow progress on sticks
            reaches = eng.flow_reaches()
            flow_r, flow_g, flow_b = _FLOW_COLOR
            for i in range(16):
                seg_for_led = i * eng.num_segments // 16
                if seg_for_led < reaches:
                    np[i] = (
                        flow_r * brightness // 255,
                        flow_g * brightness // 255,
                        flow_b * brightness // 255,
                    )
                else:
                    np[i] = (0, 0, 0)
            zone_fill(ZONE_LID_RING, _FLOW_COLOR, lid_bright)
        else:
            zone_clear(ZONE_LID_RING)

        ses_state = self._overlay.session_mgr.state
        leds = [(np[i][0], np[i][1], np[i][2]) for i in range(16)]
        leds = list(leds) + [(0, 0, 0)] * (N_LEDS - 16)
        leds = self._overlay.static_led_override(ses_state, leds, brightness)
        for i in range(N_LEDS):
            np[i] = leds[i]
        np.write()

    def render(self, tft, theme, frame):
        if self._pause.is_open:
            if self._dirty:
                self._dirty = False
                tft.fill(theme.BLACK)
                self._render_game(tft, theme, frame)
            self._pause.render(tft, theme, frame)
            return

        if self._dirty:
            self._dirty = False
            tft.fill(theme.BLACK)
            self._render_game(tft, theme, frame)

        self._pause.render(tft, theme, frame)

    def _render_game(self, tft, theme, frame):
        eng = self._engine

        if eng.state == CELEBRATE:
            self._render_celebrate(tft, theme, frame)
            return

        w = theme.width
        rgb = theme.rgb

        wall_c = rgb(*_WALL_COLOR)
        wall_sel_c = rgb(*_WALL_SELECTED)
        flow_c = rgb(*_FLOW_COLOR)
        source_c = rgb(*_SOURCE_COLOR)

        seg_w = self._seg_w
        gap_h = self._gap_h
        flow_y = self._flow_y

        # Draw source indicator (left edge)
        src_h = gap_h
        src_y = flow_y - src_h // 2
        tft.fill_rect(0, src_y, _MARGIN_LEFT - 2, src_h, source_c)

        # Draw target indicator (right edge)
        tgt_x = w - _MARGIN_RIGHT + 2
        tft.fill_rect(tgt_x, src_y, _MARGIN_RIGHT - 2, src_h, source_c)

        # Draw segments
        for i in range(eng.num_segments):
            x = self._seg_x[i]
            gap_cy = self._anim_current_y(i)
            gap_top = gap_cy - gap_h // 2
            gap_bot = gap_top + gap_h
            is_selected = i == eng.selected
            wc = wall_sel_c if is_selected else wall_c

            # Wall above gap
            wall_top = self._usable_y0
            if gap_top > wall_top:
                tft.fill_rect(x, wall_top, seg_w, gap_top - wall_top, wc)

            # Wall below gap
            wall_bot = self._usable_y0 + self._usable_h
            if gap_bot < wall_bot:
                tft.fill_rect(x, gap_bot, seg_w, wall_bot - gap_bot, wc)

            # Selected indicator: thin border on sides
            if is_selected:
                tft.fill_rect(x - 2, wall_top, 2, self._usable_h, theme.CYAN)
                tft.fill_rect(x + seg_w, wall_top, 2, self._usable_h, theme.CYAN)

        # Draw flow — animate from left through aligned gaps
        reaches = eng.flow_reaches()
        flow_h = max(4, gap_h // 3)  # flow is thinner than gap
        fy = flow_y - flow_h // 2

        # Flow from source to first segment
        if reaches > 0:
            fx_start = _MARGIN_LEFT - 2
            fx_end = self._seg_x[0]
            tft.fill_rect(fx_start, fy, fx_end - fx_start, flow_h, flow_c)

        # Flow through aligned segments
        for i in range(reaches):
            x = self._seg_x[i]
            # Flow through gap
            tft.fill_rect(x, fy, seg_w, flow_h, flow_c)
            # Flow between segments (or to target)
            if i < eng.num_segments - 1:
                next_x = self._seg_x[i + 1]
                tft.fill_rect(x + seg_w, fy, next_x - (x + seg_w), flow_h, flow_c)
            else:
                # Flow to target
                tgt_x = w - _MARGIN_RIGHT + 2
                tft.fill_rect(x + seg_w, fy, tgt_x - (x + seg_w), flow_h, flow_c)

        # Level indicator (top-right, small)
        level_str = t("flode_level", eng.level)
        tft.text(level_str, w - len(level_str) * 8 - 4, 2, theme.MUTED)

    def _render_celebrate(self, tft, theme, frame):
        """Celebration screen — big star burst effect."""
        eng = self._engine
        w = theme.width
        h = theme.height
        progress = eng.celebrate_progress

        # Expanding colored bars
        flow_c = theme.rgb(*_FLOW_COLOR)
        n_bars = 6
        for i in range(n_bars):
            bar_h = h // n_bars
            bar_y = i * bar_h
            bar_w = w * min(progress + i * 10, 100) // 100
            bar_x = (w - bar_w) // 2
            tft.fill_rect(bar_x, bar_y, bar_w, bar_h - 2, flow_c)

        # Level complete text
        draw_centered(tft, t("flode_complete"), h // 2 - 20, theme.YELLOW, w, scale=2)
        if eng.has_next_level():
            draw_centered(
                tft,
                t("flode_next", eng.level + 1),
                h // 2 + 16,
                theme.WHITE,
                w,
            )
        else:
            draw_centered(tft, t("flode_all_done"), h // 2 + 16, theme.YELLOW, w)
