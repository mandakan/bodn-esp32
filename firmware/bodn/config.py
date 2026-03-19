# bodn/config.py — pin assignments and constants for ESP32-S3-DevKit-Lipo

# Display: 1.8" ST7735 TFT (SPI bus 2)
TFT_SCK = 12
TFT_MOSI = 11
TFT_CS = 10
TFT_DC = 8
TFT_RST = 9
TFT_BL = 43
TFT_WIDTH = 128
TFT_HEIGHT = 160
TFT_MADCTL = 0x08  # bit 3 = BGR subpixel order (common for ST7735/ILI9341)
TFT_COL_OFFSET = 0
TFT_ROW_OFFSET = 0

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

# WS2812B NeoPixel LEDs (2 × 8-LED sticks chained)
NEOPIXEL_PIN = 6
NEOPIXEL_COUNT = 16
NEOPIXEL_BRIGHTNESS = 64  # 0-255, keep low for battery life and kid-safe eyes
