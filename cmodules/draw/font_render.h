/*
 * font_render.h — Bitmap font text rendering
 */

#ifndef DRAW_FONT_RENDER_H
#define DRAW_FONT_RENDER_H

#include "draw.h"

/*
 * Render a UTF-8 string into an RGB565 buffer.
 * Returns the bounding box of all pixels written.
 *
 * bg_color: -1 for read-modify-write, else fixed background color.
 */
draw_bbox_t draw_text(uint16_t *buf, int buf_w, int buf_h,
                      int x, int y, const char *utf8, size_t utf8_len,
                      const draw_asset_t *asset,
                      uint16_t color, int32_t bg_color);

/*
 * Measure the pixel width of a UTF-8 string without rendering.
 * Missing glyphs are skipped (contribute 0 width).
 */
int draw_text_width(const char *utf8, size_t utf8_len,
                    const draw_asset_t *asset);

#endif /* DRAW_FONT_RENDER_H */
