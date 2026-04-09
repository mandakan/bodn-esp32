// spidma.c — DMA-backed SPI display driver for MicroPython
//
// Replaces machine.SPI blocking writes with ESP-IDF spi_master DMA.
// push() returns immediately; ISR signals completion via busy flag.

#include "py/runtime.h"
#include "py/obj.h"
#include "py/mphal.h"
#include "spidma.h"

#include "driver/spi_master.h"
#include "driver/gpio.h"
#include "esp_heap_caps.h"

#include <string.h>

spidma_state_t *spidma_state = NULL;

// ── Internal helpers ───────────────────────────────────────────

// Wait for any in-progress async transfer on this display.
static void drain_display(spidma_display_t *disp) {
    if (disp->pending) {
        spi_transaction_t *rtrans;
        spi_device_get_trans_result(disp->handle, &rtrans, portMAX_DELAY);
        disp->pending = false;
    }
}

// Send a transaction via interrupt mode (queue + wait).
// All SPI operations use this path — never mix polling and interrupt mode.
static void send_blocking(spidma_display_t *disp, spi_transaction_t *t) {
    t->user = disp;
    spi_device_queue_trans(disp->handle, t, portMAX_DELAY);
    spi_transaction_t *rtrans;
    spi_device_get_trans_result(disp->handle, &rtrans, portMAX_DELAY);
}

// Blocking command write: DC=0 for cmd byte, DC=1 for data bytes.
static void send_cmd(spidma_display_t *disp, uint8_t cmd,
                     const uint8_t *data, size_t len) {
    spi_transaction_t t;

    // Command byte (DC=0)
    memset(&t, 0, sizeof(t));
    gpio_set_level(disp->dc_pin, 0);
    t.length = 8;
    t.tx_data[0] = cmd;
    t.flags = SPI_TRANS_USE_TXDATA;
    send_blocking(disp, &t);

    // Data bytes (DC=1)
    if (data && len > 0) {
        memset(&t, 0, sizeof(t));
        gpio_set_level(disp->dc_pin, 1);
        t.length = len * 8;
        if (len <= 4) {
            memcpy(t.tx_data, data, len);
            t.flags = SPI_TRANS_USE_TXDATA;
        } else {
            t.tx_buffer = data;
        }
        send_blocking(disp, &t);
    }
}

// Set address window for a display region.
static void set_window(spidma_display_t *disp, int x, int y, int w, int h) {
    int x0 = disp->col_off + x;
    int x1 = x0 + w - 1;
    int y0 = disp->row_off + y;
    int y1 = y0 + h - 1;

    uint8_t caset[4] = { x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF };
    uint8_t raset[4] = { y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF };

    send_cmd(disp, SPIDMA_CMD_CASET, caset, 4);
    send_cmd(disp, SPIDMA_CMD_RASET, raset, 4);
}

// Queue async DMA from an internal DRAM buffer.  Sets disp->pending.
static void queue_async(spidma_display_t *disp, const uint8_t *buf, size_t len) {
    memset(&disp->data_trans, 0, sizeof(spi_transaction_t));
    disp->data_trans.length = len * 8;
    disp->data_trans.tx_buffer = buf;
    disp->pending = true;
    spi_device_queue_trans(disp->handle, &disp->data_trans, portMAX_DELAY);
}

// Pipelined chunked push: copies PSRAM → DRAM staging buffers while
// DMA sends the previous chunk.  Last chunk is async (non-blocking).
// All operations use interrupt mode (queue_trans) — never polling_transmit.
static void push_data(spidma_display_t *disp, const uint8_t *src, size_t total) {
    int cur = 0;
    size_t remaining = total;

    // Copy first chunk
    size_t chunk = (remaining > SPIDMA_DMA_CHUNK_SZ)
                   ? SPIDMA_DMA_CHUNK_SZ : remaining;
    memcpy(spidma_state->dma_buf[0], src, chunk);
    src += chunk;
    remaining -= chunk;

    // Pipeline: DMA current buffer while copying next
    while (remaining > 0) {
        queue_async(disp, spidma_state->dma_buf[cur], chunk);

        int next = 1 - cur;
        size_t next_chunk = (remaining > SPIDMA_DMA_CHUNK_SZ)
                            ? SPIDMA_DMA_CHUNK_SZ : remaining;
        memcpy(spidma_state->dma_buf[next], src, next_chunk);
        src += next_chunk;
        remaining -= next_chunk;

        // Wait for current DMA before reusing its buffer
        drain_display(disp);

        chunk = next_chunk;
        cur = next;
    }

    // Last chunk: start async DMA and return (non-blocking)
    queue_async(disp, spidma_state->dma_buf[cur], chunk);
}

// ── Python bindings ────────────────────────────────────────────

// _spidma.init(sck=, mosi=, baudrate=26_000_000)
static mp_obj_t spidma_init(size_t n_args, const mp_obj_t *pos_args,
                            mp_map_t *kw_args) {
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_sck,      MP_ARG_REQUIRED | MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_mosi,     MP_ARG_REQUIRED | MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_baudrate, MP_ARG_KW_ONLY  | MP_ARG_INT, {.u_int = 26000000} },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args,
                     MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    int pin_sck  = args[0].u_int;
    int pin_mosi = args[1].u_int;
    int baudrate = args[2].u_int;

    // Soft-reboot safe: deinit previous instance
    if (spidma_state) {
        // Drain all displays
        for (int i = 0; i < SPIDMA_MAX_DISPLAYS; i++) {
            spidma_display_t *d = &spidma_state->displays[i];
            if (d->initialized) {
                drain_display(d);
                spi_bus_remove_device(d->handle);
                d->initialized = false;
            }
        }
        if (spidma_state->bus_initialized) {
            spi_bus_free(spidma_state->host);
            spidma_state->bus_initialized = false;
        }
        free(spidma_state);
        spidma_state = NULL;
    }

    spidma_state = calloc(1, sizeof(spidma_state_t));
    if (!spidma_state) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("spidma alloc"));
    }

    spidma_state->host = SPI2_HOST;
    spidma_state->baudrate = baudrate;

    spi_bus_config_t buscfg = {
        .mosi_io_num = pin_mosi,
        .miso_io_num = -1,
        .sclk_io_num = pin_sck,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = SPIDMA_DMA_CHUNK_SZ,
    };

    bool we_own_bus = false;
    esp_err_t err = spi_bus_initialize(spidma_state->host, &buscfg,
                                       SPI_DMA_CH_AUTO);
    if (err == ESP_OK) {
        we_own_bus = true;
    } else if (err == ESP_ERR_INVALID_STATE) {
        // Bus already initialized (machine.SPI from previous soft-reboot).
        // Try to free and re-init with our config.
        spi_bus_free(spidma_state->host);
        err = spi_bus_initialize(spidma_state->host, &buscfg,
                                 SPI_DMA_CH_AUTO);
        if (err == ESP_OK) {
            we_own_bus = true;
        } else if (err == ESP_ERR_INVALID_STATE) {
            // Orphaned devices prevent bus free — reuse the existing bus.
            // Same pins + DMA, so our devices will work on it.
            we_own_bus = false;
            err = ESP_OK;
        }
    }
    if (err != ESP_OK) {
        free(spidma_state);
        spidma_state = NULL;
        mp_raise_msg_varg(&mp_type_RuntimeError,
                          MP_ERROR_TEXT("spi_bus_init: %d"), (int)err);
    }
    spidma_state->bus_initialized = we_own_bus;

    // Allocate ping-pong DMA staging buffers in internal DRAM.
    // PSRAM buffers are rejected by spi_device_queue_trans, so we copy
    // chunks into these DMA-capable buffers for pipelined transfers.
    size_t free_dma = heap_caps_get_free_size(MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
    size_t largest_dma = heap_caps_get_largest_free_block(MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
    size_t free_internal = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
    mp_printf(&mp_plat_print,
              "spidma: DRAM free=%u largest=%u internal_total=%u need=%u\n",
              (unsigned)free_dma, (unsigned)largest_dma,
              (unsigned)free_internal, (unsigned)(SPIDMA_DMA_CHUNK_SZ * 2));

    for (int i = 0; i < 2; i++) {
        spidma_state->dma_buf[i] = heap_caps_malloc(
            SPIDMA_DMA_CHUNK_SZ, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
        if (!spidma_state->dma_buf[i]) {
            mp_printf(&mp_plat_print,
                      "spidma: buf[%d] alloc FAILED (wanted %u)\n",
                      i, (unsigned)SPIDMA_DMA_CHUNK_SZ);
            if (i == 1) heap_caps_free(spidma_state->dma_buf[0]);
            if (we_own_bus) spi_bus_free(spidma_state->host);
            free(spidma_state);
            spidma_state = NULL;
            mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("DMA buf alloc"));
        }
    }

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(spidma_init_obj, 0, spidma_init);

// _spidma.deinit()
static mp_obj_t spidma_deinit(void) {
    if (!spidma_state) return mp_const_none;

    for (int i = 0; i < SPIDMA_MAX_DISPLAYS; i++) {
        spidma_display_t *d = &spidma_state->displays[i];
        if (d->initialized) {
            drain_display(d);
            spi_bus_remove_device(d->handle);
            d->initialized = false;
        }
    }
    if (spidma_state->bus_initialized) {
        spi_bus_free(spidma_state->host);
    }
    for (int i = 0; i < 2; i++) {
        if (spidma_state->dma_buf[i]) {
            heap_caps_free(spidma_state->dma_buf[i]);
        }
    }
    free(spidma_state);
    spidma_state = NULL;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(spidma_deinit_obj, spidma_deinit);

// _spidma.add_display(slot=, cs=, dc=, width=, height=, col_off=0, row_off=0)
static mp_obj_t spidma_add_display(size_t n_args, const mp_obj_t *pos_args,
                                   mp_map_t *kw_args) {
    if (!spidma_state) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }

    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_slot,    MP_ARG_REQUIRED | MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_cs,      MP_ARG_REQUIRED | MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_dc,      MP_ARG_REQUIRED | MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_width,   MP_ARG_REQUIRED | MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_height,  MP_ARG_REQUIRED | MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_col_off, MP_ARG_KW_ONLY  | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_row_off, MP_ARG_KW_ONLY  | MP_ARG_INT, {.u_int = 0} },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args,
                     MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    int slot    = args[0].u_int;
    int pin_cs  = args[1].u_int;
    int pin_dc  = args[2].u_int;
    int width   = args[3].u_int;
    int height  = args[4].u_int;
    int col_off = args[5].u_int;
    int row_off = args[6].u_int;

    if (slot < 0 || slot >= SPIDMA_MAX_DISPLAYS) {
        mp_raise_ValueError(MP_ERROR_TEXT("slot 0-1"));
    }

    spidma_display_t *disp = &spidma_state->displays[slot];
    if (disp->initialized) {
        drain_display(disp);
        spi_bus_remove_device(disp->handle);
        disp->initialized = false;
    }

    // Configure DC pin as output
    gpio_reset_pin((gpio_num_t)pin_dc);
    gpio_set_direction((gpio_num_t)pin_dc, GPIO_MODE_OUTPUT);
    gpio_set_level((gpio_num_t)pin_dc, 1);

    spi_device_interface_config_t devcfg = {
        .clock_speed_hz = spidma_state->baudrate,
        .mode = 0,
        .spics_io_num = pin_cs,
        .queue_size = 1,
        .flags = SPI_DEVICE_HALFDUPLEX,
    };

    esp_err_t err = spi_bus_add_device(spidma_state->host, &devcfg,
                                       &disp->handle);
    if (err != ESP_OK) {
        mp_raise_msg_varg(&mp_type_RuntimeError,
                          MP_ERROR_TEXT("spi_add_device: %d"), (int)err);
    }
    disp->dc_pin  = (gpio_num_t)pin_dc;
    disp->width   = width;
    disp->height  = height;
    disp->col_off = col_off;
    disp->row_off = row_off;
    disp->pending = false;
    disp->initialized = true;

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(spidma_add_display_obj, 0,
                                  spidma_add_display);

// _spidma.cmd(slot, cmd_byte, data_bytes)
static mp_obj_t spidma_cmd_fn(mp_obj_t slot_obj, mp_obj_t cmd_obj,
                              mp_obj_t data_obj) {
    if (!spidma_state) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }

    int slot = mp_obj_get_int(slot_obj);
    if (slot < 0 || slot >= SPIDMA_MAX_DISPLAYS) {
        mp_raise_ValueError(MP_ERROR_TEXT("bad slot"));
    }
    spidma_display_t *disp = &spidma_state->displays[slot];
    if (!disp->initialized) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("display not added"));
    }

    // Wait for any async transfer before sending commands
    drain_display(disp);

    uint8_t cmd = (uint8_t)mp_obj_get_int(cmd_obj);

    if (data_obj == mp_const_none || data_obj == mp_const_empty_bytes) {
        send_cmd(disp, cmd, NULL, 0);
    } else {
        mp_buffer_info_t bufinfo;
        mp_get_buffer_raise(data_obj, &bufinfo, MP_BUFFER_READ);
        send_cmd(disp, cmd, bufinfo.buf, bufinfo.len);
    }

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_3(spidma_cmd_obj, spidma_cmd_fn);

// _spidma.push(slot, buf)
static mp_obj_t spidma_push(mp_obj_t slot_obj, mp_obj_t buf_obj) {
    if (!spidma_state) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }

    int slot = mp_obj_get_int(slot_obj);
    if (slot < 0 || slot >= SPIDMA_MAX_DISPLAYS) {
        mp_raise_ValueError(MP_ERROR_TEXT("bad slot"));
    }
    spidma_display_t *disp = &spidma_state->displays[slot];
    if (!disp->initialized) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("display not added"));
    }

    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(buf_obj, &bufinfo, MP_BUFFER_READ);

    size_t expected = (size_t)disp->width * disp->height * 2;
    if (bufinfo.len < expected) {
        mp_raise_ValueError(MP_ERROR_TEXT("buffer too small"));
    }

    // Drain any previous async transfer
    drain_display(disp);

    // Set full-screen address window (blocking, ~5µs total)
    set_window(disp, 0, 0, disp->width, disp->height);

    // RAMWR command byte (blocking via interrupt mode)
    spi_transaction_t cmd_t;
    memset(&cmd_t, 0, sizeof(cmd_t));
    gpio_set_level(disp->dc_pin, 0);
    cmd_t.length = 8;
    cmd_t.tx_data[0] = SPIDMA_CMD_RAMWR;
    cmd_t.flags = SPI_TRANS_USE_TXDATA;
    send_blocking(disp, &cmd_t);

    // Set DC=1 for pixel data, then pipeline chunks via staging buffers
    gpio_set_level(disp->dc_pin, 1);
    push_data(disp, (const uint8_t *)bufinfo.buf, expected);

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(spidma_push_obj, spidma_push);

// _spidma.push_rect(slot, buf, x, y, w, h)
static mp_obj_t spidma_push_rect(size_t n_args, const mp_obj_t *args) {
    if (!spidma_state) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("not initialised"));
    }

    int slot = mp_obj_get_int(args[0]);
    if (slot < 0 || slot >= SPIDMA_MAX_DISPLAYS) {
        mp_raise_ValueError(MP_ERROR_TEXT("bad slot"));
    }
    spidma_display_t *disp = &spidma_state->displays[slot];
    if (!disp->initialized) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("display not added"));
    }

    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(args[1], &bufinfo, MP_BUFFER_READ);

    int x = mp_obj_get_int(args[2]);
    int y = mp_obj_get_int(args[3]);
    int w = mp_obj_get_int(args[4]);
    int h = mp_obj_get_int(args[5]);

    // Clamp to display bounds
    if (x < 0) { w += x; x = 0; }
    if (y < 0) { h += y; y = 0; }
    if (x + w > disp->width)  w = disp->width - x;
    if (y + h > disp->height) h = disp->height - y;
    if (w <= 0 || h <= 0) return mp_const_none;

    // Drain any previous async transfer
    drain_display(disp);

    // Set address window for the rect
    set_window(disp, x, y, w, h);

    // RAMWR
    spi_transaction_t cmd_t;
    memset(&cmd_t, 0, sizeof(cmd_t));
    gpio_set_level(disp->dc_pin, 0);
    cmd_t.length = 8;
    cmd_t.tx_data[0] = SPIDMA_CMD_RAMWR;
    cmd_t.flags = SPI_TRANS_USE_TXDATA;
    send_blocking(disp, &cmd_t);

    gpio_set_level(disp->dc_pin, 1);

    int stride = disp->width * 2;

    if (w == disp->width) {
        // Full-width strip: contiguous — pipelined DMA
        uint8_t *src = (uint8_t *)bufinfo.buf + y * stride;
        push_data(disp, src, (size_t)h * stride);
    } else {
        // Partial-width: gather rows into staging buffer, then send.
        int row_bytes = w * 2;
        uint8_t *dst = spidma_state->dma_buf[0];
        size_t filled = 0;
        spi_transaction_t t;

        for (int row = 0; row < h; row++) {
            uint8_t *ptr = (uint8_t *)bufinfo.buf +
                           (y + row) * stride + x * 2;
            if (filled + row_bytes > SPIDMA_DMA_CHUNK_SZ && filled > 0) {
                memset(&t, 0, sizeof(t));
                t.length = filled * 8;
                t.tx_buffer = dst;
                send_blocking(disp, &t);
                filled = 0;
            }
            memcpy(dst + filled, ptr, row_bytes);
            filled += row_bytes;
        }
        if (filled > 0) {
            memset(&t, 0, sizeof(t));
            t.length = filled * 8;
            t.tx_buffer = dst;
            send_blocking(disp, &t);
        }
    }

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(spidma_push_rect_obj, 6, 6,
                                           spidma_push_rect);

// _spidma.busy(slot) -> bool
// Non-blocking check: if a result is available, consume it and return False.
static mp_obj_t spidma_busy(mp_obj_t slot_obj) {
    if (!spidma_state) return mp_const_false;

    int slot = mp_obj_get_int(slot_obj);
    if (slot < 0 || slot >= SPIDMA_MAX_DISPLAYS) return mp_const_false;

    spidma_display_t *disp = &spidma_state->displays[slot];
    if (!disp->pending) return mp_const_false;

    // Non-blocking: check if DMA completed without waiting
    spi_transaction_t *rtrans;
    esp_err_t err = spi_device_get_trans_result(disp->handle, &rtrans, 0);
    if (err == ESP_OK) {
        disp->pending = false;
        return mp_const_false;
    }
    return mp_const_true;  // still in progress
}
static MP_DEFINE_CONST_FUN_OBJ_1(spidma_busy_obj, spidma_busy);

// _spidma.wait(slot)
static mp_obj_t spidma_wait(mp_obj_t slot_obj) {
    if (!spidma_state) return mp_const_none;

    int slot = mp_obj_get_int(slot_obj);
    if (slot < 0 || slot >= SPIDMA_MAX_DISPLAYS) return mp_const_none;

    drain_display(&spidma_state->displays[slot]);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(spidma_wait_obj, spidma_wait);

// ── Module definition ──────────────────────────────────────────

static const mp_rom_map_elem_t spidma_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__),     MP_ROM_QSTR(MP_QSTR__spidma) },
    { MP_ROM_QSTR(MP_QSTR_init),         MP_ROM_PTR(&spidma_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_deinit),       MP_ROM_PTR(&spidma_deinit_obj) },
    { MP_ROM_QSTR(MP_QSTR_add_display),  MP_ROM_PTR(&spidma_add_display_obj) },
    { MP_ROM_QSTR(MP_QSTR_cmd),          MP_ROM_PTR(&spidma_cmd_obj) },
    { MP_ROM_QSTR(MP_QSTR_push),         MP_ROM_PTR(&spidma_push_obj) },
    { MP_ROM_QSTR(MP_QSTR_push_rect),    MP_ROM_PTR(&spidma_push_rect_obj) },
    { MP_ROM_QSTR(MP_QSTR_busy),         MP_ROM_PTR(&spidma_busy_obj) },
    { MP_ROM_QSTR(MP_QSTR_wait),         MP_ROM_PTR(&spidma_wait_obj) },
};
static MP_DEFINE_CONST_DICT(spidma_module_globals, spidma_module_globals_table);

const mp_obj_module_t spidma_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&spidma_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR__spidma, spidma_module);
