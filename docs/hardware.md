# Hardware

## Bill of Materials

| Qty | Component | Model / Source | Est. cost |
|-----|-----------|----------------|-----------|
| 1 | MCU board | Olimex ESP32-S3-DevKit-Lipo | ~250 SEK |
| 1 | Battery | Olimex BATTERY-LIPO6600mAh | ~150 SEK |
| 1 | Primary display | 2.8" 240×320 ILI9341 TFT with touch (AZDelivery) | ~200 SEK |
| 1 | Secondary display | 1.8" 128×160 ST7735 TFT (DollaTek) | ~130 SEK |
| 1 | Microphone | INMP441 I2S MEMS breakout (Mixitech) | ~95 SEK |
| 1 | Amplifier | MAX98357A I2S 3W class-D (AZDelivery) | ~129 SEK |
| 1 | Speaker | 3W 8Ω mini speaker (Quarkzman) | ~81 SEK |
| 3 | Rotary encoder | KY-040 with push button (AZDelivery 5-pack) | ~119 SEK |
| 8 | Push buttons | 7mm mini momentary, mixed colors (Gebildet 24-pack) | ~110 SEK |
| 4 | Toggle switches | Mini SPST on/off (Gebildet 12-pack) | ~99 SEK |
| 2 | LED sticks | WS2812 8-LED RGB modules (from 10-pack) | ~incl. |
| 1 | LED strip | WS2812B 144 LED/m RGBIC strip, cut to 640 mm (~92 LEDs) | ~169 SEK |
| 1 | GPIO expander | Waveshare MCP23017 I2C 16-IO expansion board | ~85 SEK |
| 1 | PWM driver | PCA9685 16-channel 12-bit PWM I2C breakout ([Adafruit 815](https://www.adafruit.com/product/815)) | ~120 SEK |
| 1 | DC-DC converter | Buck-boost 3–16V → 5V/2A ([Electrokit](https://www.electrokit.com/dcdc-omvandlare-step-up/step-down-3.3/5v)) | ~99 SEK |
| 2 | Temperature sensor | DS18B20 1-Wire digital ([Electrokit](https://www.electrokit.com/temperatursensor-ds18b20)) | ~78 SEK |
| — | Wiring | Dupont jumper wire kits M-M/F-M/F-F (AZDelivery 3×40) | ~89 SEK |
| 1 | Breadboard | Olimex MAXI breadboard (prototyping) | ~40 SEK |

**Estimated total: ~2 042 SEK**

## Pin assignments

Pin assignments are defined in `firmware/bodn/config.py`. See `docs/wiring.md` for the full auto-generated reference.

### Primary display — 2.8" ILI9341 (SPI)

| Signal | GPIO |
|--------|------|
| SCK | 12 |
| MOSI | 11 |
| CS | 10 |
| DC | 8 |
| RST | 9 |
| Backlight | 43 |

Touch controller (XPT2046) pins TBD — shares SPI bus with a separate CS.

### Secondary display — 1.8" ST7735 (SPI, shared bus)

| Signal | GPIO |
|--------|------|
| SCK | 12 (shared) |
| MOSI | 11 (shared) |
| CS | 39 |
| DC | 8 (shared) |
| RST | 9 (shared) |

The secondary display shares SCK, MOSI, DC, and RST with the primary. Only CS is separate — asserting one CS at a time selects which display receives data.

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

### Buttons (MCP23017)

8 × mini momentary push buttons (active low with MCP23017 internal pull-ups):

MCP23017 pins: GPA0–GPA7 (config: `MCP_BTN_PINS`)

### Toggle switches (MCP23017)

4 × SPST mini toggles (active low with MCP23017 internal pull-ups):

MCP23017 pins: GPB0–GPB3 (config: `MCP_SW_PINS`)

### Rotary encoders

| Encoder | Role | CLK | DT | SW (button) |
|---------|------|-----|----|-------------|
| 1 (NAV) | Navigation | 19 | 18 | 17 |
| 2 (ENC_A) | Parameter A | 16 | 3 | 40 |
| 3 (ENC_B) | Parameter B | 41 | 42 | 0 |

### NeoPixel LEDs (WS2812B)

| Signal | GPIO |
|--------|------|
| Data | 4 |

108 addressable RGB LEDs on a single daisy-chained data line, split into three logical zones:

| Zone | LEDs | Indices | Component | Placement |
|------|------|---------|-----------|-----------|
| Stick A | 8 | 0–7 | WS2812 8-LED module | Lid (left or parallel) |
| Stick B | 8 | 8–15 | WS2812 8-LED module | Lid (right or parallel) |
| Lid Ring | 92 | 16–107 | WS2812B 144 LED/m strip (640 mm) | Inside lid perimeter |

Chain order: Stick A DOUT → Stick B DIN → Stick B DOUT → Lid Ring DIN.

Brightness is capped in software per zone: sticks at 25% (64/255), lid ring at 12.5% (32/255) for ambient glow. For strips longer than ~0.5 m, inject 5V power at the midpoint to prevent voltage drop and color shift at the far end.

NeoPixel VDD is powered from the DC-DC converter's 5V output (see [Power distribution](#power-distribution) below), ensuring stable voltage on both USB and battery.

## Display architecture

The two displays serve different purposes:

- **Primary (ILI9341 2.8" 240×320)**: main game UI, menu navigation, all child-facing interaction. Driven by the ScreenManager framework.
- **Secondary (ST7735 1.8" 128×160)**: ambient/status display. Ideas: persistent clock, session timer, parent dashboard, idle animations, battery level. Updated independently from the main UI loop.

Both share SPI bus 2. The driver deasserts CS after each `show()`, so they can coexist without conflict. The secondary display uses a separate framebuffer (~40 KB) which fits comfortably in the 8 MB PSRAM.

## Wiring notes

- Both displays on SPI bus 2 with separate CS pins.
- ILI9341 touch (XPT2046) will need a third CS pin on the same SPI bus (pin TBD).
- INMP441 and MAX98357A on I2S (separate IN/OUT peripherals on ESP32-S3).
- All buttons and toggle switches are on the MCP23017 I2C expander with its internal pull-ups and software debouncing.
- NeoPixel chain on a single GPIO — data line through 108 LEDs (2 sticks + lid ring).
- WS2812 LEDs powered from the DC-DC converter's 5V output. The 3.3V data line from GPIO 4 works reliably with short wires. If you get flicker, add a 330Ω series resistor on the data line.
- Battery voltage can be read via the DevKit-Lipo's built-in ADC circuit.
- GPIO 0 and 46 are strapping pins but safe as inputs with pull-up after boot.
- DS18B20 temperature sensors share a single 1-Wire bus on GPIO 20 with a 4.7 kΩ pull-up to 3.3V. Mount one sensor against the LiPo pouch (Kapton thermal tape), one inside the enclosure near the DC-DC converter.

## Schematics

Board schematics (Rev B) are in [`docs/schematics/`](schematics/):

| File | Contents |
|------|----------|
| `ESP32-S3-DevKit-LiPo_Rev_B.png` | Full schematic |
| `power_supply.png` | Power supply, BAT_SENS (GPIO 6), PWR_SENS (GPIO 5) |
| `gpio_list.png` | Complete GPIO listing with board-level labels |

Source: [OLIMEX/ESP32-S3-DevKit-LiPo on GitHub](https://github.com/OLIMEX/ESP32-S3-DevKit-LiPo)

## ESP32-S3-DevKit-Lipo

Board: **Olimex ESP32-S3-DevKit-LiPo** (Rev B)

- Module: ESP32-S3-WROOM-1-N8R8 (8 MB flash + 8 MB PSRAM)
- Dual-core Xtensa LX7 @ 240 MHz, 512 KB internal SRAM
- Wi-Fi 802.11 b/g/n + Bluetooth 5 (LE)
- Two USB-C ports: one for UART (programming/console via CH340X), one for OTG/JTAG
- Built-in LiPo charger (BL4054B, 100 mA with default 10k prog resistor)
- Battery voltage measurable via ADC on GPIO 6 (BAT_SENS, voltage divider R6/R7: 470k/150k)
- External power sense on GPIO 5 (PWR_SENS, active low when USB power present)
- On-board user LED on GPIO 38 (active high, accent green)
- User button on GPIO 0, reset button on ESP_EN
- pUEXT connector (1.0 mm pitch, 10-pin) exposing UART1, I2C, SPI3 — see below
- Dimensions: 27.94 × 55.88 mm
- Extension headers (J1/J3) are fully compatible with Espressif ESP32-S3-DevKitC-1

Reference: [OLIMEX/ESP32-S3-DevKit-LiPo on GitHub](https://github.com/OLIMEX/ESP32-S3-DevKit-LiPo)

### pUEXT connector pinout

The on-board pUEXT connector (BM10B-SRSS-TB, 1.0 mm pitch) provides I2C, SPI, and UART
on a single 10-pin connector with pull-ups already fitted on the board:

| Pin | Signal | GPIO | Pull-up |
|-----|--------|------|---------|
| 1 | +3.3V | — | — |
| 2 | GND | — | — |
| 3 | U1TXD | 17 | — |
| 4 | U1RXD | 18 | — |
| 5 | I2C_SCL | 47 | 2.2k to 3.3V (R19) |
| 6 | I2C_SDA | 48 | 2.2k to 3.3V (R20) |
| 7 | SPI3_MISO | 13 | — |
| 8 | SPI3_MOSI | 11 | — |
| 9 | SPI3_CLK | 12 | — |
| 10 | SPI3_CS0 | 10 | 10k to 3.3V (R21) |

### Reserved / unavailable GPIOs

The ESP32-S3-WROOM-1-**N8R8** module uses OSPI PSRAM which occupies three GPIOs internally:

| GPIO | Reason | Note |
|------|--------|------|
| 35 | OSPI PSRAM (FSPID) | **Not available** — marked NC on extension headers |
| 36 | OSPI PSRAM (FSPICLK) | **Not available** — marked NC on extension headers |
| 37 | OSPI PSRAM (FSPIQ) | **Not available** — marked NC on extension headers |

All three pins are avoided in `config.py`. Buttons and toggles have been moved to the
MCP23017 I2C expander, and TFT2_CS has been reassigned to GPIO 39.

Other GPIOs with board-level functions — see [`docs/schematics/`](schematics/) for annotated crops:

| GPIO | Board label | Our assignment | Notes |
|------|-------------|----------------|-------|
| 0 | BUT1 (user button) | ENC3_SW | Strapping pin; safe as input after boot |
| 1 | — | TFT_BL (backlight) | Moved here from GPIO 43 (UART TX) |
| 2 | — | I2S_MIC_SD | Moved here from GPIO 38 (on-board LED) |
| 5 | PWR_SENS | `PWR_SENS_PIN` (battery module) | Active low when USB power present; **do not drive** |
| 6 | BAT_SENS | `BAT_SENS_PIN` (battery module) | R8/R9 divider; ADC only |
| 19 | USB_D− | ENC1_CLK | USB OTG D−; safe when OTG port unused ⚠ |
| 20 | USB_D+ | ONEWIRE_PIN (DS18B20) | 1-Wire bus; conflicts with OTG port (not used) |
| 38 | LED1 (green) | — (freed) | On-board LED; previously conflicted with I2S mic |
| 43 | U0TXD | — (freed) | UART TX; previously conflicted with TFT backlight |
| 44 | U0RXD | — | UART RX; avoid driving |
| 46 | — | free | Strapping pin; safe as input after boot |

⚠ GPIO 19/20 are the ESP32-S3 USB OTG D±. These conflict with ENC1 CLK/DT if the
OTG USB-C port is connected. Acceptable for production (OTG never used), but plug
the UART USB-C port — **not the OTG port** — when developing.

## MCP23017 GPIO expander

**Purpose:** Expand the available I/O for non-time-critical peripherals (buttons, toggle
switches, LEDs, and other slow-changing signals) over I2C, freeing native ESP32 GPIOs
for latency-sensitive tasks (encoders, SPI displays, I2S audio).

### Module specs

| Parameter | Value |
|-----------|-------|
| Board | Waveshare MCP23017 I2C 16-IO Expansion Board |
| Chip | Microchip MCP23017 |
| Interface | I2C (up to 1.7 MHz in fast-mode plus, 400 kHz standard) |
| I/O pins | 16 (two 8-bit ports: GPA0–7, GPB0–7) |
| Operating voltage | 1.8–5.5V (3.3V from ESP32) |
| Default I2C address | 0x20 (configurable 0x20–0x27 via A0–A2 jumpers) |
| Interrupt outputs | 2 open-drain (INTA, INTB) — optional |
| Stackable | Up to 8 boards on the same I2C bus |

### I2C bus connection

The MCP23017 connects to the ESP32-S3 via I2C. The devkit provides hardware I2C with
pull-ups on GPIO 47 (SCL) and GPIO 48 (SDA) via the pUEXT connector.

Encoder pins that previously used GPIO 47 and 48 have been reassigned (ENC3_CLK → 41,
ENC2_SW → 40) to free the I2C bus.

### Pin mapping

| MCP23017 pin | Peripheral | Notes |
|--------------|-----------|-------|
| GPA0–GPA7 | 8 push buttons | Active low with internal pull-ups (MCP23017 has configurable pull-ups) |
| GPB0–GPB3 | 4 toggle switches | Active low with internal pull-ups |
| GPB4–GPB7 | 4 × available | Future use (additional buttons, status LEDs, etc.) |

All buttons and toggle switches are permanently on the MCP23017 expander.
Native GPIOs free for future use: 20, 21, 46.

### Why not put encoders on the expander?

Rotary encoders generate rapid quadrature pulses that need low-latency IRQ handling.
The I2C round-trip through the MCP23017 adds too much delay — missed edges cause phantom
steps. Encoders must stay on native ESP32 GPIOs with hardware interrupts.

## PCA9685 PWM driver

**Purpose:** Provide 16 channels of 12-bit PWM for smooth LED dimming, backlight
control, and future servo/motor accessories — all over the existing I2C bus without
consuming additional native GPIOs.

### Module specs

| Parameter | Value |
|-----------|-------|
| Board | Adafruit PCA9685 16-channel 12-bit PWM I2C breakout (or compatible clone) |
| Chip | NXP PCA9685 |
| Interface | I2C (shared bus with MCP23017) |
| PWM channels | 16 × 12-bit (4096 steps per channel) |
| PWM frequency | 24 Hz – 1526 Hz (configurable via prescaler) |
| Operating voltage | 3.3V logic, separate V+ for LED power (up to 6V) |
| Default I2C address | 0x40 (configurable 0x40–0x7F via A0–A5) |

### I2C bus connection

The PCA9685 shares the I2C bus on GPIO 47 (SCL) / GPIO 48 (SDA) with the MCP23017.

| Address | Device |
|---------|--------|
| 0x20 | MCP23017 (buttons, toggles, power switch) |
| 0x40 | PCA9685 (PWM dimming) |

### Channel assignments

| Channel | Function | Notes |
|---------|----------|-------|
| 0 | TFT backlight | Smooth dimming (replaces binary GPIO on/off) |
| 1–15 | Available | Indicator LEDs, mood lights, servos, etc. |

### Wiring

```
ESP32-S3          PCA9685 breakout
─────────         ────────────────
GPIO 47 (SCL) ──▶ SCL
GPIO 48 (SDA) ──▶ SDA
3V3           ──▶ VCC
GND           ──▶ GND
GND           ──▶ OE  (active-low: GND = outputs enabled)
                  V+ ← external LED supply or 3V3 for low-power LEDs
```

## Power distribution

The Olimex DevKit-Lipo has no boost converter. On battery the only rails are the
raw LiPo voltage (3.0–4.2 V) and the on-board 3.3 V regulator. WS2812B NeoPixels
require ≥ 3.5 V VDD and behave best at 5 V, so a buck-boost DC-DC converter
provides a stable 5 V rail from either USB or battery power.

### DC-DC converter

| Parameter | Value |
|-----------|-------|
| Module | Buck-boost 3–16 V → 5 V / 2 A ([Electrokit](https://www.electrokit.com/dcdc-omvandlare-step-up/step-down-3.3/5v)) |
| Efficiency | Up to 95 % |
| Input | LiPo BAT+ (3.0–4.2 V) or USB VBUS (5 V) |
| Output | 5 V regulated |
| Consumers | NeoPixel VDD, PCA9685 V+ |

```
LiPo BAT+ ──▶ VIN (converter)
               VOUT (5 V) ──▶ NeoPixel VDD (all 108 LEDs)
                           ──▶ PCA9685 V+ (LED power rail)
GND ────────▶ GND (converter) ──▶ NeoPixel GND
                               ──▶ PCA9685 GND
```

The ESP32 and all 3.3 V logic components (displays, audio, MCP23017) remain on
the on-board 3.3 V regulator. Only the NeoPixels and PCA9685 LED outputs use
the 5 V rail.

## DS18B20 temperature sensors

**Purpose:** Monitor battery and enclosure temperature to detect overheating
and protect the LiPo cell. Two sensors share a single 1-Wire bus on GPIO 20.

### Module specs

| Parameter | Value |
|-----------|-------|
| Chip | Maxim DS18B20 |
| Interface | 1-Wire (multiple sensors on one GPIO) |
| Operating voltage | 3.0–5.5 V (powered from 3.3 V rail) |
| Temperature range | −55 °C to +125 °C |
| Accuracy | ±0.5 °C (−10 °C to +85 °C) |
| Resolution | 9–12 bit configurable (12-bit default, ~750 ms conversion) |

### Wiring

Both sensors connect to the same 1-Wire bus with a shared 4.7 kΩ pull-up:

```
ESP32-S3               DS18B20 sensors
─────────              ───────────────
GPIO 20 (1-Wire) ──┬──▶ DQ (sensor 1 — battery)
                   ├──▶ DQ (sensor 2 — enclosure)
                   └── 4.7 kΩ ──▶ 3V3
3V3              ──▶ VDD (both sensors)
GND              ──▶ GND (both sensors)
```

### Sensor placement

| Sensor | Location | Purpose |
|--------|----------|---------|
| Battery | Against LiPo pouch, secured with Kapton thermal tape | Detect cell overheating (warn ≥ 45 °C, critical ≥ 55 °C) |
| Enclosure | Near DC-DC converter / electronics | Detect general overheating inside the box |

### Software

Firmware module: `bodn/temperature.py`. Sensors are auto-discovered by ROM
address on the 1-Wire bus. Readings are cached for 30 s. The `is_warning()`
and `is_critical()` helpers compare against `config.TEMP_WARN_C` / `TEMP_CRIT_C`
thresholds.

## GPIO budget

| Category | Details |
|----------|---------|
| Native GPIOs in use | 24 (SPI, I2S, encoders, NeoPixel, I2C, battery, backlight, 1-Wire) |
| Native GPIOs free | 2 — GPIO 19 (USB OTG caveat), 46 |
| PSRAM-reserved (never use) | GPIO 35, 36, 37 |
| UART console (avoid) | GPIO 43 (TX), 44 (RX) |
| MCP23017 in use | 13 (8 buttons + 4 toggles + master switch) |
| MCP23017 spare | 3 (GPB5–GPB7) |
| PCA9685 in use | 1 (backlight) |
| PCA9685 spare | 15 (channels 1–15) |
