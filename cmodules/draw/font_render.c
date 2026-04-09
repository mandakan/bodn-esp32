/*
 * font_render.c — Bitmap font text rendering
 *
 * Decodes UTF-8 codepoints, looks up glyphs in a BDF asset, and renders
 * them left-to-right into an RGB565 framebuffer via draw_blit_entry().
 */

#include "font_render.h"
#include "decode.h"

/* ---- UTF-8 decoder --------------------------------------------------- */

/*
 * Decode one UTF-8 codepoint from *p.  Advances *p past the consumed bytes.
 * Returns the codepoint, or 0xFFFD (replacement char) on invalid input.
 * *remaining is decremented by the number of bytes consumed.
 */
static uint32_t utf8_next(const char **p, size_t *remaining) {
    if (*remaining == 0) return 0;

    const uint8_t *s = (const uint8_t *)*p;
    uint32_t cp;
    int need;  /* additional continuation bytes */

    if (s[0] < 0x80) {
        cp = s[0];
        need = 0;
    } else if ((s[0] & 0xE0) == 0xC0) {
        cp = s[0] & 0x1F;
        need = 1;
    } else if ((s[0] & 0xF0) == 0xE0) {
        cp = s[0] & 0x0F;
        need = 2;
    } else if ((s[0] & 0xF8) == 0xF0) {
        cp = s[0] & 0x07;
        need = 3;
    } else {
        /* Invalid lead byte — skip one byte */
        *p += 1;
        *remaining -= 1;
        return 0xFFFD;
    }

    if ((size_t)(need + 1) > *remaining) {
        /* Truncated sequence — consume what's left */
        *p += *remaining;
        *remaining = 0;
        return 0xFFFD;
    }

    for (int i = 1; i <= need; i++) {
        if ((s[i] & 0xC0) != 0x80) {
            /* Bad continuation byte — consume only the lead */
            *p += 1;
            *remaining -= 1;
            return 0xFFFD;
        }
        cp = (cp << 6) | (s[i] & 0x3F);
    }

    int consumed = need + 1;
    *p += consumed;
    *remaining -= consumed;
    return cp;
}

/* ---- Text rendering -------------------------------------------------- */

/*
 * Union two bounding boxes.  If either is empty (w==0), return the other.
 */
static draw_bbox_t bbox_union(draw_bbox_t a, draw_bbox_t b) {
    if (a.w == 0 && a.h == 0) return b;
    if (b.w == 0 && b.h == 0) return a;

    int x0 = (a.x < b.x) ? a.x : b.x;
    int y0 = (a.y < b.y) ? a.y : b.y;
    int x1a = a.x + a.w;
    int x1b = b.x + b.w;
    int y1a = a.y + a.h;
    int y1b = b.y + b.h;
    int x1 = (x1a > x1b) ? x1a : x1b;
    int y1 = (y1a > y1b) ? y1a : y1b;

    return (draw_bbox_t){ .x = x0, .y = y0, .w = x1 - x0, .h = y1 - y0 };
}

draw_bbox_t draw_text(uint16_t *buf, int buf_w, int buf_h,
                      int x, int y, const char *utf8, size_t utf8_len,
                      const draw_asset_t *asset,
                      uint16_t color, int32_t bg_color) {
    draw_bbox_t total = DRAW_BBOX_EMPTY;
    int cursor_x = x;
    size_t remaining = utf8_len;
    const char *p = utf8;

    while (remaining > 0) {
        uint32_t cp = utf8_next(&p, &remaining);
        if (cp == 0xFFFD) continue;  /* skip invalid */

        const draw_index_entry_t *entry = draw_find_entry(asset, cp);
        if (!entry) continue;  /* skip missing glyphs */

        /* Quick reject: glyph entirely off-screen to the right */
        if (cursor_x >= buf_w) break;

        draw_bbox_t bb = draw_blit_entry(buf, buf_w, buf_h,
                                         cursor_x, y,
                                         asset, entry,
                                         color, bg_color);
        total = bbox_union(total, bb);
        cursor_x += entry->width;
    }

    return total;
}

int draw_text_width(const char *utf8, size_t utf8_len,
                    const draw_asset_t *asset) {
    int width = 0;
    size_t remaining = utf8_len;
    const char *p = utf8;

    while (remaining > 0) {
        uint32_t cp = utf8_next(&p, &remaining);
        if (cp == 0xFFFD) continue;

        const draw_index_entry_t *entry = draw_find_entry(asset, cp);
        if (entry) {
            width += entry->width;
        }
    }

    return width;
}
