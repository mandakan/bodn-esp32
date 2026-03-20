#!/usr/bin/env python3
"""Push firmware files to Bodn over WiFi (OTA).

Uploads changed firmware files to the device via the web API,
then reboots. No USB or REPL needed.

Tracks file hashes in .ota-hashes.json so unchanged files are skipped.
Use --force to upload everything regardless.

Usage:
  uv run python tools/ota-push.py                           # push to 192.168.4.1 (AP mode)
  uv run python tools/ota-push.py 192.168.1.42              # push to specific IP
  uv run python tools/ota-push.py --wokwi                    # push to localhost:9080 (Wokwi)
  uv run python tools/ota-push.py --force                    # skip change detection
  uv run python tools/ota-push.py --token SECRET             # with OTA auth token
"""

import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

FIRMWARE_DIR = Path(__file__).resolve().parent.parent / "firmware"
HASH_FILE = Path(__file__).resolve().parent.parent / ".ota-hashes.json"

# Auto-discover firmware files (same logic as wokwi-sync.py)
EXCLUDE = {"__pycache__"}


def discover_files() -> list[str]:
    """Walk firmware/ and return remote paths in upload order."""
    files = []
    for p in sorted(FIRMWARE_DIR.rglob("*.py")):
        if any(part in EXCLUDE for part in p.parts):
            continue
        files.append(str(p.relative_to(FIRMWARE_DIR)))

    def _sort_key(remote: str) -> tuple[int, str]:
        if remote == "main.py":
            return (2, remote)
        if remote.endswith("__init__.py"):
            return (0, remote)
        return (1, remote)

    files.sort(key=_sort_key)
    return files


def load_hashes() -> dict[str, str]:
    if HASH_FILE.exists():
        return json.loads(HASH_FILE.read_text())
    return {}


def save_hashes(hashes: dict[str, str]) -> None:
    HASH_FILE.write_text(json.dumps(hashes, indent=2) + "\n")


def file_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


FILES = discover_files()


def push(base_url: str, token: str = "", force: bool = False) -> bool:
    ok = True
    prev_hashes = {} if force else load_hashes()
    new_hashes = dict(prev_hashes)
    uploaded = 0
    skipped = 0

    for rel_path in FILES:
        local = FIRMWARE_DIR / rel_path
        if not local.exists():
            print(f"  SKIP {rel_path} (not found)")
            continue

        h = file_hash(local)
        if not force and prev_hashes.get(rel_path) == h:
            skipped += 1
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

        success = False
        for attempt in range(3):
            timeout = 10 + attempt * 10  # 10s, 20s, 30s
            req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
            try:
                resp = urllib.request.urlopen(req, timeout=timeout)
                resp.read()
                print(f"  {rel_path} ({len(data)} bytes)")
                new_hashes[rel_path] = h
                uploaded += 1
                success = True
                break
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    print(f"  ERROR {rel_path}: Unauthorized (set --token)")
                    break  # no point retrying auth errors
                else:
                    print(f"  ERROR {rel_path}: HTTP {e.code}")
            except Exception as e:
                label = "retrying..." if attempt < 2 else "giving up."
                print(f"  {rel_path}: {e}, {label}")
                time.sleep(1)

        if not success:
            ok = False

    if ok:
        save_hashes(new_hashes)

    if skipped and not uploaded:
        print(f"  All {skipped} files unchanged.")
    elif skipped:
        print(f"  {uploaded} uploaded, {skipped} unchanged.")

    return ok and uploaded > 0


def ota_commit(base_url: str, token: str = "") -> bool:
    """Move staged files into place and reboot."""
    url = base_url.rstrip("/") + "/api/ota/commit"
    hdrs = {"Content-Type": "application/json"}
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=b"{}", headers=hdrs, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        resp.read()
        return True
    except Exception:
        return True  # device reboots mid-response, connection drops


def ota_abort(base_url: str, token: str = "") -> None:
    """Discard staged files."""
    url = base_url.rstrip("/") + "/api/ota/abort"
    hdrs = {"Content-Type": "application/json"}
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=b"{}", headers=hdrs, method="POST")
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def _parse_args():
    base_url = "http://192.168.4.1"
    token = ""
    force = False
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--wokwi":
            base_url = "http://localhost:9080"
        elif args[i] == "--force":
            force = True
        elif args[i] == "--token" and i + 1 < len(args):
            i += 1
            token = args[i]
        elif not args[i].startswith("-"):
            base_url = "http://" + args[i]
        i += 1
    return base_url, token, force


def main() -> None:
    base_url, token, force = _parse_args()

    print(f"Pushing firmware to {base_url}...")
    result = push(base_url, token, force)
    if result:
        print("Committing update...")
        ota_commit(base_url, token)
        print("Done — device is rebooting with new firmware.")
    elif result is False:
        print("Upload failed — aborting staged files.")
        ota_abort(base_url, token)
        sys.exit(1)
    # else: nothing to upload (all unchanged), no reboot needed


if __name__ == "__main__":
    main()
