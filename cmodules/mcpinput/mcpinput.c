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
// _mcpinput.get_events() -> list of (type, pin, time_ms) tuples
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
// Module definition
// ---------------------------------------------------------------------------

static const mp_rom_map_elem_t mcpinput_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__),    MP_ROM_QSTR(MP_QSTR__mcpinput) },
    { MP_ROM_QSTR(MP_QSTR_init),        MP_ROM_PTR(&mcpinput_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_deinit),      MP_ROM_PTR(&mcpinput_deinit_obj) },
    { MP_ROM_QSTR(MP_QSTR_get_events),  MP_ROM_PTR(&mcpinput_get_events_obj) },
    { MP_ROM_QSTR(MP_QSTR_read_state),  MP_ROM_PTR(&mcpinput_read_state_obj) },
    { MP_ROM_QSTR(MP_QSTR_i2c_write),   MP_ROM_PTR(&mcpinput_i2c_write_obj) },
    { MP_ROM_QSTR(MP_QSTR_i2c_read),    MP_ROM_PTR(&mcpinput_i2c_read_obj) },
    { MP_ROM_QSTR(MP_QSTR_i2c_scan),    MP_ROM_PTR(&mcpinput_i2c_scan_obj) },
    { MP_ROM_QSTR(MP_QSTR_stats),       MP_ROM_PTR(&mcpinput_stats_obj) },
    // Constants
    { MP_ROM_QSTR(MP_QSTR_PRESS),       MP_ROM_INT(MCPINPUT_PRESS) },
    { MP_ROM_QSTR(MP_QSTR_RELEASE),     MP_ROM_INT(MCPINPUT_RELEASE) },
};
static MP_DEFINE_CONST_DICT(mcpinput_module_globals,
                             mcpinput_module_globals_table);

const mp_obj_module_t mcpinput_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&mcpinput_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR__mcpinput, mcpinput_module);
