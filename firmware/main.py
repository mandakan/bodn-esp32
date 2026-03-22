# main.py — Bodn ESP32 entry point (async, UI framework)

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

import time
import neopixel
from machine import Pin, SPI, SoftI2C
from micropython import const
from bodn import config
from bodn.encoder import Encoder
from bodn.mcp23017 import MCP23017
from bodn.session import SessionManager
from bodn.web import start_server
from bodn.wifi import WiFiController
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
from bodn.ui.ambient import StatusStrip
from bodn.power import IdleTracker, PowerManager
from bodn import i18n

ENC_STEPS = const(20)
N_LEDS = const(108)  # config.NEOPIXEL_COUNT


def create_hardware():
    """Initialise all hardware peripherals.

    Returns (tft, tft2, buttons, switches, encoders, np, mcp, hw_status).
    Components that fail to initialise degrade gracefully:
    - MCP23017 missing → buttons/switches are empty lists, mcp is None.
    - SPI displays can't be probed (push-only) so are always assumed present.
    """
    hw_status = {"mcp": False}

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

    # MCP23017 GPIO expander for buttons and toggles (I2C)
    mcp = None
    buttons = []
    switches = []
    try:
        i2c = SoftI2C(scl=Pin(config.I2C_SCL), sda=Pin(config.I2C_SDA), freq=400_000)
        mcp = MCP23017(i2c, config.MCP23017_ADDR)
        buttons = [mcp.pin(p) for p in config.MCP_BTN_PINS]
        switches = [mcp.pin(p) for p in config.MCP_SW_PINS]
        hw_status["mcp"] = True
    except Exception as e:
        print("MCP23017 not found, buttons/switches disabled:", e)

    np = neopixel.NeoPixel(Pin(config.NEOPIXEL_PIN, Pin.OUT), N_LEDS, timing=1)
    encoders = [
        Encoder(
            config.ENC1_CLK,
            config.ENC1_DT,
            config.ENC1_SW,
            min_val=0,
            max_val=ENC_STEPS,
        ),
        Encoder(
            config.ENC2_CLK,
            config.ENC2_DT,
            config.ENC2_SW,
            min_val=-10000,
            max_val=10000,
        ),
        Encoder(
            config.ENC3_CLK,
            config.ENC3_DT,
            config.ENC3_SW,
            min_val=0,
            max_val=ENC_STEPS,
        ),
    ]
    encoders[config.ENC_B].value = ENC_STEPS // 4  # speed default

    return tft, tft2, buttons, switches, encoders, np, mcp, hw_status


def create_ui(
    session_mgr, settings, wifi_ctrl, tft, tft2, buttons, switches, encoders, np
):
    """Wire up UI components. Returns (manager, secondary, inp)."""
    theme = Theme(config.TFT_WIDTH, config.TFT_HEIGHT, ST7735.rgb)
    theme2 = Theme(config.TFT2_WIDTH, config.TFT2_HEIGHT, ST7735.rgb)
    inp = InputState(buttons, switches, encoders, time.ticks_ms)
    overlay = SessionOverlay(session_mgr)

    # Primary display — full screen manager with navigation
    manager = ScreenManager(tft, theme, inp)
    manager.set_overlay(overlay)
    if settings.get("debug_perf"):
        manager.debug_perf = True
        manager._perf_time_ms = time.ticks_ms

    # Secondary display — cat face (default) + status strip
    from bodn.ui.catface import CatFaceScreen

    secondary = SecondaryDisplay(tft2, theme2)
    cat = CatFaceScreen()
    secondary.set_content(cat)
    secondary.set_status(StatusStrip(session_mgr))

    def _reset_secondary():
        nonlocal cat
        cat = CatFaceScreen()
        secondary.set_content(cat)

    def _make_mystery():
        from bodn.ui.mystery import MysteryScreen

        _reset_secondary()
        return MysteryScreen(
            np,
            overlay,
            settings=settings,
            secondary_screen=cat,
            on_exit=_reset_secondary,
        )

    def _make_simon():
        from bodn.ui.simon import SimonScreen

        _reset_secondary()
        return SimonScreen(
            np,
            overlay,
            settings=settings,
            secondary_screen=cat,
            on_exit=_reset_secondary,
        )

    def _make_rulefollow():
        from bodn.ui.rulefollow import RuleFollowScreen

        _reset_secondary()
        return RuleFollowScreen(
            np,
            overlay,
            settings=settings,
            secondary_screen=cat,
            on_exit=_reset_secondary,
        )

    def _make_flode():
        from bodn.ui.flode import FlodeScreen

        _reset_secondary()
        return FlodeScreen(
            np,
            overlay,
            settings=settings,
            secondary_screen=cat,
            on_exit=_reset_secondary,
        )

    def _make_settings():
        from bodn.ui.settings import SettingsScreen

        _reset_secondary()
        return SettingsScreen(settings, np, wifi_ctrl)

    mode_screens = {
        "mystery": _make_mystery,
        "simon": _make_simon,
        "rulefollow": _make_rulefollow,
        "flode": _make_flode,
        "demo": lambda: (
            _reset_secondary(),
            DemoScreen(np, overlay, settings=settings),
        )[1],
        "clock": lambda: (_reset_secondary(), ClockScreen(settings=settings))[1],
        "settings": _make_settings,
    }
    home = HomeScreen(
        mode_screens,
        session_mgr,
        order=["mystery", "simon", "rulefollow", "flode", "demo", "clock", "settings"],
    )
    manager.push(home)

    # Clear LEDs
    for i in range(N_LEDS):
        np[i] = (0, 0, 0)
    np.write()

    return manager, secondary, inp


# ---------------------------------------------------------------------------
# Async tasks — each runs at its own tick rate so slow work in one task
# doesn't block the others.  All tasks share objects (manager, inp, …)
# through the same event loop, so no locking is needed.
# ---------------------------------------------------------------------------


async def primary_task(manager, settings, inp, encoders, mcp, idle_tracker, power_mgr):
    """Input scanning + primary display: ~30 ms tick."""
    print("primary_task started, debug_input={}".format(settings.get("debug_input")))
    frame = 0
    errors = 0
    while True:
        try:
            if mcp:
                mcp.refresh()
            manager.tick()
        except KeyboardInterrupt:
            raise
        except Exception as e:
            errors += 1
            print("primary_task error #{}: {}".format(errors, e))

        # Power management
        if inp.has_activity():
            idle_tracker.poke()

        try:
            # Master switch OFF → sleep until flipped back ON
            if power_mgr.master_switch_off():
                power_mgr.sleep_until_master_on()
                idle_tracker.wake()
                manager.invalidate()
            # Menu standby request
            elif settings.get("_sleep_now"):
                settings["_sleep_now"] = False
                power_mgr.sleep_and_wake()
                idle_tracker.wake()
                manager.invalidate()
            # Idle timeout
            elif idle_tracker.tick():
                power_mgr.sleep_and_wake()
                idle_tracker.wake()
                manager.invalidate()
        except Exception as e:
            errors += 1
            print("power_mgr error #{}: {}".format(errors, e))

        # Sync sleep timeout from settings periodically
        if frame % 150 == 0:
            idle_tracker.timeout_s = settings.get("sleep_timeout_s", 300)

        if settings.get("debug_input") and frame % 15 == 0:
            btns = "".join("1" if inp.btn_held[i] else "." for i in range(8))
            sws = "".join("1" if inp.sw[i] else "." for i in range(len(inp.sw)))
            enc_vals = " ".join("{}".format(inp.enc_pos[i]) for i in range(3))
            enc_raw = " ".join(
                "C{}D{}S{}".format(
                    encoders[i].clk.value(),
                    encoders[i].dt.value(),
                    encoders[i].sw.value(),
                )
                for i in range(3)
            )
            print(
                "INP btn[{}] sw[{}] enc[{}] raw[{}]".format(
                    btns, sws, enc_vals, enc_raw
                )
            )

        frame += 1
        await asyncio.sleep_ms(30)


async def secondary_task(secondary):
    """Secondary display: ~200 ms tick.

    Fast enough for game content updates (emotion changes), cheap when
    idle thanks to per-zone dirty tracking in SecondaryDisplay.
    """
    errors = 0
    while True:
        try:
            secondary.tick()
        except KeyboardInterrupt:
            raise
        except Exception as e:
            errors += 1
            print("secondary_task error #{}: {}".format(errors, e))
        await asyncio.sleep_ms(200)


async def housekeeping_task(session_mgr):
    """Session management and periodic bookkeeping: ~500 ms tick."""
    errors = 0
    while True:
        try:
            session_mgr.tick()
        except KeyboardInterrupt:
            raise
        except Exception as e:
            errors += 1
            print("housekeeping_task error #{}: {}".format(errors, e))
        await asyncio.sleep_ms(500)


async def main():
    """Entry point: start web server + UI loop concurrently."""
    settings = storage.load_settings()
    i18n.init(settings.get("language", "sv"))

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

    session_mgr = SessionManager(
        settings, get_time, get_date, on_session_end=on_session_end
    )
    wifi_ctrl = WiFiController(settings)

    _server = None
    try:
        _server = await start_server(session_mgr, settings)
        print("Web server running on port 80")
    except Exception as e:
        print("Web server failed to start:", e)

    tft, tft2, buttons, switches, encoders, np, mcp, hw_status = create_hardware()

    # Publish hardware status for diagnostics
    from bodn.diag import set_hw_status

    set_hw_status(hw_status)
    manager, secondary, inp = create_ui(
        session_mgr,
        settings,
        wifi_ctrl,
        tft,
        tft2,
        buttons,
        switches,
        encoders,
        np,
    )

    # Power management
    idle_tracker = IdleTracker(
        timeout_s=settings.get("sleep_timeout_s", config.SLEEP_TIMEOUT_S),
        time_fn=time.time,
    )
    power_mgr = PowerManager(tft, tft2, np, mcp)

    await asyncio.gather(
        primary_task(manager, settings, inp, encoders, mcp, idle_tracker, power_mgr),
        secondary_task(secondary),
        housekeeping_task(session_mgr),
    )


try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("Bodn stopped.")
except Exception as e:
    import sys

    print("FATAL:", e)
    sys.print_exception(e)
