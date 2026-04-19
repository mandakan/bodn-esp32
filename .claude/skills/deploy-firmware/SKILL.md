---
name: deploy-firmware
description: Pick the right path to get firmware onto the device (USB, WiFi, Wokwi) or rebuild the custom MicroPython image, including the repartition-and-erase procedure. Use when iterating on firmware, deploying to real hardware, debugging in the simulator, after adding a C user-module, or when reallocating flash between OTA slots and VFS. Summarises prerequisites and trade-offs so you don't pick a slow path when a fast one is available, and so you don't brick the device when changing the partition table.
---

# Deploy firmware

The Bodn toolchain has one entry point (`deploy.sh`) that picks the right
underlying tool automatically, plus a full-reflash path for firmware
rebuilds and partition-table changes.

## Quick picker

| Situation | Tool | Why |
|---|---|---|
| **Any normal Python-file deploy** | `tools/deploy.sh` | Auto-detects WiFi (via `bodn.local`) vs USB and dispatches |
| Live iteration over USB (no copying) | `tools/deploy.sh --mount` | Mounts `firmware/` as `/remote`; edits are instant but device depends on host |
| Added a C user-module / rebuilt firmware | `tools/build-firmware.sh flash` | Rebuilds MicroPython + flashes via esptool |
| Wokwi simulator | `tools/wokwi-sync.py` | Raw TCP REPL — Wokwi doesn't expose USB |
| Encoder IRQs blocking `mpremote` | `tools/sync.sh --minimal` | Reset board, push only boot/main/bodn/ within the safe-boot window |
| Repartitioning the flash layout | Erase + full reflash | See §"Repartitioning" — very intentional path |

## `tools/deploy.sh` (normal path)

```bash
./tools/deploy.sh                        # auto (WiFi if bodn.local, else USB)
./tools/deploy.sh --usb                  # force USB (mpremote)
./tools/deploy.sh --wifi 192.168.1.42    # force WiFi HTTP push to an IP
./tools/deploy.sh --mount                # live-mount (no copy, requires USB session)
./tools/deploy.sh --force                # re-upload all files (WiFi path)
```

Under the hood it calls `tools/sync.sh` (USB via `mpremote`) or
`tools/ota-push.py` (WiFi via HTTP). Both are delta-aware via
`.ota-hashes.json`.

- **USB** (`sync.sh`): one `mpremote fs cp -r . :/` + `reset`. Slow per-file
  roundtrip but always works when a cable is attached.
- **WiFi HTTP** (`ota-push.py`): per-file POST to `/api/upload` with retry,
  writes directly to the live path (no `/.ota/` staging) so the VFS
  partition doesn't need headroom for a second copy. Fastest for
  few-files-changed typical edits.

`tools/ftp-sync.py` still exists for bulk uploads with MANIFEST-verified
cross-file atomicity, but is effectively legacy — HTTP handles everything
smaller deploys need without FTP's per-file timeout cliffs.

## Wokwi simulator

```bash
uv run python tools/wokwi-sync.py         # watch mode, recommended
uv run python tools/wokwi-sync.py --once  # one-shot sync
```

Connects to `localhost:5555` (override via first CLI arg). Wokwi allows
only one client at a time; new connections cannot interrupt running code.
Ctrl-C resyncs; Ctrl-C twice exits.

## Custom firmware build (C modules / IDF config change)

```bash
source ~/esp-idf/export.sh            # once per terminal session
./tools/build-firmware.sh              # build
./tools/build-firmware.sh flash        # build + flash via esptool (USB)
./tools/build-firmware.sh clean        # rm build-BODN_S3/
```

Rebuild triggers:

- Added / modified a C module in `cmodules/` (see `add-c-module` skill).
- Changed anything under `boards/BODN_S3/` — `sdkconfig.board`,
  `mpconfigboard.h`, `mpconfigboard.cmake`, partition CSV.
- Upgraded MicroPython submodule or ESP-IDF.

After a plain firmware flash the board still needs the Python code —
`deploy.sh` picks that up on the next run.

Before committing any `boards/BODN_S3/` change, run `tools/size-review.py`
(see the `size-review` skill) to catch imports of features you just
disabled and to surface new optimisation leads.

## Repartitioning

Partition-table changes are uncommon but occasionally worth doing — the
typical reason is reclaiming OTA-slot headroom for VFS after a trim round
reduces firmware size. This is the only deploy operation in the toolchain
that can brick the device if interrupted, and it always loses everything
in VFS. Read this section before touching it.

### When to bother

Compute the ratio `firmware-bodn.bin / ota_slot_size`:

- ≥ 90%: you're full and an added game mode will bounce the OTA. Trim
  more (`size-review`) before repartitioning — shrinking slots doesn't
  help if the firmware won't fit in them either.
- 70-85%: healthy. Repartitioning nets maybe 0.5-1.0 MB of VFS and is
  worth it if VFS is tight (current steady-state + 20% headroom).
- ≤ 60%: slots are oversized. Repartitioning is a big win.

Decide the new slot size with **at least 15% headroom** over today's
firmware size, and round up to a 64 KiB boundary (`0x10000`) — IDF
partition offsets have to be 4 KiB aligned but 64 KiB is cleaner and
matches the flash sector-erase granularity.

### Partition CSV

Committed CSVs live in `boards/BODN_S3/`. They layer on top of the
upstream defaults in `micropython/ports/esp32/`. Example for 2.06 MiB
OTA slots + 3.81 MiB VFS on 8 MiB flash:

```
# Name,   Type, SubType, Offset,   Size,     Flags
nvs,      data, nvs,     0x9000,   0x4000,
otadata,  data, ota,     0xd000,   0x2000,
phy_init, data, phy,     0xf000,   0x1000,
ota_0,    app,  ota_0,   0x10000,  0x210000,
ota_1,    app,  ota_1,   0x220000, 0x210000,
vfs,      data, fat,     0x430000, 0x3D0000,
```

The vfs entry must be explicit when slots shrink below the stock
`partitions-8MiBplus-ota.csv` sizes — the upstream CSV leaves vfs
implicit by ending before end-of-flash, and the MicroPython esp32 port
only auto-mounts the implicit remainder.

Point `sdkconfig.board` at the new file:

```
CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions-bodn-8MiB.csv"
```

### Safe reflash procedure

```bash
# 0. Sanity: firmware fits in the new slot?
./tools/build-firmware.sh                       # rebuild with new CSV
ls -l build/firmware-bodn.bin                   # must be ≤ new ota_0 size
uv run python tools/size-review.py              # no hard fails

# 1. Everything important on device is committed / synced off?
#    - settings you care about exported via /api/settings
#    - any /data/boot_log.json or session history you want to keep
#    - any hand-recorded voices you've only got on the device

# 2. Erase the whole flash. Required — a partial flash leaves old
#    partition remnants that confuse the new layout.
esptool.py --chip esp32s3 erase-flash

# 3. Flash the new image. This writes bootloader, partition table, and
#    ota_0 in one go.
./tools/build-firmware.sh flash

# 4. Push Python firmware + sounds. VFS is empty; this is a fresh start.
./tools/deploy.sh --usb

# 5. Re-sync SD card assets if needed (sprites, story TTS, card sets).
uv run python tools/sd-sync.py
```

### What goes wrong

- **Device boots straight into the bootloader (flashing failed)**: power
  cycle, hold BOOT while pressing RESET, retry `build-firmware.sh flash`.
  The erase succeeded; only step 3 has to repeat.
- **Boot log shows `Partition table CRC mismatch`**: you ran step 3
  without step 2. Erase and retry.
- **Device boots but VFS errors on mount**: the old VFS partition sector
  range overlaps the new layout. `os.umount('/')` + `os.VfsFat.mkfs(...)`
  in REPL, or erase-flash + redo from step 2.
- **`esp_ota_get_running_partition` returns null / OTA API errors at
  runtime**: ota_0 and ota_1 have to be the same size. Re-check the CSV.

### What the erase actually loses

Everything in `/` that isn't re-uploaded by `deploy.sh`:

- `settings.json` (WiFi creds, PIN, OTA token, hostname)
- `session_history.json`
- `/data/boot_log.json`
- `/.ota/` staging leftovers (good riddance)
- Any hand-recorded voices under `firmware/recordings/` — these live on
  SD, not flash, so they *survive* unless you also wipe the SD card.

A fresh device shows `wifi_mode=ap`, no PIN, default hostname. Recovery
path: connect phone to the `Bodn` AP, visit `http://192.168.4.1`,
reconfigure.

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

- **Never** flash with raw `esptool` for a firmware update; always go
  through `build-firmware.sh flash` so the board definition layering,
  partition table, and cmodules are respected. The only direct esptool
  call in this skill is `erase-flash` during repartitioning.
- **Never** commit `.ota-hashes.json` — it's a local deploy cache.
- Wokwi sync auto-discovers all `.py` under `firmware/` — no file list to
  maintain. New C modules still require a firmware rebuild.
- After changing `firmware/bodn/config.py`, run the `wiring-sync` skill
  before committing — the pre-commit hook rejects the commit otherwise.
- When the Wokwi custom chip C source changes, run the
  `wokwi-chip-rebuild` skill; `tools/wokwi-sync.py` alone does not
  recompile the `.wasm`.
- After changing anything in `boards/BODN_S3/`, run the `size-review`
  skill / `tools/size-review.py` before committing.
