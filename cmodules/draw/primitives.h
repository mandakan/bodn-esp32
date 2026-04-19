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

/* Render an oscilloscope-style waveform into an (x,y,w,h) rect of `buf`.
 * `samples` is an int16 PCM buffer (host endian) of length `n_samples`.
 * `gain_q8` is an 8.8 fixed-point amplitude multiplier (256 = unity, 512 = 2×).
 * Fills the rect with `bg` first, then draws `fg` pixels along the scope line
 * connecting adjacent samples vertically so the trace reads as continuous.
 * Colors are in framebuf RGB565 order (byte-swapped). */
draw_bbox_t draw_waveform(uint16_t *buf, int buf_w, int buf_h,
                          int x, int y, int w, int h,
                          const int16_t *samples, int n_samples,
                          uint16_t fg, uint16_t bg, int gain_q8);

#endif /* DRAW_PRIMITIVES_H */
