# main.py — Bodn ESP32 entry point
import time
from machine import Pin, SPI
from bodn import config
from bodn.encoder import Encoder
from st7735 import ST7735

# RGB565 colours (byte-swapped for framebuf)
BLACK = ST7735.rgb(0, 0, 0)
WHITE = ST7735.rgb(255, 255, 255)
RED = ST7735.rgb(255, 0, 0)
GREEN = ST7735.rgb(0, 255, 0)
BLUE = ST7735.rgb(0, 0, 255)
YELLOW = ST7735.rgb(255, 255, 0)
CYAN = ST7735.rgb(0, 255, 255)
MAGENTA = ST7735.rgb(255, 0, 255)

BUTTON_COLOURS = [RED, GREEN, BLUE, YELLOW, WHITE, RED]
ENC_STEPS = 20


def create_display():
    spi = SPI(
        2,
        baudrate=26_000_000,
        sck=Pin(config.TFT_SCK),
        mosi=Pin(config.TFT_MOSI),
    )
    return ST7735(
        spi,
        cs=Pin(config.TFT_CS, Pin.OUT),
        dc=Pin(config.TFT_DC, Pin.OUT),
        rst=Pin(config.TFT_RST, Pin.OUT),
        width=config.TFT_WIDTH,
        height=config.TFT_HEIGHT,
        col_offset=config.TFT_COL_OFFSET,
        row_offset=config.TFT_ROW_OFFSET,
        madctl=config.TFT_MADCTL,
    )


def create_buttons():
    return [Pin(p, Pin.IN, Pin.PULL_UP) for p in config.BTN_PINS]


def create_switches():
    return [Pin(p, Pin.IN, Pin.PULL_UP) for p in config.SW_PINS]


def main():
    tft = create_display()
    buttons = create_buttons()
    switches = create_switches()
    encoders = [
        Encoder(config.ENC1_CLK, config.ENC1_DT, config.ENC1_SW),
        Encoder(config.ENC2_CLK, config.ENC2_DT, config.ENC2_SW),
    ]

    while True:
        # Find first pressed button (active low)
        pressed = None
        for i, btn in enumerate(buttons):
            if btn.value() == 0:
                pressed = i
                break

        # Check encoder buttons
        enc_pressed = None
        for i, enc in enumerate(encoders):
            if enc.pressed():
                enc_pressed = i
                break

        # Read switch states (active low)
        sw_states = [sw.value() == 0 for sw in switches]

        enc_pos = [enc.value for enc in encoders]

        # --- Draw ---
        if pressed is not None:
            colour = BUTTON_COLOURS[pressed % len(BUTTON_COLOURS)]
            tft.fill(colour)
            tft.text(f"Btn {pressed}", 10, 10, BLACK)
        elif enc_pressed is not None:
            level = enc_pos[enc_pressed] * 255 // ENC_STEPS
            colour = ST7735.rgb(level, 255 - level, 0)
            tft.fill(colour)
            tft.text(f"Enc {enc_pressed}", 10, 10, BLACK)
        else:
            tft.fill(BLACK)
            tft.text("Bodn", 40, 10, WHITE)

            # Encoder values — show as bars that grow with each step
            bar_colours = [CYAN, MAGENTA]
            for i in range(2):
                bar_y = 35 + i * 25
                max_w = 108  # max bar width in pixels
                bar_w = max_w * enc_pos[i] // ENC_STEPS
                # Background track
                tft.rect(10, bar_y, max_w, 16, WHITE)
                # Filled portion
                if bar_w > 0:
                    tft.fill_rect(10, bar_y, bar_w, 16, bar_colours[i])
                tft.text(f"E{i}:{enc_pos[i]}", 10, bar_y + 2, BLACK)

            # Switch indicators — show as filled/empty boxes
            for i in range(3):
                x = 10 + i * 40
                y = 100
                if sw_states[i]:
                    tft.fill_rect(x, y, 30, 20, GREEN)
                    tft.text("ON", x + 5, y + 5, BLACK)
                else:
                    tft.rect(x, y, 30, 20, WHITE)
                    tft.text("OFF", x + 3, y + 5, WHITE)

        tft.show()
        time.sleep_ms(50)


main()
