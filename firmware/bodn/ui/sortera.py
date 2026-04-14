# bodn/ui/sortera.py — Sortera classification game screen
#
# NFC card sorting game based on the DCCS task.  Announces a rule
# ("Find the animals!"), child scans cards.  After N correct the rule
# switches.  Demo mode: buttons 0-7 simulate card scans.

import time

from micropython import const
from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.input import BrightnessControl
from bodn.ui.widgets import draw_centered, load_emoji, blit_sprite, make_label_sprite
from bodn.ui.pause import PauseMenu
from bodn.i18n import t, capitalize
from bodn.sortera_rules import (
    SorteraEngine,
    WELCOME,
    ANNOUNCE_RULE,
    WAITING,
    CORRECT,
    WRONG,
    RULE_SWITCH,
    DEMO_CARDS,
)
from bodn.patterns import (
    N_LEDS,
    zone_fill,
    zone_pulse,
    zone_chase,
    zone_clear,
    ZONE_LID_RING,
)
from bodn.ui.catface import NEUTRAL, CURIOUS, HAPPY

NAV = const(0)

_STATE_EMOTIONS = {
    WELCOME: NEUTRAL,
    ANNOUNCE_RULE: CURIOUS,
    WAITING: CURIOUS,
    CORRECT: HAPPY,
    WRONG: NEUTRAL,
    RULE_SWITCH: CURIOUS,
}

# Tone feedback
_CORRECT_TONE = 880  # A5
_WRONG_TONE = 220  # A3
_SWITCH_TONE = 587  # D5

# Animal names for demo button labels
_ANIMAL_NAMES = ["cat", "dog", "rabbit", "bird", "fish", "horse", "cow", "frog"]

# Colour names for i18n lookup
_COLOUR_KEYS = {
    "red": "sortera_red",
    "blue": "sortera_blue",
    "green": "sortera_green",
    "yellow": "sortera_yellow",
}

# Animal names for i18n lookup
_ANIMAL_KEYS = {
    "cat": "sortera_cat",
    "dog": "sortera_dog",
    "rabbit": "sortera_rabbit",
    "bird": "sortera_bird",
    "fish": "sortera_fish",
    "horse": "sortera_horse",
    "cow": "sortera_cow",
    "frog": "sortera_frog",
}

# Vehicle names for i18n lookup
_VEHICLE_KEYS = {
    "car": "sortera_car",
    "bus": "sortera_bus",
    "firetruck": "sortera_firetruck",
    "ambulance": "sortera_ambulance",
    "train": "sortera_train",
    "taxi": "sortera_taxi",
}

# Category names for i18n lookup
_CATEGORY_KEYS = {
    "animal": "sortera_animal",
    "vehicle": "sortera_vehicle",
}


def _filter_by_cache(card_set, cache):
    """Filter a card set to only cards with programmed NFC tags.

    If the cache has no sortera entries, returns the full card set
    unchanged (assume demo/first-time use).  Otherwise, keeps only
    cards whose IDs appear in the cache, and prunes dimensions that
    no longer have at least 2 distinct values.
    """
    known_ids = set()
    for entry in cache.entries().values():
        if entry.get("mode") == "sortera":
            known_ids.add(entry["id"])

    if not known_ids:
        return card_set

    cards = [c for c in card_set.get("cards", []) if c["id"] in known_ids]
    if not cards:
        return card_set

    # Prune dimensions: keep only those with 2+ distinct values
    dims = []
    for dim in card_set.get("dimensions", []):
        values = set()
        for card in cards:
            val = card.get(dim)
            if val is not None:
                values.add(val)
        if len(values) >= 2:
            dims.append(dim)

    return {"mode": card_set.get("mode", "sortera"), "dimensions": dims, "cards": cards}


def _card_bilingual_label(card):
    """Build a dual-language label from a card dict, e.g. 'Katt / Cat'."""
    if card is None:
        return None
    sv = card.get("label_sv", "")
    en = card.get("label_en", "")
    if sv and en:
        return "{} / {}".format(capitalize(sv), capitalize(en))
    return capitalize(sv or en or "") or None


class SorteraScreen(Screen):
    """Sortera — sort the cards by the announced rule!

    Buttons 0-7 simulate NFC card scans (demo mode).
    Hold nav encoder button to open the pause menu.
    """

    nfc_modes = frozenset({"sortera"})

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
        self._rule_emoji = None  # cached emoji for current rule value

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

        card_set = load_card_set("sortera")
        if card_set is None:
            # Fallback: minimal card set for demo
            card_set = {
                "mode": "sortera",
                "dimensions": ["animal", "colour"],
                "cards": [
                    {
                        "id": c,
                        "category": "animal",
                        "animal": c.split("_")[0],
                        "colour": c.split("_")[-1],
                    }
                    for c in DEMO_CARDS
                ],
            }
        else:
            # Filter card set to only include physically programmed tags
            card_set = _filter_by_cache(card_set, UIDCache())
        self._engine = SorteraEngine(card_set)
        self._pending_card_id = None

        # Pre-render title sprite
        self._title_sprite = make_label_sprite("Sortera", 0xFFFF, scale=2)

        # Engine starts in WELCOME — play welcome TTS
        self._rule_emoji = None
        self._prev_state = WELCOME
        self._play_audio(None, WELCOME)

    def exit(self):
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

        # Demo mode: buttons 0-7 and arcade buttons 0-4 map to animals
        btn = inp.first_btn_pressed()
        if btn >= 0 and btn < len(DEMO_CARDS):
            card_id = DEMO_CARDS[btn]
        arc = inp.first_arc_pressed()
        if arc >= 0 and arc < len(DEMO_CARDS):
            card_id = DEMO_CARDS[arc]

        # NFC card delivered by global nfc_scan_task
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
            # Update cat face
            if self._secondary:
                emotion = _STATE_EMOTIONS.get(state, NEUTRAL)
                self._secondary.set_emotion(emotion)
            # Audio feedback
            self._play_audio(prev_state, state)
            # Cache rule emoji when rule changes
            if state == ANNOUNCE_RULE:
                self._cache_rule_emoji()

        # Card scan also triggers visual update
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

            leds = self._engine.make_static_leds(brightness)

            eng = self._engine
            if eng.state == CORRECT:
                zone_pulse(ZONE_LID_RING, frame, 3, (0, 255, 0), lid_bright)
            elif eng.state == WRONG:
                zone_pulse(ZONE_LID_RING, frame, 2, (255, 0, 0), lid_bright)
            elif eng.state == RULE_SWITCH:
                zone_chase(ZONE_LID_RING, frame, 4, eng.rule_colour_rgb, lid_bright)
            elif eng.state in (ANNOUNCE_RULE, WAITING):
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
            elif state == WRONG:
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

        if new_state == WELCOME:
            if say:
                try:
                    say("sortera_welcome", audio)
                except Exception:
                    pass
        elif new_state == CORRECT:
            audio.tone(_CORRECT_TONE, 150)
            if say:
                try:
                    # Say bilingual animal name (e.g. "katt, cat") instead
                    # of generic "Rätt!" — reinforces translation equivalents
                    card_name = self._card_tts_key()
                    if not card_name or not say(card_name, audio):
                        say("sortera_correct", audio)
                except Exception:
                    pass
        elif new_state == WRONG:
            audio.tone(_WRONG_TONE, 200)
        elif new_state == RULE_SWITCH:
            audio.tone(_SWITCH_TONE, 100)
            if say:
                try:
                    say("sortera_new_rule", audio)
                except Exception:
                    pass
        elif new_state == ANNOUNCE_RULE:
            # Play TTS rule announcement
            if say:
                try:
                    dim = self._engine.rule_dimension
                    val = self._engine.rule_value
                    key = "sortera_find_{}_{}".format(dim, val)
                    say(key, audio)
                except Exception:
                    audio.tone(523, 100)  # fallback beep
            else:
                audio.tone(523, 100)

    def _card_tts_key(self):
        """Return the TTS key for the last scanned card's bilingual label."""
        eng = self._engine
        if eng.last_card_id:
            animal = eng.last_card_id.split("_")[0]  # "cat_red" → "cat"
            return "sortera_label_{}".format(animal)
        return None

    def _cache_rule_emoji(self):
        """Cache the emoji sprite for the current rule value."""
        self._rule_emoji = None
        eng = self._engine
        if eng.rule_dimension in ("animal", "vehicle"):
            self._rule_emoji = load_emoji(eng.rule_value, 48)
        elif eng.rule_dimension == "category":
            # Representative emoji for the category
            if eng.rule_value == "animal":
                self._rule_emoji = load_emoji("cat", 48)
            elif eng.rule_value == "vehicle":
                self._rule_emoji = load_emoji("car", 48)

    def render(self, tft, theme, frame):
        # Let pause menu render on top if open
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
        elif eng.state == ANNOUNCE_RULE:
            self._render_announce(tft, theme, w, h)
        elif eng.state == WAITING:
            self._render_waiting(tft, theme, w, h, frame)
        elif eng.state == CORRECT:
            self._render_correct(tft, theme, w, h)
        elif eng.state == WRONG:
            self._render_wrong(tft, theme, w, h)
        elif eng.state == RULE_SWITCH:
            self._render_switch(tft, theme, w, h)

    def _render_welcome(self, tft, theme, w, h):
        if self._title_sprite:
            _, tw, _ = self._title_sprite
            blit_sprite(tft, self._title_sprite, (w - tw) // 2, 60)
        draw_centered(tft, t("sortera_welcome"), h // 2 + 20, theme.CYAN, w)

    def _render_announce(self, tft, theme, w, h):
        tft.fill(theme.BLACK)
        # Rule announcement
        eng = self._engine
        rule_text = self._rule_display_text()
        draw_centered(tft, rule_text, 40, theme.WHITE, w, scale=2)

        # Show emoji for the rule value if available
        if eng.rule_dimension == "colour":
            # Draw a large colour swatch
            r, g, b = eng.rule_colour_rgb
            col = theme.rgb(r, g, b)
            cx = (w - 60) // 2
            tft.fill_rect(cx, 80, 60, 60, col)
        else:
            # Show an animal emoji
            emoji = self._rule_emoji
            if emoji:
                asset, ew, eh = emoji
                try:
                    from bodn.ui.draw import sprite

                    ex = (w - ew) // 2
                    pad = 4
                    tft.fill_rect(
                        ex - pad, 80 - pad, ew + pad * 2, eh + pad * 2, 0xEF7D
                    )
                    sprite(tft, ex, 80, asset, 0, 0xFFFF)
                except Exception:
                    pass

        # Progress dots (all empty at start of rule)
        self._render_progress_dots(tft, theme, w, h - 30)

    def _render_waiting(self, tft, theme, w, h, frame):
        tft.fill(theme.BLACK)

        # Current rule at top
        rule_text = self._rule_display_text()
        draw_centered(tft, rule_text, 12, theme.CYAN, w)

        # Progress dots below rule
        self._render_progress_dots(tft, theme, w, 32)

        # Pulsing hint in the centre
        pulse = (frame % 40) < 20
        hint_col = theme.WHITE if pulse else theme.MUTED
        hint = t("sortera_hint_scan")
        draw_centered(tft, hint, h // 2, hint_col, w)

        # Score at bottom
        self._render_score(tft, theme, w, h)

    def _render_correct(self, tft, theme, w, h):
        tft.fill(theme.BLACK)
        eng = self._engine

        # Show scanned card emoji
        if eng.last_card:
            card_name = eng.last_card_id.split("_")[0]  # "cat_red" → "cat"
            emoji = load_emoji(card_name, 48)
            if emoji:
                asset, ew, eh = emoji
                try:
                    from bodn.ui.draw import sprite

                    ex = (w - ew) // 2
                    ey = 30
                    pad = 4
                    tft.fill_rect(
                        ex - pad, ey - pad, ew + pad * 2, eh + pad * 2, 0xEF7D
                    )
                    sprite(tft, ex, ey, asset, 0, 0xFFFF)
                except Exception as e:
                    print("Sortera: emoji render error:", e)

        # Bilingual card label below emoji
        bilabel = _card_bilingual_label(eng.last_card)
        if bilabel:
            draw_centered(tft, bilabel, h // 2 + 20, theme.WHITE, w, scale=2)

        draw_centered(tft, t("sortera_correct"), h // 2 + 46, theme.GREEN, w)
        self._render_progress_dots(tft, theme, w, h // 2 + 66)
        self._render_score(tft, theme, w, h)

    def _render_wrong(self, tft, theme, w, h):
        tft.fill(theme.BLACK)
        eng = self._engine

        # Show scanned card emoji
        if eng.last_card:
            card_name = eng.last_card_id.split("_")[0]
            emoji = load_emoji(card_name, 48)
            if emoji:
                asset, ew, eh = emoji
                try:
                    from bodn.ui.draw import sprite

                    ex = (w - ew) // 2
                    ey = 40
                    pad = 4
                    tft.fill_rect(
                        ex - pad, ey - pad, ew + pad * 2, eh + pad * 2, 0xEF7D
                    )
                    sprite(tft, ex, ey, asset, 0, 0xFFFF)
                except Exception as e:
                    print("Sortera: emoji render error:", e)

        # Bilingual card label below emoji
        bilabel = _card_bilingual_label(eng.last_card)
        if bilabel:
            draw_centered(tft, bilabel, h // 2 + 10, theme.MUTED, w)

        # Gentle feedback — show the rule so child knows what to look for
        rule_text = self._rule_display_text()
        draw_centered(tft, rule_text, h // 2 + 30, theme.MUTED, w)
        self._render_progress_dots(tft, theme, w, h // 2 + 50)
        self._render_score(tft, theme, w, h)

    def _render_switch(self, tft, theme, w, h):
        tft.fill(theme.BLACK)
        draw_centered(tft, t("sortera_new_rule"), h // 2 - 8, theme.AMBER, w, scale=2)

    def _render_progress_dots(self, tft, theme, w, y):
        """Draw filled/empty dots showing how many unique cards have been found."""
        eng = self._engine
        total = eng._switch_threshold
        found = eng._rule_correct_count
        if total <= 0:
            return

        # Dot sizing: 8px filled, 4px gap — scales down for many dots
        dot_sz = 8 if total <= 8 else 6
        gap = 4 if total <= 8 else 3
        row_w = total * dot_sz + (total - 1) * gap
        x0 = (w - row_w) // 2

        filled_col = theme.GREEN
        empty_col = theme.MUTED

        for i in range(total):
            dx = x0 + i * (dot_sz + gap)
            if i < found:
                tft.fill_rect(dx, y, dot_sz, dot_sz, filled_col)
            else:
                # Outline only
                tft.rect(dx, y, dot_sz, dot_sz, empty_col)

    def _render_score(self, tft, theme, w, h):
        """Draw score and streak at the bottom of the screen."""
        score_text = t("sortera_score", self._engine.score)
        streak_text = t("sortera_streak", self._engine.streak)
        tft.text(score_text, 8, h - 16, theme.MUTED)
        tft.text(streak_text, w - len(streak_text) * 8 - 8, h - 16, theme.MUTED)

    def _rule_display_text(self):
        """Get display text for the current rule."""
        eng = self._engine
        if eng.rule_dimension == "colour":
            return t(
                "sortera_find_colour",
                t(_COLOUR_KEYS.get(eng.rule_value, eng.rule_value)),
            )
        elif eng.rule_dimension == "animal":
            return t(
                "sortera_find_animal",
                t(_ANIMAL_KEYS.get(eng.rule_value, eng.rule_value)),
            )
        elif eng.rule_dimension == "vehicle":
            return t(
                "sortera_find_vehicle",
                t(_VEHICLE_KEYS.get(eng.rule_value, eng.rule_value)),
            )
        elif eng.rule_dimension == "category":
            return t(
                "sortera_find_animal"
                if eng.rule_value == "animal"
                else "sortera_find_vehicle",
                t(_CATEGORY_KEYS.get(eng.rule_value, eng.rule_value)),
            )
        return eng.rule_value
