---
name: add-game-mode
description: Update the developmental-science documentation when adding or significantly changing a Bodn game mode. Use when introducing a new mode (e.g. a new rules/*.py engine and ui/*.py screen), or when an existing mode gains new mechanics that change its developmental coverage. Touches development_matrix.md, development_guide.md, report.tex, and rebuilds report.pdf.
---

# Add / update a game mode

Every Bodn game mode is mapped to developmental domains (working memory,
inhibition, cognitive flexibility, etc.) in `docs/science/`. When you add or
meaningfully change a mode, keep the science docs in sync so coverage
analysis stays accurate.

## Checklist

1. **`docs/science/development_matrix.md`**
   - Add (or update) the feature's row in each aspect table.
   - Revise the coverage/gap analysis if the balance of domains shifts.

2. **`docs/science/development_guide.md`**
   - Only edit if the feature introduces or strengthens a developmental
     domain not yet covered. Add a paragraph explaining it.

3. **`docs/science/report.tex`**
   - Add or update the feature's `\subsubsection{}` in §4.1
     (Feature–Domain Mapping).
   - Add or update the feature's column in the coverage table (Table 1).
   - Mark any new `[TODO]` sections for later expansion.

4. **Rebuild the PDF**
   ```bash
   docs/science/build.sh
   ```
   Commit `report.pdf` alongside the `.tex` and `.md` changes.

## Typical code surfaces for a new mode

- `firmware/bodn/<mode>_rules.py` — pure-logic engine (host-testable with
  pytest).
- `firmware/bodn/ui/<mode>.py` — screen subclass wiring the engine to
  displays, inputs, audio, and LEDs.
- `firmware/bodn/ui/home.py` — register the mode in the carousel.
- i18n strings: add to **both** `firmware/bodn/lang/sv.py` and `en.py`
  (see the `add-i18n-string` skill).
- TTS: if the mode needs spoken prompts, allowlist the keys in
  `assets/audio/tts.json` and run the `tts-pipeline` skill.

## UX + performance reminders

- Target a 4-year-old: one concept per screen, large icons, max 3–4 active
  choices, immediate multimodal feedback. Follow `docs/UX_GUIDELINES.md`.
- Event-driven over polling; no full-screen redraws every frame.
  Game/timing state belongs in `update()`, never `render()`. Section-level
  dirty bitmasks, not a single `_dirty` flag, for multi-region screens.
  See the `perf-review` skill and `docs/PERFORMANCE_GUIDELINES.md`.
