#!/usr/bin/env bash
# Sync firmware to the ESP32 device via mpremote.
set -euo pipefail

echo "Deploying firmware..."
uv run mpremote connect auto fs cp -r firmware/ :/

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

uv run mpremote connect auto reset
echo "Done. Device is resetting."
