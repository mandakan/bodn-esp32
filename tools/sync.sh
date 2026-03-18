#!/usr/bin/env bash
# Sync firmware to the ESP32 device via mpremote.
set -euo pipefail

echo "Deploying firmware..."
uv run mpremote connect auto fs cp -r firmware/ :/
uv run mpremote connect auto reset
echo "Done. Device is resetting."
