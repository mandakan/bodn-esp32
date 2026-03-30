# bodn/story_rules.py — Story Mode rule engine (pure logic, testable on host)
#
# Data-driven branching narrative engine.  Stories are defined as Python
# dicts (directed graphs of nodes), loaded from SD or flash.  The engine
# manages state transitions; the screen handles display, audio, and LEDs.
#
# Targets ages 3-5:
#   Listening comprehension — must listen to narration to choose
#   Bilingual exposure       — every node has sv + en text
#   Imaginative play         — child steers the narrative
#   Working memory           — recall earlier scenes to inform choices
#
# No fail state — every branch leads somewhere interesting.

from micropython import const
from bodn.patterns import N_STICKS, scale, _led_buf

# --- States ---
IDLE = const(0)  # no story loaded / back at picker
NARRATING = const(1)  # TTS playing scene narration
CHOOSING = const(2)  # choices lit, waiting for arcade press
TRANSITIONING = const(3)  # brief pause between scenes
ENDING = const(4)  # terminal node reached, celebration

# Timing (frames, ~30 fps)
TRANSITION_FRAMES = const(20)  # ~0.7s between scenes
ENDING_FRAMES = const(120)  # ~4s celebration before returning to idle

# --- Mood palette (RGB tuples for stick LEDs) ---
MOOD_COLORS = {
    "warm": (255, 160, 40),
    "tense": (200, 40, 0),
    "happy": (40, 255, 80),
    "wonder": (60, 40, 200),
    "calm": (80, 80, 80),
}

# Arcade button hardware colours (matching config: green, blue, white, yellow, red)
ARC_COLORS = [
    (0, 220, 50),  # 0 green
    (0, 80, 255),  # 1 blue
    (220, 220, 220),  # 2 white
    (255, 200, 0),  # 3 yellow
    (255, 30, 0),  # 4 red
]

MAX_CHOICES = const(5)


def validate_story(story):
    """Check a story dict for structural issues.

    Returns a list of error strings (empty = valid).
    """
    errors = []
    if "id" not in story:
        errors.append("missing 'id'")
    if "start" not in story:
        errors.append("missing 'start'")
    nodes = story.get("nodes", {})
    if not nodes:
        errors.append("no nodes defined")
        return errors

    start = story.get("start")
    if start and start not in nodes:
        errors.append("start node '{}' not in nodes".format(start))

    for nid, node in nodes.items():
        if "text" not in node:
            errors.append("node '{}': missing 'text'".format(nid))
        choices = node.get("choices")
        if choices:
            if len(choices) > MAX_CHOICES:
                errors.append(
                    "node '{}': {} choices exceeds max {}".format(
                        nid, len(choices), MAX_CHOICES
                    )
                )
            for i, ch in enumerate(choices):
                if "next" not in ch:
                    errors.append("node '{}' choice {}: missing 'next'".format(nid, i))
                elif ch["next"] not in nodes:
                    errors.append(
                        "node '{}' choice {}: target '{}' not in nodes".format(
                            nid, i, ch["next"]
                        )
                    )
                if "label" not in ch:
                    errors.append("node '{}' choice {}: missing 'label'".format(nid, i))
        elif not node.get("ending"):
            errors.append("node '{}': no choices and not an ending".format(nid))

    return errors


def find_endings(story):
    """Return a list of node IDs that are endings."""
    return [nid for nid, node in story.get("nodes", {}).items() if node.get("ending")]


def reachable_nodes(story):
    """Return set of node IDs reachable from start via BFS."""
    start = story.get("start")
    nodes = story.get("nodes", {})
    if not start or start not in nodes:
        return set()
    visited = set()
    queue = [start]
    while queue:
        nid = queue.pop(0)
        if nid in visited:
            continue
        visited.add(nid)
        node = nodes.get(nid, {})
        for ch in node.get("choices", []):
            target = ch.get("next")
            if target and target not in visited:
                queue.append(target)
    return visited


class StoryEngine:
    """Stateful engine for Story Mode.

    Pure logic -- no hardware imports beyond patterns.
    Feed it arcade button presses and read back the current state.
    The screen is responsible for playing TTS audio and checking
    when narration finishes.
    """

    def __init__(self):
        self.state = IDLE
        self.story = None
        self.node_id = None
        self.node = None
        self.visited = []  # ordered list of visited node IDs
        self.ending_type = None
        self._state_frame = 0
        self._choice_count = 0

    def load(self, story):
        """Load a story dict and move to the start node.

        Returns list of validation errors (empty = OK, engine ready).
        """
        errors = validate_story(story)
        if errors:
            self.state = IDLE
            return errors
        self.story = story
        self._go_to_node(story["start"], 0)
        return []

    def reset(self):
        """Reset engine to IDLE (no story loaded)."""
        self.state = IDLE
        self.story = None
        self.node_id = None
        self.node = None
        self.visited = []
        self.ending_type = None
        self._choice_count = 0

    def _go_to_node(self, node_id, frame):
        """Set current node and determine state."""
        nodes = self.story["nodes"]
        self.node_id = node_id
        self.node = nodes[node_id]
        self.visited.append(node_id)

        if self.node.get("ending"):
            self.state = ENDING
            self.ending_type = self.node.get("ending_type", "gentle")
        else:
            self.state = NARRATING

        choices = self.node.get("choices", [])
        self._choice_count = len(choices)
        self._state_frame = frame

    @property
    def mood(self):
        """Current node's mood string (default 'calm')."""
        if self.node:
            return self.node.get("mood", "calm")
        return "calm"

    @property
    def choices(self):
        """Current node's choices list (empty if ending/narrating)."""
        if self.node and self.state in (NARRATING, CHOOSING):
            return self.node.get("choices", [])
        return []

    @property
    def choice_count(self):
        """Number of choices at current node."""
        return self._choice_count

    @property
    def narrate_choices(self):
        """Whether TTS should read choice labels aloud."""
        if self.story:
            return self.story.get("narrate_choices", True)
        return True

    @property
    def story_id(self):
        if self.story:
            return self.story.get("id", "unknown")
        return None

    @property
    def story_title(self, lang=None):
        """Return story title dict {sv: ..., en: ...} or None."""
        if self.story:
            return self.story.get("title")
        return None

    @property
    def progress(self):
        """Number of nodes visited so far."""
        return len(self.visited)

    @staticmethod
    def _strip_pause(s):
        """Remove {pause} / {pause N} markers (TTS-only hints)."""
        if "{pause" not in s:
            return s
        import re

        return re.sub(r"\{pause(?:\s+[\d.]+)?\}\s*", "", s)

    def text(self, lang):
        """Return narration text for current node in the given language."""
        if not self.node:
            return ""
        t = self.node.get("text", {})
        return self._strip_pause(t.get(lang, t.get("en", "")))

    def choice_label(self, index, lang):
        """Return choice label for given index and language."""
        choices = self.choices
        if index < 0 or index >= len(choices):
            return ""
        label = choices[index].get("label", {})
        return label.get(lang, label.get("en", ""))

    def narration_done(self, frame):
        """Called by the screen when TTS narration finishes.

        Transitions from NARRATING to CHOOSING (or ENDING if
        this is an ending node with narration).
        """
        if self.state == NARRATING:
            if self._choice_count > 0:
                self.state = CHOOSING
                self._state_frame = frame
            # If no choices (shouldn't happen for non-endings), stay

    def choose(self, arc_index, frame):
        """Handle an arcade button press during CHOOSING.

        arc_index: 0-4 (arcade button index, maps 1:1 to choice index).
        Returns True if the choice was valid, False otherwise.
        """
        if self.state != CHOOSING:
            return False
        if arc_index < 0 or arc_index >= self._choice_count:
            return False

        choices = self.node.get("choices", [])
        target = choices[arc_index]["next"]
        self.state = TRANSITIONING
        self._state_frame = frame
        self._pending_target = target
        return True

    def update(self, frame):
        """Called every frame. Handles timed transitions.

        Returns the current state.
        """
        elapsed = frame - self._state_frame

        if self.state == TRANSITIONING:
            if elapsed >= TRANSITION_FRAMES:
                self._go_to_node(self._pending_target, frame)
        elif self.state == ENDING:
            if elapsed >= ENDING_FRAMES:
                self.state = IDLE
                self._state_frame = frame

        return self.state

    # ------------------------------------------------------------------
    # LED generation (sticks only -- lid ring handled by screen)
    # ------------------------------------------------------------------

    def make_static_leds(self, brightness=128):
        """Generate LED colors for sticks based on current mood/state."""
        buf = _led_buf
        n = N_STICKS
        _s = scale

        mood = self.mood
        color = MOOD_COLORS.get(mood, MOOD_COLORS["calm"])

        if self.state == IDLE:
            # Dim warm glow
            c = _s((180, 120, 40), brightness // 4)
            for i in range(n):
                buf[i] = c
            return buf

        if self.state == ENDING:
            # Bright celebration -- cycle through happy colours
            c = _s(MOOD_COLORS["happy"], brightness)
            for i in range(n):
                buf[i] = c
            return buf

        if self.state == CHOOSING:
            # Dim mood on sticks; arcade LEDs handled by screen
            c = _s(color, brightness // 6)
            for i in range(n):
                buf[i] = c
            return buf

        # NARRATING or TRANSITIONING: mood colour at medium brightness
        c = _s(color, brightness // 3)
        for i in range(n):
            buf[i] = c
        return buf
