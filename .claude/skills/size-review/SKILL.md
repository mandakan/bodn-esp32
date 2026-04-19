---
name: size-review
description: Audit the custom MicroPython firmware for size footprint — find features that are compiled in but never imported, and catch imports of features that have been disabled. Use when modifying boards/BODN_S3/ sdkconfig or mpconfigboard files, when adding a new firmware Python import that may pull in an IDF component, or when triaging "not enough space on device" OTA failures. Complements perf-review but for flash usage instead of frame time.
---

# Size review (ESP32-S3 custom firmware)

MicroPython's ESP32 port is **not minimal by default** — it inherits a long
list of ESP-IDF components (BLE stack, full TLS, PPP, cert bundles, TinyUSB
on S3) that the Bodn firmware never touches. Every enabled-but-unused feature
eats into the 2.4 MB OTA app slot and leaves less room in the VFS for Python
code + OTA staging, which is what caused the "not enough space" failures.

The authoritative tool is:

```bash
uv run python tools/size-review.py            # report, non-zero on hard fails
uv run python tools/size-review.py --strict   # warnings fail too
```

It scans every `import` in `firmware/` and the effective sdkconfig merged
from `boards/BODN_S3/mpconfigboard.cmake`'s `SDKCONFIG_DEFAULTS`. The
pre-commit hook runs it when `boards/BODN_S3/**` or `firmware/**/*.py` is
staged.

## Two kinds of mismatch

1. **Imported but disabled — HARD FAIL** (exit 1)
   A Python file imports a module whose backing feature has been turned off.
   The device will raise `ImportError` on boot. Either re-enable the
   feature (and accept the size cost) or remove the import.

2. **Enabled but unused — WARNING**
   Feature is compiled in, nothing imports it. Review whether it's actually
   needed; if not, the report prints the exact sdkconfig line(s) to add.

## Reading the output

```
state  used  feature
------ ----- -------
on     no    BLE (NimBLE stack)
        WARN: enabled but no Python code imports it
        hint: drop sdkconfig.ble from SDKCONFIG_DEFAULTS ...
```

- `state` — derived from the effective sdkconfig (inherited files + board
  override). `on` / `off` / `?` (unknown, usually a MicroPython C define the
  analyser doesn't parse).
- `used` — whether any firmware file imports one of the feature's gateway
  modules (e.g. `bluetooth`, `ssl`, `btree`).

`?` rows aren't warnings — the analyser just can't determine state from
sdkconfig alone. The import check still runs on them.

## Things this tool deliberately doesn't do

- **Doesn't measure actual flash usage.** For that, build the firmware and
  run `idf.py size` / `idf.py size-components`. The analyser is a static
  lint; some kconfig switches have huge transitive effects while others do
  almost nothing. Measure before celebrating.
- **Doesn't parse C macro conditionals** in `mpconfigport.h`. If a
  MICROPY_PY_* define has a complex default, the feature shows as `?`.
  Listed features without sdkconfig keys (WebREPL, btree, binascii, etc.)
  are import-only checks.
- **Doesn't know about C user modules.** The `cmodules/` directory is not
  audited here — use the `add-c-module` skill for that.

## When you add a new feature

If you add a new firmware Python import that pulls in an IDF component
(e.g. starting to use TLS, or adding BLE for a future accessory), add an
entry to the `FEATURES` list in `tools/size-review.py`:

```python
Feature(
    name="Human readable name",
    imports=("module_a", "module_b"),     # what to grep for in firmware/
    off_when=[("CONFIG_FOO", "n")],       # all-must-match means off
    on_when=[("CONFIG_FOO", "y")],        # any-match means on
    default_on=True,                       # if ESP-IDF defaults it on
    how_to_disable="concrete sdkconfig lines",
    notes="rough size impact",
),
```

Keep the list focused — features worth mentioning move ≥ 10 KB. Micro-flags
add noise without helping.

## Top-three size wins for Bodn (current state)

From running the tool today:

1. **BLE** — 200–300 KB. Remove `sdkconfig.ble` from
   `SDKCONFIG_DEFAULTS`; `CONFIG_BT_ENABLED=n`.
2. **TLS** — 100–150 KB. `CONFIG_MBEDTLS_TLS_ENABLED=n` plus the
   client/server sub-switches.
3. **PPP** — ~30 KB. `CONFIG_LWIP_PPP_SUPPORT=n` (+ PAP/CHAP).

After trimming, consider re-partitioning `partitions-8MiBplus-ota.csv` to
give the saved app-partition bytes back to the VFS — that's what actually
makes OTA staging fit.

See the PR that introduced `tools/size-review.py` for context.
