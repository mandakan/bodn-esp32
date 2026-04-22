# bodn/pn532.py — Minimal PN532 NFC reader driver (I2C)
#
# Self-contained driver for PN532 over I2C.  Supports tag UID reading,
# NTAG page read/write, and power management.  Two-phase scan design
# keeps each call under ~5 ms to fit the 33 ms frame budget.
#
# I2C protocol: raw writeto/readfrom (NOT register-addressed).
# The PN532 uses a framed packet protocol over I2C:
#   Host→PN532:  00 00 FF LEN LCS D4 CMD [params...] DCS 00
#   PN532→Host:  ready byte (bit 0 = 1 when response available)
#                00 00 FF LEN LCS D5 CMD+1 [data...] DCS 00

from micropython import const

# PN532 commands
_CMD_GET_FIRMWARE_VERSION = const(0x02)
_CMD_SAM_CONFIGURATION = const(0x14)
_CMD_IN_LIST_PASSIVE_TARGET = const(0x4A)
_CMD_IN_DATA_EXCHANGE = const(0x40)
_CMD_POWER_DOWN = const(0x16)

# NTAG commands (sent via InDataExchange)
_NTAG_READ = const(0x30)
_NTAG_WRITE = const(0xA2)

# I2C ready bit
_I2C_READY = const(0x01)

# Frame constants
_PREAMBLE = const(0x00)
_STARTCODE1 = const(0x00)
_STARTCODE2 = const(0xFF)
_POSTAMBLE = const(0x00)
_HOST_TO_PN532 = const(0xD4)
_PN532_TO_HOST = const(0xD5)

# Pre-allocated buffers
_ACK = b"\x00\x00\xff\x00\xff\x00"


class PN532:
    """Minimal PN532 I2C driver for NTAG213/215 tags."""

    def __init__(self, i2c, addr=0x24):
        self._i2c = i2c
        self._addr = addr
        # Pre-allocate buffers to avoid per-frame allocations
        self._buf1 = bytearray(1)  # ready-byte read
        self._cmd_buf = bytearray(64)  # outgoing frame
        self._resp_buf = bytearray(64)  # incoming frame
        # Two-phase scan state
        self._scan_pending = False

    # ------------------------------------------------------------------
    # Low-level I2C framing
    # ------------------------------------------------------------------

    def _write_frame(self, data):
        """Build and send a PN532 command frame.

        Frame: 00 00 FF LEN LCS [data] DCS 00
        data should start with TFI (0xD4) followed by command + params.
        """
        length = len(data)
        lcs = (~length + 1) & 0xFF  # length checksum
        dcs = 0
        for b in data:
            dcs += b
        dcs = (~dcs + 1) & 0xFF  # data checksum

        buf = self._cmd_buf
        buf[0] = _PREAMBLE
        buf[1] = _STARTCODE1
        buf[2] = _STARTCODE2
        buf[3] = length
        buf[4] = lcs
        for i, b in enumerate(data):
            buf[5 + i] = b
        buf[5 + length] = dcs
        buf[6 + length] = _POSTAMBLE
        frame_len = 7 + length
        self._i2c.writeto(self._addr, memoryview(buf)[:frame_len])

    def _read_ready(self):
        """Check if the PN532 has a response ready (non-blocking)."""
        self._i2c.readfrom_into(self._addr, self._buf1)
        return bool(self._buf1[0] & _I2C_READY)

    def _read_response(self, timeout_ms=100):
        """Wait for and read a response frame. Returns payload or None.

        Payload starts after TFI byte (0xD5), so first byte is command+1.
        """
        import time

        deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
        while True:
            if self._read_ready():
                break
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                return None
            time.sleep_ms(1)

        return self._read_response_now()

    def _read_response_now(self):
        """Read a response frame assuming the ready bit was already seen.

        Does a single I2C read and parses the frame — no sleeping, no
        retry.  Used on the cooperative scan path where the caller has
        already polled the ready bit itself.  Returns payload bytes or
        None on malformed frame.
        """
        # Read response: leading ready byte + frame
        # Max expected: 1 (ready) + 6 (header) + 64 (data) + 2 (checksum+postamble)
        n = 64
        buf = self._resp_buf
        self._i2c.readfrom_into(self._addr, memoryview(buf)[:n])

        # Find start code (skip ready byte and any leading zeros)
        idx = 0
        while idx < n - 1 and not (buf[idx] == 0x00 and buf[idx + 1] == 0xFF):
            idx += 1
        if idx >= n - 2:
            return None
        idx += 2  # skip 00 FF

        length = buf[idx]
        lcs = buf[idx + 1]
        if (length + lcs) & 0xFF != 0:
            return None  # length checksum failed
        idx += 2

        if length == 0:
            return None

        # Verify TFI
        if buf[idx] != _PN532_TO_HOST:
            return None

        # Extract payload (after TFI)
        payload = bytes(buf[idx + 1 : idx + length])

        # Verify data checksum
        dcs = 0
        for i in range(length):
            dcs += buf[idx + i]
        dcs = (dcs + buf[idx + length]) & 0xFF
        if dcs != 0:
            return None  # data checksum failed

        return payload

    def _read_ack(self, timeout_ms=100):
        """Read and verify the ACK frame the PN532 sends after receiving a command."""
        import time

        deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
        while True:
            if self._read_ready():
                break
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                return False
            time.sleep_ms(1)

        # Read ACK: ready byte + 6-byte ACK frame (00 00 FF 00 FF 00)
        ack_buf = bytearray(7)
        self._i2c.readfrom_into(self._addr, ack_buf)
        # Verify ACK pattern (skip ready byte at position 0)
        return (
            ack_buf[1] == 0x00
            and ack_buf[2] == 0x00
            and ack_buf[3] == 0xFF
            and ack_buf[4] == 0x00
            and ack_buf[5] == 0xFF
            and ack_buf[6] == 0x00
        )

    def _send_command(self, cmd, params=b"", timeout_ms=100):
        """Send a command, read ACK, then wait for the response."""
        data = bytearray(2 + len(params))
        data[0] = _HOST_TO_PN532
        data[1] = cmd
        data[2:] = params
        self._write_frame(data)
        # Read and verify ACK frame
        if not self._read_ack(timeout_ms):
            return None
        # Now read the actual response
        return self._read_response(timeout_ms)

    # ------------------------------------------------------------------
    # High-level commands
    # ------------------------------------------------------------------

    def begin(self, retries=5):
        """Initialise the PN532. Returns True if hardware responds.

        Sends a wake-up first in case the chip is still in power-down
        from a previous session (e.g. after soft reboot).  Retries the
        full wake→version→SAM sequence up to *retries* times because the
        chip may need multiple wake attempts after power-down or sleep.
        """
        import time

        for attempt in range(retries):
            self.wake_up()
            fw = self.get_firmware_version()
            if fw is not None:
                if self.sam_config():
                    return True
            time.sleep_ms(50 * (attempt + 1))
        return False

    def get_firmware_version(self):
        """Read firmware version. Returns (IC, ver, rev, support) or None."""
        resp = self._send_command(_CMD_GET_FIRMWARE_VERSION, timeout_ms=200)
        if resp is None or len(resp) < 4:
            return None
        # resp[0] = command response code (0x03)
        return (resp[1], resp[2], resp[3], resp[4] if len(resp) > 4 else 0)

    def sam_config(self):
        """Configure SAM for normal mode (no SAM, timeout disabled)."""
        resp = self._send_command(
            _CMD_SAM_CONFIGURATION, b"\x01\x00\x01", timeout_ms=200
        )
        return resp is not None

    def read_passive_target(self, timeout_ms=100):
        """Detect an ISO14443A tag and return its UID bytes, or None.

        Sends InListPassiveTarget for 1 target at 106 kbps.
        """
        resp = self._send_command(
            _CMD_IN_LIST_PASSIVE_TARGET, b"\x01\x00", timeout_ms=timeout_ms
        )
        if resp is None or len(resp) < 3:
            return None
        # resp[0] = command code (0x4B), resp[1] = number of targets
        n_targets = resp[1]
        if n_targets == 0:
            return None
        # resp[2] = target number (0x01)
        # resp[3..4] = SENS_RES, resp[5] = SEL_RES
        # resp[6] = UID length, resp[7:7+uid_len] = UID
        if len(resp) < 7:
            return None
        uid_len = resp[6]
        if len(resp) < 7 + uid_len:
            return None
        return bytes(resp[7 : 7 + uid_len])

    def read_passive_target_start(self):
        """Phase 1 of two-phase scan: send the InListPassiveTarget command.

        Call read_passive_target_check() on subsequent frames to get the result.

        Returns True if the PN532 accepted the command (ACK received).  The
        ACK must be consumed here: if we leave it in the chip's buffer, the
        subsequent _read_response_now() in read_passive_target_check() reads
        the ACK frame as if it were the response, fails checksum, and
        reports "no tag" on every cycle.  ACK arrives within ~1–2 ms so a
        short blocking read here does not break cooperativeness.
        """
        data = bytearray(4)
        data[0] = _HOST_TO_PN532
        data[1] = _CMD_IN_LIST_PASSIVE_TARGET
        data[2] = 0x01  # max 1 target
        data[3] = 0x00  # 106 kbps type A
        self._write_frame(data)
        self._scan_pending = self._read_ack(timeout_ms=20)
        return self._scan_pending

    def read_passive_target_check(self):
        """Phase 2 of two-phase scan: check for response.

        Tri-state return:
          * ``None``  — chip not ready yet, call again after a short yield.
          * ``False`` — command completed but no tag was detected (or I/O
            error / malformed frame).  Scan is done; start a new one.
          * ``bytes`` — UID bytes of a detected tag.

        Callers MUST distinguish ``None`` (retry) from ``False`` (give up
        this round) — collapsing them into a single "no tag" makes the
        scanner thrash when the chip is slow.
        """
        if not self._scan_pending:
            return None
        try:
            if not self._read_ready():
                return None  # not ready yet — try next frame
        except OSError:
            self._scan_pending = False
            return False

        self._scan_pending = False
        resp = self._read_response_now()
        if resp is None or len(resp) < 3:
            return False
        n_targets = resp[1]
        if n_targets == 0:
            return False
        if len(resp) < 7:
            return False
        uid_len = resp[6]
        if len(resp) < 7 + uid_len:
            return False
        return bytes(resp[7 : 7 + uid_len])

    def ntag_read(self, page):
        """Read 4 pages (16 bytes) starting at *page*. Returns bytes or None."""
        resp = self._send_command(
            _CMD_IN_DATA_EXCHANGE,
            bytes([0x01, _NTAG_READ, page]),
            timeout_ms=200,
        )
        if resp is None or len(resp) < 2:
            return None
        # resp[0] = command code (0x41), resp[1] = status (0 = OK)
        if resp[1] != 0:
            return None
        return bytes(resp[2:18]) if len(resp) >= 18 else None

    def ntag_write(self, page, data_4bytes):
        """Write 4 bytes to a single NTAG page. Returns True on success."""
        if len(data_4bytes) != 4:
            return False
        params = bytearray(7)
        params[0] = 0x01  # target number
        params[1] = _NTAG_WRITE
        params[2] = page
        params[3:7] = data_4bytes
        resp = self._send_command(_CMD_IN_DATA_EXCHANGE, params, timeout_ms=200)
        if resp is None or len(resp) < 2:
            return False
        return resp[1] == 0

    def power_down(self):
        """Put PN532 into power-down mode (~10 uA)."""
        # Wake-up sources: I2C (bit 5)
        self._send_command(_CMD_POWER_DOWN, b"\x20", timeout_ms=200)

    def wake_up(self):
        """Wake PN532 from power-down or stuck command state.

        After a soft reboot the chip may be waiting for the host to
        read a pending response (e.g. from an interrupted InListPassive
        Target).  Sending a write in that state gets NACKed because the
        chip expects a read.  So we first try to drain any buffered
        response, then send the wake byte.
        """
        import time

        # Flush any pending response from a previous interrupted command.
        # The PN532 NACKs writes while holding unread data — drain it.
        for _ in range(3):
            try:
                self._i2c.readfrom_into(self._addr, self._resp_buf)
            except OSError:
                break
            time.sleep_ms(2)

        # Now send the wake byte (may still NACK on first attempt)
        for i in range(5):
            try:
                self._i2c.writeto(self._addr, b"\x00")
                time.sleep_ms(5)
                return
            except OSError:
                time.sleep_ms(10 * (i + 1))
