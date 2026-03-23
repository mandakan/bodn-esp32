# Bodn ESP32 — AI assistant guidelines

## How to help

- **Target audience**: a 4-year-old child. Keep UX simple, colourful, and forgiving.
- **Language**: MicroPython on ESP32-S3. No C/C++ unless absolutely required.
- **Style**: keep modules small and self-contained. Prefer clarity over cleverness.
- **Hardware**: check `firmware/bodn/config.py` before assigning pins. Non-time-critical I/O (buttons, toggles, status LEDs) should use the MCP23017 I2C expander; latency-sensitive peripherals (encoders, SPI, I2S) stay on native GPIOs. See `docs/hardware.md` for reserved pins and the GPIO budget.
- **Testing**: pure logic modules (debounce, UI state, audio format) are tested with `pytest` on the host. Hardware wrappers are tested on-device via `mpremote` or in Wokwi.
- **Dependencies**: host tools are managed with `uv`. MicroPython libs go directly into `firmware/`.
- **Pin assignments**: `firmware/bodn/config.py` is the single source of truth. Never hardcode GPIO numbers elsewhere.
- **Wiring docs**: `docs/wiring.md` is auto-generated. After changing `config.py`, run `uv run python tools/pinout.py --md` and commit both files. A pre-commit hook enforces this.
- **Wokwi sync**: `tools/wokwi-sync.py` auto-discovers all `.py` files under `firmware/`. New files are picked up automatically — no manual list to maintain. (`sync.sh` also copies the whole directory.)
- **Wokwi custom chip**: The MCP23017 GPIO expander is simulated via a custom Wokwi chip. The relevant files in the project root are:
  - `mcp23017.chip.json` — pin definitions
  - `mcp23017.chip.c` — C source implementing the register-addressed I2C protocol (`IODIRA/B`, `GPPUA/B`, `GPIOA/B`, `OLATA/B`)
  - `mcp23017.chip.wasm` — compiled binary that Wokwi loads (committed, must be kept in sync with the `.c` source)
  - `wokwi.toml` contains `[[chip]] name="mcp23017" binary="mcp23017.chip.wasm"` to register it
  - `wokwi-api.h` is a build artefact downloaded by the CLI — it is gitignored, do not commit it
  - If `mcp23017.chip.c` is changed, recompile and commit the new `.wasm`: `~/bin/wokwi-cli chip compile mcp23017.chip.c -o mcp23017.chip.wasm`
  - The `diagram.json` wires all 8 buttons (GPA0–7) and all 4 toggle switches (GPB0–3) through `mcp1` — do not bypass these with direct ESP GPIO connections in the diagram
- **UX design**: when designing screens, game modes, interactions, or feedback, follow `docs/UX_GUIDELINES.md`. Key rules: one concept per screen, large icons over text, immediate multimodal feedback, max 3–4 active choices, no complex gestures. Games should target executive functions (working memory, inhibition, cognitive flexibility) at a 4-year-old level.
- **Performance**: follow `docs/PERFORMANCE_GUIDELINES.md`. Key rules: event-driven over polling, no full-screen redraws every frame, cooperative async tasks, minimal per-frame allocations, sparse `print()` usage. The review checklist (section 10) applies to all code changes.
- **i18n**: all user-facing UI strings go through `bodn/i18n.py`. Never hardcode display text in screen modules — use `from bodn.i18n import t` and `t("key")` or `t("key", arg)`. Swedish is the default language. String keys follow `screen_concept` naming (e.g. `simon_watch`, `pause_resume`). Translation files live in `firmware/bodn/lang/sv.py` and `firmware/bodn/lang/en.py`. When adding new strings, add to **both** language files. The `test_i18n.py` test enforces key parity. Extended font glyphs for å, ä, ö, Å, Ä, Ö are in `bodn/ui/font_ext.py`. The web UI stays in English (parent-facing).

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
| Primary display | 2.8" 240×320 ILI9341 TFT with touch (AZDelivery) | SPI + XPT2046 touch |
| Secondary display | 1.8" 128×160 ST7735 TFT (DollaTek) | SPI (shared bus, separate CS) |
| Microphone | INMP441 I2S MEMS | I2S IN |
| Amplifier | MAX98357A 3W class-D (AZDelivery) | I2S OUT |
| Speaker | 3W 8Ω mini speaker (Quarkzman) | wired to MAX98357A |
| Encoders | KY-040 rotary encoder × 3 (with push button) | GPIO + pull-up |
| Buttons | Mini momentary push buttons × 8 | GPIO + pull-up |
| Toggle switches | SPST mini toggle switches × 4 | GPIO + pull-up |
| LED sticks | WS2812 8-LED modules × 2 (on lid) | NeoPixel (1 GPIO, daisy-chained) |
| LED strip | WS2812B 144 LED/m strip, 640 mm / ~92 LEDs (inside lid perimeter) | NeoPixel (chained after sticks) |
| GPIO expander | Waveshare MCP23017 16-IO board | I2C (addr 0x20) |
| DC-DC converter | Buck-boost 3–16 V → 5 V / 2 A | LiPo → 5 V for NeoPixels |
| Temperature sensors | DS18B20 × 2 (battery + enclosure) | 1-Wire (GPIO 20) |
| Power switch | Panel-mount toggle switch | — |

## Repository layout

```
bodn-esp32/
├─ firmware/
│  ├─ boot.py              # WiFi setup, NTP sync, load settings
│  ├─ main.py              # async entry point (uasyncio)
│  ├─ st7735.py            # framebuf-based ST7735/ILI9341 display driver
│  └─ bodn/
│     ├─ __init__.py
│     ├─ audio.py           # async AudioEngine (3-channel priority playback)
│     ├─ config.py          # pin assignments, constants
│     ├─ debounce.py        # generic debounce logic
│     ├─ i18n.py            # internationalisation: t(), set_language(), init()
│     ├─ lang/
│     │  ├─ sv.py           # Swedish string table (default)
│     │  └─ en.py           # English string table
│     ├─ encoder.py         # IRQ-based rotary encoder reader
│     ├─ patterns.py        # LED animation patterns (shared buffer)
│     ├─ mystery_rules.py   # Mystery Box rule engine (pure logic)
│     ├─ session.py         # play session state machine (pure logic)
│     ├─ storage.py         # JSON settings & session history on flash
│     ├─ temperature.py     # DS18B20 1-Wire temperature monitoring
│     ├─ tones.py           # procedural tone generation (pure logic)
│     ├─ wav.py             # WAV header parser + streaming reader (pure logic)
│     ├─ wifi.py            # WiFi connect (STA / AP) + runtime control
│     ├─ web.py             # async HTTP server for parental controls
│     ├─ web_ui.py          # HTML/CSS/JS served to the browser
│     └─ ui/
│        ├─ screen.py       # Screen base class + ScreenManager
│        ├─ theme.py        # colour palette and layout constants
│        ├─ font_ext.py     # 8×8 bitmap glyphs for å ä ö Å Ä Ö
│        ├─ input.py        # unified input state with debouncing
│        ├─ widgets.py      # stateless draw helpers
│        ├─ icons.py        # 16×16 bitmap icons
│        ├─ home.py         # home screen with mode selection
│        ├─ demo.py         # LED playground mode
│        ├─ mystery.py      # Mystery Box discovery game
│        ├─ clock.py        # clock display mode
│        ├─ ambient.py      # AmbientClock (content) + StatusStrip (status)
│        ├─ catface.py      # cat face with emotions (secondary content)
│        ├─ settings.py     # on-device settings menu
│        ├─ overlay.py      # session state overlay
│        ├─ pause.py        # in-game pause menu
│        └─ secondary.py    # two-zone secondary display manager
├─ docs/
│  ├─ audio.md              # audio file preparation guide
│  ├─ hardware.md           # BOM, board notes
│  ├─ wiring.md             # auto-generated pin diagram and tables
│  ├─ UX_GUIDELINES.md      # child-facing interaction design
│  ├─ PERFORMANCE_GUIDELINES.md  # ESP32 performance rules
│  └─ roadmap.md            # milestones and progress
├─ tools/
│  ├─ pinout.py             # generate wiring docs from config.py
│  ├─ sync.sh               # deploy firmware to device via mpremote
│  ├─ wokwi-sync.py         # deploy firmware to Wokwi simulator (raw TCP)
│  └─ ota-push.py           # push firmware over WiFi (no USB needed)
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

# Parental controls web UI
# On real hardware: connect to Bodn AP, open http://192.168.4.1
# In Wokwi: requires Wokwi Private Gateway for inbound port forwarding
# Without gateway, test via REPL: import boot; boot.settings["lockdown"] = True

# OTA firmware push (no USB needed)
uv run python tools/ota-push.py               # AP mode (192.168.4.1)
uv run python tools/ota-push.py 192.168.1.42  # specific IP
uv run python tools/ota-push.py --wokwi        # Wokwi (localhost:9080)
```

## Git hooks

Hooks live in `.githooks/` and are activated with `git config core.hooksPath .githooks`.

- **pre-commit**: if `firmware/bodn/config.py` is staged, verifies `docs/wiring.md` is up to date. If not, it regenerates the file and asks you to stage it.

## Roadmap

1. **Hardware bring-up** — ST7735 displaying text/graphics; buttons & encoders with debouncing.
2. **Audio basics** — play tones/samples via MAX98357A; record/playback short clips from INMP441.
3. **Kid-facing UI** — home screen with icons; modes for sounds, recording, and sequencing.
4. **Quality-of-life** — battery level indicator; serial/WiFi config; simple web UI for adults.
