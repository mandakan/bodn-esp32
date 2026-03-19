# bodn/web.py — minimal async HTTP server for parental controls

import os

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


async def _send(writer, status, content_type, body, extra_headers=None):
    """Send an HTTP response."""
    writer.write("HTTP/1.0 {} OK\r\n".format(status).encode())
    writer.write("Content-Type: {}\r\n".format(content_type).encode())
    writer.write("Content-Length: {}\r\n".format(len(body)).encode())
    if extra_headers:
        for h in extra_headers:
            writer.write("{}\r\n".format(h).encode())
    writer.write(b"Connection: close\r\n\r\n")
    writer.write(body if isinstance(body, bytes) else body.encode())
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


async def _read_raw_body(reader, headers):
    """Read HTTP body as raw bytes."""
    cl = int(headers.get("content-length", 0))
    if cl > 0:
        return await reader.read(cl)
    return b""


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

        # Parse body for POST (deferred for upload route)
        body = None
        raw_body = None
        if method == "POST" and path == "/api/upload":
            raw_body = await _read_raw_body(reader, headers)
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
                await _send(writer, 200, "application/json",
                            json.dumps({"ok": True}),
                            ["Set-Cookie: bodn_pin={}; Path=/; SameSite=Strict".format(pin)])
            else:
                await _send_unauthorized(writer, "Wrong PIN")
            return

        # --- Auth: OTA endpoints require bearer token ---
        if path in ("/api/upload", "/api/reboot", "/api/files"):
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
            await _send_json(writer, data)

        elif method == "GET" and path == "/api/settings":
            await _send_json(writer, settings)

        elif method == "POST" and path == "/api/settings":
            if body:
                settings.update(body)
                storage.save_settings(settings)
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
            from bodn.session import ALL_MODES
            mode_limits = settings.get("mode_limits", {})
            modes = []
            for m in ALL_MODES:
                modes.append({"name": m, "limit_min": mode_limits.get(m)})
            await _send_json(writer, modes)

        elif method == "POST" and path == "/api/wifi":
            if body:
                for k in ("wifi_mode", "wifi_ssid", "wifi_pass"):
                    if k in body:
                        settings[k] = body[k]
                storage.save_settings(settings)
            await _send_json(writer, {"ok": True})
            # Schedule reboot after response
            try:
                import machine

                asyncio.get_event_loop().call_later(1, machine.reset)
            except Exception:
                pass

        elif method == "POST" and path == "/api/upload":
            # OTA file upload: PUT file content with X-Path header
            remote_path = headers.get("x-path", "")
            if not remote_path or raw_body is None:
                await _send_json(writer, {"error": "need X-Path header and body"}, 400)
            else:
                try:
                    # Ensure parent directory exists
                    if "/" in remote_path:
                        parent = remote_path.rsplit("/", 1)[0]
                        try:
                            os.mkdir(parent)
                        except OSError:
                            pass
                    tmp = remote_path + ".tmp"
                    with open(tmp, "wb") as f:
                        f.write(raw_body)
                    try:
                        os.remove(remote_path)
                    except OSError:
                        pass
                    os.rename(tmp, remote_path)
                    await _send_json(writer, {"ok": True, "path": remote_path, "size": len(raw_body)})
                except Exception as e:
                    await _send_json(writer, {"error": str(e)}, 500)

        elif method == "POST" and path == "/api/reboot":
            await _send_json(writer, {"ok": True, "rebooting": True})
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
