// mcpinput.c — MicroPython bindings for the MCP23017 native input module
//
// Registers the _mcpinput module and exposes Python-callable functions
// that control the core 0 scan task and provide I2C bus access.

#include "py/runtime.h"
#include "py/obj.h"

#include "mcpinput.h"
#include "scanner.h"

// Global state — allocated by init(), freed by deinit()
mcpinput_state_t *mcpinput_state = NULL;

// ---------------------------------------------------------------------------
// _mcpinput.init(sda, scl, freq=400000, mcp_addr=0x23,
//                debounce_ms=12, int_pin=-1)
// ---------------------------------------------------------------------------

static mp_obj_t mcpinput_init(size_t n_args, const mp_obj_t *pos_args,
                               mp_map_t *kw_args) {
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_sda,         MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_scl,         MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_freq,        MP_ARG_KW_ONLY | MP_ARG_INT,  {.u_int = 400000} },
        { MP_QSTR_mcp_addr,    MP_ARG_KW_ONLY | MP_ARG_INT,  {.u_int = 0x23} },
        { MP_QSTR_debounce_ms, MP_ARG_KW_ONLY | MP_ARG_INT,  {.u_int = 12} },
        { MP_QSTR_int_pin,     MP_ARG_KW_ONLY | MP_ARG_INT,  {.u_int = -1} },
    };

    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args,
                     MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    if (mcpinput_state != NULL) {
        scanner_deinit(mcpinput_state);
        mcpinput_state = NULL;
    }

    scanner_config_t cfg = {
        .pin_sda     = args[0].u_int,
        .pin_scl     = args[1].u_int,
        .freq        = args[2].u_int,
        .mcp_addr    = args[3].u_int,
        .debounce_ms = args[4].u_int,
        .int_pin     = args[5].u_int,
    };

    const char *err = scanner_init(&cfg, &mcpinput_state);
    if (err != NULL) {
        mp_raise_msg_varg(&mp_type_RuntimeError,
                          MP_ERROR_TEXT("mcpinput: %s"), err);
    }

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(mcpinput_init_obj, 0, mcpinput_init);

// ---------------------------------------------------------------------------
// _mcpinput.deinit()
// ---------------------------------------------------------------------------

static mp_obj_t mcpinput_deinit(void) {
    if (mcpinput_state != NULL) {
        scanner_deinit(mcpinput_state);
        mcpinput_state = NULL;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mcpinput_deinit_obj, mcpinput_deinit);

// ---------------------------------------------------------------------------
// _mcpinput.scan_pause() / scan_resume()
//
// Suspend just the I2C polling work in the scan task without tearing down
// the bus or PCA9685 device handle.  PowerManager calls scan_pause() before
// machine.lightsleep() so the 500 Hz I2C polling does not run across the
// sleep transition (which wedges the bus and trips RTC_WDT).  Python I2C
// calls (mcp.refresh, etc.) still work because the mutex stays valid.
// ---------------------------------------------------------------------------

static mp_obj_t mcpinput_scan_pause(void) {
    if (mcpinput_state != NULL) {
        mcpinput_state->paused = 1;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mcpinput_scan_pause_obj, mcpinput_scan_pause);

static mp_obj_t mcpinput_scan_resume(void) {
    if (mcpinput_state != NULL) {
        mcpinput_state->paused = 0;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mcpinput_scan_resume_obj, mcpinput_scan_resume);

// ---------------------------------------------------------------------------
// _mcpinput.suppress_held()
//
// After lightsleep, primes each pin's debouncer to its live state so a
// button still held from the wake press doesn't fire a fresh PRESS edge
// into the menu/game.  Also drops any queued events.  Safe to call while
// the scan task is paused.
// ---------------------------------------------------------------------------

static mp_obj_t mcpinput_suppress_held(void) {
    if (mcpinput_state != NULL) {
        scanner_suppress_held(mcpinput_state);
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mcpinput_suppress_held_obj, mcpinput_suppress_held);

// ---------------------------------------------------------------------------
// _mcpinput.get_events() -> list of (type, pin, time_ms) tuples
//
// Allocates a fresh list every call -- convenient but wasteful when polled
// at 200 Hz from an idle device (~40 bytes per call even when empty).
// Use drain_events(buf) below for the hot path.
// ---------------------------------------------------------------------------

static mp_obj_t mcpinput_get_events(void) {
    if (mcpinput_state == NULL) {
        return mp_obj_new_list(0, NULL);
    }

    mcpinput_eventbuf_t *eb = &mcpinput_state->events;
    uint32_t rd = eb->rd;
    uint32_t wr = eb->wr;
    uint32_t count = (wr - rd) & (MCPINPUT_EVENT_BUF_SIZE - 1);

    mp_obj_t list = mp_obj_new_list(0, NULL);

    for (uint32_t i = 0; i < count; i++) {
        uint32_t idx = (rd + i) & (MCPINPUT_EVENT_BUF_SIZE - 1);
        mcpinput_event_t *ev = &eb->events[idx];

        mp_obj_t tuple[3] = {
            mp_obj_new_int(ev->type),
            mp_obj_new_int(ev->pin),
            mp_obj_new_int(ev->time_ms),
        };
        mp_obj_list_append(list, mp_obj_new_tuple(3, tuple));
    }

    // Advance read pointer
    eb->rd = wr;

    return list;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mcpinput_get_events_obj, mcpinput_get_events);

// ---------------------------------------------------------------------------
// _mcpinput.drain_events(list) -> int (count drained)
//
// Zero-allocation steady-state: clears `list` and appends one tuple per
// pending event. When the device is idle (the common case) the list stays
// empty and no allocations happen at all. Tuples are still allocated when
// events fire, but those are bursts bounded by physical input rate, not
// the 200 Hz polling rate.
//
// The caller owns `list` and reuses it across calls; MicroPython lists keep
// their backing array on .clear(), so once it's grown to handle a typical
// burst the storage is reused indefinitely.
// ---------------------------------------------------------------------------

static mp_obj_t mcpinput_drain_events(mp_obj_t list_obj) {
    mp_obj_list_t *list = MP_OBJ_TO_PTR(list_obj);
    if (!mp_obj_is_type(list_obj, &mp_type_list)) {
        mp_raise_TypeError(MP_ERROR_TEXT("expected list"));
    }
    list->len = 0;  // .clear() without freeing the backing array

    if (mcpinput_state == NULL) {
        return mp_obj_new_int(0);
    }

    mcpinput_eventbuf_t *eb = &mcpinput_state->events;
    uint32_t rd = eb->rd;
    uint32_t wr = eb->wr;
    uint32_t count = (wr - rd) & (MCPINPUT_EVENT_BUF_SIZE - 1);

    for (uint32_t i = 0; i < count; i++) {
        uint32_t idx = (rd + i) & (MCPINPUT_EVENT_BUF_SIZE - 1);
        mcpinput_event_t *ev = &eb->events[idx];
        mp_obj_t tuple[3] = {
            mp_obj_new_int(ev->type),
            mp_obj_new_int(ev->pin),
            mp_obj_new_int(ev->time_ms),
        };
        mp_obj_list_append(list_obj, mp_obj_new_tuple(3, tuple));
    }

    eb->rd = wr;
    return mp_obj_new_int(count);
}
static MP_DEFINE_CONST_FUN_OBJ_1(mcpinput_drain_events_obj, mcpinput_drain_events);

// ---------------------------------------------------------------------------
// _mcpinput.read_state() -> int (16-bit bitmask of debounced pressed state)
// ---------------------------------------------------------------------------

static mp_obj_t mcpinput_read_state(void) {
    if (mcpinput_state == NULL) {
        return mp_obj_new_int(0);
    }
    return mp_obj_new_int(mcpinput_state->port_state);
}
static MP_DEFINE_CONST_FUN_OBJ_0(mcpinput_read_state_obj, mcpinput_read_state);

// ---------------------------------------------------------------------------
// _mcpinput.i2c_write(addr, reg, data)
// ---------------------------------------------------------------------------

static mp_obj_t mcpinput_i2c_write(mp_obj_t addr_obj, mp_obj_t reg_obj,
                                    mp_obj_t data_obj) {
    if (mcpinput_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }

    uint8_t addr = (uint8_t)mp_obj_get_int(addr_obj);
    uint8_t reg = (uint8_t)mp_obj_get_int(reg_obj);

    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(data_obj, &bufinfo, MP_BUFFER_READ);

    int ret = scanner_i2c_write(mcpinput_state, addr, reg,
                                 bufinfo.buf, bufinfo.len);
    if (ret != 0) {
        mp_raise_msg_varg(&mp_type_OSError,
                          MP_ERROR_TEXT("I2C write failed (%d)"), ret);
    }

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_3(mcpinput_i2c_write_obj, mcpinput_i2c_write);

// ---------------------------------------------------------------------------
// _mcpinput.i2c_read(addr, reg, nbytes) -> bytes
// ---------------------------------------------------------------------------

static mp_obj_t mcpinput_i2c_read(mp_obj_t addr_obj, mp_obj_t reg_obj,
                                   mp_obj_t nbytes_obj) {
    if (mcpinput_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }

    uint8_t addr = (uint8_t)mp_obj_get_int(addr_obj);
    uint8_t reg = (uint8_t)mp_obj_get_int(reg_obj);
    int nbytes = mp_obj_get_int(nbytes_obj);
    if (nbytes <= 0 || nbytes > 256) {
        mp_raise_ValueError(MP_ERROR_TEXT("nbytes must be 1-256"));
    }

    uint8_t buf[nbytes];
    int ret = scanner_i2c_read(mcpinput_state, addr, reg, buf, nbytes);
    if (ret != 0) {
        mp_raise_msg_varg(&mp_type_OSError,
                          MP_ERROR_TEXT("I2C read failed (%d)"), ret);
    }

    return mp_obj_new_bytes(buf, nbytes);
}
static MP_DEFINE_CONST_FUN_OBJ_3(mcpinput_i2c_read_obj, mcpinput_i2c_read);

// ---------------------------------------------------------------------------
// _mcpinput.i2c_raw_write(addr, data)
// ---------------------------------------------------------------------------

static mp_obj_t mcpinput_i2c_raw_write(mp_obj_t addr_obj, mp_obj_t data_obj) {
    if (mcpinput_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }

    uint8_t addr = (uint8_t)mp_obj_get_int(addr_obj);

    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(data_obj, &bufinfo, MP_BUFFER_READ);

    int ret = scanner_i2c_raw_write(mcpinput_state, addr,
                                     bufinfo.buf, bufinfo.len);
    if (ret != 0) {
        mp_raise_msg_varg(&mp_type_OSError,
                          MP_ERROR_TEXT("I2C raw write failed (%d)"), ret);
    }

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(mcpinput_i2c_raw_write_obj, mcpinput_i2c_raw_write);

// ---------------------------------------------------------------------------
// _mcpinput.i2c_raw_read(addr, nbytes) -> bytes
// ---------------------------------------------------------------------------

static mp_obj_t mcpinput_i2c_raw_read(mp_obj_t addr_obj, mp_obj_t nbytes_obj) {
    if (mcpinput_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }

    uint8_t addr = (uint8_t)mp_obj_get_int(addr_obj);
    int nbytes = mp_obj_get_int(nbytes_obj);
    if (nbytes <= 0 || nbytes > 256) {
        mp_raise_ValueError(MP_ERROR_TEXT("nbytes must be 1-256"));
    }

    uint8_t buf[nbytes];
    int ret = scanner_i2c_raw_read(mcpinput_state, addr, buf, nbytes);
    if (ret != 0) {
        mp_raise_msg_varg(&mp_type_OSError,
                          MP_ERROR_TEXT("I2C raw read failed (%d)"), ret);
    }

    return mp_obj_new_bytes(buf, nbytes);
}
static MP_DEFINE_CONST_FUN_OBJ_2(mcpinput_i2c_raw_read_obj, mcpinput_i2c_raw_read);

// ---------------------------------------------------------------------------
// _mcpinput.i2c_scan() -> list of int addresses
// ---------------------------------------------------------------------------

static mp_obj_t mcpinput_i2c_scan(void) {
    if (mcpinput_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }

    uint8_t addrs[112];  // 0x08–0x77
    int count = scanner_i2c_scan(mcpinput_state, addrs, sizeof(addrs));

    mp_obj_t list = mp_obj_new_list(0, NULL);
    for (int i = 0; i < count; i++) {
        mp_obj_list_append(list, mp_obj_new_int(addrs[i]));
    }
    return list;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mcpinput_i2c_scan_obj, mcpinput_i2c_scan);

// ---------------------------------------------------------------------------
// _mcpinput.stats() -> dict
// ---------------------------------------------------------------------------

static mp_obj_t mcpinput_stats(void) {
    if (mcpinput_state == NULL) {
        return mp_obj_new_dict(0);
    }

    mcpinput_state_t *s = mcpinput_state;
    mp_obj_dict_t *d = MP_OBJ_TO_PTR(mp_obj_new_dict(5));

    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_poll_count),
        mp_obj_new_int(s->poll_count));
    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_events_total),
        mp_obj_new_int(s->events_total));
    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_stack_hwm),
        mp_obj_new_int(s->task_stack_hwm));
    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_port_state),
        mp_obj_new_int(s->port_state));
    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_debounce_ms),
        mp_obj_new_int(s->debounce_ms));

    return MP_OBJ_FROM_PTR(d);
}
static MP_DEFINE_CONST_FUN_OBJ_0(mcpinput_stats_obj, mcpinput_stats);

// ---------------------------------------------------------------------------
// _mcpinput.led_init(addr=0x40, start_ch=1, n_channels=5) -> bool
// ---------------------------------------------------------------------------

static mp_obj_t mcpinput_led_init(size_t n_args, const mp_obj_t *pos_args,
                                   mp_map_t *kw_args) {
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_addr,       MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 0x40} },
        { MP_QSTR_start_ch,   MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 1} },
        { MP_QSTR_n_channels, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 5} },
    };

    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args,
                     MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    if (mcpinput_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }

    int ret = scanner_led_init(mcpinput_state,
                                (uint8_t)args[0].u_int,
                                (uint8_t)args[1].u_int,
                                (uint8_t)args[2].u_int);
    return mp_obj_new_bool(ret == 0);
}
static MP_DEFINE_CONST_FUN_OBJ_KW(mcpinput_led_init_obj, 0, mcpinput_led_init);

// ---------------------------------------------------------------------------
// _mcpinput.led_mode(mode)
// ---------------------------------------------------------------------------

static mp_obj_t mcpinput_led_mode(mp_obj_t mode_obj) {
    if (mcpinput_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    mcpinput_state->led_mode = (uint8_t)mp_obj_get_int(mode_obj);
    // Reset step tracking so first tick after mode change triggers an update
    mcpinput_state->led_last_step = 0xFF;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mcpinput_led_mode_obj, mcpinput_led_mode);

// ---------------------------------------------------------------------------
// _mcpinput.led_set_track_active(mask)
// ---------------------------------------------------------------------------

static mp_obj_t mcpinput_led_set_track_active(mp_obj_t mask_obj) {
    if (mcpinput_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    mcpinput_state->led_track_active = (uint8_t)mp_obj_get_int(mask_obj);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mcpinput_led_set_track_active_obj,
                                  mcpinput_led_set_track_active);

// ---------------------------------------------------------------------------
// _mcpinput.led_anim(channel, mode, speed=0)
// ---------------------------------------------------------------------------

static mp_obj_t mcpinput_led_anim(size_t n_args, const mp_obj_t *args) {
    if (mcpinput_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    int ch = mp_obj_get_int(args[0]);
    if (ch < 0 || ch >= MCPINPUT_LED_MAX_CH) return mp_const_none;
    mcpinput_state->led_ch[ch].mode = (uint8_t)mp_obj_get_int(args[1]);
    if (n_args > 2) {
        mcpinput_state->led_ch[ch].speed = (uint8_t)mp_obj_get_int(args[2]);
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mcpinput_led_anim_obj, 2, 3,
                                             mcpinput_led_anim);

// ---------------------------------------------------------------------------
// _mcpinput.led_anim_all(mode, speed=0)
// ---------------------------------------------------------------------------

static mp_obj_t mcpinput_led_anim_all(size_t n_args, const mp_obj_t *args) {
    if (mcpinput_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    uint8_t mode = (uint8_t)mp_obj_get_int(args[0]);
    uint8_t speed = (n_args > 1) ? (uint8_t)mp_obj_get_int(args[1]) : 0;
    for (int i = 0; i < MCPINPUT_LED_MAX_CH; i++) {
        mcpinput_state->led_ch[i].mode = mode;
        mcpinput_state->led_ch[i].speed = speed;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mcpinput_led_anim_all_obj, 1, 2,
                                             mcpinput_led_anim_all);

// ---------------------------------------------------------------------------
// _mcpinput.led_flash(channel, duration=9)
// ---------------------------------------------------------------------------

static mp_obj_t mcpinput_led_flash(size_t n_args, const mp_obj_t *args) {
    if (mcpinput_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    int ch = mp_obj_get_int(args[0]);
    if (ch < 0 || ch >= MCPINPUT_LED_MAX_CH) return mp_const_none;
    uint8_t dur = (n_args > 1) ? (uint8_t)mp_obj_get_int(args[1]) : 9;
    mcpinput_state->led_ch[ch].mode = LED_ANIM_FLASH;
    mcpinput_state->led_ch[ch].flash_ttl = dur;
    mcpinput_state->led_ch[ch].flash_start = dur;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mcpinput_led_flash_obj, 1, 2,
                                             mcpinput_led_flash);

// ---------------------------------------------------------------------------
// _mcpinput.led_tick_flash() — decrement all active flash timers by 1 frame
// ---------------------------------------------------------------------------

static mp_obj_t mcpinput_led_tick_flash(void) {
    if (mcpinput_state == NULL) return mp_obj_new_bool(false);
    bool active = false;
    for (int i = 0; i < MCPINPUT_LED_MAX_CH; i++) {
        led_channel_t *ch = &mcpinput_state->led_ch[i];
        if (ch->mode == LED_ANIM_FLASH && ch->flash_ttl > 0) {
            ch->flash_ttl--;
            if (ch->flash_ttl > 0) {
                active = true;
            } else {
                ch->mode = LED_ANIM_OFF;
            }
        }
    }
    return mp_obj_new_bool(active);
}
static MP_DEFINE_CONST_FUN_OBJ_0(mcpinput_led_tick_flash_obj,
                                  mcpinput_led_tick_flash);

// ---------------------------------------------------------------------------
// _mcpinput.led_set_whack_pins(pins_tuple)
// ---------------------------------------------------------------------------

static mp_obj_t mcpinput_led_set_whack_pins(mp_obj_t pins_obj) {
    if (mcpinput_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    size_t len;
    mp_obj_t *items;
    mp_obj_get_array(pins_obj, &len, &items);
    if (len > MCPINPUT_LED_MAX_CH) len = MCPINPUT_LED_MAX_CH;
    for (size_t i = 0; i < len; i++) {
        mcpinput_state->whack_pins[i] = (uint8_t)mp_obj_get_int(items[i]);
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mcpinput_led_set_whack_pins_obj,
                                  mcpinput_led_set_whack_pins);

// ---------------------------------------------------------------------------
// _mcpinput.led_set_whack_target(index, deadline_ms, pulse_speed=3)
// ---------------------------------------------------------------------------

static mp_obj_t mcpinput_led_set_whack_target(size_t n_args,
                                                const mp_obj_t *args) {
    if (mcpinput_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    int idx = mp_obj_get_int(args[0]);
    mcpinput_state->whack_deadline_ms = (uint32_t)mp_obj_get_int(args[1]);
    // Store pulse speed in the target channel's animation state
    uint8_t speed = (n_args > 2) ? (uint8_t)mp_obj_get_int(args[2]) : 3;
    if (idx < MCPINPUT_LED_MAX_CH) {
        mcpinput_state->led_ch[idx].speed = speed;
    }
    mcpinput_state->whack_hit = 0;
    mcpinput_state->whack_miss = 0;
    // Set target last to avoid race with scan task
    mcpinput_state->whack_target = (uint8_t)idx;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mcpinput_led_set_whack_target_obj,
                                             2, 3,
                                             mcpinput_led_set_whack_target);

// ---------------------------------------------------------------------------
// _mcpinput.led_get_whack_result() -> (hit, miss)
// ---------------------------------------------------------------------------

static mp_obj_t mcpinput_led_get_whack_result(void) {
    if (mcpinput_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }
    uint8_t hit = mcpinput_state->whack_hit;
    uint8_t miss = mcpinput_state->whack_miss;
    // Clear flags after reading
    mcpinput_state->whack_hit = 0;
    mcpinput_state->whack_miss = 0;
    mp_obj_t tuple[2] = {
        mp_obj_new_bool(hit),
        mp_obj_new_bool(miss),
    };
    return mp_obj_new_tuple(2, tuple);
}
static MP_DEFINE_CONST_FUN_OBJ_0(mcpinput_led_get_whack_result_obj,
                                  mcpinput_led_get_whack_result);

// ---------------------------------------------------------------------------
// Module definition
// ---------------------------------------------------------------------------

static const mp_rom_map_elem_t mcpinput_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__),    MP_ROM_QSTR(MP_QSTR__mcpinput) },
    { MP_ROM_QSTR(MP_QSTR_init),        MP_ROM_PTR(&mcpinput_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_deinit),      MP_ROM_PTR(&mcpinput_deinit_obj) },
    { MP_ROM_QSTR(MP_QSTR_scan_pause),  MP_ROM_PTR(&mcpinput_scan_pause_obj) },
    { MP_ROM_QSTR(MP_QSTR_scan_resume), MP_ROM_PTR(&mcpinput_scan_resume_obj) },
    { MP_ROM_QSTR(MP_QSTR_suppress_held), MP_ROM_PTR(&mcpinput_suppress_held_obj) },
    { MP_ROM_QSTR(MP_QSTR_get_events),  MP_ROM_PTR(&mcpinput_get_events_obj) },
    { MP_ROM_QSTR(MP_QSTR_drain_events), MP_ROM_PTR(&mcpinput_drain_events_obj) },
    { MP_ROM_QSTR(MP_QSTR_read_state),  MP_ROM_PTR(&mcpinput_read_state_obj) },
    { MP_ROM_QSTR(MP_QSTR_i2c_write),   MP_ROM_PTR(&mcpinput_i2c_write_obj) },
    { MP_ROM_QSTR(MP_QSTR_i2c_read),    MP_ROM_PTR(&mcpinput_i2c_read_obj) },
    { MP_ROM_QSTR(MP_QSTR_i2c_raw_write), MP_ROM_PTR(&mcpinput_i2c_raw_write_obj) },
    { MP_ROM_QSTR(MP_QSTR_i2c_raw_read),  MP_ROM_PTR(&mcpinput_i2c_raw_read_obj) },
    { MP_ROM_QSTR(MP_QSTR_i2c_scan),    MP_ROM_PTR(&mcpinput_i2c_scan_obj) },
    { MP_ROM_QSTR(MP_QSTR_stats),       MP_ROM_PTR(&mcpinput_stats_obj) },
    // LED control
    { MP_ROM_QSTR(MP_QSTR_led_init),    MP_ROM_PTR(&mcpinput_led_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_led_mode),    MP_ROM_PTR(&mcpinput_led_mode_obj) },
    { MP_ROM_QSTR(MP_QSTR_led_set_track_active), MP_ROM_PTR(&mcpinput_led_set_track_active_obj) },
    // General animation API
    { MP_ROM_QSTR(MP_QSTR_led_anim),    MP_ROM_PTR(&mcpinput_led_anim_obj) },
    { MP_ROM_QSTR(MP_QSTR_led_anim_all), MP_ROM_PTR(&mcpinput_led_anim_all_obj) },
    { MP_ROM_QSTR(MP_QSTR_led_flash),   MP_ROM_PTR(&mcpinput_led_flash_obj) },
    { MP_ROM_QSTR(MP_QSTR_led_tick_flash), MP_ROM_PTR(&mcpinput_led_tick_flash_obj) },
    // Whack / High-Five mode
    { MP_ROM_QSTR(MP_QSTR_led_set_whack_pins), MP_ROM_PTR(&mcpinput_led_set_whack_pins_obj) },
    { MP_ROM_QSTR(MP_QSTR_led_set_whack_target), MP_ROM_PTR(&mcpinput_led_set_whack_target_obj) },
    { MP_ROM_QSTR(MP_QSTR_led_get_whack_result), MP_ROM_PTR(&mcpinput_led_get_whack_result_obj) },
    // Constants
    { MP_ROM_QSTR(MP_QSTR_PRESS),       MP_ROM_INT(MCPINPUT_PRESS) },
    { MP_ROM_QSTR(MP_QSTR_RELEASE),     MP_ROM_INT(MCPINPUT_RELEASE) },
    { MP_ROM_QSTR(MP_QSTR_LED_PYTHON),  MP_ROM_INT(MCPINPUT_LED_MODE_PYTHON) },
    { MP_ROM_QSTR(MP_QSTR_LED_BEAT_SYNC), MP_ROM_INT(MCPINPUT_LED_MODE_BEAT_SYNC) },
    { MP_ROM_QSTR(MP_QSTR_LED_WHACK),   MP_ROM_INT(MCPINPUT_LED_MODE_WHACK) },
    // Animation mode constants
    { MP_ROM_QSTR(MP_QSTR_ANIM_OFF),    MP_ROM_INT(LED_ANIM_OFF) },
    { MP_ROM_QSTR(MP_QSTR_ANIM_ON),     MP_ROM_INT(LED_ANIM_ON) },
    { MP_ROM_QSTR(MP_QSTR_ANIM_GLOW),   MP_ROM_INT(LED_ANIM_GLOW) },
    { MP_ROM_QSTR(MP_QSTR_ANIM_PULSE),  MP_ROM_INT(LED_ANIM_PULSE) },
    { MP_ROM_QSTR(MP_QSTR_ANIM_BLINK),  MP_ROM_INT(LED_ANIM_BLINK) },
    { MP_ROM_QSTR(MP_QSTR_ANIM_FLASH),  MP_ROM_INT(LED_ANIM_FLASH) },
    { MP_ROM_QSTR(MP_QSTR_ANIM_WAVE),   MP_ROM_INT(LED_ANIM_WAVE) },
};
static MP_DEFINE_CONST_DICT(mcpinput_module_globals,
                             mcpinput_module_globals_table);

const mp_obj_module_t mcpinput_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&mcpinput_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR__mcpinput, mcpinput_module);
