---
name: add-story
description: Author a new branching narrative for Story Mode, or add recorded narration to an existing one. Use when writing a new story script, porting a public-domain tale, or replacing Piper TTS lines with human recordings. Covers the script.py schema, TTS generation, hand-recorded overrides, and the SD package layout the device expects.
---

# Add a story

Story Mode is a data-driven branching narrative engine. Each story is a
self-contained package on the SD card: one `script.py` describing nodes
and choices, plus pre-generated (or hand-recorded) audio per node per
language. The device discovers stories by scanning `/sd/stories/*/` at
startup.

## Directory layout

```
assets/stories/<story_id>/
├─ script.py                            # STORY dict (authoritative)
└─ recordings/
   └─ {sv,en}/
      ├─ <node_id>.wav                  # hand-recorded narration (optional)
      └─ <node_id>_choices.wav           # hand-recorded choice prompts (optional)

build/stories/<story_id>/                # assembled by convert_audio.py
├─ script.py                             # copied as-is
├─ tts/{sv,en}/<node_id>.wav             # 16 kHz mono PCM
├─ tts/{sv,en}/<node_id>_choices.wav
└─ recordings/{sv,en}/...                # normalised recordings (if any)
```

`sd-sync.py` copies `build/stories/` to `/sd/stories/`. The device resolves
audio as `recording > TTS` within each storage layer (SD first, flash
second).

## script.py schema

```python
STORY = {
    "id": "peter_rabbit",                # unique; becomes directory name
    "version": 1,
    "title": {"sv": "Pelle Kanin", "en": "Peter Rabbit"},
    "author": "Beatrix Potter",          # optional — credit public-domain sources
    "age_min": 3,
    "age_max": 6,
    "estimated_minutes": 4,
    "narrate_choices": True,             # speak "press green to…" between scenes
    "start": "home",                     # node id to begin at
    "nodes": {
        "home": {
            "text": {
                "sv": "Pelle Kanin bodde...",
                "en": "Peter Rabbit lived...",
            },
            "mood": "warm",              # warm|happy|wonder|tense|scary|…
            "choices": [
                {"label": {"sv": "Gå till trädgården",
                           "en": "Go to the garden"},
                 "next": "garden_gate"},
                {"label": {"sv": "Plocka bär",
                           "en": "Pick berries"},
                 "next": "berries"},
            ],
        },
        "berry_end": {
            "text": {"sv": "...", "en": "..."},
            "mood": "happy",
            "ending": True,              # terminal node
            "ending_type": "happy",
        },
        # ...
    },
}
```

- **`nodes`** is a flat dict — no nesting. `choices[].next` references
  another node id; ending nodes set `ending: True`.
- **`mood`** drives a colour wash on the top third of the primary display
  and a palette for LEDs. Re-use existing values before inventing new ones.
- **`narrate_choices`** toggles whether the TTS pipeline also generates a
  `<node>_choices.wav` that reads the choice prompts aloud (arcade-button
  colour names are injected in the user's language).
- **Keep nodes short** (1–3 sentences for 3–5-year-olds). `{pause}` or
  `{pause 1.2}` markers insert silence for dramatic effect. See the Peter
  Rabbit sample.
- **Public-domain sources only** unless you've cleared the rights. Credit
  the original author in `author`.

## Authoring workflow

1. Create `assets/stories/<story_id>/script.py` with the STORY dict.
2. Preview the structure in a terminal:
   ```bash
   uv run python tools/story_preview.py <story_id>
   ```
3. Generate TTS audio:
   ```bash
   uv run python tools/generate_story_tts.py --story <story_id>
   uv run python tools/generate_story_tts.py --dry-run       # preview
   uv run python tools/generate_story_tts.py                  # all stories
   ```
   Output: `build/story_tts_raw/<story_id>/{sv,en}/*.wav` at Piper's
   native sample rate.
4. Convert to device format (16 kHz mono PCM) and assemble the package:
   ```bash
   uv run python tools/convert_audio.py
   ```
   This also copies `script.py` into `build/stories/<story_id>/`.
5. Sync to SD:
   ```bash
   uv run python tools/sd-sync.py /Volumes/BODN_SD
   ```
   (`sd-sync.py` runs steps 3–4 internally; use `--no-build` to skip.)
6. On the device, Story Mode's picker auto-discovers the new story —
   no registration code needed.

## Hand-recorded narration

Any node can be replaced by a human recording, per language, without
touching the script. Drop a WAV at:

```
assets/stories/<story_id>/recordings/{sv,en}/<node_id>.wav
assets/stories/<story_id>/recordings/{sv,en}/<node_id>_choices.wav
```

Filenames must match the node id exactly. `convert_audio.py` normalises
the recording to 16 kHz mono PCM with the same `loudnorm` filter as the
TTS pipeline, so levels stay consistent. Coverage is incremental — record
one node, the rest stay on TTS.

**Footgun**: if you change `text` in the script after recording, the old
recording silently shadows the regenerated TTS. Delete or re-record the
affected file.

## Tuning prose for TTS

Piper reads punctuation literally; short sentences sound better than long
ones. Defaults in `tools/generate_story_tts.py`:

- `length_scale = 1.2` (gentle storytelling pace)
- `0.4 s` silence between sentences
- `0.8 s` silence at `{pause}` markers

Override per story by adding `prosody` keys to the STORY dict only if a
story needs a different feel.

## Invariants

- **Node ids stable once released.** Renaming a node invalidates any
  hand-recording using the old filename.
- **`id` matches directory name** — both firmware discovery and the TTS
  pipeline rely on it.
- **Every node appears in `nodes`** — a dangling `next` reference will
  dead-end the playthrough. The story engine does not auto-validate.
- **Bilingual parity**: every node must supply both `sv` and `en` `text`
  and labels. Story Mode picks the active UI language at runtime.
- Public-domain vocabulary only. Keep sentences short, concrete, and age
  3–5 friendly; follow `docs/UX_GUIDELINES.md`.
- If Story Mode gets new mechanics (timer, inventory, multi-choice
  combos), run the `add-game-mode` skill to update `docs/science/`.
