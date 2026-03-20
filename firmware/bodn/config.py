# bodn/config.py — pin assignments and constants for ESP32-S3-DevKit-Lipo
#
# GPIO 35, 36, 37 are reserved by OSPI PSRAM on the N8R8 module — never use.
# GPIO 19, 20 are USB OTG D−/D+ — left unassigned so OTG port remains usable.
# GPIO 47 (SCL) and 48 (SDA) are reserved for the I2C bus (pUEXT pull-ups).
# Buttons and toggle switches are on the MCP23017 I2C GPIO expander.

# Primary display: 2.8" ILI9341 TFT (SPI bus — shared with secondary display)
TFT_SCK = 12
TFT_MOSI = 11
TFT_CS = 10
TFT_DC = 8
TFT_RST = 9
TFT_BL = 1  # GPIO 43 is UART TX — would flicker backlight on every print()
TFT_WIDTH = 320
TFT_HEIGHT = 240
TFT_MADCTL = 0x68  # MV + MX + BGR (landscape)
TFT_COL_OFFSET = 0
TFT_ROW_OFFSET = 0

# Secondary display: 1.8" ST7735 TFT (shares SPI bus, separate CS)
TFT2_CS = 39
TFT2_WIDTH = 128
TFT2_HEIGHT = 160
TFT2_MADCTL = 0x08  # BGR only (may need MX depending on module)
TFT2_COL_OFFSET = 0
TFT2_ROW_OFFSET = 0

# INMP441 I2S microphone (I2S IN)
I2S_MIC_SCK = 14
I2S_MIC_WS = 15
I2S_MIC_SD = 2  # GPIO 38 is on-board LED — LED load (~15 mA) corrupts I2S signal

# MAX98357A I2S amplifier (I2S OUT)
I2S_SPK_BCK = 13
I2S_SPK_WS = 45
I2S_SPK_DIN = 7  # GPIO 5 is PWR_SENS (board reserved)

# Rotary encoders (KY-040) — must stay on native GPIO for IRQ latency
ENC1_CLK, ENC1_DT, ENC1_SW = 21, 18, 17  # CLK was 19 (USB OTG D−) → moved to 21
ENC2_CLK, ENC2_DT, ENC2_SW = 16, 3, 40
ENC3_CLK, ENC3_DT, ENC3_SW = 41, 42, 0

# Encoder role indices — mount left-to-right next to the display:
#   ENC1 = NAV   (left,   nearest display — menu scroll + back button)
#   ENC2 = ENC_A (middle, mode parameter 1 — e.g. brightness)
#   ENC3 = ENC_B (right,  mode parameter 2 — e.g. speed)
ENC_NAV = 0  # index: navigation (home: scroll modes, modes: back button)
ENC_A = 1  # index: mode parameter 1
ENC_B = 2  # index: mode parameter 2

# WS2812B NeoPixel LEDs (2 × 8-LED sticks chained)
NEOPIXEL_PIN = 4  # GPIO 6 is BAT_SENS (board reserved)
NEOPIXEL_COUNT = 16
NEOPIXEL_BRIGHTNESS = 64  # 0-255, keep low for battery life and kid-safe eyes

# DevKit-Lipo on-board power monitoring (board-reserved — do not reassign)
BAT_SENS_PIN = 6  # BAT_SENS: LiPo voltage via voltage divider → ADC
PWR_SENS_PIN = 5  # PWR_SENS: high-Z on battery, driven low when USB power present

# I2C bus — pUEXT connector (2.2 kΩ pull-ups on devkit)
I2C_SCL = 47
I2C_SDA = 48

# MCP23017 GPIO expander — buttons and toggles over I2C
MCP23017_ADDR = 0x20  # A0-A2 jumpers all low
MCP_BTN_PINS = [0, 1, 2, 3, 4, 5, 6, 7]
MCP_SW_PINS = [8, 9, 10, 11]
