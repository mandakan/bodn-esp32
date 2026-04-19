#!/usr/bin/env bash
# Sync firmware to the ESP32 device via mpremote.
# Usage: ./tools/sync.sh [--clean] [--minimal]
#   --clean    Wipe device filesystem before syncing
#   --minimal  Flash only boot.py, main.py, st7735.py, sdcard.py, and bodn/
#              (skip firmware/sounds/). Useful when the device is hanging
#              badly — press RST on the devkit, then run this immediately.
#
# Reliability notes
# -----------------
# mpremote's raw-REPL entry sends Ctrl-D (soft reset) then waits ≤ 10 s for
# the `raw REPL` banner. Our normal boot (5 s safe-window + WiFi + NTP +
# display init) exceeds that budget, so sync would fail with
# `could not enter raw repl`.
#
# We sidestep the race by making the Ctrl-C path in boot.py / main.py drop
# `/skip_main` and `/fast_boot` flag files. Once those are present the next
# boot finishes in well under 10 s and mpremote can enter raw REPL reliably.
# See firmware/boot.py `_abort_boot()` and firmware/main.py's
# `except KeyboardInterrupt` handler.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MPREMOTE="uv run mpremote connect auto"

if [ "${1:-}" = "--minimal" ]; then
    echo "Deploying core files (boot.py, main.py, st7735.py, sdcard.py, bodn/)..."
    cd "$ROOT/firmware"
    $MPREMOTE \
        fs cp boot.py :boot.py + \
        fs cp main.py :main.py + \
        fs cp st7735.py :st7735.py + \
        fs cp sdcard.py :sdcard.py + \
        fs cp -r bodn :bodn + \
        reset
    echo "Done."
    exit 0
fi

if [ "${1:-}" = "--clean" ]; then
    echo "Wiping device filesystem..."
    $MPREMOTE exec "
import os
def rm_rf(path):
    try:
        for entry in os.listdir(path):
            full = path + '/' + entry if path != '/' else '/' + entry
            if os.stat(full)[0] & 0x4000:
                rm_rf(full)
            else:
                os.remove(full)
        if path != '/':
            os.rmdir(path)
    except OSError:
        pass
rm_rf('/')
print('Device wiped.')
"
fi

echo "Cleaning local build artifacts..."
find "$ROOT/firmware" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find "$ROOT/firmware" -name '.DS_Store' -delete 2>/dev/null || true
find "$ROOT/firmware" -name '*.mpy' -delete 2>/dev/null || true
find "$ROOT/firmware" -name '*.bak' -delete 2>/dev/null || true
# Stale .ota-hashes.json inside firmware/ would leak to the device
rm -f "$ROOT/firmware/.ota-hashes.json"

echo "Deploying firmware..."
# Everything in one mpremote invocation = one raw-REPL entry.
# `fs cp -r . :/` overwrites existing files, so we don't need to rm first.
# Final `machine.reset()` kills the connection → mpremote exits non-zero,
# which is expected.
cd "$ROOT/firmware"
$MPREMOTE \
    fs cp -r . :/ + \
    reset
cd "$ROOT"

# Update OTA hashes so ota-push.py / ftp-sync.py won't re-upload everything.
echo "Updating OTA hashes..."
uv run python -c "
import hashlib, json
from pathlib import Path
fw = Path('$ROOT/firmware')
hashes = {}
for p in sorted(fw.rglob('*.py')):
    if '__pycache__' not in p.parts:
        hashes[str(p.relative_to(fw))] = hashlib.md5(p.read_bytes()).hexdigest()
Path('$ROOT/.ota-hashes.json').write_text(json.dumps(hashes, indent=2) + '\n')
print(f'  {len(hashes)} files hashed')
"

echo "Done."
