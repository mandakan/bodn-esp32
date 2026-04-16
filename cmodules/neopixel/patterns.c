// patterns.c — NeoPixel pattern functions (pure math, no I/O)
//
// Direct C ports of the Python patterns in firmware/bodn/patterns.py.
// All integer math, no floating point.  Each function writes GRB data
// into the output buffer for a zone's LED range.

#include "patterns.h"
#include "neopixel_mod.h"

// ---------------------------------------------------------------------------
// HSV → RGB (same integer algorithm as patterns.py hsv_to_rgb)
// ---------------------------------------------------------------------------

void np_hsv_to_rgb(uint8_t h, uint8_t s, uint8_t v,
                   uint8_t *r_out, uint8_t *g_out, uint8_t *b_out) {
    if (s == 0) {
        *r_out = *g_out = *b_out = v;
        return;
    }
    uint16_t region = (h * 6) >> 8;
    uint16_t remainder = (h * 6) - (region << 8);
    uint8_t p = (v * (255 - s)) >> 8;
    uint8_t q = (v * (255 - ((s * remainder) >> 8))) >> 8;
    uint8_t t = (v * (255 - ((s * (255 - remainder)) >> 8))) >> 8;
    switch (region) {
        case 0: *r_out = v; *g_out = t; *b_out = p; break;
        case 1: *r_out = q; *g_out = v; *b_out = p; break;
        case 2: *r_out = p; *g_out = v; *b_out = t; break;
        case 3: *r_out = p; *g_out = q; *b_out = v; break;
        case 4: *r_out = t; *g_out = p; *b_out = v; break;
        default: *r_out = v; *g_out = p; *b_out = q; break;
    }
}

// Helper: write one GRB pixel with brightness scaling
static inline void set_grb(uint8_t *buf, int off,
                            uint8_t r, uint8_t g, uint8_t b,
                            uint8_t brightness) {
    buf[off + 0] = (g * brightness) >> 8;
    buf[off + 1] = (r * brightness) >> 8;
    buf[off + 2] = (b * brightness) >> 8;
}

// Helper: write one GRB pixel (pre-scaled)
static inline void set_grb_raw(uint8_t *buf, int off,
                                uint8_t r, uint8_t g, uint8_t b) {
    buf[off + 0] = g;
    buf[off + 1] = r;
    buf[off + 2] = b;
}

// ---------------------------------------------------------------------------
// Pattern: OFF
// ---------------------------------------------------------------------------

static void pat_off(uint8_t *buf, uint8_t count, uint8_t speed,
                    uint8_t brightness, uint8_t r, uint8_t g, uint8_t b,
                    uint8_t hue_offset, uint32_t frame) {
    (void)speed; (void)brightness; (void)r; (void)g; (void)b;
    (void)hue_offset; (void)frame;
    for (int i = 0; i < count * 3; i++) {
        buf[i] = 0;
    }
}

// ---------------------------------------------------------------------------
// Pattern: SOLID
// ---------------------------------------------------------------------------

static void pat_solid(uint8_t *buf, uint8_t count, uint8_t speed,
                      uint8_t brightness, uint8_t r, uint8_t g, uint8_t b,
                      uint8_t hue_offset, uint32_t frame) {
    (void)speed; (void)hue_offset; (void)frame;
    for (int i = 0; i < count; i++) {
        set_grb(buf, i * 3, r, g, b, brightness);
    }
}

// ---------------------------------------------------------------------------
// Pattern: RAINBOW
// ---------------------------------------------------------------------------

static void pat_rainbow(uint8_t *buf, uint8_t count, uint8_t speed,
                         uint8_t brightness, uint8_t r, uint8_t g, uint8_t b,
                         uint8_t hue_offset, uint32_t frame) {
    (void)r; (void)g; (void)b;
    for (int i = 0; i < count; i++) {
        uint8_t h = (hue_offset + i * 255 / count + frame * speed) & 0xFF;
        uint8_t cr, cg, cb;
        np_hsv_to_rgb(h, 255, 255, &cr, &cg, &cb);
        set_grb(buf, i * 3, cr, cg, cb, brightness);
    }
}

// ---------------------------------------------------------------------------
// Pattern: PULSE
// ---------------------------------------------------------------------------

static void pat_pulse(uint8_t *buf, uint8_t count, uint8_t speed,
                      uint8_t brightness, uint8_t r, uint8_t g, uint8_t b,
                      uint8_t hue_offset, uint32_t frame) {
    (void)hue_offset;
    uint8_t phase = (frame * speed) & 0xFF;
    uint8_t v = phase < 128 ? phase : 255 - phase;
    v = (v * brightness) >> 7;
    uint8_t gr = (g * v) >> 8;
    uint8_t rr = (r * v) >> 8;
    uint8_t br = (b * v) >> 8;
    for (int i = 0; i < count; i++) {
        set_grb_raw(buf, i * 3, rr, gr, br);
    }
}

// ---------------------------------------------------------------------------
// Pattern: CHASE
// ---------------------------------------------------------------------------

static void pat_chase(uint8_t *buf, uint8_t count, uint8_t speed,
                      uint8_t brightness, uint8_t r, uint8_t g, uint8_t b,
                      uint8_t hue_offset, uint32_t frame) {
    (void)hue_offset;
    int pos = (frame * speed / 2) % count;
    for (int i = 0; i < count; i++) {
        int dist = (pos - i + count) % count;
        if (dist == 0) {
            set_grb(buf, i * 3, r, g, b, brightness);
        } else if (dist < 4) {
            set_grb(buf, i * 3, r, g, b, brightness >> dist);
        } else {
            set_grb_raw(buf, i * 3, 0, 0, 0);
        }
    }
}

// ---------------------------------------------------------------------------
// Pattern: SPARKLE
// ---------------------------------------------------------------------------

static void pat_sparkle(uint8_t *buf, uint8_t count, uint8_t speed,
                         uint8_t brightness, uint8_t r, uint8_t g, uint8_t b,
                         uint8_t hue_offset, uint32_t frame) {
    (void)hue_offset;
    for (int i = 0; i < count; i++) {
        uint8_t v = ((frame * speed * 7 + i * 53) * 131) & 0xFF;
        if (v > 200) {
            set_grb(buf, i * 3, r, g, b, brightness);
        } else {
            set_grb_raw(buf, i * 3, 0, 0, 0);
        }
    }
}

// ---------------------------------------------------------------------------
// Pattern: BOUNCE
// ---------------------------------------------------------------------------

static void pat_bounce(uint8_t *buf, uint8_t count, uint8_t speed,
                        uint8_t brightness, uint8_t r, uint8_t g, uint8_t b,
                        uint8_t hue_offset, uint32_t frame) {
    (void)hue_offset;
    int n = count;
    int cycle = (n - 1) * 2;
    if (cycle <= 0) cycle = 1;
    int pos = (frame * speed / 2) % cycle;
    if (pos >= n) pos = cycle - pos;
    for (int i = 0; i < n; i++) {
        int dist = i > pos ? i - pos : pos - i;
        if (dist == 0) {
            set_grb(buf, i * 3, r, g, b, brightness);
        } else if (dist == 1) {
            set_grb(buf, i * 3, r, g, b, brightness >> 1);
        } else {
            set_grb_raw(buf, i * 3, 0, 0, 0);
        }
    }
}

// ---------------------------------------------------------------------------
// Pattern: WAVE
// ---------------------------------------------------------------------------

static void pat_wave(uint8_t *buf, uint8_t count, uint8_t speed,
                     uint8_t brightness, uint8_t r, uint8_t g, uint8_t b,
                     uint8_t hue_offset, uint32_t frame) {
    (void)hue_offset;
    for (int i = 0; i < count; i++) {
        uint8_t phase = (i * 255 / count + frame * speed) & 0xFF;
        uint8_t v = phase < 128 ? phase : 255 - phase;
        v = (v * brightness) >> 7;
        uint8_t rr = (r * v) >> 8;
        uint8_t gr = (g * v) >> 8;
        uint8_t br = (b * v) >> 8;
        set_grb_raw(buf, i * 3, rr, gr, br);
    }
}

// ---------------------------------------------------------------------------
// Pattern: SPLIT
// ---------------------------------------------------------------------------

static void pat_split(uint8_t *buf, uint8_t count, uint8_t speed,
                      uint8_t brightness, uint8_t r, uint8_t g, uint8_t b,
                      uint8_t hue_offset, uint32_t frame) {
    (void)hue_offset;
    int n = count;
    int mid = n / 2;
    int cycle = mid + 1;
    if (cycle <= 0) cycle = 1;
    int pos = (frame * speed / 2) % (cycle * 2);
    if (pos >= cycle) pos = cycle * 2 - pos - 1;

    // Clear all first
    for (int i = 0; i < n * 3; i++) buf[i] = 0;

    // Draw expanding dots from center
    for (int offset = 0; offset <= pos && offset <= mid; offset++) {
        uint8_t v = (offset == pos) ? brightness : brightness >> 2;
        int a = mid + offset;
        int bb = mid - offset;
        if (a < n) set_grb(buf, a * 3, r, g, b, v);
        if (bb >= 0) set_grb(buf, bb * 3, r, g, b, v);
    }
}

// ---------------------------------------------------------------------------
// Pattern: FILL (progressive fill/empty)
// ---------------------------------------------------------------------------

static void pat_fill(uint8_t *buf, uint8_t count, uint8_t speed,
                     uint8_t brightness, uint8_t r, uint8_t g, uint8_t b,
                     uint8_t hue_offset, uint32_t frame) {
    (void)hue_offset;
    int n = count;
    int cycle = n * 2;
    if (cycle <= 0) cycle = 1;
    int pos = (frame * speed / 2) % cycle;
    int fill = pos < n ? pos : cycle - pos;
    for (int i = 0; i < n; i++) {
        if (i < fill) {
            set_grb(buf, i * 3, r, g, b, brightness);
        } else {
            set_grb_raw(buf, i * 3, 0, 0, 0);
        }
    }
}

// ---------------------------------------------------------------------------
// Pattern lookup table
// ---------------------------------------------------------------------------

const np_pattern_fn np_pattern_funcs[NP_PAT_COUNT] = {
    [NP_PAT_OFF]     = pat_off,
    [NP_PAT_SOLID]   = pat_solid,
    [NP_PAT_RAINBOW] = pat_rainbow,
    [NP_PAT_PULSE]   = pat_pulse,
    [NP_PAT_CHASE]   = pat_chase,
    [NP_PAT_SPARKLE] = pat_sparkle,
    [NP_PAT_BOUNCE]  = pat_bounce,
    [NP_PAT_WAVE]    = pat_wave,
    [NP_PAT_SPLIT]   = pat_split,
    [NP_PAT_FILL]    = pat_fill,
};
