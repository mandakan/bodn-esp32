#!/usr/bin/env bash
# Deploy firmware to Bodn — auto-detects USB vs WiFi.
#
# Usage:
#   ./tools/deploy.sh                          auto (prefers WiFi if mDNS resolves, else USB)
#   ./tools/deploy.sh --usb                    force USB sync via mpremote (tools/sync.sh)
#   ./tools/deploy.sh --usb PATH [PATH ...]    USB-deploy just these files (no full rsync)
#   ./tools/deploy.sh --wifi                   force WiFi push via HTTP (tools/ota-push.py)
#   ./tools/deploy.sh --wifi 192.168.x         WiFi to a specific host
#   ./tools/deploy.sh --mount                  live-mount firmware/ over USB (no copy, edits are live)
#   ./tools/deploy.sh --force                  re-upload all files (skip hash cache); forwarded to WiFi path
#
# PATH arguments accept either firmware-relative (bodn/web.py) or
# repo-relative (firmware/bodn/web.py) paths. The device-side target
# mirrors the firmware-relative form.
#
# Any bare non-flag argument without --usb is treated as the WiFi host:
#   ./tools/deploy.sh 192.168.1.143
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MDNS_HOST="${BODN_MDNS:-bodn.local}"

mode=""
host=""
force=""
files=()

usage() {
    sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
    case "$1" in
        --usb)    mode=usb ;;
        --wifi)   mode=wifi ;;
        --mount)  mode=mount ;;
        --force)  force="--force" ;;
        -h|--help) usage; exit 0 ;;
        --*)      echo "unknown flag: $1" >&2; usage >&2; exit 2 ;;
        *)
            # --usb collects positionals as file paths; without an
            # explicit mode (or with --wifi) the first bare arg is the
            # host and anything else is an error.
            if [ "$mode" = "usb" ]; then
                files+=("$1")
            elif [ -z "$host" ]; then
                host="$1"
                [ -z "$mode" ] && mode=wifi
            else
                echo "unexpected argument: $1" >&2; usage >&2; exit 2
            fi
            ;;
    esac
    shift
done

# ──────────────────────────────────────────────────────────────── discovery

find_usb() {
    # First match wins. macOS: usbserial-* (CP210x/CH340 UART bridge) or
    # usbmodem* (native USB-CDC). Linux: /dev/ttyUSB* / /dev/ttyACM*.
    for pat in /dev/cu.usbserial-* /dev/cu.usbmodem* /dev/ttyUSB* /dev/ttyACM*; do
        for dev in $pat; do
            [ -e "$dev" ] && { echo "$dev"; return 0; }
        done
    done
    return 1
}

resolve_mdns() {
    # Returns the IPv4 of $MDNS_HOST if resolvable, else nothing.
    # Uses dscacheutil on macOS (reads the Bonjour cache) or getent on Linux.
    local ip=""
    if command -v dscacheutil >/dev/null 2>&1; then
        ip=$(dscacheutil -q host -a name "$MDNS_HOST" 2>/dev/null \
             | awk '/^ip_address:/ {print $2; exit}')
    elif command -v getent >/dev/null 2>&1; then
        ip=$(getent hosts "$MDNS_HOST" 2>/dev/null | awk '{print $1; exit}')
    fi
    [ -n "$ip" ] && echo "$ip"
}

# ──────────────────────────────────────────────────────────────── mode resolution

if [ -z "$mode" ]; then
    # Auto. Prefer WiFi if mDNS resolves (delta-upload is fast and works
    # from anywhere on the LAN). Fall back to USB.
    if host=$(resolve_mdns) && [ -n "$host" ]; then
        mode=wifi
        echo "deploy: auto → wifi (bodn.local → $host)"
    elif usb=$(find_usb); then
        mode=usb
        echo "deploy: auto → usb ($usb)"
    else
        echo "deploy: no USB device and $MDNS_HOST did not resolve." >&2
        echo "        Connect USB, or pass an IP: ./tools/deploy.sh 192.168.x.x" >&2
        exit 1
    fi
fi

# ──────────────────────────────────────────────────────────────── dispatch

case "$mode" in
    usb)
        if [ ${#files[@]} -gt 0 ]; then
            exec "$ROOT/tools/sync.sh" "${files[@]}"
        fi
        exec "$ROOT/tools/sync.sh"
        ;;
    mount)
        # No copy — device imports files from the host over USB. Edits are
        # live. Soft-reset (Ctrl-D in the REPL) to restart main.py with
        # the updated code.
        cd "$ROOT/firmware"
        exec uv run mpremote connect auto mount . + repl
        ;;
    wifi)
        if [ -z "$host" ]; then
            if host=$(resolve_mdns) && [ -n "$host" ]; then
                :
            else
                host="192.168.4.1"   # AP-mode fallback
                echo "deploy: no host given and $MDNS_HOST did not resolve — trying AP ($host)"
            fi
        fi
        if [ -n "$force" ]; then
            exec uv run python "$ROOT/tools/ota-push.py" "$force" "$host"
        else
            exec uv run python "$ROOT/tools/ota-push.py" "$host"
        fi
        ;;
esac
