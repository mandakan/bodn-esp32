"""Stubs for MicroPython hardware modules so tests can run on the host."""

import sys
import time
import types

# Patch time module with MicroPython tick functions if missing
if not hasattr(time, "ticks_ms"):
    time.ticks_ms = lambda: int(time.time() * 1000) & 0x3FFFFFFF
if not hasattr(time, "ticks_diff"):
    time.ticks_diff = lambda a, b: (a - b + 0x20000000) % 0x40000000 - 0x20000000
if not hasattr(time, "ticks_add"):
    time.ticks_add = lambda a, b: (a + b) & 0x3FFFFFFF
if not hasattr(time, "sleep_ms"):
    time.sleep_ms = lambda ms: time.sleep(ms / 1000)

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


class FakeADC:
    ATTN_0DB = 0
    ATTN_2_5DB = 1
    ATTN_6DB = 2
    ATTN_11DB = 3
    WIDTH_9BIT = 9
    WIDTH_10BIT = 10
    WIDTH_11BIT = 11
    WIDTH_12BIT = 12

    def __init__(self, pin=None):
        self._raw = 2000

    def atten(self, a):
        pass

    def width(self, w):
        pass

    def read(self):
        return self._raw

    def read_uv(self):
        return self._raw * 305  # rough uV approximation


class FakeI2C:
    def __init__(self, bus_id=0, scl=None, sda=None, freq=400_000):
        self._devices = {}

    def scan(self):
        return list(self._devices.keys())

    def writeto_mem(self, addr, reg, data):
        pass

    def readfrom_mem_into(self, addr, reg, buf):
        pass


class FakeRTC:
    def __init__(self):
        self._datetime = (2026, 1, 1, 0, 0, 0, 0, 0)

    def datetime(self, dt=None):
        if dt is not None:
            self._datetime = dt
        return self._datetime


machine.Pin = FakePin
machine.SPI = FakeSPI
machine.I2S = FakeI2S
machine.I2C = FakeI2C
machine.PWM = FakePWM
machine.ADC = FakeADC
machine.RTC = FakeRTC
machine.Encoder = FakeHWEncoder
machine.lightsleep = lambda ms=0: None
machine.deepsleep = lambda ms=0: None

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

    # MicroPython exposes asyncio.sleep_ms — add it on CPython for tests.
    if not hasattr(_asyncio, "sleep_ms"):
        _asyncio.sleep_ms = lambda ms: _asyncio.sleep(ms / 1000)

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

# Stub '_neopixel' C module for host tests
_neopixel_stub = types.ModuleType("_neopixel")


def _noop(*a, **kw):
    pass


for _fn in (
    "init",
    "deinit",
    "zone_pattern",
    "zone_off",
    "zone_brightness",
    "set_pixel",
    "set_pixels",
    "clear_pixel",
    "clear_pixels",
    "clear_all_overrides",
    "set_override",
    "clear_override",
    "pause",
    "resume",
):
    setattr(_neopixel_stub, _fn, _noop)
_neopixel_stub.frame = lambda: 0
_neopixel_stub.stats = lambda: {}
for _name, _val in (
    ("PAT_OFF", 0),
    ("PAT_SOLID", 1),
    ("PAT_RAINBOW", 2),
    ("PAT_PULSE", 3),
    ("PAT_CHASE", 4),
    ("PAT_SPARKLE", 5),
    ("PAT_BOUNCE", 6),
    ("PAT_WAVE", 7),
    ("PAT_SPLIT", 8),
    ("PAT_FILL", 9),
    ("ZONE_STICK_A", 0),
    ("ZONE_STICK_B", 1),
    ("ZONE_LID_RING", 2),
    ("OVERRIDE_NONE", 0),
    ("OVERRIDE_BLACK", 1),
    ("OVERRIDE_SOLID", 2),
    ("OVERRIDE_PULSE", 3),
    ("OVERRIDE_FADE", 4),
):
    setattr(_neopixel_stub, _name, _val)
sys.modules["_neopixel"] = _neopixel_stub

# Stub '_audiomix' C module for host tests
_audiomix_stub = types.ModuleType("_audiomix")
_audiomix_stub.NUM_VOICES = 16
_audiomix_stub.SCOPE_SAMPLES = 512
_audiomix_stub.WAVE_SQUARE = 0
_audiomix_stub.WAVE_SINE = 1
_audiomix_stub.WAVE_SAWTOOTH = 2
_audiomix_stub.WAVE_NOISE = 3


class _FakeAudiomix:
    """Tracks voice state for test assertions."""

    def __init__(self):
        self._voices = {}  # idx -> {"active": bool, ...}
        self._volume = 10

    def init(self, **kwargs):
        self._voices.clear()
        self._volume = 10

    def set_volume(self, vol):
        self._volume = max(0, min(100, vol))

    def get_volume(self):
        return self._volume

    def voice_active(self, idx):
        return self._voices.get(idx, {}).get("active", False)

    def voice_stop(self, idx):
        if idx in self._voices:
            self._voices[idx]["active"] = False

    def voice_tone(self, idx, freq, duration_ms, wave_id):
        self._voices[idx] = {"active": True, "type": "tone", "freq": freq}

    def voice_tone_sustained(self, idx, freq, wave_id):
        self._voices[idx] = {
            "active": True,
            "type": "tone_sustained",
            "freq": freq,
            "wave": wave_id,
        }

    def voice_set_freq(self, idx, freq):
        if idx in self._voices:
            self._voices[idx]["freq"] = freq

    def voice_set_wave(self, idx, wave_id):
        if idx in self._voices:
            self._voices[idx]["wave"] = wave_id

    def voice_set_gain(self, idx, gain):
        if idx in self._voices:
            self._voices[idx]["gain"] = gain

    def voice_set_pitch_lfo(self, idx, rate_cHz, depth_cents):
        if idx in self._voices:
            self._voices[idx]["pitch_lfo"] = (rate_cHz, depth_cents)

    def voice_set_amp_lfo(self, idx, rate_cHz, depth_q15):
        if idx in self._voices:
            self._voices[idx]["amp_lfo"] = (rate_cHz, depth_q15)

    def voice_set_bend(self, idx, cents_per_s, limit_cents):
        if idx in self._voices:
            self._voices[idx]["bend"] = (cents_per_s, limit_cents)

    def voice_set_stutter(self, idx, rate_cHz, duty_q15):
        if idx in self._voices:
            self._voices[idx]["stutter"] = (rate_cHz, duty_q15)

    def voice_clear_mods(self, idx):
        if idx in self._voices:
            for k in ("pitch_lfo", "amp_lfo", "bend", "stutter"):
                self._voices[idx].pop(k, None)

    def scope_peek(self, dst):
        # Fill with zeros — tests just need the call to succeed.
        for i in range(len(dst)):
            dst[i] = 0
        return len(dst) // 2

    def voice_play_buffer(self, idx, data, length, loop):
        self._voices[idx] = {"active": True, "type": "buffer"}

    def voice_start_stream(self, idx, loop):
        self._voices[idx] = {"active": True, "type": "stream"}

    def voice_feed(self, idx, buf, n):
        pass

    def voice_eof(self, idx):
        pass

    def voice_sequence(self, idx, packed):
        self._voices[idx] = {"active": True, "type": "sequence"}

    def ringbuf_space(self, idx):
        return 0  # no space — prevents infinite feed loops in tests

    def clock_start(self, bpm, steps):
        pass

    def clock_stop(self):
        pass

    def clock_get_step(self):
        return 0

    def clock_clear_grid(self):
        pass

    def clock_set_perc(self, step, mask):
        pass

    def clock_set_perc_buffer(self, track, buf, length):
        pass

    def clock_set_steps(self, n):
        pass

    def clock_set_bpm(self, bpm):
        pass

    def clock_set_tone_track(self, track, voice, mask):
        pass

    def clock_set_tone_step(self, track, step, freq, dur, wave, *args):
        pass

    def clock_preview(self, track):
        pass

    def clock_tone_preview(self, track):
        pass


_fake_audiomix = _FakeAudiomix()
for _attr in (
    "init",
    "set_volume",
    "get_volume",
    "voice_active",
    "voice_stop",
    "voice_tone",
    "voice_play_buffer",
    "voice_start_stream",
    "voice_feed",
    "voice_eof",
    "voice_sequence",
    "voice_tone_sustained",
    "voice_set_freq",
    "voice_set_wave",
    "voice_set_gain",
    "voice_set_pitch_lfo",
    "voice_set_amp_lfo",
    "voice_set_bend",
    "voice_set_stutter",
    "voice_clear_mods",
    "scope_peek",
    "ringbuf_space",
    "clock_start",
    "clock_stop",
    "clock_get_step",
    "clock_clear_grid",
    "clock_set_perc",
    "clock_set_perc_buffer",
    "clock_set_steps",
    "clock_set_bpm",
    "clock_set_tone_track",
    "clock_set_tone_step",
    "clock_preview",
    "clock_tone_preview",
):
    setattr(_audiomix_stub, _attr, getattr(_fake_audiomix, _attr))
sys.modules["_audiomix"] = _audiomix_stub

# Stub '_mcpinput' C module (native MCP23017 scan + LED engine on core 0)
_mcpinput_stub = types.ModuleType("_mcpinput")


def _mcpinput_noop(*a, **kw):
    pass


_mcpinput_stub.init = _mcpinput_noop
_mcpinput_stub.get_events = lambda: []
_mcpinput_stub.read_state = lambda: 0xFFFF
_mcpinput_stub.led_init = lambda **kw: True
_mcpinput_stub.led_anim = _mcpinput_noop
_mcpinput_stub.led_anim_all = _mcpinput_noop
_mcpinput_stub.led_flash = _mcpinput_noop
_mcpinput_stub.led_tick_flash = lambda: False
_mcpinput_stub.led_mode = _mcpinput_noop
_mcpinput_stub.led_set_whack_pins = _mcpinput_noop
_mcpinput_stub.led_set_whack_target = _mcpinput_noop
_mcpinput_stub.led_get_whack_result = lambda: (False, False)
for _name, _val in (
    ("PRESS", 1),
    ("RELEASE", 2),
    ("ANIM_OFF", 0),
    ("ANIM_GLOW", 1),
    ("ANIM_ON", 2),
    ("ANIM_PULSE", 3),
    ("ANIM_BLINK", 4),
    ("ANIM_WAVE", 5),
    ("LED_PYTHON", 0),
    ("LED_BEAT_SYNC", 1),
    ("LED_WHACK", 2),
):
    setattr(_mcpinput_stub, _name, _val)
sys.modules["_mcpinput"] = _mcpinput_stub
