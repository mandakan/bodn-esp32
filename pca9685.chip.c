// pca9685.chip.c — PCA9685 16-channel 12-bit PWM simulation for Wokwi
//
// Implements the I2C register protocol used by the bodn MicroPython driver
// (writeto_mem / readfrom_mem_into).
//
// Supported registers:
//   0x00 MODE1       mode register 1 (SLEEP, AI, RESTART)
//   0x04 MODE2       mode register 2
//   0x06–0x45        LEDn_ON_L/H, LEDn_OFF_L/H (channels 0–15)
//   0xFA–0xFD        ALL_LED_ON_L/H, ALL_LED_OFF_L/H
//   0xFE PRE_SCALE   prescaler for PWM frequency
//
// SPDX-License-Identifier: MIT

#include "wokwi-api.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define I2C_BASE_ADDRESS 0x40
#define NUM_CHANNELS     16
#define NUM_ADDR_BITS    6
#define NUM_REGS         0xFF

#define REG_MODE1        0x00
#define REG_MODE2        0x04
#define REG_LED0_ON_L    0x06
#define REG_ALL_LED_ON_L 0xFA
#define REG_PRE_SCALE    0xFE

#define MODE1_SLEEP      0x10
#define MODE1_AI         0x20
#define MODE1_RESTART    0x80

typedef struct {
  uint8_t address;
  pin_t   addr_pins[NUM_ADDR_BITS];
  pin_t   pwm_pins[NUM_CHANNELS];
  pin_t   oe_pin;

  uint8_t reg[NUM_REGS];  // register file
  uint8_t reg_ptr;
  bool    reg_ptr_set;

  i2c_dev_t    i2c_dev;
  i2c_config_t i2c_config;
} chip_state_t;

// ── PWM output update ────────────────────────────────────────────────────────

static void update_pwm_pin(chip_state_t *chip, int ch) {
  uint8_t base = REG_LED0_ON_L + 4 * ch;
  uint16_t on_val  = chip->reg[base] | ((chip->reg[base + 1] & 0x1F) << 8);
  uint16_t off_val = chip->reg[base + 2] | ((chip->reg[base + 3] & 0x1F) << 8);

  bool full_on  = chip->reg[base + 1] & 0x10;
  bool full_off = chip->reg[base + 3] & 0x10;

  if (full_off) {
    pin_mode(chip->pwm_pins[ch], OUTPUT_LOW);
  } else if (full_on) {
    pin_mode(chip->pwm_pins[ch], OUTPUT_HIGH);
  } else {
    // Simplified: set pin high if duty > 0
    if (off_val > on_val) {
      pin_mode(chip->pwm_pins[ch], OUTPUT_HIGH);
    } else {
      pin_mode(chip->pwm_pins[ch], OUTPUT_LOW);
    }
  }
}

static void update_all_channels(chip_state_t *chip) {
  for (int ch = 0; ch < NUM_CHANNELS; ch++) {
    update_pwm_pin(chip, ch);
  }
}

// ── register write ───────────────────────────────────────────────────────────

static void write_reg(chip_state_t *chip, uint8_t addr, uint8_t val) {
  chip->reg[addr] = val;

  if (addr == REG_MODE1) {
    // Handle restart
    if (val & MODE1_RESTART) {
      chip->reg[REG_MODE1] = val & ~MODE1_RESTART;
    }
    return;
  }

  // Individual channel registers
  if (addr >= REG_LED0_ON_L && addr < REG_LED0_ON_L + 4 * NUM_CHANNELS) {
    int ch = (addr - REG_LED0_ON_L) / 4;
    update_pwm_pin(chip, ch);
    return;
  }

  // ALL_LED registers: copy to all individual channels
  if (addr >= REG_ALL_LED_ON_L && addr <= REG_ALL_LED_ON_L + 3) {
    int offset = addr - REG_ALL_LED_ON_L;
    for (int ch = 0; ch < NUM_CHANNELS; ch++) {
      chip->reg[REG_LED0_ON_L + 4 * ch + offset] = val;
    }
    update_all_channels(chip);
    return;
  }
}

// ── I2C callbacks ────────────────────────────────────────────────────────────

static bool on_i2c_connect(void *user_data, uint32_t address, bool read) {
  chip_state_t *chip = (chip_state_t *)user_data;
  if (!read) {
    chip->reg_ptr_set = false;
  }
  return true;
}

static uint8_t on_i2c_read(void *user_data) {
  chip_state_t *chip = (chip_state_t *)user_data;
  uint8_t val = chip->reg[chip->reg_ptr];
  if (chip->reg[REG_MODE1] & MODE1_AI) {
    chip->reg_ptr++;
    // Skip reserved addresses during auto-increment
  }
  return val;
}

static bool on_i2c_write(void *user_data, uint8_t data) {
  chip_state_t *chip = (chip_state_t *)user_data;
  if (!chip->reg_ptr_set) {
    chip->reg_ptr     = data;
    chip->reg_ptr_set = true;
  } else {
    write_reg(chip, chip->reg_ptr, data);
    if (chip->reg[REG_MODE1] & MODE1_AI) {
      chip->reg_ptr++;
    }
  }
  return true;
}

static void on_i2c_disconnect(void *user_data) {
  (void)user_data;
}

// ── address pin handling ─────────────────────────────────────────────────────

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

// ── chip init ────────────────────────────────────────────────────────────────

void chip_init(void) {
  chip_state_t *chip = calloc(1, sizeof(chip_state_t));

  // Power-on defaults
  chip->reg[REG_MODE1] = MODE1_SLEEP;  // oscillator off at power-on
  chip->reg[REG_PRE_SCALE] = 0x1E;     // default prescaler (200 Hz)

  static const char *addr_names[] = {"A0", "A1", "A2", "A3", "A4", "A5"};
  static const char *pwm_names[] = {
    "PWM0",  "PWM1",  "PWM2",  "PWM3",
    "PWM4",  "PWM5",  "PWM6",  "PWM7",
    "PWM8",  "PWM9",  "PWM10", "PWM11",
    "PWM12", "PWM13", "PWM14", "PWM15",
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

  for (int i = 0; i < NUM_CHANNELS; i++) {
    chip->pwm_pins[i] = pin_init(pwm_names[i], OUTPUT_LOW);
  }

  chip->oe_pin = pin_init("OE", INPUT);

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

  printf("PCA9685 ready @ 0x%02x\n", chip->address);
}
