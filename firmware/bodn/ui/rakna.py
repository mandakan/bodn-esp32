# bodn/ui/rakna.py — Rakna NFC math game screen
#
# Progressive number sense using NFC dot-pattern cards.
# Level 1: scan any card to discover quantities.
# Level 2: "Find three!" — match the target.
# Level 3: "Find more than 3!" — comparison challenges.
#
# Demo mode: buttons 0-7 simulate card scans (dots_1..dots_8).

import time

from micropython import const
from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.input import BrightnessControl
from bodn.ui.widgets import draw_centered, make_label_sprite, blit_sprite
from bodn.ui.pause import PauseMenu
from bodn.i18n import t
from bodn.rakna_rules import (
    RaknaEngine,
    WELCOME,
    ANNOUNCE,
    WAITING,
    CORRECT,
    WRONG,
    LEVEL_UP,
    DEMO_CARDS,
    CHALLENGE_DISCOVER,
    CHALLENGE_FIND,
    CHALLENGE_MORE,
    CHALLENGE_LESS,
    CHALLENGE_ADD,
    CHALLENGE_SUB,
)
from bodn.patterns import (
    N_LEDS,
    zone_fill,
    zone_pulse,
    zone_clear,
    ZONE_LID_RING,
)
from bodn.neo import neo
from bodn.ui.catface import NEUTRAL, CURIOUS, HAPPY

NAV = const(0)

_STATE_EMOTIONS = {
    WELCOME: NEUTRAL,
    ANNOUNCE: CURIOUS,
    WAITING: CURIOUS,
    CORRECT: HAPPY,
    WRONG: NEUTRAL,
    LEVEL_UP: HAPPY,
}

# Tone feedback
_CORRECT_TONE = 880  # A5
_WRONG_TONE = 220  # A3
_LEVELUP_TONE = 587  # D5

# Dot pattern layouts (1-10): list of (dx, dy) offsets within a cell.
# Based on standard dice patterns for 1-6, structured groups for 7-10.
# Coordinates are in a 5x5 grid (0-4), scaled to actual pixel size at render.
_DOT_PATTERNS = {
    1: [(2, 2)],
    2: [(1, 1), (3, 3)],
    3: [(1, 1), (2, 2), (3, 3)],
    4: [(1, 1), (3, 1), (1, 3), (3, 3)],
    5: [(1, 1), (3, 1), (2, 2), (1, 3), (3, 3)],
    6: [(1, 1), (3, 1), (1, 2), (3, 2), (1, 3), (3, 3)],
    7: [(1, 1), (3, 1), (1, 2), (2, 2), (3, 2), (1, 3), (3, 3)],
    8: [(1, 1), (2, 1), (3, 1), (1, 2), (3, 2), (1, 3), (2, 3), (3, 3)],
    9: [(1, 1), (2, 1), (3, 1), (1, 2), (2, 2), (3, 2), (1, 3), (2, 3), (3, 3)],
    10: [
        (0, 1),
        (1, 1),
        (2, 1),
        (3, 1),
        (4, 1),
        (0, 3),
        (1, 3),
        (2, 3),
        (3, 3),
        (4, 3),
    ],
}

# Number path: 10 positions below the challenge text
_PATH_Y = const(30)
_PATH_R = const(8)  # circle radius
_PATH_SPACING = const(23)  # centre-to-centre


def _filter_by_cache(card_set, cache):
    """Filter card set to only cards with programmed NFC tags.

    If no rakna entries in the cache, returns the full set (demo/first use).
    """
    known_ids = set()
    for entry in cache.entries().values():
        if entry.get("mode") == "rakna":
            known_ids.add(entry["id"])

    if not known_ids:
        return card_set

    cards = [c for c in card_set.get("cards", []) if c["id"] in known_ids]
    if not cards:
        return card_set

    return {"mode": "rakna", "version": card_set.get("version", 1), "cards": cards}


class RaknaScreen(Screen):
    """Rakna — count, find, and compare numbers with NFC dot cards!

    Buttons 0-7 simulate NFC card scans (demo mode).
    Hold nav encoder button to open the pause menu.
    """

    nfc_modes = frozenset({"rakna"})

    def __init__(
        self,
        np,
        overlay,
        arcade=None,
        audio=None,
        settings=None,
        secondary_screen=None,
        on_exit=None,
    ):
        self._np = np
        self._overlay = overlay
        self._arcade = arcade
        self._audio = audio
        self._settings = settings
        self._secondary = secondary_screen
        self._on_exit = on_exit
        self._brightness = BrightnessControl(settings=settings)
        self._manager = None
        self._pause = PauseMenu(settings=settings)
        self._engine = None
        self._prev_state = None
        self._dirty = True
        self._full_clear = True
        self._leds_dirty = True
        self._pending_card_id = None
        self._title_sprite = None

    def on_nfc_tag(self, parsed):
        if parsed["id"] is not None:
            self._pending_card_id = parsed["id"]
            return True
        return False

    def enter(self, manager):
        self._manager = manager
        self._pause.set_manager(manager)
        self._brightness.reset()
        self._last_ms = time.ticks_ms()
        self._dirty = True
        self._full_clear = True

        # Load card set and create engine
        from bodn.nfc import load_card_set, UIDCache

        card_set = load_card_set("rakna")
        if card_set is None:
            # Fallback: minimal card set for demo
            card_set = {
                "mode": "rakna",
                "version": 1,
                "cards": [
                    {"id": c, "quantity": i + 1, "type": "number"}
                    for i, c in enumerate(DEMO_CARDS)
                ],
            }
        else:
            card_set = _filter_by_cache(card_set, UIDCache())

        # Restore persisted level
        level = 1
        if self._settings:
            level = self._settings.get("rakna_level", 1)

        self._engine = RaknaEngine(card_set, level=level)
        self._pending_card_id = None

        if neo.active:
            neo.clear_all_overrides()

        # Pre-render title sprite
        self._title_sprite = make_label_sprite("Rakna", 0xFFFF, scale=2)

        # Engine starts in WELCOME
        self._prev_state = WELCOME
        self._play_audio(None, WELCOME)

    def exit(self):
        # Persist current level
        if self._settings and self._engine:
            self._settings["rakna_level"] = self._engine.level
            try:
                from bodn.storage import save_settings

                save_settings(self._settings)
            except Exception:
                pass
        if neo.active:
            neo.all_off()
            neo.clear_all_overrides()
        if self._arcade:
            self._arcade.all_off()
            self._arcade.flush()
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
            self._full_clear = True
        if self._pause.is_open or self._pause.is_holding:
            return

        # Get card input: NFC scan or demo button press
        card_id = None

        btn = inp.first_btn_pressed()
        if btn >= 0 and btn < len(DEMO_CARDS):
            card_id = DEMO_CARDS[btn]
        arc = inp.first_arc_pressed()
        if arc >= 0 and arc < len(DEMO_CARDS):
            card_id = DEMO_CARDS[arc]

        if self._pending_card_id is not None:
            card_id = self._pending_card_id
            self._pending_card_id = None

        now = time.ticks_ms()
        dt = time.ticks_diff(now, self._last_ms)
        self._last_ms = now
        prev_state = self._engine.state
        self._engine.update(card_id, dt)

        # Detect state changes
        state = self._engine.state
        if state != self._prev_state:
            self._prev_state = state
            self._dirty = True
            self._full_clear = True
            self._leds_dirty = True
            if self._secondary:
                emotion = _STATE_EMOTIONS.get(state, NEUTRAL)
                self._secondary.set_emotion(emotion)
            self._play_audio(prev_state, state)

        if card_id is not None:
            self._dirty = True
            self._leds_dirty = True

        # Brightness control
        prev_bri = self._brightness.value
        self._brightness.update(
            inp.enc_delta[config.ENC_A], inp.enc_velocity[config.ENC_A]
        )
        if self._brightness.value != prev_bri:
            self._leds_dirty = True

        # Write LEDs
        if self._leds_dirty:
            self._leds_dirty = False
            brightness = self._brightness.value
            lid_bright = min(brightness, config.NEOPIXEL_LID_BRIGHTNESS)

            if neo.active:
                # --- C NeoPixel engine path ---
                leds = self._engine.make_static_leds(brightness)
                for i in range(16):
                    r, g, b = leds[i]
                    neo.set_pixel(i, r, g, b)

                eng = self._engine
                if eng.state == CORRECT:
                    neo.zone_pattern(
                        neo.ZONE_LID_RING,
                        neo.PAT_PULSE,
                        speed=3,
                        colour=(0, 255, 0),
                        brightness=lid_bright,
                    )
                elif eng.state == WRONG:
                    neo.zone_pattern(
                        neo.ZONE_LID_RING,
                        neo.PAT_PULSE,
                        speed=2,
                        colour=(255, 140, 0),
                        brightness=lid_bright,
                    )
                elif eng.state == LEVEL_UP:
                    neo.zone_pattern(
                        neo.ZONE_LID_RING,
                        neo.PAT_PULSE,
                        speed=4,
                        colour=(255, 200, 0),
                        brightness=lid_bright,
                    )
                elif eng.state in (ANNOUNCE, WAITING):
                    neo.zone_pattern(
                        neo.ZONE_LID_RING,
                        neo.PAT_SOLID,
                        colour=eng.rule_colour_rgb,
                        brightness=lid_bright,
                    )
                else:
                    neo.zone_off(neo.ZONE_LID_RING)
            else:
                # --- Python fallback path ---
                leds = self._engine.make_static_leds(brightness)

                eng = self._engine
                if eng.state == CORRECT:
                    zone_pulse(ZONE_LID_RING, frame, 3, (0, 255, 0), lid_bright)
                elif eng.state == WRONG:
                    zone_pulse(ZONE_LID_RING, frame, 2, (255, 140, 0), lid_bright)
                elif eng.state == LEVEL_UP:
                    zone_pulse(ZONE_LID_RING, frame, 4, (255, 200, 0), lid_bright)
                elif eng.state in (ANNOUNCE, WAITING):
                    zone_fill(ZONE_LID_RING, eng.rule_colour_rgb, lid_bright)
                else:
                    zone_clear(ZONE_LID_RING)

                ses_state = self._overlay.session_mgr.state
                leds = self._overlay.static_led_override(ses_state, leds, brightness)

                np = self._np
                for i in range(N_LEDS):
                    np[i] = leds[i]
                np.write()

        # Arcade LEDs
        arc = self._arcade
        if arc:
            if state == CORRECT:
                if not any(arc._flash_ttl):
                    for i in range(5):
                        arc.flash(i, duration=15)
                arc.tick_flash()
            else:
                arc.tick_flash()

    def _play_audio(self, prev_state, new_state):
        """Play audio feedback on state transitions."""
        audio = self._audio
        if audio is None:
            return

        try:
            from bodn.tts import say
        except ImportError:
            say = None

        eng = self._engine

        if new_state == WELCOME:
            if say:
                try:
                    say("rakna_welcome", audio)
                except Exception:
                    pass
        elif new_state == CORRECT:
            audio.tone(_CORRECT_TONE, 150)
            if say:
                try:
                    # Say the number word for the scanned card
                    key = eng.number_key
                    if key:
                        say(key, audio)
                except Exception:
                    pass
        elif new_state == WRONG:
            audio.tone(_WRONG_TONE, 200)
        elif new_state == LEVEL_UP:
            audio.tone(_LEVELUP_TONE, 100)
            if say:
                try:
                    say("rakna_level_up", audio)
                except Exception:
                    pass
        elif new_state == ANNOUNCE:
            if say:
                try:
                    ct = eng.challenge_type
                    if ct == CHALLENGE_DISCOVER:
                        say("rakna_discover", audio)
                    elif ct == CHALLENGE_FIND:
                        key = "rakna_find_{}".format(eng.target)
                        say(key, audio)
                    elif ct == CHALLENGE_MORE:
                        key = "rakna_more_{}".format(eng.target)
                        say(key, audio)
                    elif ct == CHALLENGE_LESS:
                        key = "rakna_less_{}".format(eng.target)
                        say(key, audio)
                    elif ct == CHALLENGE_ADD:
                        say("rakna_add", audio)
                    elif ct == CHALLENGE_SUB:
                        say("rakna_sub", audio)
                except Exception:
                    audio.tone(523, 100)
            else:
                audio.tone(523, 100)

    def render(self, tft, theme, frame):
        if self._pause.needs_render:
            self._pause.render(tft, theme, frame)
            return

        self._dirty = False
        w = theme.width
        h = theme.height

        if self._full_clear:
            tft.fill(theme.BLACK)
            self._full_clear = False

        eng = self._engine

        if eng.state == WELCOME:
            self._render_welcome(tft, theme, w, h)
        elif eng.state == ANNOUNCE:
            self._render_announce(tft, theme, w, h)
        elif eng.state == WAITING:
            self._render_waiting(tft, theme, w, h, frame)
        elif eng.state == CORRECT:
            self._render_correct(tft, theme, w, h)
        elif eng.state == WRONG:
            self._render_wrong(tft, theme, w, h)
        elif eng.state == LEVEL_UP:
            self._render_level_up(tft, theme, w, h)

    def _render_welcome(self, tft, theme, w, h):
        if self._title_sprite:
            _, tw, _ = self._title_sprite
            blit_sprite(tft, self._title_sprite, (w - tw) // 2, 60)
        draw_centered(tft, t("rakna_welcome"), h // 2 + 20, theme.CYAN, w)
        # Show current level
        draw_centered(tft, t("rakna_level", self._engine.level), h - 30, theme.MUTED, w)

    def _render_announce(self, tft, theme, w, h):
        tft.fill(theme.BLACK)
        eng = self._engine

        # Challenge text at top
        challenge_text = self._challenge_display_text()
        draw_centered(tft, challenge_text, 8, theme.WHITE, w, scale=2)

        # Number path below text (levels 2+ only)
        if eng.level >= 2:
            self._draw_number_path(tft, theme, w, highlight=eng.target)

        # Visual challenge content
        if eng.level in (4, 5):
            self._render_addend_dots(tft, theme, w, h)
        elif eng.level >= 2 and eng.target > 0:
            self._draw_dots(tft, theme, eng.target, w // 2, h // 2 + 20, 12, theme.CYAN)

        # Level indicator
        draw_centered(tft, t("rakna_level", eng.level), h - 16, theme.MUTED, w)

    def _render_waiting(self, tft, theme, w, h, frame):
        tft.fill(theme.BLACK)
        eng = self._engine

        # Challenge reminder at top
        challenge_text = self._challenge_display_text()
        draw_centered(tft, challenge_text, 12, theme.CYAN, w)

        # Number path with target highlighted (levels 2+ only)
        if eng.level >= 2:
            self._draw_number_path(tft, theme, w, highlight=eng.target)

        # Visual challenge content for levels 4-5
        if eng.level in (4, 5):
            self._render_addend_dots(tft, theme, w, h)
        else:
            # Pulsing scan hint
            pulse = (frame % 40) < 20
            hint_col = theme.WHITE if pulse else theme.MUTED
            draw_centered(tft, t("rakna_hint_scan"), h // 2, hint_col, w)

        # Score at bottom
        self._render_score(tft, theme, w, h)

    def _render_correct(self, tft, theme, w, h):
        tft.fill(theme.BLACK)
        eng = self._engine

        # Show scanned quantity as large dot pattern
        qty = eng.last_card_quantity
        if qty > 0:
            self._draw_dots(tft, theme, qty, w // 2, h // 2 - 20, 12, theme.GREEN)

        # Number word
        nk = eng.number_key
        if nk:
            draw_centered(tft, t(nk), h // 2 + 30, theme.WHITE, w, scale=2)

        draw_centered(tft, t("rakna_correct"), h // 2 + 56, theme.GREEN, w)

        # Number path with scanned position lit (levels 2-3 only)
        if eng.level >= 2:
            self._draw_number_path(tft, theme, w, highlight=qty, colour=theme.GREEN)

        self._render_score(tft, theme, w, h)

    def _render_wrong(self, tft, theme, w, h):
        tft.fill(theme.BLACK)
        eng = self._engine

        # Show what was scanned
        qty = eng.last_card_quantity
        if qty > 0:
            self._draw_dots(tft, theme, qty, w // 2, h // 2 - 30, 10, theme.MUTED)
            draw_centered(
                tft, t("rakna_that_was", t(eng.number_key)), h // 2, theme.MUTED, w
            )
        else:
            # Operator card or unknown
            draw_centered(tft, t("rakna_wrong_operator"), h // 2, theme.MUTED, w)

        # Show what was needed (level 2-3)
        if eng.level >= 2:
            challenge_text = self._challenge_display_text()
            draw_centered(tft, challenge_text, h // 2 + 24, theme.CYAN, w)

        self._render_score(tft, theme, w, h)

    def _render_level_up(self, tft, theme, w, h):
        tft.fill(theme.BLACK)
        draw_centered(tft, t("rakna_level_up"), h // 2 - 16, theme.AMBER, w, scale=2)
        draw_centered(
            tft,
            t("rakna_level", self._engine.level + 1),
            h // 2 + 16,
            theme.WHITE,
            w,
            scale=2,
        )

    def _render_addend_dots(self, tft, theme, w, h):
        """Draw two dot groups for levels 4-5 (addition/subtraction)."""
        eng = self._engine
        a = eng.addend_a
        b = eng.addend_b
        cy = h // 2 + 10
        dot_r = 10

        if eng.challenge_type == CHALLENGE_ADD:
            # Two groups side by side
            self._draw_dots(tft, theme, a, w // 4, cy, dot_r, theme.CYAN)
            self._draw_dots(tft, theme, b, w * 3 // 4, cy, dot_r, theme.CYAN)
            # "?" below
            draw_centered(tft, "?", h - 40, theme.WHITE, w, scale=2)
        elif eng.challenge_type == CHALLENGE_SUB:
            # Show full group: first (a-b) dots bright, last b dots faded
            remain = a - b
            self._draw_dots_split(
                tft, theme, a, remain, w // 2, cy, dot_r, theme.CYAN, theme.MUTED
            )
            # Narrative hint below
            nk_b = "{}{}".format("rakna_number_", b)
            draw_centered(tft, t("rakna_sub_hint", t(nk_b)), h - 40, theme.MUTED, w)

    def _draw_dots_split(
        self, tft, theme, total, bright_n, cx, cy, dot_r, col_bright, col_faded
    ):
        """Draw a dot pattern with first bright_n dots bright and the rest faded."""
        pattern = _DOT_PATTERNS.get(total)
        if not pattern:
            return

        grid = (dot_r * 5) // 2
        total_px = grid * 5
        ox = cx - total_px // 2
        oy = cy - total_px // 2

        for i, (dx, dy) in enumerate(pattern):
            px = ox + dx * grid + grid // 2
            py = oy + dy * grid + grid // 2
            col = col_bright if i < bright_n else col_faded
            tft.ellipse(px, py, dot_r, dot_r, col, True)

    def _render_score(self, tft, theme, w, h):
        """Draw score and streak at the bottom."""
        score_text = t("rakna_score", self._engine.score)
        streak_text = t("rakna_streak", self._engine.streak)
        tft.text(score_text, 8, h - 16, theme.MUTED)
        tft.text(streak_text, w - len(streak_text) * 8 - 8, h - 16, theme.MUTED)

    def _challenge_display_text(self):
        """Get display text for the current challenge."""
        eng = self._engine
        ct = eng.challenge_type
        if ct == CHALLENGE_DISCOVER:
            return t("rakna_discover")
        elif ct == CHALLENGE_FIND:
            return t("rakna_find", t(eng.target_number_key))
        elif ct == CHALLENGE_MORE:
            return t("rakna_more", t(eng.target_number_key))
        elif ct == CHALLENGE_LESS:
            return t("rakna_less", t(eng.target_number_key))
        elif ct == CHALLENGE_ADD:
            return t("rakna_add")
        elif ct == CHALLENGE_SUB:
            return t("rakna_sub")
        return ""

    def _draw_number_path(self, tft, theme, w, highlight=0, colour=None):
        """Draw horizontal number path (1-10) near the top of the screen."""
        total_width = 10 * _PATH_SPACING
        x0 = (w - total_width) // 2 + _PATH_R
        y = _PATH_Y + _PATH_R

        for n in range(1, 11):
            cx = x0 + (n - 1) * _PATH_SPACING
            r = _PATH_R
            if n == highlight:
                col = colour or theme.CYAN
                tft.ellipse(cx, y, r, r, col, True)
            else:
                tft.ellipse(cx, y, r, r, theme.MUTED, False)

    def _draw_dots(self, tft, theme, quantity, cx, cy, dot_r, colour):
        """Draw a dot pattern for the given quantity, centred at (cx, cy)."""
        pattern = _DOT_PATTERNS.get(quantity)
        if not pattern:
            return

        # Scale: each grid unit = dot_r * 2.5
        grid = (dot_r * 5) // 2
        total = grid * 5
        ox = cx - total // 2
        oy = cy - total // 2

        for dx, dy in pattern:
            px = ox + dx * grid + grid // 2
            py = oy + dy * grid + grid // 2
            tft.ellipse(px, py, dot_r, dot_r, colour, True)
