"""Tests for the web UI NFC provisioning endpoints (issue #170).

Covers:
- GET /api/nfc/provision/status returns the shared provisioning snapshot.
- POST /api/nfc/provision/start arms the reader and triggers a write.
- POST /api/nfc/provision/cancel releases web ownership.
- Concurrency guard: the web side refuses to start while owner=="device".
"""

import asyncio
import json

import pytest

from bodn import nfc, web

# ---------------------------------------------------------------------------
# Test scaffolding (mirrors test_web_wifi.py — kept local to avoid coupling)
# ---------------------------------------------------------------------------


class _FakeReader:
    def __init__(self, data: bytes):
        self._buf = data

    async def readline(self):
        idx = self._buf.find(b"\n")
        if idx == -1:
            line, self._buf = self._buf, b""
            return line
        line, self._buf = self._buf[: idx + 1], self._buf[idx + 1 :]
        return line

    async def read(self, n):
        chunk, self._buf = self._buf[:n], self._buf[n:]
        return chunk


class _FakeWriter:
    def __init__(self):
        self.buf = bytearray()
        self._keep_alive = False

    def write(self, data):
        self.buf.extend(data)

    async def drain(self):
        return None


class _FakeSession:
    state = "IDLE"
    time_remaining_s = 0
    cooldown_remaining_s = 0
    sessions_today = 0
    sessions_remaining = 0
    mode = None


def _request(method, path, body=None):
    headers = ["Host: test", "Connection: close"]
    body_bytes = b""
    if body is not None:
        body_bytes = json.dumps(body).encode()
        headers.append("Content-Type: application/json")
        headers.append("Content-Length: {}".format(len(body_bytes)))
    request_line = "{} {} HTTP/1.1\r\n".format(method, path).encode()
    rest = ("\r\n".join(headers) + "\r\n\r\n").encode() + body_bytes
    return request_line, _FakeReader(rest)


def _run(method, path, settings, body=None):
    request_line, reader = _request(method, path, body=body)
    writer = _FakeWriter()
    asyncio.run(
        web._handle_request(reader, writer, request_line, _FakeSession(), settings)
    )
    raw = bytes(writer.buf)
    head, _, payload = raw.partition(b"\r\n\r\n")
    status_line = head.split(b"\r\n", 1)[0].decode()
    try:
        data = json.loads(payload.decode())
    except (ValueError, UnicodeDecodeError):
        data = None
    return status_line, data


@pytest.fixture
def settings():
    return {
        "wifi_mode": "ap",
        "wifi_ssid": "",
        "wifi_pass": "",
        "hostname": "bodn",
        "ui_pin": "",
        "ota_token": "",
    }


class _FakePN532:
    """Minimal PN532 stub with a configurable write result."""

    def __init__(self, write_ok=True, uid=b"\x04\xaa\xbb\xcc"):
        self.write_ok = write_ok
        self._uid = uid
        self.writes = []

    def read_passive_target(self, timeout_ms=500):
        return self._uid

    def ntag_write(self, page, chunk):
        self.writes.append((page, bytes(chunk)))
        return self.write_ok


_TEST_CARD_SETS = {
    "sortera": {
        "mode": "sortera",
        "version": 1,
        "dimensions": ["animal"],
        "cards": [{"id": "cat_red", "label_sv": "katt", "label_en": "cat"}],
    }
}


@pytest.fixture
def reader_available(monkeypatch):
    """Install a fake PN532 + stub card-set loaders.

    Host tests don't have /nfc/*.json on disk, so we patch the loaders
    module-wide.  The endpoint re-imports them at call time, so the
    patch takes effect even though web.py already imported bodn.nfc.
    """
    old_pn = nfc._pn532
    old_shed = nfc._shed
    pn = _FakePN532(write_ok=True)
    nfc._pn532 = pn
    nfc._shed = False
    monkeypatch.setattr(nfc, "load_card_set", lambda mode: _TEST_CARD_SETS.get(mode))

    def fake_lookup(mode, card_id):
        cs = _TEST_CARD_SETS.get(mode)
        if cs is None:
            return None
        for c in cs.get("cards", []):
            if c["id"] == card_id:
                return c
        return None

    monkeypatch.setattr(nfc, "lookup_card", fake_lookup)
    # Ensure provisioning state is clean before each test.
    nfc.provision_release()
    try:
        yield pn
    finally:
        nfc._pn532 = old_pn
        nfc._shed = old_shed
        nfc.provision_release()


# ---------------------------------------------------------------------------
# Shared state module (bodn.nfc.provision_*)
# ---------------------------------------------------------------------------


class TestProvisionState:
    def test_initial_state_is_idle(self):
        nfc.provision_release()
        snap = nfc.provision_state()
        assert snap["state"] == "idle"
        assert snap["owner"] is None

    def test_acquire_sets_owner_and_suspends_scan(self):
        nfc.provision_release()
        assert nfc.is_scan_suspended() is False
        assert nfc.provision_acquire("web", "sortera", "cat_red") is True
        snap = nfc.provision_state()
        assert snap["owner"] == "web"
        assert snap["state"] == "armed"
        assert snap["mode"] == "sortera"
        assert snap["card_id"] == "cat_red"
        assert nfc.is_scan_suspended() is True
        nfc.provision_release("web")
        assert nfc.is_scan_suspended() is False

    def test_different_owner_rejected(self):
        nfc.provision_release()
        assert nfc.provision_acquire("device") is True
        # Web must not be able to steal the reader from the device screen.
        assert nfc.provision_acquire("web", "sortera", "cat_red") is False
        assert nfc.provision_state()["owner"] == "device"
        nfc.provision_release("device")

    def test_same_owner_reacquire_rearms(self):
        nfc.provision_release()
        assert nfc.provision_acquire("web", "sortera", "cat_red") is True
        assert nfc.provision_acquire("web", "rakna", "num_3") is True
        snap = nfc.provision_state()
        assert snap["mode"] == "rakna"
        assert snap["card_id"] == "num_3"
        nfc.provision_release("web")

    def test_release_with_wrong_owner_is_noop(self):
        nfc.provision_release()
        nfc.provision_acquire("device")
        assert nfc.provision_release("web") is False
        assert nfc.provision_state()["owner"] == "device"
        nfc.provision_release("device")

    def test_mark_only_updates_for_current_owner(self):
        nfc.provision_release()
        nfc.provision_acquire("web", "sortera", "cat_red")
        assert nfc.provision_mark("web", "writing") is True
        assert nfc.provision_state()["state"] == "writing"
        # A stale handler with the wrong owner must not clobber state.
        assert nfc.provision_mark("device", "ok") is False
        assert nfc.provision_state()["state"] == "writing"
        nfc.provision_release("web")


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------


class TestProvisionEndpoints:
    def test_status_reports_reader_available_and_idle(self, settings, reader_available):
        status, data = _run("GET", "/api/nfc/provision/status", settings)
        assert "200" in status
        assert data["state"] == "idle"
        assert data["owner"] is None
        assert data["reader_available"] is True

    def test_status_reports_reader_unavailable(self, settings):
        old_pn = nfc._pn532
        nfc._pn532 = None
        try:
            status, data = _run("GET", "/api/nfc/provision/status", settings)
            assert "200" in status
            assert data["reader_available"] is False
        finally:
            nfc._pn532 = old_pn

    def test_start_without_reader_returns_503(self, settings, monkeypatch):
        old_pn = nfc._pn532
        nfc._pn532 = None
        monkeypatch.setattr(
            nfc, "load_card_set", lambda mode: _TEST_CARD_SETS.get(mode)
        )
        monkeypatch.setattr(
            nfc,
            "lookup_card",
            lambda mode, cid: next(
                (
                    c
                    for c in _TEST_CARD_SETS.get(mode, {}).get("cards", [])
                    if c["id"] == cid
                ),
                None,
            ),
        )
        nfc.provision_release()
        try:
            status, data = _run(
                "POST",
                "/api/nfc/provision/start",
                settings,
                {"mode": "sortera", "card_id": "cat_red"},
            )
            assert "503" in status
            assert "error" in data
        finally:
            nfc._pn532 = old_pn

    def test_start_requires_mode(self, settings, reader_available):
        status, data = _run("POST", "/api/nfc/provision/start", settings, {})
        assert "400" in status
        assert "error" in data

    def test_start_rejects_unknown_mode(self, settings, reader_available):
        status, data = _run(
            "POST",
            "/api/nfc/provision/start",
            settings,
            {"mode": "not-a-real-mode"},
        )
        assert "404" in status

    def test_start_rejects_unknown_card_id(self, settings, reader_available):
        status, data = _run(
            "POST",
            "/api/nfc/provision/start",
            settings,
            {"mode": "sortera", "card_id": "definitely-not-a-card"},
        )
        assert "404" in status

    def test_start_writes_and_transitions_to_ok(self, settings, reader_available):
        status, data = _run(
            "POST",
            "/api/nfc/provision/start",
            settings,
            {"mode": "sortera", "card_id": "cat_red"},
        )
        assert "200" in status
        assert data["ok"] is True
        # The host-test fallback in _handle_provision_start runs the write
        # synchronously when no running event loop is available, so by
        # the time we poll /status the state has already transitioned.
        _, snap = _run("GET", "/api/nfc/provision/status", settings)
        assert snap["state"] == "ok"
        assert snap["owner"] == "web"
        assert reader_available.writes  # at least one page written

    def test_start_surfaces_write_failure(self, settings, reader_available):
        reader_available.write_ok = False
        _run(
            "POST",
            "/api/nfc/provision/start",
            settings,
            {"mode": "sortera", "card_id": "cat_red"},
        )
        _, snap = _run("GET", "/api/nfc/provision/status", settings)
        assert snap["state"] == "fail"
        assert snap["error"]

    def test_start_is_refused_when_device_holds_reader(
        self, settings, reader_available
    ):
        nfc.provision_acquire("device")
        try:
            status, data = _run(
                "POST",
                "/api/nfc/provision/start",
                settings,
                {"mode": "sortera", "card_id": "cat_red"},
            )
            assert "409" in status
            assert data["owner"] == "device"
        finally:
            nfc.provision_release("device")

    def test_status_shows_device_owner_when_device_holds(
        self, settings, reader_available
    ):
        nfc.provision_acquire("device")
        try:
            _, snap = _run("GET", "/api/nfc/provision/status", settings)
            assert snap["owner"] == "device"
        finally:
            nfc.provision_release("device")

    def test_cancel_releases_web_ownership(self, settings, reader_available):
        nfc.provision_acquire("web", "sortera", "cat_red")
        status, data = _run("POST", "/api/nfc/provision/cancel", settings)
        assert "200" in status
        assert data["ok"] is True
        assert nfc.provision_state()["owner"] is None

    def test_cancel_refuses_to_clear_device_ownership(self, settings, reader_available):
        nfc.provision_acquire("device")
        try:
            status, _ = _run("POST", "/api/nfc/provision/cancel", settings)
            assert "409" in status
            assert nfc.provision_state()["owner"] == "device"
        finally:
            nfc.provision_release("device")
