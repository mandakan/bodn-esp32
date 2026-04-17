# Roadmap

## Milestone 1: Hardware bring-up

- [x] Flash MicroPython onto ESP32-S3-DevKit-Lipo
- [x] Get ST7735 / ILI9341 displaying text and basic graphics
- [x] Read button presses with debouncing
- [x] Read rotary encoder rotation and button press with velocity tracking
- [x] Backlight and arcade button LEDs via PWM (PCA9685)
- [x] MCP23017 GPIO expander (buttons, toggles, arcade buttons)
- [x] WS2812 LED sticks + WS2812B lid ring strip (zone-aware LED architecture)
- [x] DS18B20 temperature monitoring (battery + enclosure) with thermal protection
- [x] DC-DC 5 V converter for NeoPixel power rail
- [x] No-battery detection for USB-only operation
- [x] Dual-display support (primary ILI9341 + secondary ST7735, shared SPI bus)
- [x] Custom Wokwi chip simulating MCP23017 over I2C

## Milestone 2: Audio basics

- [x] Play simple tones through MAX98357A (procedural tone generation)
- [x] Play WAV samples from flash and SD card (streaming WAV reader + audio engine)
- [x] Multi-channel audio mixing (16 uniform voices, priority channels)
- [x] Native C audio mixer on core 0 (`_audiomix`), with viper/IRQ fallback
- [x] Sample-accurate step clock for sequencer and clock-driven tone tracks
- [x] Click feedback on UI interactions
- [x] Volume control via rotary encoder
- [x] Audio asset pipeline with EBU R128 loudness normalisation
- [x] Offline Piper TTS pipeline (Swedish + English) with flash/SD split
- [x] Hand-recorded WAV overrides (recording > TTS at each storage layer)
- [ ] Record short clips from INMP441 into RAM
- [ ] Playback recorded clips

## Milestone 3: Kid-facing UI

- [x] Home screen with colourful OpenMoji carousel (velocity-aware slide, sprite cache)
- [x] Gesture layer: tap, double-tap, long-press on all buttons
- [x] Multi-button chord / combo detection
- [x] **Mystery Box** — colour discovery game with hue-shift feedback
- [x] **Simon** — pattern memory game (pattern copy / repeat)
- [x] **Flöde** — flow-alignment spatial puzzle
- [x] **Rule Follow** — inhibition & cognitive flexibility game
- [x] **Garden of Life** — Conway's Game of Life with interactive seeding
- [x] **Soundboard** — discovery mode mapping buttons to sounds
- [x] **Sequencer** — chain tones and LED steps into a loop (C-driven timing)
- [x] **High-Five Friends** — reflex game with C-driven arcade LEDs
- [x] **Spaceship** — cockpit mode with arcade buttons, ambience, and SFX
- [x] **Story Mode** — branching stories read aloud via SD-loaded TTS packages
- [x] **Sortera** — NFC classification game (DCCS-style, 16 animal cards)
- [x] **Räkna** — NFC math game (levels 1–6, from counting to symbolic equations)
- [x] Pause menu (hold-to-open), session overlay, in-game wind-down animation
- [x] Secondary display content per game mode (cat face, ambient clock, status strip)
- [x] i18n with Swedish default and English fallback (å/ä/ö extended font glyphs)
- [x] NFC launcher cards — tap a card to jump straight into any mode
- [ ] "Record & replay" mode — record voice and play back on button press

## Milestone 4: Parental controls

- [x] WiFi connect (AP mode + STA mode) + mDNS
- [x] NTP time sync at boot with DST-aware timezone support
- [x] Session state machine (play limits, break timer, quiet hours, lockdown)
- [x] Settings and session history persisted to flash (JSON)
- [x] Async web server on device (uasyncio)
- [x] Web UI for parents (dashboard, limits, history, WiFi config)
- [x] Session-aware LED animations (amber warnings, fade-off wind-down, dark sleep)
- [x] PIN protection for web UI
- [x] OTA firmware updates via HTTP (bearer token auth)
- [x] FTP-based bulk OTA sync with MD5 hash verification
- [x] Per-mode time limits (infrastructure ready, modes use when needed)
- [x] Session recording to flash (date, start time, duration, mode, end reason)
- [x] Usage statistics over time (daily totals, mode breakdown, 7-day history)
- [x] Suggested limits based on actual usage patterns
- [x] Admin QR code screen for quick phone access
- [x] Graceful degradation when MCP23017 is absent (with diag reporting)

## Milestone 5: Quality-of-life

- [x] Battery level indicator on display
- [x] Low battery warning and deep-sleep on critical battery
- [x] Serial console for configuration (REPL helpers: wifi, settings, reboot)
- [x] On-device diagnostics screen (hold-button at boot)
- [x] Power-save mode with light sleep and master switch
- [x] Thermal protection (software-only safeguard for LiPo — shed load at 50 °C, sleep at 60 °C)
- [x] SD card support for bulk media (mounted at boot, graceful fallback if absent)
- [x] Asset resolver (`bodn.assets.resolve` / `resolve_voice`) with SD-first / flash-fallback precedence
- [x] Custom MicroPython firmware build with native C modules (`_audiomix`, `_spidma`, `_draw`, `_mcpinput`, `_neopixel`)
- [x] Boot log persistence to flash, viewable via the web UI

## Milestone 6: NFC card games

- [x] NFC tag format (self-describing NDEF Text Records) and card-set schema
- [x] PN532 NFC reader driver (I2C, polling task, power-gated rail)
- [x] Robust tag writing with retries and PN532 recovery
- [x] NFC provisioning UI (card set viewer, programming, UID cache)
- [x] Card-face PDF generator (OpenMoji emoji → A4, 85×54 mm, 2×4 per page)
- [x] Sortera card set (16 animal cards × 4 colours) with runtime filter by programmed tags
- [x] Räkna card set (numbers, operators, equation builders — levels 1–6)
- [x] Launcher cards — tap any card to open the matching game mode
- [x] `bodn.thias.se` web landing page for per-card info (card viewer parses NFC URLs)
- [ ] Additional card sets — vocabulary, storytelling props, day-of-week, colours, etc.
