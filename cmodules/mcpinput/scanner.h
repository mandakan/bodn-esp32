// scanner.h — MCP23017 scanning task and I2C management

#ifndef MCPINPUT_SCANNER_H
#define MCPINPUT_SCANNER_H

#include "mcpinput.h"

// I2C + MCP configuration passed from Python
typedef struct {
    int pin_sda;
    int pin_scl;
    int freq;
    int mcp_addr;
    int debounce_ms;
    int int_pin;        // -1 = polling mode
} scanner_config_t;

// Allocate state, configure I2C + MCP, start core 0 task.
// On success: sets *state_out and returns NULL.
// On failure: returns a static error string.
const char *scanner_init(const scanner_config_t *cfg, mcpinput_state_t **state_out);

// Stop task, release I2C, free state.
void scanner_deinit(mcpinput_state_t *state);

// Mutex-protected I2C write: addr + memaddr + data.
// Returns ESP_OK on success.
int scanner_i2c_write(mcpinput_state_t *state, uint8_t addr,
                      uint8_t reg, const uint8_t *data, size_t len);

// Mutex-protected I2C read: addr + memaddr, reads into buf.
// Returns ESP_OK on success.
int scanner_i2c_read(mcpinput_state_t *state, uint8_t addr,
                     uint8_t reg, uint8_t *buf, size_t len);

// Mutex-protected I2C bus scan: returns number of addresses found,
// writes found addresses into addrs (max addrs_size entries).
int scanner_i2c_scan(mcpinput_state_t *state, uint8_t *addrs, size_t addrs_size);

#endif // MCPINPUT_SCANNER_H
