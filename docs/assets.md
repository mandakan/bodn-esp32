# Asset management

Media assets (sound banks, music, arcade sounds, images, animations, recordings) live on
the SD card. Core firmware and UI feedback sounds live on flash and are always available,
even without an SD card.

## What goes where

| Storage | Path | Contents |
|---------|------|----------|
| Flash (`/`) | `/sounds/sfx/`, `/sounds/tts/` | UI feedback SFX, critical TTS (battery warnings, goodnight). Device boots and navigates without SD card. |
| SD card (`/sd/`) | `/sd/sounds/` | Sound banks, arcade sounds, music, game-mode TTS, space SFX. Managed via PC card reader or `sd-sync.py`. |

## Path resolver

`bodn/assets.py` provides a `resolve(path)` function used by all asset loaders:

```python
from bodn.assets import resolve

path = resolve("/sounds/bank_0/0.wav")
# Returns "/sd/sounds/bank_0/0.wav" if present on SD, else "/sounds/bank_0/0.wav"
```

One `os.stat()` per call (~0.1 ms) — negligible vs file I/O. No caching, no abstraction
layers. Assets can be moved between flash and SD without any code changes.

## SD card directory structure

```
/sd/
└── sounds/
    ├── bank_0/       # Bank 0 mini-button sounds
    │   ├── 0.wav     # Button 1 (or any .wav in discovery mode)
    │   ├── 1.wav
    │   └── …
    ├── bank_1/       # Bank 1 sounds
    ├── bank_2/       # Bank 2 sounds
    ├── bank_3/       # Bank 3 sounds
    ├── arcade/       # Shared arcade button sounds (all banks)
    │   ├── 0.wav … 4.wav
    ├── music/        # Background music
    ├── space/        # Space mode button/arcade SFX
    │   ├── thruster.wav, shields.wav, …
    └── tts/          # Game-mode TTS (bulk)
        ├── sv/
        │   ├── simon_watch.wav, …
        └── en/
            └── …
```

See the soundboard screen documentation for the manifest format.

## Audio file format

WAV files must be:
- 16-bit PCM, mono or stereo
- 16 000 Hz or 44 100 Hz sample rate (16 kHz preferred — smaller files, same quality at
  low playback volume)
- Normalised to −14 LUFS (EBU R128) for consistent playback volume across sound banks

Use `tools/convert_audio.py` to batch-convert and normalise source files.

## Building and syncing SD assets

`tools/sd-sync.py` is a one-command pipeline that generates TTS audio, converts all
assets to device format, and copies them to a mounted SD card:

```bash
# Full pipeline: build + sync (auto-detects /Volumes/BODN* on macOS)
uv run python tools/sd-sync.py

# Explicit mount point
uv run python tools/sd-sync.py /Volumes/BODN_SD

# Build only (no SD card needed)
uv run python tools/sd-sync.py --build-only

# Sync previously built assets without rebuilding
uv run python tools/sd-sync.py --no-build /Volumes/BODN_SD

# Preview what would happen
uv run python tools/sd-sync.py --dry-run /Volumes/BODN_SD
```

Tip: name your SD card `BODN` (or any name starting with `BODN`) for auto-detection.

### Manual workflow

If you prefer to manage files by hand:

1. Remove the SD card from the device.
2. Insert it into a PC card reader.
3. Copy WAV files into the appropriate directory (see structure above).
4. Eject the card and reinsert it in the device.
5. Restart the device — assets are available immediately.

## Incremental updates via WiFi

For small changes when the device is running and connected to a home network (STA mode):

```bash
# Copy a single file
uv run python tools/ftp-sync.py 192.168.1.42
```

Note: FTP sync pushes firmware only by default. To sync SD content, either use the PC
card reader workflow or extend the FTP client script manually.

## Future: on-device asset downloader

Not yet implemented. Planned: a web-UI option to fetch new/updated media assets over WiFi
directly onto the SD card. The `resolve()` overlay supports this — downloaded assets would
land on `/sd/` and be picked up immediately without code changes.
