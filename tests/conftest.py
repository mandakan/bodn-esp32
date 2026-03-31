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

    def __init__(self, _id=0, **kwargs):
        self.id = _id
        self.kwargs = kwargs
        self._buf = bytearray()
        self.writes = []  # track individual write calls for testing

    def readinto(self, buf):
        for i in range(len(buf)):
            buf[i] = 0
        return len(buf)

    def write(self, buf):
        self._buf.extend(buf)
        self.writes.append(bytes(buf))
        return len(buf)

    def deinit(self):
        pass


class FakeHWEncoder:
    """Stub for machine.Encoder (PCNT hardware encoder)."""

    def __init__(self, unit_id, phase_a=None, phase_b=None, filter_ns=0):
        self._value = 0

    def value(self, v=None):
        if v is not None:
            self._value = v
        return self._value

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
machine.Encoder = FakeHWEncoder

sys.modules["machine"] = machine

# Stub 'esp32' module (SoC temperature sensor, wake sources, etc.)
esp32 = types.ModuleType("esp32")
esp32.raw_temperature = lambda: 42.0  # fake SoC temp in °C
esp32.gpio_wakeup = lambda *a, **kw: None
sys.modules["esp32"] = esp32

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

# Stub 'neopixel' module
neopixel = types.ModuleType("neopixel")


class FakeNeoPixel:
    def __init__(self, pin, n, **kwargs):
        self._leds = [(0, 0, 0)] * n
        self.n = n

    def __setitem__(self, idx, val):
        self._leds[idx] = val

    def __getitem__(self, idx):
        return self._leds[idx]

    def write(self):
        pass

    def fill(self, color):
        self._leds = [color] * self.n


neopixel.NeoPixel = FakeNeoPixel
sys.modules["neopixel"] = neopixel

# Stub 'network' module
network = types.ModuleType("network")
network.STA_IF = 0
network.AP_IF = 1


class FakeWLAN:
    def __init__(self, interface=0):
        self._active = False
        self._connected = False
        self._ip = "192.168.4.1"

    def active(self, val=None):
        if val is not None:
            self._active = val
        return self._active

    def isconnected(self):
        return self._connected

    def connect(self, ssid, password=""):
        self._connected = True

    def config(self, **kwargs):
        pass

    def ifconfig(self):
        return (self._ip, "255.255.255.0", "192.168.4.1", "0.0.0.0")


network.WLAN = FakeWLAN
sys.modules["network"] = network

# Stub 'ntptime' module
ntptime = types.ModuleType("ntptime")
ntptime.settime = lambda: None
sys.modules["ntptime"] = ntptime

# Stub 'uasyncio' — just alias to asyncio
try:
    import asyncio as _asyncio

    sys.modules["uasyncio"] = _asyncio
except ImportError:
    pass

# Stub 'ujson' — alias to json
try:
    import json as _json

    sys.modules["ujson"] = _json
except ImportError:
    pass

# Stub other common MicroPython modules
for mod_name in ("uos", "usys", "utime"):
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

# Stub 'micropython' module with const() identity function
_micropython = types.ModuleType("micropython")
_micropython.const = lambda x: x
sys.modules["micropython"] = _micropython

# Stub 'onewire' and 'ds18x20' modules for temperature sensor tests
_onewire = types.ModuleType("onewire")


class FakeOneWire:
    def __init__(self, pin):
        self.pin = pin


_onewire.OneWire = FakeOneWire
sys.modules["onewire"] = _onewire

_ds18x20 = types.ModuleType("ds18x20")


class FakeDS18X20:
    def __init__(self, ow):
        self._ow = ow
        self._temps = {}

    def scan(self):
        return list(self._temps.keys())

    def convert_temp(self):
        pass

    def read_temp(self, rom):
        return self._temps.get(rom, 25.0)


_ds18x20.DS18X20 = FakeDS18X20
sys.modules["ds18x20"] = _ds18x20
