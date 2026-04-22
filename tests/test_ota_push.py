"""Test the OTA push client's connection-reuse behaviour.

Loads tools/ota-push.py by path (the hyphen in the filename makes a
plain `import` awkward) and stubs out http.client.HTTPConnection so we
can count how many TCP connections it actually opens for N requests.

Regression target: before HTTP keep-alive, every file opened a fresh
TCP connection — N files = N connections + N handshakes (~2 s of floor
each on the ESP32). After: one connection should serve them all.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
OTA_PUSH_PATH = REPO_ROOT / "tools" / "ota-push.py"


def _load_ota_push():
    spec = importlib.util.spec_from_file_location("ota_push", OTA_PUSH_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ota_push"] = mod
    spec.loader.exec_module(mod)
    return mod


ota_push = _load_ota_push()


class FakeResponse:
    """Minimal stand-in for http.client.HTTPResponse."""

    def __init__(
        self, status: int = 200, body: bytes = b'{"ok":true}', will_close: bool = False
    ):
        self.status = status
        self._body = body
        self.will_close = will_close

    def read(self) -> bytes:
        return self._body


class FakeConnection:
    """Counts how many requests were sent on this connection."""

    instances: list["FakeConnection"] = []

    def __init__(self, host, port=80, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.requests: list[tuple[str, str, bytes, dict]] = []
        self.closed = False
        self.sock = None  # ota-push.py touches this when adjusting timeouts
        self._will_close_next = False
        FakeConnection.instances.append(self)

    def request(self, method, url, body=None, headers=None):
        self.requests.append((method, url, body or b"", dict(headers or {})))

    def getresponse(self):
        return FakeResponse(will_close=self._will_close_next)

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def reset_fake_connections():
    FakeConnection.instances.clear()
    yield
    FakeConnection.instances.clear()


def test_keep_alive_reuses_one_connection_for_many_requests(monkeypatch):
    monkeypatch.setattr(ota_push.http.client, "HTTPConnection", FakeConnection)
    client = ota_push.KeepAliveClient("http://device.local")

    for i in range(50):
        status, _ = client.request(
            "POST", "/api/upload", b"data", {"X-Path": f"/f{i}.py"}
        )
        assert status == 200

    assert len(FakeConnection.instances) == 1
    assert client.connect_count == 1
    assert len(FakeConnection.instances[0].requests) == 50


def test_keep_alive_advertised_in_headers(monkeypatch):
    monkeypatch.setattr(ota_push.http.client, "HTTPConnection", FakeConnection)
    client = ota_push.KeepAliveClient("http://device.local")
    client.request("POST", "/api/upload", b"x", {"X-Path": "/a.py"})

    sent_headers = FakeConnection.instances[0].requests[0][3]
    assert sent_headers.get("Connection") == "keep-alive"
    # Caller-supplied header survives.
    assert sent_headers.get("X-Path") == "/a.py"
    # Content-Length is set even when caller omits it.
    assert sent_headers.get("Content-Length") == "1"


def test_reconnect_on_server_close(monkeypatch):
    """If the server closes the socket between requests we should
    transparently open a new one and the caller never sees an error."""

    class FlakyConnection(FakeConnection):
        def getresponse(self):
            # First call: act normal but mark socket as torn down so
            # the next request() raises (the real http.client raises
            # RemoteDisconnected when the peer closed before the next
            # request was sent).
            if len(self.requests) == 1 and not getattr(self, "_primed", False):
                self._primed = True
                return FakeResponse()
            raise ConnectionResetError("server closed idle socket")

    monkeypatch.setattr(ota_push.http.client, "HTTPConnection", FlakyConnection)
    client = ota_push.KeepAliveClient("http://device.local")

    # First request: succeeds on the original connection.
    status, _ = client.request("POST", "/api/upload", b"a", {"X-Path": "/a"})
    assert status == 200
    # Second request: first connection raises on getresponse, so we
    # reconnect and retry. The reconnect itself succeeds.
    status, _ = client.request("POST", "/api/upload", b"b", {"X-Path": "/b"})
    assert status == 200

    # We opened at least 2 connections in total (original + at least
    # one reconnect after the simulated server close).
    assert client.connect_count >= 2


def test_close_drops_cached_connection(monkeypatch):
    monkeypatch.setattr(ota_push.http.client, "HTTPConnection", FakeConnection)
    client = ota_push.KeepAliveClient("http://device.local")
    client.request("POST", "/api/upload", b"x", {"X-Path": "/a"})
    first = FakeConnection.instances[-1]
    client.close()
    assert first.closed is True

    client.request("POST", "/api/upload", b"x", {"X-Path": "/b"})
    # A second connection was opened after close().
    assert client.connect_count == 2
    assert len(FakeConnection.instances) == 2


def test_will_close_response_drops_socket(monkeypatch):
    """If the server replies Connection: close (via response.will_close)
    we should drop the cached socket so the next request reconnects."""

    class CloseAfterFirst(FakeConnection):
        def getresponse(self):
            return FakeResponse(will_close=True)

    monkeypatch.setattr(ota_push.http.client, "HTTPConnection", CloseAfterFirst)
    client = ota_push.KeepAliveClient("http://device.local")
    client.request("POST", "/api/upload", b"x", {"X-Path": "/a"})
    client.request("POST", "/api/upload", b"x", {"X-Path": "/b"})

    assert client.connect_count == 2


# ─────────────────────────────────────────────────────────────────────
# End-to-end: real bodn.web server + real http.client over a local
# socket. Catches server-side keep-alive bugs (framing, idle timeout,
# header parsing) that pure mock tests can't see.
# ─────────────────────────────────────────────────────────────────────


def _start_real_server(port: int):
    """Boot bodn.web on 127.0.0.1:port in a background thread.

    Returns (thread, settings, stop_callable). The thread runs its own
    asyncio loop so the test can use blocking http.client calls.
    """
    import asyncio
    import threading
    import bodn.web as web

    settings = {
        "ui_pin": "",
        "ota_token": "",
        "max_session_min": 10,
        "break_min": 15,
    }

    class FakeSession:
        state = "idle"
        time_remaining_s = 0
        cooldown_remaining_s = 0
        sessions_today = 0
        sessions_remaining = 0
        mode = None

    loop_holder = {}

    def run():
        loop = asyncio.new_event_loop()
        loop_holder["loop"] = loop
        asyncio.set_event_loop(loop)
        server = loop.run_until_complete(
            web.start_server(FakeSession(), settings, port=port)
        )
        loop_holder["server"] = server
        try:
            loop.run_forever()
        finally:
            loop.close()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    # Wait for server to be ready.
    import socket
    import time

    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.02)
    else:
        raise RuntimeError("server did not start")

    def stop():
        loop = loop_holder.get("loop")
        if loop is None:
            return
        loop.call_soon_threadsafe(loop.stop)
        t.join(timeout=2)

    return settings, stop


@pytest.fixture
def real_server():
    """Boot bodn.web on a free port; tear it down after the test."""
    import socket as _s

    with _s.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    settings, stop = _start_real_server(port)
    try:
        yield port, settings
    finally:
        stop()


def test_server_serves_many_requests_on_one_connection(real_server, tmp_path):
    """Send 100 sequential GET /api/status on one TCP connection."""
    port, _settings = real_server
    client = ota_push.KeepAliveClient(f"http://127.0.0.1:{port}", timeout=5)
    try:
        for _ in range(100):
            status, body = client.request("GET", "/api/status", b"", {})
            assert status == 200
            assert b"state" in body
        assert client.connect_count == 1
    finally:
        client.close()


def test_server_idle_timeout_closes_connection(real_server):
    """After the server-side idle timeout the socket is closed; next
    request must transparently reconnect."""
    import time

    # Patch the idle timeout down to keep the test fast.
    import bodn.web as web

    original = web._KEEP_ALIVE_IDLE_S
    web._KEEP_ALIVE_IDLE_S = 0.3
    try:
        port, _ = real_server
        client = ota_push.KeepAliveClient(f"http://127.0.0.1:{port}", timeout=5)
        try:
            status, _ = client.request("GET", "/api/status", b"", {})
            assert status == 200
            time.sleep(0.6)  # let the server-side idle timeout fire
            status, _ = client.request("GET", "/api/status", b"", {})
            assert status == 200
            assert client.connect_count >= 2
        finally:
            client.close()
    finally:
        web._KEEP_ALIVE_IDLE_S = original


def test_server_honours_connection_close(real_server):
    """When the client sends Connection: close the server must not keep
    the socket open."""
    import http.client

    port, _ = real_server
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/api/status", headers={"Connection": "close"})
    resp = conn.getresponse()
    resp.read()
    assert resp.status == 200
    assert resp.will_close, "server should echo Connection: close"
    conn.close()
