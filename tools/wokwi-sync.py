#!/usr/bin/env python3
"""Push firmware files to the Wokwi simulator via raw REPL over TCP.

Bypasses mpremote entirely — connects directly to Wokwi's TCP port
and pastes file contents through the MicroPython raw REPL.

Usage:
  uv run python tools/wokwi-sync.py          # watch mode (recommended)
  uv run python tools/wokwi-sync.py --once    # sync once and exit

Watch mode keeps the connection open after syncing. This is needed because
Wokwi only allows one TCP client at a time, and a new connection cannot
interrupt running code. Press Ctrl-C to re-sync, Ctrl-C twice to quit.
"""

import hashlib
import json
import socket
import sys
import time
from pathlib import Path

WOKWI_HOST = "localhost"
WOKWI_PORT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 5555

FIRMWARE_DIR = Path(__file__).resolve().parent.parent / "firmware"
HASH_FILE = Path(__file__).resolve().parent.parent / ".ota-hashes.json"

# Auto-discover all .py files under firmware/.
# __init__.py files sort first (packages must exist before modules),
# main.py sorts last (it runs on soft-reset, so everything else must be
# uploaded first).  No manual list to maintain.
EXCLUDE = {"__pycache__"}


def discover_files() -> list[tuple[str, Path]]:
    """Walk firmware/ and return (remote_path, local_path) pairs."""
    files = []
    for p in sorted(FIRMWARE_DIR.rglob("*.py")):
        if any(part in EXCLUDE for part in p.parts):
            continue
        remote = str(p.relative_to(FIRMWARE_DIR))
        files.append((remote, p))

    def _sort_key(entry: tuple[str, Path]) -> tuple[int, str]:
        remote = entry[0]
        if remote == "main.py":
            return (2, remote)  # last
        if remote.endswith("__init__.py"):
            return (0, remote)  # first (create packages)
        return (1, remote)

    files.sort(key=_sort_key)
    return files


FILES = discover_files()


def read_until(sock: socket.socket, marker: bytes, timeout: float = 5.0) -> bytes:
    """Read from socket until marker is found or timeout."""
    data = b""
    deadline = time.time() + timeout
    while time.time() < deadline:
        sock.settimeout(max(0.1, deadline - time.time()))
        try:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
            if marker in data:
                return data
        except socket.timeout:
            continue
    return data


def drain(sock: socket.socket, timeout: float = 0.5) -> None:
    """Read and discard any pending data."""
    sock.settimeout(timeout)
    try:
        while sock.recv(4096):
            pass
    except socket.timeout:
        pass


def enter_raw_repl(sock: socket.socket) -> bool:
    """Interrupt any running program and enter raw REPL mode.

    Sends Ctrl-C bursts to break out of uasyncio, then enters raw REPL.
    """
    for attempt in range(8):
        # Send a burst of Ctrl-C to break out of running code / uasyncio
        for _ in range(10):
            sock.sendall(b"\x03")
            time.sleep(0.05)

        # Give the interpreter time to unwind (uasyncio needs longer)
        time.sleep(0.5)
        drain(sock)

        sock.sendall(b"\x02")  # Ctrl-B = normal REPL
        time.sleep(0.3)
        drain(sock, 0.5)

        sock.sendall(b"\x01")  # Ctrl-A = raw REPL
        resp = read_until(sock, b"raw REPL; CTRL-B to exit\r\n>", timeout=3)
        if b"raw REPL" in resp:
            return True

    return False


def raw_exec(sock: socket.socket, code: str) -> str:
    """Execute code in raw REPL mode and return the output."""
    sock.sendall(code.encode() + b"\x04")  # Ctrl-D to execute
    resp = read_until(sock, b"\x04>", timeout=10)
    return resp.decode(errors="replace")


def upload_file(sock: socket.socket, remote_path: str, local_path: Path) -> bool:
    """Upload a file by writing it through the raw REPL."""
    content = local_path.read_bytes()

    if "/" in remote_path:
        parent = remote_path.rsplit("/", 1)[0]
        raw_exec(
            sock, f"import os\ntry:\n os.mkdir('/{parent}')\nexcept OSError:\n pass"
        )

    chunk_size = 256
    raw_exec(sock, f"_f=open('/{remote_path}','wb')")
    for i in range(0, len(content), chunk_size):
        chunk = content[i : i + chunk_size]
        raw_exec(sock, f"_f.write({chunk!r})")
    raw_exec(sock, "_f.close()\ndel _f")
    return True


def update_ota_hashes() -> None:
    """Compute and save OTA hashes for all firmware files.

    Keeps .ota-hashes.json in sync so a subsequent OTA push
    won't re-upload files that were already deployed via USB/serial.
    """
    hashes = {}
    for remote_path, local_path in FILES:
        if local_path.exists():
            hashes[remote_path] = hashlib.md5(local_path.read_bytes()).hexdigest()
    HASH_FILE.write_text(json.dumps(hashes, indent=2) + "\n")
    print(f"Updated {HASH_FILE.name} ({len(hashes)} files)")


def sync(sock: socket.socket) -> bool:
    """Upload all firmware files and soft-reset."""
    print("Entering raw REPL...")
    if not enter_raw_repl(sock):
        print("ERROR: Could not enter raw REPL. Make sure the Wokwi tab is visible.")
        return False

    print("Uploading files...")
    for remote_path, local_path in FILES:
        if not local_path.exists():
            print(f"  SKIP {remote_path} (not found: {local_path})")
            continue
        print(f"  {remote_path}")
        upload_file(sock, remote_path, local_path)

    # Update OTA hashes so next ota-push.py won't re-upload everything
    update_ota_hashes()

    print("Soft-resetting board...")
    sock.sendall(b"\x02")  # Ctrl-B = exit raw REPL
    time.sleep(0.2)
    sock.sendall(b"\x04")  # Ctrl-D = soft reset
    time.sleep(0.5)
    drain(sock, 1.0)
    return True


def main() -> None:
    once = "--once" in sys.argv

    print(f"Connecting to Wokwi on {WOKWI_HOST}:{WOKWI_PORT}...")
    try:
        sock = socket.create_connection((WOKWI_HOST, WOKWI_PORT), timeout=5)
    except (ConnectionRefusedError, socket.timeout):
        print("ERROR: Cannot connect. Is the Wokwi simulator running and visible?")
        sys.exit(1)

    if not sync(sock):
        sock.close()
        sys.exit(1)

    print("Board running.")

    if once:
        sock.close()
        print("Done.")
        return

    # Watch mode: keep connection open for re-syncing
    print("Watching — Ctrl-C to re-sync, Ctrl-C twice to quit.\n")
    last_interrupt = 0.0
    while True:
        try:
            sock.settimeout(1.0)
            try:
                sock.recv(4096)
            except socket.timeout:
                pass
        except KeyboardInterrupt:
            now = time.time()
            if now - last_interrupt < 1.5:
                print("\nQuitting...")
                for _ in range(3):
                    sock.sendall(b"\x03")
                    time.sleep(0.1)
                sock.close()
                break
            last_interrupt = now
            print("\nRe-syncing...")
            if not sync(sock):
                sock.close()
                sys.exit(1)
            print(
                "Board running. Watching — Ctrl-C to re-sync, Ctrl-C twice to quit.\n"
            )

    print("Done.")


if __name__ == "__main__":
    main()
