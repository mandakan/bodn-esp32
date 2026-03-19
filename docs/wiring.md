# Wiring reference

Auto-generated from `firmware/bodn/config.py`. Do not edit between the markers.

Regenerate: `uv run python tools/pinout.py --md`

<!-- pinout:start -->
```mermaid
graph LR
    ESP["ESP32-S3<br/>DevKit-Lipo"]

    ["<br/><sub>GPIO 12 → SCK<br/>GPIO 11 → MOSI<br/>GPIO 10 → CS<br/>GPIO 8 → DC<br/>GPIO 9 → RST<br/>GPIO 43 → BL</sub>"]
     -.- ESP

    ST7735TFT["ST7735 TFT<br/><sub>GPIO 37 → TFT2_CS</sub>"]
    ESP -- SPI --> ST7735TFT

    INMP441I2Smicrophone["INMP441 I2S microphone<br/><sub>GPIO 14 → SCK<br/>GPIO 15 → WS<br/>GPIO 38 → SD</sub>"]
    INMP441I2Smicrophone -- I2S --> ESP

    MAX98357AI2Samplifier["MAX98357A I2S amplifier<br/><sub>GPIO 13 → BCK<br/>GPIO 45 → WS<br/>GPIO 5 → DIN</sub>"]
    ESP -- I2S --> MAX98357AI2Samplifier

    Buttons["Buttons<br/><sub>GPIO 1 → BTN 0<br/>GPIO 2 → BTN 1<br/>GPIO 4 → BTN 2<br/>GPIO 7 → BTN 3<br/>GPIO 20 → BTN 4<br/>GPIO 21 → BTN 5<br/>GPIO 35 → BTN 6<br/>GPIO 36 → BTN 7</sub>"]
    Buttons -.- ESP

    Toggleswitches["Toggle switches<br/><sub>GPIO 39 → SW 0<br/>GPIO 40 → SW 1<br/>GPIO 41 → SW 2<br/>GPIO 46 → SW 3</sub>"]
    Toggleswitches -.- ESP

    Rotaryencoders["Rotary encoders<br/><sub>GPIO 19 → CLK<br/>GPIO 18 → DT<br/>GPIO 17 → SW<br/>GPIO 16 → CLK<br/>GPIO 3 → DT<br/>GPIO 48 → SW<br/>GPIO 47 → CLK<br/>GPIO 42 → DT<br/>GPIO 0 → SW</sub>"]
    Rotaryencoders -.- ESP

    WS2812BNeoPixelLEDs["WS2812B NeoPixel LEDs<br/><sub>GPIO 6 → PIN</sub>"]
    WS2812BNeoPixelLEDs -.- ESP

```

### 

| Signal | GPIO | Config variable |
|--------|------|-----------------|
| SCK | 12 | `TFT_SCK` |
| MOSI | 11 | `TFT_MOSI` |
| CS | 10 | `TFT_CS` |
| DC | 8 | `TFT_DC` |
| RST | 9 | `TFT_RST` |
| BL | 43 | `TFT_BL` |

### ST7735 TFT

| Signal | GPIO | Config variable |
|--------|------|-----------------|
| TFT2_CS | 37 | `TFT2_CS` |

### INMP441 I2S microphone

| Signal | GPIO | Config variable |
|--------|------|-----------------|
| SCK | 14 | `I2S_MIC_SCK` |
| WS | 15 | `I2S_MIC_WS` |
| SD | 38 | `I2S_MIC_SD` |

### MAX98357A I2S amplifier

| Signal | GPIO | Config variable |
|--------|------|-----------------|
| BCK | 13 | `I2S_SPK_BCK` |
| WS | 45 | `I2S_SPK_WS` |
| DIN | 5 | `I2S_SPK_DIN` |

### Buttons

| Signal | GPIO | Config variable |
|--------|------|-----------------|
| BTN 0 | 1 | `BTN_PINS[0]` |
| BTN 1 | 2 | `BTN_PINS[1]` |
| BTN 2 | 4 | `BTN_PINS[2]` |
| BTN 3 | 7 | `BTN_PINS[3]` |
| BTN 4 | 20 | `BTN_PINS[4]` |
| BTN 5 | 21 | `BTN_PINS[5]` |
| BTN 6 | 35 | `BTN_PINS[6]` |
| BTN 7 | 36 | `BTN_PINS[7]` |

### Toggle switches

| Signal | GPIO | Config variable |
|--------|------|-----------------|
| SW 0 | 39 | `SW_PINS[0]` |
| SW 1 | 40 | `SW_PINS[1]` |
| SW 2 | 41 | `SW_PINS[2]` |
| SW 3 | 46 | `SW_PINS[3]` |

### Rotary encoders

| Signal | GPIO | Config variable |
|--------|------|-----------------|
| CLK | 19 | `ENC1_CLK` |
| DT | 18 | `ENC1_DT` |
| SW | 17 | `ENC1_SW` |
| CLK | 16 | `ENC2_CLK` |
| DT | 3 | `ENC2_DT` |
| SW | 48 | `ENC2_SW` |
| CLK | 47 | `ENC3_CLK` |
| DT | 42 | `ENC3_DT` |
| SW | 0 | `ENC3_SW` |

### WS2812B NeoPixel LEDs

| Signal | GPIO | Config variable |
|--------|------|-----------------|
| PIN | 6 | `NEOPIXEL_PIN` |

### All GPIOs

| GPIO | Component | Signal |
|------|-----------|--------|
| 0 | Rotary encoders | SW |
| 1 | Buttons | BTN 0 |
| 2 | Buttons | BTN 1 |
| 3 | Rotary encoders | DT |
| 4 | Buttons | BTN 2 |
| 5 | MAX98357A I2S amplifier | DIN |
| 6 | WS2812B NeoPixel LEDs | PIN |
| 7 | Buttons | BTN 3 |
| 8 |  | DC |
| 9 |  | RST |
| 10 |  | CS |
| 11 |  | MOSI |
| 12 |  | SCK |
| 13 | MAX98357A I2S amplifier | BCK |
| 14 | INMP441 I2S microphone | SCK |
| 15 | INMP441 I2S microphone | WS |
| 16 | Rotary encoders | CLK |
| 17 | Rotary encoders | SW |
| 18 | Rotary encoders | DT |
| 19 | Rotary encoders | CLK |
| 20 | Buttons | BTN 4 |
| 21 | Buttons | BTN 5 |
| 35 | Buttons | BTN 6 |
| 36 | Buttons | BTN 7 |
| 37 | ST7735 TFT | TFT2_CS |
| 38 | INMP441 I2S microphone | SD |
| 39 | Toggle switches | SW 0 |
| 40 | Toggle switches | SW 1 |
| 41 | Toggle switches | SW 2 |
| 42 | Rotary encoders | DT |
| 43 |  | BL |
| 45 | MAX98357A I2S amplifier | WS |
| 46 | Toggle switches | SW 3 |
| 47 | Rotary encoders | CLK |
| 48 | Rotary encoders | SW |
<!-- pinout:end -->

## Encoder roles and placement

The three KY-040 rotary encoders have fixed roles in the UI. Mount them in
a horizontal row directly next to (or below) the TFT display, left to right:

| Position | Encoder | Config index | Role | Rotation | Button press |
|----------|---------|-------------|------|----------|--------------|
| Left | ENC1 | `ENC_NAV` (0) | Navigation | Home: scroll modes | Home: enter mode / Modes: back |
| Middle | ENC2 | `ENC_A` (1) | Parameter A | Mode-specific (e.g. brightness) | Cycle pattern |
| Right | ENC3 | `ENC_B` (2) | Parameter B | Mode-specific (e.g. speed) | Cycle pattern |

**Key rules:**

- **ENC_NAV is always navigation.** It never controls a mode parameter.
  Its button is the universal "back" action inside any mode screen, and
  "enter" on the home screen.
- **ENC_A and ENC_B are mode-specific.** Each mode decides what they
  control. In Demo mode: brightness (A) and speed (B). Future modes
  may repurpose them freely.
- **Place ENC_NAV closest to the display** so the child's dominant hand
  naturally reaches both the screen and the nav knob.

### Suggested panel layout

```
  ┌──────────────────────────────────────────────────────────┐
  │                                                          │
  │    ┌────────────┐                                        │
  │    │            │                                        │
  │    │   Display  │    [NAV]    [ENC A]    [ENC B]         │
  │    │   128×160  │     ◎         ◎          ◎             │
  │    │            │                                        │
  │    └────────────┘                                        │
  │                                                          │
  │    [BTN0] [BTN1] [BTN2] [BTN3]    [SW0] [SW1] [SW2] [SW3] │
  │    [BTN4] [BTN5] [BTN6] [BTN7]                          │
  │                                                          │
  │    ═══════ NeoPixel strip (16 LEDs) ═══════              │
  │                                                          │
  └──────────────────────────────────────────────────────────┘
```

- Display and encoders grouped together at top for menu interaction.
- Buttons in a 4×2 grid below — each button maps to a pattern/colour.
- Toggle switches to the right of the buttons.
- NeoPixel strip at the bottom, visible to the child during play.





