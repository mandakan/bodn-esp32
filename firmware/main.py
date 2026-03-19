# main.py — Bodn ESP32 entry point (async, with parental session controls)

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

import time
import neopixel
from machine import Pin, SPI
from bodn import config
from bodn.encoder import Encoder
from bodn.session import SessionManager, PLAYING, WARN_5, WARN_2, WINDDOWN, SLEEPING, COOLDOWN, LOCKDOWN, IDLE
from bodn.web import start_server
from bodn import storage
from st7735 import ST7735

# RGB565 colours (byte-swapped for framebuf)
BLACK = ST7735.rgb(0, 0, 0)
WHITE = ST7735.rgb(255, 255, 255)
RED = ST7735.rgb(255, 0, 0)
GREEN = ST7735.rgb(0, 255, 0)
BLUE = ST7735.rgb(0, 0, 255)
YELLOW = ST7735.rgb(255, 255, 0)
CYAN = ST7735.rgb(0, 255, 255)
MAGENTA = ST7735.rgb(255, 0, 255)
ORANGE = ST7735.rgb(255, 128, 0)
PURPLE = ST7735.rgb(128, 0, 255)
AMBER = ST7735.rgb(255, 191, 0)

# One colour per button
BTN_COLOURS_565 = [RED, GREEN, BLUE, YELLOW, CYAN, MAGENTA, ORANGE, PURPLE]
BTN_COLOURS_RGB = [
    (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
    (0, 255, 255), (255, 0, 255), (255, 128, 0), (128, 0, 255),
]
BTN_NAMES = ["Red", "Grn", "Blu", "Yel", "Cyn", "Mag", "Org", "Pur"]

ENC_STEPS = 20
N_LEDS = config.NEOPIXEL_COUNT


def hsv_to_rgb(h, s, v):
    """Convert HSV (0-255 each) to RGB tuple."""
    if s == 0:
        return (v, v, v)
    region = (h * 6) >> 8
    remainder = (h * 6) - (region << 8)
    p = (v * (255 - s)) >> 8
    q = (v * (255 - ((s * remainder) >> 8))) >> 8
    t = (v * (255 - ((s * (255 - remainder)) >> 8))) >> 8
    if region == 0:
        return (v, t, p)
    if region == 1:
        return (q, v, p)
    if region == 2:
        return (p, v, t)
    if region == 3:
        return (p, q, v)
    if region == 4:
        return (t, p, v)
    return (v, p, q)


def scale(rgb, bright):
    """Scale an RGB tuple by brightness (0-255)."""
    return tuple((c * bright) >> 8 for c in rgb)


def create_display():
    spi = SPI(
        2,
        baudrate=26_000_000,
        sck=Pin(config.TFT_SCK),
        mosi=Pin(config.TFT_MOSI),
    )
    return ST7735(
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


# ---------------------------------------------------------------------------
# LED animation patterns — each button selects a different one
# ---------------------------------------------------------------------------

def pattern_rainbow(frame, speed, hue_off, bright):
    """Smooth rainbow flowing across the strip."""
    leds = []
    for i in range(N_LEDS):
        h = (hue_off + i * 255 // N_LEDS + frame * speed) & 0xFF
        leds.append(scale(hsv_to_rgb(h, 255, 255), bright))
    return leds


def pattern_pulse(frame, speed, colour, bright):
    """All LEDs pulse together in one colour."""
    phase = (frame * speed) & 0xFF
    v = phase if phase < 128 else 255 - phase
    v = (v * bright) >> 7
    c = scale(colour, v)
    return [c] * N_LEDS


def pattern_chase(frame, speed, colour, bright):
    """A bright dot chases around the strip, leaving a fading tail."""
    leds = []
    pos = (frame * speed // 2) % N_LEDS
    for i in range(N_LEDS):
        dist = (pos - i) % N_LEDS
        if dist == 0:
            leds.append(scale(colour, bright))
        elif dist < 4:
            fade = bright >> dist
            leds.append(scale(colour, fade))
        else:
            leds.append((0, 0, 0))
    return leds


def pattern_sparkle(frame, speed, colour, bright):
    """Random-ish sparkle — deterministic from frame number."""
    leds = []
    for i in range(N_LEDS):
        v = ((frame * speed * 7 + i * 53) * 131) & 0xFF
        if v > 200:
            leds.append(scale(colour, bright))
        else:
            leds.append((0, 0, 0))
    return leds


def pattern_bounce(frame, speed, colour, bright):
    """A dot bounces back and forth."""
    leds = []
    cycle = (N_LEDS - 1) * 2
    pos = (frame * speed // 2) % cycle
    if pos >= N_LEDS:
        pos = cycle - pos
    for i in range(N_LEDS):
        dist = abs(i - pos)
        if dist == 0:
            leds.append(scale(colour, bright))
        elif dist == 1:
            leds.append(scale(colour, bright >> 1))
        else:
            leds.append((0, 0, 0))
    return leds


def pattern_wave(frame, speed, colour, bright):
    """Sine-like wave of brightness across the strip."""
    leds = []
    for i in range(N_LEDS):
        phase = (i * 255 // N_LEDS + frame * speed) & 0xFF
        v = phase if phase < 128 else 255 - phase
        v = (v * bright) >> 7
        leds.append(scale(colour, v))
    return leds


def pattern_split(frame, speed, colour, bright):
    """Two dots start from center and expand outward, then collapse."""
    leds = [(0, 0, 0)] * N_LEDS
    mid = N_LEDS // 2
    cycle = mid + 1
    pos = (frame * speed // 2) % (cycle * 2)
    if pos >= cycle:
        pos = cycle * 2 - pos - 1
    for offset in range(min(pos + 1, mid + 1)):
        v = bright if offset == pos else bright >> 2
        a = mid + offset
        b = mid - offset
        if 0 <= a < N_LEDS:
            leds[a] = scale(colour, v)
        if 0 <= b < N_LEDS:
            leds[b] = scale(colour, v)
    return leds


def pattern_fill(frame, speed, colour, bright):
    """LEDs fill up one by one, then empty."""
    leds = []
    cycle = N_LEDS * 2
    pos = (frame * speed // 2) % cycle
    fill = pos if pos < N_LEDS else cycle - pos
    for i in range(N_LEDS):
        if i < fill:
            leds.append(scale(colour, bright))
        else:
            leds.append((0, 0, 0))
    return leds


PATTERNS = [
    pattern_rainbow,
    pattern_pulse,
    pattern_chase,
    pattern_sparkle,
    pattern_bounce,
    pattern_wave,
    pattern_split,
    pattern_fill,
]
PATTERN_NAMES = [
    "Rainbow", "Pulse", "Chase", "Sparkle",
    "Bounce", "Wave", "Split", "Fill",
]


# ---------------------------------------------------------------------------
# Session-aware display overlays
# ---------------------------------------------------------------------------

def draw_session_overlay(tft, session_mgr, frame):
    """Draw session state info on the bottom of the TFT."""
    state = session_mgr.state

    if state == PLAYING:
        remaining = session_mgr.time_remaining_s
        mins = remaining // 60
        secs = remaining % 60
        tft.text("{:d}:{:02d}".format(mins, secs), 88, 3, GREEN)

    elif state == WARN_5:
        remaining = session_mgr.time_remaining_s
        mins = remaining // 60
        secs = remaining % 60
        tft.text("{:d}:{:02d}".format(mins, secs), 88, 3, AMBER)

    elif state == WARN_2:
        remaining = session_mgr.time_remaining_s
        mins = remaining // 60
        secs = remaining % 60
        # Blink the timer
        if (frame // 15) % 2 == 0:
            tft.text("{:d}:{:02d}".format(mins, secs), 88, 3, RED)

    elif state == WINDDOWN:
        if (frame // 20) % 2 == 0:
            tft.text("Zzz...", 40, 70, AMBER)

    elif state in (SLEEPING, COOLDOWN):
        tft.fill(BLACK)
        tft.text("Zzz", 52, 60, BLUE)
        tft.text("See you", 36, 80, WHITE)
        tft.text("soon!", 44, 96, WHITE)

    elif state == LOCKDOWN:
        tft.fill(BLACK)
        tft.text("Goodnight!", 24, 70, MAGENTA)


def leds_for_state(state, frame, leds, brightness):
    """Modify LED output based on session state."""
    if state == WARN_5:
        # Shift toward amber
        amber = (255, 191, 0)
        return [scale(amber, brightness)] * N_LEDS if (frame // 30) % 2 == 0 else leds

    elif state == WARN_2:
        # Dim pulsing
        phase = (frame * 3) & 0xFF
        v = phase if phase < 128 else 255 - phase
        dim = max(10, (v * brightness) >> 8)
        return [scale((255, 100, 0), dim)] * N_LEDS

    elif state == WINDDOWN:
        # Fade off over 30 seconds (~1000 frames at 30fps)
        fade = max(0, 255 - (frame % 1000) * 255 // 1000)
        return [scale((40, 40, 80), (fade * brightness) >> 8)] * N_LEDS

    elif state in (SLEEPING, COOLDOWN, LOCKDOWN):
        return [(0, 0, 0)] * N_LEDS

    return leds


# ---------------------------------------------------------------------------
# Main async loop
# ---------------------------------------------------------------------------

async def ui_loop(session_mgr, settings):
    """Main UI coroutine — reads inputs, runs animations, manages display."""
    tft = create_display()
    buttons = [Pin(p, Pin.IN, Pin.PULL_UP) for p in config.BTN_PINS]
    switches = [Pin(p, Pin.IN, Pin.PULL_UP) for p in config.SW_PINS]
    np = neopixel.NeoPixel(Pin(config.NEOPIXEL_PIN, Pin.OUT), N_LEDS, timing=1)
    encoders = [
        Encoder(config.ENC1_CLK, config.ENC1_DT, config.ENC1_SW, min_val=0, max_val=ENC_STEPS),
        Encoder(config.ENC2_CLK, config.ENC2_DT, config.ENC2_SW, min_val=0, max_val=ENC_STEPS),
        Encoder(config.ENC3_CLK, config.ENC3_DT, config.ENC3_SW, min_val=0, max_val=ENC_STEPS),
    ]
    encoders[0].value = ENC_STEPS // 2
    encoders[2].value = ENC_STEPS // 4

    # Clear LEDs
    for i in range(N_LEDS):
        np[i] = (0, 0, 0)
    np.write()

    active_pattern = 0
    frame = 0
    # Auto-start first session
    session_mgr.try_wake()

    while True:
        frame += 1
        state = session_mgr.tick()

        # --- Handle sleeping/lockdown states (minimal processing) ---
        if state in (SLEEPING, COOLDOWN, LOCKDOWN):
            # Check for wake attempt on any button press
            any_pressed = False
            for btn in buttons:
                if btn.value() == 0:
                    any_pressed = True
                    break

            if any_pressed and state == COOLDOWN:
                # Try to wake — will fail if still in cooldown
                pass  # tick() handles the transition to IDLE
            elif any_pressed and state == IDLE:
                session_mgr.try_wake()

            # Dark display
            tft.fill(BLACK)
            draw_session_overlay(tft, session_mgr, frame)
            tft.show()

            # Dark LEDs
            for i in range(N_LEDS):
                np[i] = (0, 0, 0)
            if frame % 3 == 0:
                np.write()

            await asyncio.sleep_ms(100)
            continue

        # If we just became IDLE, try to auto-wake on button press
        if state == IDLE:
            any_pressed = False
            for btn in buttons:
                if btn.value() == 0:
                    any_pressed = True
                    break
            if any_pressed:
                session_mgr.try_wake()
            else:
                # Show idle screen
                tft.fill(BLACK)
                tft.text("~ Bodn ~", 32, 40, WHITE)
                tft.text("Press a", 36, 70, CYAN)
                tft.text("button!", 36, 86, CYAN)
                remaining = session_mgr.sessions_remaining
                tft.text("{} plays left".format(remaining), 16, 120, GREEN if remaining > 0 else RED)
                tft.show()
                for i in range(N_LEDS):
                    np[i] = (0, 0, 0)
                if frame % 3 == 0:
                    np.write()
                await asyncio.sleep_ms(100)
                continue

        # --- Active play: read inputs ---
        pressed = []
        for i, btn in enumerate(buttons):
            if btn.value() == 0:
                pressed.append(i)

        enc_pressed = []
        for i, enc in enumerate(encoders):
            if enc.pressed():
                enc_pressed.append(i)

        sw_states = [sw.value() == 0 for sw in switches]
        enc_pos = [enc.value for enc in encoders]

        brightness = min(255, max(10, enc_pos[0] * 255 // ENC_STEPS))
        hue_offset = enc_pos[1] * 255 // ENC_STEPS
        speed = max(1, enc_pos[2])

        if pressed:
            active_pattern = pressed[0] % len(PATTERNS)

        for ep in enc_pressed:
            active_pattern = (active_pattern + 1) % len(PATTERNS)

        # --- Compute LED pattern ---
        pat_fn = PATTERNS[active_pattern]
        colour = BTN_COLOURS_RGB[active_pattern]

        if active_pattern == 0:
            leds = pat_fn(frame, speed, hue_offset, brightness)
        else:
            leds = pat_fn(frame, speed, colour, brightness)

        # Toggle switch modifiers
        if sw_states[0]:
            leds = leds[::-1]
        if sw_states[1]:
            half = N_LEDS // 2
            for i in range(half):
                leds[N_LEDS - 1 - i] = leds[i]
        if sw_states[2]:
            if (frame // 4) % 2 == 0:
                leds = [(0, 0, 0)] * N_LEDS
        if len(sw_states) > 3 and sw_states[3]:
            leds = [(255 - r, 255 - g, 255 - b) for r, g, b in leds]

        # Apply session state to LEDs
        leds = leds_for_state(state, frame, leds, brightness)

        # Write to strip
        if frame % 3 == 0:
            for i in range(N_LEDS):
                np[i] = leds[i]
            np.write()
            await asyncio.sleep_ms(2)

        # --- Display ---
        tft.fill(BLACK)

        # Title + active pattern
        tft.text("~ Bodn ~", 32, 3, WHITE)
        pat_colour = BTN_COLOURS_565[active_pattern]
        tft.fill_rect(0, 16, 128, 12, pat_colour)
        tft.text(PATTERN_NAMES[active_pattern], 4, 18, BLACK)

        # Encoder bars
        bar_info = [
            ("Bri", CYAN, enc_pos[0]),
            ("Hue", MAGENTA, enc_pos[1]),
            ("Spd", ORANGE, enc_pos[2]),
        ]
        for i, (label, colour_565, val) in enumerate(bar_info):
            y = 32 + i * 16
            w = max(0, 96 * val // ENC_STEPS)
            tft.rect(24, y, 96, 10, WHITE)
            if w > 0:
                tft.fill_rect(24, y, w, 10, colour_565)
            tft.text(label, 0, y + 1, colour_565)

        # Toggle indicators
        tft.text("Toggles", 0, 82, WHITE)
        toggle_labels = ["Rev", "Mir", "Str", "Inv"]
        for i in range(len(sw_states)):
            x = i * 32
            y = 94
            if sw_states[i]:
                tft.fill_rect(x, y, 28, 14, GREEN)
                tft.text(toggle_labels[i], x + 2, y + 3, BLACK)
            else:
                tft.rect(x, y, 28, 14, WHITE)
                tft.text(toggle_labels[i], x + 2, y + 3, WHITE)

        # Button grid
        tft.text("Buttons", 0, 114, WHITE)
        for i in range(8):
            x = (i % 4) * 32
            y = 126 + (i // 4) * 16
            if i in pressed:
                tft.fill_rect(x, y, 28, 12, BTN_COLOURS_565[i])
                tft.text(BTN_NAMES[i], x + 2, y + 2, BLACK)
            else:
                tft.rect(x, y, 28, 12, BTN_COLOURS_565[i])

        # Session overlay (timer, warnings)
        draw_session_overlay(tft, session_mgr, frame)

        tft.show()
        await asyncio.sleep_ms(30)


async def main():
    """Entry point: start web server + UI loop concurrently."""
    # Import settings from boot.py (shared by reference)
    import boot

    settings = boot.settings

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

    # Start web server (non-fatal — box works without networking)
    _server = None
    try:
        _server = await start_server(session_mgr, settings)
        print("Web server running on port 80")
    except Exception as e:
        print("Web server failed to start:", e)

    # Run UI loop (keep _server alive to prevent GC)
    await ui_loop(session_mgr, settings)


try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("Bodn stopped.")
