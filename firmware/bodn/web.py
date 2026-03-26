# bodn/web.py — minimal async HTTP server for parental controls

import os

try:
    import hashlib
except ImportError:
    hashlib = None

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

try:
    import json
except ImportError:
    import ujson as json

from bodn.web_ui import HTML
from bodn import storage

OTA_STAGE = "/.ota"
_OTA_MANIFEST = OTA_STAGE + "/MANIFEST.json"


def _mkdirs(path):
    """Recursively create parent directories (MicroPython os.mkdir is single-level)."""
    parts = path.strip("/").split("/")
    for i in range(len(parts)):
        d = "/" + "/".join(parts[: i + 1])
        try:
            os.mkdir(d)
        except OSError:
            pass


def _rmtree(path):
    """Remove a directory tree (MicroPython has no shutil)."""
    try:
        for name in os.listdir(path):
            full = path + "/" + name
            try:
                os.listdir(full)  # if this works, it's a dir
                _rmtree(full)
            except OSError:
                os.remove(full)
        os.rmdir(path)
    except OSError:
        pass


def _ota_walk(stage_dir):
    """Yield (staged_path, target_path) pairs from the staging directory."""
    for name in os.listdir(stage_dir):
        full = stage_dir + "/" + name
        try:
            os.listdir(full)  # directory
            for pair in _ota_walk(full):
                yield pair
        except OSError:
            # It's a file — compute the target path by stripping the stage prefix
            target = full[len(OTA_STAGE) :]
            yield full, target


def _verify_manifest():
    """Check MANIFEST.json in staging against actual file hashes.

    Returns (ok: bool, errors: list[tuple]).
    If no manifest exists (HTTP OTA path), returns (True, []) — backward compat.
    If hashlib is unavailable, skips verification and returns (True, []).
    """
    if hashlib is None:
        return True, []
    try:
        with open(_OTA_MANIFEST) as f:
            manifest = json.load(f)
    except OSError:
        return True, []  # no manifest → HTTP OTA path, skip
    except Exception as e:
        return False, [("MANIFEST.json", "parse error: " + str(e))]

    files = manifest.get("files", {})
    if not files:
        return False, [("MANIFEST.json", "empty files list")]

    errors = []
    for rel_path, expected in files.items():
        staged = OTA_STAGE + "/" + rel_path
        try:
            h = hashlib.md5()
            with open(staged, "rb") as f:
                while True:
                    chunk = f.read(512)
                    if not chunk:
                        break
                    h.update(chunk)
            actual = "".join("{:02x}".format(b) for b in h.digest())
            if actual != expected:
                errors.append((rel_path, "hash mismatch"))
        except OSError:
            errors.append((rel_path, "missing from staging"))

    return len(errors) == 0, errors


async def _send(writer, status, content_type, body, extra_headers=None):
    """Send an HTTP response."""
    body_bytes = body if isinstance(body, bytes) else body.encode("utf-8")
    writer.write("HTTP/1.0 {} OK\r\n".format(status).encode())
    writer.write("Content-Type: {}\r\n".format(content_type).encode())
    writer.write("Content-Length: {}\r\n".format(len(body_bytes)).encode())
    if extra_headers:
        for h in extra_headers:
            writer.write("{}\r\n".format(h).encode())
    writer.write(b"Connection: close\r\n\r\n")
    writer.write(body_bytes)
    await writer.drain()


async def _send_json(writer, data, status=200):
    await _send(writer, status, "application/json", json.dumps(data))


async def _read_headers(reader):
    """Read HTTP headers, return dict."""
    headers = {}
    while True:
        line = await reader.readline()
        if line == b"\r\n" or line == b"\n" or line == b"":
            break
        if b":" in line:
            k, v = line.decode().split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return headers


async def _read_body(reader):
    """Read HTTP body as JSON (assumes Content-Length header present)."""
    headers = await _read_headers(reader)
    cl = int(headers.get("content-length", 0))
    if cl > 0:
        body = await reader.read(cl)
        return json.loads(body)
    return {}


def _check_pin(headers, settings):
    """Check if request has valid PIN cookie. Returns True if OK or no PIN set."""
    pin = settings.get("ui_pin", "")
    if not pin:
        return True
    cookie = headers.get("cookie", "")
    # Look for bodn_pin=XXXX in cookie header
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith("bodn_pin="):
            return part.split("=", 1)[1] == pin
    return False


def _check_ota_token(headers, settings):
    """Check if request has valid bearer token. Returns True if OK or no token set."""
    token = settings.get("ota_token", "")
    if not token:
        return True
    auth = headers.get("authorization", "")
    return auth == "Bearer " + token


async def _send_unauthorized(writer, msg="Unauthorized"):
    await _send(writer, 401, "application/json", json.dumps({"error": msg}))


async def _drain_body(reader, cl):
    """Read and discard cl bytes from reader."""
    while cl > 0:
        n = min(cl, 512)
        await reader.read(n)
        cl -= n


async def _handle_upload(reader, writer, headers):
    """OTA file upload — streams body to staging, checks free space first."""
    remote_path = headers.get("x-path", "")
    cl = int(headers.get("content-length", 0))

    if not remote_path:
        await _drain_body(reader, cl)
        await _send_json(writer, {"error": "need X-Path header"}, 400)
        return

    # Check free space (keep 4 KB reserve for filesystem metadata)
    try:
        st = os.statvfs("/")
        free = st[0] * st[3]  # f_bsize * f_bavail
    except Exception:
        free = 0
    if free > 0 and cl > free - 4096:
        await _drain_body(reader, cl)
        await _send_json(
            writer, {"error": "not enough space", "need": cl, "free": free}, 507
        )
        return

    try:
        staged = OTA_STAGE + remote_path
        parent = staged.rsplit("/", 1)[0]
        _mkdirs(parent)
        # Stream body in 512-byte chunks
        tmp = staged + ".tmp"
        written = 0
        with open(tmp, "wb") as f:
            remaining = cl
            while remaining > 0:
                n = min(remaining, 512)
                chunk = await reader.read(n)
                if not chunk:
                    break
                f.write(chunk)
                written += len(chunk)
                remaining -= len(chunk)
        try:
            os.remove(staged)
        except OSError:
            pass
        os.rename(tmp, staged)
        await _send_json(
            writer,
            {"ok": True, "path": remote_path, "staged": staged, "size": written},
        )
    except Exception as e:
        await _send_json(writer, {"error": str(e)}, 500)


async def _handle_request(reader, writer, session_mgr, settings):
    """Parse HTTP request and route to handler."""
    try:
        request_line = await reader.readline()
        if not request_line:
            return

        parts = request_line.decode().split()
        if len(parts) < 2:
            return

        method = parts[0]
        path = parts[1]

        # Read headers
        headers = await _read_headers(reader)

        # Parse body for POST (upload route streams directly to flash)
        body = None
        if method == "POST" and path == "/api/upload":
            pass  # body read inline by upload handler below
        elif method == "POST":
            cl = int(headers.get("content-length", 0))
            if cl > 0:
                raw = await reader.read(cl)
                body = json.loads(raw)

        # --- Auth: PIN login endpoint (always accessible) ---
        if method == "POST" and path == "/api/login":
            pin = settings.get("ui_pin", "")
            submitted = (body or {}).get("pin", "")
            if not pin or submitted == pin:
                await _send(
                    writer,
                    200,
                    "application/json",
                    json.dumps({"ok": True}),
                    ["Set-Cookie: bodn_pin={}; Path=/; SameSite=Strict".format(pin)],
                )
            else:
                await _send_unauthorized(writer, "Wrong PIN")
            return

        # --- Auth: OTA endpoints require bearer token ---
        ota_paths = (
            "/api/upload",
            "/api/reboot",
            "/api/files",
            "/api/ota/commit",
            "/api/ota/abort",
        )
        if path in ota_paths:
            if not _check_ota_token(headers, settings):
                await _send_unauthorized(writer, "Invalid OTA token")
                return

        # --- Auth: all other API/UI endpoints require PIN ---
        if path != "/api/login":
            if not _check_pin(headers, settings):
                # Serve the login page instead
                from bodn.web_ui import LOGIN_HTML

                await _send(writer, 200, "text/html", LOGIN_HTML)
                return

        # Route
        if method == "GET" and path == "/":
            await _send(writer, 200, "text/html", HTML)

        elif method == "GET" and path == "/api/status":
            data = {
                "state": session_mgr.state,
                "time_remaining_s": session_mgr.time_remaining_s,
                "sessions_today": session_mgr.sessions_today,
                "sessions_remaining": session_mgr.sessions_remaining,
                "max_session_s": settings["max_session_min"] * 60,
                "mode": session_mgr.mode,
            }
            try:
                from bodn import temperature

                t_max = temperature.max_temp()
                if t_max is not None:
                    data["temp_c"] = round(t_max, 1)
                    data["temp_status"] = temperature.status()
            except Exception:
                pass
            try:
                from bodn import battery

                pct, charging = battery.read()
                if pct is not None:
                    data["bat_pct"] = pct
                    data["bat_mv"] = battery.voltage_mv()
                    data["bat_status"] = battery.status()
                    data["bat_charging"] = charging
                else:
                    data["bat_status"] = "usb"
                    data["bat_charging"] = charging
            except Exception:
                pass
            await _send_json(writer, data)

        elif method == "GET" and path == "/api/settings":
            await _send_json(writer, settings)

        elif method == "POST" and path == "/api/settings":
            if body:
                settings.update(body)
                storage.save_settings(settings)
                # Apply language change immediately if included
                if "language" in body:
                    try:
                        from bodn.i18n import set_language

                        set_language(body["language"])
                    except Exception:
                        pass
            await _send_json(writer, {"ok": True})

        elif method == "POST" and path == "/api/lockdown":
            settings["lockdown"] = not settings.get("lockdown", False)
            storage.save_settings(settings)
            await _send_json(writer, {"ok": True, "lockdown": settings["lockdown"]})

        elif method == "GET" and path == "/api/history":
            sessions = storage.load_sessions()
            await _send_json(writer, sessions)

        elif method == "GET" and path == "/api/stats":
            sessions = storage.load_sessions()
            stats = storage.compute_stats(sessions)
            await _send_json(writer, stats)

        elif method == "GET" and path == "/api/modes":
            # Return all registered modes with visibility and per-mode limits
            all_modes = settings.get("_all_modes", [])
            mode_limits = settings.get("mode_limits", {})
            hidden = settings.get("hidden_modes", [])
            modes = []
            for m in all_modes:
                modes.append(
                    {
                        "name": m,
                        "visible": m not in hidden,
                        "limit_min": mode_limits.get(m),
                    }
                )
            await _send_json(writer, modes)

        elif method == "POST" and path == "/api/wifi":
            if body:
                for k in ("wifi_mode", "wifi_ssid", "wifi_pass", "hostname"):
                    if k in body:
                        settings[k] = body[k]
                storage.save_settings(settings)
            await _send_json(writer, {"ok": True})
            # Reboot after response is sent
            await asyncio.sleep_ms(500)
            try:
                os.sync()
            except AttributeError:
                pass
            import machine

            machine.reset()

        elif method == "POST" and path == "/api/upload":
            await _handle_upload(reader, writer, headers)

        elif method == "POST" and path == "/api/ota/commit":
            # Verify integrity (when MANIFEST.json is present), then move
            # staged files into place and reboot.
            try:
                ok, errors = _verify_manifest()
                if not ok:
                    await _send_json(
                        writer,
                        {"error": "integrity check failed", "details": errors},
                        400,
                    )
                    return
                count = 0
                for staged, target in _ota_walk(OTA_STAGE):
                    if staged == _OTA_MANIFEST:
                        continue  # control file — never deploy to live filesystem
                    parent = target.rsplit("/", 1)[0]
                    _mkdirs(parent)
                    try:
                        os.remove(target)
                    except OSError:
                        pass
                    os.rename(staged, target)
                    count += 1
                _rmtree(OTA_STAGE)
                # Flush filesystem to flash before hard reset — without this,
                # FAT metadata for unrelated dirs (e.g. /data/) can be lost.
                try:
                    os.sync()
                except AttributeError:
                    pass  # os.sync() not available on all builds
                await _send_json(writer, {"ok": True, "committed": count})
                try:
                    import machine

                    machine.reset()
                except Exception:
                    pass
            except Exception as e:
                await _send_json(writer, {"error": str(e)}, 500)

        elif method == "POST" and path == "/api/ota/abort":
            # Discard staged files.
            _rmtree(OTA_STAGE)
            await _send_json(writer, {"ok": True})

        elif method == "POST" and path == "/api/reboot":
            await _send_json(writer, {"ok": True, "rebooting": True})
            try:
                os.sync()
            except AttributeError:
                pass
            try:
                import machine

                machine.reset()
            except Exception:
                pass

        elif method == "POST" and path == "/api/debug/toggle":
            cur = settings.get("debug_input", False)
            settings["debug_input"] = not cur
            await _send_json(writer, {"debug_input": settings["debug_input"]})

        elif method == "GET" and path == "/api/files":
            # List files for dev UI
            file_list = []
            try:
                for name in os.listdir("/"):
                    file_list.append(name)
            except OSError:
                pass
            await _send_json(writer, file_list)

        else:
            await _send(writer, 404, "text/plain", "Not found")

    except Exception as e:
        try:
            await _send(writer, 500, "text/plain", str(e))
        except Exception:
            pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def start_server(session_mgr, settings, port=80):
    """Start the async web server. Returns the server object."""

    async def handler(reader, writer):
        try:
            await _handle_request(reader, writer, session_mgr, settings)
        except Exception as e:
            print("Web handler error:", e)

    server = await asyncio.start_server(handler, "0.0.0.0", port)
    return server
