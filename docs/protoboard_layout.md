# Bodn — Protoboard Layout and Wiring Plan

This document describes the recommended physical layout for building Bodn on
strip/protoboards. The goal is to partition the hardware into three domain boards
so that each board can be debugged, replaced, or upgraded independently.

> **Note:** All pin assignments and I2C addresses come from `firmware/bodn/config.py`
> and `docs/hardware.md`, which are the authoritative references. If anything here
> conflicts, trust those files.

---

## Board partition rationale

Three boards, three domains:

| Board | Location | Domain |
|-------|----------|--------|
| **A — Main/power** | Bottom of enclosure | Brains + power origin |
| **B — Display/audio** | Bottom, toward front face | Time-critical buses (SPI, I2S) |
| **C — Lid controls** | Inside lid | Human interface (buttons, arcade, toggles, LEDs) |

Why not one big board? Each board can be unbolted and re-wired without touching
the others. The harnesses between boards are well-defined and labeled, so you can
unplug a board mid-debugging without de-soldering anything.

---

## Sanity check on the original suggestions

Before the layout, a few corrections and notes:

- **MAX98357A placement:** keep the amp on board A (main). The speaker is in the
  base of the enclosure, so amp-to-speaker wires are short. Running I2S signals
  (3 lines, ~250 MHz BCLK) long distances is riskier than running speaker output
  short. If the speaker moves to the lid, revisit this.

- **PCA9685 → lid arcade LEDs:** PCA9685 stays on board A, but its CH1–5 outputs
  travel to board C (lid) to drive the 5 arcade button LEDs. Those are slow PWM
  signals (~1 kHz) — running them through the lid harness is fine. A small lid-side
  passive breakout can fan them out to the individual button connectors.

- **Display board placement:** the suggestion says "near hinge". In practice this
  board sits near the front face of the base, since that's where the display cables
  terminate. The displays themselves mount on the lid/face panel; this board is the
  breakout between the main-board harness and the display flat-flex/JST.

- **Shared DC/RST on SPI:** the ILI9341 and ST7735 share `DC` (GPIO 8) and `RST`
  (GPIO 9) on the same signal line — only `CS` (GPIO 10 / GPIO 39) is separate.
  This reduces the SPI harness by two wires.

- **INMP441 placement:** if the mic is on the front face of the box (lid or base),
  board B is a natural termination point for its cable. I2S mic signals (3 lines)
  are noise-sensitive; keep that cable short and away from NeoPixel power wires.

- **DS18B20 placement:** both sensors originate from board A (GPIO 20, 1-Wire).
  Run a 3-wire stub harness to wherever the sensors are taped (battery pouch and
  near the DC-DC converter). No need for a separate board.

- **NeoPixel power injection:** for the 92-LED lid ring (640 mm strip), inject 5 V
  power at the midpoint of the strip to avoid voltage drop and colour shift. Run a
  second 5 V/GND pair from the NeoPixel JST on board A to the midpoint pad.

---

## Board A — Main / power board

**Location:** bottom of enclosure, near battery.

### Components

| Component | Notes |
|-----------|-------|
| Olimex ESP32-S3-DevKit-Lipo | Central MCU |
| DC-DC buck-boost (3–16 V → 5 V / 2 A) | 5 V rail origin |
| PCA9685 (Adafruit breakout) | 12-bit PWM, addr 0x40 |
| MAX98357A | I2S class-D amp |
| 4.7 kΩ resistor | 1-Wire pull-up to 3.3 V |
| 10 kΩ resistor | AMP_SD pull-down (GPIO 3, prevents amp glitch on boot) |
| 330 Ω resistor | NeoPixel data series resistor (board-edge, before JST) |

### Power spines

Dedicate one row along each long edge as a power bus. Solder bridge the island
gaps to make a continuous trace.

```
╔══════════════════════════════════════════════════════════════╗
║  [GND spine — left edge, full length]                        ║
║  [5 V spine — right edge, full length, from DC-DC VOUT]      ║
╚══════════════════════════════════════════════════════════════╝
```

3.3 V is taken directly from the ESP32 3V3 pin and distributed with short wires
to PCA9685 VCC and the 1-Wire pull-up. No dedicated 3.3 V spine needed.
MCP23017 lives on board C and gets its 3.3 V via the lid harness.

### Physical layout sketch

```
┌──────────────────────────────────────────────┐  ← board A
│  [BATT JST]  [PWRSW stub]                    │
│                                              │
│  ┌─────────────────────┐                    │
│  │  ESP32-S3-DevKit-   │  ← centred,        │
│  │  Lipo (27×56 mm)    │    GPIO headers     │
│  │                     │    face outward     │
│  └─────────────────────┘                    │
│                                              │
│  [DC-DC]   [PCA9685]                        │
│             ↑ I2C bus (PCA9685 here only)    │
│  [MAX98357A]   [SPK JST]                     │
│                                              │
│  ← power corner (noisy)  | logic corner →   │
│                                              │
│  [NEO JST]  [TEMP JST]  [HDRS-to-B]  [HDRS-to-C] │
└──────────────────────────────────────────────┘
         connector edge (outward-facing)
```

Place the DC-DC converter at one end (noisy switching) and the ESP32 + I2C
modules at the other end. Connect the GND rows of both zones together with
a short wire. Keep signal wires (SPI, I2C, I2S) to the ESP32 side of the
board — don't route them through the area immediately around the DC-DC module.

### Outgoing connectors (all on connector edge)

See [JST pinouts](#jst-connector-pinouts) below.

| Connector | Type | Destination |
|-----------|------|-------------|
| `J-BATT` | JST-PH 2-pin | LiPo battery |
| `J-SPK` | JST-PH 2-pin | Speaker |
| `J-NEO` | JST-XH 3-pin | NeoPixel chain (5 V, GND, data) |
| `J-TEMP` | JST-XH 3-pin | DS18B20 1-Wire stub |
| `J-DISP` | JST-XH 10-pin | Board B (display/audio harness) |
| `J-LID` | JST-XH 10-pin | Board C (lid harness) |

---

## Board B — Display / audio breakout board

**Location:** base of enclosure, near the front face, close to where display cables exit.

This board is a breakout and termination point — it has no active components.
It converts the single 10-pin `J-DISP` harness from board A into individual
connectors for each display and the microphone.

### Components

| Component | Notes |
|-----------|-------|
| 10-pin header (input) | From board A `J-DISP` |
| 2-pin JST `J-ILI` | ILI9341 display (power + backlight) |
| 7-pin header `J-ILI-SPI` | ILI9341 SPI signals |
| 2-pin JST `J-ST7` | ST7735 display (5 V + GND) |
| 2-pin header `J-ST7-SPI` | ST7735 CS only (shares SPI from J-ILI-SPI) |
| 4-pin JST `J-MIC` | INMP441 microphone |

If the MAX98357A moves here in a future revision, add a 5-pin header for I2S OUT.

### Physical layout sketch

```
┌───────────────────────────┐  ← board B (small, ~50×40 mm)
│  [J-DISP header ← board A] │
│                            │
│  [J-ILI-SPI]  [J-ILI]     │  ← to ILI9341 ribbon/cable
│  [J-ST7-SPI]  [J-ST7]     │  ← to ST7735 cable
│  [J-MIC]                  │  ← to INMP441
└───────────────────────────┘
```

### Wiring on this board

The board simply fans out the incoming harness signals to the display/mic connectors:

```
J-DISP pin → break out to appropriate output connector
3.3V, GND from J-DISP → both display VCC rails (or per-display where needed)
5V from J-DISP → ILI9341 LED+, ST7735 VCC, ST7735 BL
SCK/MOSI/DC/RST → shared by both display connectors
TFT1_CS → ILI9341 only
TFT2_CS → ST7735 only
PCA9685 CH0 (BL_PWM) → ILI9341 LED− (PCA9685 sinks current, LED anode to 5V)
MIC_SCK, MIC_WS, MIC_SD + 3.3V/GND → J-MIC
```

---

## Board C — Lid controls board

**Location:** inside the lid, central.

The MCP23017 lives here — this is exactly why I2C runs through the lid harness.
The expander aggregates all the lid controls locally; only 2 I2C signal wires
(plus power) need to cross from the ESP32 to the lid, rather than 16 individual
switch wires.

### Components

| Component | Notes |
|-----------|-------|
| MCP23017 (CJMCU-2317 breakout) | I2C GPIO expander, addr 0x23 — sits here, close to controls |
| 10-pin header (input) | From board A `J-LID` |
| 8 × 2-pin JST (buttons) | Mini momentary buttons (8 off) |
| 2 × 2-pin JST (toggles) | SPST toggle switches |
| 1 × 2-pin JST (master switch) | Red-cover flip switch |
| 5 × 3-pin JST (arcade) | Arcade buttons (switch + LED combined) |
| 2 × 3-pin JST (LED sticks) | WS2812 8-LED sticks (A and B) |

### I2C and power spines

Run SCL, SDA, 3.3 V, and GND as continuous traces the length of this board.
The MCP23017 taps into them, and all switch/button JSTs stub off GND and the
appropriate MCP23017 GPA/GPB pin. The MCP23017 internal pull-ups handle the
active-low inputs — no external resistors needed.

```
LID HARNESS (from board A)
   │
   ├─ SCL ───────── MCP23017 SCL
   ├─ SDA ───────── MCP23017 SDA
   ├─ 3.3V ──────── MCP23017 VCC
   ├─ GND ───────── MCP23017 GND + switch common returns
   ├─ 5V ─────────── arcade LED anodes (via 5V spine)
   └─ PWM_ARC1–5 ─── arcade button LED cathodes (PCA9685 sinks current)
```

### NeoPixel sticks

The two WS2812 8-LED sticks sit on the lid. Their data chain comes from board A
via the NeoPixel JST (`J-NEO`). Run the chain: board A → Stick A → Stick B →
then the long cable continues to the lid ring perimeter strip.

> The lid ring strip power injection point (midpoint, ~LED 54 out of 92) should
> tap 5 V and GND from the `J-NEO` connector or a second `J-NEO-PWR` 2-pin JST
> run in parallel.

### Physical layout sketch

```
┌──────────────────────────────────────────────────────────┐  ← board C (lid)
│  [J-LID header ← board A]                               │
│                                                          │
│  SCL spine ──────────────────────────────────────────    │
│  SDA spine ──────────────────────────────────────────    │
│  5V  spine ──────────────────────────────────────────    │
│  GND spine ──────────────────────────────────────────    │
│                                                          │
│  [MCP23017]  ← I2C device; GPA0–7, GPB0–7 fan out       │
│       │                                                  │
│  BTN0..7    TOG0..1    MASTER    ARC1..5                 │
│  [8×JST]   [2×JST]   [1×JST]   [5×JST]                 │
│                                                          │
│  [STICK-A JST]  [STICK-B JST]  ← NeoPixel 3-pin stubs   │
└──────────────────────────────────────────────────────────┘
```

---

## JST connector pinouts

Use **JST-XH 2.5 mm** for signal harnesses (robust, keyed, widely available).
Use **JST-PH 2.0 mm** for battery and speaker (standard LiPo connector pitch).

Label both ends of every harness with a marker or heat-shrink label (e.g. `A-DISP`,
`B-DISP`, `A-LID`, `C-LID`).

---

### J-NEO — NeoPixel chain (board A → lid ring)

3-pin JST-XH on board A, plus a parallel 2-pin JST-XH for mid-strip power injection.

| Pin | Signal | Wire colour |
|-----|--------|-------------|
| 1 | 5 V | Red |
| 2 | GND | Black |
| 3 | DATA (GPIO 4, via 330 Ω) | Yellow |

Chain: board A `J-NEO` → Stick A (in, out) → Stick B (in, out) → Lid ring start.
Mid-strip power injection: a 2-pin JST `J-NEO-PWR` on board A (5 V, GND) runs a
parallel wire to the midpoint pad of the lid ring strip (~LED index 62 out of the
ring, i.e. index 78 overall).

---

### J-TEMP — DS18B20 1-Wire stub (board A → sensor locations)

3-pin JST-XH on board A. This splits near the sensor mounting points.

| Pin | Signal | Wire colour |
|-----|--------|-------------|
| 1 | 3.3 V | Red |
| 2 | GND | Black |
| 3 | DATA (GPIO 20, 4.7 kΩ pull-up on board A) | Yellow |

Sensor 1 (battery): tape to LiPo pouch with Kapton tape.
Sensor 2 (enclosure): mount near the DC-DC converter on board A.

---

### J-DISP — Display / audio harness (board A → board B)

10-pin JST-XH. Carries the shared SPI bus, both display CS lines, backlight PWM,
I2S mic, and power.

| Pin | Signal | Source | GPIO / rail |
|-----|--------|--------|-------------|
| 1 | 5 V | DC-DC | 5 V rail |
| 2 | 3.3 V | ESP32 3V3 | 3.3 V |
| 3 | GND | Common | GND |
| 4 | SPI_SCK | ESP32 | GPIO 12 |
| 5 | SPI_MOSI | ESP32 | GPIO 11 |
| 6 | SPI_DC | ESP32 | GPIO 8 (shared ILI+ST7) |
| 7 | SPI_RST | ESP32 | GPIO 9 (shared ILI+ST7) |
| 8 | TFT1_CS | ESP32 | GPIO 10 (ILI9341) |
| 9 | TFT2_CS | ESP32 | GPIO 39 (ST7735) |
| 10 | BL_PWM | PCA9685 CH0 | PCA9685 output (current sink, 5V on LED+) |

Mic harness is a separate short stub (board B has a `J-MIC` 4-pin JST-XH):

| Pin | Signal | GPIO |
|-----|--------|------|
| 1 | 3.3 V | — |
| 2 | GND | — |
| 3 | MIC_SCK | GPIO 14 |
| 4 | MIC_WS | GPIO 15 |
| 5 | MIC_SD | GPIO 2 |

> Use a 5-pin JST-XH for `J-MIC` to carry all mic signals in one plug.

---

### J-LID — Lid harness (board A → board C)

10-pin JST-XH. Carries I2C to the MCP23017 that lives on board C, power,
and PCA9685 PWM outputs for arcade LEDs. I2C runs here because the expander
is physically on the lid board — not as a "pass-through" to something further.

| Pin | Signal | Source | GPIO / rail |
|-----|--------|--------|-------------|
| 1 | 3.3 V | ESP32 3V3 | 3.3 V |
| 2 | GND | Common | GND |
| 3 | 5 V | DC-DC | 5 V (arcade LED anodes) |
| 4 | I2C_SCL | ESP32 | GPIO 47 |
| 5 | I2C_SDA | ESP32 | GPIO 48 |
| 6 | PWM_ARC1 | PCA9685 CH1 | arcade LED 1 (yellow) |
| 7 | PWM_ARC2 | PCA9685 CH2 | arcade LED 2 (red) |
| 8 | PWM_ARC3 | PCA9685 CH3 | arcade LED 3 (blue) |
| 9 | PWM_ARC4 | PCA9685 CH4 | arcade LED 4 (green) |
| 10 | PWM_ARC5 | PCA9685 CH5 | arcade LED 5 (white) |

On board C, each arcade button JST gets:
- Pin 1: 5 V (anode)
- Pin 2: PWM_ARCx (cathode — PCA9685 sinks current)
- Pin 3: switch signal → MCP23017 GPBx

> Tip: if the 10-pin connector feels too tight, split into two 5-pin JSTs:
> `J-LID-CTRL` (3.3V, GND, 5V, SCL, SDA) and `J-LID-LED` (5V, PWM×5).

---

### J-BATT — Battery (board A)

2-pin JST-PH 2.0 mm (matches the Olimex DevKit-Lipo battery connector).

| Pin | Signal |
|-----|--------|
| 1 | BAT+ |
| 2 | BAT− |

Short cable run — battery sits directly below board A.

---

### J-SPK — Speaker (board A)

2-pin JST-PH 2.0 mm.

| Pin | Signal |
|-----|--------|
| 1 | OUT+ (MAX98357A OUTP) |
| 2 | OUT− (MAX98357A OUTN) |

---

## Power distribution summary

```
LiPo 3.0–4.2 V ─── DevKit-Lipo system rail
                         │
                    ┌────┴────────────────┐
                    │                     │
              3.3V reg                DC-DC (5V/2A)
                    │                     │
        ESP32, PCA9685 VCC,         ┌──────┼──────────────────┐
        1-Wire pu, MCP23017*       │      │                  │
        (*via J-LID to board C)
                               NeoPixels  PCA9685 V+      ST7735 VCC+BL
                               (J-NEO)    │                  (J-DISP pin 1)
                                       ARC LEDs (J-LID)
                                       ILI9341 LED+ (BL_PWM via PCA9685 CH0)
```

---

## Expanding with a second MCP23017

The I2C bus supports up to 8 MCP23017 boards at addresses 0x20–0x27 (set via A0–A2
jumpers). The current boards use **0x23** (MCP1: A0=high, A1=high, A2=low) and
**0x21** (MCP2: A0=high, A1=low, A2=low).

### Where to place it

MCP1 (0x23) is already on board C. A third expander would go wherever
the new switches are physically located:

| Option | Location | Good for |
|--------|----------|---------|
| **Board C (lid)** | Inside lid | More toggle switches on the lid; taps the existing SCL/SDA spine on board C |
| **Board A (main)** | Base of enclosure | Toggle switches on the box body; taps the I2C bus locally on board A |
| **Both** | One per location | Lid on C, box on A — no harness changes needed either way |

Since the I2C bus runs continuously from board A through the harness to board C,
both boards can host MCP23017 devices and the ESP32 will see all of them.

### Wiring changes

- Second expander connects to the same SCL/SDA/3.3V/GND lines (parallel tap).
- Set address pins before soldering: solder A0–A2 to VCC or GND as needed.
  CJMCU-2317 modules have 10K pull-downs on A0–A2 (default address 0x20).
  RESET must be tied to VCC (no on-board pull-up).
- The `J-LID` harness carries I2C already; board C simply gets a second MCP23017
  breakout tapped onto its SCL/SDA spine. No connector changes.

### Software

Add a second driver instance with the new address. This is a one-line change:

```python
# config.py (add)
MCP23017_ADDR3 = const(0x22)   # third expander (example)
```

```python
# wherever expanders are initialised (e.g. main.py or arcade.py)
mcp2 = MCP23017(i2c, MCP23017_ADDR2)
```

Interrupt lines (INTA/INTB) from the second expander can share the same `MCP_INT_PIN`
(GPIO 46) if you want interrupt-driven reads, since the driver can poll both devices
when the shared interrupt fires.

---

## Passive components and power stabilisation

These components are not on any breakout board — you solder them directly on the
protoboards. They are easy to forget and hard to retrofit, so place them before
anything else on each board.

### Decoupling capacitors (bypass caps)

Every IC needs a small ceramic cap as close to its VCC/GND pins as possible.
Without these, switching transients on the supply rail corrupt logic signals.

| Board | Location | Cap value | Purpose |
|-------|----------|-----------|---------|
| A | PCA9685 VCC–GND | 100 nF (0.1 µF) ceramic | Bypass, logic supply |
| A | PCA9685 V+ (5V rail) – GND | 10 µF electrolytic + 100 nF ceramic in parallel | Bulk + bypass, LED supply |
| A | MAX98357A 5V–GND | 10 µF electrolytic + 100 nF ceramic | Audio supply, filters click on mute |
| A | DC-DC VOUT–GND | 100 µF electrolytic | Output bulk — supplements converter's own cap |
| A | ESP32 3V3–GND (at header) | 10 µF electrolytic + 100 nF ceramic | Smooths transients from SPI/I2S bursts |
| C | MCP23017 VCC–GND | 100 nF ceramic | Bypass |
| C | Second MCP23017 (if fitted) | 100 nF ceramic | Bypass |

Rule of thumb: one **100 nF** ceramic within 5 mm of every VCC pin, plus a
**10 µF** electrolytic anywhere the load changes rapidly (audio amp, NeoPixels).

### Series resistors

| Board | Location | Value | Purpose |
|-------|----------|-------|---------|
| A | NeoPixel data line (GPIO 4, before J-NEO) | 330 Ω | Dampens ringing on fast WS2812 signal edge |
| A | AMP_SD line (GPIO 3 to MAX98357A SD pin) | 10 kΩ pull-down to GND | Holds amp in shutdown during boot glitch (already in components list) |
| A | DS18B20 data line (GPIO 20) | 4.7 kΩ pull-up to 3.3 V | Required for 1-Wire protocol |

### NeoPixel power — load spreading

The 108-LED chain draws up to **~3.5 A at 5 V** at full white. In practice the
firmware caps brightness (sticks 25%, ring 12.5%), so typical draw is well under
1 A. Still:

- **Wire gauge:** use 24 AWG minimum for the 5 V/GND wires on J-NEO. 22 AWG is safer.
- **DC-DC output capacitor:** place a 100 µF electrolytic at the DC-DC VOUT pad
  on board A to absorb inrush when many LEDs switch on simultaneously.
- **Mid-strip power injection:** for the 92-LED lid ring, solder a second 5 V/GND
  wire directly to the strip pads at ~LED 54 (absolute index ~70) and run it back
  to the DC-DC 5 V rail (not through J-NEO). This keeps the voltage within spec at
  the far end of the strip and prevents colour shift.

### Speaker output

The MAX98357A outputs a high-current BTL signal (up to 600 mA peak). No series
resistor needed, but:
- Use 26 AWG or thicker wire for the speaker run.
- Keep the speaker wires twisted together to cancel the differential signal's
  radiated EMI.
- Do not route speaker wires parallel to I2S signal wires.

### I2C bus

The pUEXT connector on the ESP32 DevKit-Lipo already has 2.2 kΩ pull-ups on
SCL (GPIO 47) and SDA (GPIO 48). **Do not add additional pull-up resistors.**
With MCP23017 on board C and PCA9685 on board A, the total bus capacitance from
the harness run is fine at 400 kHz standard mode.

### Power rail summary by board

| Rail | Board A | Board C | Board B |
|------|---------|---------|---------|
| 5 V | Origin (DC-DC VOUT) | Via J-LID pin 3 | Via J-DISP pin 1 |
| 3.3 V | Origin (ESP32 3V3) | Via J-LID pin 1 | Via J-DISP pin 2 |
| GND | Star point | Via J-LID pin 2 | Via J-DISP pin 3 |

All grounds must be common. Connect GND between boards through the harness only —
do not add separate GND wires outside the defined connectors, or you create ground
loops that add noise to audio and I2S signals.

---

## Assembly tips

1. **Install power spines first.** Solder GND and 5 V bus traces on each board
   before placing any components. Test with a multimeter before powering anything.

2. **Mechanically fix the ESP32 DevKit.** Use two M2.5 standoffs through the board
   mounting holes — it is the heaviest and most-handled component.

3. **DC-DC converter corner separation.** On board A, the DC-DC switching traces
   carry the highest current and generate the most EMI. Place it at the battery
   end of the board, with a solid GND pour between it and the ESP32. Keep I2C
   traces away from the DC-DC copper.

4. **Speaker current path.** The MAX98357A can deliver 3 W peak (600 mA at 5 V).
   Use 26 AWG or heavier wire for the speaker run, and keep it away from I2S
   signal wires.

5. **NeoPixel data resistor.** Place the 330 Ω series resistor on board A, right
   before the `J-NEO` connector, not at the strip end.

6. **Lid hinge slack.** Leave at least 80–100 mm of extra wire length in the lid
   harnesses (`J-LID`, `J-NEO`) so the lid can open 180° without tension on the
   connectors.

7. **Connector orientation.** Before crimping, decide on a consistent keying
   convention — e.g. red wire always to pin 1, connector latch always faces up.
   Document any exception.

8. **Test each board standalone** before mating:
   - Board A alone: flash firmware, confirm I2C scan sees 0x40 (PCA9685). MCP1 (0x23) will only appear once the lid harness is connected, because it lives on board C.
   - Board A + C connected: I2C scan should now see 0x21, 0x23, and 0x40.
   - Board B: verify display SPI bus with both CS lines; check mic I2S with a quick record test.
