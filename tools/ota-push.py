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
import http.client
import json
import socket
import sys
import time
import urllib.parse
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


class KeepAliveClient:
    """Reuse one TCP connection across many HTTP requests.

    The previous urlopen() path opened a fresh TCP/HTTP handshake per
    file, which dominated per-file time on the device. http.client lets
    us send Connection: keep-alive and reuse the socket so the second
    request lands on an already-established connection.

    Reconnects on transport errors / unexpected EOF so a transient
    glitch (or a server-side close after the idle timeout) doesn't fail
    the whole sync — the caller's per-file retry loop then re-sends the
    request body.
    """

    def __init__(self, base_url: str, timeout: float = 10.0):
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in ("http", ""):
            raise ValueError(f"only http:// supported, got {base_url!r}")
        self.host = parsed.hostname or ""
        self.port = parsed.port or 80
        self.timeout = timeout
        self._conn: http.client.HTTPConnection | None = None
        # For tests: count how many times we opened a TCP connection.
        self.connect_count = 0

    def _connect(self) -> http.client.HTTPConnection:
        if self._conn is None:
            self._conn = http.client.HTTPConnection(
                self.host, self.port, timeout=self.timeout
            )
            self.connect_count += 1
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def request(
        self,
        method: str,
        path: str,
        body: bytes,
        headers: dict[str, str],
        timeout: float | None = None,
    ) -> tuple[int, bytes]:
        """Send one request, returning (status, body_bytes).

        Caller handles non-2xx responses; transport errors raise.
        """
        # Always advertise keep-alive — server falls back to close if it
        # doesn't support it, and we'll reconnect for the next request.
        hdrs = dict(headers)
        hdrs.setdefault("Connection", "keep-alive")
        hdrs.setdefault("Content-Length", str(len(body)))

        # One reconnect attempt: the server may have closed the socket
        # after its idle timeout. http.client raises BadStatusLine /
        # RemoteDisconnected in that case.
        for is_retry in (False, True):
            conn = self._connect()
            if timeout is not None:
                conn.timeout = timeout
                if conn.sock is not None:
                    conn.sock.settimeout(timeout)
            try:
                conn.request(method, path, body=body, headers=hdrs)
                resp = conn.getresponse()
                data = resp.read()
                # If the server signalled close, drop our cached conn so
                # the next request opens a fresh one.
                if resp.will_close:
                    self.close()
                return resp.status, data
            except (
                http.client.BadStatusLine,
                http.client.RemoteDisconnected,
                ConnectionResetError,
                BrokenPipeError,
                socket.timeout,
            ):
                # Stale socket — reconnect once and retry the same body.
                self.close()
                if is_retry:
                    raise
            except Exception:
                self.close()
                raise
        raise RuntimeError("unreachable")


def push(
    base_url: str,
    token: str = "",
    force: bool = False,
    client: KeepAliveClient | None = None,
) -> tuple[bool, int]:
    """Upload changed files. Returns (ok, uploaded_count)."""
    ok = True
    prev_hashes = {} if force else load_hashes()
    new_hashes = dict(prev_hashes)
    uploaded = 0
    skipped = 0
    total_bytes = 0
    batch_start = time.monotonic()
    own_client = client is None
    if client is None:
        client = KeepAliveClient(base_url)

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
        if len(data) == 0:
            skipped += 1
            continue
        remote = "/" + rel_path
        hdrs = {
            "X-Path": remote,
            "Content-Type": "application/octet-stream",
        }
        if token:
            hdrs["Authorization"] = f"Bearer {token}"

        success = False
        for attempt in range(3):
            req_timeout = 10 + attempt * 10  # 10s, 20s, 30s
            t0 = time.monotonic()
            try:
                status, _ = client.request(
                    "POST", "/api/upload", data, hdrs, timeout=req_timeout
                )
                if status == 401:
                    print(f"  ERROR {rel_path}: Unauthorized (set --token)")
                    break  # no point retrying auth errors
                if status == 507:
                    print(f"  ERROR {rel_path}: not enough space on device")
                    break  # no point retrying
                if status >= 400:
                    print(f"  ERROR {rel_path}: HTTP {status}")
                    continue
                dt = time.monotonic() - t0
                rate = (len(data) / dt / 1024) if dt > 0 else 0
                print(
                    f"  {rel_path}  {len(data):>7} B  {dt * 1000:>5.0f} ms  {rate:>5.0f} KB/s"
                )
                new_hashes[rel_path] = h
                uploaded += 1
                total_bytes += len(data)
                success = True
                break
            except Exception as e:
                label = "retrying..." if attempt < 2 else "giving up."
                print(f"  {rel_path}: {e}, {label}")
                time.sleep(1)

        if not success:
            ok = False

    # Save hashes for files that did upload (even if some failed)
    save_hashes(new_hashes)
    if own_client:
        client.close()

    elapsed = time.monotonic() - batch_start
    if uploaded:
        avg = (total_bytes / elapsed / 1024) if elapsed > 0 else 0
        print(
            f"  {uploaded} uploaded, {skipped} unchanged — "
            f"{total_bytes / 1024:.0f} KB in {elapsed:.1f}s "
            f"(avg {avg:.0f} KB/s)"
        )
    elif skipped:
        print(f"  All {skipped} files unchanged ({elapsed:.1f}s)")

    return ok, uploaded


def ota_commit(base_url: str, token: str = "") -> bool:
    """Move staged files into place and reboot."""
    hdrs = {"Content-Type": "application/json"}
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    client = KeepAliveClient(base_url, timeout=30)
    try:
        client.request("POST", "/api/ota/commit", b"{}", hdrs)
    except Exception:
        pass  # device reboots mid-response, connection drops
    finally:
        client.close()
    return True


def ota_abort(base_url: str, token: str = "") -> None:
    """Discard staged files."""
    hdrs = {"Content-Type": "application/json"}
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    client = KeepAliveClient(base_url, timeout=5)
    try:
        client.request("POST", "/api/ota/abort", b"{}", hdrs)
    except Exception:
        pass
    finally:
        client.close()


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
    # Clear any leftover /.ota/ staging from a previously aborted run —
    # HTTP uploads write live, but old firmware (or the FTP path) may
    # have left staged copies behind eating VFS. Best-effort: ignore
    # failures and keep going; the device-side endpoint no-ops when
    # staging is already empty.
    ota_abort(base_url, token)
    ok, uploaded = push(base_url, token, force)
    if not ok:
        print("Upload failed — aborting staged files.")
        ota_abort(base_url, token)
        sys.exit(1)
    if uploaded == 0:
        # Nothing to do — device already in sync.
        return
    print("Committing update...")
    ota_commit(base_url, token)
    print("Done — device is rebooting with new firmware.")


if __name__ == "__main__":
    main()
