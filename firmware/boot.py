# boot.py — runs before main.py
# WiFi setup, NTP sync, load settings — with animated boot screen.
# Each step shows a status dot: green=ok, amber=skipped, red=failed.

import gc
import time

settings = None
ip = "0.0.0.0"

# --- Init display + LEDs early so we can show progress ---
tft = None
np = None
try:
    from machine import Pin, SPI
    import neopixel
    from bodn import config
    from st7735 import ST7735

    spi = SPI(
        2,
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

# Boot steps: (label, message, LED colour)
STEPS = [
    ("CFG", "Waking up...", (80, 40, 120)),
    ("NET", "Finding friends...", (0, 120, 200)),
    ("NTP", "What time is it?", (200, 120, 0)),
    ("GO!", "Let's go!", (0, 200, 80)),
]

# Per-step result: None=pending, "ok", "warn", "fail", "skip"
_results = [None] * len(STEPS)


def _show_progress(step, message, led_rgb, detail=None, detail_col=None):
    """Draw boot screen with progress bar and status dots."""
    if not tft:
        return

    total = len(STEPS)
    tft.fill(COL_BLACK)

    w = tft.width
    h = tft.height

    # Title — centered
    title = "~ Bodn ~"
    tx = (w - len(title) * 8) // 2
    tft.text(title, tx, h // 8, COL_TITLE)

    # Whimsical message — centered
    mx = max(0, (w - len(message) * 8) // 2)
    tft.text(message, mx, h * 3 // 8, COL_WHITE)

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

# --- Step 3: Ready! ---
_results[3] = "ok"
_show_progress(4, STEPS[3][1], STEPS[3][2], detail="IP: " + ip, detail_col=COL_WHITE)

# Free boot screen objects before main.py starts — the 240×320
# framebuffer alone is ~150 KB of RAM.
tft = None
spi = None
np = None
gc.collect()
print("BOOT done, free={}".format(gc.mem_free()))
