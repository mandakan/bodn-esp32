# Audio file guide

Bodn plays sound effects and short audio clips through a MAX98357A amplifier.
This page explains how to prepare audio files manually.

For the full asset management workflow (adding sounds, the conversion pipeline,
`soundboard.json`, `sources.tsv`) see `docs/audio_assets.md`.

## Recommended format

| Property | Value |
|----------|-------|
| Format | WAV (PCM, uncompressed) |
| Sample rate | 16 000 Hz |
| Channels | Mono |
| Bit depth | 16-bit signed |

16 kHz is plenty for sound effects and voice clips, and halves file size
compared to CD quality (44.1 kHz). It also matches the I2S output rate so no
resampling is needed.

## File size reference

| Duration | Size |
|----------|------|
| 1 second | 32 KB |
| 5 seconds | 160 KB |
| 10 seconds | 320 KB |
| 30 seconds | 960 KB |

## Flash vs SD card

- **Flash** — UI feedback sounds (boop, click, error). Keep total < 50 KB.
- **SD card** — longer sounds, music, voice recordings. Use FAT32 format.

## Converting with ffmpeg

```bash
ffmpeg -i input.mp3 -ar 16000 -ac 1 -sample_fmt s16 -acodec pcm_s16le output.wav
```

## Converting with Audacity

1. Open your audio file.
2. Set project sample rate to **16000** (bottom-left corner).
3. **Tracks → Mix → Mix Stereo Down to Mono** (if stereo).
4. **File → Export Audio…** → choose **WAV (Microsoft) signed 16-bit PCM**.

## What works but isn't optimal

| Input | What happens |
|-------|-------------|
| 8-bit WAV | Supported — converted to 16-bit on the fly. Lower quality. |
| Stereo WAV | Left channel is extracted. Wastes half the file size. |
| 44.1 / 22.05 kHz | Works via playback speed resampling, but wastes CPU and storage. |

## What doesn't work

- **MP3, OGG, FLAC** — no decoder on ESP32 MicroPython.
- **24-bit or 32-bit WAV** — not supported by the WAV reader.
- **Compressed WAV** (ADPCM, μ-law) — only PCM format 1 is accepted.

## TTS (text-to-speech)

Spoken instructions and feedback are generated offline with [Piper TTS](https://github.com/rhasspy/piper)
and played back as regular WAV files. Swedish (`sv_SE-nst-medium`) is the default voice;
English (`en_US-amy-medium`) is secondary.

### Workflow

```bash
# 1. Generate raw TTS WAVs from i18n strings
uv run python tools/generate_tts.py

# 2. Convert flash TTS + SD TTS staging to device format (16 kHz mono PCM)
uv run python tools/convert_audio.py

# 3. Copy converted SD files to the SD card
cp -r build/tts_converted/ /Volumes/BODN_SD/sounds/tts/
```

### Storage split

| Location | Path | What |
|----------|------|------|
| Flash (committed) | `firmware/sounds/tts/{lang}/{key}.wav` | Generic UI + safety (~3 keys × 2 langs) |
| SD card | `/sd/sounds/tts/{lang}/{key}.wav` | Game-mode-specific (bulk) |

Flash TTS source files live in `assets/audio/source/tts/` and are picked up by
`convert_audio.py` like any other audio category. SD staging files are in `build/tts/`
(not committed); converted output goes to `build/tts_converted/`.

### Key allowlist

The file `assets/audio/tts.json` controls which i18n keys get TTS generated and
whether each key lives on flash or SD. Keys whose text contains `{}` format
placeholders are automatically skipped (variable content cannot be spoken verbatim).

### Device API

```python
from bodn.tts import say

# Play TTS for the current language; falls back gracefully if file missing.
if not say("simon_watch", audio):
    audio.play_sound("boop")   # procedural tone fallback
```

`say()` calls `bodn.assets.resolve()` internally, so SD files are preferred over
flash automatically.
