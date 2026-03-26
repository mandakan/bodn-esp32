#!/usr/bin/env python3
"""Push firmware files to Bodn over WiFi using FTP.

Files are uploaded to the device's OTA staging directory (/.ota/) via a
single FTP session, then committed via the HTTP API. Before activation the
device verifies MD5 hashes from a MANIFEST file — any truncated or corrupted
transfer causes the commit to be refused and staging is preserved intact.

Requires the device to be running in STA (home network) mode, not AP mode.
FTP credentials are set via ftp_user / ftp_pass in device settings (default bodn/bodn).

Usage:
  uv run python tools/ftp-sync.py                    # push to 192.168.4.1
  uv run python tools/ftp-sync.py 192.168.1.42       # specific IP
  uv run python tools/ftp-sync.py --force            # upload all, skip change detection
  uv run python tools/ftp-sync.py --token SECRET     # OTA auth token for commit step
  uv run python tools/ftp-sync.py --user U --pass P  # custom FTP credentials
"""

import ftplib
import hashlib
import io
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

FIRMWARE_DIR = Path(__file__).resolve().parent.parent / "firmware"
HASH_FILE = Path(__file__).resolve().parent.parent / ".ota-hashes.json"
EXCLUDE = {"__pycache__"}
DEFAULT_FTP_PORT = 21
DEFAULT_FTP_USER = "bodn"
DEFAULT_FTP_PASS = "bodn"


def discover_files() -> list[str]:
    """Walk firmware/ and return relative paths in safe upload order."""
    files = []
    for p in sorted(FIRMWARE_DIR.rglob("*.py")):
        if any(part in EXCLUDE for part in p.parts):
            continue
        files.append(str(p.relative_to(FIRMWARE_DIR)))

    def _key(rel: str) -> tuple[int, str]:
        if rel == "main.py":
            return (2, rel)
        if rel.endswith("__init__.py"):
            return (0, rel)
        return (1, rel)

    files.sort(key=_key)
    return files


def load_hashes() -> dict[str, str]:
    if HASH_FILE.exists():
        return json.loads(HASH_FILE.read_text())
    return {}


def save_hashes(hashes: dict[str, str]) -> None:
    HASH_FILE.write_text(json.dumps(hashes, indent=2) + "\n")


def file_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _http_post(url: str, token: str = "") -> tuple[bool, dict]:
    """POST to the device HTTP API. Returns (success, response_body)."""
    hdrs = {"Content-Type": "application/json"}
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=b"{}", headers=hdrs, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        body = json.loads(resp.read().decode())
        return True, body
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except Exception:
            body = {"error": f"HTTP {e.code}"}
        return False, body
    except Exception:
        # Device reboots mid-response on commit — treat as success
        return True, {}


def _ensure_remote_dirs(ftp: ftplib.FTP, rel_path: str) -> None:
    """Create all intermediate directories on the FTP server for a file path."""
    parts = rel_path.replace("\\", "/").split("/")[:-1]
    cur = ""
    for part in parts:
        cur = f"{cur}/{part}" if cur else part
        try:
            ftp.mkd(cur)
        except ftplib.error_perm:
            pass  # directory already exists


def sync(
    host: str,
    token: str = "",
    force: bool = False,
    ftp_port: int = DEFAULT_FTP_PORT,
    ftp_user: str = DEFAULT_FTP_USER,
    ftp_pass: str = DEFAULT_FTP_PASS,
) -> bool:
    base_url = f"http://{host}"

    # Discard any staging left over from a previous partial or failed sync
    print("Clearing old staging...")
    _http_post(f"{base_url}/api/ota/abort", token)

    # Decide which files to upload
    prev_hashes = {} if force else load_hashes()
    to_upload: list[tuple[str, Path, str]] = []

    for rel_path in discover_files():
        local = FIRMWARE_DIR / rel_path
        if not local.exists() or local.stat().st_size == 0:
            continue
        h = file_hash(local)
        if force or prev_hashes.get(rel_path) != h:
            to_upload.append((rel_path, local, h))

    if not to_upload:
        print("All files unchanged.")
        return True

    # Manifest covers only the files being uploaded; the device verifies
    # that every listed file arrived intact before moving anything to live.
    manifest = {rel: h for rel, _, h in to_upload}

    print(f"Uploading {len(to_upload)} file(s) via FTP to {host}:{ftp_port}...")
    t0 = time.monotonic()

    try:
        with ftplib.FTP() as ftp:
            ftp.connect(host, ftp_port, timeout=10)
            ftp.login(ftp_user, ftp_pass)
            ftp.set_pasv(True)

            for rel_path, local, _ in to_upload:
                _ensure_remote_dirs(ftp, rel_path)
                with open(local, "rb") as f:
                    ftp.storbinary(f"STOR {rel_path}", f)
                print(f"  {rel_path} ({local.stat().st_size} B)")

            # Upload manifest last. The commit endpoint requires it to be
            # present and will refuse to activate if any hash mismatches.
            manifest_bytes = json.dumps({"version": 1, "files": manifest}).encode()
            ftp.storbinary("STOR MANIFEST.json", io.BytesIO(manifest_bytes))
            print(f"  MANIFEST.json ({len(manifest_bytes)} B)")

    except Exception as e:
        print(f"FTP error: {e}")
        print("Aborting — staging cleared.")
        _http_post(f"{base_url}/api/ota/abort", token)
        return False

    elapsed = time.monotonic() - t0
    print(f"Upload complete in {elapsed:.1f}s — committing...")

    # Commit: device verifies hashes, moves files to live, reboots
    ok, body = _http_post(f"{base_url}/api/ota/commit", token)
    if not ok:
        details = body.get("details", [])
        print(f"Commit refused: {body.get('error', 'unknown error')}")
        if details:
            for path, reason in details:
                print(f"  {path}: {reason}")
        print("Staging preserved — fix the issue and retry.")
        return False

    # Persist hashes only after the device confirms the commit
    new_hashes = {**load_hashes(), **{rel: h for rel, _, h in to_upload}}
    save_hashes(new_hashes)
    committed = body.get("committed", len(to_upload))
    print(f"Done — {committed} file(s) activated, device is rebooting.")
    return True


def _parse_args():
    host = "192.168.4.1"
    token = ""
    force = False
    ftp_user = DEFAULT_FTP_USER
    ftp_pass = DEFAULT_FTP_PASS
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--force":
            force = True
        elif args[i] == "--token" and i + 1 < len(args):
            i += 1
            token = args[i]
        elif args[i] == "--user" and i + 1 < len(args):
            i += 1
            ftp_user = args[i]
        elif args[i] == "--pass" and i + 1 < len(args):
            i += 1
            ftp_pass = args[i]
        elif not args[i].startswith("-"):
            host = args[i]
        i += 1
    return host, token, force, ftp_user, ftp_pass


def main() -> None:
    host, token, force, ftp_user, ftp_pass = _parse_args()
    print(f"Syncing firmware to {host}...")
    ok = sync(host, token, force, ftp_user=ftp_user, ftp_pass=ftp_pass)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
