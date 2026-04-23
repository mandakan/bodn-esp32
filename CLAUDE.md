# Bodn ESP32 — AI assistant guidelines

## How to help

- **Target audience**: a 4-year-old child. Keep UX simple, colourful, and forgiving.
- **Language**: MicroPython on ESP32-S3. No C/C++ unless absolutely required.
- **Style**: keep modules small and self-contained. Prefer clarity over cleverness.
- **Hardware**: check `firmware/bodn/config.py` before assigning pins. Non-time-critical I/O (buttons, toggles, status LEDs) should use the MCP23017 I2C expanders; latency-sensitive peripherals (encoder CLK/DT, SPI, I2S) stay on native GPIOs. See `docs/hardware.md` for reserved pins and the GPIO budget.
- **SD card**: media assets (sound banks, arcade sounds, music, game-mode TTS, space SFX, story packages, hand-recorded voices) live on `/sd/`. Only critical audio (UI SFX, battery/goodnight TTS) stays on flash. Use `from bodn.assets import resolve` to look up any asset path — it checks SD first, falls back to flash transparently. `tools/convert_audio.py` routes SD-bound output to `build/sounds/`; `tools/sd-sync.py` copies it to the card. See `docs/assets.md` for the directory structure. The SD card is mounted at boot; the device runs normally without one (soundboard falls back gracefully).
- **Testing**: pure logic modules (debounce, UI state, audio format) are tested with `pytest` on the host. Hardware wrappers are tested on-device via `mpremote` or in Wokwi. MicroPython compatibility tests (`tests/test_micropython_compat.py`) import firmware modules under the real MicroPython Unix port to catch CPython-only APIs (e.g. `str.capitalize()`) before they reach the device. These tests are skipped if the Unix port binary hasn't been built — see "MicroPython Unix port" below for setup.
- **MicroPython portability**: MicroPython `str` lacks `.capitalize()`, `.title()`, `.swapcase()`, and `.casefold()`. Use `from bodn.i18n import capitalize` instead. The compat tests catch this automatically.
- **Dependencies**: host tools are managed with `uv`. MicroPython libs go directly into `firmware/`.
- **Pin assignments**: `firmware/bodn/config.py` is the single source of truth. Never hardcode GPIO numbers elsewhere. After editing it, regenerate `docs/wiring.md` (see the `wiring-sync` skill — a pre-commit hook enforces this).
- **Wokwi sync**: `tools/wokwi-sync.py` auto-discovers all `.py` files under `firmware/`. New files are picked up automatically. The MCP23017 GPIO expander runs as a custom Wokwi chip — the committed `mcp23017.chip.wasm` must stay in sync with `mcp23017.chip.c` (see the `wokwi-chip-rebuild` skill). The `diagram.json` routes all buttons, toggles, and arcade buttons through `mcp1`; do not bypass with direct ESP GPIO connections.
- **UX design**: when designing screens, game modes, interactions, or feedback, follow `docs/UX_GUIDELINES.md`. Key rules: one concept per screen, large icons over text, immediate multimodal feedback, max 3–4 active choices, no complex gestures. Games should target executive functions (working memory, inhibition, cognitive flexibility) at a 4-year-old level.
- **Developmental science docs**: `docs/science/` maps each feature to developmental domains. When adding or significantly changing a game mode, update `development_matrix.md`, `development_guide.md`, `report.tex`, and rebuild `report.pdf` — see the `add-game-mode` skill for the exact procedure.
- **Performance**: follow `docs/PERFORMANCE_GUIDELINES.md` and apply the `perf-review` skill to new/changed firmware. Top rules: event-driven over polling, cooperative async tasks, no full-screen redraws every frame. Three pitfalls: (1) single `_dirty` flag on multi-region screens — use a section bitmask (§3.05); (2) bundling cheap I2C LED writes with expensive NeoPixel writes (§3.2); (3) updating game/timing state in `render()` instead of `update()` — skipped renders drift (§3.3). Keep animated dirty rects ≤ 50 full-width rows (1 DMA chunk, ~1 ms). Pre-render scaled icons/text as sprites in `enter()` via `make_icon_sprite()` / `make_label_sprite()`; blit per frame.
- **Thermal safety**: the LiPo charger (BL4054B) and battery have NO hardware thermal protection — software is the only safeguard. Any new peripheral that draws significant power (LEDs, motors, RF) **must** be added to the power-shedding logic in `main.py` `housekeeping_task()`. Non-critical loads are disabled at ≥ 50 °C (critical) and the device deep-sleeps at ≥ 60 °C (emergency). See `docs/hardware.md` § "Thermal protection" for the escalation table.
- **i18n**: all user-facing UI strings go through `bodn/i18n.py` (`t("key")`); never hardcode display text. Swedish is the default, English is secondary. Keys follow `screen_concept` naming. When adding strings, add to **both** `firmware/bodn/lang/sv.py` and `en.py` — see the `add-i18n-string` skill. Extended glyphs for å, ä, ö, Å, Ä, Ö are in `bodn/ui/font_ext.py`. The web UI stays in English (parent-facing).
- **TTS and hand-recordings**: two offline Piper TTS pipelines feed spoken audio — i18n TTS (`tools/generate_tts.py`) and story TTS (`tools/generate_story_tts.py`). Any TTS line can be overridden by dropping a WAV in the matching recordings directory; filenames must match the TTS key/node exactly. `bodn.assets.resolve_voice()` resolves `recording > TTS`, SD first then flash. See the `tts-pipeline` skill for the generate → convert → sync procedure and the recording override footgun.

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
| Encoders | KY-040 rotary encoder × 2 (with push button) | GPIO + pull-up |
| Buttons | Mini momentary push buttons × 8 | GPIO + pull-up |
| Toggle switches | SPST mini toggle switches × 2 | MCP23017 I2C expander |
| LED sticks | WS2812 8-LED modules × 2 (on lid) | NeoPixel (1 GPIO, daisy-chained) |
| LED strip | WS2812B 144 LED/m strip, 640 mm / ~92 LEDs (inside lid perimeter) | NeoPixel (chained after sticks) |
| GPIO expanders | CJMCU-2317 MCP23017 16-IO boards × 2 | I2C (MCP1 0x23, MCP2 0x21) |
| DC-DC converter | Buck-boost 3–16 V → 5 V / 2 A | LiPo → 5 V for NeoPixels |
| Temperature sensors | DS18B20 × 2 (battery + enclosure) | 1-Wire (GPIO 20) |
| Power switch | Panel-mount toggle switch | — |

## Repository layout

```
bodn-esp32/
├─ firmware/
│  ├─ boot.py              # WiFi setup, NTP sync, battery check, boot screen
│  ├─ main.py              # async entry point (uasyncio) + housekeeping/thermal task
│  ├─ sdcard.py            # SPI SD card driver (native-optimised for audio streaming)
│  ├─ st7735.py            # framebuf-based ST7735/ILI9341 driver (DMA or blocking SPI)
│  └─ bodn/
│     ├─ __init__.py
│     ├─ arcade.py          # arcade button input + LED output via MCP/PCA
│     ├─ assets.py          # SD-first / flash-fallback asset path resolver
│     ├─ audio.py           # AudioEngine (native core-0 C mixer or fallback viper)
│     ├─ battery.py         # battery level reading and USB-only detection
│     ├─ chord.py           # multi-button chord/combo detection
│     ├─ cli.py             # serial REPL helpers (wifi, settings, reboot)
│     ├─ config.py          # pin assignments, constants, encoder sensitivity
│     ├─ debounce.py        # generic debounce logic
│     ├─ diag.py            # system diagnostics data gathering
│     ├─ encoder.py         # PCNT hardware rotary encoder (zero-CPU quadrature)
│     ├─ encoder_scope.py   # visual encoder oscilloscope (CLK/DT on TFT)
│     ├─ flode_rules.py     # Flöde puzzle engine (pure logic)
│     ├─ gesture.py         # tap/hold/long-press gesture detection
│     ├─ highfive_rules.py  # High-Five Friends reflex game engine (pure logic)
│     ├─ i2c_diag.py        # live I2C bus diagnostic tool (REPL)
│     ├─ i18n.py            # internationalisation: t(), set_language(), init()
│     ├─ lang/
│     │  ├─ sv.py           # Swedish string table (default)
│     │  └─ en.py           # English string table
│     ├─ life_presets.py    # curated Game of Life seed patterns
│     ├─ life_rules.py      # Game of Life cellular automata (pure logic)
│     ├─ mcp23017.py        # MCP23017 I2C GPIO expander driver
│     ├─ mystery_rules.py   # Mystery Box rule engine (pure logic)
│     ├─ native_i2c.py      # native C I2C wrapper for deterministic scans
│     ├─ neo.py             # NeoPixel facade over the native _neopixel C engine
│     ├─ nfc.py             # NFC tag parsing, NDEF records, card sets, UID cache
│     ├─ patterns.py        # LED animation patterns (shared buffer)
│     ├─ pca9685.py         # PCA9685 I2C PWM driver (arcade button LEDs)
│     ├─ pn532.py           # PN532 NFC reader driver (I2C, polling task)
│     ├─ power.py           # power management (sleep, wake, master switch)
│     ├─ qr.py              # minimal QR code encoder (V1-V2)
│     ├─ rakna_rules.py     # Räkna math game engine (levels 1–6, pure logic)
│     ├─ rulefollow_rules.py # Rule Follow game engine (pure logic)
│     ├─ sdcard.py          # SD card initialisation and mount
│     ├─ sequencer_rules.py # loop Sequencer timing and step model (pure logic)
│     ├─ session.py         # play session state machine (pure logic)
│     ├─ simon_rules.py     # Simon game engine (pure logic)
│     ├─ sortera_rules.py   # Sortera classification game engine (pure logic)
│     ├─ soundboard_rules.py # Soundboard bank/slot model (pure logic)
│     ├─ sounds.py          # sound asset catalogue
│     ├─ space_rules.py     # Spaceship cockpit state machine (pure logic)
│     ├─ storage.py         # JSON settings & session history on flash
│     ├─ stories/           # story package — scripts discovered at runtime on SD
│     ├─ story_rules.py     # story graph validation + traversal (pure logic)
│     ├─ temperature.py     # DS18B20 + SoC temperature monitoring
│     ├─ tones.py           # procedural tone generation (pure logic)
│     ├─ tts.py             # TTS playback helper (SD-first voice resolution)
│     ├─ wav.py             # WAV header parser + streaming reader (pure logic)
│     ├─ wifi.py            # WiFi connect (STA / AP) + mDNS + runtime control
│     ├─ web.py             # async HTTP server for parental controls
│     ├─ web_ui.py          # HTML/CSS/JS served to the browser
│     └─ ui/
│        ├─ admin_qr.py     # admin URL screen with QR code
│        ├─ ambient.py      # AmbientClock (content) + StatusStrip (status)
│        ├─ android.py      # boot-time Android-style status bar helper
│        ├─ catface.py      # cat face with emotions (secondary content)
│        ├─ clock.py        # clock display mode
│        ├─ demo.py         # LED playground mode
│        ├─ diag.py         # on-device diagnostics screen
│        ├─ draw.py         # wrapper around the native _draw C module
│        ├─ flode.py        # Flöde flow alignment puzzle
│        ├─ font_ext.py     # 8×8 bitmap glyphs for å ä ö Å Ä Ö
│        ├─ garden.py       # Garden of Life (cellular automata)
│        ├─ garden_secondary.py # Garden secondary display content
│        ├─ highfive.py     # High-Five Friends reflex game screen
│        ├─ home.py         # home screen with carousel mode selection
│        ├─ icon_browser.py # OpenMoji emoji sprite browser (settings)
│        ├─ icons.py        # 16×16 bitmap icons (flash fallback)
│        ├─ input.py        # unified input state with debouncing
│        ├─ logo.py         # pixel art boot logo (Norse mead vessel)
│        ├─ mystery.py      # Mystery Box discovery game
│        ├─ nfc_provision.py # NFC card set viewer + tag programming
│        ├─ overlay.py      # session state overlay
│        ├─ pause.py        # in-game pause menu (hold-to-open)
│        ├─ rakna.py        # Räkna NFC math game screen
│        ├─ rulefollow.py   # Rule Follow game screen
│        ├─ screen.py       # Screen base class + ScreenManager
│        ├─ secondary.py    # two-zone secondary display manager
│        ├─ sequencer.py    # loop Sequencer mode
│        ├─ sequencer_secondary.py # Sequencer secondary display content
│        ├─ settings.py     # on-device settings menu (scrollable)
│        ├─ simon.py        # Simon memory game screen
│        ├─ sortera.py      # Sortera NFC classification game
│        ├─ soundboard.py   # Soundboard discovery mode
│        ├─ soundboard_secondary.py # Soundboard secondary display content
│        ├─ space.py        # Spaceship cockpit mode
│        ├─ story.py        # branching story mode (scripts + TTS on SD)
│        ├─ theme.py        # colour palette and layout constants
│        └─ widgets.py      # stateless draw helpers + sprite cache
├─ docs/
│  ├─ assets.md             # SD/flash asset layout and resolver rules
│  ├─ audio.md              # audio file preparation guide
│  ├─ audio_assets.md       # sound asset pipeline, drum kits, recordings
│  ├─ getting-started.md    # first-boot walkthrough (flashing, serial, debugging)
│  ├─ hardware.md           # BOM, board notes, pin assignments
│  ├─ nfc.md                # NFC tag format, card sets, provisioning
│  ├─ PERFORMANCE_GUIDELINES.md  # ESP32 performance rules
│  ├─ protoboard_layout.md  # hand-wired protoboard reference
│  ├─ roadmap.md            # milestones and progress
│  ├─ schematics/           # reference images for DevKit, GPIO, power supply
│  ├─ science/              # development matrix, guide, report.tex/pdf/bib
│  ├─ soundboard.md         # soundboard bank layout and manifest
│  ├─ story_authoring.md    # branching story authoring guide
│  ├─ UX_GUIDELINES.md      # child-facing interaction design
│  └─ wiring.md             # auto-generated pin diagram and tables
├─ tools/
│  ├─ pinout.py             # generate wiring docs from config.py
│  ├─ deploy.sh             # top-level deploy entry point (auto-detects USB/WiFi)
│  ├─ sync.sh               # USB sync via mpremote (used by deploy.sh --usb)
│  ├─ wokwi-sync.py         # deploy firmware to Wokwi simulator (raw TCP)
│  ├─ wokwi-push.py         # push a single file into a running Wokwi sim
│  ├─ ota-push.py           # WiFi push via HTTP (used by deploy.sh --wifi)
│  ├─ build-firmware.sh     # build custom MicroPython firmware with C modules
│  ├─ generate_tts.py       # generate i18n TTS WAVs from STRINGS dicts
│  ├─ generate_story_tts.py # generate story narration TTS from story scripts
│  ├─ convert_audio.py      # convert all audio sources to device format
│  ├─ story_preview.py      # preview story scripts in terminal / browser
│  ├─ sd-sync.py            # build + sync SD card assets (TTS, sounds, etc.)
│  ├─ generate_cards.py     # NFC card face PDF generator (OpenMoji → A4 PDF)
│  ├─ convert_icons.py      # OpenMoji SVG → BDF sprite conversion for on-screen icons
│  ├─ import_freesound.py   # import and licence-track Freesound.org samples
│  └─ make_asset.py         # rasterise SVG sources into 4bpp BDF sprites
├─ cmodules/                  # native C extensions (compiled into firmware)
│  ├─ micropython.cmake       # top-level cmake: includes sub-modules
│  ├─ audiomix/               # native audio mixer (_audiomix module, core 0)
│  │  ├─ micropython.cmake    # per-module cmake (INTERFACE lib)
│  │  ├─ audiomix.c/h         # Python bindings + shared types (16 uniform voices)
│  │  ├─ mixer.c/h            # FreeRTOS task: mix loop + I2S + step clock on core 0
│  │  ├─ ringbuf.c/h          # lock-free SPSC ring buffer
│  │  └─ tonegen.c/h          # sine/square/sawtooth/noise generators
│  ├─ spidma/                 # DMA SPI display driver (_spidma module, ISR-driven)
│  │  ├─ micropython.cmake    # per-module cmake (INTERFACE lib)
│  │  └─ spidma.c/h           # Python bindings + ESP-IDF spi_master DMA
│  ├─ draw/                   # bitmap fonts, sprite blit, primitives (_draw module)
│  │  ├─ micropython.cmake    # per-module cmake (INTERFACE lib)
│  │  ├─ draw.c/h             # Python bindings
│  │  ├─ primitives.c/h       # fill_rect, hline/vline, blit helpers
│  │  ├─ blit.c/h             # sprite blit with optional alpha
│  │  ├─ decode.c/h           # BDF sprite decoder (1/2/4/8 bpp)
│  │  ├─ font_render.c/h      # bitmap font rasteriser
│  │  └─ fonts/               # compiled BDF font headers
│  ├─ mcpinput/               # deterministic MCP23017 input scanner (_mcpinput)
│  │  ├─ micropython.cmake    # per-module cmake (INTERFACE lib)
│  │  ├─ mcpinput.c/h         # Python bindings + core 1 scan task
│  │  └─ scanner.c/h          # I2C read loop + edge detection
│  └─ neopixel/               # NeoPixel pattern engine (_neopixel module)
│     ├─ micropython.cmake    # per-module cmake (INTERFACE lib)
│     ├─ neopixel_mod.c/h     # Python bindings
│     ├─ engine.c/h           # animation engine (tick, blend, frame buffer)
│     └─ patterns.c/h         # built-in animations (breathe, chase, rainbow, …)
├─ boards/
│  └─ BODN_S3/                # custom board definition (external to MicroPython tree)
│     ├─ mpconfigboard.cmake  # sdkconfig layering (spiram_oct, I2S IRAM-safe)
│     ├─ mpconfigboard.h      # board name + MCU name
│     └─ sdkconfig.board      # dual-core, I2S ISR safety
├─ micropython/                # git submodule → micropython/micropython @ v1.27.0
├─ tests/
│  ├─ conftest.py              # MicroPython hardware stubs
│  ├─ test_micropython_compat.py # import tests under real MicroPython Unix port
│  └─ test_*.py                # host-side unit tests
├─ web/                        # bodn.thias.se — NFC card info landing page
│  ├─ docker-compose.yml      # single-service compose (nginx)
│  ├─ Dockerfile              # nginx:alpine + static HTML + card set JSONs
│  ├─ nginx.conf              # SPA routing + /nfc/ JSON serving
│  └─ public/
│     └─ index.html           # card viewer (parses URL path, shows emoji + labels)
├─ .githooks/
│  └─ pre-commit              # ensures wiring.md stays in sync, checks formatting
├─ pyproject.toml             # host-side tooling (mpremote, ruff, black)
└─ README.md
```

## Common commands

```bash
# Install host tools
uv sync

# Deploy firmware to device (auto-detects USB vs WiFi)
./tools/deploy.sh                         # auto (WiFi via bodn.local if resolvable, else USB)
./tools/deploy.sh --usb                   # force USB
./tools/deploy.sh --wifi 192.168.1.143    # force WiFi to a specific IP
./tools/deploy.sh --mount                 # live-mount firmware/ over USB (no copy; edits are live)
./tools/deploy.sh --force                 # re-upload all files (WiFi path)

# Underlying tools (deploy.sh picks one):
./tools/sync.sh                           # USB sync via mpremote
uv run python tools/ota-push.py HOST       # WiFi push via HTTP

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

# MicroPython Unix port (one-time build — catches CPython-only APIs in tests)
# Requires: Xcode command-line tools (macOS) or build-essential (Linux)
make -C micropython/mpy-cross                     # build the cross-compiler
make -C micropython/ports/unix submodules          # init Unix port dependencies
make -C micropython/ports/unix                     # build the Unix port binary
# After building, `uv run pytest` automatically includes the MicroPython
# import-compatibility suite. If the binary isn't built, they skip gracefully.

# Parental controls web UI
# On real hardware: connect to Bodn AP, open http://192.168.4.1
# In Wokwi: requires Wokwi Private Gateway for inbound port forwarding
# Without gateway, test via REPL: import boot; boot.settings["lockdown"] = True

# OTA firmware push via HTTP (works in AP and STA mode — use deploy.sh normally)
uv run python tools/ota-push.py               # AP mode (192.168.4.1)
uv run python tools/ota-push.py 192.168.1.42  # specific IP
uv run python tools/ota-push.py --wokwi        # Wokwi (localhost:9080)

# TTS pipeline (generate spoken audio from i18n strings + story scripts)
# Install Piper TTS once: pip install piper-tts
uv run python tools/generate_tts.py               # generate i18n TTS WAVs
uv run python tools/generate_tts.py --dry-run     # preview without generating
uv run python tools/generate_tts.py --lang sv      # Swedish only
uv run python tools/generate_tts.py --key simon_watch  # single key
uv run python tools/generate_story_tts.py          # generate story narration TTS
uv run python tools/generate_story_tts.py --dry-run  # preview
uv run python tools/generate_story_tts.py --story peter_rabbit  # single story
uv run python tools/convert_audio.py              # convert all audio to device format

# Custom firmware build (optional — enables native C audio mixer on core 0)
# One-time setup:
#   git submodule add https://github.com/micropython/micropython.git micropython
#   cd micropython && git checkout v1.27.0 && cd ..
#   git clone -b v5.5.1 --recursive https://github.com/espressif/esp-idf.git ~/esp-idf
#   ~/esp-idf/install.sh esp32s3
source ~/esp-idf/export.sh                        # once per terminal session
./tools/build-firmware.sh                          # build firmware
./tools/build-firmware.sh flash                    # build + flash
./tools/build-firmware.sh clean                    # clean build directory
# The custom firmware is stock MicroPython + _audiomix, _spidma, _draw,
# _mcpinput, and _neopixel C modules. Each has a Python fallback:
#   _audiomix  → AudioEngine falls back to the viper/IRQ path
#   _spidma    → display writes fall back to blocking machine.SPI
#   _draw      → bodn.ui.draw falls back to pure-Python framebuf helpers
#   _mcpinput  → MCP23017 input scanned on the main loop
#   _neopixel  → bodn.neo falls back to the built-in neopixel module

# SD card asset sync (build + copy in one step — runs all 3 steps above)
uv run python tools/sd-sync.py                    # auto-detect BODN* SD card on macOS
uv run python tools/sd-sync.py /Volumes/BODN_SD   # explicit mount point
uv run python tools/sd-sync.py --build-only        # build without copying
uv run python tools/sd-sync.py --no-build /Volumes/BODN_SD  # copy without rebuilding
uv run python tools/sd-sync.py --dry-run           # preview what would happen

# OpenMoji setup (one-time, ~200 MB — used by card generator + icon converter)
# All OpenMoji tools check: --openmoji flag > $OPENMOJI_DIR > ~/openmoji
git clone --depth 1 https://github.com/hfg-gmuend/openmoji.git ~/openmoji
# Or set env var: export OPENMOJI_DIR=/path/to/openmoji

# NFC card face PDF generator
uv run python tools/generate_cards.py                        # generate all card PDFs
uv run python tools/generate_cards.py --set sortera          # specific set
uv run python tools/generate_cards.py --dry-run              # preview without generating

# OpenMoji on-screen icon conversion (SVG → BDF sprites for home screen)
# sd-sync.py runs this automatically as step 5 of the build pipeline
uv run python tools/convert_icons.py                         # convert all emoji icons
uv run python tools/convert_icons.py --dry-run               # preview without converting
uv run python tools/convert_icons.py --force                 # force rebuild all
```

## NFC card info site (bodn.thias.se)

```bash
# Build and run locally
cd web && docker compose up --build         # serves at http://localhost:8080

# Test card URLs
open http://localhost:8080/1/sortera/cat_red  # game card
open http://localhost:8080/1/simon            # launcher card
open http://localhost:8080/                   # landing page
```

The site is a single-page app that parses the URL path, fetches card set
JSONs from `/nfc/*.json`, and displays the card's OpenMoji emoji, bilingual
labels, and a link to the GitHub project. Card set JSONs from `assets/nfc/`
are baked into the Docker image at build time.

## Git hooks

Hooks live in `.githooks/` and are activated with `git config core.hooksPath .githooks`.

- **pre-commit**: if `firmware/bodn/config.py` is staged, verifies `docs/wiring.md` is up to date. If not, it regenerates the file and asks you to stage it.

## Roadmap

See [`docs/roadmap.md`](docs/roadmap.md) for the authoritative milestone
breakdown. Status at a glance:

1. **Hardware bring-up** — complete (dual displays, inputs, LEDs, thermal).
2. **Audio basics** — complete (16-voice native C mixer, TTS, hand-recordings).
   Record/replay from INMP441 still outstanding.
3. **Kid-facing UI** — 12 game modes shipped (Mystery, Simon, Flöde, Rule
   Follow, Garden, Soundboard, Sequencer, High-Five, Space, Story, Sortera,
   Räkna). Record & replay still planned.
4. **Parental controls** — complete (web UI, session limits, PIN, OTA).
5. **Quality-of-life** — complete (battery, thermal, diagnostics, SD card,
   asset resolver, custom firmware build, boot-log persistence).
6. **NFC card games** — PN532 driver + provisioning UI shipped; Sortera,
   Räkna, and launcher card sets live. More card sets planned.
