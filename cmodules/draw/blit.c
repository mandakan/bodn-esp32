/*
 * blit.c — Sprite frame rendering
 *
 * Thin wrapper around draw_find_entry() + draw_blit_entry().
 * Sprites always use read-modify-write blending (bg_color = -1).
 */

#include "blit.h"
#include "decode.h"

draw_bbox_t draw_sprite(uint16_t *buf, int buf_w, int buf_h,
                        int x, int y,
                        const draw_asset_t *asset,
                        uint32_t frame_id,
                        uint16_t color) {
    const draw_index_entry_t *entry = draw_find_entry(asset, frame_id);
    if (!entry) {
        return DRAW_BBOX_EMPTY;
    }

    return draw_blit_entry(buf, buf_w, buf_h, x, y,
                           asset, entry, color, -1);
}
