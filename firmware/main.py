# main.py — Bodn ESP32 entry point (async, UI framework)

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

import time
import neopixel
from machine import Pin, SPI
from bodn import config
from bodn.encoder import Encoder
from bodn.session import SessionManager
from bodn.web import start_server
from bodn import storage
from st7735 import ST7735

from bodn.ui.theme import Theme
from bodn.ui.input import InputState
from bodn.ui.screen import ScreenManager
from bodn.ui.overlay import SessionOverlay
from bodn.ui.secondary import SecondaryDisplay
from bodn.ui.home import HomeScreen
from bodn.ui.demo import DemoScreen
from bodn.ui.clock import ClockScreen
from bodn.ui.ambient import AmbientClock

ENC_STEPS = 20
N_LEDS = config.NEOPIXEL_COUNT


def create_hardware():
    """Initialise all hardware peripherals. Returns (spi, tft, tft2, buttons, switches, encoders, np)."""
    spi = SPI(
        2,
        baudrate=26_000_000,
        sck=Pin(config.TFT_SCK),
        mosi=Pin(config.TFT_MOSI),
    )

    # Shared DC and RST pins
    dc = Pin(config.TFT_DC, Pin.OUT)
    rst = Pin(config.TFT_RST, Pin.OUT)

    # Primary display (ILI9341 240×320)
    tft = ST7735(
        spi,
        cs=Pin(config.TFT_CS, Pin.OUT),
        dc=dc,
        rst=rst,
        width=config.TFT_WIDTH,
        height=config.TFT_HEIGHT,
        col_offset=config.TFT_COL_OFFSET,
        row_offset=config.TFT_ROW_OFFSET,
        madctl=config.TFT_MADCTL,
    )

    # Secondary display (ST7735 128×160, shared bus)
    tft2 = ST7735(
        spi,
        cs=Pin(config.TFT2_CS, Pin.OUT),
        dc=dc,
        rst=rst,
        width=config.TFT2_WIDTH,
        height=config.TFT2_HEIGHT,
        col_offset=config.TFT2_COL_OFFSET,
        row_offset=config.TFT2_ROW_OFFSET,
        madctl=config.TFT2_MADCTL,
    )

    buttons = [Pin(p, Pin.IN, Pin.PULL_UP) for p in config.BTN_PINS]
    switches = [Pin(p, Pin.IN, Pin.PULL_UP) for p in config.SW_PINS]
    np = neopixel.NeoPixel(Pin(config.NEOPIXEL_PIN, Pin.OUT), N_LEDS, timing=1)
    encoders = [
        Encoder(config.ENC1_CLK, config.ENC1_DT, config.ENC1_SW, min_val=0, max_val=ENC_STEPS),
        Encoder(config.ENC2_CLK, config.ENC2_DT, config.ENC2_SW, min_val=0, max_val=ENC_STEPS),
        Encoder(config.ENC3_CLK, config.ENC3_DT, config.ENC3_SW, min_val=0, max_val=ENC_STEPS),
    ]
    encoders[config.ENC_A].value = ENC_STEPS // 2   # brightness default
    encoders[config.ENC_B].value = ENC_STEPS // 4   # speed default
    return tft, tft2, buttons, switches, encoders, np


async def ui_loop(session_mgr):
    """Main UI coroutine — both displays driven from the same loop."""
    tft, tft2, buttons, switches, encoders, np = create_hardware()

    theme = Theme(config.TFT_WIDTH, config.TFT_HEIGHT, ST7735.rgb)
    theme2 = Theme(config.TFT2_WIDTH, config.TFT2_HEIGHT, ST7735.rgb)
    inp = InputState(buttons, switches, encoders, time.ticks_ms)
    overlay = SessionOverlay(session_mgr)

    # Primary display — full screen manager with navigation
    manager = ScreenManager(tft, theme, inp)
    manager.set_overlay(overlay)

    mode_screens = {
        "demo": lambda: DemoScreen(np, overlay, enc_steps=ENC_STEPS),
        "clock": lambda: ClockScreen(),
    }
    home = HomeScreen(mode_screens, session_mgr)
    manager.push(home)

    # Secondary display — ambient clock
    secondary = SecondaryDisplay(tft2, theme2)
    secondary.set_screen(AmbientClock())

    # Clear LEDs
    for i in range(N_LEDS):
        np[i] = (0, 0, 0)
    np.write()

    while True:
        manager.tick()
        secondary.tick()
        session_mgr.tick()
        await asyncio.sleep_ms(30)


async def main():
    """Entry point: start web server + UI loop concurrently."""
    settings = storage.load_settings()

    def get_time():
        return time.time()

    def get_date():
        t = time.localtime()
        return "{:04d}-{:02d}-{:02d}".format(t[0], t[1], t[2])

    def on_session_end(record):
        try:
            storage.save_session(record)
        except Exception as e:
            print("Failed to save session:", e)

    session_mgr = SessionManager(settings, get_time, get_date, on_session_end=on_session_end)

    _server = None
    try:
        _server = await start_server(session_mgr, settings)
        print("Web server running on port 80")
    except Exception as e:
        print("Web server failed to start:", e)

    await ui_loop(session_mgr)


try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("Bodn stopped.")
except Exception as e:
    import sys
    sys.print_exception(e)
