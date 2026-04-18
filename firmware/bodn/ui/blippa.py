# bodn/ui/blippa.py — free-play "blip any card" screen
#
# Tap any Sortera/Räkna card (or any future card set) and get instant
# audio + visual feedback.  No goal, no failure state — the simplest
# screen in the codebase.  Launcher cards continue to launch their mode
# (routing fix in nfc.route_tag guarantees that).

import time

from micropython import const
from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.input import BrightnessControl
from bodn.ui.widgets import (
    draw_centered,
    load_emoji,
    blit_sprite,
    make_label_sprite,
)
from bodn.ui.pause import PauseMenu
from bodn.i18n import t, capitalize
from bodn.neo import neo
from bodn.ui.catface import NEUTRAL, CURIOUS, HAPPY


# Card-set modes Blippa listens to.  Add new modes here when new card
# sets ship (see docs/nfc.md).  Launcher tags are handled globally by
# bodn.nfc.route_tag and never reach this screen.
_SUBSCRIBED = ("sortera", "rakna")

# Procedural "default blip" — two short square-wave chirps evocative of
# a POS scanner.  Used when a known card has no custom ``sound`` stem.
_BLIP_TONE_A_HZ = const(2400)
_BLIP_TONE_B_HZ = const(3200)
_BLIP_TONE_MS = const(45)

# Mystery-blip: a known mode but the id isn't in our card set.  The
# pitch is derived from a stable hash of the id so repeat scans always
# sound the same.  Range ~ A4..A5 so it reads as musical, not alarm.
_MYSTERY_BASE_HZ = const(440)
_MYSTERY_SPREAD_HZ = const(440)
_MYSTERY_TONE_MS = const(150)

# After a blip, hold the emoji on screen for this long before returning
# to the idle "tap a card" prompt.  Short enough to stay responsive;
# long enough for a 4-year-old to see what card they scanned.
_HOLD_MS = const(2500)


def _card_bilingual_label(card):
    """Build a dual-language label, e.g. 'Katt / Cat'."""
    if card is None:
        return None
    sv = card.get("label_sv", "")
    en = card.get("label_en", "")
    if sv and en:
        return "{} / {}".format(capitalize(sv), capitalize(en))
    return capitalize(sv or en or "") or None


def _stable_hash(s):
    """Cross-platform deterministic hash of a short string.

    MicroPython and CPython disagree on ``hash()``, so we use a simple
    byte-sum so mystery-blip pitches are reproducible on both.
    """
    h = 0
    for ch in s:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h


class BlippaScreen(Screen):
    """Blippa — tap any card, hear a blip.  Free-play, no goal."""

    # Subscribe to every known non-launcher card-set mode.  Launcher
    # tags are filtered out by bodn.nfc.route_tag before reaching here,
    # so tapping a launcher card (even for a subscribed mode) still
    # launches that mode instead of being swallowed by Blippa.
    nfc_modes = frozenset(_SUBSCRIBED)

    def __init__(
        self,
        overlay,
        arcade=None,
        audio=None,
        settings=None,
        secondary_screen=None,
        on_exit=None,
    ):
        self._overlay = overlay
        self._arcade = arcade
        self._audio = audio
        self._secondary = secondary_screen
        self._on_exit = on_exit
        self._brightness = BrightnessControl(settings=settings)
        self._manager = None
        self._pause = PauseMenu(settings=settings)

        self._cards = {}  # (mode, id) → card dict
        self._pending_tag = None  # (mode, id) from last NFC scan
        self._active_tag = None  # (mode, id) currently displayed
        self._hold_until_ms = 0

        self._dirty = True
        self._full_clear = True
        self._title_sprite = None
        self._hint_sprite = None

    def on_nfc_tag(self, parsed):
        mode = parsed["mode"]
        card_id = parsed["id"]
        if not card_id:
            return False
        self._pending_tag = (mode, card_id)
        return True

    def enter(self, manager):
        self._manager = manager
        self._pause.set_manager(manager)
        self._brightness.reset()
        self._dirty = True
        self._full_clear = True

        # Build the (mode, id) → card lookup once.  ~50 cards across the
        # bundled sets; each dict is small, total footprint < 4 KB.
        from bodn.nfc import load_card_set

        self._cards = {}
        for mode in _SUBSCRIBED:
            cs = load_card_set(mode)
            if not cs:
                continue
            for card in cs.get("cards", []):
                cid = card.get("id")
                if cid:
                    self._cards[(mode, cid)] = card

        self._pending_tag = None
        self._active_tag = None
        self._hold_until_ms = 0

        neo.clear_all_overrides()
        neo.all_off()

        self._title_sprite = make_label_sprite(
            capitalize(t("mode_blippa")), 0xFFFF, scale=3
        )
        self._hint_sprite = make_label_sprite(t("blippa_hint_scan"), 0xFFFF, scale=2)

        if self._secondary:
            self._secondary.set_emotion(CURIOUS)

    def exit(self):
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
        # Pause menu always wins
        result = self._pause.update(inp, frame)
        if result == "quit" and self._manager:
            self._manager.pop()
            return
        elif result == "resume":
            self._dirty = True
            self._full_clear = True
        if self._pause.is_open or self._pause.is_holding:
            return

        # Consume pending NFC tag
        if self._pending_tag is not None:
            tag = self._pending_tag
            self._pending_tag = None
            self._active_tag = tag
            self._hold_until_ms = time.ticks_add(time.ticks_ms(), _HOLD_MS)
            self._dirty = True
            self._full_clear = True
            self._play_blip(tag)
            if self._secondary:
                self._secondary.set_emotion(HAPPY)

        # After the hold window expires, return to idle
        if (
            self._active_tag is not None
            and time.ticks_diff(time.ticks_ms(), self._hold_until_ms) >= 0
        ):
            self._active_tag = None
            self._dirty = True
            self._full_clear = True
            if self._secondary:
                self._secondary.set_emotion(NEUTRAL)

        # Brightness — rotary encoder A (primary)
        prev_bri = self._brightness.value
        self._brightness.update(
            inp.enc_delta[config.ENC_A], inp.enc_velocity[config.ENC_A]
        )
        if self._brightness.value != prev_bri:
            # No LED state to redraw; brightness affects the NeoPixel
            # output if/when we use it.  Kept for consistency.
            pass

    # ------------------------------------------------------------------
    # Audio
    # ------------------------------------------------------------------

    def _play_blip(self, tag):
        audio = self._audio
        if audio is None:
            return
        mode, card_id = tag
        card = self._cards.get(tag)

        # 1. Custom per-card sound (opt-in via JSON "sound" field)
        if card is not None:
            stem = card.get("sound")
            if stem and self._try_play_custom(stem):
                return

        # 2. Known card with no custom sound → default POS blip
        if card is not None:
            try:
                audio.tone(_BLIP_TONE_A_HZ, _BLIP_TONE_MS, "square")
                audio.tone(_BLIP_TONE_B_HZ, _BLIP_TONE_MS, "square")
            except Exception:
                pass
            return

        # 3. Unknown card in a known mode → deterministic mystery blip
        pitch = _MYSTERY_BASE_HZ + (_stable_hash(card_id) % _MYSTERY_SPREAD_HZ)
        try:
            audio.tone(pitch, _MYSTERY_TONE_MS, "sine")
        except Exception:
            pass

    def _try_play_custom(self, stem):
        audio = self._audio
        try:
            from bodn.assets import resolve
            import os

            path = resolve("/sounds/blippa/" + stem + ".wav")
            try:
                os.stat(path)
            except OSError:
                return False
            audio.play(path, channel="sfx")
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

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

        if self._active_tag is None:
            self._render_idle(tft, theme, w, h)
        else:
            self._render_card(tft, theme, w, h)

    def _render_idle(self, tft, theme, w, h):
        if self._title_sprite:
            _, tw, _ = self._title_sprite
            blit_sprite(tft, self._title_sprite, (w - tw) // 2, h // 3 - 20)
        if self._hint_sprite:
            _, hw, _ = self._hint_sprite
            blit_sprite(tft, self._hint_sprite, (w - hw) // 2, h // 2 + 20)

    def _render_card(self, tft, theme, w, h):
        mode, card_id = self._active_tag
        card = self._cards.get(self._active_tag)

        # Emoji — prefer the card's own icon-family name.  Sortera cards
        # encode the subject in the id prefix (e.g. "cat_red" → "cat");
        # Räkna number cards use "dots_N" which has no emoji, so fall
        # back on the label.
        emoji_name = self._emoji_name_for(mode, card_id, card)
        emoji = load_emoji(emoji_name, 96) if emoji_name else None
        if emoji is None and emoji_name:
            emoji = load_emoji(emoji_name, 48)

        if emoji:
            asset, ew, eh = emoji
            try:
                from bodn.ui.draw import sprite

                ex = (w - ew) // 2
                ey = 30
                pad = 4
                tft.fill_rect(ex - pad, ey - pad, ew + pad * 2, eh + pad * 2, 0xEF7D)
                sprite(tft, ex, ey, asset, 0, 0xFFFF)
            except Exception:
                pass

        label = _card_bilingual_label(card) or capitalize(card_id)
        if label:
            draw_centered(tft, label, h - 60, theme.WHITE, w, scale=2)

        draw_centered(tft, t("mode_" + mode), h - 20, theme.MUTED, w)

    def _emoji_name_for(self, mode, card_id, card):
        """Pick the best emoji family name for a card."""
        # Sortera: id is "<subject>_<colour>" — subject is the emoji name.
        if mode == "sortera" and card_id:
            return card_id.split("_")[0]
        # Räkna number cards: quantity → digit word (the OpenMoji manifest
        # doesn't include digit sprites; leave unmapped so we show the
        # bilingual label without an emoji).
        if mode == "rakna" and card is not None:
            op = card.get("operator")
            if op == "+":
                return "plus"
            if op == "-":
                return "minus"
            if op == "=":
                return "equals"
            return None
        # Fallback: try the raw id
        return card_id
