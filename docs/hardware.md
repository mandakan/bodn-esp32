# Hardware

## Bill of Materials

| Qty | Component | Model / Source | Est. cost |
|-----|-----------|----------------|-----------|
| 1 | MCU board | Olimex ESP32-S3-DevKit-Lipo | ~250 SEK |
| 1 | Battery | Olimex BATTERY-LIPO6600mAh | ~150 SEK |
| 1 | Display | 1.8" 128×160 ST7735 TFT (DollaTek) | ~130 SEK |
| 1 | Microphone | INMP441 I2S MEMS breakout (Mixitech) | ~95 SEK |
| 1 | Amplifier | MAX98357A I2S 3W class-D (AZDelivery) | ~129 SEK |
| 1 | Speaker | 3W 8Ω mini speaker (Quarkzman) | ~81 SEK |
| 3 | Rotary encoder | KY-040 with push button (AZDelivery 5-pack) | ~119 SEK |
| 8 | Push buttons | 7mm mini momentary, mixed colors (Gebildet 24-pack) | ~110 SEK |
| 4 | Toggle switches | Mini SPST on/off (Gebildet 12-pack) | ~99 SEK |
| 2 | LED sticks | WS2812 8-LED RGB modules (from 10-pack) | ~incl. |
| — | Wiring | Dupont jumper wire kits M-M/F-M/F-F (AZDelivery 3×40) | ~89 SEK |
| 1 | Breadboard | Olimex MAXI breadboard (prototyping) | ~40 SEK |

**Estimated total: ~1 290 SEK** (within the 1 500 SEK budget)

## Pin assignments

Pin assignments are defined in `firmware/bodn/config.py`. See `docs/wiring.md` for the full auto-generated reference.

### Display (SPI)

| Signal | GPIO |
|--------|------|
| SCK | 12 |
| MOSI | 11 |
| CS | 10 |
| DC | 8 |
| RST | 9 |
| Backlight | 43 |

### INMP441 Microphone (I2S IN)

| Signal | GPIO |
|--------|------|
| SCK | 14 |
| WS | 15 |
| SD | 38 |

### MAX98357A Amplifier (I2S OUT)

| Signal | GPIO |
|--------|------|
| BCLK | 13 |
| LRCLK (WS) | 45 |
| DIN | 5 |

### Buttons

8 × mini momentary push buttons (active low with internal pull-up):

GPIOs: 1, 2, 4, 7, 20, 21, 35, 36

### Toggle switches

4 × SPST mini toggles (active low with internal pull-up):

GPIOs: 39, 40, 41, 46

### Rotary encoders

| Encoder | CLK | DT | SW (button) |
|---------|-----|----|-------------|
| 1 | 19 | 18 | 17 |
| 2 | 16 | 3 | 48 |
| 3 | 47 | 42 | 0 |

### NeoPixel LEDs (WS2812B)

| Signal | GPIO |
|--------|------|
| Data | 6 |

16 addressable RGB LEDs (2 × 8-LED WS2812 sticks chained).
Brightness capped in software for battery life and kid-safe eyes.
Future option: add a WS2812B 144 LED/m strip for ambient lighting in transparent enclosure.

## Wiring notes

- ST7735 on SPI bus 2.
- INMP441 and MAX98357A on I2S (separate IN/OUT peripherals on ESP32-S3).
- All buttons and toggle switches use internal pull-ups with software debouncing.
- NeoPixel strip on a single GPIO — data line chained through all 16 LEDs.
- WS2812 LEDs run at 5V but the data line works reliably from 3.3V with short wires. If you get flicker, add a 330Ω series resistor on the data line.
- Battery voltage can be read via the DevKit-Lipo's built-in ADC circuit.
- GPIO 0 and 46 are strapping pins but safe as inputs with pull-up after boot.

## ESP32-S3-DevKit-Lipo notes

- USB-C for power, programming, and serial console.
- Built-in LiPo charging circuit — just plug in the battery.
- Battery voltage measurable via ADC (check Olimex docs for the specific ADC pin).
- 8 MB PSRAM available for audio buffers and larger assets.

## GPIO budget

34 of ~36 usable GPIOs allocated. 2 free (GPIO 37, 44 — reserved for real hardware only, not available in Wokwi sim).
