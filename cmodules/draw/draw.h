/*
 * draw.h — Bodn Draw Format types and constants
 *
 * Unified binary format (.bdf) for bitmap fonts and sprite sheets.
 * Multi-bpp (1/2/4/8) with alpha blending into RGB565 framebuffers.
 */

#ifndef DRAW_H
#define DRAW_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

/* BDF file magic: 'B','D' stored little-endian → 0x4442 */
#define DRAW_MAGIC   0x4442
#define DRAW_VERSION 1

#define DRAW_TYPE_FONT        0
#define DRAW_TYPE_SPRITESHEET 1

/* Header flags */
#define DRAW_FLAG_COLOR  0x01  /* bit 0: RGB565 color data + alpha (vs alpha-only) */

/* ---------- On-disk structures (packed, little-endian) ---------- */

typedef struct __attribute__((packed)) {
    uint16_t magic;            /* 0x4442 ('BD' LE) */
    uint8_t  version;          /* 1 */
    uint8_t  type;             /* DRAW_TYPE_FONT or DRAW_TYPE_SPRITESHEET */
    uint8_t  bpp;              /* 1, 2, 4, or 8 */
    uint8_t  flags;            /* reserved, 0 */
    uint16_t num_entries;
    uint16_t max_width;
    uint16_t height;           /* line height (font) or max frame height (sprite) */
    uint16_t baseline;         /* fonts only; 0 for sprites */
    uint32_t bitmap_offset;    /* byte offset from file start to bitmap data */
    uint16_t reserved;         /* 0 */
} draw_header_t;

_Static_assert(sizeof(draw_header_t) == 20, "header must be 20 bytes");

typedef struct __attribute__((packed)) {
    uint32_t id;               /* Unicode codepoint (font) or frame id (sprite) */
    uint8_t  width;
    uint8_t  height;
    uint32_t byte_offset;      /* offset into bitmap data section */
} draw_index_entry_t;

_Static_assert(sizeof(draw_index_entry_t) == 10, "index entry must be 10 bytes");

/* ---------- Runtime asset handle ---------- */

typedef struct {
    const uint8_t            *data;     /* raw file bytes (Python-owned) */
    size_t                    data_len;
    const draw_header_t      *header;   /* == data */
    const draw_index_entry_t *index;    /* == data + sizeof(header) */
    const uint8_t            *bitmap;   /* == data + header->bitmap_offset */
} draw_asset_t;

/* Bounding box returned for dirty-rect tracking */
typedef struct {
    int16_t x, y, w, h;
} draw_bbox_t;

/* Sentinel: empty bounding box (nothing drawn) */
#define DRAW_BBOX_EMPTY ((draw_bbox_t){0, 0, 0, 0})

/* ---------- RGB565 byte-swap helpers ----------
 *
 * MicroPython framebuf.RGB565 stores pixels byte-swapped (big-endian wire
 * order in little-endian memory).  All colors arrive from Python already
 * swapped, so we swap before decomposing and after composing.
 */

static inline uint16_t draw_bswap16(uint16_t v) {
    return (v >> 8) | (v << 8);
}

static inline void draw_rgb565_decompose(uint16_t le, uint8_t *r, uint8_t *g, uint8_t *b) {
    uint16_t be = draw_bswap16(le);
    *r = (be >> 11) & 0x1F;
    *g = (be >> 5)  & 0x3F;
    *b =  be        & 0x1F;
}

static inline uint16_t draw_rgb565_compose(uint8_t r, uint8_t g, uint8_t b) {
    uint16_t be = ((uint16_t)r << 11) | ((uint16_t)g << 5) | b;
    return draw_bswap16(be);
}

#endif /* DRAW_H */
