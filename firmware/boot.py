# boot.py — runs before main.py
# WiFi setup, NTP sync, load settings — with animated boot screen.

import time

settings = None
ip = "0.0.0.0"
ntp_ok = False

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
        Pin(config.NEOPIXEL_PIN, Pin.OUT), config.NEOPIXEL_COUNT, timing=1,
    )
except Exception as e:
    print("Boot display init error:", e)


# --- Colours ---
_rgb = ST7735.rgb if tft else lambda r, g, b: 0
COL_TITLE = _rgb(233, 69, 96)
COL_WHITE = _rgb(255, 255, 255)
COL_GREEN = _rgb(39, 174, 96)
COL_AMBER = _rgb(255, 191, 0)
COL_CYAN = _rgb(0, 255, 255)
COL_BAR_BG = _rgb(40, 40, 40)
COL_BLACK = 0

# Progress bar geometry — derived from display size
_w = config.TFT_WIDTH if tft else 128
_h = config.TFT_HEIGHT if tft else 160
BAR_W = _w * 3 // 4
BAR_X = (_w - BAR_W) // 2
BAR_Y = _h * 5 // 8
BAR_H = max(10, _h // 16)
N_LEDS = config.NEOPIXEL_COUNT if tft else 0

# Boot steps: (message, LED colour as RGB tuple)
STEPS = [
    ("Waking up...", (80, 40, 120)),
    ("Finding friends...", (0, 120, 200)),
    ("What time is it?", (200, 120, 0)),
    ("Let's go!", (0, 200, 80)),
]


def _show_progress(step, total, message, led_rgb, detail=None, detail_col=None):
    """Draw boot screen with progress bar and light LEDs."""
    if not tft:
        return

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

    # Step dots below the bar
    dot_y = BAR_Y + BAR_H + h // 20
    dot_spacing = max(12, w // 16)
    dot_x0 = (w - total * dot_spacing) // 2 + dot_spacing // 4
    dot_size = max(6, dot_spacing // 2)
    for i in range(total):
        dx = dot_x0 + i * dot_spacing
        if i < step:
            tft.fill_rect(dx, dot_y, dot_size, dot_size, COL_GREEN)
        elif i == step:
            tft.fill_rect(dx, dot_y, dot_size, dot_size, COL_CYAN)
        else:
            tft.rect(dx, dot_y, dot_size, dot_size, COL_BAR_BG)

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


# --- Step 1: Load settings ---
_show_progress(0, len(STEPS), STEPS[0][0], STEPS[0][1])

try:
    from bodn.storage import load_settings
    settings = load_settings()
except Exception as e:
    print("Settings load failed:", e)

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

_show_progress(1, len(STEPS), STEPS[0][0], STEPS[0][1])

# --- Step 2: Connect WiFi ---
_show_progress(1, len(STEPS), STEPS[1][0], STEPS[1][1])

try:
    from bodn.wifi import connect
    ip = connect(settings)
    print("Bodn IP:", ip)
except Exception as e:
    print("WiFi failed:", e)

_show_progress(2, len(STEPS), STEPS[1][0], STEPS[1][1],
               detail="IP: " + ip, detail_col=COL_WHITE)
time.sleep(0.5)

# --- Step 3: NTP sync ---
_show_progress(2, len(STEPS), STEPS[2][0], STEPS[2][1])

try:
    import ntptime
    ntptime.settime()
    ntp_ok = True
    print("NTP synced")
except Exception as e:
    print("NTP failed:", e)
    settings["quiet_start"] = None
    settings["quiet_end"] = None

ntp_detail = "NTP OK" if ntp_ok else "NTP fail"
ntp_col = COL_GREEN if ntp_ok else COL_AMBER
_show_progress(3, len(STEPS), STEPS[2][0], STEPS[2][1],
               detail=ntp_detail, detail_col=ntp_col)
time.sleep(0.5)

# --- Step 4: Ready! ---
_show_progress(4, len(STEPS), STEPS[3][0], STEPS[3][1],
               detail="IP: " + ip, detail_col=COL_WHITE)

# Clear LEDs before main.py takes over
if np:
    for i in range(N_LEDS):
        np[i] = (0, 0, 0)
    np.write()
