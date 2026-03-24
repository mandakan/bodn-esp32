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
from bodn.pca9685 import PCA9685
from bodn.arcade import ArcadeButtons
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

N_LEDS = const(108)  # config.NEOPIXEL_COUNT


def create_hardware():
    """Initialise all hardware peripherals.

    Returns (tft, tft2, buttons, switches, encoders, np, mcp, pwm, arcade, hw_status).
    Components that fail to initialise degrade gracefully:
    - MCP23017 missing → buttons/switches are empty lists, mcp is None.
    - PCA9685 missing → pwm is None (no LED dimming), arcade LEDs disabled.
    - SPI displays can't be probed (push-only) so are always assumed present.
    """
    hw_status = {"mcp": False, "pca": False, "temp": False}

    spi = SPI(
        1,
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
    # skip_reset=True — shares RST pin with primary, don't reset both
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
        skip_reset=True,
    )

    # Shared I2C bus for MCP23017 and PCA9685
    i2c = SoftI2C(scl=Pin(config.I2C_SCL), sda=Pin(config.I2C_SDA), freq=400_000)

    # MCP23017 GPIO expander for buttons, toggles, and arcade switches
    mcp = None
    pwm = None
    arcade = None
    buttons = []
    switches = []
    try:
        mcp = MCP23017(i2c, config.MCP23017_ADDR)
        buttons = [mcp.pin(p) for p in config.MCP_BTN_PINS]
        switches = [mcp.pin(p) for p in config.MCP_SW_PINS]
        hw_status["mcp"] = True
    except Exception as e:
        print("MCP23017 not found, buttons/switches disabled:", e)

    # PCA9685 PWM driver for LED dimming + arcade LEDs + amp mute
    try:
        pwm = PCA9685(i2c, config.PCA9685_ADDR)
        pwm.set_freq(1000)
        hw_status["pca"] = True
        # Enable amplifier by default (SD pin high = on)
        pwm.set_duty(config.PWM_CH_AMP_SD, 4095)
    except Exception as e:
        print("PCA9685 not found, PWM dimming disabled:", e)

    # Arcade buttons (switch input via MCP23017 + LED output via PCA9685)
    if mcp:
        pwm_channels = [
            config.PWM_CH_ARC1,
            config.PWM_CH_ARC2,
            config.PWM_CH_ARC3,
            config.PWM_CH_ARC4,
            config.PWM_CH_ARC5,
        ]
        arcade = ArcadeButtons(mcp, config.MCP_ARC_PINS, pwm, pwm_channels)

    # DS18B20 temperature sensors (1-Wire)
    try:
        from bodn.temperature import scan as temp_scan

        n_sensors = temp_scan()
        if n_sensors > 0:
            hw_status["temp"] = True
            print("DS18B20: {} sensor(s) found".format(n_sensors))
        else:
            print("DS18B20: no sensors on 1-Wire bus")
    except Exception as e:
        print("DS18B20 init failed:", e)

    np = neopixel.NeoPixel(Pin(config.NEOPIXEL_PIN, Pin.OUT), N_LEDS, timing=1)
    encoders = [
        Encoder(config.ENC1_CLK, config.ENC1_DT, config.ENC1_SW),
        Encoder(config.ENC2_CLK, config.ENC2_DT, config.ENC2_SW),
        Encoder(config.ENC3_CLK, config.ENC3_DT, config.ENC3_SW),
    ]

    return tft, tft2, buttons, switches, encoders, np, mcp, pwm, arcade, hw_status


def create_ui(
    session_mgr,
    settings,
    wifi_ctrl,
    tft,
    tft2,
    buttons,
    switches,
    encoders,
    np,
    arcade=None,
):
    """Wire up UI components. Returns (manager, secondary, inp)."""
    theme = Theme(config.TFT_WIDTH, config.TFT_HEIGHT, ST7735.rgb)
    theme2 = Theme(config.TFT2_WIDTH, config.TFT2_HEIGHT, ST7735.rgb)
    arcade_pins = arcade.pins if arcade else []
    inp = InputState(
        buttons, switches, encoders, time.ticks_ms, arcade_pins=arcade_pins
    )
    overlay = SessionOverlay(session_mgr, settings=settings)

    # Primary display — full screen manager with navigation
    manager = ScreenManager(tft, theme, inp)
    manager.set_overlay(overlay)
    if settings.get("debug_perf"):
        manager.debug_perf = True
        manager._perf_time_ms = time.ticks_ms

    # Secondary display — cat face (default) + status strip
    from bodn.ui.catface import CatFaceScreen

    secondary = SecondaryDisplay(tft2, theme2, landscape=config.TFT2_LANDSCAPE)
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

    def _make_garden():
        from bodn.ui.garden import GardenScreen
        from bodn.ui.garden_secondary import GardenSecondary

        garden_sec = GardenSecondary()
        secondary.set_content(garden_sec)
        return GardenScreen(
            np,
            overlay,
            settings=settings,
            secondary_screen=garden_sec,
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
        "garden": _make_garden,
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
        order=[
            "mystery",
            "simon",
            "rulefollow",
            "flode",
            "garden",
            "demo",
            "clock",
            "settings",
        ],
        settings=settings,
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
            if errors <= 3:
                import sys

                sys.print_exception(e)
            else:
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
            btns = "".join(
                "1" if inp.btn_held[i] else "." for i in range(len(inp.btn_held))
            )
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


async def housekeeping_task(session_mgr, np, settings):
    """Session management, temperature + battery monitoring: ~500 ms tick.

    Temperature overwatch (thresholds in config.py):
      OK       (< 40 °C): normal operation.
      WARNING  (≥ 40 °C): log, amber banner, reduce LED brightness.
      CRITICAL (≥ 50 °C): kill LEDs, dim backlight, full-screen alert.
      EMERGENCY(≥ 60 °C): forced deep sleep (5 min cycle).

    Battery overwatch (thresholds in config.py, mV-based):
      OK       (> 3.4 V): normal operation.
      WARNING  (≤ 3.4 V): log, amber banner, reduce LED brightness.
      CRITICAL (≤ 3.2 V): kill LEDs, full-screen "CHARGE ME!" alert.
      SHUTDOWN (≤ 3.1 V): forced light sleep to protect the cell.

    Shared settings keys for UI:
      _temp_status / _temp_c   — temperature state + reading.
      _bat_status  / _bat_mv   — battery state + voltage.
    """
    from bodn import temperature
    from bodn import battery

    errors = 0
    _prev_temp = "ok"
    _prev_bat = "ok"
    settings["_temp_status"] = "ok"
    settings["_temp_c"] = None
    settings["_bat_status"] = "ok"
    settings["_bat_mv"] = 0

    while True:
        try:
            session_mgr.tick()
        except KeyboardInterrupt:
            raise
        except Exception as e:
            errors += 1
            print("housekeeping_task error #{}: {}".format(errors, e))

        # Temperature overwatch — poll is cheap (cached 30 s in temperature.py)
        try:
            if temperature.sensor_count() > 0:
                temp_status = temperature.status()
                t_max = temperature.max_temp()
                settings["_temp_status"] = temp_status
                settings["_temp_c"] = t_max

                # Emergency: forced deep sleep — only way to cut power draw
                if temp_status == "emergency":
                    print(
                        "TEMP EMERGENCY ({}C >= {}C): FORCED DEEP SLEEP".format(
                            int(t_max), config.TEMP_EMERGENCY_C
                        )
                    )
                    # Kill everything before sleeping
                    for i in range(N_LEDS):
                        np[i] = (0, 0, 0)
                    np.write()
                    try:
                        from machine import Pin, deepsleep

                        Pin(config.TFT_BL, Pin.OUT).value(0)
                        # Deep sleep for 5 minutes, then wake to re-check
                        deepsleep(300_000)
                    except Exception:
                        pass

                if temp_status == "critical" and _prev_temp != "critical":
                    print(
                        "TEMP CRITICAL ({}C >= {}C): "
                        "killing NeoPixels, dimming backlight".format(
                            int(t_max), config.TEMP_CRIT_C
                        )
                    )
                    # Kill NeoPixels — biggest heat contributor
                    for i in range(N_LEDS):
                        np[i] = (0, 0, 0)
                    np.write()
                    # Dim display backlight to minimum
                    try:
                        from machine import Pin

                        Pin(config.TFT_BL, Pin.OUT).value(0)
                    except Exception:
                        pass

                elif temp_status == "warn" and _prev_temp == "ok":
                    print(
                        "TEMP WARNING ({}C >= {}C): "
                        "reducing NeoPixel brightness".format(
                            int(t_max), config.TEMP_WARN_C
                        )
                    )

                elif temp_status == "ok" and _prev_temp != "ok":
                    print("TEMP OK ({}C): resumed normal operation".format(int(t_max)))
                    # Restore backlight
                    try:
                        from machine import Pin

                        Pin(config.TFT_BL, Pin.OUT).value(1)
                    except Exception:
                        pass

                _prev_temp = temp_status
        except Exception as e:
            errors += 1
            print("temp_monitor error #{}: {}".format(errors, e))

        # Battery overwatch — only meaningful when on battery (not USB)
        try:
            bat_status = battery.status()
            settings["_bat_status"] = bat_status
            settings["_bat_mv"] = battery.voltage_mv()

            if bat_status == "shutdown":
                mv = battery.voltage_mv()
                print(
                    "BAT SHUTDOWN ({}mV <= {}mV): FORCED LIGHT SLEEP".format(
                        mv, config.BAT_SHUTDOWN_MV
                    )
                )
                # Kill LEDs + backlight, then sleep
                for i in range(N_LEDS):
                    np[i] = (0, 0, 0)
                np.write()
                try:
                    from machine import Pin
                    import machine as _machine

                    Pin(config.TFT_BL, Pin.OUT).value(0)
                    # Light sleep (not deep) — preserves RAM, wakes on
                    # USB plug (PWR_SENS goes low) or button press.
                    import esp32

                    pwr_pin = Pin(config.PWR_SENS_PIN, Pin.IN)
                    esp32.gpio_wakeup(pwr_pin, esp32.WAKEUP_ANY_LOW)
                    _machine.lightsleep(60_000)  # re-check every 60 s
                except Exception:
                    pass

            elif bat_status == "critical" and _prev_bat != "critical":
                mv = battery.voltage_mv()
                print(
                    "BAT CRITICAL ({}mV <= {}mV): killing NeoPixels".format(
                        mv, config.BAT_CRIT_MV
                    )
                )
                for i in range(N_LEDS):
                    np[i] = (0, 0, 0)
                np.write()

            elif bat_status == "warn" and _prev_bat == "ok":
                mv = battery.voltage_mv()
                print(
                    "BAT WARNING ({}mV <= {}mV): reducing NeoPixel brightness".format(
                        mv, config.BAT_WARN_MV
                    )
                )

            elif bat_status in ("ok", "usb") and _prev_bat not in ("ok", "usb"):
                print("BAT OK: resumed normal operation")

            _prev_bat = bat_status
        except Exception as e:
            errors += 1
            print("bat_monitor error #{}: {}".format(errors, e))

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

    tft, tft2, buttons, switches, encoders, np, mcp, pwm, arcade, hw_status = (
        create_hardware()
    )

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
        arcade=arcade,
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
        housekeeping_task(session_mgr, np, settings),
    )


try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("Bodn stopped.")
except Exception as e:
    import sys

    print("FATAL:", e)
    sys.print_exception(e)
