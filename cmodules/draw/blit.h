/*
 * blit.h — Sprite frame rendering
 */

#ifndef DRAW_BLIT_H
#define DRAW_BLIT_H

#include "draw.h"

/*
 * Render a single sprite frame into an RGB565 buffer.
 *
 * For 1bpp assets, color is the foreground; 0-pixels are transparent.
 * For multi-bpp assets, color is the tint and pixel value is the alpha.
 *
 * Always uses read-modify-write blending (sprites overlay existing content).
 * Returns bounding box of pixels actually written.
 */
draw_bbox_t draw_sprite(uint16_t *buf, int buf_w, int buf_h,
                        int x, int y,
                        const draw_asset_t *asset,
                        uint32_t frame_id,
                        uint16_t color);

#endif /* DRAW_BLIT_H */
