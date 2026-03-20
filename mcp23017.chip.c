// mcp23017.chip.c — MCP23017 I2C GPIO expander simulation for Wokwi
//
// Implements the register-addressed I2C protocol used by the bodn
// MicroPython driver (writeto_mem / readfrom_mem_into).
//
// Supported registers (IOCON.BANK=0 default layout):
//   0x00 IODIRA   0x01 IODIRB   direction (1=input, 0=output)
//   0x0C GPPUA    0x0D GPPUB    pull-ups
//   0x12 GPIOA    0x13 GPIOB    GPIO read / output latch write
//   0x14 OLATA    0x15 OLATB    output latches
//
// All other register addresses are accepted but ignored.
//
// SPDX-License-Identifier: MIT

#include "wokwi-api.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define I2C_BASE_ADDRESS 0x20
#define NUM_GPIO         16
#define NUM_ADDR_BITS    3
#define NUM_REGS         0x16  // registers 0x00–0x15

#define REG_IODIRA  0x00
#define REG_IODIRB  0x01
#define REG_GPPUA   0x0C
#define REG_GPPUB   0x0D
#define REG_GPIOA   0x12
#define REG_GPIOB   0x13
#define REG_OLATA   0x14
#define REG_OLATB   0x15

typedef struct {
  uint8_t address;
  pin_t   addr_pins[NUM_ADDR_BITS];
  pin_t   io[NUM_GPIO];

  pin_watch_config_t io_watch;

  uint8_t reg[NUM_REGS];   // register file
  uint8_t reg_ptr;         // current register pointer (persists across transactions)
  bool    reg_ptr_set;     // true after the address byte of a write transaction

  i2c_dev_t    i2c_dev;
  i2c_config_t i2c_config;
} chip_state_t;

// ── pin helpers ───────────────────────────────────────────────────────────────

static void update_pin(chip_state_t *chip, int i) {
  pin_t   p    = chip->io[i];
  int     port = i / 8;
  uint8_t bit  = 1 << (i % 8);

  uint8_t iodir = chip->reg[port == 0 ? REG_IODIRA : REG_IODIRB];
  uint8_t gppu  = chip->reg[port == 0 ? REG_GPPUA  : REG_GPPUB];
  uint8_t olat  = chip->reg[port == 0 ? REG_OLATA  : REG_OLATB];

  pin_watch_stop(p);
  if (iodir & bit) {
    pin_mode(p, (gppu & bit) ? INPUT_PULLUP : INPUT);
    pin_watch(p, &chip->io_watch);
  } else {
    pin_mode(p, (olat & bit) ? OUTPUT_HIGH : OUTPUT_LOW);
  }
}

static uint8_t read_gpio_port(chip_state_t *chip, int port) {
  uint8_t iodir = chip->reg[port == 0 ? REG_IODIRA : REG_IODIRB];
  uint8_t olat  = chip->reg[port == 0 ? REG_OLATA  : REG_OLATB];
  uint8_t val   = 0;
  for (int i = 0; i < 8; i++) {
    if (iodir & (1 << i)) {
      if (pin_read(chip->io[port * 8 + i])) val |= (1 << i);
    } else {
      if (olat & (1 << i)) val |= (1 << i);
    }
  }
  return val;
}

// ── register write ────────────────────────────────────────────────────────────

static void write_reg(chip_state_t *chip, uint8_t addr, uint8_t val) {
  if (addr >= NUM_REGS) return;
  chip->reg[addr] = val;

  switch (addr) {
    case REG_IODIRA:
      for (int i = 0; i < 8; i++) update_pin(chip, i);
      break;
    case REG_IODIRB:
      for (int i = 0; i < 8; i++) update_pin(chip, 8 + i);
      break;
    case REG_GPPUA:
      for (int i = 0; i < 8; i++)
        if (chip->reg[REG_IODIRA] & (1 << i)) update_pin(chip, i);
      break;
    case REG_GPPUB:
      for (int i = 0; i < 8; i++)
        if (chip->reg[REG_IODIRB] & (1 << i)) update_pin(chip, 8 + i);
      break;
    case REG_GPIOA:
    case REG_OLATA:
      chip->reg[REG_OLATA] = val;
      for (int i = 0; i < 8; i++)
        if (!(chip->reg[REG_IODIRA] & (1 << i))) update_pin(chip, i);
      break;
    case REG_GPIOB:
    case REG_OLATB:
      chip->reg[REG_OLATB] = val;
      for (int i = 0; i < 8; i++)
        if (!(chip->reg[REG_IODIRB] & (1 << i))) update_pin(chip, 8 + i);
      break;
  }
}

// ── I2C callbacks ─────────────────────────────────────────────────────────────

// MicroPython readfrom_mem_into generates two transactions:
//   1. connect(write) → write(reg) → disconnect   ← sets reg_ptr
//   2. connect(read)  → read()     → disconnect   ← returns reg value
// reg_ptr must persist across the disconnect between them.

static bool on_i2c_connect(void *user_data, uint32_t address, bool read) {
  chip_state_t *chip = (chip_state_t *)user_data;
  if (!read) {
    chip->reg_ptr_set = false;  // next write byte is the register address
  } else {
    // Snapshot live pin values into the GPIO registers before the read
    chip->reg[REG_GPIOA] = read_gpio_port(chip, 0);
    chip->reg[REG_GPIOB] = read_gpio_port(chip, 1);
  }
  return true;
}

static uint8_t on_i2c_read(void *user_data) {
  chip_state_t *chip = (chip_state_t *)user_data;
  uint8_t val = (chip->reg_ptr < NUM_REGS) ? chip->reg[chip->reg_ptr] : 0xFF;
  chip->reg_ptr = (chip->reg_ptr + 1) % NUM_REGS;
  return val;
}

static bool on_i2c_write(void *user_data, uint8_t data) {
  chip_state_t *chip = (chip_state_t *)user_data;
  if (!chip->reg_ptr_set) {
    chip->reg_ptr     = data;
    chip->reg_ptr_set = true;
  } else {
    write_reg(chip, chip->reg_ptr, data);
    chip->reg_ptr = (chip->reg_ptr + 1) % NUM_REGS;
  }
  return true;
}

static void on_i2c_disconnect(void *user_data) {
  (void)user_data;
}

// ── address pin handling ──────────────────────────────────────────────────────

static uint8_t calc_address(chip_state_t *chip) {
  uint8_t addr = I2C_BASE_ADDRESS;
  for (int i = 0; i < NUM_ADDR_BITS; i++)
    if (pin_read(chip->addr_pins[i])) addr |= (1 << i);
  return addr;
}

static void on_addr_change(void *user_data, pin_t pin, uint32_t value) {
  chip_state_t *chip = (chip_state_t *)user_data;
  chip->address = calc_address(chip);
}

static void on_io_change(void *user_data, pin_t pin, uint32_t value) {
  // Values are read on demand in on_i2c_connect(read=true); nothing to do here.
}

// ── chip init ─────────────────────────────────────────────────────────────────

void chip_init(void) {
  chip_state_t *chip = calloc(1, sizeof(chip_state_t));

  // Power-on defaults: all pins are inputs, no pull-ups, output latches low
  chip->reg[REG_IODIRA] = 0xFF;
  chip->reg[REG_IODIRB] = 0xFF;

  chip->io_watch.edge       = BOTH;
  chip->io_watch.pin_change = on_io_change;
  chip->io_watch.user_data  = chip;

  static const char *addr_names[] = {"A0", "A1", "A2"};
  static const char *io_names[]   = {
    "GPA0", "GPA1", "GPA2", "GPA3", "GPA4", "GPA5", "GPA6", "GPA7",
    "GPB0", "GPB1", "GPB2", "GPB3", "GPB4", "GPB5", "GPB6", "GPB7",
  };

  pin_watch_config_t addr_watch = {
    .edge       = BOTH,
    .pin_change = on_addr_change,
    .user_data  = chip,
  };
  for (int i = 0; i < NUM_ADDR_BITS; i++) {
    chip->addr_pins[i] = pin_init(addr_names[i], INPUT);
    pin_watch(chip->addr_pins[i], &addr_watch);
  }

  for (int i = 0; i < NUM_GPIO; i++) {
    chip->io[i] = pin_init(io_names[i], INPUT_PULLUP);
    pin_watch(chip->io[i], &chip->io_watch);
  }

  chip->address            = calc_address(chip);
  chip->i2c_config.address = chip->address;
  chip->i2c_config.scl     = pin_init("SCL", INPUT_PULLUP);
  chip->i2c_config.sda     = pin_init("SDA", INPUT_PULLUP);
  chip->i2c_config.connect    = on_i2c_connect;
  chip->i2c_config.read       = on_i2c_read;
  chip->i2c_config.write      = on_i2c_write;
  chip->i2c_config.disconnect = on_i2c_disconnect;
  chip->i2c_config.user_data  = chip;

  chip->i2c_dev = i2c_init(&chip->i2c_config);

  printf("MCP23017 ready @ 0x%02x\n", chip->address);
}
