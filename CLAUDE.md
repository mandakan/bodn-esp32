# Bodn ESP32 — AI assistant guidelines

## How to help

- **Target audience**: a 4-year-old child. Keep UX simple, colourful, and forgiving.
- **Language**: MicroPython on ESP32-S3. No C/C++ unless absolutely required.
- **Style**: keep modules small and self-contained. Prefer clarity over cleverness.
- **Hardware**: check `firmware/bodn/config.py` before assigning pins. Non-time-critical I/O (buttons, toggles, status LEDs) should use the MCP23017 I2C expanders; latency-sensitive peripherals (encoder CLK/DT, SPI, I2S) stay on native GPIOs. See `docs/hardware.md` for reserved pins and the GPIO budget.
- **SD card**: media assets (sound banks, arcade sounds, music, game-mode TTS, space SFX) live on `/sd/`. Only critical audio (UI SFX, battery/goodnight TTS) stays on flash. Use `from bodn.assets import resolve` to look up any asset path — it checks SD first, falls back to flash transparently. `tools/convert_audio.py` routes SD-bound output to `build/sounds/`; `tools/sd-sync.py` copies it to the card. See `docs/assets.md` for the directory structure. The SD card is mounted at boot; the device runs normally without one (soundboard falls back gracefully).
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
  - The `diagram.json` wires all 8 buttons (GPA0–7), 2 toggle switches (GPB0–1), and 5 arcade buttons (GPB2–3, GPB5–7) through `mcp1` — do not bypass these with direct ESP GPIO connections in the diagram
- **UX design**: when designing screens, game modes, interactions, or feedback, follow `docs/UX_GUIDELINES.md`. Key rules: one concept per screen, large icons over text, immediate multimodal feedback, max 3–4 active choices, no complex gestures. Games should target executive functions (working memory, inhibition, cognitive flexibility) at a 4-year-old level.
- **Developmental science docs**: `docs/science/` documents the research foundations behind each feature. When adding or significantly changing a game mode, update these files:
  - `docs/science/development_matrix.md` — add or update the feature's row in each aspect table, and revise the coverage/gap analysis if the balance shifts.
  - `docs/science/development_guide.md` — if the feature introduces or strengthens a developmental domain not yet covered, add a paragraph explaining it.
  - `docs/science/report.tex` — add or update the feature's `\subsubsection{}` in §4.1 (Feature–Domain Mapping) and its column in the coverage table (Table 1). Mark any new [TODO] sections for later expansion.
  - Rebuild `report.pdf` with `docs/science/build.sh` and commit it alongside the source changes.
- **Performance**: follow `docs/PERFORMANCE_GUIDELINES.md`. Key rules: event-driven over polling, no full-screen redraws every frame, cooperative async tasks, minimal per-frame allocations, sparse `print()` usage. The review checklist (section 10) applies to all code changes. Critical pitfalls: (1) screens with multiple independent regions must use **section-level dirty bitmasks**, not a single `_dirty` flag (§3.05); (2) cheap I2C LED writes (PCA9685) must not be bundled with expensive NeoPixel writes — different throttle rates (§3.2); (3) game/timing state must be updated in `update()`, never in `render()` — skipped renders cause state drift (§3.3).
- **Display DMA budget**: the `_spidma` module sends display data in 32 KB DMA chunks at 40 MHz SPI (configurable via `TFT_SPI_BAUDRATE` in `config.py`). The last chunk is async (Python returns immediately), all earlier chunks block. **If a dirty rect fits in one chunk (≤50 full-width rows on the primary display), the push costs only ~1 ms.** Each additional chunk adds ~6.5 ms of blocking. Design animations to stay within a narrow band (≤50 rows) whenever possible — see §3.0 in the performance guidelines. If displays show glitches, lower `TFT_SPI_BAUDRATE` to `26_000_000` — no firmware rebuild needed.
- **Sprites for scaled graphics**: never draw scaled icons or text pixel-by-pixel in `render()`. Use `make_icon_sprite()` / `make_label_sprite()` in `enter()` to pre-render into cached FrameBuffers, then `blit_sprite()` per frame. One `blit()` call replaces hundreds of `fill_rect()` calls. See `bodn/ui/widgets.py` for the API and `bodn/ui/home.py` for the reference pattern. Sprite buffers >8 KB go to PSRAM automatically.
- **Thermal safety**: the LiPo charger (BL4054B) and battery have NO hardware thermal protection — software is the only safeguard. Any new peripheral that draws significant power (LEDs, motors, RF) **must** be added to the power-shedding logic in `main.py` `housekeeping_task()`. Non-critical loads are disabled at ≥ 50 °C (critical) and the device deep-sleeps at ≥ 60 °C (emergency). See `docs/hardware.md` § "Thermal protection" for the escalation table.
- **i18n**: all user-facing UI strings go through `bodn/i18n.py`. Never hardcode display text in screen modules — use `from bodn.i18n import t` and `t("key")` or `t("key", arg)`. Swedish is the default language. String keys follow `screen_concept` naming (e.g. `simon_watch`, `pause_resume`). Translation files live in `firmware/bodn/lang/sv.py` and `firmware/bodn/lang/en.py`. When adding new strings, add to **both** language files. The `test_i18n.py` test enforces key parity. Extended font glyphs for å, ä, ö, Å, Ä, Ö are in `bodn/ui/font_ext.py`. The web UI stays in English (parent-facing).
- **TTS**: two TTS pipelines generate spoken audio offline with Piper TTS:
  - **i18n TTS** (`tools/generate_tts.py`): game instructions and system alerts from i18n STRINGS dicts. The allowlist and voice config live in `assets/audio/tts.json`. Flash keys (safety: `bat_critical`, `bat_low`, `overlay_goodnight`) go to `assets/audio/source/tts/{lang}/` → `firmware/sounds/tts/`. SD keys (game-mode-specific) stage in `build/tts/` → `build/tts_converted/`.
  - **Story TTS** (`tools/generate_story_tts.py`): narration and choice labels from story scripts in `assets/stories/*/script.py`. Output goes to `build/story_tts_raw/{story_id}/{lang}/`. Converted to device format and assembled into self-contained story packages under `build/stories/{story_id}/` (script.py + tts/{lang}/*.wav) by `tools/convert_audio.py`.
  - i18n TTS is converted to device format (16 kHz mono PCM) by `tools/convert_audio.py`. Story packages and i18n TTS are synced to the SD card by `tools/sd-sync.py`. On the device, i18n TTS uses `from bodn.tts import say`; story TTS resolves paths directly via `bodn.assets.resolve` from `/stories/{id}/tts/{lang}/{node}.wav`.

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
│  ├─ main.py              # async entry point (uasyncio)
│  ├─ st7735.py            # framebuf-based ST7735/ILI9341 driver (DMA or blocking SPI)
│  └─ bodn/
│     ├─ __init__.py
│     ├─ arcade.py          # arcade button input + LED output via MCP/PCA
│     ├─ audio.py           # AudioEngine (native core-0 C mixer or fallback viper)
│     ├─ chord.py           # multi-button chord/combo detection
│     ├─ cli.py             # serial REPL helpers (wifi, settings, reboot)
│     ├─ config.py          # pin assignments, constants, encoder sensitivity
│     ├─ debounce.py        # generic debounce logic
│     ├─ diag.py            # system diagnostics data gathering
│     ├─ encoder.py         # PCNT hardware rotary encoder (zero-CPU quadrature)
│     ├─ encoder_scope.py   # visual encoder oscilloscope (CLK/DT on TFT)
│     ├─ flode_rules.py     # Flöde puzzle engine (pure logic)
│     ├─ gesture.py         # tap/hold/long-press gesture detection
│     ├─ i2c_diag.py        # live I2C bus diagnostic tool (REPL)
│     ├─ i18n.py            # internationalisation: t(), set_language(), init()
│     ├─ lang/
│     │  ├─ sv.py           # Swedish string table (default)
│     │  └─ en.py           # English string table
│     ├─ life_rules.py      # Game of Life cellular automata (pure logic)
│     ├─ mcp23017.py        # MCP23017 I2C GPIO expander driver
│     ├─ mystery_rules.py   # Mystery Box rule engine (pure logic)
│     ├─ patterns.py        # LED animation patterns (shared buffer)
│     ├─ pca9685.py         # PCA9685 I2C PWM driver
│     ├─ power.py           # power management (sleep, wake, master switch)
│     ├─ qr.py              # minimal QR code encoder (V1-V2)
│     ├─ rulefollow_rules.py # Rule Follow game engine (pure logic)
│     ├─ session.py         # play session state machine (pure logic)
│     ├─ simon_rules.py     # Simon game engine (pure logic)
│     ├─ storage.py         # JSON settings & session history on flash
│     ├─ temperature.py     # DS18B20 + SoC temperature monitoring
│     ├─ tones.py           # procedural tone generation (pure logic)
│     ├─ wav.py             # WAV header parser + streaming reader (pure logic)
│     ├─ wifi.py            # WiFi connect (STA / AP) + mDNS + runtime control
│     ├─ web.py             # async HTTP server for parental controls
│     ├─ web_ui.py          # HTML/CSS/JS served to the browser
│     └─ ui/
│        ├─ admin_qr.py     # admin URL screen with QR code
│        ├─ ambient.py      # AmbientClock (content) + StatusStrip (status)
│        ├─ catface.py      # cat face with emotions (secondary content)
│        ├─ clock.py        # clock display mode
│        ├─ demo.py         # LED playground mode
│        ├─ diag.py         # on-device diagnostics screen
│        ├─ flode.py        # Flöde flow alignment puzzle
│        ├─ font_ext.py     # 8×8 bitmap glyphs for å ä ö Å Ä Ö
│        ├─ garden.py       # Garden of Life (cellular automata)
│        ├─ garden_secondary.py # Garden secondary display content
│        ├─ home.py         # home screen with carousel mode selection
│        ├─ icons.py        # 16×16 bitmap icons
│        ├─ input.py        # unified input state with debouncing
│        ├─ logo.py         # pixel art boot logo (Norse mead vessel)
│        ├─ mystery.py      # Mystery Box discovery game
│        ├─ overlay.py      # session state overlay
│        ├─ pause.py        # in-game pause menu (hold-to-open)
│        ├─ rulefollow.py   # Rule Follow game screen
│        ├─ screen.py       # Screen base class + ScreenManager
│        ├─ secondary.py    # two-zone secondary display manager
│        ├─ settings.py     # on-device settings menu (scrollable)
│        ├─ simon.py        # Simon memory game screen
│        ├─ theme.py        # colour palette and layout constants
│        └─ widgets.py      # stateless draw helpers
├─ docs/
│  ├─ audio.md              # audio file preparation guide
│  ├─ hardware.md           # BOM, board notes, pin assignments
│  ├─ wiring.md             # auto-generated pin diagram and tables
│  ├─ UX_GUIDELINES.md      # child-facing interaction design
│  ├─ PERFORMANCE_GUIDELINES.md  # ESP32 performance rules
│  └─ roadmap.md            # milestones and progress
├─ tools/
│  ├─ pinout.py             # generate wiring docs from config.py
│  ├─ sync.sh               # deploy firmware to device via mpremote
│  ├─ wokwi-sync.py         # deploy firmware to Wokwi simulator (raw TCP)
│  ├─ ota-push.py           # push firmware over WiFi via HTTP (no USB needed)
│  ├─ ftp-sync.py           # push firmware over WiFi via FTP (faster, STA mode only)
│  ├─ build-firmware.sh      # build custom MicroPython firmware with C modules
│  ├─ generate_story_tts.py  # generate story narration TTS from story scripts
│  ├─ story_preview.py      # preview story scripts in terminal
│  └─ sd-sync.py            # build + sync SD card assets (TTS, sounds, etc.)
├─ cmodules/                  # native C extensions (compiled into firmware)
│  ├─ micropython.cmake       # top-level cmake: includes sub-modules
│  ├─ audiomix/               # native audio mixer (_audiomix module, core 0)
│  │  ├─ micropython.cmake    # per-module cmake (INTERFACE lib)
│  │  ├─ audiomix.c/h         # Python bindings + shared types (16 uniform voices)
│  │  ├─ mixer.c/h            # FreeRTOS task: mix loop + I2S + step clock on core 0
│  │  ├─ ringbuf.c/h          # lock-free SPSC ring buffer
│  │  └─ tonegen.c/h          # sine/square/sawtooth/noise generators
│  └─ spidma/                 # DMA SPI display driver (_spidma module, ISR-driven)
│     ├─ micropython.cmake    # per-module cmake (INTERFACE lib)
│     └─ spidma.c/h           # Python bindings + ESP-IDF spi_master DMA
├─ boards/
│  └─ BODN_S3/                # custom board definition (external to MicroPython tree)
│     ├─ mpconfigboard.cmake  # sdkconfig layering (spiram_oct, I2S IRAM-safe)
│     ├─ mpconfigboard.h      # board name + MCU name
│     └─ sdkconfig.board      # dual-core, I2S ISR safety
├─ micropython/                # git submodule → micropython/micropython @ v1.27.0
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

# OTA firmware push via HTTP (works in AP and STA mode)
uv run python tools/ota-push.py               # AP mode (192.168.4.1)
uv run python tools/ota-push.py 192.168.1.42  # specific IP
uv run python tools/ota-push.py --wokwi        # Wokwi (localhost:9080)

# OTA firmware push via FTP (faster bulk sync — STA/home network only)
# Device must be in STA mode; credentials set via ftp_user/ftp_pass in settings
uv run python tools/ftp-sync.py 192.168.1.42       # specific IP
uv run python tools/ftp-sync.py 192.168.1.42 --force  # re-upload all files

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

# Custom firmware build (optional — enables native C audio mixer on core 1)
# One-time setup:
#   git submodule add https://github.com/micropython/micropython.git micropython
#   cd micropython && git checkout v1.27.0 && cd ..
#   git clone -b v5.5.1 --recursive https://github.com/espressif/esp-idf.git ~/esp-idf
#   ~/esp-idf/install.sh esp32s3
source ~/esp-idf/export.sh                        # once per terminal session
./tools/build-firmware.sh                          # build firmware
./tools/build-firmware.sh flash                    # build + flash
./tools/build-firmware.sh clean                    # clean build directory
# The custom firmware is stock MicroPython + _audiomix + _spidma C modules.
# If _audiomix is not available, AudioEngine falls back to the viper/IRQ path.
# If _spidma is not available, display writes fall back to blocking machine.SPI.

# SD card asset sync (build + copy in one step — runs all 3 steps above)
uv run python tools/sd-sync.py                    # auto-detect BODN* SD card on macOS
uv run python tools/sd-sync.py /Volumes/BODN_SD   # explicit mount point
uv run python tools/sd-sync.py --build-only        # build without copying
uv run python tools/sd-sync.py --no-build /Volumes/BODN_SD  # copy without rebuilding
uv run python tools/sd-sync.py --dry-run           # preview what would happen
```

## Git hooks

Hooks live in `.githooks/` and are activated with `git config core.hooksPath .githooks`.

- **pre-commit**: if `firmware/bodn/config.py` is staged, verifies `docs/wiring.md` is up to date. If not, it regenerates the file and asks you to stage it.

## Roadmap

1. **Hardware bring-up** — ST7735 displaying text/graphics; buttons & encoders with debouncing.
2. **Audio basics** — play tones/samples via MAX98357A; record/playback short clips from INMP441.
3. **Kid-facing UI** — home screen with icons; modes for sounds, recording, and sequencing.
4. **Quality-of-life** — battery level indicator; serial/WiFi config; simple web UI for adults.
