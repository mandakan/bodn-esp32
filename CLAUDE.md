# Bodn ESP32 — AI assistant guidelines

## How to help

- **Target audience**: a 4-year-old child. Keep UX simple, colourful, and forgiving.
- **Language**: MicroPython on ESP32-S3. No C/C++ unless absolutely required.
- **Style**: keep modules small and self-contained. Prefer clarity over cleverness.
- **Hardware**: assume we have limited GPIO budget — check `firmware/bodn/config.py` before assigning pins.
- **Testing**: pure logic modules (debounce, UI state, audio format) are tested with `pytest` on the host. Hardware wrappers are tested on-device via `mpremote` or in Wokwi.
- **Dependencies**: host tools are managed with `uv`. MicroPython libs go directly into `firmware/`.
- **Pin assignments**: `firmware/bodn/config.py` is the single source of truth. Never hardcode GPIO numbers elsewhere.
- **Wiring docs**: `docs/wiring.md` is auto-generated. After changing `config.py`, run `uv run python tools/pinout.py --md` and commit both files. A pre-commit hook enforces this.

## Project overview

Battery-powered, kid-friendly interactive box built on ESP32-S3.

Core experiences:
1. Press buttons / turn knobs → sounds, colours, simple animations.
2. Record and play back short voice clips.
3. Later: create sequences (lights + sounds) → intro to programming concepts.

Constraints: ≤ 1500 SEK budget, modular & hackable, open source from day one.

## Name

**Bodn** (Böðn) — one of the vessels holding the skaldic mead in Norse mythology, the drink granting wisdom and inspiration.

## Hardware

| Component | Model | Interface |
|---|---|---|
| MCU | Olimex ESP32-S3-DevKit-Lipo (8 MB flash + 8 MB PSRAM) | USB-C, built-in LiPo charger |
| Battery | Olimex BATTERY-LIPO6600mAh | direct to DevKit-Lipo |
| Display | 1.8" 128×160 ST7735 TFT (DollaTek) | SPI |
| Microphone | INMP441 I2S MEMS | I2S IN |
| Amplifier | MAX98357A 3W class-D (AZDelivery) | I2S OUT |
| Speaker | 3W 8Ω mini speaker (Quarkzman) | wired to MAX98357A |
| Encoders | KY-040 rotary encoder × 3 (with push button) | GPIO + pull-up |
| Buttons | Mini momentary push buttons × 8 | GPIO + pull-up |
| Toggle switches | SPST mini toggle switches × 4 | GPIO + pull-up |
| LEDs | WS2812 8-LED sticks × 2 (16 addressable RGB) | NeoPixel (1 GPIO) |
| Power switch | Panel-mount toggle switch | — |

## Repository layout

```
bodn-esp32/
├─ firmware/
│  ├─ boot.py              # wifi / boot mode handling
│  ├─ main.py              # application entry point
│  ├─ st7735.py            # framebuf-based ST7735/ILI9341 display driver
│  └─ bodn/
│     ├─ __init__.py
│     ├─ config.py          # pin assignments, constants
│     ├─ debounce.py        # generic debounce logic
│     └─ encoder.py         # IRQ-based rotary encoder reader
├─ docs/
│  ├─ hardware.md           # BOM, board notes
│  ├─ wiring.md             # auto-generated pin diagram and tables
│  └─ roadmap.md            # milestones and progress
├─ tools/
│  ├─ pinout.py             # generate wiring docs from config.py
│  ├─ sync.sh               # deploy firmware to device via mpremote
│  └─ wokwi-sync.py         # deploy firmware to Wokwi simulator (raw TCP)
├─ tests/
│  ├─ conftest.py           # MicroPython hardware stubs
│  └─ test_*.py             # host-side unit tests
├─ .githooks/
│  └─ pre-commit            # ensures wiring.md stays in sync
├─ pyproject.toml            # host-side tooling (mpremote, ruff, black)
└─ README.md
```

## Common commands

```bash
# Install host tools
uv sync

# Deploy firmware to device
./tools/sync.sh

# Deploy firmware to Wokwi simulator (start simulator first)
uv run python tools/wokwi-sync.py

# Open a REPL on the device
uv run mpremote connect auto repl

# Lint
uv run ruff check firmware/

# Format
uv run black firmware/

# Wiring reference (terminal)
uv run python tools/pinout.py

# Regenerate docs/wiring.md
uv run python tools/pinout.py --md

# Run tests
uv run pytest
```

## Git hooks

Hooks live in `.githooks/` and are activated with `git config core.hooksPath .githooks`.

- **pre-commit**: if `firmware/bodn/config.py` is staged, verifies `docs/wiring.md` is up to date. If not, it regenerates the file and asks you to stage it.

## Roadmap

1. **Hardware bring-up** — ST7735 displaying text/graphics; buttons & encoders with debouncing.
2. **Audio basics** — play tones/samples via MAX98357A; record/playback short clips from INMP441.
3. **Kid-facing UI** — home screen with icons; modes for sounds, recording, and sequencing.
4. **Quality-of-life** — battery level indicator; serial/WiFi config; simple web UI for adults.
