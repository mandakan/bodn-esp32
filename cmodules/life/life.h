// life.h — Game of Life step kernel (pure C, no MicroPython dependencies).
//
// One generation: evolves `grid` into `new_grid` using totalistic birth/survive
// rules encoded as bitmasks (bit N = alive with N live neighbours). Born cells
// take the nearest palette colour to the average RGB of their live neighbours.
// Writes changed coordinates to the caller-supplied events buffers as packed
// (x, y) byte pairs.

#ifndef BODN_LIFE_H
#define BODN_LIFE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// Evolve one generation.
//
//   grid       : input grid of w*h cells (0 = dead, 1..pal_len = alive+colour)
//   new_grid   : output grid of w*h cells (caller-allocated, same size)
//   w, h       : grid dimensions (both must fit in uint8_t — <= 255)
//   birth_mask : bit N set => cell born with N live neighbours
//   survive_mask : bit N set => live cell survives with N live neighbours
//   wrap       : non-zero => edges wrap (toroidal)
//   palette    : packed R,G,B bytes; 3 * pal_len bytes long
//   pal_len    : number of palette entries (>= 1)
//   births_out : buffer receiving (x, y) byte pairs for each birth
//   n_births   : on return, number of birth events written
//   deaths_out : buffer receiving (x, y) byte pairs for each death
//   n_deaths   : on return, number of death events written
//
// births_out and deaths_out must each have capacity >= 2 * w * h bytes.
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
);

#ifdef __cplusplus
}
#endif

#endif
