# Bodn ESP32

Bodn is a battery-powered, kid-friendly interactive box built on the ESP32-S3.
The name comes from Böðn, one of the vessels that held the skaldic mead in Norse
mythology — the drink that granted wisdom and poetic inspiration.

## What it does

A colourful, tactile device that grows with a child (starting around age 4):

- **Press buttons and turn knobs** → hear sounds, see colours and animations
- **Play games** → Simon memory, Mystery Box discovery, Flöde flow puzzles, Rule Follow, Garden of Life, Soundboard, Spaceship cockpit, Story Mode, High-Five Friends, Sequencer, Tone Lab (free-play sound design), Blippa (free-play NFC)
- **NFC card games** → scan physical cards for Sortera (classification) and Räkna (math); launcher cards start any game mode (PN532 reader + NTAG213 stickers)
- **Offline spoken audio** → Piper TTS generates Swedish and English narration for game instructions and stories; hand-recorded WAVs can transparently override any line
- **Parental controls** → session time limits, break enforcement, quiet hours, lockdown, NFC tag provisioning — all configured from a phone via a local web UI

## Hardware

| Component | Model |
|---|---|
| MCU | Olimex ESP32-S3-DevKit-Lipo (8 MB flash, 8 MB PSRAM, USB-C, LiPo charger) |
| Battery | Olimex BATTERY-LIPO6600mAh 6600 mAh |
| Primary display | 2.8" 240×320 ILI9341 TFT with touch (SPI) |
| Secondary display | 1.8" 128×160 ST7735 TFT (SPI, shared bus) |
| Microphone | INMP441 I2S MEMS |
| Amplifier | MAX98357A I2S 3W class-D + 3W 8Ω speaker |
| LED sticks | WS2812 8-LED sticks × 2 (daisy-chained, 16 addressable RGB) |
| LED strip | WS2812B 144 LED/m, 640 mm / ~92 LEDs (lid perimeter, chained after sticks) |
| Inputs | 2× KY-040 rotary encoders, 8× momentary push buttons, 2× toggle switches |
| Arcade buttons | 5× illuminated arcade buttons with PWM LED control |
| GPIO expanders | CJMCU-2317 MCP23017 16-IO boards × 2 (I2C, MCP1 0x23 / MCP2 0x21) |
| Temperature | DS18B20 × 2 (battery + enclosure, 1-Wire) |
| DC-DC converter | Buck-boost 3–16 V → 5 V / 2 A (LiPo → 5 V for NeoPixels) |
| Power switch | Panel-mount toggle switch |

See [`docs/hardware.md`](docs/hardware.md) for full pinout, wiring, and BOM.

## Firmware

Written in MicroPython, runs directly on the ESP32-S3.

```
firmware/
  boot.py              # WiFi setup, NTP sync, battery check, boot screen
  main.py              # async entry point (uasyncio) + housekeeping/thermal task
  sdcard.py            # SPI SD card driver (optimised for ESP32-S3 audio streaming)
  st7735.py            # framebuf-based ST7735/ILI9341 driver + dirty rect tracking
  bodn/
    arcade.py           # arcade button input + LED output via MCP/PCA
    assets.py           # SD-first / flash-fallback asset path resolver
    audio.py            # AudioEngine (native core-0 C mixer, falls back to viper)
    battery.py          # battery level reading and USB-only detection
    chord.py            # multi-button chord/combo detection
    cli.py              # serial REPL helpers (wifi, settings, reboot)
    config.py           # pin assignments, constants, encoder sensitivity
    debounce.py         # generic debounce logic
    diag.py             # system diagnostics data gathering
    encoder.py          # PCNT hardware rotary encoder (zero-CPU quadrature)
    encoder_scope.py    # visual encoder oscilloscope (CLK/DT on TFT)
    gesture.py          # tap/hold/long-press gesture detection
    i18n.py             # internationalisation: t(), set_language(), init()
    i2c_diag.py         # live I2C bus diagnostic tool (REPL)
    lang/
      sv.py             # Swedish string table (default)
      en.py             # English string table
    mcp23017.py         # MCP23017 I2C GPIO expander driver
    native_i2c.py       # native C I2C wrapper for deterministic scans
    neo.py              # NeoPixel facade over the native C pattern engine
    nfc.py              # NFC tag parsing, card sets, UID cache
    patterns.py         # LED animation patterns (shared buffer)
    pca9685.py          # PCA9685 I2C PWM driver (arcade button LEDs)
    pn532.py            # PN532 NFC reader driver (I2C, polling task)
    power.py            # power management (sleep, wake, master switch)
    qr.py               # minimal QR code encoder (V1–V2)
    sdcard.py           # SD card initialisation and mount
    session.py          # play session state machine (pure logic)
    sounds.py           # sound asset catalogue
    storage.py          # JSON settings & session history on flash
    stories/            # story package (scripts discovered at runtime on SD)
    temperature.py      # DS18B20 + SoC temperature monitoring
    tone_explorer_rules.py # Tone Lab / Ljudlabb state model (pure logic)
    tones.py            # procedural tone generation (pure logic)
    tts.py              # TTS playback helper (SD-first voice resolution)
    wav.py              # WAV header parser + streaming reader (pure logic)
    web.py              # async HTTP server for parental controls
    web_ui.py           # HTML/CSS/JS served to the browser
    wifi.py             # WiFi connect (STA / AP) + mDNS + runtime control
    *_rules.py          # pure-logic game engines: mystery, simon, flode,
                        #   rulefollow, life, soundboard, space, story,
                        #   sequencer, highfive, sortera, rakna, tone_explorer
    ui/
      screen.py         # Screen base class + ScreenManager
      theme.py          # colour palette and layout constants
      input.py          # unified input state with debouncing
      draw.py           # wrapper around the native _draw C module
      widgets.py        # stateless draw helpers + sprite cache
      icons.py          # 16×16 bitmap icons (flash fallback)
      font_ext.py       # extended glyphs: å ä ö Å Ä Ö
      logo.py           # pixel-art boot logo
      android.py        # boot-time Android-style status bar helper
      home.py           # home screen with animated carousel
      demo.py           # LED playground mode
      mystery.py              # Mystery Box discovery game
      simon.py                # Simon memory game
      flode.py                # Flöde flow-alignment puzzle
      rulefollow.py           # Rule Follow (inhibition & flexibility)
      garden.py               # Garden of Life (cellular automata)
      garden_secondary.py     # Garden secondary display content
      soundboard.py           # Soundboard discovery mode
      soundboard_secondary.py # Soundboard secondary display content
      sequencer.py            # loop sequencer mode
      sequencer_secondary.py  # Sequencer secondary display content
      highfive.py             # High-Five Friends reflex game
      space.py                # Spaceship cockpit mode
      story.py                # branching story mode (scripts + TTS on SD)
      sortera.py              # Sortera NFC classification game
      rakna.py                # Räkna NFC math game
      tone_explorer.py           # Tone Lab / Ljudlabb free-play screen
      tone_explorer_secondary.py # Tone Lab secondary display content
      blippa.py               # Blippa free-play "blip any card" NFC mode
      clock.py          # clock display mode
      catface.py        # animated cat face (secondary content)
      ambient.py        # AmbientClock + StatusStrip (secondary display)
      secondary.py      # two-zone secondary display manager
      settings.py       # on-device settings menu (scrollable)
      overlay.py        # session state overlay
      pause.py          # in-game pause menu (hold-to-open)
      diag.py           # on-device diagnostics screen
      admin_qr.py       # admin URL screen with QR code
      nfc_provision.py  # NFC card set viewer + provisioning
      icon_browser.py   # OpenMoji emoji sprite browser
      launch_splash.py  # full-screen "Loading <mode>" splash for NFC launches
      ota.py            # OTA firmware sync takeover status screen
```

### Native C modules

Six C modules in `cmodules/` compile into a custom MicroPython firmware build
(see `tools/build-firmware.sh`). Each has a Python fallback so stock
MicroPython still runs — the board definition lives in `boards/BODN_S3/`.

| Module | What it does |
|---|---|
| `_audiomix` | 16-voice audio mixer + I2S + step clock on core 0 |
| `_spidma` | DMA-driven SPI display writes in 32 KB chunks |
| `_draw` | Bitmap fonts, sprite blit, primitives with alpha blending |
| `_mcpinput` | Deterministic MCP23017 input scanner (core 1 task) |
| `_neopixel` | NeoPixel pattern engine (animations run in C, not Python) |
| `_life` | Game of Life step kernel (torus-wrap, falls back to Python) |

## Getting started

For a complete first-boot walkthrough (flashing MicroPython, serial console, debugging),
see [`docs/getting-started.md`](docs/getting-started.md).

### Prerequisites

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- An ESP32-S3 board flashed with MicroPython

### Setup

```bash
# Install host tools (mpremote, ruff, black)
uv sync

# Deploy firmware to the device (auto-detects USB vs WiFi via bodn.local)
./tools/deploy.sh

# Open a REPL
uv run mpremote connect auto repl
```

### Device configuration

Connect to the REPL and use the built-in CLI helpers:

```bash
# Open a REPL (Ctrl-C to stop main loop first)
uv run mpremote connect auto repl
```

```python
from bodn.cli import *

# Configure WiFi (saves immediately, reboot to apply)
wifi("MyNetwork", "MyPassword")
reboot()

# Show all settings
show()

# Change any setting
set("language", "en")       # en or sv
set("sleep_timeout_s", 600) # idle sleep in seconds
save()                      # persist to flash

# Switch to AP mode (creates its own network)
ap()
reboot()
```

**Skip main.py for debugging** — create a flag file, then reset:

```bash
uv run mpremote connect auto fs touch :/skip_main
# Press RST — boots to REPL without starting the UI/encoder IRQs
# The flag auto-deletes — next reset boots normally
```

**Built-in diagnostic tools** (run from REPL after skipping main):

```python
# I2C bus monitor — live device detection + MCP pin states
from bodn.i2c_diag import run; run()

# Encoder oscilloscope — raw CLK/DT waveforms on the TFT
from bodn.encoder_scope import run; run()       # both encoders
from bodn.encoder_scope import run; run(enc=1)  # ENC1 only
```

### OTA push (no USB needed)

Once the device is running and on WiFi, you can push firmware updates over the air:

```bash
# HTTP push — works in both AP and STA mode
uv run python tools/ota-push.py                          # AP mode default (192.168.4.1)
uv run python tools/ota-push.py 192.168.1.42             # specific device IP
uv run python tools/ota-push.py --wokwi                   # Wokwi (localhost:9080)
```

**Note:** OTA reboot does not work in Wokwi — the simulator's filesystem is in RAM
and is lost on reset. Use `wokwi-sync.py` for Wokwi development instead.

### Wokwi simulation

The firmware runs in [Wokwi](https://wokwi.com/) via the VS Code extension. The simulator includes a custom chip that faithfully emulates the MCP23017 GPIO expander over I2C, so the same driver code runs in simulation and on hardware.

```bash
# Push firmware to the running Wokwi simulator (start it first in VS Code)
uv run python tools/wokwi-sync.py

# Re-sync once and exit
uv run python tools/wokwi-sync.py --once
```

**Custom MCP23017 chip** — the chip is implemented in `mcp23017.chip.c` and compiled to `mcp23017.chip.wasm` (committed). If you change the C source, recompile before committing:

```bash
# First-time: download wokwi-cli (macOS arm64 shown; see wokwi-cli releases for other platforms)
curl -L https://github.com/wokwi/wokwi-cli/releases/latest/download/wokwi-cli-macos-arm64 \
  -o ~/bin/wokwi-cli && chmod +x ~/bin/wokwi-cli

# Recompile after editing mcp23017.chip.c
~/bin/wokwi-cli chip compile mcp23017.chip.c -o mcp23017.chip.wasm
```

The `wokwi-api.h` header downloaded by the CLI on first run is gitignored — don't commit it.

### Lint & format

```bash
uv run ruff check firmware/
uv run black firmware/
```

## Parental controls (web UI)

The box enforces play limits so **Bodn** is the one saying "time to rest", not the
parent. Parents configure limits from their phone via a local web UI — no app, no cloud.

### How it works

On boot the device either creates a WiFi access point named **Bodn** (default) or
connects to your home network (configurable). Open the device's IP in a browser to
reach the control panel.

**Dashboard** — current state, session count, time remaining.
**Limits** — session length, max sessions/day, break duration, quiet hours.
**History** — today's play sessions at a glance.
**WiFi** — switch between AP and station mode.

Default limits: 20 min per session, 5 sessions/day, 15 min break between sessions.

### Session flow

`IDLE → PLAYING → WARN (5 min) → WARN (2 min) → WIND-DOWN → SLEEP → COOLDOWN → IDLE`

During wind-down the LEDs fade out and the display shows a sleepy animation.
During cooldown the box stays dark. A **lockdown** toggle immediately puts the box to
sleep from any state.

### Reaching the web UI

**On real hardware (AP mode):** connect your phone to the "Bodn" WiFi network,
then open `http://192.168.4.1`.

**On real hardware (STA mode):** configure WiFi credentials via the REPL (see
below), then open the IP shown on the TFT boot screen.

**In Wokwi:** the ESP32 connects to WiFi (Wokwi-GUEST) but inbound port
forwarding requires the [Wokwi Private Gateway](https://docs.wokwi.com/guides/esp32-wifi#connecting-to-the-simulated-esp32-from-your-computer)
(Wokwi Club subscription). Without it, use the REPL to test parental controls:

```python
import boot
boot.settings["max_session_min"] = 1   # 1-minute session for testing
boot.settings["lockdown"] = True        # instant lockdown
```

For quick testing, set **Session length** to 1 minute to see the full
wind-down cycle.

## Roadmap

See [`docs/roadmap.md`](docs/roadmap.md) for detailed milestones.

1. ~~**Hardware bring-up**~~ — display, buttons, encoders ✓
2. ~~**Audio basics**~~ — tones, WAV playback, native C mixer on core 0 ✓
3. **Kid-facing UI** — 14 game modes shipped (incl. Sortera + Räkna NFC games, Tone Lab, Blippa); record & replay still planned
4. ~~**Parental controls**~~ — web UI, session limits, PIN, OTA sync, NFC tag provisioning from the browser ✓
5. **Quality-of-life** — battery indicator, temperature monitoring, i18n (Swedish/English), offline TTS ✓
6. **NFC integration** — PN532 driver, Sortera + Räkna shipped; more card-based modes on deck

## Developmental foundations

Every game mode is grounded in developmental science — executive functions,
sensorimotor skills, guided play, and tangible interface research. Three
companion documents live in [`docs/science/`](docs/science/):

- **[Development Matrix](docs/science/development_matrix.md)** — feature × developmental aspect coverage, gap analysis, and age progression timeline
- **[Development Guide](docs/science/development_guide.md)** — plain-language overview for parents and educators
- **[Report (PDF)](docs/science/report.pdf)** — scientific report with proper citations ([LaTeX source](docs/science/report.tex), [bibliography](docs/science/report.bib))

Build the report PDF (requires a TeX distribution):

```bash
docs/science/build.sh        # render report.pdf
docs/science/build.sh clean  # remove build artefacts
```

## NFC card games

Bodn supports NFC-tagged physical cards as input for classification, math, storytelling,
and vocabulary games. Cards carry self-describing data (NDEF Text Records) so they work
across devices and are readable by phones.

See [`docs/nfc.md`](docs/nfc.md) for the tag format specification and
[`docs/science/nfc_tangible_learning.md`](docs/science/nfc_tangible_learning.md) for the
research foundations.

### Hardware

A PN532 NFC reader connects via I2C (address 0x24) on a power-gated rail so it
can be turned off during sleep and low-battery states. The driver (`bodn/pn532.py`)
runs a polling task; tags are written with retries and automatic PN532 recovery.

### Shipped card sets

| Set | Game | Contents |
|---|---|---|
| `sortera` | Classification (DCCS-style) | 16 animal cards in 4 colours |
| `rakna` | Math (levels 1–6) | Numbers, operators, and equation builders |
| `launcher` | Shortcut cards | Tap a card to jump straight into any game mode |

Programmed cards are tracked via the NFC provisioning UI; the Sortera set filters
down to whatever is actually written to tags on startup.

### Card production

Cards are printed on paper/cardstock with an NFC sticker on the back, then laminated.

```bash
# One-time: clone OpenMoji icons (CC-BY-SA 4.0, ~200 MB)
git clone --depth 1 https://github.com/hfg-gmuend/openmoji.git ~/openmoji

# Generate printable A4 PDFs for all card sets (85×54 mm, 2×4 per page)
uv run python tools/generate_cards.py

# Specific set only
uv run python tools/generate_cards.py --set sortera

# Preview without generating
uv run python tools/generate_cards.py --dry-run
```

Output: `build/cards/*_cards.pdf` — print, cut, laminate, attach NFC stickers.

## OpenMoji icons

On-screen mode icons use [OpenMoji](https://openmoji.org/) (CC-BY-SA 4.0) — colourful
emoji rendered as BDF sprites via the existing native `_draw` module. The home screen
carousel loads them automatically from the SD card, falling back to built-in 1-bit icons
if not available.

### Setup

```bash
# Clone OpenMoji (one-time, or set OPENMOJI_DIR to an existing checkout)
git clone --depth 1 https://github.com/hfg-gmuend/openmoji.git ~/openmoji

# Convert all icons (33 emoji × 4 sizes → BDF sprites, ~4 bpp)
uv run python tools/convert_icons.py

# Or let sd-sync handle everything automatically:
uv run python tools/sd-sync.py
```

All three OpenMoji tools (`convert_icons.py`, `generate_cards.py`, `sd-sync.py`) resolve
the OpenMoji directory in this order: `--openmoji` flag → `$OPENMOJI_DIR` env var → `~/openmoji`.

### SD card build pipeline

```bash
# Build and sync all SD card assets (TTS, audio, sprites, emoji, NFC configs)
uv run python tools/sd-sync.py                      # auto-detect SD card
uv run python tools/sd-sync.py /Volumes/BODN_SD     # explicit path
uv run python tools/sd-sync.py --build-only          # build without copying
uv run python tools/sd-sync.py --dry-run             # preview
```

The pipeline runs 5 steps: TTS generation → story TTS → audio conversion → sprite
building → emoji icon conversion. Each step skips up-to-date files automatically.

## Stories and TTS

Two offline TTS pipelines generate spoken audio with [Piper TTS](https://github.com/rhasspy/piper):

- **i18n TTS** (`tools/generate_tts.py`) — game instructions, safety alerts, and
  overlay phrases from the `STRINGS` dicts in `firmware/bodn/lang/`. Safety-critical
  keys (e.g. `bat_critical`, `overlay_goodnight`) stay on flash; the rest live on
  the SD card.
- **Story TTS** (`tools/generate_story_tts.py`) — narration and choice labels for
  branching stories authored in `assets/stories/{story_id}/script.py`. Stories are
  self-contained SD packages: script + per-language WAVs, discovered at runtime.
  Ships with `peter_rabbit` and `forest_walk`.

Any TTS line can be replaced with a human recording — drop a WAV at
`assets/audio/source/recordings/{lang}/{key}.wav` (i18n) or
`assets/stories/{id}/recordings/{lang}/{node}.wav` (story). Filenames must match
the TTS key/node exactly. `convert_audio.py` normalises the recording to 16 kHz
mono PCM with loudnorm; `bodn.assets.resolve_voice()` prefers recordings over
TTS. Coverage is incremental — record one key, the rest stay on TTS.

See [`docs/story_authoring.md`](docs/story_authoring.md) for the story authoring
guide and [`docs/audio_assets.md`](docs/audio_assets.md) for the audio pipeline.

## Design goals

- **Cheap-ish**: ≤ 1500 SEK total
- **Modular & hackable**: breadboard prototyping, iterate fast
- **Open source**: firmware and docs from day one

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup, testing, and development workflow.

## License

MIT
