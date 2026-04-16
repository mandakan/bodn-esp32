// engine.h — NeoPixel pattern engine (FreeRTOS task + RMT)

#ifndef NEOPIXEL_ENGINE_H
#define NEOPIXEL_ENGINE_H

#include "neopixel_mod.h"

// Configuration passed from Python
typedef struct {
    int gpio_pin;       // GPIO for NeoPixel data line
} np_engine_config_t;

// Allocate state, configure RMT, start core 0 task.
// On success: sets *state_out and returns NULL.
// On failure: returns a static error string.
const char *engine_init(const np_engine_config_t *cfg, np_state_t **state_out);

// Stop task, release RMT, free state.
void engine_deinit(np_state_t *state);

#endif // NEOPIXEL_ENGINE_H
