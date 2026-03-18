"""Stubs for MicroPython hardware modules so tests can run on the host."""

import sys
import types

# Build a fake 'machine' module with Pin, SPI, I2S, PWM stubs.
machine = types.ModuleType("machine")


class FakePin:
    IN = 0
    OUT = 1
    PULL_UP = 2

    def __init__(self, pin_id, mode=None, pull=None):
        self.pin_id = pin_id
        self.mode = mode
        self.pull = pull
        self._value = 1  # pull-up default: high (not pressed)

    def value(self, v=None):
        if v is not None:
            self._value = v
        return self._value

    def on(self):
        self._value = 1

    def off(self):
        self._value = 0


class FakeSPI:
    def __init__(self, bus_id=None, **kwargs):
        self.bus_id = bus_id
        self.kwargs = kwargs

    def write(self, data):
        pass


class FakeI2S:
    RX = 0
    TX = 1
    MONO = 0
    STEREO = 1

    def __init__(self, _id, **kwargs):
        self.id = _id
        self.kwargs = kwargs
        self._buf = bytearray()

    def readinto(self, buf):
        for i in range(len(buf)):
            buf[i] = 0
        return len(buf)

    def write(self, buf):
        self._buf.extend(buf)
        return len(buf)

    def deinit(self):
        pass


class FakePWM:
    def __init__(self, pin, freq=1000, duty=0):
        self.pin = pin
        self._freq = freq
        self._duty = duty

    def freq(self, f=None):
        if f is not None:
            self._freq = f
        return self._freq

    def duty(self, d=None):
        if d is not None:
            self._duty = d
        return self._duty

    def deinit(self):
        pass


machine.Pin = FakePin
machine.SPI = FakeSPI
machine.I2S = FakeI2S
machine.PWM = FakePWM

sys.modules["machine"] = machine

# Stub 'framebuf' (used by display drivers)
framebuf = types.ModuleType("framebuf")
framebuf.RGB565 = 1


class FakeFrameBuffer:
    def __init__(self, buf, width, height, fmt):
        self._buf = buf
        self.width = width
        self.height = height

    def fill(self, color):
        pass

    def text(self, s, x, y, color=0xFFFF):
        pass

    def rect(self, x, y, w, h, color):
        pass

    def fill_rect(self, x, y, w, h, color):
        pass

    def pixel(self, x, y, color=None):
        return 0

    def line(self, x1, y1, x2, y2, color):
        pass

    def hline(self, x, y, w, color):
        pass

    def vline(self, x, y, h, color):
        pass


framebuf.FrameBuffer = FakeFrameBuffer
sys.modules["framebuf"] = framebuf

# Stub other common MicroPython modules
for mod_name in ("micropython", "uos", "usys", "utime"):
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)
