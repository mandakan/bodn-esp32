# bodn/pca9685.py — PCA9685 16-channel 12-bit PWM driver over I2C
#
# Provides smooth LED dimming, backlight control, and future servo/motor
# support without consuming native ESP32 GPIOs.

from micropython import const

_MODE1 = const(0x00)
_MODE2 = const(0x04)
_LED0_ON_L = const(0x06)
_ALL_LED_ON_L = const(0xFA)
_PRE_SCALE = const(0xFE)

_MODE1_SLEEP = const(0x10)  # bit 4: oscillator off
_MODE1_AI = const(0x20)  # bit 5: auto-increment
_MODE1_RESTART = const(0x80)  # bit 7: restart

_OSC_CLOCK = 25_000_000  # 25 MHz internal oscillator


def _prescale(freq_hz):
    """Calculate prescaler value for a given PWM frequency.

    PCA9685 formula: prescale = round(osc_clock / (4096 * freq)) - 1
    Valid range: 3–255 → ~24 Hz–1526 Hz.
    """
    val = round(_OSC_CLOCK / (4096 * freq_hz)) - 1
    if val < 3:
        return 3
    if val > 255:
        return 255
    return val


class PCA9685:
    """PCA9685 16-channel 12-bit PWM driver.

    Args:
        i2c: machine.I2C (or SoftI2C) instance.
        addr: 7-bit I2C address (default 0x40).
    """

    def __init__(self, i2c, addr=0x40):
        self._i2c = i2c
        self._addr = addr
        self._buf = bytearray(4)
        self.reset()

    def reset(self):
        """Reset the PCA9685 to a known state: all outputs off, auto-increment on."""
        self._write_reg(_MODE1, _MODE1_SLEEP | _MODE1_AI)
        self._write_reg(_MODE2, 0x04)  # totem-pole outputs (default)
        # Turn off all channels
        self._write_block(_ALL_LED_ON_L, 0, 0, 0, 0x10)  # full-off bit
        # Wake up (clear sleep bit)
        self._write_reg(_MODE1, _MODE1_AI)

    def _write_reg(self, reg, value):
        self._i2c.writeto_mem(self._addr, reg, bytes([value]))

    def _read_reg(self, reg):
        buf = bytearray(1)
        self._i2c.readfrom_mem_into(self._addr, reg, buf)
        return buf[0]

    def _write_block(self, reg, b0, b1, b2, b3):
        self._buf[0] = b0
        self._buf[1] = b1
        self._buf[2] = b2
        self._buf[3] = b3
        self._i2c.writeto_mem(self._addr, reg, self._buf)

    def set_freq(self, freq_hz):
        """Set PWM frequency in Hz (24–1526).

        The prescaler can only be changed while the oscillator is stopped,
        so this briefly puts the chip to sleep.
        """
        prescale = _prescale(freq_hz)
        old_mode = self._read_reg(_MODE1)
        # Sleep (stop oscillator)
        self._write_reg(_MODE1, (old_mode & 0x7F) | _MODE1_SLEEP)
        self._write_reg(_PRE_SCALE, prescale)
        # Wake up and restart
        self._write_reg(_MODE1, old_mode | _MODE1_RESTART)

    def set_pwm(self, channel, on, off):
        """Set raw on/off tick counts for a channel (0–15).

        Args:
            channel: PWM channel 0–15.
            on: 12-bit tick when output turns ON (0–4095).
            off: 12-bit tick when output turns OFF (0–4095).
        """
        reg = _LED0_ON_L + 4 * channel
        self._write_block(reg, on & 0xFF, on >> 8, off & 0xFF, off >> 8)

    def set_duty(self, channel, duty):
        """Set duty cycle for a channel using a 12-bit value (0–4095).

        0 = fully off, 4095 = fully on.
        """
        if duty <= 0:
            # Full off: set the full-off bit (bit 4 of OFF_H)
            self._write_block(_LED0_ON_L + 4 * channel, 0, 0, 0, 0x10)
        elif duty >= 4095:
            # Full on: set the full-on bit (bit 4 of ON_H)
            self._write_block(_LED0_ON_L + 4 * channel, 0, 0x10, 0, 0)
        else:
            self.set_pwm(channel, 0, duty)

    def set_duty_batch(self, start_channel, duties):
        """Write multiple contiguous channels in a single I2C transaction.

        Uses PCA9685 auto-increment: one writeto_mem starting at the
        first channel's register, 4 bytes per channel.

        Args:
            start_channel: first PWM channel number (0–15).
            duties: list/tuple of 12-bit duty values, one per channel.
        """
        n = len(duties)
        buf = bytearray(n * 4)
        for i in range(n):
            d = duties[i]
            off = i * 4
            if d <= 0:
                buf[off] = 0
                buf[off + 1] = 0
                buf[off + 2] = 0
                buf[off + 3] = 0x10
            elif d >= 4095:
                buf[off] = 0
                buf[off + 1] = 0x10
                buf[off + 2] = 0
                buf[off + 3] = 0
            else:
                buf[off] = 0
                buf[off + 1] = 0
                buf[off + 2] = d & 0xFF
                buf[off + 3] = d >> 8
        reg = _LED0_ON_L + 4 * start_channel
        self._i2c.writeto_mem(self._addr, reg, buf)

    def set_all_duty(self, duty):
        """Set the same duty cycle on all 16 channels at once.

        Uses the ALL_LED registers for a single I2C transaction.
        """
        if duty <= 0:
            self._write_block(_ALL_LED_ON_L, 0, 0, 0, 0x10)
        elif duty >= 4095:
            self._write_block(_ALL_LED_ON_L, 0, 0x10, 0, 0)
        else:
            self._write_block(_ALL_LED_ON_L, 0, 0, duty & 0xFF, duty >> 8)
