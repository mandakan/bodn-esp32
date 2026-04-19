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

draw_bbox_t draw_waveform(uint16_t *buf, int buf_w, int buf_h,
                          int x, int y, int w, int h,
                          const int16_t *samples, int n_samples,
                          uint16_t fg, uint16_t bg, int gain_q8) {
    /* Clip to framebuffer bounds. */
    int x0 = x, y0 = y, x1 = x + w, y1 = y + h;
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 > buf_w) x1 = buf_w;
    if (y1 > buf_h) y1 = buf_h;
    if (x1 <= x0 || y1 <= y0 || n_samples <= 0) return DRAW_BBOX_EMPTY;

    int cw = x1 - x0;
    int ch = y1 - y0;

    /* Fill background. */
    for (int row = y0; row < y1; row++) {
        uint16_t *line = buf + row * buf_w + x0;
        for (int col = 0; col < cw; col++) line[col] = bg;
    }

    /* Previous sample's y-pixel, used to connect consecutive samples with a
     * vertical run so the trace looks continuous even where the waveform is
     * steep.  Start at the centre. */
    int mid = y0 + ch / 2;
    int prev_py = mid;

    for (int col = 0; col < cw; col++) {
        /* Map column -> sample index.  Use ((col + clip offset) * n / w)
         * so the scope shows the same samples even after horizontal clip. */
        int src_col = col + (x0 - x);
        int si = (int)((long)src_col * n_samples / w);
        if (si < 0) si = 0;
        if (si >= n_samples) si = n_samples - 1;
        int32_t s = samples[si];
        s = (s * gain_q8) >> 8;
        if (s >  32767) s =  32767;
        if (s < -32768) s = -32768;
        /* Map sample -> y within rect.  Positive sample = above centre. */
        int py = mid - (int)((s * (ch / 2)) / 32768);
        if (py < y0) py = y0;
        if (py >= y1) py = y1 - 1;

        int top = py, bot = prev_py;
        if (top > bot) { int tmp = top; top = bot; bot = tmp; }
        if (col == 0) { top = py; bot = py; }

        uint16_t *colbase = buf + x0 + col;
        for (int row = top; row <= bot; row++) {
            colbase[row * buf_w] = fg;
        }
        prev_py = py;
    }

    return (draw_bbox_t){(int16_t)x0, (int16_t)y0, (int16_t)cw, (int16_t)ch};
}
