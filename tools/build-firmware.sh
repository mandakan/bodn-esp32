#!/bin/bash
# build-firmware.sh — build custom MicroPython firmware with audiomix C module
#
# Prerequisites:
#   1. MicroPython submodule: git submodule update --init --recursive
#   2. ESP-IDF v5.5.1 installed (required by MicroPython v1.27.0)
#
# ESP-IDF setup (one-time):
#   git clone -b v5.5.1 --recursive https://github.com/espressif/esp-idf.git ~/esp-idf
#   ~/esp-idf/install.sh esp32s3
#   source ~/esp-idf/export.sh
#
# Usage:
#   ./tools/build-firmware.sh           # full build
#   ./tools/build-firmware.sh clean     # clean build directory
#   ./tools/build-firmware.sh flash     # build + flash via esptool

set -euo pipefail

PROJ="$(cd "$(dirname "$0")/.." && pwd)"
MPY_DIR="$PROJ/micropython"
PORT_DIR="$MPY_DIR/ports/esp32"
BOARD_DIR="$PROJ/boards/BODN_S3"
CMODULES="$PROJ/cmodules/micropython.cmake"
BUILD_DIR="$PROJ/build"

# Check prerequisites
if [ ! -d "$MPY_DIR/py" ]; then
    echo "Error: MicroPython submodule not initialised."
    echo "Run: git submodule add https://github.com/micropython/micropython.git micropython"
    echo "     cd micropython && git checkout v1.27.0 && cd .."
    echo "     git submodule update --init --recursive"
    exit 1
fi

# Auto-source ESP-IDF if not already in PATH
if ! command -v xtensa-esp32s3-elf-gcc &>/dev/null; then
    # Try common locations
    IDF_SEARCH=(
        "${IDF_PATH:-}"
        "$HOME/esp-idf"
        "$HOME/esp/esp-idf"
        "/opt/esp-idf"
    )
    for idf_dir in "${IDF_SEARCH[@]}"; do
        if [ -n "$idf_dir" ] && [ -f "$idf_dir/export.sh" ]; then
            echo "Sourcing ESP-IDF from $idf_dir"
            source "$idf_dir/export.sh"
            break
        fi
    done
fi

if ! command -v xtensa-esp32s3-elf-gcc &>/dev/null; then
    echo "Error: ESP-IDF toolchain not found."
    echo ""
    echo "Install ESP-IDF v5.5.1 (one-time):"
    echo "  git clone -b v5.5.1 --recursive https://github.com/espressif/esp-idf.git ~/esp-idf"
    echo "  ~/esp-idf/install.sh esp32s3"
    echo ""
    echo "Then either source it before running this script:"
    echo "  source ~/esp-idf/export.sh"
    echo "Or set IDF_PATH:"
    echo "  export IDF_PATH=~/esp-idf"
    exit 1
fi

mkdir -p "$BUILD_DIR"

case "${1:-build}" in
    clean)
        echo "Cleaning build directory..."
        rm -rf "$PORT_DIR/build-BODN_S3"
        echo "Done."
        ;;

    flash)
        "$0" build
        echo ""
        echo "Flashing firmware..."
        esptool.py --chip esp32s3 write_flash -z 0 "$BUILD_DIR/firmware-bodn.bin"
        ;;

    build)
        # Build mpy-cross (cross-compiler for frozen bytecode)
        if [ ! -f "$MPY_DIR/mpy-cross/build/mpy-cross" ]; then
            echo "=== Building mpy-cross ==="
            make -C "$MPY_DIR/mpy-cross" -j"$(nproc 2>/dev/null || sysctl -n hw.ncpu)"
        fi

        # Fetch ESP32 port submodules (berkeley-db, etc.)
        echo "=== Fetching ESP32 port submodules ==="
        make -C "$PORT_DIR" submodules

        # Build firmware
        echo "=== Building firmware ==="
        make -C "$PORT_DIR" -j"$(nproc 2>/dev/null || sysctl -n hw.ncpu)" \
            BOARD_DIR="$BOARD_DIR" \
            USER_C_MODULES="$CMODULES"

        # Copy output
        cp "$PORT_DIR/build-BODN_S3/firmware.bin" "$BUILD_DIR/firmware-bodn.bin"
        echo ""
        echo "=== Build complete ==="
        echo "Firmware: $BUILD_DIR/firmware-bodn.bin"
        echo ""
        echo "To flash:"
        echo "  esptool.py --chip esp32s3 erase_flash  # first time only"
        echo "  esptool.py --chip esp32s3 write_flash -z 0 $BUILD_DIR/firmware-bodn.bin"
        echo ""
        echo "Then deploy Python files:"
        echo "  ./tools/sync.sh"
        ;;

    *)
        echo "Usage: $0 [build|clean|flash]"
        exit 1
        ;;
esac
