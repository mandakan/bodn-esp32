/*
 * draw.c — MicroPython bindings for the _draw module
 *
 * Provides bitmap font rendering, sprite blitting, and (later) drawing
 * primitives.  All operations write directly into RGB565 framebuffers.
 */

#include "py/runtime.h"
#include "py/obj.h"
#include "py/objstr.h"

#include "draw.h"
#include "decode.h"
#include "font_render.h"
#include "blit.h"
#include "primitives.h"
#include "fonts/builtin_8x8.h"

/* ══════════════════════════════════════════════════════════════════
 * Asset handle type
 * ══════════════════════════════════════════════════════════════════ */

typedef struct {
    mp_obj_base_t base;
    draw_asset_t  asset;
    mp_obj_t      data_ref;   /* Python bytes/bytearray — prevent GC */
} draw_asset_obj_t;

static void asset_print(const mp_print_t *print, mp_obj_t self_in, mp_print_kind_t kind) {
    (void)kind;
    draw_asset_obj_t *self = MP_OBJ_TO_PTR(self_in);
    const draw_header_t *h = self->asset.header;
    mp_printf(print, "<_draw.Asset type=%d bpp=%d entries=%d %dx%d>",
              h->type, h->bpp, h->num_entries, h->max_width, h->height);
}

static MP_DEFINE_CONST_OBJ_TYPE(
    draw_asset_type,
    MP_QSTR_Asset,
    MP_TYPE_FLAG_NONE,
    print, asset_print
);

/* Helper: extract draw_asset_t* from a Python arg (must be our type) */
static draw_asset_t *asset_from_obj(mp_obj_t obj) {
    if (!mp_obj_is_type(obj, &draw_asset_type)) {
        mp_raise_TypeError(MP_ERROR_TEXT("expected _draw.Asset"));
    }
    return &((draw_asset_obj_t *)MP_OBJ_TO_PTR(obj))->asset;
}

/* ══════════════════════════════════════════════════════════════════
 * Built-in 8x8 font
 * ══════════════════════════════════════════════════════════════════ */

static draw_asset_obj_t builtin_8x8_obj = {
    .base = { .type = &draw_asset_type },
    .data_ref = MP_OBJ_NULL,  /* lives in flash — no GC needed */
    .asset = {
        .data     = builtin_8x8_data,
        .data_len = sizeof(builtin_8x8_data),
        .header   = (const draw_header_t *)builtin_8x8_data,
        .index    = (const draw_index_entry_t *)(builtin_8x8_data + 20),
        .bitmap   = builtin_8x8_data + 1050,  /* 20 + 103*10 = 1050 */
    },
};

/* ══════════════════════════════════════════════════════════════════
 * _draw.load(data_bytes) → Asset
 * ══════════════════════════════════════════════════════════════════ */

static mp_obj_t draw_load(mp_obj_t data_obj) {
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(data_obj, &bufinfo, MP_BUFFER_READ);

    if (bufinfo.len < sizeof(draw_header_t)) {
        mp_raise_ValueError(MP_ERROR_TEXT("data too small"));
    }

    const draw_header_t *hdr = (const draw_header_t *)bufinfo.buf;
    if (hdr->magic != DRAW_MAGIC) {
        mp_raise_ValueError(MP_ERROR_TEXT("bad magic"));
    }
    if (hdr->version != DRAW_VERSION) {
        mp_raise_ValueError(MP_ERROR_TEXT("bad version"));
    }
    if (hdr->bpp != 1 && hdr->bpp != 2 && hdr->bpp != 4 && hdr->bpp != 8) {
        mp_raise_ValueError(MP_ERROR_TEXT("bad bpp"));
    }

    /* Sanity: index + bitmap must fit in the data */
    size_t min_size = sizeof(draw_header_t) +
                      (size_t)hdr->num_entries * sizeof(draw_index_entry_t);
    if (bufinfo.len < min_size || bufinfo.len < hdr->bitmap_offset) {
        mp_raise_ValueError(MP_ERROR_TEXT("data truncated"));
    }

    draw_asset_obj_t *obj = mp_obj_malloc(draw_asset_obj_t, &draw_asset_type);
    obj->data_ref = data_obj;  /* prevent GC of the backing buffer */

    draw_asset_t *a = &obj->asset;
    a->data     = bufinfo.buf;
    a->data_len = bufinfo.len;
    a->header   = hdr;
    a->index    = (const draw_index_entry_t *)((const uint8_t *)bufinfo.buf + sizeof(draw_header_t));
    a->bitmap   = (const uint8_t *)bufinfo.buf + hdr->bitmap_offset;

    return MP_OBJ_FROM_PTR(obj);
}
static MP_DEFINE_CONST_FUN_OBJ_1(draw_load_obj, draw_load);

/* ══════════════════════════════════════════════════════════════════
 * _draw.text(buf, buf_w, x, y, string, asset, color [, bg]) → (x,y,w,h)
 * ══════════════════════════════════════════════════════════════════ */

static mp_obj_t draw_text_fn(size_t n_args, const mp_obj_t *args) {
    /* args: buf, buf_w, x, y, string, asset, color [, bg] */
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(args[0], &bufinfo, MP_BUFFER_WRITE);

    int buf_w = mp_obj_get_int(args[1]);
    if (buf_w <= 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("buf_w must be > 0"));
    }
    int buf_h = (int)(bufinfo.len / ((size_t)buf_w * 2));

    int x = mp_obj_get_int(args[2]);
    int y = mp_obj_get_int(args[3]);

    size_t str_len;
    const char *str = mp_obj_str_get_data(args[4], &str_len);

    draw_asset_t *asset = asset_from_obj(args[5]);
    uint16_t color = (uint16_t)mp_obj_get_int(args[6]);

    int32_t bg = -1;
    if (n_args > 7 && args[7] != mp_const_none) {
        bg = (int32_t)mp_obj_get_int(args[7]);
    }

    draw_bbox_t bb = draw_text((uint16_t *)bufinfo.buf, buf_w, buf_h,
                               x, y, str, str_len, asset, color, bg);

    mp_obj_t items[4] = {
        MP_OBJ_NEW_SMALL_INT(bb.x),
        MP_OBJ_NEW_SMALL_INT(bb.y),
        MP_OBJ_NEW_SMALL_INT(bb.w),
        MP_OBJ_NEW_SMALL_INT(bb.h),
    };
    return mp_obj_new_tuple(4, items);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(draw_text_obj, 7, 8, draw_text_fn);

/* ══════════════════════════════════════════════════════════════════
 * _draw.text_width(string, asset) → int
 * ══════════════════════════════════════════════════════════════════ */

static mp_obj_t draw_text_width_fn(mp_obj_t str_obj, mp_obj_t asset_obj) {
    size_t str_len;
    const char *str = mp_obj_str_get_data(str_obj, &str_len);
    draw_asset_t *asset = asset_from_obj(asset_obj);

    return MP_OBJ_NEW_SMALL_INT(draw_text_width(str, str_len, asset));
}
static MP_DEFINE_CONST_FUN_OBJ_2(draw_text_width_obj, draw_text_width_fn);

/* ══════════════════════════════════════════════════════════════════
 * _draw.sprite(buf, buf_w, x, y, asset, frame_id, color) → (x,y,w,h)
 * ══════════════════════════════════════════════════════════════════ */

static mp_obj_t draw_sprite_fn(size_t n_args, const mp_obj_t *args) {
    (void)n_args;  /* always 7 */
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(args[0], &bufinfo, MP_BUFFER_WRITE);

    int buf_w = mp_obj_get_int(args[1]);
    if (buf_w <= 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("buf_w must be > 0"));
    }
    int buf_h = (int)(bufinfo.len / ((size_t)buf_w * 2));

    int x = mp_obj_get_int(args[2]);
    int y = mp_obj_get_int(args[3]);
    draw_asset_t *asset = asset_from_obj(args[4]);
    uint32_t frame_id = (uint32_t)mp_obj_get_int(args[5]);
    uint16_t color = (uint16_t)mp_obj_get_int(args[6]);

    draw_bbox_t bb = draw_sprite((uint16_t *)bufinfo.buf, buf_w, buf_h,
                                 x, y, asset, frame_id, color);

    mp_obj_t items[4] = {
        MP_OBJ_NEW_SMALL_INT(bb.x),
        MP_OBJ_NEW_SMALL_INT(bb.y),
        MP_OBJ_NEW_SMALL_INT(bb.w),
        MP_OBJ_NEW_SMALL_INT(bb.h),
    };
    return mp_obj_new_tuple(4, items);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(draw_sprite_obj, 7, 7, draw_sprite_fn);

/* ══════════════════════════════════════════════════════════════════
 * _draw.info(asset) → dict
 * ══════════════════════════════════════════════════════════════════ */

static mp_obj_t draw_info_fn(mp_obj_t asset_obj) {
    draw_asset_t *asset = asset_from_obj(asset_obj);
    const draw_header_t *h = asset->header;

    mp_obj_dict_t *d = MP_OBJ_TO_PTR(mp_obj_new_dict(6));
    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_type),
        MP_OBJ_NEW_SMALL_INT(h->type));
    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_bpp),
        MP_OBJ_NEW_SMALL_INT(h->bpp));
    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_num_entries),
        MP_OBJ_NEW_SMALL_INT(h->num_entries));
    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_max_width),
        MP_OBJ_NEW_SMALL_INT(h->max_width));
    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_height),
        MP_OBJ_NEW_SMALL_INT(h->height));
    mp_obj_dict_store(MP_OBJ_FROM_PTR(d),
        MP_OBJ_NEW_QSTR(MP_QSTR_baseline),
        MP_OBJ_NEW_SMALL_INT(h->baseline));

    return MP_OBJ_FROM_PTR(d);
}
static MP_DEFINE_CONST_FUN_OBJ_1(draw_info_obj, draw_info_fn);

/* ══════════════════════════════════════════════════════════════════
 * _draw.waveform(fb, buf_w, x, y, w, h, samples, fg, bg, gain_q8) → (x,y,w,h)
 *
 * Render an oscilloscope trace into an RGB565 framebuffer.  `samples` is a
 * bytes-like object of int16 PCM samples; the scope stretches its entire
 * length horizontally across `w` pixels.
 * ══════════════════════════════════════════════════════════════════ */

static mp_obj_t draw_waveform_fn(size_t n_args, const mp_obj_t *args) {
    (void)n_args;  /* always 10 */
    mp_buffer_info_t fbinfo;
    mp_get_buffer_raise(args[0], &fbinfo, MP_BUFFER_WRITE);

    int buf_w = mp_obj_get_int(args[1]);
    if (buf_w <= 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("buf_w must be > 0"));
    }
    int buf_h = (int)(fbinfo.len / ((size_t)buf_w * 2));

    int x = mp_obj_get_int(args[2]);
    int y = mp_obj_get_int(args[3]);
    int w = mp_obj_get_int(args[4]);
    int h = mp_obj_get_int(args[5]);

    mp_buffer_info_t sbinfo;
    mp_get_buffer_raise(args[6], &sbinfo, MP_BUFFER_READ);
    int n_samples = (int)(sbinfo.len / 2);

    uint16_t fg = (uint16_t)mp_obj_get_int(args[7]);
    uint16_t bg = (uint16_t)mp_obj_get_int(args[8]);
    int gain_q8 = mp_obj_get_int(args[9]);

    draw_bbox_t bb = draw_waveform((uint16_t *)fbinfo.buf, buf_w, buf_h,
                                   x, y, w, h,
                                   (const int16_t *)sbinfo.buf, n_samples,
                                   fg, bg, gain_q8);

    mp_obj_t items[4] = {
        MP_OBJ_NEW_SMALL_INT(bb.x),
        MP_OBJ_NEW_SMALL_INT(bb.y),
        MP_OBJ_NEW_SMALL_INT(bb.w),
        MP_OBJ_NEW_SMALL_INT(bb.h),
    };
    return mp_obj_new_tuple(4, items);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(draw_waveform_obj, 10, 10, draw_waveform_fn);

/* ══════════════════════════════════════════════════════════════════
 * Module definition
 * ══════════════════════════════════════════════════════════════════ */

static const mp_rom_map_elem_t draw_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__),    MP_ROM_QSTR(MP_QSTR__draw) },
    { MP_ROM_QSTR(MP_QSTR_load),        MP_ROM_PTR(&draw_load_obj) },
    { MP_ROM_QSTR(MP_QSTR_text),        MP_ROM_PTR(&draw_text_obj) },
    { MP_ROM_QSTR(MP_QSTR_text_width),  MP_ROM_PTR(&draw_text_width_obj) },
    { MP_ROM_QSTR(MP_QSTR_sprite),      MP_ROM_PTR(&draw_sprite_obj) },
    { MP_ROM_QSTR(MP_QSTR_waveform),    MP_ROM_PTR(&draw_waveform_obj) },
    { MP_ROM_QSTR(MP_QSTR_info),        MP_ROM_PTR(&draw_info_obj) },
    { MP_ROM_QSTR(MP_QSTR_BUILTIN_8X8), MP_ROM_PTR(&builtin_8x8_obj) },
    { MP_ROM_QSTR(MP_QSTR_Asset),       MP_ROM_PTR(&draw_asset_type) },
};
static MP_DEFINE_CONST_DICT(draw_module_globals, draw_module_globals_table);

const mp_obj_module_t draw_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&draw_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR__draw, draw_module);
