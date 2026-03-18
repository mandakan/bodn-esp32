# Hardware

## Bill of Materials

| Qty | Component | Model / Source | Est. cost |
|-----|-----------|----------------|-----------|
| 1 | MCU board | Olimex ESP32-S3-DevKit-Lipo | ~250 SEK |
| 1 | Battery | Olimex BATTERY-LIPO6600mAh | ~150 SEK |
| 1 | Display | 1.8" 128×160 ST7735 TFT (DollaTek) | ~60 SEK |
| 1 | Microphone | INMP441 I2S MEMS breakout | ~50 SEK |
| 1 | Amplifier | MAX98357A I2S 3W class-D (AZDelivery) | ~60 SEK |
| 1 | Speaker | 3W 8Ω mini speaker (Quarkzman) | ~40 SEK |
| 2 | Rotary encoder | KY-040 with push button | ~30 SEK |
| 6 | Push buttons | Mini momentary panel-mount | ~30 SEK |
| 1 | Power switch | Panel-mount toggle (SPST) | ~20 SEK |
| — | Wiring | Dupont jumper wire kits (M-M, M-F, F-F) | ~50 SEK |
| 1 | Breadboard | Olimex MAXI breadboard (prototyping) | ~40 SEK |

**Estimated total: ~780 SEK** (well within the 1500 SEK budget)

## Pin assignments

Pin assignments are defined in `firmware/bodn/config.py`. Current mapping:

### Display (SPI)

| Signal | GPIO |
|--------|------|
| SCK | 12 |
| MOSI | 11 |
| CS | 10 |
| DC | 8 |
| RST | 9 |
| Backlight | 6 |

### INMP441 Microphone (I2S IN)

| Signal | GPIO |
|--------|------|
| SCK | 14 |
| WS | 15 |
| SD | 32 |

### MAX98357A Amplifier (I2S OUT)

| Signal | GPIO |
|--------|------|
| BCLK | 13 |
| LRCLK (WS) | 33 |
| DIN | 5 |

### Buttons

GPIOs: 1, 2, 4, 7, 20, 21 (active low with internal pull-up)

### Rotary encoders

| Encoder | CLK | DT | SW (button) |
|---------|-----|----|-------------|
| 1 | 19 | 18 | 17 |
| 2 | 16 | 3 | 0 |

## Wiring notes

- ST7735 on SPI bus 2.
- INMP441 and MAX98357A on I2S (separate IN/OUT peripherals on ESP32-S3).
- All buttons use internal pull-ups with software debouncing.
- Optionally add an LED per button on spare GPIOs.
- Battery voltage can be read via the DevKit-Lipo's built-in ADC circuit.

## ESP32-S3-DevKit-Lipo notes

- USB-C for power, programming, and serial console.
- Built-in LiPo charging circuit — just plug in the battery.
- Battery voltage measurable via ADC (check Olimex docs for the specific ADC pin).
- 8 MB PSRAM available for audio buffers and larger assets.
