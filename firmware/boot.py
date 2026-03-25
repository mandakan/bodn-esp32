# boot.py — runs before main.py
# WiFi setup, NTP sync, load settings — with animated boot screen.
# Each step shows a status dot: green=ok, amber=skipped, red=failed.
# Hold NAV encoder button (ENC1_SW) during power-on for diagnostic screen.

import gc
import time

# Keep amplifier in shutdown immediately — before anything else can make noise.
# PCA9685 PWM glitches during power-on, so amp SD uses a direct GPIO.
from machine import Pin

Pin(3, Pin.OUT, value=0)  # config.AMP_SD_PIN — LOW = shutdown

# Safe-boot window: pause briefly so Ctrl-C can interrupt before heavy init.
# Also lets the ESP32 task watchdog breathe between reset cycles.
print("boot.py: 1s safe-boot window (Ctrl-C to abort)...")
time.sleep(1)

settings = None
ip = "0.0.0.0"

# --- Init display + LEDs early so we can show progress ---
tft = None
np = None
_diag_requested = False
try:
    from machine import Pin, SPI
    import neopixel
    from bodn import config
    from st7735 import ST7735

    # Check NAV encoder button (active-low with pull-up) for diagnostic mode
    _diag_btn = Pin(config.ENC1_SW, Pin.IN, Pin.PULL_UP)
    _diag_requested = _diag_btn.value() == 0
    _diag_btn = None  # release pin — encoder driver will reclaim it

    spi = SPI(
        1,
        baudrate=26_000_000,
        sck=Pin(config.TFT_SCK),
        mosi=Pin(config.TFT_MOSI),
    )
    tft = ST7735(
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
    np = neopixel.NeoPixel(
        Pin(config.NEOPIXEL_PIN, Pin.OUT),
        config.NEOPIXEL_COUNT,
        timing=1,
    )
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
N_LEDS = config.NEOPIXEL_COUNT if tft else 0

# Boot steps: (label, message_key, LED colour)
# message_key is used with i18n.t() after settings are loaded;
# before that, the raw key is shown (acceptable for a brief moment).
STEPS = [
    ("CFG", "boot_cfg", (80, 40, 120)),
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
    except Exception:
        return key


# Load extended font glyphs for Swedish characters (å ä ö etc.)
try:
    from bodn.ui.font_ext import GLYPHS as _EXT_GLYPHS
except ImportError:
    _EXT_GLYPHS = {}

# Load pixel art logo
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
    if _draw_logo:
        logo_scale = 3 if w >= 240 else 2
        logo_w = 16 * logo_scale
        logo_h = 16 * logo_scale
        # Center logo + name as a unit
        title = "Bodn"
        title_w = len(title) * 8
        block_h = logo_h + 4 + 8  # logo + gap + text height
        ly = max(2, (h * 3 // 8 - block_h) // 2)
        lx = (w - logo_w) // 2
        _draw_logo(tft, lx, ly, _LOGO_COLORS, scale=logo_scale)
        tx = (w - title_w) // 2
        _boot_text(tft, title, tx, ly + logo_h + 4, COL_TITLE)
    else:
        title = "~ Bodn ~"
        tx = (w - len(title) * 8) // 2
        _boot_text(tft, title, tx, h // 8, COL_TITLE)

    # Whimsical message — centered
    msg_y = h * 3 // 8 + (12 if _draw_logo else 0)
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

    # Light LEDs proportionally
    if np:
        lit = N_LEDS * step // total
        for i in range(N_LEDS):
            if i < lit:
                np[i] = tuple(c // 4 for c in led_rgb)
            else:
                np[i] = (0, 0, 0)
        np.write()


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
    except Exception:
        pass
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
_show_progress(1, STEPS[0][1], STEPS[0][2])

# --- Step 1: Connect WiFi ---
_show_progress(1, STEPS[1][1], STEPS[1][2])

try:
    from bodn.wifi import connect

    ip = connect(settings)
    _results[1] = "ok"
except Exception as e:
    print("WiFi failed:", e)
    _results[1] = "fail"

print("BOOT [NET]", _results[1], "ip=" + ip)

_show_progress(2, STEPS[1][1], STEPS[1][2], detail="IP: " + ip, detail_col=COL_WHITE)
time.sleep(0.5)

# --- Step 2: NTP sync ---
_show_progress(2, STEPS[2][1], STEPS[2][2])

try:
    import ntptime

    ntptime.settime()
    _results[2] = "ok"
except Exception:
    _results[2] = "warn"
    settings["quiet_start"] = None
    settings["quiet_end"] = None

print("BOOT [NTP]", _results[2])
ntp_detail = "NTP OK" if _results[2] == "ok" else "NTP skip"
ntp_col = COL_GREEN if _results[2] == "ok" else COL_AMBER
_show_progress(3, STEPS[2][1], STEPS[2][2], detail=ntp_detail, detail_col=ntp_col)
time.sleep(0.5)

# --- Step 3: Battery check ---
_show_progress(3, STEPS[3][1], STEPS[3][2])

try:
    from machine import ADC

    _bat_adc = ADC(Pin(config.BAT_SENS_PIN))
    _bat_adc.atten(ADC.ATTN_11DB)
    _bat_adc.width(ADC.WIDTH_12BIT)
    _bat_mv = _bat_adc.read_uv() // 1000 * 2  # voltage divider ×2
    _bat_adc = None
    if _bat_mv > 3000:
        _results[3] = "ok"
        _bat_detail = "{}mV".format(_bat_mv)
        _bat_col = COL_GREEN
    elif _bat_mv > 0:
        _results[3] = "warn"
        _bat_detail = "LOW {}mV".format(_bat_mv)
        _bat_col = COL_AMBER
    else:
        # No battery — USB powered
        _results[3] = "ok"
        _bat_detail = "USB"
        _bat_col = COL_GREEN
except Exception as e:
    print("Battery check failed:", e)
    _results[3] = "skip"
    _bat_detail = "N/A"
    _bat_col = COL_AMBER

print("BOOT [BAT]", _results[3], _bat_detail)
_show_progress(4, STEPS[3][1], STEPS[3][2], detail=_bat_detail, detail_col=_bat_col)
time.sleep(0.5)

# --- Step 4: Ready! ---
_results[4] = "ok"
_show_progress(5, STEPS[4][1], STEPS[4][2], detail="IP: " + ip, detail_col=COL_WHITE)

# --- Diagnostic boot screen (hold NAV encoder button to activate) ---
if _diag_requested and tft:
    from bodn.diag import gather as _diag_gather

    _diag_info = _diag_gather(ip=ip, boot_results=_results, boot_steps=STEPS)

    # --- Draw diagnostic screen ---
    tft.fill(COL_BLACK)
    _line_h = 14
    _y = 4
    _title = "~ Diagnostics ~"
    _tx = (tft.width - len(_title) * 8) // 2
    tft.text(_title, _tx, _y, COL_TITLE)
    _y += _line_h + 4

    for _label, _val in _diag_info:
        tft.text(_label, 4, _y, COL_AMBER)
        _vx = min(80, (len(_label) + 1) * 8 + 4)
        tft.text(str(_val), _vx, _y, COL_WHITE)
        _y += _line_h

    # Hint at bottom
    _hint = "Press any button"
    _hx = (tft.width - len(_hint) * 8) // 2
    tft.text(_hint, _hx, tft.height - 16, COL_CYAN)
    tft.show()

    # Wait for any encoder button press (MCP23017 not available yet)
    _enc_btns = [
        Pin(config.ENC1_SW, Pin.IN, Pin.PULL_UP),
        Pin(config.ENC2_SW, Pin.IN, Pin.PULL_UP),
    ]
    # First wait for the held button to be released
    while _enc_btns[0].value() == 0:
        time.sleep_ms(50)
    # Then wait for any encoder button press to dismiss
    while all(b.value() == 1 for b in _enc_btns):
        time.sleep_ms(50)
    _enc_btns = None

    print("BOOT [DIAG] screen shown")

# Free boot screen objects before main.py starts — the 240×320
# framebuffer alone is ~150 KB of RAM.
tft = None
spi = None
np = None
gc.collect()
print("BOOT done, free={}".format(gc.mem_free()))
