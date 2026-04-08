// mixer.h — core 1 mix task and I2S management

#ifndef AUDIOMIX_MIXER_H
#define AUDIOMIX_MIXER_H

#include "audiomix.h"

// I2S + pin configuration passed from Python
typedef struct {
    int pin_bck;
    int pin_ws;
    int pin_din;
    int pin_amp;
    int rate;
    int ibuf;
} mixer_config_t;

// Allocate state, configure I2S, start core 1 task.
// On success: sets *state_out and returns NULL.
// On failure: returns a static error string describing what failed.
const char *mixer_init(const mixer_config_t *cfg, audiomix_state_t **state_out);

// Stop core 1 task, release I2S, free state.
void mixer_deinit(audiomix_state_t *state);

#endif // AUDIOMIX_MIXER_H
