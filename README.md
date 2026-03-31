# Bodn ESP32

Bodn is a battery-powered, kid-friendly interactive box built on the ESP32-S3.
The name comes from Böðn, one of the vessels that held the skaldic mead in Norse
mythology — the drink that granted wisdom and poetic inspiration.

## What it does

A colourful, tactile device that grows with a child (starting around age 4):

- **Press buttons and turn knobs** → hear sounds, see colours and animations
- **Play games** → Simon memory game, Mystery Box discovery, Flöde flow puzzles, Rule Follow, Garden of Life, Soundboard
- **Record and play back** short voice clips *(planned)*
- **Create sequences** of lights and sounds → first steps into programming concepts *(planned)*
- **Parental controls** → session time limits, break enforcement, quiet hours, lockdown — all configured from a phone via a local web UI

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
  main.py              # async entry point (uasyncio)
  st7735.py            # framebuf-based ST7735/ILI9341 driver + dirty rect tracking
  bodn/
    config.py           # pin assignments, constants, encoder sensitivity
    arcade.py           # arcade button input + LED output via MCP/PCA
    audio.py            # async AudioEngine (multi-channel priority playback)
    battery.py          # battery level reading and USB-only detection
    chord.py            # multi-button chord/combo detection
    cli.py              # serial REPL helpers (wifi, settings, reboot)
    debounce.py         # generic debounce logic
    diag.py             # system diagnostics data gathering
    encoder.py          # PCNT hardware rotary encoder (zero-CPU quadrature)
    ftp.py              # FTP server for OTA bulk sync
    gesture.py          # tap/hold/long-press gesture detection
    i18n.py             # internationalisation: t(), set_language(), init()
    lang/
      sv.py             # Swedish string table (default)
      en.py             # English string table
    mcp23017.py         # MCP23017 I2C GPIO expander driver
    patterns.py         # LED animation patterns (shared buffer)
    pca9685.py          # PCA9685 I2C PWM driver (arcade button LEDs)
    power.py            # power management (sleep, wake, master switch)
    qr.py               # minimal QR code encoder (V1–V2)
    session.py          # play session state machine (pure logic)
    sounds.py           # sound asset catalogue
    storage.py          # JSON settings & session history on flash
    temperature.py      # DS18B20 + SoC temperature monitoring
    tones.py            # procedural tone generation (pure logic)
    wav.py              # WAV header parser + streaming reader (pure logic)
    wifi.py             # WiFi connect (STA / AP) + mDNS + runtime control
    web.py              # async HTTP server for parental controls
    web_ui.py           # HTML/CSS/JS served to the browser
    *_rules.py          # pure-logic game engines (mystery, simon, flode,
                        #   rulefollow, life, soundboard)
    ui/
      screen.py         # Screen base class + ScreenManager
      theme.py          # colour palette and layout constants
      input.py          # unified input state with debouncing
      widgets.py        # stateless draw helpers
      icons.py          # 16×16 bitmap icons
      font_ext.py       # extended glyphs: å ä ö Å Ä Ö
      logo.py           # pixel-art boot logo
      home.py           # home screen with animated carousel
      demo.py           # LED playground mode
      mystery.py        # Mystery Box discovery game
      simon.py          # Simon memory game
      flode.py          # Flöde flow-alignment puzzle
      rulefollow.py     # Rule Follow (inhibition & flexibility)
      garden.py         # Garden of Life (cellular automata)
      soundboard.py     # Soundboard discovery mode
      clock.py          # clock display mode
      catface.py        # animated cat face (secondary content)
      ambient.py        # AmbientClock + StatusStrip (secondary display)
      secondary.py      # two-zone secondary display manager
      settings.py       # on-device settings menu (scrollable)
      overlay.py        # session state overlay
      pause.py          # in-game pause menu (hold-to-open)
      diag.py           # on-device diagnostics screen
      admin_qr.py       # admin URL screen with QR code
```

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

# Deploy firmware to the device
./tools/sync.sh

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

# FTP bulk sync — faster, STA/home network only; uses MD5 to skip unchanged files
uv run python tools/ftp-sync.py 192.168.1.42             # sync changed files
uv run python tools/ftp-sync.py 192.168.1.42 --force     # re-upload all files
```

FTP credentials are set via `ftp_user` / `ftp_pass` in the device settings.

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
2. ~~**Audio basics**~~ — tones, WAV playback, volume control ✓
3. **Kid-facing UI** — six game modes shipped; record/replay and sequencer planned
4. ~~**Parental controls**~~ — web UI, session limits, OTA, FTP sync ✓
5. **Quality-of-life** — battery indicator, temperature monitoring, i18n (Swedish/English) ✓

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

## Design goals

- **Cheap-ish**: ≤ 1500 SEK total
- **Modular & hackable**: breadboard prototyping, iterate fast
- **Open source**: firmware and docs from day one

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup, testing, and development workflow.

## License

MIT
