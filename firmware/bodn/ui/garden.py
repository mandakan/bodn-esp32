# bodn/ui/garden.py — Garden of Life game screen (cellular automata for kids)
#
# Tier 1: "Magic Garden" — pure exploration, buttons plant colored flowers.
# Tier 2: "Garden Puzzles" — target shapes (future).
# Tier 3: "Life Lab" — full rule control (future).
#
# Hardware mapping:
#   Buttons 0–7: plant a flower of that color at the cursor position
#                (also plants at the matching garden plot for quick seeding).
#   ENC_A rotation: generation speed (slow ↔ fast).
#   ENC_A button: toggle run/pause.
#   ENC_B rotation: move cursor across the grid.
#   ENC_B button: toggle cell at cursor (plant/remove).
#   Toggle SW0: normal vs. friendly rules.
#   Toggle SW1: wrap-around edges vs. walls.
#   Toggle SW2: show next-gen ghost preview.
#   Toggle SW3: enable undo (rewind one generation).

from micropython import const
from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.input import BrightnessControl, EncoderAccumulator
from bodn.ui.pause import PauseMenu
from bodn.life_rules import (
    GRID_W,
    GRID_H,
    CELL_COLORS,
    GARDEN_PLOTS,
    CONWAY_BIRTH,
    CONWAY_SURVIVE,
    FRIENDLY_BIRTH,
    FRIENDLY_SURVIVE,
    step,
    population,
    is_empty,
    clear,
    place,
    toggle,
)
from bodn.i18n import t
from bodn.patterns import (
    N_LEDS,
    _led_buf,
    scale,
    zone_fill,
    ZONE_STICKS,
    ZONE_LID_RING,
)

import time

NAV = const(0)

# Cell size in pixels on primary display (240×320 landscape → 20px cells)
CELL_PX = const(20)

# Grid offset on screen (centered in 320×240)
GRID_OX = const(0)  # (320 - 16*20) // 2 = 0
GRID_OY = const(0)  # (240 - 12*20) // 2 = 0

# Speed range (ms between generations)
SPEED_MIN_MS = const(300)
SPEED_MAX_MS = const(3000)
SPEED_DEFAULT_MS = const(1000)
SPEED_STEP_MS = const(100)

# Empty garden prompt timing
EMPTY_PROMPT_MS = const(2000)

# Minimum cells before evolution auto-starts
AUTO_START_CELLS = const(3)

# Total grid cells (for cursor wrapping)
_GRID_TOTAL = const(192)  # GRID_W * GRID_H


class GardenScreen(Screen):
    """Garden of Life — cellular automata reimagined as a garden.

    Turn ENC_B to move the cursor, press any colored button to plant.
    Hold nav encoder button to open the pause menu (resume / back to menu).
    """

    def __init__(self, np, overlay, settings=None, secondary_screen=None, on_exit=None):
        self._np = np
        self._overlay = overlay
        self._secondary = secondary_screen
        self._on_exit = on_exit
        self._settings = settings or {}
        self._manager = None
        self._pause = PauseMenu(settings=settings)
        self._brightness = BrightnessControl()

        # Speed control via ENC_A
        self._speed_acc = EncoderAccumulator(
            detents_per_unit=2, fast_threshold=400, fast_multiplier=3
        )
        self._speed_ms = SPEED_DEFAULT_MS

        # Cursor control via ENC_B — higher dpu filters encoder jitter,
        # high fast_multiplier lets fast spins scan the grid quickly
        self._cursor_acc = EncoderAccumulator(
            detents_per_unit=3, fast_threshold=300, fast_multiplier=5
        )
        self._cursor_pos = 0  # flat index 0..(GRID_W*GRID_H-1)
        self._cursor_color = 1  # last-used color index (1-indexed)
        self._prev_cursor_pos = -1  # last rendered cursor position (for erase)

        # Grid state
        self._grid = clear(GRID_W, GRID_H)
        self._prev_grid = None  # for undo
        self._generation = 0
        self._population = 0
        self._running = False
        self._last_step_ms = 0

        # Render state
        self._dirty = True
        self._dirty_cells = set()  # cells that changed since last render
        self._full_redraw = True
        self._leds_dirty = True
        self._empty_since_ms = 0

        # Rule modifiers (from toggle switches)
        self._friendly = False
        self._wrap = False
        self._ghost = False
        self._undo_enabled = False

    def _cursor_xy(self):
        """Convert flat cursor position to (x, y)."""
        return self._cursor_pos % GRID_W, self._cursor_pos // GRID_W

    def enter(self, manager):
        self._manager = manager
        self._pause.set_manager(manager)
        self._brightness.reset()
        self._speed_acc.reset()
        self._cursor_acc.reset()
        self._cursor_pos = _GRID_TOTAL // 2  # start in center
        self._prev_cursor_pos = -1
        self._dirty = True
        self._full_redraw = True
        self._leds_dirty = True
        self._running = False
        self._last_step_ms = time.ticks_ms()

    def exit(self):
        if self._on_exit:
            self._on_exit()

    def needs_redraw(self):
        return self._dirty or self._pause.needs_render

    def update(self, inp, frame):
        # Pause menu
        result = self._pause.update(inp, frame)
        if result == "quit" and self._manager:
            self._manager.pop()
            return
        elif result == "resume":
            self._dirty = True
            self._full_redraw = True
        if self._pause.is_open or self._pause.is_holding:
            return

        now = time.ticks_ms()

        # Read toggle switches
        prev_mods = (self._friendly, self._wrap, self._ghost, self._undo_enabled)
        self._friendly = inp.sw[0]
        self._wrap = inp.sw[1]
        self._ghost = inp.sw[2]
        self._undo_enabled = len(inp.sw) > 3 and inp.sw[3]
        new_mods = (self._friendly, self._wrap, self._ghost, self._undo_enabled)
        if new_mods != prev_mods:
            self._dirty = True
            self._full_redraw = True

        # Speed control via ENC_A
        speed_units = self._speed_acc.update(
            inp.enc_delta[config.ENC_A], inp.enc_velocity[config.ENC_A]
        )
        if speed_units:
            self._speed_ms = max(
                SPEED_MIN_MS,
                min(SPEED_MAX_MS, self._speed_ms - speed_units * SPEED_STEP_MS),
            )
            self._dirty = True

        # Cursor movement via ENC_B
        cursor_units = self._cursor_acc.update(
            inp.enc_delta[config.ENC_B], inp.enc_velocity[config.ENC_B]
        )
        if cursor_units:
            self._cursor_pos = (self._cursor_pos + cursor_units) % _GRID_TOTAL
            self._dirty = True

        # Brightness via ENC_A button (cycle through levels)
        if inp.enc_btn_pressed[config.ENC_A]:
            bri = self._brightness.value
            if bri < 80:
                self._brightness.reset(value=128)
            elif bri < 200:
                self._brightness.reset(value=255)
            else:
                self._brightness.reset(value=40)
            self._leds_dirty = True

        # Button presses — plant at cursor AND at garden plot
        btn = inp.first_btn_pressed()
        if btn >= 0 and btn < 8:
            color_idx = btn + 1  # 1-indexed color
            self._cursor_color = color_idx

            # Plant at cursor position
            cx, cy = self._cursor_xy()
            place(self._grid, cx, cy, GRID_W, color_idx)
            self._dirty_cells.add((cx, cy))

            # Also plant at the matching garden plot (quick-seed shortcut)
            if btn < len(GARDEN_PLOTS):
                px, py = GARDEN_PLOTS[btn]
                if (px, py) != (cx, cy):
                    place(self._grid, px, py, GRID_W, color_idx)
                    self._dirty_cells.add((px, py))

            self._dirty = True
            self._leds_dirty = True
            self._population = population(self._grid)
            # Reset step timer so child has time to add more
            self._last_step_ms = now
            # Auto-start once enough seeds are planted
            if not self._running and self._population >= AUTO_START_CELLS:
                self._running = True

        # ENC_B button: toggle cell at cursor (plant/remove)
        if inp.enc_btn_pressed[config.ENC_B]:
            if self._undo_enabled and self._prev_grid:
                # Undo mode: rewind one generation
                self._grid = self._prev_grid
                self._prev_grid = None
                self._generation = max(0, self._generation - 1)
                self._population = population(self._grid)
                self._dirty = True
                self._full_redraw = True
                self._leds_dirty = True
            else:
                # Toggle cell at cursor
                cx, cy = self._cursor_xy()
                toggle(self._grid, cx, cy, GRID_W, self._cursor_color)
                self._dirty_cells.add((cx, cy))
                self._dirty = True
                self._leds_dirty = True
                self._population = population(self._grid)
                self._last_step_ms = now
                if not self._running and self._population >= AUTO_START_CELLS:
                    self._running = True

        # Evolution tick
        if self._running and time.ticks_diff(now, self._last_step_ms) >= self._speed_ms:
            self._last_step_ms = now
            self._evolve()

        # Track empty garden for prompt
        if is_empty(self._grid):
            if self._empty_since_ms == 0:
                self._empty_since_ms = now
        else:
            self._empty_since_ms = 0

        # Update LEDs
        if self._leds_dirty:
            self._leds_dirty = False
            self._update_leds(frame)

    def _evolve(self):
        """Run one generation step."""
        birth = FRIENDLY_BIRTH if self._friendly else CONWAY_BIRTH
        survive = FRIENDLY_SURVIVE if self._friendly else CONWAY_SURVIVE

        if self._undo_enabled:
            self._prev_grid = bytearray(self._grid)

        new_grid, births, deaths = step(
            self._grid, GRID_W, GRID_H, birth, survive, self._wrap
        )

        if births or deaths:
            self._grid = new_grid
            self._generation += 1
            self._population = population(self._grid)
            for cell in births:
                self._dirty_cells.add(cell)
            for cell in deaths:
                self._dirty_cells.add(cell)
            self._dirty = True
            self._leds_dirty = True

            # Update secondary display
            if self._secondary:
                self._secondary.set_population(self._population, self._generation)
        elif is_empty(self._grid):
            self._running = False
            self._generation = 0
            self._dirty = True
            self._full_redraw = True

    def _update_leds(self, frame):
        """Update NeoPixel LEDs to reflect garden state."""
        brightness = self._brightness.value
        lid_bright = min(brightness, config.NEOPIXEL_LID_BRIGHTNESS)
        pop = self._population
        total = GRID_W * GRID_H

        # Sticks: heartbeat pulse synced to generation tick
        if self._running and pop > 0:
            pulse_color = (0, 200, 100)
            phase = (frame * 3) & 0xFF
            v = phase if phase < 128 else 255 - phase
            v = (v * brightness) >> 7
            c = scale(pulse_color, v)
            buf = _led_buf
            for i in range(16):
                buf[i] = c
        else:
            zone_fill(ZONE_STICKS, (30, 10, 40), brightness // 4)

        # Lid ring: density mapped to lit LEDs
        if pop > 0:
            lit = max(1, pop * 92 // total)
            dom_color = self._dominant_grid_color()
            c = scale(dom_color, lid_bright)
            dim = scale(dom_color, lid_bright // 6)
            buf = _led_buf
            for i in range(92):
                buf[16 + i] = c if i < lit else dim
        else:
            zone_fill(ZONE_LID_RING, (10, 5, 20), lid_bright // 3)

        ses_state = self._overlay.session_mgr.state
        leds = self._overlay.static_led_override(ses_state, _led_buf, brightness)

        np = self._np
        for i in range(N_LEDS):
            np[i] = leds[i]
        np.write()

    def _dominant_grid_color(self):
        """Find the most common cell color in the grid."""
        counts = [0] * 9  # index 0 unused, 1–8 for colors
        for c in self._grid:
            if c:
                counts[c] += 1
        best = 1
        for i in range(1, 9):
            if counts[i] > counts[best]:
                best = i
        if best - 1 < len(CELL_COLORS):
            return CELL_COLORS[best - 1]
        return (0, 200, 100)

    def render(self, tft, theme, frame):
        if self._pause.is_open:
            if self._dirty:
                self._dirty = False
                self._render_grid(tft, theme, frame, full=True)
            self._pause.render(tft, theme, frame)
            return

        if self._dirty:
            self._dirty = False
            full = self._full_redraw
            self._full_redraw = False
            self._render_grid(tft, theme, frame, full=full)

        self._pause.render(tft, theme, frame)

    def _render_grid(self, tft, theme, frame, full=False):
        """Draw the garden grid on the primary display."""
        w = theme.width
        h = theme.height

        if full:
            tft.fill(theme.BLACK)
            # Draw grid lines
            for x in range(GRID_W + 1):
                px = GRID_OX + x * CELL_PX
                if px < w:
                    tft.vline(px, GRID_OY, GRID_H * CELL_PX, theme.MUTED)
            for y in range(GRID_H + 1):
                py = GRID_OY + y * CELL_PX
                if py < h:
                    tft.hline(GRID_OX, py, GRID_W * CELL_PX, theme.MUTED)
            # Draw all cells
            self._draw_all_cells(tft, theme)
            self._dirty_cells.clear()
            self._prev_cursor_pos = -1  # force cursor draw
        else:
            # Erase old cursor first (redraw that cell cleanly)
            if self._prev_cursor_pos >= 0 and self._prev_cursor_pos != self._cursor_pos:
                ox = self._prev_cursor_pos % GRID_W
                oy = self._prev_cursor_pos // GRID_W
                self._draw_cell(tft, theme, ox, oy)
                self._redraw_grid_lines(tft, theme, ox, oy)

            # Redraw changed cells
            for cx, cy in self._dirty_cells:
                self._draw_cell(tft, theme, cx, cy)
            self._dirty_cells.clear()

        # Ghost preview (next generation state shown faintly)
        if self._ghost and self._running:
            self._draw_ghost(tft, theme)

        # Garden plots (tier 1) — show highlighted spots when few cells planted
        if self._population < AUTO_START_CELLS:
            for i, (px, py) in enumerate(GARDEN_PLOTS):
                if not self._grid[py * GRID_W + px]:
                    sx = GRID_OX + px * CELL_PX + 2
                    sy = GRID_OY + py * CELL_PX + 2
                    r, g, b = CELL_COLORS[i]
                    c565 = tft.rgb(r, g, b)
                    tft.rect(sx, sy, CELL_PX - 4, CELL_PX - 4, c565)

        # Cursor — bright outline on the current cell
        self._draw_cursor(tft, theme, frame)
        self._prev_cursor_pos = self._cursor_pos

        # HUD: generation counter, population, speed
        hud_y = h - 14
        tft.fill_rect(0, hud_y, w, 14, theme.BLACK)
        gen_text = "G:{}".format(self._generation)
        pop_text = "P:{}".format(self._population)
        speed_text = "{:.1f}s".format(self._speed_ms / 1000)
        tft.text(gen_text, 4, hud_y + 2, theme.MUTED)
        tft.text(pop_text, 80, hud_y + 2, theme.MUTED)

        # Running/paused indicator
        if self._running:
            tft.text(">", 160, hud_y + 2, theme.GREEN)
        elif self._population > 0 and self._population < AUTO_START_CELLS:
            dots = "." * self._population
            tft.text(dots, 160, hud_y + 2, theme.CYAN)
        else:
            tft.text("||", 160, hud_y + 2, theme.YELLOW)

        tft.text(speed_text, w - len(speed_text) * 8 - 4, hud_y + 2, theme.MUTED)

        # Modifier dots
        mods = [
            (self._friendly, theme.GREEN),
            (self._wrap, theme.CYAN),
            (self._ghost, theme.YELLOW),
            (self._undo_enabled, theme.MAGENTA),
        ]
        dx = 200
        for active, color in mods:
            if active:
                tft.fill_rect(dx, hud_y + 4, 6, 6, color)
            else:
                tft.rect(dx, hud_y + 4, 6, 6, theme.MUTED)
            dx += 10

        # Empty garden prompt
        if is_empty(self._grid):
            now = time.ticks_ms()
            if (
                self._empty_since_ms
                and time.ticks_diff(now, self._empty_since_ms) > EMPTY_PROMPT_MS
            ):
                from bodn.ui.widgets import draw_centered

                draw_centered(
                    tft, t("garden_plant"), h // 2 - 20, theme.CYAN, w, scale=2
                )

    def _draw_cursor(self, tft, theme, frame):
        """Draw a bright outline at the cursor position."""
        cx, cy = self._cursor_xy()
        sx = GRID_OX + cx * CELL_PX
        sy = GRID_OY + cy * CELL_PX

        # Cursor color matches the current plant color (bright + white)
        idx = min(self._cursor_color - 1, len(CELL_COLORS) - 1)
        r, g, b = CELL_COLORS[idx]
        c565 = tft.rgb(r, g, b)

        # Thick outline (2px) for visibility — drawn just inside grid lines
        tft.rect(sx + 1, sy + 1, CELL_PX - 1, CELL_PX - 1, c565)
        tft.rect(sx + 2, sy + 2, CELL_PX - 3, CELL_PX - 3, theme.WHITE)

    def _redraw_grid_lines(self, tft, theme, cx, cy):
        """Restore grid lines around cell (cx, cy) after cursor erase."""
        sx = GRID_OX + cx * CELL_PX
        sy = GRID_OY + cy * CELL_PX
        # Left and top edges of this cell
        tft.vline(sx, sy, CELL_PX + 1, theme.MUTED)
        tft.hline(sx, sy, CELL_PX + 1, theme.MUTED)
        # Right and bottom edges (shared with next cell)
        rx = sx + CELL_PX
        by = sy + CELL_PX
        if rx <= GRID_OX + GRID_W * CELL_PX:
            tft.vline(rx, sy, CELL_PX + 1, theme.MUTED)
        if by <= GRID_OY + GRID_H * CELL_PX:
            tft.hline(sx, by, CELL_PX + 1, theme.MUTED)

    def _draw_all_cells(self, tft, theme):
        """Draw every cell in the grid."""
        for y in range(GRID_H):
            row = y * GRID_W
            for x in range(GRID_W):
                c = self._grid[row + x]
                if c:
                    self._draw_alive_cell(tft, x, y, c)

    def _draw_cell(self, tft, theme, cx, cy):
        """Draw a single cell (alive or dead)."""
        sx = GRID_OX + cx * CELL_PX + 1
        sy = GRID_OY + cy * CELL_PX + 1
        cell_inner = CELL_PX - 1
        c = self._grid[cy * GRID_W + cx]
        if c:
            self._draw_alive_cell(tft, cx, cy, c)
        else:
            # Clear cell to black (with grid line preserved)
            tft.fill_rect(sx, sy, cell_inner, cell_inner, theme.BLACK)

    def _draw_alive_cell(self, tft, cx, cy, color_idx):
        """Draw a chunky flower icon for an alive cell."""
        sx = GRID_OX + cx * CELL_PX + 1
        sy = GRID_OY + cy * CELL_PX + 1
        inner = CELL_PX - 1

        # Get color from index (1-indexed)
        idx = min(color_idx - 1, len(CELL_COLORS) - 1)
        r, g, b = CELL_COLORS[idx]
        c565 = tft.rgb(r, g, b)

        # Chunky flower: filled square with darker border
        tft.fill_rect(sx + 2, sy + 2, inner - 4, inner - 4, c565)
        # Center dot (bright)
        tft.fill_rect(
            sx + inner // 2 - 2, sy + inner // 2 - 2, 4, 4, tft.rgb(255, 255, 255)
        )

    def _draw_ghost(self, tft, theme):
        """Draw faint outlines where cells will appear/disappear next generation."""
        birth = FRIENDLY_BIRTH if self._friendly else CONWAY_BIRTH
        survive = FRIENDLY_SURVIVE if self._friendly else CONWAY_SURVIVE
        _, births, deaths = step(self._grid, GRID_W, GRID_H, birth, survive, self._wrap)
        ghost_color = tft.rgb(40, 60, 40)
        death_color = tft.rgb(60, 20, 20)
        for x, y in births:
            sx = GRID_OX + x * CELL_PX + 4
            sy = GRID_OY + y * CELL_PX + 4
            tft.rect(sx, sy, CELL_PX - 8, CELL_PX - 8, ghost_color)
        for x, y in deaths:
            sx = GRID_OX + x * CELL_PX + 6
            sy = GRID_OY + y * CELL_PX + 6
            tft.fill_rect(sx, sy, 3, 3, death_color)
