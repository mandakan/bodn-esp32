#!/usr/bin/env python3
"""Flag mismatches between the custom firmware's enabled features and what
the Python code actually imports.

Two kinds of mismatch:

  1. **Imported but disabled** — hard failure. A Python file imports a
     module whose backing feature has been turned off in the custom
     firmware. The device will raise ImportError on boot.

  2. **Enabled but unused** — warning. The feature takes flash and app
     partition space but no Python code uses it. Candidate for trimming.

Runs as a pre-commit check. It's a *lint*, not a build system — the only
authoritative size breakdown comes from `idf.py size-components` after a
real build. Treat warnings as leads, not rules.

Usage:
    uv run python tools/size-review.py              # report; exits 1 on hard fails
    uv run python tools/size-review.py --strict     # warnings become failures too
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOARD_DIR = ROOT / "boards" / "BODN_S3"
MPY_PORT_DIR = ROOT / "micropython" / "ports" / "esp32"
FIRMWARE_DIR = ROOT / "firmware"


# --------------------------------------------------------------- Feature table
#
# Each entry describes one knob (or small set of related knobs) that can be
# turned off to shrink the firmware. Keep the list focused on features that
# actually move the needle — micro-flags (a few KB) aren't worth the noise.
#
# "imports"     — top-level Python module names that pull this feature in.
#                 An import of *any* of these counts as "feature is used".
# "off_when"    — list of (CONFIG_KEY, value) pairs; if every pair matches
#                 the effective sdkconfig, the feature is considered disabled.
# "on_when"     — same, but any match means enabled (checked after off_when).
# "how_to_*"    — short human-readable hint printed with the report.


@dataclass
class Feature:
    name: str
    imports: tuple[str, ...]
    off_when: list[tuple[str, str]] = field(default_factory=list)
    on_when: list[tuple[str, str]] = field(default_factory=list)
    # ESP-IDF kconfig defaults aren't written into any sdkconfig.defaults
    # file — only explicit overrides are. Set default_on for features that
    # ESP-IDF ships enabled, so the analyzer treats silence as "on" rather
    # than "unknown".
    default_on: bool = False
    how_to_disable: str = ""
    how_to_enable: str = ""
    notes: str = ""


FEATURES: list[Feature] = [
    Feature(
        name="BLE (NimBLE stack)",
        imports=("bluetooth", "ubluetooth", "aioble"),
        off_when=[("CONFIG_BT_ENABLED", "n")],
        on_when=[("CONFIG_BT_ENABLED", "y")],
        how_to_disable=(
            "drop sdkconfig.ble from SDKCONFIG_DEFAULTS in "
            "boards/BODN_S3/mpconfigboard.cmake; add CONFIG_BT_ENABLED=n "
            "to sdkconfig.board"
        ),
        notes="Biggest single win — typically 200-300 KB in the app partition.",
    ),
    Feature(
        name="TLS (mbedtls TLS layer)",
        imports=("ssl", "ussl", "tls"),
        off_when=[("CONFIG_MBEDTLS_TLS_ENABLED", "n")],
        on_when=[("CONFIG_MBEDTLS_TLS_ENABLED", "y")],
        default_on=True,  # ESP-IDF default
        how_to_disable=(
            "add CONFIG_MBEDTLS_TLS_ENABLED=n + CONFIG_MBEDTLS_TLS_CLIENT=n "
            "+ CONFIG_MBEDTLS_TLS_SERVER=n to sdkconfig.board"
        ),
        notes=(
            "WPA2/WPA3 keeps lower mbedtls primitives (AES, SHA, bignum) "
            "regardless — only the TLS/X.509 top layer goes."
        ),
    ),
    Feature(
        name="PPP (serial IP over UART)",
        imports=(),  # no direct Python module
        off_when=[("CONFIG_LWIP_PPP_SUPPORT", "n")],
        on_when=[("CONFIG_LWIP_PPP_SUPPORT", "y")],
        how_to_disable=(
            "add CONFIG_LWIP_PPP_SUPPORT=n + CONFIG_LWIP_PPP_PAP_SUPPORT=n "
            "+ CONFIG_LWIP_PPP_CHAP_SUPPORT=n to sdkconfig.board"
        ),
        notes="Not used by Bodn; pure saving.",
    ),
    Feature(
        name="Ethernet (SPI-attached PHY drivers)",
        imports=(),  # network.LAN is the user API; no direct import name
        off_when=[("CONFIG_ETH_USE_SPI_ETHERNET", "n")],
        on_when=[("CONFIG_ETH_USE_SPI_ETHERNET", "y")],
        default_on=True,  # sdkconfig.base enables the SPI-Ethernet drivers
        how_to_disable=(
            "add CONFIG_ETH_ENABLED=n + CONFIG_ETH_USE_SPI_ETHERNET=n + "
            "CONFIG_ETH_SPI_ETHERNET_W5500=n + "
            "CONFIG_ETH_SPI_ETHERNET_KSZ8851SNL=n + "
            "CONFIG_ETH_SPI_ETHERNET_DM9051=n to sdkconfig.board"
        ),
        notes=(
            "S3 has no internal MAC and the board has no SPI-Ethernet chip. "
            "MICROPY_PY_NETWORK_LAN auto-flips to 0 when these are off."
        ),
    ),
    Feature(
        name="ESP-NOW",
        imports=("espnow", "aioespnow"),
        off_when=[("CONFIG_ESP_WIFI_ESPNOW_ENABLED", "n")],
        on_when=[("CONFIG_ESP_WIFI_ESPNOW_ENABLED", "y")],
    ),
    Feature(
        name="BTree key-value store",
        imports=("btree",),
        # Controlled by MICROPY_PY_BTREE (C define, not sdkconfig). We still
        # list it so the import check catches accidental use.
    ),
    Feature(
        name="WebREPL",
        imports=("webrepl", "webrepl_setup"),
        # Controlled by MICROPY_PY_WEBREPL.
    ),
    Feature(
        name="zlib / deflate",
        imports=("zlib", "deflate", "uzlib"),
        # Controlled by MICROPY_PY_DEFLATE.
    ),
    Feature(
        name="cryptolib",
        imports=("cryptolib", "ucryptolib"),
        # Controlled by MICROPY_PY_CRYPTOLIB.
    ),
    Feature(
        name="binascii",
        imports=("binascii", "ubinascii"),
        # Small; listed mostly for completeness.
    ),
]


# --------------------------------------------------------------- sdkconfig I/O


def parse_sdkconfig(path: Path) -> dict[str, str]:
    """Return {CONFIG_NAME: value_str} from a single sdkconfig file.

    Also understands the `# CONFIG_FOO is not set` comment form, which
    ESP-IDF emits for boolean options that are explicitly off.
    """
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        # Explicit off via comment form
        m = re.match(r"#\s*(CONFIG_\w+)\s+is not set\s*$", line)
        if m:
            result[m.group(1)] = "n"
            continue
        if line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        result[k.strip()] = v.strip().strip('"')
    return result


def sdkconfig_files_from_cmake(cmake: Path) -> list[Path]:
    """Extract the ordered list of sdkconfig defaults from mpconfigboard.cmake."""
    if not cmake.is_file():
        return []
    text = cmake.read_text()
    m = re.search(r"set\s*\(\s*SDKCONFIG_DEFAULTS\s+([^)]+)\)", text, re.DOTALL)
    if not m:
        return []
    paths: list[Path] = []
    for line in m.group(1).splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        entry = entry.replace("${_PORT_DIR}", str(MPY_PORT_DIR))
        entry = entry.replace("${CMAKE_CURRENT_LIST_DIR}", str(cmake.parent))
        if "$" in entry:
            # Unsubstituted variable — skip rather than guess.
            continue
        paths.append(Path(entry))
    return paths


def effective_sdkconfig() -> tuple[dict[str, str], list[Path]]:
    """Merge inherited sdkconfig files + the board's override in cmake order."""
    cmake = BOARD_DIR / "mpconfigboard.cmake"
    files = sdkconfig_files_from_cmake(cmake)
    cfg: dict[str, str] = {}
    for f in files:
        cfg.update(parse_sdkconfig(f))
    return cfg, files


# --------------------------------------------------------------- Imports scan


IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([\w.]+)", re.MULTILINE)


def collect_imports() -> dict[str, set[Path]]:
    """Return {top_level_module_name: {file_where_imported, ...}}."""
    result: dict[str, set[Path]] = {}
    for py in FIRMWARE_DIR.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        try:
            text = py.read_text()
        except OSError:
            continue
        for m in IMPORT_RE.finditer(text):
            top = m.group(1).split(".", 1)[0]
            result.setdefault(top, set()).add(py.relative_to(ROOT))
    return result


# --------------------------------------------------------------- Feature state


def feature_is_off(f: Feature, cfg: dict[str, str]) -> bool:
    return bool(f.off_when) and all(cfg.get(k) == v for k, v in f.off_when)


def feature_is_on(f: Feature, cfg: dict[str, str]) -> bool:
    return bool(f.on_when) and any(cfg.get(k) == v for k, v in f.on_when)


def feature_state(f: Feature, cfg: dict[str, str]) -> str:
    """Return 'off', 'on', or 'unknown'.

    Features without any sdkconfig pairs are marked 'unknown' — they're
    controlled by MICROPY_PY_* C defines which we don't parse. The import
    check still runs.
    """
    if feature_is_off(f, cfg):
        return "off"
    if feature_is_on(f, cfg):
        return "on"
    if f.default_on:
        return "on"
    return "unknown"


def feature_is_used(f: Feature, imports: dict[str, set[Path]]) -> list[Path]:
    hits: set[Path] = set()
    for name in f.imports:
        hits.update(imports.get(name, ()))
    return sorted(hits)


# --------------------------------------------------------------- Main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--strict",
        action="store_true",
        help="warnings (enabled-but-unused) become failures too",
    )
    args = ap.parse_args()

    cfg, files = effective_sdkconfig()
    if not files:
        print(
            "size-review: could not resolve SDKCONFIG_DEFAULTS from "
            "boards/BODN_S3/mpconfigboard.cmake — is the MicroPython "
            "submodule initialised?",
            file=sys.stderr,
        )
        return 2

    imports = collect_imports()
    hard_fails = 0
    warnings = 0

    print("size-review — firmware feature vs import audit")
    print()
    print("Inherited sdkconfig files (in order):")
    for f in files:
        try:
            rel = f.relative_to(ROOT)
        except ValueError:
            rel = f
        mark = "✓" if f.is_file() else "✗ missing"
        print(f"  {mark}  {rel}")
    print()

    col = {"off": "off   ", "on": "on    ", "unknown": "?     "}
    print(f"{'state':<6} {'used':<5} feature")
    print(f"{'-' * 6} {'-' * 5} {'-' * 40}")

    for feat in FEATURES:
        state = feature_state(feat, cfg)
        used_in = feature_is_used(feat, imports)
        used = "yes" if used_in else "no "

        print(f"{col[state]} {used:<5} {feat.name}")

        # Mismatches
        if state == "off" and used_in:
            hard_fails += 1
            print("        FAIL: imported but disabled — will ImportError at runtime")
            for p in used_in[:5]:
                print(f"              {p}")
            if len(used_in) > 5:
                print(f"              (+{len(used_in) - 5} more)")
            if feat.how_to_enable:
                print(f"        fix: {feat.how_to_enable}")
        elif state == "on" and not used_in:
            warnings += 1
            print("        WARN: enabled but no Python code imports it")
            if feat.how_to_disable:
                print(f"        hint: {feat.how_to_disable}")
            if feat.notes:
                print(f"        note: {feat.notes}")
        elif state == "unknown" and used_in:
            # Used, and we can't tell if it's really compiled in — just FYI
            pass

    print()
    print(f"Summary: {hard_fails} hard fail(s), {warnings} warning(s)")
    print()
    print(
        "Truth source for actual flash use is `idf.py size-components` after "
        "a rebuild.\nTreat warnings as leads — some features pull in a lot "
        "of code transitively\nwhile others are already compiled out by "
        "default. Measure before committing."
    )

    if hard_fails:
        return 1
    if warnings and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
