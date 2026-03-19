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
| Display | 1.8" 128×160 ST7735 TFT (SPI) |
| Microphone | INMP441 I2S MEMS |
| Amplifier | MAX98357A I2S 3W class-D + 3W 8Ω speaker |
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
    session.py          # play session state machine
    storage.py          # JSON settings & session history on flash
    wifi.py             # WiFi connect (STA / AP)
    web.py              # async HTTP server for parental controls
    web_ui.py           # HTML/CSS/JS served to the browser
```

## Getting started

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
