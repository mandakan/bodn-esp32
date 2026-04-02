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
| 2 | Rotary encoder | KY-040 with push button (AZDelivery 5-pack) | ~119 SEK |
| 8 | Push buttons | 7mm mini momentary, mixed colors (Gebildet 24-pack) | ~110 SEK |
| 5 | Arcade buttons | 30mm illuminated LED, mixed colors (Electrokit) | ~150 SEK |
| 2 | Toggle switches | Mini SPST on/off (Gebildet 12-pack) | ~99 SEK |
| 2 | LED sticks | WS2812 8-LED RGB modules (from 10-pack) | ~incl. |
| 1 | LED strip | WS2812B 144 LED/m RGBIC strip, cut to 640 mm (~92 LEDs) | ~169 SEK |
| 2 | GPIO expander | CJMCU-2317 MCP23017 I2C 16-IO expansion board | ~80 SEK |
| 1 | PWM driver | PCA9685 16-channel 12-bit PWM I2C breakout ([Adafruit 815](https://www.adafruit.com/product/815)) | ~120 SEK |
| 1 | SD card | Micro SD card, 4–32 GB FAT32 (any brand) | ~50 SEK |
| 1 | DC-DC converter | Buck-boost 3–16V → 5V/2A ([Electrokit](https://www.electrokit.com/dcdc-omvandlare-step-up/step-down-3.3/5v)) | ~99 SEK |
| 2 | Temperature sensor | DS18B20 1-Wire digital ([Electrokit](https://www.electrokit.com/temperatursensor-ds18b20)) | ~78 SEK |
| — | Wiring | Dupont jumper wire kits M-M/F-M/F-F (AZDelivery 3×40) | ~89 SEK |
| 1 | Breadboard | Olimex MAXI breadboard (prototyping) | ~40 SEK |

**Estimated total: ~2 177 SEK**

## Pin assignments

Pin assignments are defined in `firmware/bodn/config.py`. See `docs/wiring.md` for the full auto-generated reference.

### Primary display — 2.8" ILI9341 (SPI)

| Signal | GPIO / connection |
|--------|-------------------|
| SCK | GPIO 12 |
| MOSI | GPIO 11 |
| CS | GPIO 10 |
| DC | GPIO 8 |
| RST | GPIO 9 |
| BL (PWM dim) | PCA9685 CH0 (control signal) |
| LED+ (power) | 5 V from DC-DC converter (via PCA9685 V+) |

The PCA9685 drives the backlight LED through its CH0 output; the LED anode power
comes from the PCA9685 V+ pin, which is tied to the DC-DC 5 V rail.

The ILI9341 display breakout includes an SD card slot whose SPI pads are wired to the dedicated SD SPI3 bus (see [SD card](#sd-card) below). Touch controller (XPT2046) is not used — its GPIOs have been repurposed for SD.

### Secondary display — 1.8" ST7735 (SPI, shared bus)

| Signal | GPIO |
|--------|------|
| SCK | 12 (shared) |
| MOSI | 11 (shared) |
| CS | 39 |
| DC | 8 (shared) |
| RST | 9 (shared) |
| VCC | 5V (DC-DC converter) |
| BL | 5V (DC-DC converter) |

The DollaTek module requires **5V on VCC** (J1 jumper open = default = 5V mode). An onboard regulator steps down to 3.3V for the ST7735 chip, so 3.3V SPI signals from the ESP32 work fine. The backlight also needs 5V — tie BL to the same 5V rail.

The secondary display shares SCK, MOSI, DC, and RST with the primary. Only CS is separate — asserting one CS at a time selects which display receives data.

### INMP441 Microphone (I2S IN)

| Signal | GPIO |
|--------|------|
| SCK | 14 |
| WS | 15 |
| SD | 2 |

### MAX98357A Amplifier (I2S OUT)

| Signal | Connection |
|--------|------------|
| BCLK | GPIO 13 |
| LRCLK (WS) | GPIO 45 |
| DIN | GPIO 7 |
| SD | GPIO 3 (direct — PCA9685 glitches on boot; add 10kΩ pull-down to GND) |
| GAIN | floating (9dB default) |

### Mini push buttons (MCP23017)

8 × 7 mm mini momentary push buttons (active low with MCP23017 internal pull-ups):

MCP23017 pins: GPA0–GPA7 (config: `MCP_BTN_PINS`)

#### Physical layout

The mini buttons sit in an evenly-spaced row ~1 cm above the arcade buttons on the
lid. Electrical index 0–7 runs left-to-right. Colors repeat due to limited variety:

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                              LID (front)                                    ║
║                                                                             ║
║                         ┌─────────────────┐                                 ║
║                         │  PRIMARY DISPLAY │                                ║
║                         │   (ILI9341)      │                                ║
║                         └─────────────────┘                                 ║
║                                                                             ║
║  ┌─┐  ┌─────┐   ┌─┐      ┌─┐     ┌─────┐   ┌─┐                           ║
║  │⇕│  │ NAV │   │⇕│      │⇕│     │ENC_A│   │⇕│                           ║
║  │L│  │ ENC │   │0│      │1│     │ ENC │   │R│    (toggles + encoders)    ║
║  └─┘  └─────┘   └─┘      └─┘     └─────┘   └─┘                           ║
║                                                                             ║
║  ┌───┐  ┌────┐  ┌───┐  ┌────┐  ┌───┐  ┌───┐  ┌───┐  ┌────┐              ║
║  │GRN│  │BLU │  │WHT│  │YLW │  │RED│  │BLK│  │GRN│  │BLU │              ║
║  │ 0 │  │ 1  │  │ 2 │  │ 3  │  │ 4 │  │ 5 │  │ 6 │  │ 7  │  (mini)     ║
║  └───┘  └────┘  └───┘  └────┘  └───┘  └───┘  └───┘  └────┘              ║
║                                                                             ║
║   ┌───────┐  ┌──────┐  ┌───────┐  ┌────────┐  ┌─────┐                     ║
║   │ GREEN │  │ BLUE │  │ WHITE │  │ YELLOW │  │ RED │  (arcade)           ║
║   │ idx 0 │  │ idx 1│  │ idx 2 │  │ idx 3  │  │idx 4│                     ║
║   └───────┘  └──────┘  └───────┘  └────────┘  └─────┘                     ║
╚═══════════════════════════════════════════════════════════════════════════════╝

Toggle/encoder row (left to right):
  ⇕L    = SW_L  (MCP2 GPA2)     — extra toggle, far left
  NAV   = ENC1  (CLK/DT native, SW → MCP2 GPA0)
  ⇕0    = SW0   (MCP1 GPB0)     — bank select bit 0
  ⇕1    = SW1   (MCP1 GPB1)     — bank select bit 1
  ENC_A = ENC2  (CLK/DT native, SW → MCP2 GPA1)
  ⇕R    = SW_R  (MCP2 GPA3)     — extra toggle, far right
```

| Index | Color  | MCP1 pin |
|-------|--------|----------|
| 0     | Green  | GPA0     |
| 1     | Blue   | GPA1     |
| 2     | White  | GPA2     |
| 3     | Yellow | GPA3     |
| 4     | Red    | GPA4     |
| 5     | Black  | GPA5     |
| 6     | Green  | GPA6     |
| 7     | Blue   | GPA7     |

The color list is defined in `config.py` as `BUTTON_COLORS`.

### Toggle switches (MCP23017)

4 × SPST mini toggles (active low with internal pull-ups), split across both expanders:

| Switch | Expander | Pin  | Config constant | Position on lid |
|--------|----------|------|-----------------|-----------------|
| SW0    | MCP1     | GPB0 | `MCP_SW_PINS[0]` | Centre-left (bank select bit 0) |
| SW1    | MCP1     | GPB1 | `MCP_SW_PINS[1]` | Centre-right (bank select bit 1) |
| SW_L   | MCP2     | GPA2 | `MCP2_SW_LEFT`  | Far left |
| SW_R   | MCP2     | GPA3 | `MCP2_SW_RIGHT` | Far right |

SW0 and SW1 are used for soundboard bank selection. SW_L and SW_R are general-purpose
toggles available to game modes (e.g. demo, spaceship).

### Arcade buttons (MCP23017)

5 × 30mm illuminated arcade buttons (switch contacts, active low with MCP23017 internal pull-ups):

MCP23017 pins: GPB2, GPB3, GPB5, GPB6, GPB7 (config: `MCP_ARC_PINS`)

Arcade button LEDs are driven by the PCA9685 PWM driver (see below).

### Arcade button physical layout

The five arcade buttons are arranged in a row across the lower part of the lid.
The physical left-to-right order matches the electrical index order (0–4):

```
╔═══════════════════════════════════════════════════════════════╗
║                          LID (front)                         ║
║                                                              ║
║   ┌───────┐  ┌──────┐  ┌───────┐  ┌────────┐  ┌─────┐     ║
║   │ GREEN │  │ BLUE │  │ WHITE │  │ YELLOW │  │ RED │     ║
║   │ idx 0 │  │ idx 1│  │ idx 2 │  │ idx 3  │  │idx 4│     ║
║   └───────┘  └──────┘  └───────┘  └────────┘  └─────┘     ║
╚═══════════════════════════════════════════════════════════════╝
```

| Position (L→R) | Color  | Index | MCP1 pin | PCA9685 channel |
|-----------------|--------|-------|----------|-----------------|
| 1 (far left)    | Green  | 0     | GPB2     | CH1             |
| 2               | Blue   | 1     | GPB3     | CH2             |
| 3 (centre)      | White  | 2     | GPB5     | CH3             |
| 4               | Yellow | 3     | GPB6     | CH4             |
| 5 (far right)   | Red    | 4     | GPB7     | CH5             |

The color list is defined in `config.py` as `ARCADE_COLORS`. Since the physical
and electrical orders match, no separate spatial mapping is needed.

### Rotary encoders

CLK and DT stay on native GPIOs, decoded by the ESP32-S3 PCNT (Pulse Counter) hardware peripheral — zero-CPU quadrature decoding with a 1µs glitch filter. Push buttons (SW) are routed through MCP2 to free GPIOs 17 and 40 for the SD card SPI3 bus.

| Encoder | Role | CLK | DT | SW (button) |
|---------|------|-----|----|-------------|
| 1 (NAV) | Navigation + Parameter B | 21 | 18 | MCP2 GPA0 |
| 2 (ENC_A) | Parameter A | 16 | 41 | MCP2 GPA1 |

NAV doubles as parameter B in game modes — rotation controls speed/cursor, short tap triggers game actions, long press (1.5s) opens the pause menu.

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

- Both displays on SPI bus 2 with separate CS pins. Touch controller (XPT2046) not used.
- SD card on dedicated SPI3 bus (GPIOs 0/17/40/38) — independent of display SPI2.
- INMP441 and MAX98357A on I2S (separate IN/OUT peripherals on ESP32-S3).
- Buttons, toggles, arcade switches on MCP1 (0x23). Encoder push buttons on MCP2 (0x21). Both share the I2C bus with internal pull-ups and software debouncing. RESET pins must be tied to VCC (no on-board pull-up on the CJMCU-2317 modules).
- NeoPixel chain on a single GPIO — data line through 108 LEDs (2 sticks + lid ring).
- WS2812 LEDs powered from the DC-DC converter's 5V output. The 3.3V data line from GPIO 4 works reliably with short wires. If you get flicker, add a 330Ω series resistor on the data line.
- Battery voltage can be read via the DevKit-Lipo's built-in ADC circuit.
- GPIO 0 is a strapping pin (SD_CS) — its pull-up deasserts CS at boot, which is the safe/correct default.
- GPIO 46 is a strapping pin used for MCP_INT (safe as input after boot).
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
| 0 | BUT1 (user button) | SD_CS | Strapping pull-up = CS deasserted at boot ✓ |
| 1 | — | TFT_BL (backlight) | Moved here from GPIO 43 (UART TX) |
| 2 | — | I2S_MIC_SD | Moved here from GPIO 38 (on-board LED) |
| 5 | PWR_SENS | `PWR_SENS_PIN` (battery module) | Active low when USB power present; **do not drive** |
| 6 | BAT_SENS | `BAT_SENS_PIN` (battery module) | R8/R9 divider; ADC only |
| 17 | — | SD_SCK | Freed from ENC1_SW (moved to MCP2) |
| 19 | USB_D− | — (reserved) | USB OTG D−; do not use |
| 20 | USB_D+ | ONEWIRE_PIN (DS18B20) | 1-Wire bus; conflicts with OTG port (not used) |
| 38 | LED1 (green) | SD_MISO | On-board LED freed; GPIO 19 (USB D−) avoided |
| 40 | — | SD_MOSI | Freed from ENC2_SW (moved to MCP2) |
| 43 | U0TXD | — (freed) | UART TX; previously conflicted with TFT backlight |
| 44 | U0RXD | — | UART RX; avoid driving |
| 46 | — | MCP_INT | Strapping pin; safe as input after boot |

Note: GPIO 19 (USB OTG D−) is avoided to prevent USB enumeration issues. SD_MISO was
moved to GPIO 38 (the on-board LED pin, which is freed since LED control is not needed).

## MCP23017 GPIO expanders

**Purpose:** Expand the available I/O for non-time-critical peripherals over I2C,
freeing native ESP32 GPIOs for latency-sensitive tasks (encoders, SPI, I2S).

Two MCP23017 boards share the same I2C bus with different addresses:

| Board | I2C address | A0–A2 jumpers | Role |
|-------|-------------|---------------|------|
| MCP1 | 0x23 | A0=high, A1=high, A2=low | Buttons, toggles, arcade switches |
| MCP2 | 0x21 | A0=high, A1=low, A2=low | Encoder push buttons |

### Module specs

| Parameter | Value |
|-----------|-------|
| Board | CJMCU-2317 MCP23017 I2C 16-IO Expansion Board |
| Chip | Microchip MCP23017 |
| Interface | I2C (up to 1.7 MHz in fast-mode plus, 400 kHz standard) |
| I/O pins | 16 (two 8-bit ports: GPA0–7, GPB0–7) |
| Operating voltage | 1.8–5.5V (3.3V from ESP32) |
| Interrupt outputs | 2 open-drain (INTA, INTB) — optional |
| Stackable | Up to 8 boards on the same I2C bus |

### I2C bus connection

Both boards share GPIO 47 (SCL) / GPIO 48 (SDA) with 2.2 kΩ pull-ups on the devkit.
The MCP interrupt line from MCP1 is on GPIO 46 (active-low, open-drain).

### MCP1 pin mapping (addr 0x23)

| MCP1 pin | Peripheral | Notes |
|----------|-----------|-------|
| GPA0–GPA7 | 8 push buttons | Active low with internal pull-ups |
| GPB0–GPB1 | 2 toggle switches | Active low with internal pull-ups |
| GPB2–GPB3 | Arcade buttons 1–2 | Active low with internal pull-ups |
| GPB4 | Master switch | Red-cover flip switch (active-low) |
| GPB5–GPB7 | Arcade buttons 3–5 | Active low with internal pull-ups |

All 16 MCP1 pins are allocated.

### MCP2 pin mapping (addr 0x21)

| MCP2 pin | Peripheral | Notes |
|----------|-----------|-------|
| GPA0 | ENC1 push button (NAV SW) | Active low with internal pull-ups |
| GPA1 | ENC2 push button (ENC_A SW) | Active low with internal pull-ups |
| GPA2 | Toggle switch SW_L (far left) | Active low with internal pull-ups |
| GPA3 | Toggle switch SW_R (far right) | Active low with internal pull-ups |
| GPA4–GPA7 | Available | Future use |
| GPB0–GPB7 | Available | Future use |

MCP2 uses 4 of 16 pins; 12 spare I/O pins available for future expansion.

### Why not put encoder CLK/DT on the expander?

Rotary encoders generate rapid quadrature pulses that need dedicated GPIO pins. The
ESP32-S3 PCNT peripheral reads CLK and DT atomically in hardware with a configurable
glitch filter — impossible through the MCP23017 I2C bus. The I2C round-trip delay
would cause missed edges and phantom steps.
Push buttons (SW) have no latency requirement and work fine via MCP2.

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
| 0x23 | MCP1 — MCP23017 (buttons, toggles, power switch, arcade) |
| 0x21 | MCP2 — MCP23017 (encoder push buttons) |
| 0x40 | PCA9685 (PWM dimming) |

### Channel assignments

| Channel | Function | Notes |
|---------|----------|-------|
| 0 | TFT backlight | Smooth dimming (replaces binary GPIO on/off) |
| 1 | Arcade LED 1 (green) | 5V via V+ rail, ~10 mA |
| 2 | Arcade LED 2 (blue) | 5V via V+ rail, ~10 mA |
| 3 | Arcade LED 3 (white) | 5V via V+ rail, ~10 mA |
| 4 | Arcade LED 4 (yellow) | 5V via V+ rail, ~10 mA |
| 5 | Arcade LED 5 (red) | 5V via V+ rail, ~10 mA |
| 6 | MAX98357A SD (mute) | 0 = shutdown, 4095 = enabled |
| 7–15 | Available | Future use (servos, indicators, etc.) |

### Wiring

```
ESP32-S3          PCA9685 breakout
─────────         ────────────────
GPIO 47 (SCL) ──▶ SCL
GPIO 48 (SDA) ──▶ SDA
3V3           ──▶ VCC  (logic supply)
GND           ──▶ GND
GND           ──▶ OE   (active-low: GND = outputs enabled)
DC-DC 5 V     ──▶ V+   (LED power rail — arcade LEDs + ILI9341 backlight)
```

## Power distribution

The Olimex DevKit-Lipo has no boost converter. On battery the only rails are the
raw LiPo voltage (3.0–4.2 V) and the on-board 3.3 V regulator. Several peripherals
(NeoPixels, display backlights, arcade button LEDs) require a stable 5 V, so a
buck-boost DC-DC converter provides a single 5 V rail that works on both USB and
battery.

### Power sources

The device runs from either USB or LiPo battery:

```
USB VBUS (5 V) ─────────────────────────┐
                                         ├──▶ DevKit-Lipo system rail
LiPo BAT+ (3.0–4.2 V) ─▶ BL4054B ──────┘      │
                          (charger)             ├──▶ On-board 3.3 V regulator ──▶ ESP32, logic
                                                └──▶ DC-DC VIN (buck-boost) ──▶ 5 V rail
```

When USB is connected the BL4054B trickle-charges the LiPo and the system rail is
held at ~USB VBUS. On battery the system rail follows the LiPo voltage (3.0–4.2 V).
The buck-boost converter handles the full input range in both cases.

### DC-DC converter

| Parameter | Value |
|-----------|-------|
| Module | Buck-boost 3–16 V → 5 V / 2 A ([Electrokit](https://www.electrokit.com/dcdc-omvandlare-step-up/step-down-3.3/5v)) |
| Efficiency | Up to 95 % |
| Input | System power rail (USB VBUS or LiPo BAT+, 3.0–5.5 V) |
| Output | 5 V regulated |
| Consumers | NeoPixel VDD, PCA9685 V+ (arcade LEDs + ILI9341 backlight), ST7735 VCC + BL |

```
System rail ──▶ VIN (DC-DC converter)
                VOUT (5 V) ──▶ NeoPixel VDD (108 LEDs — sticks + lid ring)
                           ──▶ PCA9685 V+  ──▶ Arcade button LEDs (CH1–5)
                                           ──▶ ILI9341 backlight LED+ (CH0)
                           ──▶ ST7735 VCC  (ST7735 module requires 5 V on VCC;
                           ──▶ ST7735 BL    onboard reg steps down to 3.3 V for SPI)
GND ────────▶ GND (DC-DC) ──▶ NeoPixel GND, PCA9685 GND, ST7735 GND
```

The ESP32 core and all 3.3 V logic (SPI/I2S/I2C, MCP23017, audio, mic) run from
the on-board 3.3 V regulator and do **not** depend on the DC-DC converter. If the
DC-DC fails the ESP32 keeps running but LEDs and displays go dark.

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
| Battery | Against LiPo pouch, secured with Kapton thermal tape | Detect cell overheating |
| Enclosure | Near DC-DC converter / electronics | Detect general overheating inside the box |

### Software — thermal protection

Firmware module: `bodn/temperature.py`. DS18B20 sensors are auto-discovered by ROM
address on the 1-Wire bus. Readings are cached for 30 s.

In addition, the ESP32-S3 on-chip temperature sensor (`esp32.raw_temperature()`)
provides instant SoC temperature readings (±3 °C accuracy). This sensor is always
available — even when no external DS18B20 sensors are connected — ensuring thermal
protection is never fully disabled. The `max_temp()` function returns the highest
reading across all sources (DS18B20 + SoC).

**Important:** The BL4054B charger IC on the DevKit-Lipo has **no NTC thermistor
input** and the Olimex battery has **no temperature wire**. This software watchdog
is the **only thermal protection** for the LiPo cell. The hardware provides no
automatic charge/discharge cutoff based on temperature.

#### Threshold escalation

| Level | Threshold | Action | Recovery |
|-------|-----------|--------|----------|
| OK | < 40 °C | Normal operation | — |
| Warning | ≥ 40 °C | Log to serial, amber banner on both displays, web UI alert. NeoPixel brightness halved (biggest heat source). | Clears when temp drops below 40 °C |
| Critical | ≥ 50 °C | Kill all NeoPixels, dim display backlight. Full-screen "TOO HOT" takeover on primary display. Red alert on secondary + web UI. | Restores when temp drops below 40 °C |
| Emergency | ≥ 60 °C | **Forced deep sleep** (ESP32 powers down all peripherals). Wakes after 5 min to re-check; re-sleeps if still hot. | Automatic after cool-down |

Thresholds are defined in `config.py` as `TEMP_WARN_C`, `TEMP_CRIT_C`, and
`TEMP_EMERGENCY_C`.

### Software — low-battery protection

Firmware module: `bodn/battery.py`. Reads BAT_SENS (GPIO 6) via ADC with
voltage divider. The battery pack's hardware over-discharge cutoff (3.0 V)
is listed but not explicitly confirmed, so software enforces shutdown well
above that level.

#### Battery threshold escalation

| Level | Voltage | Action | Recovery |
|-------|---------|--------|----------|
| OK | > 3.4 V | Normal operation | — |
| Warning | ≤ 3.4 V (~15 %) | Log to serial, amber "BATTERY LOW" banner on displays, web UI alert. NeoPixel brightness reduced. | Clears when voltage rises (charging) |
| Critical | ≤ 3.2 V (~5 %) | Kill NeoPixels. Full-screen "CHARGE ME!" takeover. Red alert on secondary + web UI. | Restores when voltage rises |
| Shutdown | ≤ 3.1 V (~2 %) | **Forced light sleep** (preserves RAM). Wakes on USB power (charger plugged in) or every 60 s to re-check. | Automatic when charger connected |

Thresholds are defined in `config.py` as `BAT_WARN_MV`, `BAT_CRIT_MV`, and
`BAT_SHUTDOWN_MV`.

**Adding new power-drawing peripherals:** Any new component that draws
significant power (LEDs, motors, RF modules, heaters) **must** be registered
in the power-shedding logic in `main.py` `housekeeping_task()`. Both thermal
and battery escalation should disable non-critical loads. See section 9 of
`docs/PERFORMANCE_GUIDELINES.md`.

## SD card

The ILI9341 display breakout's built-in SD card slot is wired to a dedicated SPI3 bus
on ESP32, giving zero contention with the display SPI2 bus.

| Signal | Display SD pad | GPIO |
|--------|---------------|------|
| SD_CS | SD_CS / SD_SS | 0 |
| SD_SCK | SD_CLK / SD_SCK | 17 |
| SD_MOSI | SD_DI / SD_MOSI | 40 |
| SD_MISO | SD_DO / SD_MISO | 38 |

All 3.3V logic — no level shifter needed. Keep wires under 15 cm.

**Card format:** FAT32, any capacity up to 32 GB. Larger cards may work but are not tested.

**Mount point:** `/sd` — mounted at boot if a card is present.

**Graceful degradation:** The device boots and runs normally without an SD card.
Core firmware, UI sounds, and navigation all live on flash. Only media assets (sound banks,
arcade sounds, images, animations) require the SD card.

**Asset management workflow:** Pop the card into a PC card reader and copy files directly —
this is the primary method for bulk loading. The existing WiFi sync tools (`sync.sh`,
`ftp-sync.py`, `ota-push.py`) push firmware to flash only and do not touch SD card content.
See `docs/assets.md` for the directory structure.

## GPIO budget

| Category | Details |
|----------|---------|
| Native GPIOs in use | 26 (SPI2, SPI3/SD, I2S, encoders, NeoPixel, I2C, battery, backlight, 1-Wire) |
| Native GPIOs free | 0 (all pins assigned) |
| PSRAM-reserved (never use) | GPIO 35, 36, 37 |
| UART console (avoid) | GPIO 43 (TX), 44 (RX) |
| MCP1 (0x23) in use | 16 (8 buttons + 2 toggles + master switch + 5 arcade) |
| MCP1 spare | 0 |
| MCP2 (0x21) in use | 4 (encoder push buttons GPA0–1, extra toggles GPA2–3) |
| MCP2 spare | 12 (GPA4–7, GPB0–7 — future expansion) |
| PCA9685 in use | 7 (backlight + 5 arcade LEDs + amp mute) |
| PCA9685 spare | 9 (channels 7–15) |
