# Audio asset management

This document covers how audio files are sourced, converted, deployed, and
referenced in code. Read this before adding any new sounds.

## Overview

There are six categories of audio:

| Category | What it is | Triggered by | Storage |
|---|---|---|---|
| **Soundboard** | One WAV per button slot | Child pressing a button | SD |
| **SFX** | Short named clips for game/UI events | Code (`audio.play(WAV["sfx"]["..."])`) | Flash |
| **Music** | Background loops | Code (`audio.play(WAV["music"]["..."], loop=True)`) | SD |
| **Drum kits** | Named percussion samples for the Sequencer mode | Sequencer engine step trigger / arcade button press | SD |
| **i18n TTS** | Spoken game instructions and system alerts | `tts.say(key, audio)` | Flash (safety) / SD (game) |
| **Story TTS** | Narration and choice labels for Story Mode | `tts.say(key, audio)` | SD |

There is a seventh category not in the table — **procedural tones** — which are synthesised at runtime from note sequences defined in `firmware/bodn/sounds.py` (`SOUNDS` dict). Those do not go through the asset pipeline.

---

## Directory layout

```
assets/audio/                        ← source side (this repo)
  soundboard.json                    ← single source of truth (see below)
  kits.json                          ← drum kit manifest for Sequencer mode (see below)
  sources.tsv                        ← attribution / license log
  source/
    soundboard/                      ← original downloaded files, any format
    soundboard/arcade/               ← arcade button source files
    sfx/                             ← source SFX files, renamed to logical names
    music/                           ← source music files, renamed to logical names

firmware/sounds/                     ← flash (this repo, committed)
  sfx/                               ← UI feedback SFX (click, confirm, error)
  tts/{sv,en}/                       ← critical TTS (battery warnings, goodnight)
  manifest.json                      ← generated soundboard labels — never edit by hand

build/                               ← SD-bound (generated, not committed)
  sounds/
    bank_0/ … bank_3/                ← converted soundboard WAVs (0.wav – 7.wav)
    arcade/                          ← converted arcade WAVs (0.wav – 4.wav)
    kits/                            ← converted drum kit WAVs (one subdirectory per kit)
      basic/                         ← starter kit (kick, snare, hihat, tom, crash)
    music/                           ← converted music WAVs
  tts/{sv,en}/                       ← i18n TTS staging (from generate_tts.py)
  story_tts/{sv,en}/                 ← story TTS staging (from generate_story_tts.py)
  tts_converted/{sv,en}/             ← final converted TTS (i18n + story merged)
```

`firmware/sounds/` (flash) is committed so deploying to a fresh device requires no build step — UI SFX and safety TTS are always available. Soundboard, arcade, and music are SD-only; run `tools/sd-sync.py` to build and copy them to the card. Source files in `assets/audio/source/` are **gitignored for CC0 downloads** (they are re-fetchable from `sources.tsv`) — commit your own recordings directly or via git-lfs.

---

## Tools

### `tools/import_freesound.py`

Parses a Freesound bookmark-category license `.txt` file. Appends new entries to `sources.tsv` and prints ready-to-paste JSON stubs for `soundboard.json`.

```bash
uv run python tools/import_freesound.py path/to/license.txt
uv run python tools/import_freesound.py path/to/license.txt --dry-run    # preview only
uv run python tools/import_freesound.py path/to/license.txt --stubs-only # reprint stubs
```

Running it repeatedly is safe — it deduplicates by URL.

### `tools/convert_audio.py`

Batch-converts all source files to device format (16 kHz, mono, 16-bit PCM WAV) and regenerates `firmware/sounds/manifest.json` from `soundboard.json`. Processes six categories:

| Category | Source | Output | Target |
|---|---|---|---|
| Soundboard | `assets/audio/source/soundboard/` | `build/sounds/bank_*/` | SD |
| Arcade | `assets/audio/source/soundboard/` | `build/sounds/arcade/` | SD |
| **Drum kits** | `assets/audio/source/` (paths from `kits.json`) | `build/sounds/kits/{kit_name}/` | SD |
| SFX | `assets/audio/source/sfx/` | `firmware/sounds/sfx/` | Flash |
| Music | `assets/audio/source/music/` | `build/sounds/music/` | SD |
| Flash TTS | `assets/audio/source/tts/` | `firmware/sounds/tts/` | Flash |
| SD TTS (i18n) | `build/tts/` | `build/tts_converted/` | SD |
| Story TTS | `build/story_tts/` | `build/tts_converted/` | SD |

```bash
uv run python tools/convert_audio.py             # convert everything
uv run python tools/convert_audio.py --dry-run   # show what would run
uv run python tools/convert_audio.py --force     # reconvert regardless of mtime
```

Requires `ffmpeg` (`brew install ffmpeg`).

### `tools/generate_story_tts.py`

Generates TTS narration for Story Mode. Discovers stories from `assets/stories/*/script.py`
and the built-in flash story, extracts per-node text and choice labels, and generates WAVs
via Piper TTS with storytelling prosody (slower pace, sentence pauses).

Output: `build/story_tts/{lang}/story_{id}_{node}.wav` (+ `_choices.wav` variants).
Converted to `build/tts_converted/` by `convert_audio.py`, then synced to SD card.

```bash
uv run python tools/generate_story_tts.py                # generate all
uv run python tools/generate_story_tts.py --dry-run      # preview
uv run python tools/generate_story_tts.py --story forest_walk  # single story
uv run python tools/generate_story_tts.py --lang sv       # single language
```

---

## Adding new sounds

### Step 1 — import the license file

```bash
uv run python tools/import_freesound.py ~/Downloads/SFX\ Banks.txt
```

This updates `sources.tsv` and prints stubs like:

```
── Soundboard stubs (3 unassigned) ──────────────────────────
        "N": {"sv": "", "en": "", "source": "soundboard/832418__kodshin__bubble-button.wav.wav"},
        // https://freesound.org/s/832418/
```

### Step 2 — drop source files

**Soundboard sounds** — keep the original download name, drop into the flat directory:

```
assets/audio/source/soundboard/832418__kodshin__bubble-button.wav.wav
```

No renaming. The slot assignment lives in `soundboard.json`, not in the filename.

**SFX / music** — rename to a short logical name that will be the code reference:

```
assets/audio/source/sfx/bubble.wav       ← was 832418__kodshin__bubble-button.wav.wav
assets/audio/source/music/ambient.wav
```

### Step 3 — assign soundboard sounds to slots

Edit `assets/audio/soundboard.json`. Paste the stubs from step 1 into the right bank,
replace `"N"` with the slot number (0–7), and fill in the Swedish and English labels:

```json
"0": {
  "name_sv": "Effekter",
  "name_en": "Effects",
  "color": "#FF6B35",
  "slots": {
    "0": {"sv": "Bubbla", "en": "Bubble", "source": "soundboard/832418__kodshin__bubble-button.wav.wav"},
    "1": {"sv": "Alarm",  "en": "Alarm",  "source": "soundboard/834495__cvltiv8r__sci-fi-glitch-sweep-alarm-burst.wav.wav"}
  }
}
```

Only populated slots need entries. Empty slots play a boop fallback on the device.

### Step 4 — add SFX to the code catalog

If you added SFX or music, open `firmware/bodn/sounds.py` and add an entry to the `WAV` dict:

```python
WAV = {
    "sfx": {
        "bubble": "/sounds/sfx/bubble.wav",
    },
    "music": {
        "ambient": "/sounds/music/ambient.wav",
    },
}
```

Keep keys stable — they are referenced in game and UI code.

### Step 5 — convert

```bash
uv run python tools/convert_audio.py
```

### Step 5b — sync to SD card

```bash
uv run python tools/sd-sync.py              # build + sync to auto-detected SD card
uv run python tools/sd-sync.py --build-only  # build only (no card needed)
```

### Step 6 — commit

```bash
git add assets/audio/soundboard.json assets/audio/sources.tsv
git add firmware/sounds/ firmware/bodn/sounds.py
git commit -m "Add audio: <brief description>"
```

---

## Re-downloading from scratch

If you lose your source files, reconstruct them from `sources.tsv`:

```
filename    url                          license  attribution
832418__kodshin__bubble-button.wav.wav   https://freesound.org/s/832418/   CC0   kodshin (...)
```

Fetch each URL, place the file in `assets/audio/source/soundboard/` (or `sfx/`/`music/`
for renamed files — the notes column in `sources.tsv` is a good place to record the
logical name), then run `convert_audio.py`. The slot ordering is reproduced exactly
because `soundboard.json` is committed.

---

## Drum kits (Sequencer mode)

The Sequencer mode uses named percussion samples stored in `build/sounds/kits/{kit_name}/`
on the SD card. Each kit is a flat directory of WAV files, one per drum voice. The kit
manifest lives at `assets/audio/kits.json` — that is the only file you edit to manage kits.

### How it works at runtime

On entering Sequencer mode the device preloads all five samples for the active kit into
PSRAM once (`preload_sounds("/sounds/kits/basic/", [...])` in `bodn/assets.py`). Playback
is then zero-latency from RAM — no SD reads during play. The mapping is:

| Arcade button | Drum voice | File |
|---|---|---|
| 0 (green) | Hi-hat | `hihat.wav` |
| 1 (blue)  | Snare  | `snare.wav` |
| 2 (white) | Kick   | `kick.wav`  |
| 3 (yellow)| Tom    | `tom.wav`   |
| 4 (red)   | Crash  | `crash.wav` |

The filenames are fixed. Adding a new kit means adding a new directory — not changing filenames.

### Pipeline: source → SD card

```
assets/audio/kits.json          ← you edit this (source paths + labels)
    │
    ▼  uv run python tools/convert_audio.py
build/sounds/kits/basic/        ← 16 kHz mono PCM WAVs (generated, not committed)
    │
    ▼  uv run python tools/sd-sync.py
/sd/sounds/kits/basic/          ← on the SD card, ready for the device
```

Or in one step:
```bash
uv run python tools/sd-sync.py              # build + auto-detect SD card (macOS: BODN*)
uv run python tools/sd-sync.py --build-only  # build only, no card needed
```

### Adding or replacing a sample

1. Drop the source file into `assets/audio/source/` (any location — typically `soundboard/`
   if it already lives there, or a new `kits/` subdirectory for kit-specific files).

2. Edit `assets/audio/kits.json` — update the `"source"` path for the drum you want to replace:

   ```json
   "kick": {"sv": "Bastrumma", "en": "Kick", "source": "kits/my_kick.wav"}
   ```

3. Convert and sync:

   ```bash
   uv run python tools/convert_audio.py
   uv run python tools/sd-sync.py
   ```

4. Commit `kits.json` and any new source files you own (CC0 downloads are gitignored —
   add them to `sources.tsv` for provenance).

### Adding a new kit

1. Add a new top-level key under `"kits"` in `assets/audio/kits.json`:

   ```json
   "rock": {
     "name_sv": "Rock",
     "name_en": "Rock",
     "drums": {
       "hihat": {"sv": "Hi-hat", "en": "Hi-hat", "source": "kits/rock_hihat.wav"},
       "snare": {"sv": "Virvel",  "en": "Snare",  "source": "kits/rock_snare.wav"},
       "kick":  {"sv": "Bastrumma", "en": "Kick", "source": "kits/rock_kick.wav"},
       "tom":   {"sv": "Tom",     "en": "Tom",    "source": "kits/rock_tom.wav"},
       "crash": {"sv": "Crash",   "en": "Crash",  "source": "kits/rock_crash.wav"}
     }
   }
   ```

   Use exactly the same five drum key names (`hihat`, `snare`, `kick`, `tom`, `crash`) —
   the Sequencer screen references them by name. Order does not matter.

2. Run `convert_audio.py` — it outputs `build/sounds/kits/rock/`.

3. Run `sd-sync.py` — it syncs `build/sounds/kits/rock/` to `/sd/sounds/kits/rock/`.

4. In `firmware/bodn/ui/sequencer.py`, update the kit path in `enter()`:

   ```python
   self._drum_bufs = preload_sounds("/sounds/kits/rock/", _DRUM_NAMES)
   ```

   (Kit selection UI is planned for a future release — for now the kit is hardcoded.)

### `kits.json` reference

```json
{
  "_comment": "Drum kit manifest. Source paths relative to assets/audio/source/.",
  "kits": {
    "<kit_name>": {
      "name_sv": "<Swedish display name>",
      "name_en": "<English display name>",
      "drums": {
        "<drum_key>": {
          "sv":     "<Swedish label>",
          "en":     "<English label>",
          "source": "<path relative to assets/audio/source/>"
        }
      }
    }
  }
}
```

| Field | Required | Description |
|---|---|---|
| `name_sv` / `name_en` | yes | Display name for future kit-picker UI |
| `drums.<key>.source` | yes | Source file path, relative to `assets/audio/source/` |
| `drums.<key>.sv` / `.en` | recommended | Label shown in future kit editor; used in `kits.json` display only |

The five drum keys the Sequencer expects: `hihat`, `snare`, `kick`, `tom`, `crash`.
Extra keys are ignored. Missing keys produce silence for that voice (no error).

---

## `soundboard.json` reference

`assets/audio/soundboard.json` is the **only file you edit** to manage soundboard
content. The device-side `firmware/sounds/manifest.json` is generated from it and
must never be edited by hand.

### Top-level structure

```json
{
  "banks": {
    "0": { ... },
    "1": { ... },
    "2": { ... },
    "3": { ... }
  },
  "arcade": {
    "0": { ... },
    "1": { ... }
  }
}
```

### Bank fields

| Field | Type | Description |
|---|---|---|
| `name_sv` | string | Swedish bank name shown on screen |
| `name_en` | string | English bank name shown on screen |
| `color` | `"#RRGGBB"` | Accent color for slot borders and NeoPixel bank glow |
| `slots` | object | Slot entries keyed `"0"`–`"7"` |

### Slot fields

| Field | Type | Description |
|---|---|---|
| `sv` | string | Swedish label shown on the button |
| `en` | string | English label shown on the button |
| `source` | string | Path to source file, relative to `assets/audio/source/` |

A slot can also be a plain string for a language-neutral label: `"0": "Miaow"`.

### Arcade entries

Same structure as slots; `source` relative to `assets/audio/source/`. Arcade buttons are shared across all banks.

---

## `sources.tsv` reference

Plain TSV, one row per source file. Tracks provenance for license compliance.

| Column | Description |
|---|---|
| `filename` | Original download filename |
| `url` | Canonical Freesound (or other) URL |
| `license` | `CC0`, `CC-BY 4.0`, etc. |
| `attribution` | Author name + profile URL |
| `notes` | Optional — logical name for renamed SFX/music files |

`import_freesound.py` populates this automatically for Freesound downloads.
Fill in the `notes` column manually for renamed SFX/music so you can trace
a `click.wav` back to its original file.

---

## `firmware/bodn/sounds.py` reference

Two dicts:

- **`SOUNDS`** — procedural tone sequences. Used by `audio.play_sound("boop")`.
  No audio files involved.
- **`WAV`** — filesystem paths to pre-recorded WAV files.
  Used by `audio.play(WAV["sfx"]["bubble"])`.

Soundboard paths are **not** in `WAV` — they are assigned dynamically by
`soundboard_rules.py` based on the bank and slot index at runtime.

---

## Device format

All device-ready WAV files (in `firmware/sounds/` and `build/sounds/`) must be:

| Property | Value |
|---|---|
| Format | WAV, PCM uncompressed |
| Sample rate | 16 000 Hz |
| Channels | Mono |
| Bit depth | 16-bit signed |

The conversion tool enforces this. See `docs/audio.md` for size estimates
and manual conversion instructions.
