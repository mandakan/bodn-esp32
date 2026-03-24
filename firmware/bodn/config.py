# bodn/config.py — pin assignments and constants for ESP32-S3-DevKit-Lipo
#
# GPIO 35, 36, 37 are reserved by OSPI PSRAM on the N8R8 module — never use.
# GPIO 19 is USB OTG D− — left unassigned so OTG port remains usable.
# GPIO 20 (USB OTG D+) is used for 1-Wire (OTG port not used in this project).
# GPIO 47 (SCL) and 48 (SDA) are reserved for the I2C bus (pUEXT pull-ups).
# Buttons and toggle switches are on the MCP23017 I2C GPIO expander.

from micropython import const

# Primary display: 2.8" ILI9341 TFT (SPI bus — shared with secondary display)
TFT_SCK = const(12)
TFT_MOSI = const(11)
TFT_CS = const(10)
TFT_DC = const(8)
TFT_RST = const(9)
TFT_BL = const(1)  # GPIO 43 is UART TX — would flicker backlight on every print()
TFT_WIDTH = const(320)
TFT_HEIGHT = const(240)
TFT_MADCTL = const(0xE0)  # MY + MX + MV (landscape, RGB order)
TFT_COL_OFFSET = const(0)
TFT_ROW_OFFSET = const(0)

# Secondary display: 1.8" ST7735 TFT (shares SPI bus, separate CS)
TFT2_CS = const(39)
TFT2_PANEL_W = 128  # physical panel short side (not a GPIO — no const)
TFT2_PANEL_H = 160  # physical panel long side (not a GPIO — no const)
TFT2_LANDSCAPE = False  # set True when display is mounted sideways

# Effective dimensions after rotation
if TFT2_LANDSCAPE:
    TFT2_WIDTH = 160
    TFT2_HEIGHT = 128
    TFT2_MADCTL = 0x68  # MV + MX + BGR (90° CW — adjust MX/MY to match mounting)
    TFT2_COL_OFFSET = 0
    TFT2_ROW_OFFSET = 0
else:
    TFT2_WIDTH = 128
    TFT2_HEIGHT = 160
    TFT2_MADCTL = 0x08  # BGR only (may need MX depending on module)
    TFT2_COL_OFFSET = 0
    TFT2_ROW_OFFSET = 0

# INMP441 I2S microphone (I2S IN)
I2S_MIC_SCK = const(14)
I2S_MIC_WS = const(15)
I2S_MIC_SD = const(2)  # GPIO 38 is on-board LED — LED load (~15 mA) corrupts I2S signal

# MAX98357A I2S amplifier (I2S OUT)
I2S_SPK_BCK = const(13)
I2S_SPK_WS = const(45)
I2S_SPK_DIN = const(7)  # GPIO 5 is PWR_SENS (board reserved)

# Rotary encoders (KY-040) — must stay on native GPIO for IRQ latency
ENC1_CLK = const(21)  # CLK was 19 (USB OTG D−) → moved to 21
ENC1_DT = const(18)
ENC1_SW = const(17)
ENC2_CLK = const(16)
ENC2_DT = const(3)
ENC2_SW = const(40)
ENC3_CLK = const(41)
ENC3_DT = const(42)
ENC3_SW = const(0)

# Encoder role indices — mount left-to-right next to the display:
#   ENC1 = NAV   (left,   nearest display — menu scroll + back button)
#   ENC2 = ENC_A (middle, mode parameter 1 — e.g. brightness)
#   ENC3 = ENC_B (right,  mode parameter 2 — e.g. speed)
ENC_NAV = const(0)  # index: navigation (home: scroll modes, modes: back button)
ENC_A = const(1)  # index: mode parameter 1
ENC_B = const(2)  # index: mode parameter 2

# WS2812B NeoPixel LEDs — three zones daisy-chained on one data line:
#   Stick A (8 LEDs)  →  Stick B (8 LEDs)  →  Lid Ring (92 LEDs)
# The two sticks sit on the lid (opposite sides or parallel).
# The 144 LED/m strip runs around the inside of the translucent lid perimeter
# (200×120 mm = 640 mm ≈ 92 LEDs).
NEOPIXEL_PIN = const(4)  # GPIO 6 is BAT_SENS (board reserved)
NEOPIXEL_COUNT = const(108)  # 8 + 8 + 92

# LED zone boundaries (start, count) — indices into the NeoPixel chain
LED_STICK_A = (0, 8)  # first 8-LED stick
LED_STICK_B = (8, 8)  # second 8-LED stick
LED_STICKS = (0, 16)  # both sticks combined
LED_LID_RING = (16, 92)  # 144 LED/m strip around lid perimeter

NEOPIXEL_BRIGHTNESS = const(64)  # 0-255, sticks — low for battery + kid eyes
NEOPIXEL_LID_BRIGHTNESS = const(32)  # 0-255, lid ring — lower for ambient glow

# DevKit-Lipo on-board power monitoring (board-reserved — do not reassign)
BAT_SENS_PIN = const(6)  # BAT_SENS: LiPo voltage via voltage divider → ADC
PWR_SENS_PIN = const(5)  # PWR_SENS: high-Z on battery, low when USB present

# DS18B20 1-Wire temperature sensors (battery + enclosure monitoring)
ONEWIRE_PIN = const(20)  # 1-Wire bus — multiple sensors share one GPIO
TEMP_WARN_C = const(40)  # warn threshold (°C) — LiPo degradation accelerates above 40°C
TEMP_CRIT_C = const(50)  # critical threshold (°C) — kill LEDs + dim backlight
TEMP_EMERGENCY_C = const(60)  # emergency (°C) — forced deep sleep (hardware off)

# Low-battery thresholds (mV) — escalation mirrors thermal protection.
# The pack may have a hardware cutoff at ~3.0 V but this is not confirmed,
# so we treat software as the only reliable protection.
BAT_WARN_MV = const(3400)  # ~15 % — show warning, dim LEDs
BAT_CRIT_MV = const(3200)  # ~5 % — kill LEDs, show low-battery screen
BAT_SHUTDOWN_MV = const(3100)  # ~2 % — forced light sleep to protect cell

# I2C bus — pUEXT connector (2.2 kΩ pull-ups on devkit)
I2C_SCL = const(47)
I2C_SDA = const(48)

# MCP23017 GPIO expander — buttons and toggles over I2C
MCP23017_ADDR = const(0x20)  # A0-A2 jumpers all low
MCP_INT_PIN = const(46)  # MCP23017 INTA/INTB → GPIO 46 (active-low, open-drain)
MCP_BTN_PINS = [0, 1, 2, 3, 4, 5, 6, 7]
MCP_SW_PINS = [8, 9]  # GPB0–GPB1 (2 toggle switches; GPB2–3 freed for arcade)
MCP_MASTER_SW_PIN = const(12)  # GPB4 — red-cover flip switch (active-low: 0 = ON)
MCP_ARC_PINS = [10, 11, 13, 14, 15]  # GPB2,GPB3,GPB5,GPB6,GPB7 — 5 arcade buttons

# PCA9685 16-channel 12-bit PWM driver — LED dimming over I2C
PCA9685_ADDR = const(0x40)  # A0-A5 all low (default)
PWM_CH_BACKLIGHT = const(0)  # TFT backlight dimming channel
PWM_CH_ARC1 = const(1)  # Arcade button 1 LED (yellow)
PWM_CH_ARC2 = const(2)  # Arcade button 2 LED (red)
PWM_CH_ARC3 = const(3)  # Arcade button 3 LED (blue)
PWM_CH_ARC4 = const(4)  # Arcade button 4 LED (green)
PWM_CH_ARC5 = const(5)  # Arcade button 5 LED (white)
PWM_CH_AMP_SD = const(6)  # MAX98357A SD pin — hardware mute (0=off, 4095=on)

# Power save
SLEEP_TIMEOUT_S = 300  # default 5 minutes of inactivity before light sleep
