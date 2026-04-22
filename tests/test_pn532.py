"""Tests for bodn.pn532 — PN532 I2C driver frame building and response parsing."""

import pytest
from bodn.pn532 import PN532


# ---------------------------------------------------------------------------
# Fake I2C that records writes and queues read responses
# ---------------------------------------------------------------------------


class FakePN532I2C:
    """Stub I2C with writeto/readfrom_into for PN532 raw I2C protocol."""

    def __init__(self):
        self.writes = []  # list of (addr, bytes)
        self.reads = []  # queue of bytes to return on readfrom_into

    def writeto(self, addr, data):
        self.writes.append((addr, bytes(data)))

    def readfrom_into(self, addr, buf):
        if not self.reads:
            for i in range(len(buf)):
                buf[i] = 0
            return
        resp = self.reads.pop(0)
        for i in range(min(len(buf), len(resp))):
            buf[i] = resp[i]

    def queue_ready_and_response(self, frame_data):
        """Queue a ready byte (for _read_ready) + frame data (for _read_response)."""
        self.reads.append(bytes([0x01]))  # ready byte
        self.reads.append(frame_data)

    def queue_not_ready(self):
        """Queue a not-ready response."""
        self.reads.append(bytes([0x00]))


def _build_response_frame(cmd_code, payload):
    """Build a valid PN532 response frame for testing.

    Returns the raw frame bytes (no ready byte — that's queued separately).
    """
    data = bytes([0xD5, cmd_code]) + payload
    length = len(data)
    lcs = (~length + 1) & 0xFF
    dcs = 0
    for b in data:
        dcs += b
    dcs = (~dcs + 1) & 0xFF
    return bytes([0x00, 0xFF, length, lcs]) + data + bytes([dcs, 0x00])


# ---------------------------------------------------------------------------
# Frame building
# ---------------------------------------------------------------------------


class TestFrameBuilding:
    def test_write_frame_sent_to_i2c(self):
        i2c = FakePN532I2C()
        pn = PN532(i2c, addr=0x24)
        # Call the internal _write_frame with a simple command
        pn._write_frame(bytes([0xD4, 0x02]))  # GetFirmwareVersion
        assert len(i2c.writes) == 1
        addr, data = i2c.writes[0]
        assert addr == 0x24

    def test_frame_preamble_and_startcode(self):
        i2c = FakePN532I2C()
        pn = PN532(i2c, addr=0x24)
        pn._write_frame(bytes([0xD4, 0x02]))
        _, data = i2c.writes[0]
        assert data[0] == 0x00  # preamble
        assert data[1] == 0x00  # startcode 1
        assert data[2] == 0xFF  # startcode 2

    def test_frame_length_and_checksum(self):
        i2c = FakePN532I2C()
        pn = PN532(i2c, addr=0x24)
        pn._write_frame(bytes([0xD4, 0x02]))  # 2 bytes
        _, data = i2c.writes[0]
        length = data[3]
        lcs = data[4]
        assert length == 2
        assert (length + lcs) & 0xFF == 0

    def test_frame_data_checksum(self):
        i2c = FakePN532I2C()
        pn = PN532(i2c, addr=0x24)
        cmd_data = bytes([0xD4, 0x02])
        pn._write_frame(cmd_data)
        _, data = i2c.writes[0]
        # Data starts at index 5, length is data[3]
        length = data[3]
        dcs_sum = 0
        for i in range(length):
            dcs_sum += data[5 + i]
        dcs_sum += data[5 + length]  # DCS byte
        assert dcs_sum & 0xFF == 0

    def test_frame_postamble(self):
        i2c = FakePN532I2C()
        pn = PN532(i2c, addr=0x24)
        pn._write_frame(bytes([0xD4, 0x02]))
        _, data = i2c.writes[0]
        length = data[3]
        assert data[6 + length] == 0x00  # postamble


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


class TestResponseParsing:
    def test_parse_firmware_version(self):
        i2c = FakePN532I2C()
        pn = PN532(i2c, addr=0x24)
        # Response code 0x03, IC=0x07, Ver=1, Rev=6, Support=0x07
        resp = _build_response_frame(0x03, bytes([0x07, 0x01, 0x06, 0x07]))
        i2c.queue_ready_and_response(resp)
        payload = pn._read_response(timeout_ms=10)
        assert payload is not None
        assert payload[0] == 0x03  # command response code
        assert payload[1] == 0x07  # IC
        assert payload[2] == 0x01  # version
        assert payload[3] == 0x06  # revision

    def test_not_ready_returns_none(self):
        i2c = FakePN532I2C()
        pn = PN532(i2c, addr=0x24)
        # Queue only not-ready responses — should timeout
        for _ in range(20):
            i2c.queue_not_ready()
        payload = pn._read_response(timeout_ms=5)
        assert payload is None

    def test_invalid_checksum_rejected(self):
        i2c = FakePN532I2C()
        pn = PN532(i2c, addr=0x24)
        # Build a valid frame then corrupt the data checksum
        resp = bytearray(_build_response_frame(0x03, bytes([0x07, 0x01, 0x06])))
        resp[-2] ^= 0xFF  # corrupt DCS
        i2c.queue_ready_and_response(bytes(resp))
        payload = pn._read_response(timeout_ms=10)
        assert payload is None


# ---------------------------------------------------------------------------
# UID parsing
# ---------------------------------------------------------------------------


class TestUIDParsing:
    def _make_passive_target_response(self, uid):
        """Build InListPassiveTarget response with given UID bytes."""
        # resp[0]=cmd (0x4B), resp[1]=n_targets, resp[2]=tg,
        # resp[3:5]=SENS_RES, resp[5]=SEL_RES, resp[6]=uid_len, resp[7:]=uid
        payload = bytes([0x01, 0x01, 0x00, 0x04, 0x60, len(uid)]) + uid
        return _build_response_frame(0x4B, payload)

    def test_4byte_uid(self):
        i2c = FakePN532I2C()
        pn = PN532(i2c, addr=0x24)
        uid_bytes = bytes([0x04, 0xA3, 0xB2, 0xC1])
        resp = self._make_passive_target_response(uid_bytes)
        i2c.queue_ready_and_response(resp)
        result = pn._read_response(timeout_ms=10)
        assert result is not None
        n_targets = result[1]
        assert n_targets == 1
        uid_len = result[6]
        assert uid_len == 4
        parsed_uid = bytes(result[7 : 7 + uid_len])
        assert parsed_uid == uid_bytes

    def test_7byte_uid(self):
        i2c = FakePN532I2C()
        pn = PN532(i2c, addr=0x24)
        uid_bytes = bytes([0x04, 0xA3, 0xB2, 0xC1, 0xD4, 0xE5, 0xF6])
        resp = self._make_passive_target_response(uid_bytes)
        i2c.queue_ready_and_response(resp)
        result = pn._read_response(timeout_ms=10)
        assert result is not None
        uid_len = result[6]
        assert uid_len == 7
        parsed_uid = bytes(result[7 : 7 + uid_len])
        assert parsed_uid == uid_bytes

    def test_no_tag_returns_zero_targets(self):
        i2c = FakePN532I2C()
        pn = PN532(i2c, addr=0x24)
        resp = _build_response_frame(0x4B, bytes([0x00]))
        i2c.queue_ready_and_response(resp)
        result = pn._read_response(timeout_ms=10)
        assert result is not None
        assert result[1] == 0  # n_targets


# ---------------------------------------------------------------------------
# Two-phase scan
# ---------------------------------------------------------------------------


ACK_FRAME_7 = bytes([0x01, 0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00])


class TestTwoPhaseScan:
    def test_start_sends_command_and_consumes_ack(self):
        i2c = FakePN532I2C()
        pn = PN532(i2c, addr=0x24)
        # Queue the ACK the PN532 sends after accepting the command —
        # read_passive_target_start must consume it so the next
        # read_passive_target_check reads the response, not the ACK.
        i2c.reads.append(bytes([0x01]))  # _read_ready sees ready
        i2c.reads.append(ACK_FRAME_7)  # _read_ack consumes ACK
        ok = pn.read_passive_target_start()
        assert ok is True
        assert len(i2c.writes) == 1
        assert pn._scan_pending is True

    def test_start_fails_when_ack_missing(self):
        """No ACK queued → timeout returns False, scan not marked pending."""
        i2c = FakePN532I2C()
        pn = PN532(i2c, addr=0x24)
        ok = pn.read_passive_target_start()
        assert ok is False
        assert pn._scan_pending is False

    def test_check_not_ready(self):
        i2c = FakePN532I2C()
        pn = PN532(i2c, addr=0x24)
        pn._scan_pending = True
        # Not ready response (ready bit = 0)
        i2c.queue_not_ready()
        result = pn.read_passive_target_check()
        assert result is None
        assert pn._scan_pending is True  # still pending

    def test_check_without_start(self):
        i2c = FakePN532I2C()
        pn = PN532(i2c, addr=0x24)
        result = pn.read_passive_target_check()
        assert result is None


# ---------------------------------------------------------------------------
# NTAG read/write
# ---------------------------------------------------------------------------


class TestNTAGReadWrite:
    def test_ntag_write_rejects_wrong_length(self):
        i2c = FakePN532I2C()
        pn = PN532(i2c, addr=0x24)
        assert pn.ntag_write(4, b"\x00\x00\x00") is False  # 3 bytes, need 4
        assert pn.ntag_write(4, b"\x00\x00\x00\x00\x00") is False  # 5 bytes


# ---------------------------------------------------------------------------
# Power management
# ---------------------------------------------------------------------------


class TestPowerManagement:
    def test_wake_up_sends_i2c_write(self):
        i2c = FakePN532I2C()
        pn = PN532(i2c, addr=0x24)
        pn.wake_up()
        assert len(i2c.writes) == 1
        addr, data = i2c.writes[0]
        assert addr == 0x24
