"""Tests for the PCA9685 16-channel 12-bit PWM driver (pure logic, no hardware)."""

from bodn.pca9685 import PCA9685, _prescale


class FakeI2C:
    """Minimal I2C stub that records writes and returns preset reads."""

    def __init__(self):
        self.writes = []  # (addr, reg, data_bytes)
        self.regs = {}  # reg -> value

    def writeto_mem(self, addr, reg, data):
        self.writes.append((addr, reg, bytes(data)))
        # Store each byte at sequential registers (for block writes)
        for i, b in enumerate(data):
            self.regs[reg + i] = b

    def readfrom_mem_into(self, addr, reg, buf):
        buf[0] = self.regs.get(reg, 0x00)


class TestPrescaler:
    def test_1000hz(self):
        # round(25_000_000 / (4096 * 1000)) - 1 = 5
        assert _prescale(1000) == 5

    def test_50hz_servo(self):
        # round(25_000_000 / (4096 * 50)) - 1 = 121
        assert _prescale(50) == 121

    def test_1526hz_max(self):
        # round(25_000_000 / (4096 * 1526)) - 1 = 3
        assert _prescale(1526) == 3

    def test_24hz_min(self):
        # round(25_000_000 / (4096 * 24)) - 1 = 253
        assert _prescale(24) == 253

    def test_clamp_high_freq(self):
        """Frequencies above 1526 Hz clamp prescaler to minimum (3)."""
        assert _prescale(10000) == 3

    def test_clamp_low_freq(self):
        """Frequencies below 24 Hz clamp prescaler to maximum (255)."""
        assert _prescale(1) == 255


class TestPCA9685Init:
    def test_reset_turns_off_all_channels(self):
        i2c = FakeI2C()
        PCA9685(i2c, 0x40)
        # ALL_LED_OFF_H (0xFD) should have full-off bit set (0x10)
        all_led_writes = [(a, r, d) for a, r, d in i2c.writes if r == 0xFA]
        assert len(all_led_writes) >= 1
        # The ALL_LED block write: ON_L=0, ON_H=0, OFF_L=0, OFF_H=0x10
        assert all_led_writes[0] == (0x40, 0xFA, bytes([0, 0, 0, 0x10]))

    def test_custom_address(self):
        i2c = FakeI2C()
        PCA9685(i2c, 0x41)
        assert any(addr == 0x41 for addr, _, _ in i2c.writes)

    def test_auto_increment_enabled(self):
        i2c = FakeI2C()
        PCA9685(i2c, 0x40)
        # Final MODE1 write should have AI bit (0x20) set, SLEEP cleared
        mode1_writes = [(a, r, d) for a, r, d in i2c.writes if r == 0x00]
        last_mode1 = mode1_writes[-1][2][0]
        assert last_mode1 & 0x20  # auto-increment on
        assert not (last_mode1 & 0x10)  # sleep off


class TestSetDuty:
    def test_mid_duty(self):
        i2c = FakeI2C()
        pwm = PCA9685(i2c, 0x40)
        i2c.writes.clear()
        pwm.set_duty(0, 2048)
        # Channel 0 register = 0x06, OFF = 2048 → OFF_L=0x00, OFF_H=0x08
        assert i2c.writes[-1] == (0x40, 0x06, bytes([0, 0, 0x00, 0x08]))

    def test_full_off(self):
        i2c = FakeI2C()
        pwm = PCA9685(i2c, 0x40)
        i2c.writes.clear()
        pwm.set_duty(3, 0)
        # Channel 3 register = 0x06 + 12 = 0x12
        # Full off: OFF_H bit 4 set
        assert i2c.writes[-1] == (0x40, 0x12, bytes([0, 0, 0, 0x10]))

    def test_full_on(self):
        i2c = FakeI2C()
        pwm = PCA9685(i2c, 0x40)
        i2c.writes.clear()
        pwm.set_duty(5, 4095)
        # Channel 5 register = 0x06 + 20 = 0x1A
        # Full on: ON_H bit 4 set
        assert i2c.writes[-1] == (0x40, 0x1A, bytes([0, 0x10, 0, 0]))

    def test_channel_15(self):
        i2c = FakeI2C()
        pwm = PCA9685(i2c, 0x40)
        i2c.writes.clear()
        pwm.set_duty(15, 1000)
        # Channel 15 register = 0x06 + 60 = 0x42
        # OFF = 1000 → OFF_L=0xE8, OFF_H=0x03
        assert i2c.writes[-1] == (0x40, 0x42, bytes([0, 0, 0xE8, 0x03]))


class TestSetAllDuty:
    def test_all_off(self):
        i2c = FakeI2C()
        pwm = PCA9685(i2c, 0x40)
        i2c.writes.clear()
        pwm.set_all_duty(0)
        assert i2c.writes[-1] == (0x40, 0xFA, bytes([0, 0, 0, 0x10]))

    def test_all_on(self):
        i2c = FakeI2C()
        pwm = PCA9685(i2c, 0x40)
        i2c.writes.clear()
        pwm.set_all_duty(4095)
        assert i2c.writes[-1] == (0x40, 0xFA, bytes([0, 0x10, 0, 0]))

    def test_all_mid(self):
        i2c = FakeI2C()
        pwm = PCA9685(i2c, 0x40)
        i2c.writes.clear()
        pwm.set_all_duty(512)
        assert i2c.writes[-1] == (0x40, 0xFA, bytes([0, 0, 0x00, 0x02]))


class TestSetFreq:
    def test_set_freq_writes_prescaler(self):
        i2c = FakeI2C()
        pwm = PCA9685(i2c, 0x40)
        i2c.writes.clear()
        pwm.set_freq(1000)
        # Should write to PRE_SCALE register (0xFE) with value 5
        prescale_writes = [(a, r, d) for a, r, d in i2c.writes if r == 0xFE]
        assert len(prescale_writes) == 1
        assert prescale_writes[0][2] == bytes([5])

    def test_set_freq_sleeps_then_restarts(self):
        i2c = FakeI2C()
        pwm = PCA9685(i2c, 0x40)
        i2c.writes.clear()
        pwm.set_freq(50)
        mode1_writes = [(a, r, d) for a, r, d in i2c.writes if r == 0x00]
        # First MODE1 write: sleep bit set
        assert mode1_writes[0][2][0] & 0x10
        # Last MODE1 write: restart bit set
        assert mode1_writes[-1][2][0] & 0x80


class TestSetPwm:
    def test_raw_pwm(self):
        i2c = FakeI2C()
        pwm = PCA9685(i2c, 0x40)
        i2c.writes.clear()
        pwm.set_pwm(7, 100, 3000)
        # Channel 7 register = 0x06 + 28 = 0x22
        # ON=100 → ON_L=0x64, ON_H=0x00
        # OFF=3000 → OFF_L=0xB8, OFF_H=0x0B
        assert i2c.writes[-1] == (0x40, 0x22, bytes([0x64, 0x00, 0xB8, 0x0B]))
