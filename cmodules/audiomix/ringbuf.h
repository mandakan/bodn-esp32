// ringbuf.h — lock-free single-producer single-consumer ring buffer

#ifndef AUDIOMIX_RINGBUF_H
#define AUDIOMIX_RINGBUF_H

#include <stdint.h>

#include "audiomix.h"

// Allocate and initialise a ring buffer of the given size (must be power of 2).
void ringbuf_init(audiomix_ringbuf_t *rb, uint32_t size);

// Free ring buffer memory.
void ringbuf_deinit(audiomix_ringbuf_t *rb);

// Reset read/write indices (call only when both sides are idle).
void ringbuf_reset(audiomix_ringbuf_t *rb);

// Write up to `len` bytes into the ring buffer. Returns bytes actually written.
// Called from core 0 (Python / producer).
uint32_t ringbuf_write(audiomix_ringbuf_t *rb, const uint8_t *data, uint32_t len);

// Read up to `len` bytes from the ring buffer into `dst`.
// Returns bytes actually read. Called from core 1 (mixer / consumer).
uint32_t ringbuf_read(audiomix_ringbuf_t *rb, uint8_t *dst, uint32_t len);

// Return the number of bytes available to read.
uint32_t ringbuf_available(const audiomix_ringbuf_t *rb);

// Return the number of free bytes available for writing.
uint32_t ringbuf_free(const audiomix_ringbuf_t *rb);

#endif // AUDIOMIX_RINGBUF_H
