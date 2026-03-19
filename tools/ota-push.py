#!/usr/bin/env python3
"""Push firmware files to Bodn over WiFi (OTA).

Uploads all firmware files to the device via the web API,
then reboots. No USB or REPL needed.

Usage:
  uv run python tools/ota-push.py                           # push to 192.168.4.1 (AP mode)
  uv run python tools/ota-push.py 192.168.1.42              # push to specific IP
  uv run python tools/ota-push.py --wokwi                    # push to localhost:9080 (Wokwi)
  uv run python tools/ota-push.py --token SECRET             # with OTA auth token
  uv run python tools/ota-push.py --wokwi --token SECRET     # Wokwi + auth
"""

import sys
import urllib.error
import urllib.request
from pathlib import Path

FIRMWARE_DIR = Path(__file__).resolve().parent.parent / "firmware"

# Files to upload, in order (remote path relative to /)
FILES = [
    "boot.py",
    "st7735.py",
    "bodn/__init__.py",
    "bodn/config.py",
    "bodn/debounce.py",
    "bodn/encoder.py",
    "bodn/storage.py",
    "bodn/session.py",
    "bodn/wifi.py",
    "bodn/web_ui.py",
    "bodn/web.py",
    "main.py",
]


def push(base_url: str, token: str = "") -> bool:
    ok = True
    for rel_path in FILES:
        local = FIRMWARE_DIR / rel_path
        if not local.exists():
            print(f"  SKIP {rel_path} (not found)")
            continue

        data = local.read_bytes()
        remote = "/" + rel_path
        url = base_url.rstrip("/") + "/api/upload"
        hdrs = {
            "X-Path": remote,
            "Content-Type": "application/octet-stream",
        }
        if token:
            hdrs["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            print(f"  {rel_path} ({len(data)} bytes) -> {remote}")
            resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 401:
                print(f"  ERROR {rel_path}: Unauthorized (set --token)")
            else:
                print(f"  ERROR {rel_path}: HTTP {e.code}")
            ok = False
        except Exception as e:
            print(f"  ERROR {rel_path}: {e}")
            ok = False

    return ok


def reboot(base_url: str, token: str = "") -> None:
    url = base_url.rstrip("/") + "/api/reboot"
    hdrs = {}
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=b"{}", headers=hdrs, method="POST")
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # device reboots mid-response, connection drops


def _parse_args():
    base_url = "http://192.168.4.1"
    token = ""
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--wokwi":
            base_url = "http://localhost:9080"
        elif args[i] == "--token" and i + 1 < len(args):
            i += 1
            token = args[i]
        elif not args[i].startswith("-"):
            base_url = "http://" + args[i]
        i += 1
    return base_url, token


def main() -> None:
    base_url, token = _parse_args()

    print(f"Pushing firmware to {base_url}...")
    if push(base_url, token):
        print("Rebooting device...")
        reboot(base_url, token)
        print("Done.")
    else:
        print("Some files failed to upload.")
        sys.exit(1)


if __name__ == "__main__":
    main()
