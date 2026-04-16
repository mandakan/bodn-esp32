// patterns.h — NeoPixel pattern functions (pure math, no I/O)

#ifndef NEOPIXEL_PATTERNS_H
#define NEOPIXEL_PATTERNS_H

#include <stdint.h>

// Pattern function signature:
//   buf       — GRB output buffer (count * 3 bytes)
//   count     — number of LEDs in this zone
//   speed     — 1-10
//   brightness — 0-255
//   r, g, b   — base colour
//   hue_offset — for rainbow
//   frame     — global frame counter
typedef void (*np_pattern_fn)(
    uint8_t *buf, uint8_t count, uint8_t speed, uint8_t brightness,
    uint8_t r, uint8_t g, uint8_t b, uint8_t hue_offset, uint32_t frame);

// Pattern lookup table (indexed by NP_PAT_*)
extern const np_pattern_fn np_pattern_funcs[];

// HSV to RGB conversion (0-255 each)
void np_hsv_to_rgb(uint8_t h, uint8_t s, uint8_t v,
                   uint8_t *r_out, uint8_t *g_out, uint8_t *b_out);

#endif // NEOPIXEL_PATTERNS_H
