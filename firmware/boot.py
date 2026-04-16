# boot.py — runs before main.py
# WiFi setup, NTP sync, load settings — with animated boot screen.
# Each step shows a status dot: green=ok, amber=skipped, red=failed.
# Hold NAV encoder button (ENC1_SW) during power-on for diagnostic screen.

import gc
import sys as _sys
import time

# Keep amplifier in shutdown immediately — before anything else can make noise.
# PCA9685 PWM glitches during power-on, so amp SD uses a direct GPIO.
from machine import Pin

Pin(3, Pin.OUT, value=0)  # config.AMP_SD_PIN — LOW = shutdown

# Turn on display backlight via PCA9685 channel 0.
# The LED input is wired to PCA9685 CH0, not a direct GPIO.
# Use SoftI2C (bit-banged, no conflict with hardware I2C(0) in main.py)
# and raw register writes — no driver import needed at this stage.
try:
    from machine import SoftI2C

    _bi2c = SoftI2C(scl=Pin(47), sda=Pin(48), freq=400_000)
    _bi2c.writeto_mem(0x40, 0x00, b"\x20")  # MODE1: wake oscillator, auto-increment
    _bi2c.writeto_mem(0x40, 0x06, b"\x00\x10\x00\x00")  # CH0: ON_H full-on bit, OFF=0
    del _bi2c
except Exception as _e:
    print("boot: PCA9685 backlight init skipped:", _e)

# Safe-boot window: pause briefly so Ctrl-C can interrupt before heavy init.
# Also lets the ESP32 task watchdog breathe between reset cycles.
#
# To skip main.py and drop to REPL on next boot:
#   uv run mpremote connect auto fs touch :/skip_main
# The flag file is auto-deleted on boot so it only skips once.
import os as _os  # noqa: E402 — must run after time.sleep() boot window above

_skip_main = False
_fast_boot = False
try:
    _os.stat("/skip_main")
    _skip_main = True
    _os.remove("/skip_main")
    print("boot.py: /skip_main flag found — will drop to REPL after boot")
    print("  Tip: from bodn.i2c_diag import run; run()")
except OSError:
    pass

try:
    _os.stat("/fast_boot")
    _fast_boot = True
    _os.remove("/fast_boot")
    print("boot.py: /fast_boot flag found — skipping WiFi/NTP for quick sync")
except OSError:
    pass


def _abort_boot():
    """Ctrl-C during boot — exit immediately so REPL is available for mpremote."""
    print("boot.py: interrupted — dropping to REPL")
    _sys.exit()


if not _fast_boot:
    print("boot.py: 5s safe-boot window (Ctrl-C to abort)...")
    try:
        time.sleep(5)
    except KeyboardInterrupt:
        _abort_boot()

settings = None
ip = "0.0.0.0"

# --- Init display early so we can show progress ---
tft = None
try:
    from machine import Pin
    from bodn import config
    from st7735 import ST7735
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
    tft = ST7735(
        0,
        rst=Pin(config.TFT_RST, Pin.OUT),
        width=config.TFT_WIDTH,
        height=config.TFT_HEIGHT,
        col_offset=config.TFT_COL_OFFSET,
        row_offset=config.TFT_ROW_OFFSET,
        madctl=config.TFT_MADCTL,
    )
except KeyboardInterrupt:
    _abort_boot()
except Exception as e:
    print("Boot display init error:", e)


# --- Colours ---
_rgb = ST7735.rgb if tft else lambda r, g, b: 0
COL_TITLE = _rgb(233, 69, 96)
COL_WHITE = _rgb(255, 255, 255)
COL_GREEN = _rgb(39, 174, 96)
COL_RED = _rgb(231, 76, 60)
COL_AMBER = _rgb(255, 191, 0)
COL_CYAN = _rgb(0, 255, 255)
COL_BAR_BG = _rgb(40, 40, 40)
COL_BLACK = 0

# Status colours for step dots
_STATUS_COL = {
    "ok": COL_GREEN,
    "warn": COL_AMBER,
    "fail": COL_RED,
    "skip": COL_BAR_BG,
}

# Progress bar geometry — derived from display size
_w = config.TFT_WIDTH if tft else 128
_h = config.TFT_HEIGHT if tft else 160
BAR_W = _w * 3 // 4
BAR_X = (_w - BAR_W) // 2
BAR_Y = _h * 5 // 8
BAR_H = max(10, _h // 16)

# Boot steps: (label, message_key, LED colour)
# message_key is used with i18n.t() after settings are loaded;
# before that, the raw key is shown (acceptable for a brief moment).
STEPS = [
    ("CFG", "boot_cfg", (80, 40, 120)),
    ("SD", "boot_sd", (180, 120, 40)),
    ("NET", "boot_net", (0, 120, 200)),
    ("NTP", "boot_ntp", (200, 120, 0)),
    ("BAT", "boot_bat", (200, 60, 0)),
    ("GO!", "boot_go", (0, 200, 80)),
]

# Per-step result: None=pending, "ok", "warn", "fail", "skip"
_results = [None] * len(STEPS)


def _translate(key):
    """Try to translate a boot message key; return key itself if i18n not ready."""
    try:
        from bodn.i18n import t

        return t(key)
    except KeyboardInterrupt:
        _abort_boot()
    except Exception:
        return key


# Load extended font glyphs for Swedish characters (å ä ö etc.)
try:
    from bodn.ui.font_ext import GLYPHS as _EXT_GLYPHS
except ImportError:
    _EXT_GLYPHS = {}

# Load pixel art logo (fallback)
try:
    from bodn.ui.logo import draw_logo as _draw_logo

    _LOGO_COLORS = {
        "body": _rgb(200, 150, 50),  # warm amber
        "mead": COL_TITLE,  # crimson red
        "rim": _rgb(255, 220, 100),  # bright gold
        "sparkle": COL_CYAN,  # magic sparkles
    }
except ImportError:
    _draw_logo = None
    _LOGO_COLORS = {}

# Native _draw module for sprite logos (loaded after SD mount)
_logo_sprite = None  # large logo for boot splash
_logo_sprite_w = 0
_logo_sprite_h = 0
_logo_sm_sprite = None  # small logo for progress screen (replaces pixel-art)
_logo_sm_w = 0
_logo_sm_h = 0
_logo_s2_sprite = None  # secondary display logo
_logo_s2_w = 0
_logo_s2_h = 0
try:
    import _draw as _draw_mod
except ImportError:
    _draw_mod = None


def _boot_text(tft, text, x, y, color):
    """Draw text with extended glyph support (boot screen version).

    Like widgets.draw_label() but standalone — no widget imports needed.
    """
    cx = x
    ascii_start = cx
    ascii_buf = []
    for ch in text:
        glyph = _EXT_GLYPHS.get(ch)
        if glyph:
            if ascii_buf:
                tft.text("".join(ascii_buf), ascii_start, y, color)
                ascii_buf = []
            for row in range(8):
                byte = glyph[row]
                if byte == 0:
                    continue
                for col in range(8):
                    if byte & (0x80 >> col):
                        tft.pixel(cx + col, y + row, color)
            cx += 8
            ascii_start = cx
        else:
            ascii_buf.append(ch)
            cx += 8
    if ascii_buf:
        tft.text("".join(ascii_buf), ascii_start, y, color)


def _show_progress(step, message_key, led_rgb, detail=None, detail_col=None):
    """Draw boot screen with progress bar and status dots."""
    if not tft:
        return
    message = _translate(message_key)

    total = len(STEPS)
    tft.fill(COL_BLACK)

    w = tft.width
    h = tft.height

    # Logo or title — centered at top
    # Prefer the small sprite (48px), fall back to pixel-art, then text-only
    _active_logo = _logo_sm_sprite
    _active_w = _logo_sm_w
    _active_h = _logo_sm_h
    if _active_logo is not None:
        logo_w = _active_w
        logo_h = _active_h
        title = "Böðn"
        title_w = len(title) * 8
        block_h = logo_h + 4 + 8
        ly = max(2, (h * 3 // 8 - block_h) // 2)
        lx = (w - logo_w) // 2
        _draw_mod.sprite(tft._buf, tft.width, lx, ly, _active_logo, 0, COL_WHITE)
        tft.mark_dirty(lx, ly, logo_w, logo_h)
        tx = (w - title_w) // 2
        _boot_text(tft, title, tx, ly + logo_h + 4, COL_TITLE)
    elif _draw_logo:
        # Pixel-art fallback logo
        logo_scale = 3 if w >= 240 else 2
        logo_w = 16 * logo_scale
        logo_h = 16 * logo_scale
        title = "Böðn"
        title_w = len(title) * 8
        block_h = logo_h + 4 + 8  # logo + gap + text height
        ly = max(2, (h * 3 // 8 - block_h) // 2)
        lx = (w - logo_w) // 2
        _draw_logo(tft, lx, ly, _LOGO_COLORS, scale=logo_scale)
        tx = (w - title_w) // 2
        _boot_text(tft, title, tx, ly + logo_h + 4, COL_TITLE)
    else:
        title = "~ Böðn ~"
        tx = (w - len(title) * 8) // 2
        _boot_text(tft, title, tx, h // 8, COL_TITLE)

    # Whimsical message — centered
    has_logo = _logo_sprite is not None or _draw_logo is not None
    msg_y = h * 3 // 8 + (12 if has_logo else 0)
    mx = max(0, (w - len(message) * 8) // 2)
    _boot_text(tft, message, mx, msg_y, COL_WHITE)

    # Progress bar
    tft.fill_rect(BAR_X, BAR_Y, BAR_W, BAR_H, COL_BAR_BG)
    fill_w = BAR_W * step // total
    if fill_w > 0:
        tft.fill_rect(BAR_X, BAR_Y, fill_w, BAR_H, COL_CYAN)
    tft.rect(BAR_X, BAR_Y, BAR_W, BAR_H, COL_WHITE)

    # Status dots below the bar — colour shows result per step
    dot_y = BAR_Y + BAR_H + h // 20
    dot_spacing = max(16, w // 12)
    dot_x0 = (w - total * dot_spacing) // 2 + dot_spacing // 4
    dot_size = max(6, dot_spacing // 3)
    label_y = dot_y + dot_size + 3

    for i in range(total):
        dx = dot_x0 + i * dot_spacing
        label = STEPS[i][0]
        result = _results[i]

        if result is not None:
            # Completed — fill with status colour
            col = _STATUS_COL.get(result, COL_GREEN)
            tft.fill_rect(dx, dot_y, dot_size, dot_size, col)
        elif i == step:
            # Currently running — cyan filled
            tft.fill_rect(dx, dot_y, dot_size, dot_size, COL_CYAN)
        else:
            # Pending — outline only
            tft.rect(dx, dot_y, dot_size, dot_size, COL_BAR_BG)

        # Step label below dot
        lx = dx + (dot_size - len(label) * 8) // 2
        label_col = COL_WHITE if i <= step else COL_BAR_BG
        tft.text(label, lx, label_y, label_col)

    # Optional detail line
    if detail:
        dx = max(0, (w - len(detail) * 8) // 2)
        tft.text(detail, dx, h * 7 // 8, detail_col or COL_WHITE)

    tft.show()


# --- Step 0: Load settings ---
_show_progress(0, STEPS[0][1], STEPS[0][2])

try:
    from bodn.storage import load_settings

    settings = load_settings()
    _results[0] = "ok"
    # Init i18n early so boot messages can be translated
    try:
        from bodn.i18n import init as _i18n_init

        _i18n_init(settings.get("language", "sv"))
    except KeyboardInterrupt:
        _abort_boot()
    except Exception:
        pass
except KeyboardInterrupt:
    _abort_boot()
except Exception as e:
    print("Settings load failed:", e)
    _results[0] = "fail"

if settings is None:
    settings = {
        "max_session_min": 20,
        "max_sessions_day": 5,
        "break_min": 15,
        "lockdown": False,
        "quiet_start": None,
        "quiet_end": None,
        "wifi_ssid": "",
        "wifi_pass": "",
        "wifi_mode": "ap",
        "ui_pin": "",
        "ota_token": "",
    }
    if _results[0] != "fail":
        _results[0] = "warn"  # defaults used

print("BOOT [CFG]", _results[0])

# --- Step 1: SD card mount ---
_show_progress(1, STEPS[1][1], STEPS[1][2])

try:
    from bodn.sdcard import mount as _sd_mount

    if _sd_mount():
        _results[1] = "ok"
    else:
        _results[1] = "skip"
except KeyboardInterrupt:
    _abort_boot()
except Exception as e:
    print("SD card mount skipped:", e)
    _results[1] = "skip"

print("BOOT [SD]", _results[1])

# Try to load logo sprites from SD (only if _draw C module available)
if _results[1] == "ok" and _draw_mod is not None:

    def _load_sprite(path):
        with open(path, "rb") as f:
            data = f.read()
        asset = _draw_mod.load(data)
        info = _draw_mod.info(asset)
        return asset, data, info["max_width"], info["height"]

    # Large boot splash logo
    try:
        _logo_sprite, _logo_data, _logo_sprite_w, _logo_sprite_h = _load_sprite(
            "/sd/sprites/lo-logo.bdf"
        )
    except KeyboardInterrupt:
        _abort_boot()
    except Exception as _e:
        print("BOOT logo:", _e)

    # Small logo for progress screen (replaces pixel-art)
    try:
        _logo_sm_sprite, _logo_sm_data, _logo_sm_w, _logo_sm_h = _load_sprite(
            "/sd/sprites/lo-logo-sm.bdf"
        )
    except KeyboardInterrupt:
        _abort_boot()
    except Exception as _e:
        print("BOOT logo-sm:", _e)

    # Secondary display logo
    try:
        _logo_s2_sprite, _logo_s2_data, _logo_s2_w, _logo_s2_h = _load_sprite(
            "/sd/sprites/lo-logo-s2.bdf"
        )
    except KeyboardInterrupt:
        _abort_boot()
    except Exception as _e:
        print("BOOT logo-s2:", _e)

_show_progress(2, STEPS[1][1], STEPS[1][2])

# --- Step 2: Connect WiFi ---
_show_progress(2, STEPS[2][1], STEPS[2][2])

if _fast_boot:
    _results[2] = "skip"
else:
    try:
        from bodn.wifi import connect

        ip = connect(settings)
        _results[2] = "ok"
    except KeyboardInterrupt:
        _abort_boot()
    except Exception as e:
        print("WiFi failed:", e)
        _results[2] = "fail"

print("BOOT [NET]", _results[2], "ip=" + ip)

_show_progress(3, STEPS[2][1], STEPS[2][2], detail="IP: " + ip, detail_col=COL_WHITE)
time.sleep(0.5)

# --- Step 3: NTP sync ---
_show_progress(3, STEPS[3][1], STEPS[3][2])


def _last_sunday_of(year, month):
    """Return day-of-month of last Sunday in the given month."""
    import time

    days_in_month = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if month == 2 and (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)):
        days_in_month[2] = 29
    last = days_in_month[month]
    t = time.mktime((year, month, last, 0, 0, 0, 0, 0))
    wd = time.localtime(t)[6]  # 0=Mon..6=Sun
    return last - (wd + 1) % 7


def _is_eu_dst(year, month, day, hour):
    """Return True if EU summer time (DST) is active for the given UTC time."""
    if month < 3 or month > 10:
        return False
    if 3 < month < 10:
        return True
    ds = _last_sunday_of(year, 3)
    de = _last_sunday_of(year, 10)
    if month == 3:
        return day > ds or (day == ds and hour >= 1)
    # month == 10: DST ends at 01:00 UTC on last Sunday
    return not (day > de or (day == de and hour >= 1))


if _fast_boot:
    _results[3] = "skip"
else:
    try:
        import ntptime
        import machine

        ntptime.settime()
        # Adjust RTC from UTC to local time (EU DST rules)
        import time as _t

        _utc = _t.localtime()
        _base = settings.get("tz_offset", 1)
        _dst = _is_eu_dst(_utc[0], _utc[1], _utc[2], _utc[3])
        _off = (_base + (1 if _dst else 0)) * 3600
        _local = _t.localtime(_t.mktime(_utc) + _off)
        machine.RTC().datetime(
            (
                _local[0],
                _local[1],
                _local[2],
                _local[6],
                _local[3],
                _local[4],
                _local[5],
                0,
            )
        )
        _results[3] = "ok"
    except KeyboardInterrupt:
        _abort_boot()
    except Exception:
        _results[3] = "warn"
        settings["quiet_start"] = None
        settings["quiet_end"] = None

print("BOOT [NTP]", _results[3])
ntp_detail = "NTP OK" if _results[3] == "ok" else "NTP skip"
ntp_col = COL_GREEN if _results[3] == "ok" else COL_AMBER
_show_progress(4, STEPS[3][1], STEPS[3][2], detail=ntp_detail, detail_col=ntp_col)
time.sleep(0.5)

# --- Step 4: Battery check ---
_show_progress(4, STEPS[4][1], STEPS[4][2])

try:
    from machine import ADC

    _bat_adc = ADC(Pin(config.BAT_SENS_PIN))
    _bat_adc.atten(ADC.ATTN_11DB)
    _bat_adc.width(ADC.WIDTH_12BIT)
    _bat_mv = _bat_adc.read_uv() // 1000 * 2  # voltage divider ×2
    _bat_adc = None
    if _bat_mv > 3000:
        _results[4] = "ok"
        _bat_detail = "{}mV".format(_bat_mv)
        _bat_col = COL_GREEN
    elif _bat_mv > 0:
        _results[4] = "warn"
        _bat_detail = "LOW {}mV".format(_bat_mv)
        _bat_col = COL_AMBER
    else:
        # No battery — USB powered
        _results[4] = "ok"
        _bat_detail = "USB"
        _bat_col = COL_GREEN
except KeyboardInterrupt:
    _abort_boot()
except Exception as e:
    print("Battery check failed:", e)
    _results[4] = "skip"
    _bat_detail = "N/A"
    _bat_col = COL_AMBER

print("BOOT [BAT]", _results[4], _bat_detail)
_show_progress(5, STEPS[4][1], STEPS[4][2], detail=_bat_detail, detail_col=_bat_col)
time.sleep(0.5)

# --- Step 5: Ready! ---
_results[5] = "ok"
_show_progress(6, STEPS[5][1], STEPS[5][2], detail="IP: " + ip, detail_col=COL_WHITE)

# Free the small logo immediately — progress screen is done
_logo_sm_sprite = None
_logo_sm_data = None  # noqa: F841

# --- Boot splash: show large logo while cleanup + main.py init run ---
if _logo_sprite is not None and tft:
    tft.fill(COL_BLACK)
    _lx = (tft.width - _logo_sprite_w) // 2
    _ly = (tft.height - _logo_sprite_h) // 2
    # White backing rect so the logo's dark parts are visible on black
    _pad = 6
    tft.fill_rect(
        _lx - _pad,
        _ly - _pad,
        _logo_sprite_w + _pad * 2,
        _logo_sprite_h + _pad * 2,
        COL_WHITE,
    )
    _draw_mod.sprite(tft._buf, tft.width, _lx, _ly, _logo_sprite, 0, COL_WHITE)
    tft.mark_dirty(
        _lx - _pad, _ly - _pad, _logo_sprite_w + _pad * 2, _logo_sprite_h + _pad * 2
    )
    tft.show()

# Free large logo — splash is done
_logo_sprite = None
_logo_data = None  # noqa: F841

# Free boot screen objects before main.py starts — the 240×320
# framebuffer alone is ~150 KB of RAM.
# Deinit the SPI bus so main.py can re-initialize it cleanly.
tft = None
_logo_s2_sprite = None
_logo_s2_data = None  # noqa: F841 — frees backing buffer
_draw_mod = None
try:
    _spidma.deinit()
except KeyboardInterrupt:
    _abort_boot()
except Exception:
    pass
gc.threshold(gc.mem_free() // 4)
gc.collect()
print("BOOT done, free={}".format(gc.mem_free()))

# --- Persist boot log for web UI inspection ---
try:
    import json as _json

    _boot_log = {
        "ts": time.time(),
        "steps": [
            {"key": STEPS[i][0], "result": _results[i] or "skip"}
            for i in range(len(STEPS))
        ],
        "ip": ip,
        "bat": _bat_detail,
        "free_kb": gc.mem_free() // 1024,
    }
    with open("/data/boot_log.json", "w") as _f:
        _json.dump(_boot_log, _f)
    del _json, _boot_log
except KeyboardInterrupt:
    _abort_boot()
except Exception as _e:
    print("boot log:", _e)
