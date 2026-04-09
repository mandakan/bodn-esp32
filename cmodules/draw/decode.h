/*
 * decode.h — Shared bitmap decoding, binary search, alpha blending
 */

#ifndef DRAW_DECODE_H
#define DRAW_DECODE_H

#include "draw.h"

/*
 * Find an index entry by id (binary search, O(log n)).
 * Returns NULL if not found.
 */
const draw_index_entry_t *draw_find_entry(const draw_asset_t *asset, uint32_t id);

/*
 * Blit one glyph/frame into an RGB565 buffer.
 *
 * buf      — writable RGB565 pixel buffer
 * buf_w    — buffer width in pixels (stride = buf_w * 2 bytes)
 * buf_h    — buffer height in pixels
 * x, y     — destination top-left
 * asset    — loaded asset
 * entry    — glyph/frame to render (from draw_find_entry)
 * color    — foreground/tint color (byte-swapped RGB565)
 * bg_color — background color for blending, or -1 for read-modify-write
 *
 * Returns bounding box of pixels actually written.
 */
draw_bbox_t draw_blit_entry(uint16_t *buf, int buf_w, int buf_h,
                            int x, int y,
                            const draw_asset_t *asset,
                            const draw_index_entry_t *entry,
                            uint16_t color, int32_t bg_color);

#endif /* DRAW_DECODE_H */
