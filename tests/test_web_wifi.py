"""Regression tests for the WiFi section of the parental-controls web UI.

Issue #169: the SSID/password fields rendered empty even when the device was
connected to a network, and the stored password was echoed back to the
browser. The fix introduces a /api/wifi/status endpoint that surfaces the
live SSID, strips the password from /api/settings, and lets POST /api/wifi
keep the existing password when the form leaves the field blank.
"""

import asyncio
import json
import sys
import types

import pytest

# bodn.web pulls in bodn.web_ui which imports several display-related
# modules; the conftest stubs cover those, but bodn.web also imports
# `hashlib` lazily for OTA — present on CPython, fine.
from bodn import web, wifi


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


def _request(method, path, body=None, cookie=None):
    headers = ["Host: test", "Connection: close"]
    if cookie:
        headers.append("Cookie: " + cookie)
    body_bytes = b""
    if body is not None:
        body_bytes = json.dumps(body).encode()
        headers.append("Content-Type: application/json")
        headers.append("Content-Length: {}".format(len(body_bytes)))
    request_line = "{} {} HTTP/1.1\r\n".format(method, path).encode()
    rest = ("\r\n".join(headers) + "\r\n\r\n").encode() + body_bytes
    return request_line, _FakeReader(rest)


def _run(method, path, settings, body=None, cookie=None):
    request_line, reader = _request(method, path, body=body, cookie=cookie)
    writer = _FakeWriter()
    asyncio.run(
        web._handle_request(reader, writer, request_line, _FakeSession(), settings)
    )
    raw = bytes(writer.buf)
    head, _, payload = raw.partition(b"\r\n\r\n")
    status_line = head.split(b"\r\n", 1)[0].decode()
    return status_line, payload


def _json_response(payload):
    return json.loads(payload.decode())


@pytest.fixture
def settings():
    # Minimal subset of DEFAULT_SETTINGS — we only exercise WiFi/auth paths.
    return {
        "wifi_mode": "sta",
        "wifi_ssid": "HomeNet",
        "wifi_pass": "supersecret",
        "hostname": "bodn",
        "ui_pin": "",
        "ota_token": "",
    }


# --- /api/settings ----------------------------------------------------------


def test_settings_endpoint_strips_wifi_password(settings):
    status, payload = _run("GET", "/api/settings", settings)
    assert "200" in status
    data = _json_response(payload)
    assert "wifi_pass" not in data, "stored password must not leak to clients"
    assert data["wifi_pass_set"] is True
    assert data["wifi_ssid"] == "HomeNet"


def test_settings_wifi_pass_set_false_when_no_password(settings):
    settings["wifi_pass"] = ""
    _, payload = _run("GET", "/api/settings", settings)
    data = _json_response(payload)
    assert data["wifi_pass_set"] is False


# --- /api/wifi/status -------------------------------------------------------


def test_wifi_status_reports_stored_and_live_ssid(monkeypatch, settings):
    monkeypatch.setattr(wifi, "live_ssid", lambda: "Wokwi-GUEST")
    monkeypatch.setattr(wifi, "is_sta_connected", lambda: True)
    monkeypatch.setattr(wifi, "get_ip", lambda: "10.13.37.2")

    _, payload = _run("GET", "/api/wifi/status", settings)
    data = _json_response(payload)
    assert data == {
        "wifi_mode": "sta",
        "stored_ssid": "HomeNet",
        "live_ssid": "Wokwi-GUEST",
        "connected": True,
        "ip": "10.13.37.2",
        "hostname": "bodn",
        "wifi_pass_set": True,
    }


def test_wifi_status_when_disconnected(monkeypatch, settings):
    settings["wifi_mode"] = "ap"
    settings["wifi_ssid"] = ""
    settings["wifi_pass"] = ""
    monkeypatch.setattr(wifi, "live_ssid", lambda: "")
    monkeypatch.setattr(wifi, "is_sta_connected", lambda: False)
    monkeypatch.setattr(wifi, "get_ip", lambda: "192.168.4.1")

    _, payload = _run("GET", "/api/wifi/status", settings)
    data = _json_response(payload)
    assert data["connected"] is False
    assert data["live_ssid"] == ""
    assert data["wifi_pass_set"] is False
    assert data["wifi_mode"] == "ap"


# --- POST /api/wifi ---------------------------------------------------------


def _post_wifi_no_reset(monkeypatch, settings, body):
    """POST /api/wifi without actually rebooting the host."""
    saved = {"called": False}

    def fake_save(s):
        saved["called"] = True

    monkeypatch.setattr(web.storage, "save_settings", fake_save)

    fake_machine = types.ModuleType("machine")
    fake_machine.reset = lambda: (_ for _ in ()).throw(SystemExit)
    monkeypatch.setitem(sys.modules, "machine", fake_machine)

    # asyncio.sleep_ms is patched in conftest; the reset SystemExit terminates
    # the coroutine after the response is queued.
    request_line, reader = _request("POST", "/api/wifi", body=body)
    writer = _FakeWriter()
    try:
        asyncio.run(
            web._handle_request(reader, writer, request_line, _FakeSession(), settings)
        )
    except SystemExit:
        pass
    return saved["called"], writer


def test_post_wifi_keeps_password_when_blank(monkeypatch, settings):
    saved, _ = _post_wifi_no_reset(
        monkeypatch,
        settings,
        {
            "wifi_mode": "sta",
            "wifi_ssid": "NewNet",
            "wifi_pass": "",
            "hostname": "bodn",
        },
    )
    assert saved is True
    assert settings["wifi_ssid"] == "NewNet"
    # Critical: blank password must not wipe the stored credential.
    assert settings["wifi_pass"] == "supersecret"


def test_post_wifi_replaces_password_when_provided(monkeypatch, settings):
    _post_wifi_no_reset(
        monkeypatch,
        settings,
        {
            "wifi_mode": "sta",
            "wifi_ssid": "NewNet",
            "wifi_pass": "freshpass",
            "hostname": "bodn",
        },
    )
    assert settings["wifi_pass"] == "freshpass"


def test_post_wifi_omitted_password_keeps_existing(monkeypatch, settings):
    """Field absent from the JSON body is treated the same as blank."""
    _post_wifi_no_reset(
        monkeypatch,
        settings,
        {"wifi_mode": "sta", "wifi_ssid": "NewNet", "hostname": "bodn"},
    )
    assert settings["wifi_pass"] == "supersecret"


# --- wifi.live_ssid / is_sta_connected --------------------------------------


def test_live_ssid_returns_empty_when_inactive():
    sta = sys.modules["network"].WLAN(0)
    sta._active = False
    sta._connected = False
    assert wifi.live_ssid() == ""
    assert wifi.is_sta_connected() is False


def test_live_ssid_reads_essid_when_connected(monkeypatch):
    sta = sys.modules["network"].WLAN(0)
    sta._active = True
    sta._connected = True

    def fake_config(*args, **kwargs):
        if args and args[0] == "essid":
            return "MyHomeWiFi"
        raise ValueError("unsupported")

    monkeypatch.setattr(sta, "config", fake_config, raising=False)
    # The module-level WLAN factory always returns a fresh instance, so
    # patch the factory to return our prepared one.
    monkeypatch.setattr(
        sys.modules["network"], "WLAN", lambda iface=0: sta, raising=False
    )

    assert wifi.is_sta_connected() is True
    assert wifi.live_ssid() == "MyHomeWiFi"
