---
name: deploy-firmware
description: Pick the right path to get firmware onto the device (USB, WiFi, FTP, Wokwi) or rebuild the custom MicroPython image. Use when iterating on firmware, deploying to real hardware, debugging in the simulator, or after adding a C user-module. Summarises prerequisites and trade-offs so you don't pick a slow path when a fast one is available.
---

# Deploy firmware

The Bodn toolchain has five deploy paths. Each exists for a specific
situation — pick the wrong one and you wait minutes per iteration, or fail
to reach the device at all.

## Quick picker

| Situation | Tool | Why |
|---|---|---|
| Simulator (Wokwi running locally) | `tools/wokwi-sync.py` | Raw TCP REPL, no USB needed |
| USB-attached hardware, fresh flash | `tools/sync.sh --clean` | Wipes FS first, full upload |
| USB-attached hardware, iterative dev | `tools/sync.sh` | Fast path if `mpremote` is responsive |
| Hardware on home network (STA mode) | `tools/ftp-sync.py <ip>` | Fastest OTA — single FTP session + hash-verified commit |
| Hardware on own AP (no home WiFi) | `tools/ota-push.py <ip>` | HTTP per-file; works on `192.168.4.1` |
| Added a C user-module / first time | `tools/build-firmware.sh flash` | Rebuilds MicroPython + flashes via esptool |
| Encoder IRQs are blocking mpremote | `tools/sync.sh --minimal` | Reset device, immediately push core files only |

## USB (`mpremote`)

```bash
./tools/sync.sh            # push firmware/ and soft-reset
./tools/sync.sh --clean    # wipe FS first (use after renaming/removing files)
./tools/sync.sh --minimal  # only boot.py, main.py, st7735.py, bodn/
uv run mpremote connect auto repl    # REPL
```

`--minimal` is the rescue path when encoder interrupts saturate the REPL
after a soft-reboot — press the board's **RST** button, then run
`sync.sh --minimal` within a second or two.

## Wokwi simulator

```bash
uv run python tools/wokwi-sync.py         # watch mode, recommended
uv run python tools/wokwi-sync.py --once  # one-shot sync
```

Connects to `localhost:5555` (override via first CLI arg). Keeps the TCP
session open because Wokwi allows only one client at a time and a new
connection cannot interrupt running code. Ctrl-C resyncs; Ctrl-C twice
exits.

## OTA over HTTP (AP mode)

```bash
uv run python tools/ota-push.py                  # AP default 192.168.4.1
uv run python tools/ota-push.py 192.168.1.42     # specific IP
uv run python tools/ota-push.py --wokwi          # localhost:9080
uv run python tools/ota-push.py --force          # ignore hash cache
uv run python tools/ota-push.py --token SECRET   # with OTA auth
```

Uploads changed files via the device's HTTP API. Hashes cached in
`.ota-hashes.json` so unchanged files are skipped.

## OTA over FTP (STA mode — fastest)

```bash
uv run python tools/ftp-sync.py 192.168.1.42
uv run python tools/ftp-sync.py 192.168.1.42 --force
uv run python tools/ftp-sync.py --user U --pass P
```

One FTP session uploads all dirty files to `/.ota/`, then an HTTP commit
verifies MD5s against a MANIFEST before activating — a truncated transfer
leaves staging intact and refuses the commit. Much faster than `ota-push`
for any non-trivial change set, but only works on the home network (device
in STA mode). Default FTP creds are `bodn` / `bodn` — override via
`ftp_user` / `ftp_pass` in device settings.

## Custom firmware build (C modules)

```bash
source ~/esp-idf/export.sh            # once per terminal session
./tools/build-firmware.sh              # build
./tools/build-firmware.sh flash        # build + flash via esptool
./tools/build-firmware.sh clean        # rm build-BODN_S3/
```

One-time setup (MicroPython submodule + ESP-IDF v5.5.1) is documented in
the `add-c-module` skill and the script's own header. After a flash the
device has stock MicroPython + Bodn's C modules (`_audiomix`, `_spidma`,
`_draw`, `_mcpinput`, `_neopixel`). You still need to push the Python
firmware with one of the sync tools after flashing.

## SD card asset sync (separate pipeline)

Not deploying code, but often confused with it. SD card assets (sounds,
TTS, stories, card set JSONs, sprites) are built and copied by a single
command:

```bash
uv run python tools/sd-sync.py /Volumes/BODN_SD
uv run python tools/sd-sync.py --build-only
uv run python tools/sd-sync.py --no-build /Volumes/BODN_SD
```

See the `tts-pipeline` skill for the generation steps that feed this.

## Invariants

- **Never** flash with `esptool` directly; go through `build-firmware.sh
  flash` so the board definition layering is respected.
- **Never** commit `.ota-hashes.json` — it is a local deploy cache.
- Wokwi sync auto-discovers all `.py` under `firmware/` — no file list to
  maintain. New C modules still require a firmware rebuild.
- After changing `firmware/bodn/config.py`, run the `wiring-sync` skill
  before committing — the pre-commit hook rejects the commit otherwise.
- When the Wokwi custom chip C source changes, run the
  `wokwi-chip-rebuild` skill; `tools/wokwi-sync.py` alone does not
  recompile the `.wasm`.
