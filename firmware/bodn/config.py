# bodn/config.py — pin assignments and constants for ESP32-S3-DevKit-Lipo

# Primary display: 2.8" ILI9341 TFT with touch (SPI bus 2)
# Shares SPI bus (SCK, MOSI) with secondary display
# Real hardware: 240×320. Wokwi can't allocate the framebuffer, so we
# use 128×160 until real hardware arrives. Change these two lines:
TFT_SCK = 12
TFT_MOSI = 11
TFT_CS = 10
TFT_DC = 8
TFT_RST = 9
TFT_BL = 43
TFT_WIDTH = 320
TFT_HEIGHT = 240
TFT_MADCTL = 0x68  # MV + MX + BGR (landscape)
TFT_COL_OFFSET = 0
TFT_ROW_OFFSET = 0

# Secondary display: 1.8" ST7735 TFT (shares SPI bus, separate CS)
TFT2_CS = 37
TFT2_WIDTH = 128
TFT2_HEIGHT = 160
TFT2_MADCTL = 0x08  # BGR only (may need MX depending on module)
TFT2_COL_OFFSET = 0
TFT2_ROW_OFFSET = 0

# INMP441 I2S microphone (I2S IN)
I2S_MIC_SCK = 14
I2S_MIC_WS = 15
I2S_MIC_SD = 38

# MAX98357A I2S amplifier (I2S OUT)
I2S_SPK_BCK = 13
I2S_SPK_WS = 45
I2S_SPK_DIN = 5

# Buttons (active low, internal pull-up)
BTN_PINS = [1, 2, 4, 7, 20, 21, 35, 36]

# Toggle switches (active low, internal pull-up)
SW_PINS = [39, 40, 41, 46]

# Rotary encoders (KY-040)
ENC1_CLK, ENC1_DT, ENC1_SW = 19, 18, 17
ENC2_CLK, ENC2_DT, ENC2_SW = 16, 3, 48
ENC3_CLK, ENC3_DT, ENC3_SW = 47, 42, 0

# Encoder role indices — mount left-to-right next to the display:
#   ENC1 = NAV   (left,   nearest display — menu scroll + back button)
#   ENC2 = ENC_A (middle, mode parameter 1 — e.g. brightness)
#   ENC3 = ENC_B (right,  mode parameter 2 — e.g. speed)
ENC_NAV = 0   # index: navigation (home: scroll modes, modes: back button)
ENC_A = 1     # index: mode parameter 1
ENC_B = 2     # index: mode parameter 2

# WS2812B NeoPixel LEDs (2 × 8-LED sticks chained)
NEOPIXEL_PIN = 6
NEOPIXEL_COUNT = 16
NEOPIXEL_BRIGHTNESS = 64  # 0-255, keep low for battery life and kid-safe eyes
