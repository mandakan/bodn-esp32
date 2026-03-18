# Bodn ESP32

Bodn is a battery-powered, kid-friendly interactive box built on the ESP32-S3.
The name comes from Böðn, one of the vessels that held the skaldic mead in Norse
mythology — the drink that granted wisdom and poetic inspiration.

## What it does

A colourful, tactile device that grows with a child (starting around age 4):

- **Press buttons and turn knobs** → hear sounds, see colours and animations
- **Record and play back** short voice clips
- **Create sequences** of lights and sounds → first steps into programming concepts

## Hardware

| Component | Model |
|---|---|
| MCU | Olimex ESP32-S3-DevKit-Lipo (8 MB flash, 8 MB PSRAM, USB-C, LiPo charger) |
| Battery | Olimex BATTERY-LIPO6600mAh |
| Display | 1.8" 128×160 ST7735 TFT (SPI) |
| Microphone | INMP441 I2S MEMS |
| Amplifier | MAX98357A I2S 3W class-D + 3W 8Ω speaker |
| Inputs | 2× KY-040 rotary encoders, 6× momentary push buttons, 3× toggle switches |

See [`docs/hardware.md`](docs/hardware.md) for full pinout, wiring, and BOM.

## Firmware

Written in MicroPython, runs directly on the ESP32-S3.

```
firmware/
  boot.py              # wifi / boot mode handling
  main.py              # application entry point
  st7735.py            # framebuf-based ST7735/ILI9341 display driver
  bodn/
    config.py           # pin assignments, constants
    debounce.py         # generic debounce logic
    encoder.py          # IRQ-based rotary encoder reader
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

### Lint & format

```bash
uv run ruff check firmware/
uv run black firmware/
```

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
