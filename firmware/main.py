# main.py — Bodn ESP32 entry point (async, UI framework)

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

import time
import micropython
from machine import Pin
from bodn.neo import neo
from micropython import const
from bodn import config
from bodn.encoder import Encoder
from bodn.mcp23017 import MCP23017
from bodn.pca9685 import PCA9685
from bodn.arcade import ArcadeButtons
from bodn.session import SessionManager
from bodn.web import start_server
from bodn.ftp import start_ftp
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

# Ensure Ctrl-C (0x03) always raises KeyboardInterrupt, even under async load.
micropython.kbd_intr(3)

# Frame budget for the priority-ordered main loop.
# Graphics are opportunistic: render only when time remains after
# input + audio servicing.  This caps the frame rate at ~30 fps and
# ensures audio never starves.
_FRAME_BUDGET_MS = const(33)
_MIN_RENDER_MS = const(5)  # don't start a render with less than this


def _i2c_bus_recover(scl_pin, sda_pin):
    """Bit-bang 9 SCL clocks to unstick any I2C slave holding SDA low.

    Must be called BEFORE any I2C peripheral is initialised so we can
    freely toggle the pins as GPIO.  Standard recovery per I2C spec §3.1.16.
    """
    import time

    scl = Pin(scl_pin, Pin.OUT, value=1)
    sda = Pin(sda_pin, Pin.IN, Pin.PULL_UP)

    if sda.value():
        return  # SDA is high — bus is fine, skip recovery

    print("I2C: SDA stuck low, running bus recovery")
    for _ in range(9):
        scl.value(0)
        time.sleep_us(5)
        scl.value(1)
        time.sleep_us(5)
        if sda.value():
            break

    # Generate STOP condition: SDA low→high while SCL is high
    sda_out = Pin(sda_pin, Pin.OUT, value=0)
    time.sleep_us(5)
    sda_out.value(1)
    time.sleep_us(5)


def create_hardware():
    """Initialise all hardware peripherals.

    Returns (tft, tft2, buttons, switches, encoders, mcp, pwm, arcade, audio, hw_status).
    Components that fail to initialise degrade gracefully:
    - MCP23017 missing → buttons/switches are empty lists, mcp is None.
    - PCA9685 missing → pwm is None (no LED dimming), arcade LEDs disabled.
    - AudioEngine missing → audio is None (no sound).
    - SPI displays can't be probed (push-only) so are always assumed present.
    """
    hw_status = {
        "mcp": False,
        "pca": False,
        "temp": False,
        "audio": False,
        "nfc": False,
    }

    # Shared RST pin
    rst = Pin(config.TFT_RST, Pin.OUT)

    import _spidma

    _spidma.init(
        sck=config.TFT_SCK,
        mosi=config.TFT_MOSI,
        baudrate=config.TFT_SPI_BAUDRATE,
    )
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

    # Primary display (ILI9341 240×320, DMA slot 0)
    tft = ST7735(
        0,
        rst=rst,
        width=config.TFT_WIDTH,
        height=config.TFT_HEIGHT,
        col_offset=config.TFT_COL_OFFSET,
        row_offset=config.TFT_ROW_OFFSET,
        madctl=config.TFT_MADCTL,
    )

    # Secondary display (ST7735 128×160, DMA slot 1)
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
    print("SPI: DMA")

    # Show logo on secondary display while the rest of init runs
    try:
        import _draw as _dm

        with open("/sd/sprites/lo-logo-s2.bdf", "rb") as _f:
            _s2d = _f.read()
        _s2a = _dm.load(_s2d)
        _s2i = _dm.info(_s2a)
        _s2w, _s2h = _s2i["max_width"], _s2i["height"]
        tft2.fill(0)
        _dm.sprite(
            tft2._buf,
            tft2.width,
            (tft2.width - _s2w) // 2,
            (tft2.height - _s2h) // 2,
            _s2a,
            0,
            ST7735.rgb(255, 255, 255),
        )
        tft2.show()
        del _s2d, _s2a, _s2i, _dm
    except Exception as _e:
        print("Secondary logo:", _e)

    # Shared I2C bus for MCP23017 and PCA9685
    # I2C bus recovery — after a soft reboot, the PN532 may be stuck
    # mid-transaction (SDA held low).  9 SCL clock pulses flush the
    # slave state machine.  Must run BEFORE any I2C peripheral init.
    _i2c_bus_recover(config.I2C_SCL, config.I2C_SDA)

    # Native _mcpinput C module — deterministic input capture on core 0.
    import _mcpinput

    # boot.py uses SoftI2C so I2C_NUM_0 is free for us.
    _mcpinput.init(
        sda=config.I2C_SDA,
        scl=config.I2C_SCL,
        freq=400_000,
        mcp_addr=config.MCP23017_ADDR,
        debounce_ms=12,
        int_pin=-1,
    )
    from bodn.native_i2c import NativeI2C

    i2c = NativeI2C()
    print("_mcpinput: native I2C + MCP1 scan task on core 0")

    # I2C bus scan — show all devices for diagnostics
    i2c_devs = i2c.scan()
    print("I2C scan: [{}]".format(", ".join("0x{:02X}".format(a) for a in i2c_devs)))
    hw_status["i2c"] = ["0x{:02X}".format(a) for a in i2c_devs]

    # MCP1 — MCP23017 GPIO expander for buttons, toggles, and arcade switches
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
        print(
            "MCP1 (0x{:02X}) initialised — {} buttons, {} switches".format(
                config.MCP23017_ADDR, len(buttons), len(switches)
            )
        )
    except Exception as e:
        print(
            "MCP1 (0x{:02X}) not found, buttons/switches disabled: {}".format(
                config.MCP23017_ADDR, e
            )
        )

    # MCP2 — second MCP23017 for encoder push buttons + extra toggles
    mcp2 = None
    try:
        mcp2 = MCP23017(i2c, config.MCP2_ADDR)
        # Append extra toggle switches from MCP2 (sw[2] = SW_L, sw[3] = SW_R)
        switches.append(mcp2.pin(config.MCP2_SW_LEFT))
        switches.append(mcp2.pin(config.MCP2_SW_RIGHT))
        print(
            "MCP2 (0x{:02X}) initialised — encoder switches + 2 toggles".format(
                config.MCP2_ADDR
            )
        )
    except Exception as e:
        print(
            "MCP2 (0x{:02X}) not found, encoder buttons via fallback: {}".format(
                config.MCP2_ADDR, e
            )
        )

    # PCA9685 PWM driver for LED dimming + arcade LEDs + amp mute
    try:
        pwm = PCA9685(i2c, config.PCA9685_ADDR)
        pwm.set_freq(1000)
        # Restore backlight — PCA9685.reset() turned all channels off
        pwm.set_duty(config.PWM_CH_BACKLIGHT, 4095)
        hw_status["pca"] = True
        print(
            "PCA9685 (0x{:02X}) initialised — PWM @ 1 kHz".format(config.PCA9685_ADDR)
        )
    except Exception as e:
        print(
            "PCA9685 (0x{:02X}) not found, PWM dimming disabled: {}".format(
                config.PCA9685_ADDR, e
            )
        )

    # PN532 NFC reader (shared I2C bus)
    # MCP2 controls PN532 power via transistor gate — power-cycles
    # the chip on every boot for reliable recovery after soft reboot.
    try:
        from bodn import nfc as _nfc_mod

        _nfc_mod.init(i2c, mcp2=mcp2)
        _nfc_mod.power_on()
        from bodn.nfc import NFCReader as _NFCProbe

        _nfc_probe = _NFCProbe()
        if _nfc_probe.available():
            hw_status["nfc"] = True
            print("PN532 (0x{:02X}) initialised — NFC ready".format(config.PN532_ADDR))
        else:
            print("PN532 (0x{:02X}) not found, NFC disabled".format(config.PN532_ADDR))
        del _nfc_probe
    except Exception as e:
        print("NFC init failed:", e)

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
        # Restore backlight — C led_init may have cleared all PCA9685 channels
        if pwm:
            pwm.set_duty(config.PWM_CH_BACKLIGHT, 4095)

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

    # NeoPixel init (C engine)
    neo.init()
    print("NeoPixel: C engine on GPIO", config.NEOPIXEL_PIN)

    # Encoder push buttons are on MCP2. If MCP2 is unavailable, the sw
    # attribute falls back to a stub that always reads 1 (not pressed).
    if mcp2:
        enc1_sw = mcp2.pin(config.MCP2_ENC1_SW)
        enc2_sw = mcp2.pin(config.MCP2_ENC2_SW)
    else:
        from bodn.mcp23017 import _StubPin

        enc1_sw = _StubPin()
        enc2_sw = _StubPin()

    encoders = [
        Encoder(config.ENC1_CLK, config.ENC1_DT, enc1_sw),
        Encoder(config.ENC2_CLK, config.ENC2_DT, enc2_sw),
    ]

    # I2S audio output (MAX98357A) — native _audiomix C mixer on core 0
    audio = None
    try:
        from bodn.audio import AudioEngine

        audio = AudioEngine(
            bck=config.I2S_SPK_BCK,
            ws=config.I2S_SPK_WS,
            din=config.I2S_SPK_DIN,
            amp=config.AMP_SD_PIN,
        )
        hw_status["audio"] = True
        print("AudioEngine initialised (native, core 0)")
    except Exception as e:
        print("Audio init failed:", e)

    return (
        tft,
        tft2,
        buttons,
        switches,
        encoders,
        mcp,
        mcp2,
        pwm,
        arcade,
        audio,
        hw_status,
    )


def create_ui(
    session_mgr,
    settings,
    wifi_ctrl,
    tft,
    tft2,
    buttons,
    switches,
    encoders,
    arcade=None,
    audio=None,
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
            overlay,
            arcade=arcade,
            audio=audio,
            settings=settings,
            secondary_screen=cat,
            on_exit=_reset_secondary,
        )

    def _make_simon():
        from bodn.ui.simon import SimonScreen

        _reset_secondary()
        return SimonScreen(
            overlay,
            arcade=arcade,
            audio=audio,
            settings=settings,
            secondary_screen=cat,
            on_exit=_reset_secondary,
        )

    def _make_rulefollow():
        from bodn.ui.rulefollow import RuleFollowScreen

        _reset_secondary()
        return RuleFollowScreen(
            overlay,
            arcade=arcade,
            audio=audio,
            settings=settings,
            secondary_screen=cat,
            on_exit=_reset_secondary,
        )

    def _make_sortera():
        from bodn.ui.sortera import SorteraScreen

        _reset_secondary()
        return SorteraScreen(
            overlay,
            arcade=arcade,
            audio=audio,
            settings=settings,
            secondary_screen=cat,
            on_exit=_reset_secondary,
        )

    def _make_rakna():
        from bodn.ui.rakna import RaknaScreen

        _reset_secondary()
        return RaknaScreen(
            overlay,
            arcade=arcade,
            audio=audio,
            settings=settings,
            secondary_screen=cat,
            on_exit=_reset_secondary,
        )

    def _make_blippa():
        from bodn.ui.blippa import BlippaScreen

        _reset_secondary()
        return BlippaScreen(
            overlay,
            arcade=arcade,
            audio=audio,
            settings=settings,
            secondary_screen=cat,
            on_exit=_reset_secondary,
        )

    def _make_flode():
        from bodn.ui.flode import FlodeScreen

        _reset_secondary()
        return FlodeScreen(
            overlay,
            arcade=arcade,
            audio=audio,
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
            overlay,
            arcade=arcade,
            settings=settings,
            secondary_screen=garden_sec,
            on_exit=_reset_secondary,
        )

    def _make_soundboard(on_progress=None):
        from bodn.ui.soundboard import SoundboardScreen
        from bodn.ui.soundboard_secondary import SoundboardSecondary

        sb_sec = SoundboardSecondary()
        secondary.set_content(sb_sec)
        return SoundboardScreen(
            overlay,
            audio=audio,
            arcade=arcade,
            settings=settings,
            secondary_screen=sb_sec,
            on_exit=_reset_secondary,
            on_progress=on_progress,
        )

    def _make_sequencer(on_progress=None):
        from bodn.ui.sequencer import SequencerScreen, preload_sequencer_assets
        from bodn.ui.sequencer_secondary import SequencerSecondary

        drum_bufs = preload_sequencer_assets(on_progress=on_progress)
        seq_sec = SequencerSecondary()
        secondary.set_content(seq_sec)
        return SequencerScreen(
            overlay,
            audio=audio,
            arcade=arcade,
            settings=settings,
            secondary_screen=seq_sec,
            on_exit=_reset_secondary,
            drum_bufs=drum_bufs,
        )

    def _make_space(on_progress=None):
        from bodn.ui.space import SpaceScreen, preload_space_assets
        from bodn.ui.android import AndroidFaceScreen

        bufs = preload_space_assets(on_progress=on_progress)
        stellar = AndroidFaceScreen()
        secondary.set_content(stellar)
        return SpaceScreen(
            overlay,
            audio=audio,
            arcade=arcade,
            settings=settings,
            secondary_screen=stellar,
            on_exit=_reset_secondary,
            preloaded_bufs=bufs,
        )

    def _make_story():
        from bodn.ui.story import StoryScreen

        _reset_secondary()
        return StoryScreen(
            overlay,
            audio=audio,
            arcade=arcade,
            settings=settings,
            secondary_screen=cat,
            on_exit=_reset_secondary,
        )

    def _make_tone_explorer():
        from bodn.ui.tone_explorer import ToneExplorerScreen
        from bodn.ui.tone_explorer_secondary import ToneExplorerSecondary

        sec = ToneExplorerSecondary()
        secondary.set_content(sec)
        return ToneExplorerScreen(
            overlay,
            audio=audio,
            arcade=arcade,
            settings=settings,
            secondary_screen=sec,
            on_exit=_reset_secondary,
        )

    def _make_highfive(on_progress=None):
        from bodn.ui.highfive import HighFiveScreen, preload_highfive_assets

        sound_bufs = preload_highfive_assets(on_progress=on_progress)
        _reset_secondary()
        return HighFiveScreen(
            overlay,
            arcade=arcade,
            audio=audio,
            settings=settings,
            secondary_screen=cat,
            on_exit=_reset_secondary,
            sound_bufs=sound_bufs,
        )

    def _make_settings():
        from bodn.ui.settings import SettingsScreen

        _reset_secondary()
        return SettingsScreen(settings, wifi_ctrl)

    mode_screens = {
        "mystery": _make_mystery,
        "simon": _make_simon,
        "rulefollow": _make_rulefollow,
        "flode": _make_flode,
        "garden": _make_garden,
        "space": _make_space,
        "story": _make_story,
        "soundboard": _make_soundboard,
        "sequencer": _make_sequencer,
        "tone_explorer": _make_tone_explorer,
        "highfive": _make_highfive,
        "blippa": _make_blippa,
        "sortera": _make_sortera,
        "rakna": _make_rakna,
        "demo": lambda: (
            _reset_secondary(),
            DemoScreen(overlay, arcade=arcade, settings=settings),
        )[1],
        "clock": lambda: (_reset_secondary(), ClockScreen(settings=settings))[1],
        "settings": _make_settings,
    }
    mode_order = [
        "demo",
        "mystery",
        "simon",
        "highfive",
        "rulefollow",
        "space",
        "story",
        "flode",
        "garden",
        "soundboard",
        "sequencer",
        "tone_explorer",
        "blippa",
        "sortera",
        "rakna",
        "clock",
        "settings",
    ]
    # Expose mode list to web API (not persisted, runtime only)
    settings["_all_modes"] = mode_order
    home = HomeScreen(
        mode_screens,
        session_mgr,
        order=mode_order,
        settings=settings,
        audio=audio,
    )
    manager.push(home)

    # Clear LEDs
    neo.all_off()

    return manager, secondary, inp, mode_screens


# ---------------------------------------------------------------------------
# Async tasks — each runs at its own tick rate so slow work in one task
# doesn't block the others.  All tasks share objects (manager, inp, …)
# through the same event loop, so no locking is needed.
# ---------------------------------------------------------------------------


async def input_scan_task(mcp, mcp2, inp, switches=None):
    """Fast input scanning at ~200 Hz.

    MCP1 buttons/arcade are debounced by the _mcpinput C task on core 0.
    Python drains events and scans MCP2 + encoders only.

    Edges are latched until the display task calls inp.consume().
    """
    import _mcpinput

    # Build MCP1 pin → (kind, index) lookup from config
    _pin_map = {}
    for i, p in enumerate(config.MCP_BTN_PINS):
        _pin_map[p] = ("btn", i)
    for i, p in enumerate(config.MCP_ARC_PINS):
        _pin_map[p] = ("arc", i)
    # MCP1 toggle switch pins (read from bitmask, not events)
    _sw_pins = config.MCP_SW_PINS
    # Number of MCP1 switches (sw[0], sw[1])
    _n_mcp1_sw = len(_sw_pins)
    _sw = switches or []

    while True:
        try:
            # Drain debounced events from C module
            events = _mcpinput.get_events()
            for ev_type, pin, _t in events:
                mapping = _pin_map.get(pin)
                if mapping:
                    kind, idx = mapping
                    if ev_type == _mcpinput.PRESS:
                        inp.native_press(kind, idx)
                    else:
                        inp.native_release(kind, idx)

            # Read MCP1 toggle switch state from bitmask
            port_state = _mcpinput.read_state()
            for i in range(_n_mcp1_sw):
                inp.sw[i] = bool(port_state & (1 << _sw_pins[i]))

            # Read MCP2 toggle switches (sw[2], sw[3], etc.) via Python
            for i in range(_n_mcp1_sw, len(_sw)):
                inp.sw[i] = _sw[i].value() == 0

            # MCP2 refresh for encoder buttons
            if mcp2:
                mcp2.refresh()

            # Encoders + encoder buttons (PCNT + MCP2)
            inp.scan_encoders()
        except Exception:
            pass
        await asyncio.sleep_ms(5)


async def primary_task(
    manager, settings, inp, encoders, mcp, mcp2, idle_tracker, power_mgr
):
    """Display update + power management with frame-skip budgeting.

    update() always runs (game logic, timing accumulators).
    render+show is skipped when the frame budget is exhausted,
    keeping input and audio responsive under heavy graphics load.
    """
    print("primary_task started, debug_input={}".format(settings.get("debug_input")))
    frame = 0
    errors = 0
    ticks_ms = time.ticks_ms
    ticks_diff = time.ticks_diff
    prev_render_ms = 0
    tft = manager.tft
    _dma = getattr(tft, "_native", False)
    # vsync=True (default): skip frame if DMA busy (tear-free)
    # vsync=False: draw over buffer during DMA (may tear, higher FPS)
    _vsync = settings.get("vsync", True) if _dma else False

    # Frame timing instrumentation
    _perf = settings.get("debug_perf", False)
    _perf_renders = 0
    _perf_skips = 0
    _perf_render_ms = 0
    _perf_total_ms = 0
    _perf_t0 = ticks_ms()
    _PERF_INTERVAL = const(60)  # print every 60 frames

    while True:
        t0 = ticks_ms()

        # ── Input + game logic (always runs) ──────────────────
        try:
            needs_render = manager.consume_and_update()
        except KeyboardInterrupt:
            raise
        except Exception as e:
            needs_render = False
            errors += 1
            if errors <= 3:
                import sys

                sys.print_exception(e)
            else:
                print("primary_task update error #{}: {}".format(errors, e))

        # ── Graphics — DMA-aware or predictive budget ─────────
        if _dma:
            # DMA mode: skip render if previous push still in flight (vsync)
            can_render = needs_render and (not _vsync or not tft.busy())
        else:
            # Blocking mode: predictive budget from previous frame cost
            elapsed = ticks_diff(ticks_ms(), t0)
            predicted = elapsed + prev_render_ms
            can_render = needs_render and predicted < _FRAME_BUDGET_MS

        if can_render:
            try:
                t_render = ticks_ms()
                manager.render_and_show()
                prev_render_ms = ticks_diff(ticks_ms(), t_render)
                if _perf:
                    _perf_renders += 1
                    _perf_render_ms += prev_render_ms
            except KeyboardInterrupt:
                raise
            except Exception as e:
                prev_render_ms = 0
                errors += 1
                if errors <= 3:
                    import sys

                    sys.print_exception(e)
                else:
                    print("primary_task render error #{}: {}".format(errors, e))
        elif needs_render:
            manager.skip_render()
            prev_render_ms = 0  # reset predictor after a skip
            if _perf:
                _perf_skips += 1

        # ── Power management ──────────────────────────────────
        if inp.has_activity():
            idle_tracker.poke()

        try:
            # Master switch OFF → sleep until flipped back ON
            if power_mgr.master_switch_off():
                power_mgr.sleep_until_master_on()
                idle_tracker.wake()
                inp.resync_encoders()
                manager.invalidate()
            # Menu standby request
            elif settings.get("_sleep_now"):
                settings["_sleep_now"] = False
                power_mgr.sleep_and_wake()
                idle_tracker.wake()
                inp.resync_encoders()
                manager.invalidate()
            # Idle timeout
            elif idle_tracker.tick():
                power_mgr.sleep_and_wake()
                idle_tracker.wake()
                inp.resync_encoders()
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
            n_enc = len(encoders)
            enc_vals = " ".join("{}".format(inp.enc_pos[i]) for i in range(n_enc))
            enc_raw = " ".join(
                "C{}D{}S{}".format(
                    encoders[i].clk.value(),
                    encoders[i].dt.value(),
                    encoders[i].sw.value(),
                )
                for i in range(n_enc)
            )
            print(
                "INP btn[{}] sw[{}] enc[{}] raw[{}]".format(
                    btns, sws, enc_vals, enc_raw
                )
            )

        # ── Perf stats ───────────────────────────────────────
        if _perf and frame > 0 and frame % _PERF_INTERVAL == 0:
            dt = ticks_diff(ticks_ms(), _perf_t0)
            fps = _perf_renders * 1000 // dt if dt > 0 else 0
            avg_render = _perf_render_ms // _perf_renders if _perf_renders > 0 else 0
            busy_now = tft.busy() if _dma else False
            print(
                "PERF fps={} renders={} skips={} avg_render={}ms busy={} dt={}ms".format(
                    fps, _perf_renders, _perf_skips, avg_render, busy_now, dt
                )
            )
            _perf_renders = 0
            _perf_skips = 0
            _perf_render_ms = 0
            _perf_t0 = ticks_ms()

        frame += 1
        await asyncio.sleep_ms(2)


async def secondary_task(secondary):
    """Secondary display tick.

    DMA mode: 50 ms (20 fps) — SPI no longer blocks Python.
    Blocking mode: 200 ms (5 fps) — conservative to avoid stalls.
    Per-zone dirty tracking keeps redraws cheap when idle.
    """
    _dma = getattr(secondary.tft, "_native", False)
    _interval = 50 if _dma else 200
    errors = 0
    while True:
        try:
            secondary.tick()
        except KeyboardInterrupt:
            raise
        except Exception as e:
            errors += 1
            print("secondary_task error #{}: {}".format(errors, e))
        await asyncio.sleep_ms(_interval)


async def housekeeping_task(session_mgr, settings, audio=None, pwm=None):
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

        # Temperature overwatch — SoC sensor is always available; DS18B20 cached 30 s
        try:
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
                neo.set_override(neo.OVERRIDE_BLACK)
                try:
                    from machine import deepsleep

                    if pwm:
                        pwm.set_duty(config.PWM_CH_BACKLIGHT, 0)
                    # Deep sleep for 5 minutes, then wake to re-check
                    deepsleep(300_000)
                except Exception:
                    pass

            elif temp_status == "critical" and _prev_temp != "critical":
                print(
                    "TEMP CRITICAL ({}C >= {}C): "
                    "killing NeoPixels, dimming backlight".format(
                        int(t_max), config.TEMP_CRIT_C
                    )
                )
                # Kill NeoPixels — biggest heat contributor
                neo.set_override(neo.OVERRIDE_BLACK)
                # Dim display backlight to minimum
                if pwm:
                    try:
                        pwm.set_duty(config.PWM_CH_BACKLIGHT, 0)
                    except Exception:
                        pass

            elif temp_status == "warn" and _prev_temp == "ok":
                print(
                    "TEMP WARNING ({}C >= {}C): reducing NeoPixel brightness".format(
                        int(t_max), config.TEMP_WARN_C
                    )
                )

            elif temp_status == "ok" and _prev_temp != "ok":
                print("TEMP OK ({}C): resumed normal operation".format(int(t_max)))
                # Restore backlight
                if pwm:
                    try:
                        pwm.set_duty(config.PWM_CH_BACKLIGHT, 4095)
                    except Exception:
                        pass

            # Shed NFC polling at critical+ temperatures
            try:
                from bodn import nfc as _nfc_mod

                _nfc_mod.set_thermal_shed(temp_status in ("critical", "emergency"))
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
                neo.set_override(neo.OVERRIDE_BLACK)
                try:
                    import machine as _machine

                    if pwm:
                        pwm.set_duty(config.PWM_CH_BACKLIGHT, 0)
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
                neo.set_override(neo.OVERRIDE_BLACK)

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

        # Sync audio volume from settings + health check
        if audio:
            if settings.get("audio_enabled", True):
                target = settings.get("volume", 30)
            else:
                target = 0
            if audio.volume != target:
                audio.volume = target

        await asyncio.sleep_ms(500)


async def nfc_scan_task(manager, mode_screens, session_mgr, audio):
    """Poll NFC reader cooperatively and route tags globally.

    Uses the PN532 two-phase API via ``NFCReader.scan_cooperative`` so a
    single scan cycle is broken into ~1 ms I2C transactions separated by
    short awaits.  This keeps the scan running across every screen —
    including latency-sensitive games — without blocking the asyncio
    loop for the full 50 ms detect window.

    Adaptive polling rate (picked each cycle from the active screen):
      * home screen                → ~3 Hz
      * screen opts in via nfc_modes → ~4 Hz
      * screen opts in via nfc_low_priority → ~2 Hz
      * otherwise                   → ~3 Hz
    """
    from bodn.nfc import NFCReader, parse_tag_data, is_scan_suspended, route_tag

    reader = NFCReader()
    prev_uid = None

    def _idle_delay_ms():
        active = manager.active
        if len(manager._stack) <= 1:
            return 150
        if active is None:
            return 300
        if getattr(active, "nfc_low_priority", False):
            return 500
        if active.nfc_modes:
            return 250
        return 300

    def _mark_unavailable():
        reader._available = False
        reader._pn532 = None
        from bodn import nfc as _nfc_mod

        _nfc_mod._pn532 = None

    while True:
        # Retry init if NFC hardware isn't available yet (e.g. after
        # sleep or soft reboot when PN532 needs time to come up).
        if not reader.available():
            await asyncio.sleep_ms(2000)
            continue

        # Provisioning screens hold the bus for a blocking write — skip
        # one tick rather than race them.
        if is_scan_suspended():
            prev_uid = None
            await asyncio.sleep_ms(200)
            continue

        try:
            uid, data = await reader.scan_cooperative()
        except OSError as e:
            print("NFC: I2C error during scan:", e)
            _mark_unavailable()
            await asyncio.sleep_ms(2000)
            continue
        except Exception as e:
            print("NFC: scan error:", e)
            _mark_unavailable()
            await asyncio.sleep_ms(2000)
            continue

        # Re-read active after the awaits — user may have navigated.
        active = manager.active

        if uid and data and uid != prev_uid:
            parsed = parse_tag_data(data)
            if parsed:
                active_modes = active.nfc_modes if active else frozenset()
                try_consume, mode = route_tag(parsed, active_modes)

                consumed = False
                if try_consume and active:
                    consumed = active.on_nfc_tag(parsed)

                # Mode switch: launch the game if not consumed
                if not consumed and mode in mode_screens:
                    factory = mode_screens[mode]
                    try:
                        screen = factory()
                        if mode != "settings":
                            session_mgr.try_wake(mode)
                        if audio:
                            audio.play_sound("select")
                        # From home (depth 1): push.  In-game (depth 2+): replace.
                        if len(manager._stack) <= 1:
                            manager.push(screen)
                        else:
                            manager.replace(screen)
                    except Exception as e:
                        print("NFC launch error:", e)

        if uid is None:
            prev_uid = None
        else:
            prev_uid = uid

        await asyncio.sleep_ms(_idle_delay_ms())


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

    # Create IdleTracker up front and expose it via settings so HTTP and FTP
    # servers can poke it on activity — prevents lightsleep during an active
    # sync (otherwise a multi-minute upload trips the idle timeout).
    idle_tracker = IdleTracker(
        timeout_s=settings.get("sleep_timeout_s", config.SLEEP_TIMEOUT_S),
        time_fn=time.time,
    )
    settings["_idle_tracker"] = idle_tracker

    _server = None
    try:
        _server = await start_server(session_mgr, settings)
        print("Web server running on port 80")
    except Exception as e:
        print("Web server failed to start:", e)

    try:
        await start_ftp(settings)
    except Exception as e:
        print("FTP server failed to start:", e)

    (
        tft,
        tft2,
        buttons,
        switches,
        encoders,
        mcp,
        mcp2,
        pwm,
        arcade,
        audio,
        hw_status,
    ) = create_hardware()

    # Publish hardware status for diagnostics
    from bodn.diag import set_hw_status

    set_hw_status(hw_status)

    # Update boot log with hardware initialisation results
    try:
        import json as _json

        try:
            with open("/data/boot_log.json") as _f:
                _boot_log = _json.load(_f)
        except Exception:
            _boot_log = {}
        _boot_log["i2c"] = hw_status.get("i2c", [])
        _boot_log["hw"] = {k: v for k, v in hw_status.items() if k != "i2c"}
        with open("/data/boot_log.json", "w") as _f:
            _json.dump(_boot_log, _f)
        del _boot_log, _json
    except Exception as _e:
        print("boot log hw update:", _e)

    # Expose PCA9685 PWM driver so BrightnessControl can dim the backlight
    settings["_pwm"] = pwm

    manager, secondary, inp, mode_screens = create_ui(
        session_mgr,
        settings,
        wifi_ctrl,
        tft,
        tft2,
        buttons,
        switches,
        encoders,
        arcade=arcade,
        audio=audio,
    )

    # Sync audio settings
    if audio:
        audio.volume = settings.get("volume", 30)
        if not settings.get("audio_enabled", True):
            audio.volume = 0

    # Power management (idle_tracker already constructed above so network
    # servers can see it — just create the hardware-side PowerManager here).
    power_mgr = PowerManager(tft, tft2, mcp, pwm=pwm)

    # Startup sound disabled — re-enable when tuned:
    # if audio and settings.get("audio_enabled", True):
    #     if not session_mgr._in_quiet_hours():
    #         audio.play_sound("start")

    tasks = [
        input_scan_task(mcp, mcp2, inp, switches),
        primary_task(
            manager,
            settings,
            inp,
            encoders,
            mcp,
            mcp2,
            idle_tracker,
            power_mgr,
        ),
        secondary_task(secondary),
        housekeeping_task(session_mgr, settings, audio=audio, pwm=pwm),
    ]
    if audio:
        tasks.append(audio.start())
    # Always start NFC task — it retries init if hardware wasn't ready at boot
    tasks.append(nfc_scan_task(manager, mode_screens, session_mgr, audio))
    await asyncio.gather(*tasks)


try:
    _skip = _skip_main  # set by boot.py if /skip_main flag file existed
except NameError:
    _skip = False

if not _skip:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Make the next boot fast + drop to REPL so mpremote (which does
        # a Ctrl-D soft reset with a 10 s deadline) can enter raw REPL
        # reliably. Mirror of boot.py's _abort_boot() behaviour.
        try:
            open("/skip_main", "w").close()
            open("/fast_boot", "w").close()
        except OSError:
            pass
        print("Bodn stopped — next boot fast.")
    except Exception as e:
        import sys

        print("FATAL:", e)
        sys.print_exception(e)
    finally:
        # Put PN532 into clean power-down (I2C wake) so it recovers
        # after soft reboot without needing a hardware reset pin.
        try:
            from bodn import nfc as _nfc_cleanup

            if _nfc_cleanup._pn532:
                _nfc_cleanup._pn532.power_down()
        except Exception:
            pass
else:
    print("main.py: skipped — REPL active. Reset to boot normally.")
