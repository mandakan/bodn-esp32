# Getting started with hardware

This guide walks through first boot on real hardware — from flashing MicroPython to
seeing debug output on the serial console.

## Prerequisites

- Olimex ESP32-S3-DevKit-Lipo (or compatible ESP32-S3 board)
- USB-C cable
- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Host tools installed: `uv sync`

## Which USB port?

The Olimex board has **two USB-C ports**:

| Port | Chip | Use for |
|------|------|---------|
| **UART** (top, near antenna) | CH340X | Programming, serial console, REPL |
| **USB OTG** (bottom) | Native USB | Not used — **avoid plugging this one** during development (GPIO 19 = SD_MISO, GPIO 20 = 1-Wire; OTG will conflict) |

Always plug into the **UART port**.

## 1. Flash MicroPython

If your board doesn't have MicroPython yet:

```bash
# Install esptool
uv pip install esptool

# Find your serial port
ls /dev/cu.usbserial-*    # macOS
ls /dev/ttyUSB*            # Linux

# Erase flash (hold BOOT button while plugging in if needed)
esptool.py --chip esp32s3 --port /dev/cu.usbserial-XXXX erase_flash

# Flash MicroPython (download the ESP32-S3 build with SPIRAM from micropython.org)
esptool.py --chip esp32s3 --port /dev/cu.usbserial-XXXX \
    write_flash -z 0 ESP32_GENERIC_S3-SPIRAM_OCT-20xxxxxx-vX.Y.Z.bin
```

Use the **ESP32_GENERIC_S3-SPIRAM_OCT** build (octal SPIRAM matches the N8R8 module).

### Custom firmware (optional)

A custom firmware build adds the `_audiomix` native C module, which moves audio
mixing to a dedicated FreeRTOS task on core 0 (Python runs on core 1). This
eliminates audio glitches caused by SPI display writes blocking the Python VM.
It provides 16 uniform voices and a sample-accurate step clock for the sequencer.
The device works fine with stock firmware — `AudioEngine` falls back to the
viper/IRQ path automatically.

```bash
# One-time: install ESP-IDF v5.5.1
git clone -b v5.5.1 --recursive https://github.com/espressif/esp-idf.git ~/esp-idf
~/esp-idf/install.sh esp32s3

# One-time: init MicroPython submodule (if not already)
git submodule update --init --recursive

# Build
source ~/esp-idf/export.sh
./tools/build-firmware.sh

# Flash
esptool.py --chip esp32s3 --port /dev/cu.usbserial-XXXX erase_flash
esptool.py --chip esp32s3 --port /dev/cu.usbserial-XXXX \
    write_flash -z 0 build/firmware-bodn.bin
```

Verify on the REPL: `import _audiomix` should succeed without errors.

## 2. Deploy firmware

```bash
# Copy all firmware files to the device
./tools/sync.sh
```

This uses `mpremote` under the hood. The device resets automatically after deploy.

## 3. Connect to the serial console

### Option A: mpremote REPL (recommended)

```bash
uv run mpremote connect auto repl
```

This connects to the first available serial port and drops you into the MicroPython
REPL. You'll see boot output (`BOOT [CFG] ok`, `BOOT [NET] ok`, etc.) followed by
`main.py` startup messages.

Press **Ctrl-C** to interrupt the running program and get an interactive `>>>` prompt.
Press **Ctrl-D** to soft-reset (re-runs `boot.py` + `main.py`).
Press **Ctrl-X** to exit mpremote.

### Option B: plain serial terminal

Any serial terminal at **115200 baud** works:

```bash
# Find the port
ls /dev/cu.usbserial-*    # macOS — look for CH340 device
ls /dev/ttyUSB*            # Linux

# screen
screen /dev/cu.usbserial-XXXX 115200

# minicom
minicom -D /dev/cu.usbserial-XXXX -b 115200

# picocom (Linux)
picocom -b 115200 /dev/ttyUSB0
```

To exit `screen`: press **Ctrl-A** then **K**, confirm with **Y**.

## 4. What you'll see on boot

A successful boot prints:

```
BOOT [CFG] ok
BOOT [NET] ok ip=192.168.4.1
BOOT [NTP] warn
BOOT done, free=XXXXXX
```

Meanwhile, the primary display shows a progress bar with status dots
(green = ok, amber = skipped, red = failed).

| Step | What it does | Common warnings |
|------|-------------|-----------------|
| CFG | Load settings from flash | `warn` on first boot (no saved settings yet — defaults used) |
| NET | Connect WiFi | `fail` if no WiFi credentials configured (AP mode still works) |
| NTP | Sync clock | `warn` if no internet — quiet hours disabled, clock inaccurate |
| GO! | Ready | Always ok |

## 5. Diagnostic screen

Hold the **NAV encoder button** (ENC1, MCP2 GPA0) while powering on to enter the
diagnostic screen. It shows:

- MicroPython version and platform
- CPU frequency
- RAM free/used
- Flash free/total
- WiFi MAC address and IP
- Battery level (if battery module present)
- Boot step results

Press any encoder button to dismiss and continue to `main.py`.

## 6. Configure WiFi

By default the device starts in AP mode (creates its own "Bodn" network).
To connect to your home WiFi, open a REPL and use the CLI helpers:

```python
from bodn.cli import *

wifi("YourNetwork", "YourPassword")
# WiFi configured: mode=sta ssid=YourNetwork
# Reboot to apply: reboot()
reboot()
```

Other useful CLI commands:

```python
show()                        # print all settings
set("language", "en")         # change language (en/sv)
set("sleep_timeout_s", 600)   # idle sleep timeout
save()                        # persist to flash
ap()                          # switch back to AP mode
```

## 7. Skip main.py for debugging

If the device is stuck (e.g. encoder IRQs blocking Ctrl-C), create a flag
file to skip main.py on the next boot:

```bash
uv run mpremote connect auto fs touch :/skip_main
# Press RST — boots normally but drops to REPL instead of starting main.py
# The flag auto-deletes so the next reset boots normally
```

From the REPL you can run the built-in diagnostic tools:

### I2C bus monitor

Live-polls the I2C bus and reports devices appearing/disappearing. Also
reads MCP23017 pin states so you can verify buttons while wiggling wires.

```python
from bodn.i2c_diag import run
run()     # Ctrl-C to stop
```

Example output:
```
[SCAN] Found: 0x21, 0x23, 0x40
0x23 A=[11111111] B=[11111111]  MCP1 (buttons/switches)
[-] 0x23 LOST      (MCP1 (buttons/switches))    ← wire disconnected
[+] 0x23 appeared  (MCP1 (buttons/switches))    ← reconnected
```

### Encoder oscilloscope

Displays raw CLK and DT signals on the primary TFT as a rolling scope
trace. Useful for checking quadrature waveforms, spotting noise from long
wires, or confirming that pull-up resistors are working.

```python
from bodn.encoder_scope import run
run()             # both encoders (4 traces: CLK1, DT1, CLK2, DT2)
run(enc=1)        # ENC1 (NAV) only — larger traces
run(enc=2)        # ENC2 only
run(sample_ms=1)  # fastest sweep (1ms per pixel)
run(sample_ms=5)  # slower sweep, easier to see individual detents
```

Turn the encoder slowly and look for clean square waves with CLK leading
DT by 90°. Noise shows up as ragged edges or random spikes — add 4.7kΩ
pull-ups to 3.3V on the CLK and DT lines if you see this.

## 8. Common debug tasks

### Check if I2C devices are detected

```python
from machine import I2C, Pin
i2c = I2C(0, scl=Pin(47), sda=Pin(48))
[hex(a) for a in i2c.scan()]
# ['0x21', '0x23', '0x40']    # MCP2 + MCP1 + PCA9685
```

### Read a button via MCP23017

```python
from bodn.mcp23017 import MCP23017
from machine import I2C, Pin
i2c = I2C(0, scl=Pin(47), sda=Pin(48))
mcp = MCP23017(i2c, 0x23)
mcp.read_port_a()  # returns byte — bit 0 = GPA0, etc.
```

### Test NeoPixels

```python
import neopixel
from machine import Pin
np = neopixel.NeoPixel(Pin(4, Pin.OUT), 108, timing=1)
np[0] = (10, 0, 0)  # dim red on first LED
np.write()
```

### Test display

```python
from machine import Pin, SPI
from bodn import config
from st7735 import ST7735
spi = SPI(2, baudrate=26_000_000, sck=Pin(config.TFT_SCK), mosi=Pin(config.TFT_MOSI))
tft = ST7735(spi, cs=Pin(config.TFT_CS, Pin.OUT), dc=Pin(config.TFT_DC, Pin.OUT),
    rst=Pin(config.TFT_RST, Pin.OUT), width=config.TFT_WIDTH, height=config.TFT_HEIGHT,
    col_offset=config.TFT_COL_OFFSET, row_offset=config.TFT_ROW_OFFSET, madctl=config.TFT_MADCTL)
tft.fill(ST7735.rgb(0, 0, 255))
tft.show()
```

### Soft reset

```python
import machine
machine.soft_reset()   # re-runs boot.py + main.py
```

## 9. Troubleshooting

| Problem | Fix |
|---------|-----|
| No serial output at all | Wrong USB port — use the UART port (CH340X), not OTG |
| `No module named 'bodn'` | Firmware not deployed — run `./tools/sync.sh` |
| Port not found (`/dev/cu.usbserial-*`) | Install CH340 driver: [macOS driver](https://www.wch-ic.com/downloads/CH341SER_MAC_ZIP.html) |
| `BOOT [NET] fail` | Normal on first boot — WiFi defaults to AP mode. Connect to the "Bodn" network |
| `BOOT [NTP] warn` | No internet access — harmless, just means clock isn't synced |
| Display shows nothing | Check SPI wiring (SCK→12, MOSI→11, CS→10, DC→8, RST→9) |
| MCP23017 not found (missing from I2C scan) | Check I2C wiring (SCL→47, SDA→48), 3.3V power, and RESET tied to VCC. Run `from bodn.i2c_diag import run; run()` |
| MCP pins fluctuate with no buttons pressed | Long button wires need 4.7kΩ external pull-ups to 3.3V (internal 100kΩ too weak for >10cm wires) |
| Encoders skip steps or behave erratically | Add 4.7kΩ pull-ups on CLK/DT lines. Check wire length and routing away from power lines |
| Can't Ctrl-C to REPL (encoder IRQ blocks it) | Create `/skip_main` flag file (see §7), or press RST and run `./tools/sync.sh --minimal` within 1s |

## 10. Next steps

- **Wokwi simulation**: see the [README](../README.md#wokwi-simulation) for running in the simulator
- **OTA updates**: once WiFi is working, use `tools/ota-push.py` to push firmware without USB
- **Parental controls**: connect to the device's IP in a browser to configure session limits
- **Pin reference**: see `docs/wiring.md` for the full auto-generated pinout
