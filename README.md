# Bodn ESP32

Bodn is a battery-powered, kid-friendly interactive box built on the ESP32-S3.
The name comes from Böðn, one of the vessels that held the skaldic mead in Norse
mythology — the drink that granted wisdom and poetic inspiration.

## What it does

A colourful, tactile device that grows with a child (starting around age 4):

- **Press buttons and turn knobs** → hear sounds, see colours and animations
- **Record and play back** short voice clips
- **Create sequences** of lights and sounds → first steps into programming concepts
- **Parental controls** → session time limits, break enforcement, quiet hours, lockdown — all configured from a phone via a local web UI

## Hardware

| Component | Model |
|---|---|
| MCU | Olimex ESP32-S3-DevKit-Lipo (8 MB flash, 8 MB PSRAM, USB-C, LiPo charger) |
| Battery | Olimex BATTERY-LIPO6600mAh |
| Primary display | 2.8" 240×320 ILI9341 TFT with touch (SPI) |
| Secondary display | 1.8" 128×160 ST7735 TFT (SPI, shared bus) |
| Microphone | INMP441 I2S MEMS |
| Amplifier | MAX98357A I2S 3W class-D + 3W 8Ω speaker |
| LEDs | WS2812 8-LED sticks × 2 (16 addressable RGB NeoPixels) |
| Inputs | 3× KY-040 rotary encoders, 8× momentary push buttons, 4× toggle switches |

See [`docs/hardware.md`](docs/hardware.md) for full pinout, wiring, and BOM.

## Firmware

Written in MicroPython, runs directly on the ESP32-S3.

```
firmware/
  boot.py              # WiFi setup, NTP sync, load settings
  main.py              # async entry point (uasyncio)
  st7735.py            # framebuf-based ST7735/ILI9341 display driver
  bodn/
    config.py           # pin assignments, constants
    debounce.py         # generic debounce logic
    encoder.py          # IRQ-based rotary encoder reader
    patterns.py         # LED animation patterns (shared buffer)
    mystery_rules.py    # Mystery Box rule engine (pure logic)
    session.py          # play session state machine
    storage.py          # JSON settings & session history on flash
    wifi.py             # WiFi connect (STA / AP) + runtime control
    web.py              # async HTTP server for parental controls
    web_ui.py           # HTML/CSS/JS served to the browser
    ui/
      screen.py         # Screen base class + ScreenManager
      theme.py          # colour palette and layout constants
      input.py          # unified input state with debouncing
      widgets.py        # stateless draw helpers (labels, bars, grids)
      icons.py          # 16×16 bitmap icons
      home.py           # home screen with mode selection
      demo.py           # LED playground mode
      mystery.py        # Mystery Box discovery game
      clock.py          # clock display mode
      ambient.py        # secondary display (clock + session bar)
      settings.py       # on-device settings menu
      overlay.py        # session state overlay
      pause.py          # in-game pause menu
      secondary.py      # secondary display manager
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

### OTA push (no USB needed)

Once the device is running and on WiFi, you can push firmware updates over the air:

```bash
uv run python tools/ota-push.py                          # AP mode default (192.168.4.1)
uv run python tools/ota-push.py 192.168.1.42             # specific device IP
uv run python tools/ota-push.py --token SECRET            # with OTA auth token
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
>>> import boot
>>> boot.settings["max_session_min"] = 1   # 1-minute session for testing
>>> boot.settings["lockdown"] = True        # instant lockdown
```

For quick testing, set **Session length** to 1 minute to see the full
wind-down cycle.

## Roadmap

See [`docs/roadmap.md`](docs/roadmap.md) for detailed milestones.

1. **Hardware bring-up** — display, buttons, encoders
2. **Audio basics** — tones, samples, record/playback
3. **Kid-facing UI** — home screen, sound modes, sequencing
4. **Quality-of-life** — battery indicator, WiFi config, web UI

## Design goals

- **Cheap-ish**: ≤ 1500 SEK total
- **Modular & hackable**: breadboard prototyping, iterate fast
- **Open source**: firmware and docs from day one

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup, testing, and development workflow.

## License

MIT
