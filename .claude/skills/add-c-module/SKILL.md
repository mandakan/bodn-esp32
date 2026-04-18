---
name: add-c-module
description: Add a native C user-module (cmodules/<name>/) to the custom MicroPython firmware. Use when CPU-bound work (audio mixing, DMA display, LED animation, deterministic input scanning) needs to escape the Python VM. Covers the cmake plumbing, Python binding boilerplate, build-firmware.sh workflow, and the one-time ESP-IDF setup.
---

# Add a native C module

The Bodn firmware is stock MicroPython v1.27.0 plus a handful of C user-modules
under `cmodules/`. Each module is compiled into the firmware image at build
time and imported as `_<name>` from Python (the leading underscore marks it
as an internal module with a thin Python wrapper on top).

Existing modules: `_audiomix` (core-0 mixer), `_spidma` (DMA SPI displays),
`_draw` (bitmap fonts + blit primitives), `_mcpinput` (I2C input scan +
PCA9685 LED animation), `_neopixel` (pattern engine + RMT driver).

## Directory layout

```
cmodules/
├─ micropython.cmake              # top-level, `include()`s each sub-module
└─ <name>/
   ├─ micropython.cmake           # INTERFACE lib declaration
   ├─ <name>_mod.c (or <name>.c)  # Python bindings: MP_REGISTER_MODULE, method table
   ├─ <impl>.c/h                  # pure C implementation (testable without MP)
   └─ ...
```

Minimal `<name>/micropython.cmake`:

```cmake
add_library(usermod_<name> INTERFACE)

target_sources(usermod_<name> INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/<name>_mod.c
    ${CMAKE_CURRENT_LIST_DIR}/<impl>.c
)

target_include_directories(usermod_<name> INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)

target_link_libraries(usermod INTERFACE usermod_<name>)
```

Then add one line to `cmodules/micropython.cmake`:

```cmake
include(${CMAKE_CURRENT_LIST_DIR}/<name>/micropython.cmake)
```

## Python binding skeleton

`<name>_mod.c` registers the module and its method table. Minimal shape
(see `cmodules/neopixel/neopixel_mod.c` for a full example):

```c
#include "py/runtime.h"
#include "py/obj.h"

static mp_obj_t mymod_do_thing(mp_obj_t arg) {
    // ...
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mymod_do_thing_obj, mymod_do_thing);

static const mp_rom_map_elem_t mymod_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR__mymod) },
    { MP_ROM_QSTR(MP_QSTR_do_thing), MP_ROM_PTR(&mymod_do_thing_obj) },
    { MP_ROM_QSTR(MP_QSTR_SOME_CONST), MP_ROM_INT(42) },
};
static MP_DEFINE_CONST_DICT(mymod_module_globals, mymod_module_globals_table);

const mp_obj_module_t mymod_cmod_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&mymod_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR__mymod, mymod_cmod_module);
```

Argument parsing patterns:
- `MP_DEFINE_CONST_FUN_OBJ_{0,1,2,3}` — fixed-arity functions.
- `MP_DEFINE_CONST_FUN_OBJ_KW` + `mp_arg_parse_all` — keyword args.
- Read buffers with `mp_get_buffer_raise()`; return with `mp_obj_new_bytearray`.

## Building the firmware

One-time prerequisites:

```bash
git submodule update --init --recursive      # micropython/micropython @ v1.27.0
git clone -b v5.5.1 --recursive https://github.com/espressif/esp-idf.git ~/esp-idf
~/esp-idf/install.sh esp32s3
```

Every terminal session:

```bash
source ~/esp-idf/export.sh       # once per session
./tools/build-firmware.sh         # full build
./tools/build-firmware.sh flash   # build + flash
./tools/build-firmware.sh clean   # remove build-BODN_S3/
```

`build-firmware.sh` auto-sources ESP-IDF from `$IDF_PATH`, `~/esp-idf`,
`~/esp/esp-idf`, or `/opt/esp-idf` if the toolchain isn't already in `$PATH`.

## Core & task layout

Rule of thumb from existing modules:

- **Core 0** (protocol core) runs FreeRTOS tasks for real-time work —
  `_audiomix` mixer + I2S pump, `_neopixel` pattern engine + RMT,
  `_mcpinput` 500 Hz input scan.
- **Core 1** runs the MicroPython VM and `asyncio` tasks.
- Shared state uses lock-free SPSC ring buffers (`cmodules/audiomix/ringbuf.c`)
  or atomic reads/writes of small state — **no mutexes** across the core
  boundary.
- For display data paths, prefer ISR-driven DMA (see `_spidma`) over
  FreeRTOS tasks.
- Keep task stacks tight (the NeoPixel engine uses 3 KB). ESP32-S3 PSRAM
  **must not** be used for FreeRTOS stacks — DRAM only.

## sdkconfig changes

Board-specific sdkconfig layering lives in
`boards/BODN_S3/sdkconfig.board`. If your module needs a non-default
Kconfig (e.g. `CONFIG_FREERTOS_UNICORE=n`, IRAM-safe I2S), add it there.
The layering order is set in `boards/BODN_S3/mpconfigboard.cmake`.

## Python wrapper

Typical pattern in `firmware/bodn/<name>.py`:

```python
import _mymod

class MyEngine:
    def __init__(self, pin):
        _mymod.init(pin=pin)
    def do_thing(self):
        _mymod.do_thing()
```

There is **no Python fallback** in the current firmware — `audio.py`,
`arcade.py`, `patterns.py`, and `st7735.py` all hard-import their C
modules. If you want the device to run on stock MicroPython too, gate the
import with `try: import _mymod; except ImportError: ...` and write a
slow-path Python equivalent. CLAUDE.md still mentions a viper fallback for
`_audiomix` — that path has been removed.

## Verification

1. `./tools/build-firmware.sh` succeeds and produces
   `micropython/ports/esp32/build-BODN_S3/firmware.bin`.
2. On-device REPL: `import _<name>; dir(_<name>)` lists the expected
   functions.
3. Host tests for the pure-C parts (if any) can run under the MicroPython
   Unix port — see CLAUDE.md "MicroPython Unix port".

## Invariants

- `cmodules/<name>/micropython.cmake` must use `INTERFACE` libs and link
  into the global `usermod` target, not a new target.
- `MP_QSTR_*` identifiers must match exactly — typos silently produce an
  `AttributeError` at runtime, not a compile error.
- Committed firmware binaries (none currently) would need the same treatment
  as the Wokwi `.wasm` — see the `wokwi-chip-rebuild` skill.
- Performance-critical work belongs in C; UX glue belongs in MicroPython.
  Don't port game logic to C — the rules engines stay host-testable.
