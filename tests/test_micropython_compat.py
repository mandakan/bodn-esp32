"""Test that firmware modules import cleanly under the MicroPython Unix port.

This catches CPython-only APIs (str.capitalize, etc.) that would only fail
on-device at runtime. The Unix port binary is built from the micropython
submodule — see CLAUDE.md for build instructions.

Skipped automatically if the binary hasn't been built.
"""

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
MP_BINARY = (
    REPO_ROOT / "micropython" / "ports" / "unix" / "build-standard" / "micropython"
)
FW_DIR = REPO_ROOT / "firmware"

# Modules that import cleanly on the Unix port (no ESP32 hardware needed).
# Add new modules here as they're created — if a module uses machine/neopixel
# etc. at import time, it won't work and shouldn't be listed.
IMPORTABLE_MODULES = [
    # Pure logic
    "bodn.i18n",
    "bodn.debounce",
    "bodn.wav",
    "bodn.session",
    "bodn.simon_rules",
    "bodn.sortera_rules",
    "bodn.mystery_rules",
    "bodn.rulefollow_rules",
    "bodn.flode_rules",
    "bodn.life_rules",
    "bodn.qr",
    "bodn.chord",
    "bodn.gesture",
    "bodn.nfc",
    # UI (framebuf available in Unix port)
    "bodn.ui.screen",
    "bodn.ui.theme",
    "bodn.ui.widgets",
    "bodn.ui.icons",
    "bodn.ui.font_ext",
    "bodn.ui.home",
    "bodn.ui.launch_splash",
    "bodn.ui.sortera",
    "bodn.ui.soundboard",
    "bodn.ui.soundboard_secondary",
    "bodn.ui.nfc_provision",
]


@pytest.fixture(scope="module")
def mp_binary():
    if not MP_BINARY.exists():
        pytest.skip(
            "MicroPython Unix port not built. "
            "Run: make -C micropython/ports/unix submodules && "
            "make -C micropython/mpy-cross && "
            "make -C micropython/ports/unix"
        )
    return str(MP_BINARY)


@pytest.mark.parametrize("module", IMPORTABLE_MODULES)
def test_import_under_micropython(mp_binary, module):
    """Import a firmware module under the real MicroPython runtime."""
    result = subprocess.run(
        [mp_binary, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        timeout=10,
        env={"MICROPYPATH": str(FW_DIR)},
    )
    if result.returncode != 0:
        pytest.fail(f"MicroPython import failed:\n{result.stderr.strip()}")


def test_launch_splash_callback_executes(mp_binary):
    """Exercise make_launch_splash's returned callback under MicroPython.

    Importing the module isn't enough — the bug we hit (``_paint.first =
    True`` function-attribute assignment) only fails when the helper is
    actually called.  This spins up a stub TFT/theme, calls the helper,
    invokes the returned callback twice, and asserts no AttributeError.
    """
    script = r"""
import sys
sys.path.insert(0, "firmware")


class StubTFT:
    def rgb(self, r, g, b):
        return (r << 8) | g

    def fill(self, c):
        pass

    def fill_rect(self, x, y, w, h, c):
        pass

    def rect(self, x, y, w, h, c):
        pass

    def show(self):
        pass

    def show_rect(self, x, y, w, h):
        pass

    def text(self, s, x, y, c):
        pass

    def pixel(self, x, y, c):
        pass

    def blit(self, fb, x, y, key=-1):
        pass

    def mark_dirty(self, x, y, w, h):
        pass


class StubTheme:
    def __init__(self):
        self.width = 320
        self.height = 240
        self.BLACK = 0
        self.WHITE = 0xFFFF
        self.DIM = 0x4208
        self.CYAN = 0x07FF
        self.MUTED = 0x8410


class StubManager:
    def __init__(self):
        self.tft = StubTFT()
        self.theme = StubTheme()


from bodn import i18n
i18n.init("en")

from bodn.ui.launch_splash import make_launch_splash
cb = make_launch_splash(StubManager(), "simon")
cb(0, 1)   # first call: full-screen paint
cb(3, 10)  # subsequent call: bar-only update
print("OK")
"""
    result = subprocess.run(
        [mp_binary, "-c", script],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        pytest.fail(
            "launch splash callback failed under MicroPython:\n" + result.stderr.strip()
        )
    assert "OK" in result.stdout
