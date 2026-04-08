# bodn/ui/soundboard.py — Soundboard mode screen
#
# 8 mini buttons trigger sounds in the current bank.
# 5 illuminated arcade buttons trigger shared sounds (across banks).
# 2 toggle switches select the bank (bank 0–3).
# ENC_A (right) adjusts volume; click toggles mute.
# NAV (left) hold = pause menu (hold-to-open, same as other game modes).

from micropython import const
from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.widgets import draw_centered, draw_progress_bar
from bodn.ui.pause import PauseMenu
from bodn.i18n import t
from bodn.soundboard_rules import (
    SoundboardState,
    bank_from_toggles,
    NUM_MINI_BUTTONS,
    NUM_ARCADE_BUTTONS,
)
from bodn.patterns import (
    N_LEDS,
    ZONE_STICK_B,
    ZONE_LID_RING,
    zone_fill,
    zone_pulse,
    zone_clear,
    scale as led_scale,
)

NAV = const(0)  # config.ENC_NAV
ENC_A = const(1)  # config.ENC_A

# Flash duration for button-press feedback (frames at ~33 fps)
_FLASH_FRAMES = const(10)

# Auto-color cycle for anonymous slots (one color per button index)
_SLOT_COLORS_RGB = [
    (255, 80, 80),  # 0 — coral red
    (80, 255, 80),  # 1 — lime
    (80, 140, 255),  # 2 — sky blue
    (255, 230, 60),  # 3 — yellow
    (0, 220, 220),  # 4 — cyan
    (230, 80, 230),  # 5 — magenta
    (255, 150, 40),  # 6 — orange
    (160, 80, 255),  # 7 — violet
]

# Arc colors (for the 5 arcade buttons)
_ARC_COLORS_RGB = [
    (60, 220, 60),  # green (far left)
    (60, 100, 255),  # blue
    (255, 255, 255),  # white (centre)
    (255, 220, 60),  # yellow
    (255, 60, 60),  # red (far right)
]


def _rgb_to_565(rgb_fn, r, g, b):
    return rgb_fn(r, g, b)


class SoundboardScreen(Screen):
    """Soundboard — press buttons to play sounds.

    Primary display: 2×4 grid of mini-button slots + 5 arcade slots + volume bar.
    Secondary display: bank name and volume indicator.
    """

    def __init__(
        self,
        np,
        overlay,
        audio,
        arcade=None,
        settings=None,
        secondary_screen=None,
        on_exit=None,
        on_progress=None,
    ):
        self._np = np
        self._overlay = overlay
        self._arcade = arcade
        self._audio = audio
        self._secondary = secondary_screen
        self._on_exit = on_exit
        self._settings = settings
        self._on_progress = on_progress
        self._state = SoundboardState()
        self._manager = None
        self._pause = PauseMenu(settings=settings)

        # Flash state: (slot_type, slot_idx, flash_end_frame)
        # slot_type: 'mini' or 'arc'
        self._flash = None
        self._prev_flash = None  # previous flash for partial clear

        self._dirty = True
        self._full_clear = True
        self._slots_dirty = False  # only affected slots need redraw
        self._vol_dirty = False  # only volume bar needs redraw
        self._leds_dirty = True
        self._prev_bank = -1
        self._prev_volume = -1
        self._prev_muted = None

    def enter(self, manager):
        self._manager = manager
        self._pause.set_manager(manager)
        # Read toggle switches before loading so we start on the correct
        # bank instead of defaulting to 0 and then immediately switching.
        sw = manager.inp.sw
        self._state.bank = bank_from_toggles(
            sw[0] if len(sw) > 0 else False,
            sw[1] if len(sw) > 1 else False,
        )
        self._state.load(on_progress=self._on_progress)
        # Initialise volume from settings so it matches the housekeeping loop
        if self._settings:
            self._state.volume = self._settings.get("volume", 50)
        self._dirty = True
        self._full_clear = True
        self._slots_dirty = False
        self._vol_dirty = False
        self._leds_dirty = True
        self._prev_bank = -1
        self._prev_volume = -1
        self._prev_muted = None
        self._flash = None
        self._prev_flash = None
        # Sounds are preloaded into PSRAM (no file I/O), but keep burst
        # moderate for responsive button handling.
        self._audio.burst = 2

    def exit(self):
        self._audio.burst = 0  # restore auto-scaling
        if self._arcade:
            self._arcade.all_off()
            self._arcade.flush()
        if self._on_exit:
            self._on_exit()

    def on_reveal(self):
        self._dirty = True

    def needs_redraw(self):
        return (
            self._dirty
            or self._slots_dirty
            or self._vol_dirty
            or self._pause.needs_render
        )

    def update(self, inp, frame):
        # Pause menu handles hold-to-open and menu navigation
        result = self._pause.update(inp, frame)
        if result == "quit" and self._manager:
            self._manager.pop()
            return
        elif result == "resume":
            self._dirty = True
            self._full_clear = True
        if self._pause.is_open or self._pause.is_holding:
            return

        state = self._state

        # --- Toggle switches → bank select ---
        new_bank = bank_from_toggles(inp.sw[0], inp.sw[1])
        if new_bank != state.bank:
            state.set_bank(new_bank)
            self._audio.play_sound("select", channel="ui")
            self._dirty = True
            self._full_clear = True
            self._leds_dirty = True

        # --- ENC_A click → mute/unmute ---
        if inp.enc_btn_pressed[ENC_A]:
            state.toggle_mute()
            self._sync_volume(state)
            self._audio.play_sound("nav_click", channel="ui")
            self._vol_dirty = True

        # --- ENC_A turn → volume ---
        delta = inp.enc_delta[ENC_A]
        if delta:
            prev_vol = state.volume
            state.adjust_volume(delta)
            if state.volume != prev_vol:
                self._sync_volume(state)
                self._vol_dirty = True

        # --- Mini button presses ---
        for i in range(NUM_MINI_BUTTONS):
            if inp.btn_just_pressed[i]:
                buf, path = state.press_slot(i)
                if buf:
                    self._audio.play_buffer(buf, channel="sfx")
                elif path:
                    self._audio.play(path, channel="sfx")
                else:
                    self._audio.play_sound("boop", channel="ui")
                self._prev_flash = self._flash
                self._flash = ("mini", i, frame + _FLASH_FRAMES)
                self._slots_dirty = True
                self._leds_dirty = True

        # --- Arcade button presses ---
        for i in range(NUM_ARCADE_BUTTONS):
            if inp.arc_just_pressed[i]:
                buf, path = state.press_arcade(i)
                if buf:
                    self._audio.play_buffer(buf, channel="sfx")
                elif path:
                    self._audio.play(path, channel="sfx")
                else:
                    self._audio.play_sound("boop", channel="ui")
                self._prev_flash = self._flash
                self._flash = ("arc", i, frame + _FLASH_FRAMES)
                self._slots_dirty = True
                self._leds_dirty = True

        # --- Check if audio finished ---
        if self._audio.sfx_active == 0:
            if state.playing_slots or state.playing_arcades:
                state.on_playback_done()
                self._slots_dirty = True
                self._leds_dirty = True

        # --- Expire flash ---
        if self._flash and frame >= self._flash[2]:
            self._prev_flash = self._flash
            self._flash = None
            self._slots_dirty = True
            self._leds_dirty = True

        # --- Update LEDs ---
        if self._leds_dirty:
            self._leds_dirty = False
            self._update_leds(frame)

        # --- Update secondary display ---
        if self._secondary:
            playing = bool(state.playing_slots or state.playing_arcades)
            bank_name = self._resolve_bank_name(state)
            self._secondary.update(bank_name, state.volume, state.muted, playing)

    def _sync_volume(self, state):
        """Apply volume to audio engine and write back to settings."""
        vol = state.effective_volume()
        self._audio.volume = vol
        if self._settings is not None:
            self._settings["volume"] = state.volume

    def _resolve_bank_name(self, state):
        """Return display name for current bank (manifest or i18n fallback)."""
        name = state.bank_name()
        # If still a key (starts with sb_bank_), look it up via i18n
        if name.startswith("sb_bank_"):
            return t(name)
        return name

    def _update_leds(self, frame):
        from bodn.patterns import _led_buf as leds

        state = self._state
        np = self._np
        bank_color = state.bank_color()
        brightness = config.NEOPIXEL_BRIGHTNESS
        lid_bright = config.NEOPIXEL_LID_BRIGHTNESS
        playing_any = bool(state.playing_slots or state.playing_arcades)

        # Stick A: one LED per mini button (indices 0–7)
        for i in range(8):
            if self._flash and self._flash[0] == "mini" and self._flash[1] == i:
                leds[i] = led_scale(_SLOT_COLORS_RGB[i], brightness)
            elif i in state.playing_slots:
                phase = (frame * 4) & 0xFF
                v = phase if phase < 128 else 255 - phase
                v = (v * brightness) >> 8
                leds[i] = led_scale(_SLOT_COLORS_RGB[i], max(v, 30))
            elif state.slots_present[i]:
                leds[i] = led_scale(_SLOT_COLORS_RGB[i], brightness >> 2)
            else:
                leds[i] = led_scale(bank_color, brightness >> 5)

        # Stick B: ambient pulse in bank color during playback
        if playing_any:
            zone_pulse(ZONE_STICK_B, frame, 2, bank_color, brightness)
        else:
            zone_fill(ZONE_STICK_B, bank_color, brightness >> 4)

        # Lid ring
        if playing_any:
            zone_pulse(ZONE_LID_RING, frame, 1, bank_color, lid_bright)
        else:
            zone_clear(ZONE_LID_RING)

        # Session overlay
        ses_state = self._overlay.session_mgr.state
        leds_list = leds  # _led_buf is a list, compatible with static_led_override
        leds_list = self._overlay.static_led_override(ses_state, leds_list, brightness)

        for i in range(N_LEDS):
            np[i] = leds_list[i]
        np.write()

        # Arcade button LEDs via PCA9685
        arc = self._arcade
        if arc:
            for i in range(NUM_ARCADE_BUTTONS):
                if self._flash and self._flash[0] == "arc" and self._flash[1] == i:
                    arc.on(i)
                elif i in state.playing_arcades:
                    arc.pulse(i, frame, speed=4)
                elif state.arcade_present[i]:
                    arc.glow(i)
                else:
                    arc.off(i)
            arc.flush()

    def render(self, tft, theme, frame):
        if self._pause.is_open:
            if self._dirty:
                self._dirty = False
                self._slots_dirty = False
                self._vol_dirty = False
                tft.fill(theme.BLACK)
                self._full_clear = False
                self._render_content(tft, theme, frame)
            self._pause.render(tft, theme, frame)
            return

        if self._dirty:
            # Full redraw (bank change, initial draw, resume)
            self._dirty = False
            self._slots_dirty = False
            self._vol_dirty = False
            if self._full_clear:
                self._full_clear = False
                tft.fill(theme.BLACK)
            self._render_content(tft, theme, frame)
        else:
            # Partial updates — much cheaper
            if self._slots_dirty:
                self._slots_dirty = False
                self._render_changed_slots(tft, theme, frame)
            if self._vol_dirty:
                self._vol_dirty = False
                self._render_volume_bar(tft, theme)

        self._pause.render(tft, theme, frame)

    def _grid_geometry(self, theme):
        """Compute grid layout constants (cached values would be better but
        this is cheap and keeps the code simple)."""
        w = theme.width
        h = theme.height
        cols = 4
        rows = 2
        margin = 4
        grid_top = 24
        cell_w = (w - margin * (cols + 1)) // cols
        cell_h = (h - grid_top - 60) // rows
        arc_top = grid_top + rows * (cell_h + margin) + 4
        arc_cell_w = (w - margin * (NUM_ARCADE_BUTTONS + 1)) // NUM_ARCADE_BUTTONS
        arc_cell_h = h - arc_top - 20
        return margin, grid_top, cell_w, cell_h, arc_top, arc_cell_w, arc_cell_h

    def _slot_xy(self, idx, margin, grid_top, cell_w, cell_h):
        """Return (x, y) for mini-button slot idx."""
        col = idx % 4
        row = idx // 4
        return margin + col * (cell_w + margin), grid_top + row * (cell_h + margin)

    def _render_changed_slots(self, tft, theme, frame):
        """Redraw only the slots that changed (flash on/off, playback done)."""
        state = self._state
        rgb = tft.rgb
        margin, grid_top, cell_w, cell_h, arc_top, arc_cell_w, arc_cell_h = (
            self._grid_geometry(theme)
        )

        # Determine which slots need redraw from flash transitions
        to_redraw_mini = set()
        to_redraw_arc = set()

        # Previous flash slot needs clearing
        pf = self._prev_flash
        if pf:
            if pf[0] == "mini":
                to_redraw_mini.add(pf[1])
            else:
                to_redraw_arc.add(pf[1])
            self._prev_flash = None

        # Current flash slot needs drawing
        cf = self._flash
        if cf:
            if cf[0] == "mini":
                to_redraw_mini.add(cf[1])
            else:
                to_redraw_arc.add(cf[1])

        # If playback just finished, redraw all previously-playing slots
        if not state.playing_slots and not state.playing_arcades:
            # All slots might need un-highlighting — redraw all present
            for i in range(NUM_MINI_BUTTONS):
                if state.slots_present[i]:
                    to_redraw_mini.add(i)
            for i in range(NUM_ARCADE_BUTTONS):
                if state.arcade_present[i]:
                    to_redraw_arc.add(i)

        for i in to_redraw_mini:
            x, y = self._slot_xy(i, margin, grid_top, cell_w, cell_h)
            self._draw_slot(tft, theme, rgb, state, i, x, y, cell_w, cell_h, frame)

        for i in to_redraw_arc:
            x = margin + i * (arc_cell_w + margin)
            self._draw_arc_slot(
                tft, theme, rgb, state, i, x, arc_top, arc_cell_w, arc_cell_h, frame
            )

    def _render_volume_bar(self, tft, theme):
        """Redraw only the volume bar strip at the bottom."""
        state = self._state
        w = theme.width
        h = theme.height
        vol_y = h - 14
        tft.fill_rect(0, vol_y, w, 14, theme.BLACK)
        if state.muted:
            draw_centered(tft, t("sb_muted"), vol_y, theme.RED, w)
        else:
            vol_label = t("sb_volume", state.volume)
            tft.text(vol_label, 4, vol_y, theme.MUTED)
            bar_x = len(vol_label) * 8 + 8
            draw_progress_bar(
                tft,
                bar_x,
                vol_y + 1,
                w - bar_x - 4,
                6,
                state.volume,
                100,
                theme.CYAN,
                theme.DIM,
                border=theme.DIM,
            )

    def _render_content(self, tft, theme, frame):
        landscape = theme.width > theme.height
        if landscape:
            self._render_landscape(tft, theme, frame)
        else:
            self._render_portrait(tft, theme, frame)

    def _render_landscape(self, tft, theme, frame):
        """Primary display: 320×240 landscape layout."""
        state = self._state
        w = theme.width  # 320
        h = theme.height  # 240
        rgb = tft.rgb

        # --- Header (clear first to avoid text-on-text when bank changes) ---
        tft.fill_rect(0, 0, w, 20, theme.BLACK)
        bank_name = self._resolve_bank_name(state)
        bank_label = t("sb_bank", state.bank + 1)
        draw_centered(tft, bank_name.upper(), 2, theme.CYAN, w, scale=2)
        bank_lbl_x = w - len(bank_label) * 8 - 4
        tft.text(bank_label, bank_lbl_x, 4, theme.MUTED)

        # --- Mini button grid: 2 rows × 4 cols ---
        cols = 4
        rows = 2
        margin = 4
        grid_top = 24
        cell_w = (w - margin * (cols + 1)) // cols  # ~74px
        cell_h = (h - grid_top - 60) // rows  # ~72px with room below

        for i in range(NUM_MINI_BUTTONS):
            col = i % cols
            row = i // cols
            x = margin + col * (cell_w + margin)
            y = grid_top + row * (cell_h + margin)
            self._draw_slot(tft, theme, rgb, state, i, x, y, cell_w, cell_h, frame)

        # --- Arcade button row ---
        arc_top = grid_top + rows * (cell_h + margin) + 4
        arc_cell_w = (
            w - margin * (NUM_ARCADE_BUTTONS + 1)
        ) // NUM_ARCADE_BUTTONS  # ~56px
        arc_cell_h = h - arc_top - 20

        for i in range(NUM_ARCADE_BUTTONS):
            x = margin + i * (arc_cell_w + margin)
            y = arc_top
            self._draw_arc_slot(
                tft, theme, rgb, state, i, x, y, arc_cell_w, arc_cell_h, frame
            )

        # --- Volume bar (clear row to avoid text-on-text) ---
        vol_y = h - 14
        tft.fill_rect(0, vol_y, w, 14, theme.BLACK)
        if state.muted:
            draw_centered(tft, t("sb_muted"), vol_y, theme.RED, w)
        else:
            vol_label = t("sb_volume", state.volume)
            tft.text(vol_label, 4, vol_y, theme.MUTED)
            bar_x = len(vol_label) * 8 + 8
            draw_progress_bar(
                tft,
                bar_x,
                vol_y + 1,
                w - bar_x - 4,
                6,
                state.volume,
                100,
                theme.CYAN,
                theme.DIM,
                border=theme.DIM,
            )

    def _draw_slot(self, tft, theme, rgb, state, idx, x, y, w, h, frame):
        """Draw one mini-button slot square."""
        present = state.slots_present[idx]
        playing = idx in state.playing_slots
        flashing = self._flash and self._flash[0] == "mini" and self._flash[1] == idx

        slot_rgb = _SLOT_COLORS_RGB[idx]
        color_full = rgb(*slot_rgb)

        if flashing or playing:
            # Bright fill
            if playing:
                phase = (frame * 4) & 0xFF
                v = phase if phase < 128 else 255 - phase
                r = (slot_rgb[0] * v) >> 8
                g = (slot_rgb[1] * v) >> 8
                b = (slot_rgb[2] * v) >> 8
                fill_c = rgb(max(r, 60), max(g, 60), max(b, 60))
            else:
                fill_c = color_full
            tft.fill_rect(x, y, w, h, fill_c)
            tft.rect(x, y, w, h, theme.WHITE)
        elif present:
            # Dim colored fill
            r = slot_rgb[0] >> 2
            g = slot_rgb[1] >> 2
            b = slot_rgb[2] >> 2
            tft.fill_rect(x, y, w, h, rgb(r, g, b))
            tft.rect(x, y, w, h, color_full)
        else:
            # Empty — dark outline
            tft.rect(x, y, w, h, theme.DIM)

        # Label — manifest label or fallback
        label = state.slot_label(idx)
        if label is None:
            label = t("sb_sound", idx + 1)
        # Truncate to fit (cell_w / 8 chars)
        max_chars = max(1, (w - 4) // 8)
        if len(label) > max_chars:
            label = label[:max_chars]
        lx = x + (w - len(label) * 8) // 2
        ly = y + h - 10
        if flashing or playing:
            tft.text(label, lx, ly, theme.BLACK)
        elif present:
            tft.text(label, lx, ly, theme.WHITE)
        else:
            tft.text(label, lx, ly, theme.DIM)

    def _draw_arc_slot(self, tft, theme, rgb, state, idx, x, y, w, h, frame):
        """Draw one arcade-button slot square (smaller)."""
        present = state.arcade_present[idx]
        playing = idx in state.playing_arcades
        flashing = self._flash and self._flash[0] == "arc" and self._flash[1] == idx

        arc_rgb = _ARC_COLORS_RGB[idx]
        color_full = rgb(*arc_rgb)

        if flashing or playing:
            tft.fill_rect(x, y, w, h, color_full)
            tft.rect(x, y, w, h, theme.WHITE)
        elif present:
            r = arc_rgb[0] >> 2
            g = arc_rgb[1] >> 2
            b = arc_rgb[2] >> 2
            tft.fill_rect(x, y, w, h, rgb(r, g, b))
            tft.rect(x, y, w, h, color_full)
        else:
            tft.rect(x, y, w, h, theme.DIM)

        # Label: manifest name or fallback "A1"–"A5"
        label = self._state.arcade_label(idx)
        if label is None:
            label = t("sb_extra", idx + 1)
        if len(label) > (w // 8):
            label = label[: w // 8]
        lx = x + (w - len(label) * 8) // 2
        ly = y + (h - 8) // 2
        if flashing or playing:
            tft.text(label, lx, ly, theme.BLACK)
        elif present:
            tft.text(label, lx, ly, theme.WHITE)
        else:
            tft.text(label, lx, ly, theme.DIM)

    def _render_portrait(self, tft, theme, frame):
        """Secondary/portrait layout (128×160) — simplified grid."""
        state = self._state
        w = theme.width  # 128
        h = theme.height  # 160
        rgb = tft.rgb

        # Header (clear first to avoid text-on-text when bank changes)
        tft.fill_rect(0, 0, w, 20, theme.BLACK)
        bank_name = self._resolve_bank_name(state)
        draw_centered(tft, bank_name[:8].upper(), 2, theme.CYAN, w, scale=2)

        # Mini button grid: 4×2
        cell_w = (w - 8) // 4
        cell_h = 28
        top = 22
        for i in range(NUM_MINI_BUTTONS):
            col = i % 4
            row = i // 4
            x = 4 + col * cell_w
            y = top + row * (cell_h + 2)
            self._draw_slot(tft, theme, rgb, state, i, x, y, cell_w - 2, cell_h, frame)

        # Arcade row
        arc_top = top + 2 * (cell_h + 2) + 4
        arc_w = (w - 6) // NUM_ARCADE_BUTTONS
        for i in range(NUM_ARCADE_BUTTONS):
            x = 3 + i * arc_w
            self._draw_arc_slot(
                tft, theme, rgb, state, i, x, arc_top, arc_w - 2, 22, frame
            )

        # Volume (clear row to avoid text-on-text)
        vol_y = h - 14
        tft.fill_rect(0, vol_y, w, 14, theme.BLACK)
        if state.muted:
            draw_centered(tft, t("sb_muted"), vol_y, theme.RED, w)
        else:
            vol_label = t("sb_volume", state.volume)
            draw_centered(tft, vol_label, vol_y, theme.MUTED, w)
