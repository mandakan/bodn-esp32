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
| **USB OTG** (bottom) | Native USB | Not used — **avoid plugging this one** during development (GPIO 19/20 conflict with ENC1) |

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

Hold the **NAV encoder button** (ENC1, GPIO 17) while powering on to enter the
diagnostic screen. It shows:

- MicroPython version and platform
- CPU frequency
- RAM free/used
- Flash free/total
- WiFi MAC address and IP
- Battery level (if battery module present)
- Boot step results

Press any encoder button to dismiss and continue to `main.py`.

## 6. Common debug tasks

### Check if I2C devices are detected

```python
>>> from machine import SoftI2C, Pin
>>> i2c = SoftI2C(scl=Pin(47), sda=Pin(48))
>>> [hex(a) for a in i2c.scan()]
['0x20', '0x40']    # MCP23017 + PCA9685
```

### Read a button via MCP23017

```python
>>> from bodn.mcp23017 import MCP23017
>>> from machine import SoftI2C, Pin
>>> i2c = SoftI2C(scl=Pin(47), sda=Pin(48))
>>> mcp = MCP23017(i2c)
>>> mcp.read_port_a()  # returns byte — bit 0 = GPA0, etc.
```

### Test NeoPixels

```python
>>> import neopixel
>>> from machine import Pin
>>> np = neopixel.NeoPixel(Pin(4, Pin.OUT), 108, timing=1)
>>> np[0] = (10, 0, 0)  # dim red on first LED
>>> np.write()
```

### Test display

```python
>>> from machine import Pin, SPI
>>> from bodn import config
>>> from st7735 import ST7735
>>> spi = SPI(2, baudrate=26_000_000, sck=Pin(config.TFT_SCK), mosi=Pin(config.TFT_MOSI))
>>> tft = ST7735(spi, cs=Pin(config.TFT_CS, Pin.OUT), dc=Pin(config.TFT_DC, Pin.OUT),
...     rst=Pin(config.TFT_RST, Pin.OUT), width=config.TFT_WIDTH, height=config.TFT_HEIGHT,
...     col_offset=config.TFT_COL_OFFSET, row_offset=config.TFT_ROW_OFFSET, madctl=config.TFT_MADCTL)
>>> tft.fill(ST7735.rgb(0, 0, 255))
>>> tft.show()
```

### Soft reset

```python
>>> import machine
>>> machine.soft_reset()   # re-runs boot.py + main.py
```

## 7. Troubleshooting

| Problem | Fix |
|---------|-----|
| No serial output at all | Wrong USB port — use the UART port (CH340X), not OTG |
| `No module named 'bodn'` | Firmware not deployed — run `./tools/sync.sh` |
| Port not found (`/dev/cu.usbserial-*`) | Install CH340 driver: [macOS driver](https://www.wch-ic.com/downloads/CH341SER_MAC_ZIP.html) |
| `BOOT [NET] fail` | Normal on first boot — WiFi defaults to AP mode. Connect to the "Bodn" network |
| `BOOT [NTP] warn` | No internet access — harmless, just means clock isn't synced |
| Display shows nothing | Check SPI wiring (SCK→12, MOSI→11, CS→10, DC→8, RST→9) |
| MCP23017 not found (`0x20` missing from I2C scan) | Check I2C wiring (SCL→47, SDA→48) and 3.3V power |
| Encoders skip steps or behave erratically | OTG USB port is plugged in (conflicts with ENC1 on GPIO 19) |

## 8. Next steps

- **Wokwi simulation**: see the [README](../README.md#wokwi-simulation) for running in the simulator
- **OTA updates**: once WiFi is working, use `tools/ota-push.py` to push firmware without USB
- **Parental controls**: connect to the device's IP in a browser to configure session limits
- **Pin reference**: see `docs/wiring.md` for the full auto-generated pinout
