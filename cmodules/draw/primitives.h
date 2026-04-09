/*
 * primitives.h — Drawing primitives (filled shapes)
 *
 * Stubbed — implement as game modes need them.
 */

#ifndef DRAW_PRIMITIVES_H
#define DRAW_PRIMITIVES_H

#include "draw.h"

draw_bbox_t draw_fill_circle(uint16_t *buf, int buf_w, int buf_h,
                             int cx, int cy, int r, uint16_t color);

draw_bbox_t draw_fill_rrect(uint16_t *buf, int buf_w, int buf_h,
                            int x, int y, int w, int h, int r,
                            uint16_t color);

draw_bbox_t draw_fill_triangle(uint16_t *buf, int buf_w, int buf_h,
                               int x0, int y0, int x1, int y1,
                               int x2, int y2, uint16_t color);

#endif /* DRAW_PRIMITIVES_H */
