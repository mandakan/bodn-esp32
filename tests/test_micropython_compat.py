"""Test that firmware modules import cleanly under the MicroPython Unix port.

This catches CPython-only APIs (str.capitalize, etc.) that would only fail
on-device at runtime. The Unix port binary is built from the micropython
submodule — see CLAUDE.md for build instructions.

Skipped automatically if the binary hasn't been built.
"""

import subprocess
import sys
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
    "bodn.ui.sequencer",
    "bodn.ui.sortera",
    "bodn.ui.soundboard",
    "bodn.ui.soundboard_secondary",
    "bodn.ui.highfive",
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
