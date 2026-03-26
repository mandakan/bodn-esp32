# Soundboard mode

Press buttons to play sounds. The 2 toggle switches choose the active bank; the 8 mini buttons and 5 arcade buttons trigger WAV files from internal flash.

## Controls

| Control | Action |
|---|---|
| Mini buttons 0–7 | Play slot sound. Press during playback → restart |
| Arcade buttons 0–4 | Play shared arcade sound (same across all banks) |
| Toggles 0–1 | Select bank (2-bit: 00=Bank 1, 01=Bank 2, 10=Bank 3, 11=Bank 4) |
| ENC_A (right) turn | Volume up/down |
| ENC_A (right) click | Mute / unmute |
| NAV (left) click | Exit to home |

Empty slots (no WAV file) play a short "boop" instead of silence — no wrong moves.

## File layout

Sounds live on internal flash. The directory structure is mandatory; filenames are fixed.

```
/sounds/
├── bank_0/
│   ├── 0.wav
│   ├── 1.wav
│   └── ...
│   └── 7.wav
├── bank_1/
│   └── ...
├── bank_2/
│   └── ...
├── bank_3/
│   └── ...
├── arcade/
│   ├── 0.wav
│   ├── 1.wav
│   ├── 2.wav
│   ├── 3.wav
│   └── 4.wav
└── manifest.json   ← optional
```

**WAV format**: 16-bit mono, 22 050 Hz. ~44 KB per second of audio.
Files not in this exact structure are ignored — dumping files in `/sounds/` directly has no effect.

Upload via `sync.sh`, `ota-push.py`, or the web UI (planned).

## manifest.json

All fields are optional. Without a manifest the soundboard still works: bank names default to "Bank 1"–"Bank 4" and slot labels default to "Ljud 1"–"Ljud 8" / "Sound 1"–"Sound 8".

```json
{
  "banks": {
    "0": {
      "name_sv": "Djur",
      "name_en": "Animals",
      "color": "#FF6B35",
      "slots": {
        "0": {"sv": "Hund",   "en": "Dog"},
        "1": {"sv": "Katt",   "en": "Cat"},
        "2": {"sv": "Groda",  "en": "Frog"},
        "3": {"sv": "Lejon",  "en": "Lion"},
        "4": {"sv": "Gris",   "en": "Pig"},
        "5": {"sv": "Ko",     "en": "Cow"},
        "6": {"sv": "Häst",   "en": "Horse"},
        "7": {"sv": "Höna",   "en": "Hen"}
      }
    },
    "1": {
      "name_sv": "Instrument",
      "name_en": "Instruments",
      "color": "#3B82F6",
      "slots": {
        "0": {"sv": "Trumma",  "en": "Drum"},
        "1": {"sv": "Piano",   "en": "Piano"},
        "2": {"sv": "Gitarr",  "en": "Guitar"},
        "3": {"sv": "Trumpet", "en": "Trumpet"},
        "4": {"sv": "Fiol",    "en": "Violin"},
        "5": {"sv": "Flöjt",   "en": "Flute"},
        "6": {"sv": "Orgel",   "en": "Organ"},
        "7": {"sv": "Klocka",  "en": "Bell"}
      }
    },
    "2": {
      "name_sv": "Fordon",
      "name_en": "Vehicles",
      "color": "#10B981"
    },
    "3": {
      "name_sv": "Roliga",
      "name_en": "Silly",
      "color": "#F59E0B"
    }
  }
}
```

### Bank fields

| Field | Type | Description |
|---|---|---|
| `name_sv` | string | Swedish bank name shown on screen |
| `name_en` | string | English bank name shown on screen |
| `name` | string | Language-neutral fallback name |
| `color` | `"#RRGGBB"` | Accent color — used for slot borders and NeoPixel bank glow |
| `slots` | object | Per-slot labels, keyed `"0"`–`"7"` |

Name resolution order: `name_<lang>` → `name` → "Bank N".

### Slot label values

A slot label can be a plain string (language-neutral) or a per-language dict:

```json
"slots": {
  "0": "Hund",
  "1": {"sv": "Katt", "en": "Cat"}
}
```

Dict resolution order: active language → `"sv"` → first available key.

### Arcade slots

The 5 arcade buttons are shared across all banks; their sounds live in `/sounds/arcade/`. Labels and custom colors for arcade buttons are not supported in the manifest — they use fixed colors (yellow/red/blue/green/white).

## Preparing audio files

For the full workflow — downloading from Freesound, the conversion pipeline,
`soundboard.json`, and `sources.tsv` — see `docs/audio_assets.md`.

Quick manual conversion reference:

```bash
ffmpeg -i input.mp3 -ar 16000 -ac 1 -sample_fmt s16 -acodec pcm_s16le output.wav
```
