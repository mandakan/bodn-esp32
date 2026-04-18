// life.c — Game of Life step kernel.
//
// Ported from firmware/bodn/life_rules.py::step() + _mixed_color(). The Python
// implementation stays as the host-testable reference; this file mirrors its
// semantics exactly (same neighbour order, same palette snap, same events
// output) so test_life_rules.py continues to cover both paths.

#include "life.h"

static const int8_t NEIGHBOR_DX[8] = { -1, 0, 1, -1, 1, -1, 0, 1 };
static const int8_t NEIGHBOR_DY[8] = { -1, -1, -1, 0, 0, 1, 1, 1 };

// Average the RGB of live neighbours and return the nearest palette index
// (1-indexed, matching the cell-value convention). If there are no live
// neighbours, returns 1 — same behaviour as the Python reference.
static uint8_t mixed_colour(int r_sum, int g_sum, int b_sum, int n,
                             const uint8_t *palette, int pal_len) {
    if (n == 0) {
        return 1;
    }
    int mr = r_sum / n;
    int mg = g_sum / n;
    int mb = b_sum / n;

    int best = 0;
    int best_dist = 0x7FFFFFFF;
    for (int i = 0; i < pal_len; i++) {
        int dr = mr - palette[i * 3 + 0];
        int dg = mg - palette[i * 3 + 1];
        int db = mb - palette[i * 3 + 2];
        int dist = dr * dr + dg * dg + db * db;
        if (dist < best_dist) {
            best_dist = dist;
            best = i;
        }
    }
    return (uint8_t)(best + 1);
}

void life_step(
    const uint8_t *grid,
    uint8_t       *new_grid,
    int            w,
    int            h,
    uint16_t       birth_mask,
    uint16_t       survive_mask,
    int            wrap,
    const uint8_t *palette,
    int            pal_len,
    uint8_t       *births_out,
    int           *n_births,
    uint8_t       *deaths_out,
    int           *n_deaths
) {
    int bi = 0;
    int di = 0;
    int pal_max = pal_len - 1;

    for (int y = 0; y < h; y++) {
        int row = y * w;
        for (int x = 0; x < w; x++) {
            int idx = row + x;
            uint8_t alive = grid[idx];

            int r_sum = 0, g_sum = 0, b_sum = 0;
            int n = 0;

            for (int k = 0; k < 8; k++) {
                int nx = x + NEIGHBOR_DX[k];
                int ny = y + NEIGHBOR_DY[k];
                if (wrap) {
                    if (nx < 0)      nx += w;
                    else if (nx >= w) nx -= w;
                    if (ny < 0)      ny += h;
                    else if (ny >= h) ny -= h;
                } else {
                    if (nx < 0 || nx >= w || ny < 0 || ny >= h) continue;
                }
                uint8_t c = grid[ny * w + nx];
                if (c) {
                    n++;
                    int ci = c - 1;
                    if (ci > pal_max) ci = pal_max;
                    r_sum += palette[ci * 3 + 0];
                    g_sum += palette[ci * 3 + 1];
                    b_sum += palette[ci * 3 + 2];
                }
            }

            uint16_t bit = (uint16_t)(1u << n);

            if (alive) {
                if (survive_mask & bit) {
                    new_grid[idx] = alive;
                } else {
                    new_grid[idx] = 0;
                    deaths_out[di * 2 + 0] = (uint8_t)x;
                    deaths_out[di * 2 + 1] = (uint8_t)y;
                    di++;
                }
            } else {
                if (birth_mask & bit) {
                    new_grid[idx] = mixed_colour(r_sum, g_sum, b_sum, n,
                                                  palette, pal_len);
                    births_out[bi * 2 + 0] = (uint8_t)x;
                    births_out[bi * 2 + 1] = (uint8_t)y;
                    bi++;
                } else {
                    new_grid[idx] = 0;
                }
            }
        }
    }

    *n_births = bi;
    *n_deaths = di;
}
