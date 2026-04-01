# Audio asset management

This document covers how audio files are sourced, converted, deployed, and
referenced in code. Read this before adding any new sounds.

## Overview

There are three categories of audio:

| Category | What it is | Triggered by |
|---|---|---|
| **Soundboard** | One WAV per button slot | Child pressing a button |
| **SFX** | Short named clips for game/UI events | Code (`audio.play(WAV["sfx"]["..."])`) |
| **Music** | Background loops | Code (`audio.play(WAV["music"]["..."], loop=True)`) |

There is a fourth category — **procedural tones** — which are synthesised at runtime from note sequences defined in `firmware/bodn/sounds.py` (`SOUNDS` dict). Those do not go through the asset pipeline.

---

## Directory layout

```
assets/audio/                        ← source side (this repo)
  soundboard.json                    ← single source of truth (see below)
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

build/sounds/                        ← SD-bound (generated, not committed)
  bank_0/ … bank_3/                  ← converted soundboard WAVs (0.wav – 7.wav)
  arcade/                            ← converted arcade WAVs (0.wav – 4.wav)
  music/                             ← converted music WAVs
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

Batch-converts all source files to device format (16 kHz, mono, 16-bit PCM WAV) and regenerates `firmware/sounds/manifest.json` from `soundboard.json`. SFX and flash TTS go to `firmware/sounds/` (flash); soundboard, arcade, and music go to `build/sounds/` (SD). Skips files already up-to-date.

```bash
uv run python tools/convert_audio.py             # convert everything
uv run python tools/convert_audio.py --dry-run   # show what would run
uv run python tools/convert_audio.py --force     # reconvert regardless of mtime
```

Requires `ffmpeg` (`brew install ffmpeg`).

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
