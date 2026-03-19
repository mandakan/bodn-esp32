# Roadmap

## Milestone 1: Hardware bring-up

- [ ] Flash MicroPython onto ESP32-S3-DevKit-Lipo
- [ ] Get ST7735 displaying text and basic graphics
- [ ] Read button presses with debouncing
- [ ] Read rotary encoder rotation and button press
- [ ] Backlight control via PWM

## Milestone 2: Audio basics

- [ ] Play simple tones through MAX98357A
- [ ] Play WAV samples from flash
- [ ] Record short clips from INMP441 into RAM
- [ ] Playback recorded clips
- [ ] Volume control via rotary encoder

## Milestone 3: Kid-facing UI

- [ ] Home screen with colourful icons
- [ ] "Sound board" mode: each button plays a different sound
- [ ] "Record & replay" mode
- [ ] "Sequencer" mode: chain lights + sounds into a sequence
- [ ] Simple animations on the display

## Milestone 4: Parental controls

- [x] WiFi connect (AP mode + STA mode)
- [x] NTP time sync at boot
- [x] Session state machine (play limits, break timer, quiet hours, lockdown)
- [x] Settings and session history persisted to flash (JSON)
- [x] Async web server on device (uasyncio)
- [x] Web UI for parents (dashboard, limits, history, WiFi config)
- [x] Wokwi port forwarding (device:80 → localhost:8080)
- [x] Convert main loop to uasyncio (web server + UI run concurrently)
- [x] Session-aware LED animations (amber warnings, fade-off wind-down, dark sleep)

## Milestone 5: Quality-of-life

- [ ] Battery level indicator on display
- [ ] Low battery warning
- [ ] Serial console for configuration
- [ ] OTA firmware updates
