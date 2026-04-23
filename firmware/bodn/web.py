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

# Deadline in ticks_ms; once past it, ota_active() returns False and the
# main render tasks go back to normal. Refreshed on every /api/upload
# and /api/ota/* call, so an interrupted deploy recovers on its own.
_OTA_QUIET_MS = 10_000


def _mark_ota_active(settings):
    """Extend the 'OTA in progress' window.

    primary_task / secondary_task poll `ota_active(settings)` and
    render the OTA status screen at low fps while the flag is set,
    freeing the Python VM so the upload handler's many `await` points
    return promptly instead of round-tripping through a full frame of
    the game screen each time.
    """
    import time

    settings["_ota_deadline_ms"] = time.ticks_add(time.ticks_ms(), _OTA_QUIET_MS)


def _reset_ota_progress(settings):
    """Clear per-sync counters. Called from /api/ota/begin and
    /api/ota/abort so the status screen doesn't show stale numbers
    from a previous sync.
    """
    settings["_ota_current_path"] = ""
    settings["_ota_files_done"] = 0
    settings["_ota_bytes_done"] = 0
    settings["_ota_total_files"] = 0
    settings["_ota_total_bytes"] = 0


def ota_active(settings):
    """Query whether we're currently mid-OTA and render loops should step aside."""
    deadline = settings.get("_ota_deadline_ms")
    if deadline is None:
        return False
    import time

    if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
        settings["_ota_deadline_ms"] = None
        return False
    return True


# MicroPython's FAT statvfs walks the FAT to count free clusters —
# ~1.1-1.3 s per call on the 6 MiB VFS partition. Calling it per
# /api/upload turned a 97-file --force into ~125 s of pure statvfs
# overhead. Cache the answer, decrement by bytes we write ourselves,
# and only re-stat when the estimate drifts stale (a fresh write might
# exceed it) or a generous time budget elapses.
_FREE_CACHE = {"bytes": None, "written_since": 0, "refreshed_ms": 0}
_FREE_REFRESH_BYTES = 500_000
_FREE_REFRESH_MS = 60_000


def _estimated_free(force=False):
    import time

    now = time.ticks_ms()
    stale = (
        _FREE_CACHE["bytes"] is None
        or force
        or _FREE_CACHE["written_since"] >= _FREE_REFRESH_BYTES
        or time.ticks_diff(now, _FREE_CACHE["refreshed_ms"]) >= _FREE_REFRESH_MS
    )
    if stale:
        try:
            st = os.statvfs("/")
            _FREE_CACHE["bytes"] = st[0] * st[3]
        except Exception:
            _FREE_CACHE["bytes"] = 0
        _FREE_CACHE["written_since"] = 0
        _FREE_CACHE["refreshed_ms"] = now
    return _FREE_CACHE["bytes"]


def _record_free_delta(bytes_written):
    """Decrement the cached estimate. Approximate — the FAT may charge
    a cluster-rounded amount, but over-writes get caught the next time
    we re-stat (either by the byte or time budget).
    """
    if _FREE_CACHE["bytes"] is not None:
        _FREE_CACHE["bytes"] -= bytes_written
    _FREE_CACHE["written_since"] += bytes_written


def _mkdirs(path):
    """Recursively create parent directories (MicroPython os.mkdir is single-level)."""
    parts = path.strip("/").split("/")
    for i in range(len(parts)):
        d = "/" + "/".join(parts[: i + 1])
        try:
            os.mkdir(d)
        except OSError:
            pass


async def _send(writer, status, content_type, body, extra_headers=None):
    """Send an HTTP response.

    Honours `writer._keep_alive` (set by the connection loop) to pick the
    response protocol (HTTP/1.1 vs 1.0) and Connection header. Always sends
    an explicit Content-Length so the client can reuse the socket.

    Batches headers + body into a single write(): under keep-alive there's
    no terminating close() to flush a half-filled segment, so splitting the
    response across multiple write() calls lets Nagle + delayed-ACK pair up
    and add ~hundreds of ms per request on MicroPython. One write() →
    one segment → fast.
    """
    keep_alive = getattr(writer, "_keep_alive", False)
    body_bytes = body if isinstance(body, bytes) else body.encode("utf-8")
    proto = "HTTP/1.1" if keep_alive else "HTTP/1.0"
    conn = "keep-alive" if keep_alive else "close"
    parts = [
        "{} {} OK\r\n".format(proto, status).encode(),
        "Content-Type: {}\r\n".format(content_type).encode(),
        "Content-Length: {}\r\n".format(len(body_bytes)).encode(),
    ]
    if extra_headers:
        for h in extra_headers:
            parts.append("{}\r\n".format(h).encode())
    parts.append("Connection: {}\r\n\r\n".format(conn).encode())
    parts.append(body_bytes)
    writer.write(b"".join(parts))
    await writer.drain()


def _wants_keep_alive(request_line, headers):
    """Decide whether to keep the connection open after this request.

    HTTP/1.1 defaults to keep-alive (RFC 7230); HTTP/1.0 defaults to close
    unless the client opted in with `Connection: keep-alive`. An explicit
    `Connection: close` always wins.
    """
    conn = headers.get("connection", "").lower()
    if "close" in conn:
        return False
    if "keep-alive" in conn:
        return True
    return b"HTTP/1.1" in request_line


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
        chunk = await reader.read(n)
        if not chunk:
            break
        cl -= len(chunk)


async def _read_exact(reader, n):
    """Read exactly n bytes (loops until full or EOF). Required for
    keep-alive: a single read() may return short, leaving body bytes in
    the socket that would then be parsed as the next request line.
    """
    if n <= 0:
        return b""
    buf = bytearray()
    while len(buf) < n:
        chunk = await reader.read(n - len(buf))
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)


async def _handle_upload(reader, writer, headers, settings=None):
    """OTA file upload — streams body directly to the target path.

    We used to stage into /.ota/ and copy to live on commit, but that
    doubles filesystem usage, which exceeds the VFS partition on the 8 MiB
    build once firmware grows past ~half the partition. HTTP uploads are
    one-file-at-a-time and retry per file, so per-file atomicity (write
    .new + rename) is sufficient.

    When `settings["debug_ota"]` is truthy, prints a per-phase timing
    breakdown to serial so a slow floor can be diagnosed without guessing.
    """
    import time

    debug = bool(settings and settings.get("debug_ota"))
    ticks = time.ticks_ms
    diff = time.ticks_diff
    t_start = ticks()

    remote_path = headers.get("x-path", "")
    cl = int(headers.get("content-length", 0))
    tracker = settings.get("_idle_tracker") if settings is not None else None

    # Publish the current file path so the OTA status screen can show
    # it while we process this upload.
    if settings is not None and remote_path:
        settings["_ota_current_path"] = remote_path

    if not remote_path:
        await _drain_body(reader, cl)
        await _send_json(writer, {"error": "need X-Path header"}, 400)
        return

    # Need room for the new copy + small metadata reserve. The old copy
    # still on disk is freed by the rename below; if the new file is
    # larger than the old we have to hold both briefly, which is what
    # this check ensures. Uses the cached estimate — see _estimated_free.
    t_stat0 = ticks()
    free = _estimated_free()
    t_stat = diff(ticks(), t_stat0)
    if free > 0 and cl > free - 4096:
        # Cache may be stale — force one authoritative re-stat before
        # refusing the upload.
        free = _estimated_free(force=True)
    if free > 0 and cl > free - 4096:
        await _drain_body(reader, cl)
        await _send_json(
            writer, {"error": "not enough space", "need": cl, "free": free}, 507
        )
        return

    try:
        target = remote_path  # remote_path starts with "/"
        parent = target.rsplit("/", 1)[0]
        if parent and parent != "":
            _mkdirs(parent)
        written = 0
        # 4 KiB chunks: 8× fewer Python loop iterations than 512 B, and
        # comfortably fits in L1 on the ESP32-S3. Flash writes are
        # block-level anyway, so larger chunks also reduce FAT overhead.
        CHUNK = 4096
        short_read = False
        # Write directly to target — not via a `.new` + remove + rename
        # dance. On MicroPython FAT, each os.rename costs ~150-1000 ms
        # (rises linearly within a directory until it hits a cluster
        # boundary), and every rename is preceded by an os.remove that
        # also scans the directory. Over a 97-file --force that totalled
        # ~60 s of pure FAT metadata work. Writing in place sacrifices
        # atomicity (power loss mid-write corrupts the target instead
        # of keeping the old version), which is an acceptable trade-off
        # for HTTP OTA: the client retries on error, and on any write
        # exception we delete the target so the next boot fails
        # cleanly on a missing file rather than importing a truncated
        # one.
        t_open0 = ticks()
        t_read = 0
        t_write = 0
        with open(target, "wb") as f:
            t_open = diff(ticks(), t_open0)
            remaining = cl
            bytes_since_poke = 0
            while remaining > 0:
                n = min(remaining, CHUNK)
                tr0 = ticks()
                chunk = await reader.read(n)
                t_read += diff(ticks(), tr0)
                if not chunk:
                    short_read = True
                    break
                tw0 = ticks()
                f.write(chunk)
                t_write += diff(ticks(), tw0)
                written += len(chunk)
                remaining -= len(chunk)
                bytes_since_poke += len(chunk)
                # Keep idle timer fresh during long single-file uploads
                # (~every 32 KB regardless of chunk size).
                if tracker is not None and bytes_since_poke >= 32768:
                    tracker.poke()
                    bytes_since_poke = 0
        if short_read:
            # The file is now truncated on flash. Delete it — better a
            # missing import than a half-written one.
            try:
                os.remove(target)
            except OSError:
                pass
            # Socket framing is also ambiguous — force the client to
            # reconnect rather than misread leftover bytes as the next
            # request line.
            writer._keep_alive = False
        _record_free_delta(written)
        # Bump per-sync counters for the status screen.
        if settings is not None:
            settings["_ota_files_done"] = settings.get("_ota_files_done", 0) + 1
            settings["_ota_bytes_done"] = settings.get("_ota_bytes_done", 0) + written
        t_resp0 = ticks()
        await _send_json(
            writer,
            {"ok": True, "path": remote_path, "size": written},
        )
        t_resp = diff(ticks(), t_resp0)
        if debug:
            print(
                "OTA {} {}B  stat={} open={} read={} write={} resp={} total={}".format(
                    remote_path,
                    written,
                    t_stat,
                    t_open,
                    t_read,
                    t_write,
                    t_resp,
                    diff(ticks(), t_start),
                )
            )
    except Exception as e:
        # Mid-write failure leaves an unknown number of bytes in the
        # socket AND possibly a partial file. Delete the partial and
        # drop the connection.
        try:
            os.remove(target)
        except (OSError, NameError):
            pass
        writer._keep_alive = False
        await _send_json(writer, {"error": str(e)}, 500)


async def _handle_request(reader, writer, request_line, session_mgr, settings):
    """Parse HTTP request and route to handler.

    `request_line` has already been read by the connection loop. Returns
    True if the connection should be kept alive for another request.
    """
    # Default: don't keep alive — error paths fall through here and we
    # can't safely reuse the socket if the request body wasn't drained.
    writer._keep_alive = False
    try:
        # Keep the device awake while clients are actively talking to us —
        # OTA/UI/status requests all count as activity. Without this a
        # multi-minute sync can trip the idle-timeout lightsleep.
        tracker = settings.get("_idle_tracker")
        if tracker is not None:
            tracker.poke()

        parts = request_line.decode().split()
        if len(parts) < 2:
            return False

        method = parts[0]
        path = parts[1]

        # Read headers
        headers = await _read_headers(reader)
        # Decide keep-alive intent now that we have headers; individual
        # endpoints can downgrade to close (e.g. before reboot, or when
        # they bail without draining the body).
        writer._keep_alive = _wants_keep_alive(request_line, headers)

        # Parse body for POST (upload route streams directly to flash)
        body = None
        if method == "POST" and path == "/api/upload":
            pass  # body read inline by upload handler below
        elif method == "POST":
            cl = int(headers.get("content-length", 0))
            if cl > 0:
                raw = await _read_exact(reader, cl)
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
            return writer._keep_alive

        # --- Auth: OTA endpoints require bearer token ---
        ota_paths = (
            "/api/upload",
            "/api/reboot",
            "/api/files",
            "/api/ota/begin",
            "/api/ota/commit",
            "/api/ota/abort",
        )
        if path in ota_paths:
            if not _check_ota_token(headers, settings):
                # /api/upload bodies are large and we haven't read them
                # yet — force the client to reconnect rather than draining
                # a rejected upload through the socket.
                writer._keep_alive = False
                await _send_unauthorized(writer, "Invalid OTA token")
                return False
            # Mark OTA active *after* auth succeeds — an attacker probing
            # with no token shouldn't be able to freeze the UI.
            _mark_ota_active(settings)

        # --- Auth: all other API/UI endpoints require PIN ---
        if path != "/api/login":
            if not _check_pin(headers, settings):
                # Serve the login page instead
                from bodn.web_ui import LOGIN_HTML

                await _send(writer, 200, "text/html", LOGIN_HTML)
                return writer._keep_alive

        # Route
        if method == "GET" and path == "/":
            await _send(writer, 200, "text/html", HTML)

        elif method == "GET" and path == "/api/status":
            data = {
                "state": session_mgr.state,
                "time_remaining_s": session_mgr.time_remaining_s,
                "cooldown_remaining_s": session_mgr.cooldown_remaining_s,
                "break_s": settings["break_min"] * 60,
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
            # Strip runtime-only keys (non-serializable objects like _pwm,
            # _idle_tracker, plus internal lists like _all_modes).
            public = {k: v for k, v in settings.items() if not k.startswith("_")}
            # Never echo the WiFi password back. The UI gets a
            # `wifi_pass_set` flag instead and only sends a new password
            # when the user actually wants to replace it.
            stored_pass = public.pop("wifi_pass", "")
            public["wifi_pass_set"] = bool(stored_pass)
            await _send_json(writer, public)

        elif method == "GET" and path == "/api/wifi/status":
            from bodn import wifi as _wifi

            data = {
                "wifi_mode": settings.get("wifi_mode", "ap"),
                "stored_ssid": settings.get("wifi_ssid", ""),
                "live_ssid": _wifi.live_ssid(),
                "connected": _wifi.is_sta_connected(),
                "ip": _wifi.get_ip(),
                "hostname": settings.get("hostname", "bodn"),
                "wifi_pass_set": bool(settings.get("wifi_pass", "")),
            }
            await _send_json(writer, data)

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

        elif method == "POST" and path == "/api/resume":
            ok = session_mgr.resume_now()
            await _send_json(writer, {"ok": ok, "state": session_mgr.state})

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
                for k in ("wifi_mode", "wifi_ssid", "hostname"):
                    if k in body:
                        settings[k] = body[k]
                # Only overwrite the stored password when the client sends
                # a non-empty value. The UI leaves the field blank to mean
                # "keep the existing password" — clearing it here would
                # silently brick STA mode on the next reboot.
                new_pass = body.get("wifi_pass")
                if new_pass:
                    settings["wifi_pass"] = new_pass
                storage.save_settings(settings)
            writer._keep_alive = False  # we're about to reset
            await _send_json(writer, {"ok": True})
            # Reboot after response is sent
            await asyncio.sleep_ms(500)
            try:
                os.sync()
            except Exception:
                pass
            import machine

            machine.reset()

        elif method == "POST" and path == "/api/upload":
            await _handle_upload(reader, writer, headers, settings=settings)

        elif method == "POST" and path == "/api/ota/commit":
            # HTTP (/api/upload) writes directly to the live path, so commit
            # is just "flush FAT metadata and reboot".
            try:
                # Flush filesystem to flash before hard reset — without this,
                # FAT metadata for unrelated dirs (e.g. /data/) can be lost.
                try:
                    os.sync()
                except Exception:
                    pass  # os.sync() not available on all builds
                writer._keep_alive = False  # we're about to reset
                await _send_json(writer, {"ok": True, "committed": 0})
                try:
                    import machine

                    machine.reset()
                except Exception:
                    pass
            except Exception as e:
                await _send_json(writer, {"error": str(e)}, 500)

        elif method == "POST" and path == "/api/ota/begin":
            # Called by ota-push.py once per sync, before the first
            # /api/upload, with {"files": N, "bytes": M}. Used by the
            # OTA status screen to render a real progress bar instead
            # of an indeterminate pulse. Body is optional — if it's
            # missing we just fall through to the indeterminate state.
            _reset_ota_progress(settings)
            if body:
                try:
                    settings["_ota_total_files"] = int(body.get("files", 0) or 0)
                    settings["_ota_total_bytes"] = int(body.get("bytes", 0) or 0)
                except (TypeError, ValueError):
                    pass  # malformed — keep the zeroed counters
            await _send_json(writer, {"ok": True})

        elif method == "POST" and path == "/api/ota/abort":
            # Clear any progress state — a follow-up sync starts fresh.
            _reset_ota_progress(settings)
            await _send_json(writer, {"ok": True})

        elif method == "POST" and path == "/api/reboot":
            writer._keep_alive = False  # we're about to reset
            await _send_json(writer, {"ok": True, "rebooting": True})
            try:
                os.sync()
            except Exception:
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

        elif method == "GET" and path == "/api/boot-log":
            try:
                with open("/data/boot_log.json") as f:
                    raw = f.read()
                await _send(writer, 200, "application/json", raw)
            except OSError:
                await _send_json(writer, {"error": "no boot log yet"})

        elif method == "GET" and path == "/api/files":
            # List files for dev UI
            file_list = []
            try:
                for name in os.listdir("/"):
                    file_list.append(name)
            except OSError:
                pass
            await _send_json(writer, file_list)

        # --- NFC card set endpoints ---

        elif method == "GET" and path == "/api/nfc/sets":
            try:
                from bodn.nfc import list_card_sets, load_card_set

                sets = []
                for mode in list_card_sets():
                    cs = load_card_set(mode)
                    if cs:
                        sets.append(
                            {
                                "mode": mode,
                                "version": cs.get("version", 1),
                                "card_count": len(cs.get("cards", [])),
                                "dimensions": cs.get("dimensions", []),
                            }
                        )
                await _send_json(writer, sets)
            except Exception as e:
                await _send_json(writer, {"error": str(e)}, 500)

        elif method == "GET" and path.startswith("/api/nfc/set/"):
            mode_name = path.rsplit("/", 1)[-1]
            try:
                from bodn.nfc import load_card_set

                cs = load_card_set(mode_name)
                if cs:
                    await _send_json(writer, cs)
                else:
                    await _send_json(writer, {"error": "not found"}, 404)
            except Exception as e:
                await _send_json(writer, {"error": str(e)}, 500)

        elif method == "GET" and path == "/api/nfc/cache":
            try:
                from bodn.nfc import UIDCache

                cache = UIDCache()
                await _send_json(writer, cache.entries())
            except Exception as e:
                await _send_json(writer, {"error": str(e)}, 500)

        # NFC provisioning endpoints (POST /api/nfc/provision/*) will be
        # added when the PN532 hardware reader is available (issue #121).

        else:
            await _send(writer, 404, "text/plain", "Not found")

    except Exception as e:
        # Internal error: socket may be in an unknown state — close.
        writer._keep_alive = False
        try:
            await _send(writer, 500, "text/plain", str(e))
        except Exception:
            pass

    return writer._keep_alive


# Idle timeout for an open keep-alive connection. The full --force OTA
# push has gaps of a few hundred ms between requests; 5 s is plenty of
# headroom while still freeing the socket promptly when the client is
# done.
_KEEP_ALIVE_IDLE_S = 5


async def _connection_loop(reader, writer, session_mgr, settings):
    """Serve sequential requests on one TCP connection until the client
    closes, the keep-alive timeout fires, or a handler downgrades to
    Connection: close.
    """
    try:
        while True:
            try:
                request_line = await asyncio.wait_for(
                    reader.readline(), _KEEP_ALIVE_IDLE_S
                )
            except Exception:
                # asyncio.TimeoutError on idle, or a transport error —
                # either way we're done with this connection.
                break
            if not request_line:
                break  # client closed cleanly between requests
            keep_alive = await _handle_request(
                reader, writer, request_line, session_mgr, settings
            )
            if not keep_alive:
                break
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


def _disable_nagle(writer):
    """Turn off Nagle's algorithm on the accepted TCP socket.

    Without TCP_NODELAY, small writes (response headers, small JSON
    bodies) get stuck waiting for the ACK of the previous segment, which
    on MicroPython's lwIP can pause ~200ms per request. Under keep-alive
    this overhead stacks across every file in an OTA sync.
    """
    sock = None
    try:
        sock = writer.get_extra_info("socket")
    except Exception:
        pass
    if sock is None:
        sock = getattr(writer, "s", None)  # MicroPython uasyncio
    if sock is None:
        return
    try:
        import socket as _sock

        sock.setsockopt(_sock.IPPROTO_TCP, _sock.TCP_NODELAY, 1)
    except Exception:
        pass  # platform/build doesn't expose TCP_NODELAY — no-op


async def start_server(session_mgr, settings, port=80):
    """Start the async web server. Returns the server object."""

    async def handler(reader, writer):
        _disable_nagle(writer)
        try:
            await _connection_loop(reader, writer, session_mgr, settings)
        except Exception as e:
            print("Web handler error:", e)

    server = await asyncio.start_server(handler, "0.0.0.0", port)
    return server
