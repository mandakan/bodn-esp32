# bodn/config.py — pin assignments and constants for ESP32-S3-DevKit-Lipo
#
# GPIO 35, 36, 37 are reserved by OSPI PSRAM on the N8R8 module — never use.
# GPIO 20 (USB OTG D+) is used for 1-Wire (OTG port not used in this project).
# GPIO 47 (SCL) and 48 (SDA) are reserved for the I2C bus (pUEXT pull-ups).
# Buttons and toggle switches are on MCP1 (MCP23017 at 0x23) I2C GPIO expander.
# Encoder push buttons are on MCP2 (MCP23017 at 0x21).
# SD card uses a dedicated SPI3 bus on freed GPIOs (see SD card section below).

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
TFT_MADCTL = const(0xE8)  # MY + MX + MV + BGR (landscape, panel uses BGR subpixels)
TFT_COL_OFFSET = const(0)
TFT_ROW_OFFSET = const(0)

# Secondary display: 1.8" ST7735 TFT (shares SPI bus, separate CS)
TFT2_CS = const(39)
TFT2_PANEL_W = const(128)  # physical panel short side
TFT2_PANEL_H = const(160)  # physical panel long side
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
AMP_SD_PIN = const(3)  # amp shutdown — direct GPIO (PCA9685 glitches on boot)

# Rotary encoders (KY-040) — CLK/DT on native GPIO, decoded by PCNT hardware.
# Push buttons (SW) moved to MCP2 to free GPIOs 17 and 40 for SD card SPI3.
ENC1_CLK = const(21)  # CLK was 19 (USB OTG D−) → moved to 21
ENC1_DT = const(18)
ENC2_CLK = const(16)
ENC2_DT = const(41)  # was 44 — GPIO 44 is UART0 RX, encoder signal blocks serial

# Encoder role indices — two encoders, NAV doubles as parameter B in game modes:
#   ENC1 = NAV   (left,  menu scroll + back button; rotation = param B in games)
#   ENC2 = ENC_A (right, mode parameter 1 — e.g. brightness)
ENC_NAV = const(0)  # index: navigation + parameter B in game modes
ENC_A = const(1)  # index: mode parameter 1
ENC_B = const(0)  # same as NAV — NAV rotation doubles as param B in games

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

# MCP1 — MCP23017 GPIO expander: buttons, toggles, arcade switches over I2C
MCP23017_ADDR = const(0x23)  # A0=high, A1=high, A2=low
MCP_INT_PIN = const(46)  # MCP23017 INTA/INTB → GPIO 46 (active-low, open-drain)

# MCP2 — second MCP23017: encoder push buttons + extra toggles (frees GPIOs 17/40 for SD SPI3)
MCP2_ADDR = const(0x21)  # A0=high, A1=low, A2=low
MCP2_ENC1_SW = const(0)  # GPA0 — ENC1 push button (NAV, was GPIO 17)
MCP2_ENC2_SW = const(1)  # GPA1 — ENC2 push button (ENC_A, was GPIO 40)
MCP2_SW_LEFT = const(2)  # GPA2 — toggle switch (far left on lid)
MCP2_SW_RIGHT = const(3)  # GPA3 — toggle switch (far right on lid)

# SD card — dedicated SPI3 bus on ILI9341 display breakout SD slot
# GPIOs 17 and 40 freed by moving encoder buttons to MCP2.
# GPIO 0: strapping pin with pull-up → CS deasserted at boot (safe default).
# GPIO 19: previously reserved for touch CS (touch dropped).
SD_CS = const(0)  # SD chip select (strapping pull-up = deasserted at boot)
SD_SCK = const(17)  # freed from ENC1_SW
SD_MOSI = const(40)  # freed from ENC2_SW
SD_MISO = const(38)  # GPIO 19 is USB D−; GPIO 38 is on-board LED (freed)
MCP_BTN_PINS = (0, 1, 2, 3, 4, 5, 6, 7)
MCP_SW_PINS = (8, 9)  # GPB0–GPB1 (2 toggle switches; GPB2–3 freed for arcade)
MCP_MASTER_SW_PIN = const(12)  # GPB4 — red-cover flip switch (active-low: 0 = ON)
MCP_ARC_PINS = (10, 11, 13, 14, 15)  # GPB2,GPB3,GPB5,GPB6,GPB7 — 5 arcade buttons

# PCA9685 16-channel 12-bit PWM driver — LED dimming over I2C
PCA9685_ADDR = const(0x40)  # A0-A5 all low (default)
PWM_CH_BACKLIGHT = const(0)  # TFT backlight dimming channel
PWM_CH_ARC1 = const(1)  # Arcade idx 0 — green (far left)
PWM_CH_ARC2 = const(2)  # Arcade idx 1 — blue
PWM_CH_ARC3 = const(3)  # Arcade idx 2 — white (centre)
PWM_CH_ARC4 = const(4)  # Arcade idx 3 — yellow
PWM_CH_ARC5 = const(5)  # Arcade idx 4 — red (far right)
PWM_CH_AMP_SD = const(6)  # UNUSED — amp SD moved to GPIO 3 (PCA9685 glitches on boot)

# Mini button colors — physical left-to-right matches electrical index 0–7
BUTTON_COLORS = ("green", "blue", "white", "yellow", "red", "black", "green", "blue")
# Arcade button colors — physical left-to-right matches electrical index 0–4
ARCADE_COLORS = ("green", "blue", "white", "yellow", "red")

# Encoder sensitivity: detents per logical unit
# 1=high (every click), 2=medium, 3=low (for young children)
ENCODER_SENS_OPTIONS = (1, 2, 3)
ENCODER_SENS_DEFAULT = 1
ENCODER_SENS_LABELS = ("high", "medium", "low")


def encoder_dpu(settings):
    """Return detents-per-unit from settings (1=high, 2=medium, 3=low)."""
    return settings.get("encoder_sensitivity", ENCODER_SENS_DEFAULT)


# Power save
SLEEP_TIMEOUT_S = (
    0  # 0 = disabled; sleep unreliable until wake sources are fully tested
)

# FTP server (dev mode — STA only, never exposed on AP)
FTP_PORT = 21
