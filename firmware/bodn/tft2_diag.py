# bodn/tft2_diag.py -- secondary display hardware diagnostic
#
# REPL usage (after boot or main.py has run):
#
#     from bodn.tft2_diag import test
#     test()
#
# The test:
#   1. (re)initialises _spidma slot 1 for the secondary
#   2. resets the panel via the shared RST pin
#   3. drives RED, GREEN, BLUE, WHITE, BLACK full-screen for 1s each
#   4. draws a 4-quadrant pattern so you can see CS/MOSI/DC integrity
#
# What to expect on healthy hardware:
#   - All five solid colours render edge-to-edge with no fringing
#   - The quadrant pattern shows top-left RED, top-right GREEN,
#     bottom-left BLUE, bottom-right WHITE
#
# Failure signatures:
#   - Stays white / unchanged across all colours -> CS, MOSI, or DC
#     not reaching the panel (or panel VCC/GND broken)
#   - Random noise that does not change with each colour ->
#     the controller never received valid init commands; check RST
#   - Colours wrong / swapped -> MADCTL / RGB-BGR config issue, not wiring
#   - Quadrants smeared or duplicated -> SPI signal integrity (clock too
#     fast for the wiring, or a long unshielded jumper)

import time

from machine import Pin

from bodn import config
from st7735 import ST7735


def _build_displays():
    """Init _spidma for both slots and return (tft, tft2)."""
    import _spidma

    _spidma.init(
        sck=config.TFT_SCK,
        mosi=config.TFT_MOSI,
        baudrate=config.TFT_SPI_BAUDRATE,
    )
    # Re-adding a slot is safe; it overwrites the existing entry.
    _spidma.add_display(
        slot=0,
        cs=config.TFT_CS,
        dc=config.TFT_DC,
        width=config.TFT_WIDTH,
        height=config.TFT_HEIGHT,
        col_off=config.TFT_COL_OFFSET,
        row_off=config.TFT_ROW_OFFSET,
    )
    _spidma.add_display(
        slot=1,
        cs=config.TFT2_CS,
        dc=config.TFT_DC,
        width=config.TFT2_WIDTH,
        height=config.TFT2_HEIGHT,
        col_off=config.TFT2_COL_OFFSET,
        row_off=config.TFT2_ROW_OFFSET,
    )
    rst = Pin(config.TFT_RST, Pin.OUT)
    tft = ST7735(
        0,
        rst=rst,
        width=config.TFT_WIDTH,
        height=config.TFT_HEIGHT,
        col_offset=config.TFT_COL_OFFSET,
        row_offset=config.TFT_ROW_OFFSET,
        madctl=config.TFT_MADCTL,
        skip_reset=False,
    )
    tft2 = ST7735(
        1,
        rst=rst,
        width=config.TFT2_WIDTH,
        height=config.TFT2_HEIGHT,
        col_offset=config.TFT2_COL_OFFSET,
        row_offset=config.TFT2_ROW_OFFSET,
        madctl=config.TFT2_MADCTL,
        skip_reset=True,
    )
    return tft, tft2


def test(hold_ms=1000):
    """Drive solid colour cycles on BOTH displays so they can be compared.

    Reading the result:
      - If primary cycles colours and secondary stays white -> secondary
        is not receiving slot-1 SPI traffic. Suspect CS=GPIO39 wiring or
        the secondary module itself.
      - If neither display cycles -> _spidma bus is dead or shared
        wiring (SCK/MOSI/DC) is broken.
      - If both cycle correctly -> displays are fine, the issue is
        elsewhere in main.py.
    """
    print("tft2_diag: building displays (resets shared RST)")
    tft, tft2 = _build_displays()

    rgb = ST7735.rgb
    colours = (
        ("RED", rgb(255, 0, 0)),
        ("GREEN", rgb(0, 255, 0)),
        ("BLUE", rgb(0, 0, 255)),
        ("WHITE", rgb(255, 255, 255)),
        ("BLACK", 0),
    )
    for name, c in colours:
        print("tft2_diag:", name, "-> both displays")
        tft.fill(c)
        tft.show()
        tft2.fill(c)
        tft2.show()
        time.sleep_ms(hold_ms)

    print("tft2_diag: quadrants on tft2 (TL=R TR=G BL=B BR=W)")
    w, h = tft2.width, tft2.height
    hw, hh = w // 2, h // 2
    tft2.fill(0)
    tft2.fill_rect(0, 0, hw, hh, rgb(255, 0, 0))
    tft2.fill_rect(hw, 0, w - hw, hh, rgb(0, 255, 0))
    tft2.fill_rect(0, hh, hw, h - hh, rgb(0, 0, 255))
    tft2.fill_rect(hw, hh, w - hw, h - hh, rgb(255, 255, 255))
    tft2.show()
    print("tft2_diag: done")
    return tft, tft2


def cs_toggle(count=20, period_ms=100):
    """Toggle TFT2_CS as a plain GPIO so you can scope it.

    Useful when test() leaves both displays white -- this isolates whether
    GPIO 39 itself can drive a pin, separate from the SPI peripheral.
    """
    cs = Pin(config.TFT2_CS, Pin.OUT)
    print("tft2_diag: toggling GPIO", config.TFT2_CS, "x", count)
    for _ in range(count):
        cs.value(0)
        time.sleep_ms(period_ms)
        cs.value(1)
        time.sleep_ms(period_ms)
    print("tft2_diag: cs_toggle done")
