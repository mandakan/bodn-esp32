---
name: add-i18n-string
description: Add a new user-facing string to the Bodn i18n system. Use whenever a screen or flow needs new display text — never hardcode UI text in screen modules. Keeps sv.py and en.py in parity (enforced by test_i18n.py) and flags when the key needs a TTS regeneration.
---

# Add an i18n string

All user-facing UI text goes through `bodn/i18n.py`. Screen modules call
`t("key")` or `t("key", arg)`; they must never contain hardcoded display
strings.

## Steps

1. **Pick a key** using the `screen_concept` convention
   (e.g. `simon_watch`, `pause_resume`, `flode_win`).
2. **Add to both language files** — the `test_i18n.py` parity test fails
   otherwise:
   - `firmware/bodn/lang/sv.py` (Swedish — default)
   - `firmware/bodn/lang/en.py`
3. **Use it in the screen module**:
   ```python
   from bodn.i18n import t
   draw_label(t("simon_watch"))
   draw_label(t("rakna_score", points))
   ```
4. **Capitalisation**: MicroPython `str` lacks `.capitalize()`, `.title()`,
   `.swapcase()`, `.casefold()`. If you need case changes, use
   `from bodn.i18n import capitalize`. The compat tests in
   `tests/test_micropython_compat.py` catch CPython-only APIs before they
   hit the device.
5. **Extended glyphs**: å, ä, ö, Å, Ä, Ö are provided by
   `bodn/ui/font_ext.py`. Any other non-ASCII glyph needs a font extension.

## TTS follow-up

If the key should be spoken:

1. Add it to the allowlist in `assets/audio/tts.json`.
2. Decide between **flash** (safety-critical: `bat_critical`, `bat_low`,
   `overlay_goodnight`) and **SD** (everything else).
3. Run the `tts-pipeline` skill to generate, convert, and sync the audio.

## Verification

```bash
uv run pytest tests/test_i18n.py              # key parity
uv run pytest tests/test_micropython_compat.py  # CPython-only API check
```

## Scope note

The web UI (`bodn/web_ui.py`) stays in English — it is parent-facing and not
routed through the i18n layer.
