#!/usr/bin/env bash
# Sync firmware to the ESP32 device via mpremote.
# Usage: ./tools/sync.sh [--clean]
set -euo pipefail

MPREMOTE="uv run mpremote connect auto"

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

echo "Cleaning build artifacts..."
find firmware -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find firmware -name '.DS_Store' -delete 2>/dev/null || true
find firmware -name '*.mpy' -delete 2>/dev/null || true
find firmware -name '*.bak' -delete 2>/dev/null || true

echo "Removing old boot/main to prevent boot loops if sync fails..."
$MPREMOTE fs rm :/boot.py 2>/dev/null || true
$MPREMOTE fs rm :/main.py 2>/dev/null || true

echo "Deploying firmware..."
cd firmware && uv run mpremote connect auto fs cp -r . :/ && cd ..

# Update OTA hashes so next ota-push.py won't re-upload everything
echo "Updating OTA hashes..."
uv run python -c "
import hashlib, json
from pathlib import Path
fw = Path('firmware')
hashes = {}
for p in sorted(fw.rglob('*.py')):
    if '__pycache__' not in p.parts:
        hashes[str(p.relative_to(fw))] = hashlib.md5(p.read_bytes()).hexdigest()
Path('.ota-hashes.json').write_text(json.dumps(hashes, indent=2) + '\n')
print(f'  {len(hashes)} files hashed')
"

# If we got here without errors, auto-reboot the device
echo "Rebooting device..."
if $MPREMOTE exec "import machine; machine.reset()" 2>/dev/null; then
    echo "Done. Device is rebooting."
else
    echo "Auto-reboot failed. Press reset button or power-cycle to boot."
fi
