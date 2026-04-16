// neopixel_mod.c — MicroPython bindings for the NeoPixel pattern engine
//
// Registers the _neopixel module and exposes Python-callable functions
// that control the core 0 pattern engine task.

#include <string.h>

#include "py/runtime.h"
#include "py/obj.h"

#include "neopixel_mod.h"
#include "engine.h"

// Global state — allocated by init(), freed by deinit()
np_state_t *neopixel_state = NULL;

// ---------------------------------------------------------------------------
// _neopixel.init(pin=4)
// ---------------------------------------------------------------------------

static mp_obj_t neopixel_init(size_t n_args, const mp_obj_t *pos_args,
                               mp_map_t *kw_args) {
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_pin, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 4} },
    };

    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args,
                     MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    // Clean up previous instance (soft reboot)
    if (neopixel_state != NULL) {
        engine_deinit(neopixel_state);
        neopixel_state = NULL;
    }

    np_engine_config_t cfg = {
        .gpio_pin = args[0].u_int,
    };

    const char *err = engine_init(&cfg, &neopixel_state);
    if (err != NULL) {
        mp_raise_msg_varg(&mp_type_RuntimeError,
                          MP_ERROR_TEXT("neopixel: %s"), err);
    }

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(neopixel_init_obj, 0, neopixel_init);

// ---------------------------------------------------------------------------
// _neopixel.deinit()
// ---------------------------------------------------------------------------

static mp_obj_t neopixel_deinit(void) {
    if (neopixel_state != NULL) {
        engine_deinit(neopixel_state);
        neopixel_state = NULL;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(neopixel_deinit_obj, neopixel_deinit);

// ---------------------------------------------------------------------------
// Helper: require state initialised
// ---------------------------------------------------------------------------

static inline np_state_t *require_state(void) {
    if (neopixel_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    return neopixel_state;
}

// ---------------------------------------------------------------------------
// _neopixel.zone_pattern(zone, pattern, speed=3,
//                        colour=(255,255,255), brightness=64, hue_offset=0)
// ---------------------------------------------------------------------------

static mp_obj_t neopixel_zone_pattern(size_t n_args, const mp_obj_t *pos_args,
                                       mp_map_t *kw_args) {
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_zone,       MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_pattern,    MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_speed,      MP_ARG_KW_ONLY | MP_ARG_INT,  {.u_int = 3} },
        { MP_QSTR_colour,     MP_ARG_KW_ONLY | MP_ARG_OBJ,  {.u_rom_obj = MP_ROM_NONE} },
        { MP_QSTR_brightness, MP_ARG_KW_ONLY | MP_ARG_INT,  {.u_int = 64} },
        { MP_QSTR_hue_offset, MP_ARG_KW_ONLY | MP_ARG_INT,  {.u_int = 0} },
    };

    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args,
                     MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    np_state_t *state = require_state();

    int zone = args[0].u_int;
    if (zone < 0 || zone >= NP_NUM_ZONES) {
        mp_raise_ValueError(MP_ERROR_TEXT("zone 0-2"));
    }

    int pattern = args[1].u_int;
    if (pattern < 0 || pattern >= NP_PAT_COUNT) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid pattern"));
    }

    np_zone_t *z = &state->zones[zone];

    // Parse colour tuple if provided
    if (args[3].u_obj != mp_const_none) {
        size_t len;
        mp_obj_t *items;
        mp_obj_get_array(args[3].u_obj, &len, &items);
        if (len >= 3) {
            z->r = (uint8_t)mp_obj_get_int(items[0]);
            z->g = (uint8_t)mp_obj_get_int(items[1]);
            z->b = (uint8_t)mp_obj_get_int(items[2]);
        }
    }

    z->speed = (uint8_t)args[2].u_int;
    z->brightness = (uint8_t)args[4].u_int;
    z->hue_offset = (uint8_t)args[5].u_int;
    // Set pattern last to avoid tearing
    z->pattern = (uint8_t)pattern;

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(neopixel_zone_pattern_obj, 2,
                                   neopixel_zone_pattern);

// ---------------------------------------------------------------------------
// _neopixel.zone_off(zone)
// ---------------------------------------------------------------------------

static mp_obj_t neopixel_zone_off(mp_obj_t zone_obj) {
    np_state_t *state = require_state();
    int zone = mp_obj_get_int(zone_obj);
    if (zone < 0 || zone >= NP_NUM_ZONES) return mp_const_none;
    state->zones[zone].pattern = NP_PAT_OFF;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(neopixel_zone_off_obj, neopixel_zone_off);

// ---------------------------------------------------------------------------
// _neopixel.zone_brightness(zone, brightness)
// ---------------------------------------------------------------------------

static mp_obj_t neopixel_zone_brightness(mp_obj_t zone_obj,
                                          mp_obj_t bright_obj) {
    np_state_t *state = require_state();
    int zone = mp_obj_get_int(zone_obj);
    if (zone < 0 || zone >= NP_NUM_ZONES) return mp_const_none;
    state->zones[zone].brightness = (uint8_t)mp_obj_get_int(bright_obj);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(neopixel_zone_brightness_obj,
                                  neopixel_zone_brightness);

// ---------------------------------------------------------------------------
// _neopixel.set_pixel(index, r, g, b)
// ---------------------------------------------------------------------------

static mp_obj_t neopixel_set_pixel(size_t n_args, const mp_obj_t *args) {
    np_state_t *state = require_state();
    int idx = mp_obj_get_int(args[0]);
    if (idx < 0 || idx >= NP_NUM_LEDS) return mp_const_none;

    uint8_t r = (uint8_t)mp_obj_get_int(args[1]);
    uint8_t g = (uint8_t)mp_obj_get_int(args[2]);
    uint8_t b = (uint8_t)mp_obj_get_int(args[3]);

    int off = idx * 3;
    state->overrides.rgb[off + 0] = g;  // GRB order
    state->overrides.rgb[off + 1] = r;
    state->overrides.rgb[off + 2] = b;
    // Set mask bit
    state->overrides.mask[idx >> 3] |= (1 << (idx & 7));

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(neopixel_set_pixel_obj, 4, 4,
                                             neopixel_set_pixel);

// ---------------------------------------------------------------------------
// _neopixel.set_pixels(start, data) — bulk set from bytes(r,g,b,...)
// ---------------------------------------------------------------------------

static mp_obj_t neopixel_set_pixels(mp_obj_t start_obj, mp_obj_t data_obj) {
    np_state_t *state = require_state();
    int start = mp_obj_get_int(start_obj);

    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(data_obj, &bufinfo, MP_BUFFER_READ);

    const uint8_t *data = bufinfo.buf;
    int n_pixels = bufinfo.len / 3;

    for (int i = 0; i < n_pixels; i++) {
        int idx = start + i;
        if (idx < 0 || idx >= NP_NUM_LEDS) continue;

        int off = idx * 3;
        int src = i * 3;
        state->overrides.rgb[off + 0] = data[src + 1];  // G
        state->overrides.rgb[off + 1] = data[src + 0];  // R
        state->overrides.rgb[off + 2] = data[src + 2];  // B
        state->overrides.mask[idx >> 3] |= (1 << (idx & 7));
    }

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(neopixel_set_pixels_obj, neopixel_set_pixels);

// ---------------------------------------------------------------------------
// _neopixel.clear_pixel(index)
// ---------------------------------------------------------------------------

static mp_obj_t neopixel_clear_pixel(mp_obj_t idx_obj) {
    np_state_t *state = require_state();
    int idx = mp_obj_get_int(idx_obj);
    if (idx < 0 || idx >= NP_NUM_LEDS) return mp_const_none;
    state->overrides.mask[idx >> 3] &= ~(1 << (idx & 7));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(neopixel_clear_pixel_obj,
                                  neopixel_clear_pixel);

// ---------------------------------------------------------------------------
// _neopixel.clear_pixels(start, count)
// ---------------------------------------------------------------------------

static mp_obj_t neopixel_clear_pixels(mp_obj_t start_obj, mp_obj_t count_obj) {
    np_state_t *state = require_state();
    int start = mp_obj_get_int(start_obj);
    int count = mp_obj_get_int(count_obj);
    for (int i = start; i < start + count && i < NP_NUM_LEDS; i++) {
        if (i >= 0) {
            state->overrides.mask[i >> 3] &= ~(1 << (i & 7));
        }
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(neopixel_clear_pixels_obj,
                                  neopixel_clear_pixels);

// ---------------------------------------------------------------------------
// _neopixel.clear_all_overrides()
// ---------------------------------------------------------------------------

static mp_obj_t neopixel_clear_all_overrides(void) {
    np_state_t *state = require_state();
    memset((void *)state->overrides.mask, 0, NP_OVERRIDE_BITMAP_SIZE);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(neopixel_clear_all_overrides_obj,
                                  neopixel_clear_all_overrides);

// ---------------------------------------------------------------------------
// _neopixel.set_override(mode, r=0, g=0, b=0)
// ---------------------------------------------------------------------------

static mp_obj_t neopixel_set_override(size_t n_args, const mp_obj_t *pos_args,
                                       mp_map_t *kw_args) {
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_mode, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_r,    MP_ARG_KW_ONLY | MP_ARG_INT,  {.u_int = 0} },
        { MP_QSTR_g,    MP_ARG_KW_ONLY | MP_ARG_INT,  {.u_int = 0} },
        { MP_QSTR_b,    MP_ARG_KW_ONLY | MP_ARG_INT,  {.u_int = 0} },
    };

    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args,
                     MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    np_state_t *state = require_state();
    state->override_r = (uint8_t)args[1].u_int;
    state->override_g = (uint8_t)args[2].u_int;
    state->override_b = (uint8_t)args[3].u_int;
    // Set mode last to avoid tearing
    state->override_mode = (uint8_t)args[0].u_int;

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(neopixel_set_override_obj, 1,
                                   neopixel_set_override);

// ---------------------------------------------------------------------------
// _neopixel.clear_override()
// ---------------------------------------------------------------------------

static mp_obj_t neopixel_clear_override(void) {
    np_state_t *state = require_state();
    state->override_mode = NP_OVERRIDE_NONE;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(neopixel_clear_override_obj,
                                  neopixel_clear_override);

// ---------------------------------------------------------------------------
// _neopixel.pause() / resume()
// ---------------------------------------------------------------------------

static mp_obj_t neopixel_pause(void) {
    np_state_t *state = require_state();
    state->paused = 1;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(neopixel_pause_obj, neopixel_pause);

static mp_obj_t neopixel_resume(void) {
    np_state_t *state = require_state();
    state->paused = 0;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(neopixel_resume_obj, neopixel_resume);

// ---------------------------------------------------------------------------
// _neopixel.frame() -> int
// ---------------------------------------------------------------------------

static mp_obj_t neopixel_frame(void) {
    if (neopixel_state == NULL) return mp_obj_new_int(0);
    return mp_obj_new_int(neopixel_state->frame);
}
static MP_DEFINE_CONST_FUN_OBJ_0(neopixel_frame_obj, neopixel_frame);

// ---------------------------------------------------------------------------
// _neopixel.stats() -> dict
// ---------------------------------------------------------------------------

static mp_obj_t neopixel_stats(void) {
    if (neopixel_state == NULL) return mp_obj_new_dict(0);

    np_state_t *s = neopixel_state;
    mp_obj_dict_t *d = MP_OBJ_TO_PTR(mp_obj_new_dict(4));

    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_frame),
        mp_obj_new_int(s->frame));
    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_write_count),
        mp_obj_new_int(s->write_count));
    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_stack_hwm),
        mp_obj_new_int(s->task_stack_hwm));
    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_last_frame_us),
        mp_obj_new_int(s->last_frame_us));

    return MP_OBJ_FROM_PTR(d);
}
static MP_DEFINE_CONST_FUN_OBJ_0(neopixel_stats_obj, neopixel_stats);

// ---------------------------------------------------------------------------
// Module definition
// ---------------------------------------------------------------------------

static const mp_rom_map_elem_t neopixel_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__),           MP_ROM_QSTR(MP_QSTR__neopixel) },
    // Lifecycle
    { MP_ROM_QSTR(MP_QSTR_init),               MP_ROM_PTR(&neopixel_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_deinit),             MP_ROM_PTR(&neopixel_deinit_obj) },
    // Zone control
    { MP_ROM_QSTR(MP_QSTR_zone_pattern),       MP_ROM_PTR(&neopixel_zone_pattern_obj) },
    { MP_ROM_QSTR(MP_QSTR_zone_off),           MP_ROM_PTR(&neopixel_zone_off_obj) },
    { MP_ROM_QSTR(MP_QSTR_zone_brightness),    MP_ROM_PTR(&neopixel_zone_brightness_obj) },
    // Per-pixel overrides
    { MP_ROM_QSTR(MP_QSTR_set_pixel),          MP_ROM_PTR(&neopixel_set_pixel_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_pixels),         MP_ROM_PTR(&neopixel_set_pixels_obj) },
    { MP_ROM_QSTR(MP_QSTR_clear_pixel),        MP_ROM_PTR(&neopixel_clear_pixel_obj) },
    { MP_ROM_QSTR(MP_QSTR_clear_pixels),       MP_ROM_PTR(&neopixel_clear_pixels_obj) },
    { MP_ROM_QSTR(MP_QSTR_clear_all_overrides), MP_ROM_PTR(&neopixel_clear_all_overrides_obj) },
    // Session override
    { MP_ROM_QSTR(MP_QSTR_set_override),       MP_ROM_PTR(&neopixel_set_override_obj) },
    { MP_ROM_QSTR(MP_QSTR_clear_override),     MP_ROM_PTR(&neopixel_clear_override_obj) },
    // Pause / resume
    { MP_ROM_QSTR(MP_QSTR_pause),              MP_ROM_PTR(&neopixel_pause_obj) },
    { MP_ROM_QSTR(MP_QSTR_resume),             MP_ROM_PTR(&neopixel_resume_obj) },
    // Query
    { MP_ROM_QSTR(MP_QSTR_frame),              MP_ROM_PTR(&neopixel_frame_obj) },
    { MP_ROM_QSTR(MP_QSTR_stats),              MP_ROM_PTR(&neopixel_stats_obj) },
    // Pattern constants
    { MP_ROM_QSTR(MP_QSTR_PAT_OFF),            MP_ROM_INT(NP_PAT_OFF) },
    { MP_ROM_QSTR(MP_QSTR_PAT_SOLID),          MP_ROM_INT(NP_PAT_SOLID) },
    { MP_ROM_QSTR(MP_QSTR_PAT_RAINBOW),        MP_ROM_INT(NP_PAT_RAINBOW) },
    { MP_ROM_QSTR(MP_QSTR_PAT_PULSE),          MP_ROM_INT(NP_PAT_PULSE) },
    { MP_ROM_QSTR(MP_QSTR_PAT_CHASE),          MP_ROM_INT(NP_PAT_CHASE) },
    { MP_ROM_QSTR(MP_QSTR_PAT_SPARKLE),        MP_ROM_INT(NP_PAT_SPARKLE) },
    { MP_ROM_QSTR(MP_QSTR_PAT_BOUNCE),         MP_ROM_INT(NP_PAT_BOUNCE) },
    { MP_ROM_QSTR(MP_QSTR_PAT_WAVE),           MP_ROM_INT(NP_PAT_WAVE) },
    { MP_ROM_QSTR(MP_QSTR_PAT_SPLIT),          MP_ROM_INT(NP_PAT_SPLIT) },
    { MP_ROM_QSTR(MP_QSTR_PAT_FILL),           MP_ROM_INT(NP_PAT_FILL) },
    // Zone constants
    { MP_ROM_QSTR(MP_QSTR_ZONE_STICK_A),       MP_ROM_INT(NP_ZONE_STICK_A) },
    { MP_ROM_QSTR(MP_QSTR_ZONE_STICK_B),       MP_ROM_INT(NP_ZONE_STICK_B) },
    { MP_ROM_QSTR(MP_QSTR_ZONE_LID_RING),      MP_ROM_INT(NP_ZONE_LID_RING) },
    // Override constants
    { MP_ROM_QSTR(MP_QSTR_OVERRIDE_NONE),      MP_ROM_INT(NP_OVERRIDE_NONE) },
    { MP_ROM_QSTR(MP_QSTR_OVERRIDE_BLACK),     MP_ROM_INT(NP_OVERRIDE_BLACK) },
    { MP_ROM_QSTR(MP_QSTR_OVERRIDE_SOLID),     MP_ROM_INT(NP_OVERRIDE_SOLID) },
    { MP_ROM_QSTR(MP_QSTR_OVERRIDE_PULSE),     MP_ROM_INT(NP_OVERRIDE_PULSE) },
    { MP_ROM_QSTR(MP_QSTR_OVERRIDE_FADE),      MP_ROM_INT(NP_OVERRIDE_FADE) },
};
static MP_DEFINE_CONST_DICT(neopixel_module_globals,
                             neopixel_module_globals_table);

const mp_obj_module_t neopixel_cmod_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&neopixel_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR__neopixel, neopixel_cmod_module);
