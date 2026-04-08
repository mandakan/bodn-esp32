// audiomix.c — MicroPython bindings for the Bodn audio mixer
//
// Registers the _audiomix module and exposes Python-callable functions
// that control the core 1 mix task.

#include "py/runtime.h"
#include "py/obj.h"

#include "audiomix.h"
#include "mixer.h"
#include "ringbuf.h"
#include "tonegen.h"

// Global state — allocated by init(), freed by deinit()
audiomix_state_t *audiomix_state = NULL;

// ---------------------------------------------------------------------------
// _audiomix.init(bck, ws, din, amp, rate=16000, ibuf=16384)
// ---------------------------------------------------------------------------

static mp_obj_t audiomix_init(size_t n_args, const mp_obj_t *pos_args,
                               mp_map_t *kw_args) {
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_bck,  MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_ws,   MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_din,  MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_amp,  MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_rate, MP_ARG_KW_ONLY | MP_ARG_INT,  {.u_int = 16000} },
        { MP_QSTR_ibuf, MP_ARG_KW_ONLY | MP_ARG_INT,  {.u_int = 16384} },
    };

    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args,
                     MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    if (audiomix_state != NULL) {
        // Re-init after soft reset — clean up the old instance
        mixer_deinit(audiomix_state);
        audiomix_state = NULL;
    }

    mixer_config_t cfg = {
        .pin_bck  = args[0].u_int,
        .pin_ws   = args[1].u_int,
        .pin_din  = args[2].u_int,
        .pin_amp  = args[3].u_int,
        .rate     = args[4].u_int,
        .ibuf     = args[5].u_int,
    };

    const char *err = mixer_init(&cfg, &audiomix_state);
    if (err != NULL) {
        mp_raise_msg_varg(&mp_type_RuntimeError,
                          MP_ERROR_TEXT("audiomix: %s"), err);
    }

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(audiomix_init_obj, 0, audiomix_init);

// ---------------------------------------------------------------------------
// _audiomix.deinit()
// ---------------------------------------------------------------------------

static mp_obj_t audiomix_deinit(void) {
    if (audiomix_state != NULL) {
        mixer_deinit(audiomix_state);
        audiomix_state = NULL;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(audiomix_deinit_obj, audiomix_deinit);

// ---------------------------------------------------------------------------
// _audiomix.set_volume(percent)
// ---------------------------------------------------------------------------

static mp_obj_t audiomix_set_volume(mp_obj_t vol_obj) {
    if (audiomix_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    int vol = mp_obj_get_int(vol_obj);
    if (vol < 0) vol = 0;
    if (vol > 100) vol = 100;
    audiomix_state->master_volume = vol;
    audiomix_state->vol_mult = vol * 655;  // fixed-point 16.16
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(audiomix_set_volume_obj, audiomix_set_volume);

// ---------------------------------------------------------------------------
// _audiomix.get_volume() -> int
// ---------------------------------------------------------------------------

static mp_obj_t audiomix_get_volume(void) {
    if (audiomix_state == NULL) {
        return mp_obj_new_int(0);
    }
    return mp_obj_new_int(audiomix_state->master_volume);
}
static MP_DEFINE_CONST_FUN_OBJ_0(audiomix_get_volume_obj, audiomix_get_volume);

// ---------------------------------------------------------------------------
// _audiomix.voice_tone(idx, freq_hz, duration_ms, wave)
// ---------------------------------------------------------------------------

static mp_obj_t audiomix_voice_tone(size_t n_args, const mp_obj_t *args) {
    if (audiomix_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    int idx = mp_obj_get_int(args[0]);
    if (idx < 0 || idx >= AUDIOMIX_NUM_VOICES) {
        mp_raise_ValueError(MP_ERROR_TEXT("bad voice index"));
    }

    uint32_t freq     = mp_obj_get_int(args[1]);
    uint32_t dur_ms   = mp_obj_get_int(args[2]);
    uint32_t wave     = mp_obj_get_int(args[3]);

    audiomix_voice_t *v = &audiomix_state->voices[idx];
    // Write payload fields first
    v->tone_freq = freq;
    v->tone_samples_left = (audiomix_state->sample_rate * dur_ms) / 1000;
    v->tone_phase = 0;
    v->tone_wave = wave;
    v->loop = 0;
    v->fade_in = 1;
    v->stop_req = 0;
    audiomix_state->seq_counter++;
    v->start_seq = audiomix_state->seq_counter;
    // Mark manual trigger for anti-double logic
    audiomix_state->clock.manual_trigger_sample[idx] =
        audiomix_state->clock.total_samples;
    // Commit
    v->source_type = SRC_TONE;

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(audiomix_voice_tone_obj, 4, 4,
                                            audiomix_voice_tone);

// ---------------------------------------------------------------------------
// _audiomix.voice_sequence(idx, packed_bytes)
// ---------------------------------------------------------------------------

static mp_obj_t audiomix_voice_sequence(mp_obj_t idx_obj, mp_obj_t data_obj) {
    if (audiomix_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    int idx = mp_obj_get_int(idx_obj);
    if (idx < 0 || idx >= AUDIOMIX_NUM_VOICES) {
        mp_raise_ValueError(MP_ERROR_TEXT("bad voice index"));
    }

    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(data_obj, &bufinfo, MP_BUFFER_READ);

    uint32_t n_steps = bufinfo.len / AUDIOMIX_SEQ_STEP_SIZE;
    if (n_steps == 0 || n_steps > AUDIOMIX_SEQ_MAX_STEPS) {
        mp_raise_ValueError(MP_ERROR_TEXT("bad sequence length"));
    }

    audiomix_voice_t *v = &audiomix_state->voices[idx];
    uint32_t copy_len = n_steps * AUDIOMIX_SEQ_STEP_SIZE;
    memcpy(v->seq_buf, bufinfo.buf, copy_len);
    v->seq_n_steps = n_steps;
    v->seq_current = 0;
    v->seq_samples_left = 0;
    v->seq_phase = 0;
    v->loop = 0;
    v->fade_in = 1;
    v->stop_req = 0;
    audiomix_state->seq_counter++;
    v->start_seq = audiomix_state->seq_counter;
    // Commit
    v->source_type = SRC_SEQUENCE;

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(audiomix_voice_sequence_obj,
                                  audiomix_voice_sequence);

// ---------------------------------------------------------------------------
// _audiomix.voice_start_stream(idx, loop)
// ---------------------------------------------------------------------------

static mp_obj_t audiomix_voice_start_stream(mp_obj_t idx_obj, mp_obj_t loop_obj) {
    if (audiomix_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    int idx = mp_obj_get_int(idx_obj);
    if (idx < 0 || idx >= AUDIOMIX_NUM_VOICES) {
        mp_raise_ValueError(MP_ERROR_TEXT("bad voice index"));
    }

    audiomix_voice_t *v = &audiomix_state->voices[idx];
    // Stop any current playback first
    v->source_type = SRC_NONE;
    ringbuf_reset(&v->ringbuf);
    v->eof = 0;
    v->loop = mp_obj_is_true(loop_obj) ? 1 : 0;
    v->fade_in = 1;
    v->stop_req = 0;
    audiomix_state->seq_counter++;
    v->start_seq = audiomix_state->seq_counter;
    // Commit
    v->source_type = SRC_RINGBUF;

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(audiomix_voice_start_stream_obj,
                                  audiomix_voice_start_stream);

// ---------------------------------------------------------------------------
// _audiomix.voice_feed(idx, buf, n) -> int
// ---------------------------------------------------------------------------

static mp_obj_t audiomix_voice_feed(mp_obj_t idx_obj, mp_obj_t buf_obj,
                                     mp_obj_t n_obj) {
    if (audiomix_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    int idx = mp_obj_get_int(idx_obj);
    if (idx < 0 || idx >= AUDIOMIX_NUM_VOICES) {
        mp_raise_ValueError(MP_ERROR_TEXT("bad voice index"));
    }

    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(buf_obj, &bufinfo, MP_BUFFER_READ);
    uint32_t n = mp_obj_get_int(n_obj);
    if (n > bufinfo.len) n = bufinfo.len;

    // Release GIL during memcpy into ring buffer
    MP_THREAD_GIL_EXIT();
    uint32_t written = ringbuf_write(&audiomix_state->voices[idx].ringbuf,
                                      bufinfo.buf, n);
    MP_THREAD_GIL_ENTER();

    return mp_obj_new_int(written);
}
static MP_DEFINE_CONST_FUN_OBJ_3(audiomix_voice_feed_obj, audiomix_voice_feed);

// ---------------------------------------------------------------------------
// _audiomix.voice_eof(idx)
// ---------------------------------------------------------------------------

static mp_obj_t audiomix_voice_eof(mp_obj_t idx_obj) {
    if (audiomix_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    int idx = mp_obj_get_int(idx_obj);
    if (idx < 0 || idx >= AUDIOMIX_NUM_VOICES) {
        mp_raise_ValueError(MP_ERROR_TEXT("bad voice index"));
    }
    audiomix_state->voices[idx].eof = 1;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(audiomix_voice_eof_obj, audiomix_voice_eof);

// ---------------------------------------------------------------------------
// _audiomix.voice_play_buffer(idx, buf, n_bytes, loop)
// ---------------------------------------------------------------------------

static mp_obj_t audiomix_voice_play_buffer(size_t n_args, const mp_obj_t *args) {
    if (audiomix_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    int idx = mp_obj_get_int(args[0]);
    if (idx < 0 || idx >= AUDIOMIX_NUM_VOICES) {
        mp_raise_ValueError(MP_ERROR_TEXT("bad voice index"));
    }

    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(args[1], &bufinfo, MP_BUFFER_READ);
    uint32_t n_bytes = mp_obj_get_int(args[2]);
    if (n_bytes > bufinfo.len) n_bytes = bufinfo.len;
    bool loop = mp_obj_is_true(args[3]);

    audiomix_voice_t *v = &audiomix_state->voices[idx];
    // Write payload first
    v->buf_ptr = bufinfo.buf;
    v->buf_len = n_bytes;
    v->buf_pos = 0;
    v->loop = loop ? 1 : 0;
    v->fade_in = 1;
    v->stop_req = 0;
    // Mark manual trigger for anti-double logic
    audiomix_state->clock.manual_trigger_sample[idx] =
        audiomix_state->clock.total_samples;
    audiomix_state->seq_counter++;
    v->start_seq = audiomix_state->seq_counter;
    // Commit
    v->source_type = SRC_BUFFER;

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(audiomix_voice_play_buffer_obj, 4, 4,
                                            audiomix_voice_play_buffer);

// ---------------------------------------------------------------------------
// _audiomix.voice_stop(idx)
// ---------------------------------------------------------------------------

static mp_obj_t audiomix_voice_stop(mp_obj_t idx_obj) {
    if (audiomix_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    int idx = mp_obj_get_int(idx_obj);
    if (idx < 0 || idx >= AUDIOMIX_NUM_VOICES) {
        mp_raise_ValueError(MP_ERROR_TEXT("bad voice index"));
    }
    audiomix_state->voices[idx].stop_req = 1;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(audiomix_voice_stop_obj, audiomix_voice_stop);

// ---------------------------------------------------------------------------
// _audiomix.voice_active(idx) -> bool
// ---------------------------------------------------------------------------

static mp_obj_t audiomix_voice_active(mp_obj_t idx_obj) {
    if (audiomix_state == NULL) {
        return mp_const_false;
    }
    int idx = mp_obj_get_int(idx_obj);
    if (idx < 0 || idx >= AUDIOMIX_NUM_VOICES) {
        return mp_const_false;
    }
    return mp_obj_new_bool(
        audiomix_state->voices[idx].source_type != SRC_NONE);
}
static MP_DEFINE_CONST_FUN_OBJ_1(audiomix_voice_active_obj,
                                  audiomix_voice_active);

// ---------------------------------------------------------------------------
// _audiomix.voice_set_gain(idx, gain_mult)
// ---------------------------------------------------------------------------

static mp_obj_t audiomix_voice_set_gain(mp_obj_t idx_obj, mp_obj_t gain_obj) {
    if (audiomix_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    int idx = mp_obj_get_int(idx_obj);
    if (idx < 0 || idx >= AUDIOMIX_NUM_VOICES) {
        mp_raise_ValueError(MP_ERROR_TEXT("bad voice index"));
    }
    audiomix_state->voices[idx].gain = mp_obj_get_int(gain_obj);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(audiomix_voice_set_gain_obj,
                                  audiomix_voice_set_gain);

// ---------------------------------------------------------------------------
// _audiomix.ringbuf_space(idx) -> int
// ---------------------------------------------------------------------------

static mp_obj_t audiomix_ringbuf_space(mp_obj_t idx_obj) {
    if (audiomix_state == NULL) {
        return mp_obj_new_int(0);
    }
    int idx = mp_obj_get_int(idx_obj);
    if (idx < 0 || idx >= AUDIOMIX_NUM_VOICES) {
        return mp_obj_new_int(0);
    }
    return mp_obj_new_int(
        ringbuf_free(&audiomix_state->voices[idx].ringbuf));
}
static MP_DEFINE_CONST_FUN_OBJ_1(audiomix_ringbuf_space_obj,
                                  audiomix_ringbuf_space);

// ---------------------------------------------------------------------------
// Step clock API
// ---------------------------------------------------------------------------

// _audiomix.clock_start(bpm, n_steps)
static mp_obj_t audiomix_clock_start(mp_obj_t bpm_obj, mp_obj_t steps_obj) {
    if (audiomix_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    seq_clock_t *clk = &audiomix_state->clock;
    int bpm = mp_obj_get_int(bpm_obj);
    int n = mp_obj_get_int(steps_obj);
    if (bpm < 1) bpm = 1;
    if (n < 1) n = 1;
    if (n > SEQ_MAX_STEPS) n = SEQ_MAX_STEPS;

    clk->bpm = bpm;
    clk->n_steps = n;
    // Each step = one 8th note = 60/(bpm*2) seconds
    clk->samples_per_step = audiomix_state->sample_rate * 60 / (bpm * 2);
    clk->sample_count = 0;
    clk->current_step = n - 1;  // will advance to 0 on first tick
    clk->playing = 1;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(audiomix_clock_start_obj, audiomix_clock_start);

// _audiomix.clock_stop()
static mp_obj_t audiomix_clock_stop(void) {
    if (audiomix_state != NULL) {
        audiomix_state->clock.playing = 0;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(audiomix_clock_stop_obj, audiomix_clock_stop);

// _audiomix.clock_set_bpm(bpm)
static mp_obj_t audiomix_clock_set_bpm(mp_obj_t bpm_obj) {
    if (audiomix_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    seq_clock_t *clk = &audiomix_state->clock;
    int bpm = mp_obj_get_int(bpm_obj);
    if (bpm < 1) bpm = 1;
    clk->bpm = bpm;
    clk->samples_per_step = audiomix_state->sample_rate * 60 / (bpm * 2);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(audiomix_clock_set_bpm_obj, audiomix_clock_set_bpm);

// _audiomix.clock_set_steps(n_steps)
static mp_obj_t audiomix_clock_set_steps(mp_obj_t steps_obj) {
    if (audiomix_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    int n = mp_obj_get_int(steps_obj);
    if (n < 1) n = 1;
    if (n > SEQ_MAX_STEPS) n = SEQ_MAX_STEPS;
    audiomix_state->clock.n_steps = n;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(audiomix_clock_set_steps_obj, audiomix_clock_set_steps);

// _audiomix.clock_get_step() -> int
static mp_obj_t audiomix_clock_get_step(void) {
    if (audiomix_state == NULL) return mp_obj_new_int(0);
    return mp_obj_new_int(audiomix_state->clock.current_step);
}
static MP_DEFINE_CONST_FUN_OBJ_0(audiomix_clock_get_step_obj, audiomix_clock_get_step);

// _audiomix.clock_set_perc(step, perc_mask)
// perc_mask: bits 0-4 = tracks 0-4
static mp_obj_t audiomix_clock_set_perc(mp_obj_t step_obj, mp_obj_t mask_obj) {
    if (audiomix_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    int step = mp_obj_get_int(step_obj);
    if (step < 0 || step >= SEQ_MAX_STEPS) {
        mp_raise_ValueError(MP_ERROR_TEXT("bad step"));
    }
    audiomix_state->clock.steps[step].perc_mask = mp_obj_get_int(mask_obj) & 0x1F;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(audiomix_clock_set_perc_obj, audiomix_clock_set_perc);

// _audiomix.clock_set_melody(step, freq_hz)
// freq_hz: 0 = off, >0 = note frequency
static mp_obj_t audiomix_clock_set_melody(mp_obj_t step_obj, mp_obj_t freq_obj) {
    if (audiomix_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    int step = mp_obj_get_int(step_obj);
    if (step < 0 || step >= SEQ_MAX_STEPS) {
        mp_raise_ValueError(MP_ERROR_TEXT("bad step"));
    }
    audiomix_state->clock.steps[step].melody_freq = mp_obj_get_int(freq_obj);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(audiomix_clock_set_melody_obj, audiomix_clock_set_melody);

// _audiomix.clock_set_perc_buffer(track, buf, n_bytes)
// Register a pre-loaded PCM buffer for a percussion track
static mp_obj_t audiomix_clock_set_perc_buffer(mp_obj_t track_obj,
                                                mp_obj_t buf_obj,
                                                mp_obj_t n_obj) {
    if (audiomix_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    int track = mp_obj_get_int(track_obj);
    if (track < 0 || track >= SEQ_MAX_PERC_TRACKS) {
        mp_raise_ValueError(MP_ERROR_TEXT("bad track"));
    }
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(buf_obj, &bufinfo, MP_BUFFER_READ);
    uint32_t n = mp_obj_get_int(n_obj);
    if (n > bufinfo.len) n = bufinfo.len;

    seq_perc_track_t *pt = &audiomix_state->clock.perc_tracks[track];
    pt->buf_ptr = bufinfo.buf;
    pt->buf_len = n;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_3(audiomix_clock_set_perc_buffer_obj,
                                  audiomix_clock_set_perc_buffer);

// _audiomix.clock_set_melody_config(duration_ms, wave)
static mp_obj_t audiomix_clock_set_melody_config(mp_obj_t dur_obj, mp_obj_t wave_obj) {
    if (audiomix_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    audiomix_state->clock.melody_duration_ms = mp_obj_get_int(dur_obj);
    audiomix_state->clock.melody_wave = mp_obj_get_int(wave_obj);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(audiomix_clock_set_melody_config_obj,
                                  audiomix_clock_set_melody_config);

// _audiomix.clock_clear_grid()
static mp_obj_t audiomix_clock_clear_grid(void) {
    if (audiomix_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    seq_clock_t *clk = &audiomix_state->clock;
    for (int i = 0; i < SEQ_MAX_STEPS; i++) {
        clk->steps[i].perc_mask = 0;
        clk->steps[i].melody_freq = 0;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(audiomix_clock_clear_grid_obj, audiomix_clock_clear_grid);

// ---------------------------------------------------------------------------
// _audiomix.stats() -> dict
// ---------------------------------------------------------------------------

static mp_obj_t audiomix_stats(void) {
    if (audiomix_state == NULL) {
        return mp_obj_new_dict(0);
    }
    audiomix_state_t *s = audiomix_state;
    mp_obj_dict_t *d = MP_OBJ_TO_PTR(mp_obj_new_dict(10));

    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_mix_calls),
        mp_obj_new_int(s->mix_calls));
    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_mix_us_last),
        mp_obj_new_int(s->mix_us_last));
    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_mix_us_max),
        mp_obj_new_int(s->mix_us_max));
    uint32_t avg = s->mix_avg_count ? s->mix_us_sum / s->mix_avg_count : 0;
    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_mix_us_avg),
        mp_obj_new_int(avg));
    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_underruns),
        mp_obj_new_int(s->underruns));
    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_active_voices),
        mp_obj_new_int(s->active_voices));
    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_stack_hwm),
        mp_obj_new_int(s->task_stack_hwm));
    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_volume),
        mp_obj_new_int(s->master_volume));
    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_sample_rate),
        mp_obj_new_int(s->sample_rate));
    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_dma_wait_us),
        mp_obj_new_int(s->dma_wait_us));

    // Per-voice ring buffer fill levels
    mp_obj_t rb_list = mp_obj_new_list(0, NULL);
    for (int i = 0; i < AUDIOMIX_NUM_VOICES; i++) {
        mp_obj_list_append(rb_list,
            mp_obj_new_int(ringbuf_available(&s->voices[i].ringbuf)));
    }
    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_ringbuf_fill),
        rb_list);

    return MP_OBJ_FROM_PTR(d);
}
static MP_DEFINE_CONST_FUN_OBJ_0(audiomix_stats_obj, audiomix_stats);

// ---------------------------------------------------------------------------
// _audiomix.reset_stats()
// ---------------------------------------------------------------------------

static mp_obj_t audiomix_reset_stats(void) {
    if (audiomix_state != NULL) {
        audiomix_state->mix_us_max = 0;
        audiomix_state->mix_us_sum = 0;
        audiomix_state->mix_avg_count = 0;
        audiomix_state->underruns = 0;
        audiomix_state->mix_calls = 0;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(audiomix_reset_stats_obj, audiomix_reset_stats);

// ---------------------------------------------------------------------------
// Module definition
// ---------------------------------------------------------------------------

static const mp_rom_map_elem_t audiomix_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__),           MP_ROM_QSTR(MP_QSTR__audiomix) },
    { MP_ROM_QSTR(MP_QSTR_init),               MP_ROM_PTR(&audiomix_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_deinit),             MP_ROM_PTR(&audiomix_deinit_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_volume),          MP_ROM_PTR(&audiomix_set_volume_obj) },
    { MP_ROM_QSTR(MP_QSTR_get_volume),          MP_ROM_PTR(&audiomix_get_volume_obj) },
    { MP_ROM_QSTR(MP_QSTR_voice_tone),          MP_ROM_PTR(&audiomix_voice_tone_obj) },
    { MP_ROM_QSTR(MP_QSTR_voice_sequence),      MP_ROM_PTR(&audiomix_voice_sequence_obj) },
    { MP_ROM_QSTR(MP_QSTR_voice_start_stream),  MP_ROM_PTR(&audiomix_voice_start_stream_obj) },
    { MP_ROM_QSTR(MP_QSTR_voice_feed),          MP_ROM_PTR(&audiomix_voice_feed_obj) },
    { MP_ROM_QSTR(MP_QSTR_voice_eof),           MP_ROM_PTR(&audiomix_voice_eof_obj) },
    { MP_ROM_QSTR(MP_QSTR_voice_play_buffer),   MP_ROM_PTR(&audiomix_voice_play_buffer_obj) },
    { MP_ROM_QSTR(MP_QSTR_voice_stop),          MP_ROM_PTR(&audiomix_voice_stop_obj) },
    { MP_ROM_QSTR(MP_QSTR_voice_active),        MP_ROM_PTR(&audiomix_voice_active_obj) },
    { MP_ROM_QSTR(MP_QSTR_voice_set_gain),      MP_ROM_PTR(&audiomix_voice_set_gain_obj) },
    { MP_ROM_QSTR(MP_QSTR_ringbuf_space),       MP_ROM_PTR(&audiomix_ringbuf_space_obj) },
    { MP_ROM_QSTR(MP_QSTR_stats),              MP_ROM_PTR(&audiomix_stats_obj) },
    { MP_ROM_QSTR(MP_QSTR_reset_stats),        MP_ROM_PTR(&audiomix_reset_stats_obj) },
    // Step clock
    { MP_ROM_QSTR(MP_QSTR_clock_start),        MP_ROM_PTR(&audiomix_clock_start_obj) },
    { MP_ROM_QSTR(MP_QSTR_clock_stop),         MP_ROM_PTR(&audiomix_clock_stop_obj) },
    { MP_ROM_QSTR(MP_QSTR_clock_set_bpm),      MP_ROM_PTR(&audiomix_clock_set_bpm_obj) },
    { MP_ROM_QSTR(MP_QSTR_clock_set_steps),    MP_ROM_PTR(&audiomix_clock_set_steps_obj) },
    { MP_ROM_QSTR(MP_QSTR_clock_get_step),     MP_ROM_PTR(&audiomix_clock_get_step_obj) },
    { MP_ROM_QSTR(MP_QSTR_clock_set_perc),     MP_ROM_PTR(&audiomix_clock_set_perc_obj) },
    { MP_ROM_QSTR(MP_QSTR_clock_set_melody),   MP_ROM_PTR(&audiomix_clock_set_melody_obj) },
    { MP_ROM_QSTR(MP_QSTR_clock_set_perc_buffer), MP_ROM_PTR(&audiomix_clock_set_perc_buffer_obj) },
    { MP_ROM_QSTR(MP_QSTR_clock_set_melody_config), MP_ROM_PTR(&audiomix_clock_set_melody_config_obj) },
    { MP_ROM_QSTR(MP_QSTR_clock_clear_grid),   MP_ROM_PTR(&audiomix_clock_clear_grid_obj) },
    // Constants for voice indices
    { MP_ROM_QSTR(MP_QSTR_V_MUSIC),             MP_ROM_INT(AUDIOMIX_V_MUSIC) },
    { MP_ROM_QSTR(MP_QSTR_V_SFX_BASE),          MP_ROM_INT(AUDIOMIX_V_SFX_BASE) },
    { MP_ROM_QSTR(MP_QSTR_V_SFX_END),           MP_ROM_INT(AUDIOMIX_V_SFX_END) },
    { MP_ROM_QSTR(MP_QSTR_V_UI),                MP_ROM_INT(AUDIOMIX_V_UI) },
    // Waveform type constants
    { MP_ROM_QSTR(MP_QSTR_WAVE_SQUARE),          MP_ROM_INT(AUDIOMIX_WAVE_SQUARE) },
    { MP_ROM_QSTR(MP_QSTR_WAVE_SINE),            MP_ROM_INT(AUDIOMIX_WAVE_SINE) },
    { MP_ROM_QSTR(MP_QSTR_WAVE_SAWTOOTH),        MP_ROM_INT(AUDIOMIX_WAVE_SAWTOOTH) },
    { MP_ROM_QSTR(MP_QSTR_WAVE_NOISE),           MP_ROM_INT(AUDIOMIX_WAVE_NOISE) },
};
static MP_DEFINE_CONST_DICT(audiomix_module_globals,
                             audiomix_module_globals_table);

const mp_obj_module_t audiomix_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&audiomix_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR__audiomix, audiomix_module);
