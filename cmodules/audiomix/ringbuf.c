// ringbuf.c — lock-free SPSC ring buffer
//
// Single producer (core 0 / Python) writes PCM data.
// Single consumer (core 1 / mixer) reads it.
// No locks needed — the classic index-based SPSC pattern with volatile
// indices and power-of-2 masking.

#include <string.h>
#include <stdlib.h>

#include "ringbuf.h"

// PSRAM allocation via ESP-IDF heap_caps
#include "esp_heap_caps.h"
#define RB_MALLOC(sz) heap_caps_malloc(sz, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT)
#define RB_FREE(p)    heap_caps_free(p)

void ringbuf_init(audiomix_ringbuf_t *rb, uint32_t size) {
    rb->buf = RB_MALLOC(size);
    rb->size = size;
    rb->wr = 0;
    rb->rd = 0;
}

void ringbuf_deinit(audiomix_ringbuf_t *rb) {
    if (rb->buf) {
        RB_FREE(rb->buf);
        rb->buf = NULL;
    }
    rb->size = 0;
    rb->wr = 0;
    rb->rd = 0;
}

void ringbuf_reset(audiomix_ringbuf_t *rb) {
    rb->wr = 0;
    rb->rd = 0;
}

uint32_t ringbuf_available(const audiomix_ringbuf_t *rb) {
    uint32_t wr = rb->wr;
    uint32_t rd = rb->rd;
    return (wr - rd) & (rb->size - 1);
}

uint32_t ringbuf_free(const audiomix_ringbuf_t *rb) {
    // Reserve 1 byte to distinguish full from empty
    return rb->size - 1 - ringbuf_available(rb);
}

uint32_t ringbuf_write(audiomix_ringbuf_t *rb, const uint8_t *data, uint32_t len) {
    uint32_t avail = ringbuf_free(rb);
    if (len > avail) len = avail;
    if (len == 0) return 0;

    uint32_t mask = rb->size - 1;
    uint32_t wr = rb->wr;

    // First chunk: from wr to end of buffer (or len, whichever is smaller)
    uint32_t pos = wr & mask;
    uint32_t first = rb->size - pos;
    if (first > len) first = len;
    memcpy(rb->buf + pos, data, first);

    // Second chunk: wrap around to start
    uint32_t second = len - first;
    if (second > 0) {
        memcpy(rb->buf, data + first, second);
    }

    // Publish write index (producer side)
    rb->wr = wr + len;
    return len;
}

uint32_t ringbuf_read(audiomix_ringbuf_t *rb, uint8_t *dst, uint32_t len) {
    uint32_t avail = ringbuf_available(rb);
    if (len > avail) len = avail;
    if (len == 0) return 0;

    uint32_t mask = rb->size - 1;
    uint32_t rd = rb->rd;

    // First chunk
    uint32_t pos = rd & mask;
    uint32_t first = rb->size - pos;
    if (first > len) first = len;
    memcpy(dst, rb->buf + pos, first);

    // Second chunk (wrap)
    uint32_t second = len - first;
    if (second > 0) {
        memcpy(dst + first, rb->buf, second);
    }

    // Publish read index (consumer side)
    rb->rd = rd + len;
    return len;
}
