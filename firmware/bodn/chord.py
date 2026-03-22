"""Chord / multi-button combo detection.

Recognises "hold modifier(s), press trigger" patterns so screens can
bind advanced actions to button combinations without polluting the
primary single-button UX.

Pure logic — no hardware deps, testable on host with pytest.
"""


class ChordDetector:
    """Detect multi-button chord combos from held + just-pressed state.

    Usage::

        chords = ChordDetector({
            (0, 7): "secret_menu",   # hold btn 0, press btn 7
            (1, 2): "skip_level",    # hold btn 1, press btn 2
            (0, 1, 7): "debug",      # hold btn 0+1, press btn 7
        })

        fired = chords.update(inp.btn_held, inp.btn_just_pressed)
        if fired:
            handle(fired)

    Each combo tuple has one or more modifier indices (all but last) that
    must be *held*, and a trigger index (last element) that must be
    *just pressed* this frame.  Longer modifier lists take priority over
    shorter ones when multiple combos share the same trigger.
    """

    def __init__(self, combos):
        # combos: dict mapping tuple(int...) -> action
        # Build lookup: trigger -> list of (frozen_modifiers, action)
        # sorted longest-modifier-first for greedy matching.
        self._by_trigger = {}
        self._suppressed = []  # pre-allocated list for suppress indices
        for keys, action in combos.items():
            if len(keys) < 2:
                raise ValueError(
                    "combo must have at least one modifier and one trigger"
                )
            trigger = keys[-1]
            modifiers = frozenset(keys[:-1])
            if trigger in self._by_trigger:
                self._by_trigger[trigger].append((modifiers, action))
            else:
                self._by_trigger[trigger] = [(modifiers, action)]
        # Sort each trigger's entries longest-first (greedy match).
        for entries in self._by_trigger.values():
            entries.sort(key=lambda e: len(e[0]), reverse=True)

    def update(self, held, just_pressed):
        """Check for chord matches this frame.

        Args:
            held: list/array of bool — button held state per channel.
            just_pressed: list/array of bool — rising edge per channel.

        Returns:
            The action value of the first matched chord, or *None*.
            Also populates ``suppressed`` with trigger indices that
            should have their tap gesture consumed.
        """
        self._suppressed.clear()
        for trigger, entries in self._by_trigger.items():
            if not just_pressed[trigger]:
                continue
            for modifiers, action in entries:
                if all(held[m] for m in modifiers):
                    self._suppressed.append(trigger)
                    return action
        return None

    @property
    def suppressed(self):
        """Trigger button indices suppressed by the last ``update()``.

        Screens should clear the corresponding ``tap`` flag in the
        gesture detector so the trigger press isn't also handled as a
        normal tap::

            fired = chords.update(inp.btn_held, inp.btn_just_pressed)
            for idx in chords.suppressed:
                inp.gestures.tap[idx] = False
        """
        return self._suppressed
