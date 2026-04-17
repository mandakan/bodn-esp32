---
name: tts-pipeline
description: Generate, convert, and sync Piper TTS audio for i18n strings and story narration. Use when adding or changing i18n keys on the TTS allowlist, authoring/editing story scripts, adding hand-recorded overrides, or when the device is missing spoken prompts. Covers generate_tts.py, generate_story_tts.py, convert_audio.py, and sd-sync.py.
---

# TTS pipeline

Two offline TTS pipelines feed the device, both powered by Piper TTS. Audio
always goes through `bodn.assets.resolve_voice()` at runtime — SD first, flash
fallback, with hand-recordings shadowing TTS at each layer.

Install Piper once: `pip install piper-tts`.

## i18n TTS (game instructions, system alerts)

Source: `STRINGS` dicts in `firmware/bodn/lang/{sv,en}.py`.
Allowlist + voice config: `assets/audio/tts.json`.

- **Flash keys** (safety-critical, must work without SD):
  `bat_critical`, `bat_low`, `overlay_goodnight`.
  Output: `assets/audio/source/tts/{lang}/` → `firmware/sounds/tts/`.
- **SD keys** (game-mode-specific): stage in `build/tts/` → `build/tts_converted/`.

```bash
uv run python tools/generate_tts.py                  # all keys, all languages
uv run python tools/generate_tts.py --dry-run        # preview
uv run python tools/generate_tts.py --lang sv        # Swedish only
uv run python tools/generate_tts.py --key simon_watch  # single key
```

Runtime lookup: `from bodn.tts import say; say("simon_watch")`.

## Story TTS (narration + choice labels)

Source: `assets/stories/*/script.py`.
Output: `build/story_tts_raw/{story_id}/{lang}/` → packaged into
`build/stories/{story_id}/` (`script.py` + `tts/{lang}/*.wav`).

```bash
uv run python tools/generate_story_tts.py
uv run python tools/generate_story_tts.py --dry-run
uv run python tools/generate_story_tts.py --story peter_rabbit
```

Runtime lookup inside `bodn/ui/story.py`:
`/stories/{id}/tts/{lang}/{node}.wav`.

## Hand-recorded overrides

Any TTS line can be replaced with a human recording — no code change needed.

- i18n: `assets/audio/source/recordings/{lang}/{key}.wav`
- Story: `assets/stories/{id}/recordings/{lang}/{node}.wav`
  (use the `_choices` suffix for choice narration)

Filenames must match the TTS key/node **exactly**. `convert_audio.py`
normalises the recording to 16 kHz mono PCM with loudnorm (same as TTS) into
`build/sounds/recordings/…` or `build/stories/{id}/recordings/…`.

**Footgun:** if the source text changes after recording, the old recording
silently shadows the regenerated TTS. Delete or re-record the affected file.

## Full pipeline: generate → convert → sync to SD

```bash
uv run python tools/generate_tts.py                  # 1. i18n TTS
uv run python tools/generate_story_tts.py            # 2. story TTS
uv run python tools/convert_audio.py                 # 3. device format (16 kHz mono PCM)
uv run python tools/sd-sync.py /Volumes/BODN_SD      # 4. copy to card
```

`tools/sd-sync.py` runs steps 1–3 internally; `--no-build` skips regeneration,
`--build-only` skips the copy.

## Invariants

- Add new i18n strings to **both** `sv.py` and `en.py` (the `test_i18n.py`
  parity test enforces this).
- Only allowlisted keys in `assets/audio/tts.json` get TTS generated. Add the
  key there if you want spoken output.
- Swedish is the default language; English is the secondary.
- Flash TTS is reserved for safety-critical prompts. Put game-mode prompts on SD.
