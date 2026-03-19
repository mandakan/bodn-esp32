# boot.py — runs before main.py
# WiFi setup, NTP sync, load settings, show IP on display.

import time

settings = None
ip = "0.0.0.0"
ntp_ok = False

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

# Connect WiFi (non-fatal — box works without it, just no web UI)
try:
    from bodn.wifi import connect

    ip = connect(settings)
    print("Bodn IP:", ip)
except Exception as e:
    print("WiFi failed:", e)

# NTP sync (best-effort — quiet hours disabled if it fails)
try:
    import ntptime

    ntptime.settime()
    ntp_ok = True
    print("NTP synced")
except Exception as e:
    print("NTP failed:", e)
    settings["quiet_start"] = None
    settings["quiet_end"] = None

# Brief IP display on TFT
try:
    from machine import Pin, SPI
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
    tft.fill(0)
    tft.text("Bodn", 48, 40, ST7735.rgb(233, 69, 96))
    tft.text("IP: " + ip, 8, 70, ST7735.rgb(255, 255, 255))
    if ntp_ok:
        tft.text("NTP OK", 40, 90, ST7735.rgb(39, 174, 96))
    else:
        tft.text("NTP fail", 32, 90, ST7735.rgb(255, 165, 0))
    tft.show()
    time.sleep(2)
except Exception as e:
    print("Boot display error:", e)
