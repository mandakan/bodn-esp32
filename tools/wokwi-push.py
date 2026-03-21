#!/usr/bin/env python3
"""Push file(s) to Wokwi and soft-reset. Shows device output after."""

import os
import socket
import sys
import time


def read_until(s, m, t=5):
    d = b""
    end = time.time() + t
    while time.time() < end:
        s.settimeout(max(0.1, end - time.time()))
        try:
            c = s.recv(4096)
            if not c:
                break
            d += c
            if m in d:
                return d
        except socket.timeout:
            pass
    return d


def drain(s, t=0.5):
    s.settimeout(t)
    try:
        while s.recv(4096):
            pass
    except socket.timeout:
        pass


def raw_exec(s, code):
    s.sendall(code.encode() + b"\x04")
    return read_until(s, b"\x04>", 10)


host, port = "localhost", 5555
files = sys.argv[1:]
if not files:
    print("Usage: wokwi-push.py firmware/path/file.py ...")
    sys.exit(1)

s = socket.create_connection((host, port), 5)
for _ in range(3):
    for _ in range(10):
        s.sendall(b"\x03")
        time.sleep(0.05)
    time.sleep(0.3)
    drain(s)
s.sendall(b"\x01")
if b"raw REPL" not in read_until(s, b"raw REPL", 3):
    print("ERROR: can't enter raw REPL")
    sys.exit(1)

for path in files:
    # Strip firmware/ prefix if present, otherwise use basename
    if "firmware/" in path:
        remote = path[path.index("firmware/") + 9 :]
    else:
        remote = os.path.basename(path)
    content = open(path, "rb").read()
    if "/" in remote:
        p = remote.rsplit("/", 1)[0]
        raw_exec(s, f"import os\ntry:\n os.mkdir('/{p}')\nexcept OSError:\n pass")
    raw_exec(s, f"_f=open('/{remote}','wb')")
    for i in range(0, len(content), 256):
        raw_exec(s, f"_f.write({content[i : i + 256]!r})")
    raw_exec(s, "_f.close();del _f")
    print(f"  /{remote} ({len(content)} bytes)")

s.sendall(b"\x02")
time.sleep(0.2)
s.sendall(b"\x04")
print("Reset. Watching output (Ctrl-C to quit)...")
try:
    while True:
        s.settimeout(1.0)
        try:
            data = s.recv(4096)
            if data:
                sys.stdout.write(data.decode(errors="replace"))
                sys.stdout.flush()
        except socket.timeout:
            pass
except KeyboardInterrupt:
    print("\nDone.")
s.close()
