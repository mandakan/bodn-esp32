// life_mod.c — MicroPython bindings for the _life module.
//
// Exposes one function:
//   _life.step(grid, w, h, birth_mask, survive_mask, wrap, palette)
//     -> (new_grid: bytearray, births: [(x,y), ...], deaths: [(x,y), ...])
//
// birth_mask / survive_mask are bitmasks where bit N is set for neighbour
// count N (covers 0..8). The Python wrapper in bodn/life_rules.py converts
// the existing frozenset-of-ints rule representation into these masks and
// supplies the packed palette. Output shape matches the reference step().

#include "py/runtime.h"
#include "py/obj.h"
#include "py/objlist.h"
#include "py/objtuple.h"

#include "life.h"

// _life.step(grid, w, h, birth_mask, survive_mask, wrap, palette)
static mp_obj_t life_step_fn(size_t n_args, const mp_obj_t *args) {
    (void)n_args;  // fixed arity enforced by MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN

    mp_buffer_info_t grid_buf;
    mp_get_buffer_raise(args[0], &grid_buf, MP_BUFFER_READ);

    int w = mp_obj_get_int(args[1]);
    int h = mp_obj_get_int(args[2]);
    mp_uint_t birth_mask   = mp_obj_get_int_truncated(args[3]);
    mp_uint_t survive_mask = mp_obj_get_int_truncated(args[4]);
    int wrap = mp_obj_is_true(args[5]) ? 1 : 0;

    mp_buffer_info_t pal_buf;
    mp_get_buffer_raise(args[6], &pal_buf, MP_BUFFER_READ);

    if (w <= 0 || h <= 0 || w > 255 || h > 255) {
        mp_raise_ValueError(MP_ERROR_TEXT("life: bad grid dimensions"));
    }
    int total = w * h;
    if ((int)grid_buf.len != total) {
        mp_raise_ValueError(MP_ERROR_TEXT("life: grid size mismatch"));
    }
    if (pal_buf.len == 0 || (pal_buf.len % 3) != 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("life: palette must be 3*N bytes"));
    }
    int pal_len = pal_buf.len / 3;

    // Output grid — a fresh bytearray the Python caller can hold onto.
    // Use the by-ref constructor with a GC-tracked buffer; passing NULL to the
    // copying mp_obj_new_bytearray memcpys from address 0 and crashes.
    uint8_t *new_buf = m_new(uint8_t, total);
    mp_obj_t new_grid_obj = mp_obj_new_bytearray_by_ref(total, new_buf);

    // Scratch buffers for births/deaths — at most w*h events each.
    uint8_t *births_buf = m_new(uint8_t, 2 * total);
    uint8_t *deaths_buf = m_new(uint8_t, 2 * total);
    int n_births = 0;
    int n_deaths = 0;

    life_step(
        (const uint8_t *)grid_buf.buf,
        new_buf,
        w, h,
        (uint16_t)birth_mask,
        (uint16_t)survive_mask,
        wrap,
        (const uint8_t *)pal_buf.buf,
        pal_len,
        births_buf, &n_births,
        deaths_buf, &n_deaths
    );

    mp_obj_t births_list = mp_obj_new_list(0, NULL);
    for (int i = 0; i < n_births; i++) {
        mp_obj_t pair[2] = {
            MP_OBJ_NEW_SMALL_INT(births_buf[2 * i + 0]),
            MP_OBJ_NEW_SMALL_INT(births_buf[2 * i + 1]),
        };
        mp_obj_list_append(births_list, mp_obj_new_tuple(2, pair));
    }

    mp_obj_t deaths_list = mp_obj_new_list(0, NULL);
    for (int i = 0; i < n_deaths; i++) {
        mp_obj_t pair[2] = {
            MP_OBJ_NEW_SMALL_INT(deaths_buf[2 * i + 0]),
            MP_OBJ_NEW_SMALL_INT(deaths_buf[2 * i + 1]),
        };
        mp_obj_list_append(deaths_list, mp_obj_new_tuple(2, pair));
    }

    m_del(uint8_t, births_buf, 2 * total);
    m_del(uint8_t, deaths_buf, 2 * total);

    mp_obj_t ret[3] = { new_grid_obj, births_list, deaths_list };
    return mp_obj_new_tuple(3, ret);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(life_step_obj, 7, 7, life_step_fn);

static const mp_rom_map_elem_t life_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR__life) },
    { MP_ROM_QSTR(MP_QSTR_step),     MP_ROM_PTR(&life_step_obj) },
};
static MP_DEFINE_CONST_DICT(life_module_globals, life_module_globals_table);

const mp_obj_module_t life_cmod_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&life_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR__life, life_cmod_module);
