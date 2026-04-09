/*
 * decode.c — Shared bitmap decoding, binary search, alpha blending
 *
 * Operates on the Bodn Draw Format (.bdf) binary layout defined in draw.h.
 * All pixel writes go directly into an RGB565 framebuffer.
 *
 * Two pixel modes (selected by DRAW_FLAG_COLOR in header flags):
 *   - Alpha-only (flags & 0x01 == 0): each pixel is bpp-bit intensity,
 *     rendered with a caller-supplied tint color.
 *   - Color+alpha (flags & 0x01 == 1): each pixel is 2 bytes RGB565 followed
 *     by bpp-bit alpha.  The stored color is used directly.
 */

#include "decode.h"

/* ---- Binary search --------------------------------------------------- */

const draw_index_entry_t *draw_find_entry(const draw_asset_t *asset, uint32_t id) {
    const draw_index_entry_t *base = asset->index;
    int lo = 0;
    int hi = asset->header->num_entries - 1;

    while (lo <= hi) {
        int mid = lo + (hi - lo) / 2;
        uint32_t mid_id = base[mid].id;
        if (mid_id == id) {
            return &base[mid];
        } else if (mid_id < id) {
            lo = mid + 1;
        } else {
            hi = mid - 1;
        }
    }
    return NULL;
}

/* ---- Alpha-only pixel extraction ------------------------------------- */

/*
 * Extract the intensity value of pixel (px, py) from packed alpha-only data.
 * Returns 0..max where max = (1 << bpp) - 1.
 */
static inline uint8_t get_alpha_pixel(const uint8_t *data, int offset,
                                      int width, int bpp, int px, int py) {
    int bits_per_row = width * bpp;
    int bytes_per_row = (bits_per_row + 7) >> 3;

    int bit_pos = px * bpp;
    int byte_idx = offset + py * bytes_per_row + (bit_pos >> 3);
    int bit_offset = bit_pos & 7;

    uint8_t raw = data[byte_idx];
    uint8_t mask = ((1 << bpp) - 1);
    int shift = 8 - bpp - bit_offset;
    return (raw >> shift) & mask;
}

/* ---- Color+alpha pixel extraction ------------------------------------ */

/*
 * For color mode, each entry's data is laid out as:
 *   [RGB565 plane]: width * height * 2 bytes (byte-swapped RGB565, row-major)
 *   [Alpha plane]:  packed at bpp bits per pixel (same as alpha-only)
 */

static inline uint16_t get_color_rgb(const uint8_t *data, int offset,
                                     int width, int px, int py) {
    int idx = offset + (py * width + px) * 2;
    /* Read as little-endian uint16 (matching framebuf byte order) */
    return (uint16_t)data[idx] | ((uint16_t)data[idx + 1] << 8);
}

static inline uint8_t get_color_alpha(const uint8_t *data, int offset,
                                      int width, int height, int bpp,
                                      int px, int py) {
    /* Alpha plane starts after the RGB565 plane */
    int alpha_offset = offset + width * height * 2;
    return get_alpha_pixel(data, alpha_offset, width, bpp, px, py);
}

/* ---- Alpha blending -------------------------------------------------- */

static inline uint16_t blend(uint16_t fg, uint16_t bg, uint8_t intensity, uint8_t max_val) {
    if (intensity == max_val) return fg;
    if (intensity == 0) return bg;

    uint8_t fr, fg_g, fb, br, bg_g, bb;
    draw_rgb565_decompose(fg, &fr, &fg_g, &fb);
    draw_rgb565_decompose(bg, &br, &bg_g, &bb);

    uint8_t r = br + ((int)(fr - br) * intensity + (max_val >> 1)) / max_val;
    uint8_t g = bg_g + ((int)(fg_g - bg_g) * intensity + (max_val >> 1)) / max_val;
    uint8_t b = bb + ((int)(fb - bb) * intensity + (max_val >> 1)) / max_val;

    return draw_rgb565_compose(r, g, b);
}

/* ---- Blit one entry -------------------------------------------------- */

draw_bbox_t draw_blit_entry(uint16_t *buf, int buf_w, int buf_h,
                            int x, int y,
                            const draw_asset_t *asset,
                            const draw_index_entry_t *entry,
                            uint16_t color, int32_t bg_color) {
    int ew = entry->width;
    int eh = entry->height;
    int bpp = asset->header->bpp;
    uint8_t max_val = (1 << bpp) - 1;
    int entry_off = entry->byte_offset;
    const uint8_t *bitmap = asset->bitmap;
    bool is_color = (asset->header->flags & DRAW_FLAG_COLOR) != 0;

    /* Clip: determine visible rectangle */
    int x0 = (x < 0) ? 0 : x;
    int y0 = (y < 0) ? 0 : y;
    int x1 = x + ew;
    int y1 = y + eh;
    if (x1 > buf_w) x1 = buf_w;
    if (y1 > buf_h) y1 = buf_h;

    if (x0 >= x1 || y0 >= y1) {
        return DRAW_BBOX_EMPTY;
    }

    /* Track actual drawn bounds for dirty rect */
    int dx0 = x1, dy0 = y1, dx1 = x0, dy1 = y0;

    bool rmw = (bg_color < 0);

    for (int py = y0 - y; py < y1 - y; py++) {
        int dst_y = y + py;
        for (int px = x0 - x; px < x1 - x; px++) {
            uint8_t alpha;
            uint16_t fg;

            if (is_color) {
                alpha = get_color_alpha(bitmap, entry_off, ew, eh, bpp, px, py);
                if (alpha == 0) continue;
                fg = get_color_rgb(bitmap, entry_off, ew, px, py);
            } else {
                alpha = get_alpha_pixel(bitmap, entry_off, ew, bpp, px, py);
                if (alpha == 0) continue;
                fg = color;
            }

            int dst_x = x + px;
            int dst_idx = dst_y * buf_w + dst_x;

            uint16_t out;
            if (alpha == max_val) {
                out = fg;
            } else {
                uint16_t bg = rmw ? buf[dst_idx] : (uint16_t)bg_color;
                out = blend(fg, bg, alpha, max_val);
            }
            buf[dst_idx] = out;

            /* Expand dirty bounds */
            if (dst_x < dx0) dx0 = dst_x;
            if (dst_x >= dx1) dx1 = dst_x + 1;
            if (dst_y < dy0) dy0 = dst_y;
            if (dst_y >= dy1) dy1 = dst_y + 1;
        }
    }

    if (dx0 >= dx1 || dy0 >= dy1) {
        return DRAW_BBOX_EMPTY;
    }

    return (draw_bbox_t){ .x = dx0, .y = dy0, .w = dx1 - dx0, .h = dy1 - dy0 };
}
