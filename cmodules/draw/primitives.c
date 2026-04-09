/*
 * primitives.c — Drawing primitives (filled shapes)
 *
 * Stubbed — implement as game modes need them.
 */

#include "primitives.h"

draw_bbox_t draw_fill_circle(uint16_t *buf, int buf_w, int buf_h,
                             int cx, int cy, int r, uint16_t color) {
    (void)buf; (void)buf_w; (void)buf_h;
    (void)cx; (void)cy; (void)r; (void)color;
    return DRAW_BBOX_EMPTY;
}

draw_bbox_t draw_fill_rrect(uint16_t *buf, int buf_w, int buf_h,
                            int x, int y, int w, int h, int r,
                            uint16_t color) {
    (void)buf; (void)buf_w; (void)buf_h;
    (void)x; (void)y; (void)w; (void)h; (void)r; (void)color;
    return DRAW_BBOX_EMPTY;
}

draw_bbox_t draw_fill_triangle(uint16_t *buf, int buf_w, int buf_h,
                               int x0, int y0, int x1, int y1,
                               int x2, int y2, uint16_t color) {
    (void)buf; (void)buf_w; (void)buf_h;
    (void)x0; (void)y0; (void)x1; (void)y1; (void)x2; (void)y2; (void)color;
    return DRAW_BBOX_EMPTY;
}
