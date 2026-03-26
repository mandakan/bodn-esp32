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
- [x] Play WAV samples from flash (streaming WAV reader + audio engine)
- [x] Multi-channel audio mixing (6 simultaneous voices, priority channels)
- [x] Click feedback on UI interactions
- [x] Volume control via rotary encoder
- [x] Audio asset pipeline with EBU R128 loudness normalisation
- [ ] Record short clips from INMP441 into RAM
- [ ] Playback recorded clips

## Milestone 3: Kid-facing UI

- [x] Home screen with colourful icons and animated carousel (velocity-aware slide)
- [x] Gesture layer: tap, double-tap, long-press on all buttons
- [x] Multi-button chord / combo detection
- [x] **Mystery Box** — colour discovery game with hue-shift feedback
- [x] **Simon** — pattern memory game (pattern copy / repeat)
- [x] **Flöde** — flow-alignment spatial puzzle
- [x] **Rule Follow** — inhibition & cognitive flexibility game
- [x] **Garden of Life** — Conway's Game of Life with interactive seeding
- [x] **Soundboard** — discovery mode mapping buttons to sounds
- [x] Pause menu (hold-to-open), session overlay, in-game wind-down animation
- [x] Secondary display content per game mode (cat face, ambient clock, status strip)
- [x] i18n with Swedish default and English fallback (å/ä/ö extended font glyphs)
- [ ] "Record & replay" mode — record voice and play back on button press
- [ ] "Sequencer" mode — chain lights + sounds into a sequence

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
