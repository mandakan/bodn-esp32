# main.py — Bodn ESP32 entry point (hardware test / playground)
import time
import neopixel
from machine import Pin, SPI
from bodn import config
from bodn.encoder import Encoder
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
    # Triangle wave: 0→255→0 over ~128 frames
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
        # Simple pseudo-random based on frame and LED index
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
        # Approximate sine with triangle
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


def main():
    tft = create_display()
    buttons = [Pin(p, Pin.IN, Pin.PULL_UP) for p in config.BTN_PINS]
    switches = [Pin(p, Pin.IN, Pin.PULL_UP) for p in config.SW_PINS]
    np = neopixel.NeoPixel(Pin(config.NEOPIXEL_PIN, Pin.OUT), N_LEDS, timing=1)
    encoders = [
        Encoder(config.ENC1_CLK, config.ENC1_DT, config.ENC1_SW, min_val=0, max_val=ENC_STEPS),
        Encoder(config.ENC2_CLK, config.ENC2_DT, config.ENC2_SW, min_val=0, max_val=ENC_STEPS),
        Encoder(config.ENC3_CLK, config.ENC3_DT, config.ENC3_SW, min_val=0, max_val=ENC_STEPS),
    ]
    # Sensible defaults: brightness mid, hue 0, speed mid
    encoders[0].value = ENC_STEPS // 2
    encoders[2].value = ENC_STEPS // 4

    # Clear LEDs
    for i in range(N_LEDS):
        np[i] = (0, 0, 0)
    np.write()

    active_pattern = 0  # default: rainbow
    frame = 0

    while True:
        frame += 1

        # --- Read inputs ---
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

        # Encoder 1 = brightness
        brightness = min(255, max(10, enc_pos[0] * 255 // ENC_STEPS))
        # Encoder 2 = hue offset / colour shift
        hue_offset = enc_pos[1] * 255 // ENC_STEPS
        # Encoder 3 = animation speed
        speed = max(1, enc_pos[2])

        # Button press selects the LED pattern
        if pressed:
            active_pattern = pressed[0] % len(PATTERNS)

        # Encoder buttons cycle patterns too
        for ep in enc_pressed:
            active_pattern = (active_pattern + 1) % len(PATTERNS)

        # --- Compute LED pattern ---
        pat_fn = PATTERNS[active_pattern]
        colour = BTN_COLOURS_RGB[active_pattern]

        if active_pattern == 0:
            # Rainbow uses hue_offset instead of fixed colour
            leds = pat_fn(frame, speed, hue_offset, brightness)
        else:
            leds = pat_fn(frame, speed, colour, brightness)

        # Toggle switches modify the output:
        # SW0: reverse the LED order
        if sw_states[0]:
            leds = leds[::-1]
        # SW1: mirror (first half mirrored to second)
        if sw_states[1]:
            half = N_LEDS // 2
            for i in range(half):
                leds[N_LEDS - 1 - i] = leds[i]
        # SW2: strobe — blink every 4th frame
        if sw_states[2]:
            if (frame // 4) % 2 == 0:
                leds = [(0, 0, 0)] * N_LEDS
        # SW3: colour invert
        if len(sw_states) > 3 and sw_states[3]:
            leds = [(255 - r, 255 - g, 255 - b) for r, g, b in leds]

        # Write to strip (every 3rd frame to avoid simulator timing glitches)
        if frame % 3 == 0:
            for i in range(N_LEDS):
                np[i] = leds[i]
            np.write()
            time.sleep_ms(2)

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

        # Button grid — show which are pressed
        tft.text("Buttons", 0, 114, WHITE)
        for i in range(8):
            x = (i % 4) * 32
            y = 126 + (i // 4) * 16
            if i in pressed:
                tft.fill_rect(x, y, 28, 12, BTN_COLOURS_565[i])
                tft.text(BTN_NAMES[i], x + 2, y + 2, BLACK)
            else:
                tft.rect(x, y, 28, 12, BTN_COLOURS_565[i])

        tft.show()
        time.sleep_ms(30)


main()
