// spidma.h — DMA-backed SPI display driver for MicroPython
//
// Owns ESP-IDF SPI master on SPI2_HOST (MicroPython SPI(1)).
// Two display slots with independent CS, shared DC pin.
// Non-blocking push via spi_device_queue_trans() + ISR callback.

#ifndef SPIDMA_H
#define SPIDMA_H

#include <stdint.h>
#include <stdbool.h>
#include "driver/spi_master.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"

#define SPIDMA_MAX_DISPLAYS  2
#define SPIDMA_DMA_CHUNK_SZ  (32 * 1024)   // 32 KB — max safe DMA transfer on ESP32-S3

// ST7735/ILI9341/ST7789 shared commands
#define SPIDMA_CMD_CASET  0x2A
#define SPIDMA_CMD_RASET  0x2B
#define SPIDMA_CMD_RAMWR  0x2C

typedef struct {
    spi_device_handle_t handle;
    gpio_num_t dc_pin;
    int width;
    int height;
    int col_off;
    int row_off;
    volatile bool pending;          // queue_trans called but get_trans_result not yet
    spi_transaction_t data_trans;   // reused for async pixel DMA transfer
    bool initialized;
} spidma_display_t;

typedef struct {
    spi_host_device_t host;
    spidma_display_t displays[SPIDMA_MAX_DISPLAYS];
    int baudrate;
    bool bus_initialized;
    uint8_t *dma_buf[2];    // ping-pong DMA staging buffers (internal DRAM)
} spidma_state_t;

extern spidma_state_t *spidma_state;

#endif // SPIDMA_H
