# bodn/ui/story.py — Story Mode screen (branching interactive narrative)
#
# Data-driven: stories are Python dicts loaded from SD (/sd/stories/*/script.py).
# The screen handles display, audio, LEDs, and arcade button input; the engine
# (story_rules.py) handles pure logic.
#
# Layout (320x240 landscape):
#   Top ~120px: mood colour wash
#   Middle ~60px: narration text (word-wrapped, scale 2)
#   Bottom ~60px: choice labels with arcade button colour dots

import time
#
# Arcade buttons 0..N light up during CHOOSING to show available choices.

import os

from micropython import const
from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.input import BrightnessControl
from bodn.ui.widgets import (
    draw_centered,
    draw_label,
    make_label_sprite,
    blit_sprite,
    blit_centered,
)
from bodn.ui.pause import PauseMenu
from bodn.i18n import t, get_language
from bodn.story_rules import (
    StoryEngine,
    IDLE,
    NARRATING,
    CHOOSING,
    TRANSITIONING,
    ENDING,
    MOOD_COLORS,
    ARC_COLORS,
)
from bodn.ui.catface import NEUTRAL, CURIOUS, HAPPY
from bodn.neo import neo

NAV = const(0)  # config.ENC_NAV
N_ARCADE = const(5)

# Mood colour wash → RGB565 (pre-computed at render time from theme.rgb)
_MOOD_565 = {}

# Map moods to cat emotions
_MOOD_EMOTIONS = {
    "warm": NEUTRAL,
    "tense": CURIOUS,
    "happy": HAPPY,
    "wonder": CURIOUS,
    "calm": NEUTRAL,
}

# Arcade button 565 colours (index 0-4: green, blue, white, yellow, red)
_ARC_565 = None

# End menu: arcade button assignments (hardware indices from config.ARCADE_COLORS)
_END_REPLAY = const(0)  # yellow — replay same story
_END_EXIT = const(1)  # red — exit story mode
_END_PICK = const(2)  # blue — pick another story (only when multiple)


def _discover_stories():
    """Find story scripts on SD card. Returns list of (story_id, path) tuples."""
    stories = []
    try:
        for name in os.listdir("/sd/stories"):
            path = "/sd/stories/{}/script.py".format(name)
            try:
                os.stat(path)
                stories.append((name, path))
            except OSError:
                pass
    except OSError:
        pass
    return stories


def _load_story_from_file(path):
    """Load a STORY dict from a script.py file. Returns dict or None."""
    ns = {}
    try:
        with open(path) as f:
            exec(f.read(), ns)
        return ns.get("STORY")
    except Exception as e:
        print("story load error {}: {}".format(path, e))
        return None


def _load_story_title(path, story_id):
    """Extract just the title from a story script without loading the full dict.

    Falls back to story_id if loading fails.
    """
    try:
        story = _load_story_from_file(path)
        if story:
            titles = story.get("title", {})
            return titles  # {lang: title} dict
    except Exception:
        pass
    return {"en": story_id}


def _word_wrap(text, max_chars):
    """Simple word wrap. Returns list of lines."""
    words = text.split(" ")
    lines = []
    line = ""
    for word in words:
        if line and len(line) + 1 + len(word) > max_chars:
            lines.append(line)
            line = word
        else:
            line = (line + " " + word) if line else word
    if line:
        lines.append(line)
    return lines


class StoryScreen(Screen):
    """Story Mode — branching interactive narratives.

    Arcade buttons (0-4) select choices.  Hold nav encoder to pause.
    Stories are discovered from SD (/sd/stories/*/script.py).
    If multiple stories exist, a simple picker is shown first.
    """

    def __init__(
        self,
        overlay,
        audio=None,
        arcade=None,
        settings=None,
        secondary_screen=None,
        on_exit=None,
    ):
        self._overlay = overlay
        self._audio = audio
        self._arcade = arcade
        self._secondary = secondary_screen
        self._on_exit = on_exit
        self._engine = StoryEngine()
        self._brightness = BrightnessControl(settings=settings)
        self._manager = None
        self._pause = PauseMenu(settings=settings)
        self._prev_state = None
        self._dirty = True
        self._full_clear = True
        self._leds_dirty = True
        # Story selection
        self._stories = []  # [(id, path)]
        self._picker_index = 0
        self._picker_mode = False
        self._end_menu = False  # post-story choice screen
        self._last_story_index = 0  # for replay
        # Sprite caches (built in enter / on node transitions)
        self._spr = {}  # static i18n sprites
        self._narr_sprites = []  # word-wrapped narration lines
        self._end_sprites = []  # end menu option labels
        # TTS state
        self._tts_playing = False
        self._tts_has_choices = False
        self._tts_phase = 0  # 0=scene, 1=choices, 2=done
        # Fallback timer: if no TTS file, auto-advance after this many frames
        self._narrate_timer = 0
        self._narrate_timeout = 0  # set per-node based on text length

    def enter(self, manager):
        self._manager = manager
        self._pause.set_manager(manager)
        self._engine.reset()
        self._brightness.reset()
        self._last_ms = time.ticks_ms()
        self._dirty = True
        self._full_clear = True
        neo.clear_all_overrides()

        # Init 565 colour caches
        global _MOOD_565, _ARC_565
        rgb = manager.theme.rgb
        _MOOD_565 = {mood: rgb(c[0], c[1], c[2]) for mood, c in MOOD_COLORS.items()}
        _ARC_565 = [rgb(c[0], c[1], c[2]) for c in ARC_COLORS]

        # Pre-render static i18n label sprites
        theme = manager.theme
        self._spr = {
            "title2": make_label_sprite(t("story_title"), theme.CYAN, scale=2),
            "title_muted": make_label_sprite(t("story_title"), theme.MUTED, scale=2),
            "the_end3": make_label_sprite(t("story_the_end"), theme.YELLOW, scale=3),
            "the_end2": make_label_sprite(t("story_the_end"), theme.YELLOW, scale=2),
            "dots3": make_label_sprite("...", theme.MUTED, scale=2),
            "dots2": make_label_sprite("..", theme.MUTED, scale=2),
            "trans": make_label_sprite("...", theme.MUTED, scale=2),
        }

        # Discover available stories from SD and pre-load titles
        self._stories = _discover_stories()
        self._story_titles = {}
        for sid, path in self._stories:
            self._story_titles[sid] = _load_story_title(path, sid)

        if not self._stories:
            # No stories on SD — stay in picker (shows "no stories" message)
            self._picker_mode = True
            self._picker_index = 0
            return

        if len(self._stories) == 1:
            # Single story — load directly
            self._picker_mode = False
            self._load_story(0)
        else:
            self._picker_mode = True
            self._picker_index = 0

    def _load_story(self, index):
        """Load story at index and start the engine."""
        self._last_story_index = index
        self._end_menu = False
        sid, path = self._stories[index]
        story = _load_story_from_file(path)
        if story is None:
            return
        errors = self._engine.load(story)
        if errors:
            print("story validation errors:", errors)
            return
        self._picker_mode = False
        self._dirty = True
        self._full_clear = True
        self._leds_dirty = True
        self._cache_narration_sprites()
        self._start_narration()

    def _resolve_story_tts(self, node_id, suffix=""):
        """Build and resolve a story narration path.

        Story audio lives alongside the story script on SD:
          /stories/{story_id}/tts/{lang}/{node_id}{suffix}.wav        (generated)
          /stories/{story_id}/recordings/{lang}/{node_id}{suffix}.wav (recorded)

        Recordings override generated TTS per-node via bodn.assets.resolve_voice.
        Returns the resolved filesystem path, or None if neither exists.
        """
        eng = self._engine
        lang = get_language()
        from bodn.assets import resolve_voice

        return resolve_voice(
            "/stories/{}/tts/{}/{}{}.wav".format(eng.story_id, lang, node_id, suffix)
        )

    def _cache_narration_sprites(self):
        """Pre-render word-wrapped narration lines for the current node."""
        eng = self._engine
        lang = get_language()
        text = eng.text(lang)
        w = self._manager.theme.width if self._manager else 240
        max_chars = w // 16  # scale 2 = 16px per char
        lines = _word_wrap(text, max_chars)
        color = self._manager.theme.WHITE if self._manager else 0xFFFF
        self._narr_sprites = [
            make_label_sprite(line, color, scale=2) for line in lines[:4]
        ]

    def _cache_end_sprites(self):
        """Pre-render end menu option labels."""
        color = self._manager.theme.WHITE if self._manager else 0xFFFF
        labels = [t("story_end_replay"), t("story_end_exit")]
        if len(self._stories) > 1:
            labels.append(t("story_end_pick"))
        self._end_sprites = [make_label_sprite(lb, color, scale=2) for lb in labels]

    def _start_narration(self):
        """Begin TTS for the current node.

        If TTS files exist, plays them via the audio engine with a
        scene → choices sequence.  If no TTS files, uses a text-length-
        based timer so the child has time to read/absorb the scene.
        """
        self._tts_phase = 0
        eng = self._engine
        lang = get_language()
        # Check if choices TTS should be played after scene narration
        self._tts_has_choices = eng.narrate_choices and eng.choice_count > 0
        # Try to play scene TTS
        tts_found = False
        if self._audio and self._audio._voices:
            scene_path = self._resolve_story_tts(eng.node_id)
            if scene_path:
                self._audio.play(scene_path, channel="ui")
                tts_found = True
        self._tts_playing = tts_found
        if not tts_found:
            # No TTS — use a timer based on text length (~3 frames per word)
            text = eng.text(lang)
            word_count = len(text.split()) if text else 0
            self._narrate_timer = 0
            self._narrate_timeout = max(60, word_count * 3)  # min ~2s

    def _check_tts_done(self):
        """Check if narration has finished (TTS or timer fallback).

        Manages the scene → choices → done sequence.
        Only meaningful during NARRATING or ENDING — skip otherwise.
        """
        if self._engine.state not in (NARRATING, ENDING):
            return

        if self._tts_playing:
            # Check if UI voice is still active
            if self._audio and self._audio._voices:
                from bodn.audio import V_UI

                ui_voice = self._audio._voices[V_UI]
                if ui_voice.source is not None:
                    return  # still playing
            # TTS phase finished
            if self._tts_phase == 0:
                # Scene done — try choices
                if self._tts_has_choices:
                    choices_path = self._resolve_story_tts(
                        self._engine.node_id, "_choices"
                    )
                    if choices_path:
                        self._tts_phase = 1
                        self._audio.play(choices_path, channel="ui")
                        return  # choices TTS started
                # No choices TTS or not applicable — done
                self._tts_phase = 2
                self._tts_playing = False
                self._engine.narration_done()
            elif self._tts_phase == 1:
                # Choices narration done
                self._tts_phase = 2
                self._tts_playing = False
                self._engine.narration_done()
        else:
            # Timer-based fallback
            self._narrate_timer += 1
            if self._narrate_timer >= self._narrate_timeout:
                self._engine.narration_done()

    def exit(self):
        # Stop any TTS still playing
        if self._audio:
            self._audio.stop("ui")
        neo.all_off()
        neo.clear_all_overrides()
        # Turn off arcade LEDs
        if self._arcade:
            self._arcade.all_off()
            self._arcade.flush()
        if self._on_exit:
            self._on_exit()

    def needs_redraw(self):
        return self._dirty or self._pause.needs_render

    def update(self, inp, frame):
        # Picker and end menu run without pause hold detection
        # (pause only applies during active story playback)
        if self._picker_mode:
            self._update_picker(inp, frame)
            return
        if self._end_menu:
            self._update_end_menu(inp, frame)
            return

        # Pause menu (only during active story)
        result = self._pause.update(inp, frame)
        if result == "quit" and self._manager:
            self._manager.pop()
            return
        elif result == "resume":
            self._dirty = True
            self._full_clear = True
        if self._pause.is_open or self._pause.is_holding:
            return

        # Engine update
        prev_state = self._engine.state
        now = time.ticks_ms()
        dt = time.ticks_diff(now, self._last_ms)
        self._last_ms = now
        self._engine.update(dt)

        # Handle state transitions (before TTS check so _start_narration
        # resets TTS state before _check_tts_done inspects it)
        state = self._engine.state
        if state != prev_state:
            self._prev_state = prev_state
            self._dirty = True
            self._full_clear = True
            self._leds_dirty = True

            if self._secondary:
                mood = self._engine.mood
                emotion = _MOOD_EMOTIONS.get(mood, NEUTRAL)
                if state == ENDING:
                    emotion = HAPPY
                self._secondary.set_emotion(emotion)

            # Start narration when entering a new scene (or ending)
            if prev_state == TRANSITIONING and state in (NARRATING, ENDING):
                self._cache_narration_sprites()
                self._start_narration()

            # Show end menu when story finishes
            if state == IDLE and prev_state == ENDING:
                self._end_menu = True
                self._cache_end_sprites()
                self._dirty = True
                self._full_clear = True
                self._leds_dirty = True
                return

        # Check TTS completion (after state transitions so _start_narration
        # has a chance to reset TTS state for new nodes)
        self._check_tts_done()

        # _check_tts_done may have changed state (NARRATING → CHOOSING,
        # or ENDING → handled).  Detect that transition here so the UI
        # gets _dirty / LED updates exactly like engine-driven transitions.
        new_state = self._engine.state
        if new_state != state:
            self._prev_state = state
            state = new_state
            self._dirty = True
            self._full_clear = True
            self._leds_dirty = True

            if self._secondary:
                mood = self._engine.mood
                emotion = _MOOD_EMOTIONS.get(mood, NEUTRAL)
                if state == ENDING:
                    emotion = HAPPY
                self._secondary.set_emotion(emotion)

        # Handle arcade input during CHOOSING
        if state == CHOOSING:
            arc = inp.first_arc_pressed() if hasattr(inp, "first_arc_pressed") else -1
            if arc < 0:
                # Also accept regular buttons as fallback
                btn = inp.first_btn_pressed()
                if 0 <= btn < self._engine.choice_count:
                    arc = btn
            if arc >= 0 and self._engine.choose(arc):
                self._dirty = True
                self._leds_dirty = True
                if self._audio:
                    self._audio.play_sound("select")

        # Brightness control
        prev_bri = self._brightness.value
        self._brightness.update(
            inp.enc_delta[config.ENC_A], inp.enc_velocity[config.ENC_A]
        )
        if self._brightness.value != prev_bri:
            self._leds_dirty = True

        # Update LEDs (NeoPixels only on dirty; arcade every frame for animation)
        if self._leds_dirty:
            self._leds_dirty = False
            self._update_leds(frame)
        elif self._arcade:
            self._update_arcade_leds(self._engine.state, frame)

    def _update_picker(self, inp, frame):
        """Handle story picker input."""
        if not self._stories:
            return
        delta = inp.enc_delta[NAV]
        if delta != 0:
            self._picker_index = (self._picker_index + delta) % len(self._stories)
            self._dirty = True

        # Accept nav encoder press, any mini button, or any arcade button
        arc = inp.first_arc_pressed() if hasattr(inp, "first_arc_pressed") else -1
        if inp.any_btn_pressed() or inp.enc_btn_pressed[NAV] or arc >= 0:
            # Play select sound on SFX channel (UI channel is reserved for narration)
            if self._audio:
                self._audio.play_sound("select", channel="sfx")
            self._load_story(self._picker_index)

    def _update_end_menu(self, inp, frame):
        """Handle post-story end menu input."""
        arc = inp.first_arc_pressed() if hasattr(inp, "first_arc_pressed") else -1
        if arc < 0:
            btn = inp.first_btn_pressed()
            if 0 <= btn <= 2:
                arc = btn

        if arc == _END_REPLAY:
            # Replay same story
            if self._audio:
                self._audio.play_sound("select")
            self._load_story(self._last_story_index)
        elif arc == _END_EXIT:
            # Exit story mode
            if self._audio:
                self._audio.play_sound("select")
            if self._manager:
                self._manager.pop()
        elif arc == _END_PICK and len(self._stories) > 1:
            # Go to story picker
            if self._audio:
                self._audio.play_sound("select")
            self._end_menu = False
            self._picker_mode = True
            self._dirty = True
            self._full_clear = True
            self._leds_dirty = True

        if not self._end_menu:
            return

        # LEDs: dim warm glow on sticks, lid off, arcade pulses on options
        if self._leds_dirty:
            self._leds_dirty = False
            brightness = self._brightness.value
            from bodn.patterns import N_STICKS, scale as _s

            c = _s((180, 120, 40), brightness // 4)
            for i in range(N_STICKS):
                neo.set_pixel(i, c[0], c[1], c[2])
            neo.zone_off(neo.ZONE_LID_RING)

        if self._arcade:
            n_options = 3 if len(self._stories) > 1 else 2
            for i in range(N_ARCADE):
                if i < n_options:
                    self._arcade.pulse(i, frame, speed=1)
                else:
                    self._arcade.off(i)
            self._arcade.flush()

    def _update_leds(self, frame):
        """Write NeoPixels and arcade LEDs."""
        brightness = self._brightness.value
        lid_bright = min(brightness, config.NEOPIXEL_LID_BRIGHTNESS)

        state = self._engine.state
        mood = self._engine.mood
        mood_rgb = MOOD_COLORS.get(mood, MOOD_COLORS["calm"])

        # Sticks: game feedback as pixel overrides
        leds = self._engine.make_static_leds(brightness)
        for i in range(16):
            r, g, b = leds[i]
            neo.set_pixel(i, r, g, b)

        # Lid ring: mood-based ambient
        if state == ENDING:
            neo.zone_pattern(
                neo.ZONE_LID_RING, neo.PAT_RAINBOW, speed=2, brightness=lid_bright
            )
        elif state == CHOOSING:
            neo.zone_pattern(
                neo.ZONE_LID_RING,
                neo.PAT_PULSE,
                speed=1,
                colour=mood_rgb,
                brightness=lid_bright,
            )
        elif state == NARRATING:
            neo.zone_pattern(
                neo.ZONE_LID_RING,
                neo.PAT_FILL,
                colour=mood_rgb,
                brightness=lid_bright,
            )
        else:
            neo.zone_off(neo.ZONE_LID_RING)

        # Arcade LEDs (animated — also called standalone between dirty frames)
        if self._arcade:
            self._update_arcade_leds(state, frame)

    def _update_arcade_leds(self, state, frame):
        """Update arcade button LEDs. Called every frame for smooth animation."""
        if state == CHOOSING:
            for i in range(N_ARCADE):
                if i < self._engine.choice_count:
                    self._arcade.pulse(i, frame, speed=1)
                else:
                    self._arcade.off(i)
        elif state == NARRATING:
            self._arcade.wave(frame, speed=1)
        elif state == ENDING:
            self._arcade.wave(frame, speed=2)
        else:
            self._arcade.all_off()
        self._arcade.flush()

    def render(self, tft, theme, frame):
        if self._pause.is_open:
            if self._dirty:
                self._dirty = False
                tft.fill(theme.BLACK)
                self._full_clear = False
            self._pause.render(tft, theme, frame)
            return

        if self._dirty:
            self._dirty = False
            if self._full_clear:
                self._full_clear = False
                tft.fill(theme.BLACK)

            if self._picker_mode:
                self._render_picker(tft, theme, frame)
            elif self._end_menu:
                self._render_end_menu(tft, theme, frame)
            else:
                self._render_story(tft, theme, frame)

        self._pause.render(tft, theme, frame)

    def _render_picker(self, tft, theme, frame):
        """Render the story selection screen."""
        w = theme.width
        h = theme.height

        blit_centered(tft, self._spr["title2"], 16, w)

        if not self._stories:
            draw_centered(tft, t("story_no_stories"), h // 2, theme.MUTED, w)
            return

        # Show current story title (from cache — loaded during enter())
        sid, path = self._stories[self._picker_index]
        titles = self._story_titles.get(sid, {})
        title = titles.get(get_language(), titles.get("en", sid))

        # Clear title + dots region before redrawing
        title_y = h // 2 - 8
        tft.fill_rect(0, title_y, w, 16, theme.BLACK)
        # Picker titles are dynamic — build sprite on demand
        spr = make_label_sprite(title, theme.WHITE, scale=2)
        blit_centered(tft, spr, title_y, w)

        # Dots
        n = len(self._stories)
        if n > 1:
            dot_y = h // 2 + 30
            tft.fill_rect(0, dot_y - 3, w, 6, theme.BLACK)
            gap = 12
            total_w = n * gap
            x0 = (w - total_w) // 2
            for i in range(n):
                cx = x0 + i * gap + 3
                if i == self._picker_index:
                    tft.fill_rect(cx - 3, dot_y - 3, 6, 6, theme.CYAN)
                else:
                    tft.rect(cx - 3, dot_y - 3, 6, 6, theme.DIM)

        draw_centered(tft, t("story_press_start"), h - 30, theme.MUTED, w)

    def _render_end_menu(self, tft, theme, frame):
        """Render the post-story choice screen."""
        w = theme.width
        h = theme.height

        # Title
        blit_centered(tft, self._spr["the_end3"], 30, w)

        # Options with arcade button colour dots
        n_options = 3 if len(self._stories) > 1 else 2
        y0 = h // 2 - n_options * 12
        for i in range(n_options):
            y = y0 + i * 28
            if _ARC_565 and i < len(_ARC_565):
                tft.fill_rect(40, y + 2, 12, 12, _ARC_565[i])
            if i < len(self._end_sprites):
                blit_sprite(tft, self._end_sprites[i], 60, y)

    def _render_story(self, tft, theme, frame):
        """Render the active story scene."""
        w = theme.width
        h = theme.height
        eng = self._engine
        state = eng.state
        lang = get_language()

        if state == IDLE:
            blit_centered(tft, self._spr["title_muted"], h // 2, w)
            return

        # --- Top: mood colour wash ---
        mood = eng.mood
        wash_color = _MOOD_565.get(mood, _MOOD_565.get("calm", theme.DIM))
        wash_h = 100
        tft.fill_rect(0, 0, w, wash_h, wash_color)

        # Progress dots on the wash
        n_visited = eng.progress
        dot_y = wash_h - 12
        dot_gap = 10
        max_dots = min(n_visited, w // dot_gap)
        dot_x0 = (w - max_dots * dot_gap) // 2
        for i in range(max_dots):
            cx = dot_x0 + i * dot_gap + 3
            tft.fill_rect(cx - 2, dot_y - 2, 4, 4, theme.WHITE)

        # --- Middle: narration text (pre-rendered sprites) ---
        text_y = wash_h + 8
        for i, spr in enumerate(self._narr_sprites):
            blit_centered(tft, spr, text_y + i * 20, w)

        # --- Bottom: choices or status ---
        choice_y = h - 56

        if state == NARRATING:
            # Listening indicator
            key = "dots3" if (frame // 15) % 2 == 0 else "dots2"
            blit_centered(tft, self._spr[key], choice_y + 20, w)

        elif state == CHOOSING:
            # Show choices with arcade button colour indicators (scale=1, no sprites needed)
            choices = eng.choices
            for i, ch in enumerate(choices):
                if i >= N_ARCADE:
                    break
                label = ch.get("label", {})
                text = label.get(lang, label.get("en", "?"))
                y = choice_y + i * 14
                # Colour dot
                if _ARC_565 and i < len(_ARC_565):
                    tft.fill_rect(8, y + 1, 8, 8, _ARC_565[i])
                # Label (scale=1 — already fast)
                draw_label(tft, text, 20, y, theme.WHITE)

        elif state == ENDING:
            blit_centered(tft, self._spr["the_end2"], choice_y + 10, w)

        elif state == TRANSITIONING:
            blit_centered(tft, self._spr["trans"], choice_y + 20, w)
