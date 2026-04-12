# bodn/nfc.py — NFC tag data handling, card set loading, and UID cache
#
# Tag data format (NDEF Text Record payload):
#   BODN:1:sortera:cat_red
#   ^^^^  ^ ^^^^^^^ ^^^^^^^
#   prefix version mode   card_id
#
# Card set templates live on SD at /sd/nfc/{mode}.json
# UID cache lives on flash at /data/nfc_cache.json

import os

try:
    import json
except ImportError:
    import ujson as json

TAG_PREFIX = "BODN"
TAG_VERSION = 1
NFC_CACHE_PATH = "/data/nfc_cache.json"
NFC_DIR = "/nfc"


# ---------------------------------------------------------------------------
# Tag data parsing and encoding
# ---------------------------------------------------------------------------


def parse_tag_data(data):
    """Parse a BODN tag identifier from raw NDEF bytes or a plain string.

    Accepts either:
      - bytes/bytearray (NDEF Text Record: status byte + lang code + text)
      - str (plain text: "BODN:1:sortera:cat_red")

    Returns dict with keys (prefix, version, mode, id) or None on failure.
    """
    if isinstance(data, (bytes, bytearray)):
        text = _decode_ndef_text(data)
        if text is None:
            return None
    else:
        text = str(data)

    parts = text.split(":")
    if len(parts) < 4:
        return None
    if parts[0] != TAG_PREFIX:
        return None

    try:
        version = int(parts[1])
    except (ValueError, IndexError):
        return None

    return {
        "prefix": parts[0],
        "version": version,
        "mode": parts[2],
        "id": parts[3],
    }


def encode_tag_data(mode, card_id, version=None):
    """Create NDEF Text Record payload bytes for writing to a tag.

    Returns bytes: status_byte + b'en' + payload text.
    The status byte encodes UTF-8 flag (bit 7 = 0) and language code
    length (bits 5-0 = 2 for 'en').
    """
    if version is None:
        version = TAG_VERSION
    text = "{}:{}:{}:{}".format(TAG_PREFIX, version, mode, card_id)
    lang = b"en"
    status = len(lang)  # UTF-8 (bit 7 = 0), lang length = 2
    return bytes([status]) + lang + text.encode("utf-8")


def _decode_ndef_text(data):
    """Decode an NDEF Text Record payload to a string.

    Format: 1 byte status (bit 7 = encoding, bits 5-0 = lang code length)
            N bytes language code
            remaining bytes = text
    """
    if len(data) < 2:
        return None
    status = data[0]
    lang_len = status & 0x3F
    if len(data) < 1 + lang_len + 1:
        return None
    text_bytes = data[1 + lang_len :]
    try:
        return text_bytes.decode("utf-8")
    except (UnicodeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Card set loading
# ---------------------------------------------------------------------------


def load_card_set(mode):
    """Load a card set template from /nfc/{mode}.json.

    Checks SD card first via assets.resolve(), falls back to flash.
    Returns the parsed dict or None on error.
    """
    path = "{}/{}.json".format(NFC_DIR, mode)
    try:
        from bodn.assets import resolve

        resolved = resolve(path)
    except ImportError:
        resolved = path

    try:
        with open(resolved, "r") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def lookup_card(mode, card_id):
    """Find a specific card within a card set by ID.

    Returns the card dict or None.
    """
    cs = load_card_set(mode)
    if cs is None:
        return None
    for card in cs.get("cards", []):
        if card.get("id") == card_id:
            return card
    return None


def list_card_sets():
    """List available card set modes by scanning the NFC directory.

    Returns a list of mode name strings (filenames without .json).
    """
    # Try SD first, then flash
    for base in ("/sd" + NFC_DIR, NFC_DIR):
        try:
            entries = os.listdir(base)
            return [name[:-5] for name in sorted(entries) if name.endswith(".json")]
        except OSError:
            continue
    return []


# ---------------------------------------------------------------------------
# UID cache
# ---------------------------------------------------------------------------


class UIDCache:
    """On-device UID-to-card mapping cache.

    Persisted at /data/nfc_cache.json. This is a performance optimisation
    only — the tag data on the NFC tag is the source of truth. If the
    cache is lost or corrupted, it rebuilds automatically from tag reads.
    """

    def __init__(self, path=None):
        self._path = path or NFC_CACHE_PATH
        self._cache = {}
        self._load()

    def _load(self):
        try:
            with open(self._path, "r") as f:
                self._cache = json.load(f)
        except (OSError, ValueError):
            self._cache = {}

    def _save(self):
        _ensure_dir(self._path)
        tmp = self._path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._cache, f)
        try:
            os.remove(self._path)
        except OSError:
            pass
        os.rename(tmp, self._path)

    def lookup(self, uid):
        """Look up a UID string. Returns dict {mode, id} or None."""
        return self._cache.get(uid)

    def store(self, uid, mode, card_id):
        """Store a UID mapping and persist to flash."""
        self._cache[uid] = {"mode": mode, "id": card_id}
        self._save()

    def clear(self):
        """Clear all cached mappings."""
        self._cache = {}
        self._save()

    def entries(self):
        """Return the full cache dict (for diagnostics/web UI)."""
        return dict(self._cache)


def _ensure_dir(path):
    """Create parent directory if it doesn't exist."""
    parts = path.rsplit("/", 1)
    if len(parts) == 2 and parts[0]:
        try:
            os.mkdir(parts[0])
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Module-level NFC hardware state
# ---------------------------------------------------------------------------

_i2c = None
_pn532 = None
_shed = False


def init(i2c):
    """Initialise NFC subsystem with I2C bus. Called once from create_hardware().

    If the I2C object lacks raw writeto/readfrom (e.g. NativeI2C shim),
    a separate machine.I2C(1) is created on the same pins.
    """
    global _i2c
    _i2c = i2c


def set_thermal_shed(active):
    """Enable/disable thermal shedding. Called by housekeeping_task."""
    global _shed
    _shed = active


# ---------------------------------------------------------------------------
# NFC reader (PN532 hardware driver)
# ---------------------------------------------------------------------------


class NFCReader:
    """NFC reader backed by PN532 over I2C.

    Provides the interface that game modes and provisioning code use.
    Construction is zero-args — the I2C bus is set by the module-level
    init() call at boot.
    """

    def __init__(self):
        self._pn532 = _pn532
        self._available = _pn532 is not None
        self._init_attempted = _pn532 is not None

    def available(self):
        """Return True if NFC hardware is detected on the I2C bus."""
        if not self._init_attempted:
            self._init_attempted = True
            self._try_init()
        return self._available

    def _try_init(self):
        global _pn532
        if _i2c is None:
            return
        try:
            from bodn.pn532 import PN532

            pn = PN532(_i2c)
            if pn.begin():
                self._pn532 = pn
                _pn532 = pn
                self._available = True
        except Exception as e:
            print("NFC: PN532 init failed:", e)

    def scan(self):
        """Scan for a tag in the field.

        Returns (uid_str, raw_data_bytes) if a tag is present,
        or (None, None) if no tag is detected.

        uid_str format: colon-separated hex, e.g. "04:A3:B2:C1:D4:E5:F6"
        raw_data_bytes: NDEF Text Record payload (status + lang + text)
        """
        if not self._available or _shed:
            return None, None
        uid = self._pn532.read_passive_target(timeout_ms=50)
        if uid is None:
            return None, None
        uid_str = ":".join("{:02X}".format(b) for b in uid)
        data = self._read_ndef()
        return uid_str, data

    def _read_ndef(self):
        """Read NDEF Text Record from NTAG user pages (pages 4+).

        NTAG memory layout:
          Page 3: Capability Container
          Page 4+: NDEF message (TLV format)

        TLV: type=0x03 (NDEF message), length, value..., terminator=0xFE
        NDEF record payload is the Text Record bytes.
        """
        # Read pages 4-7 (16 bytes) — covers most short BODN payloads
        raw = self._pn532.ntag_read(4)
        if raw is None:
            return None

        # Parse TLV to find NDEF message
        i = 0
        while i < len(raw):
            tlv_type = raw[i]
            if tlv_type == 0x00:  # NULL TLV
                i += 1
                continue
            if tlv_type == 0xFE:  # Terminator
                break
            if i + 1 >= len(raw):
                break
            tlv_len = raw[i + 1]
            i += 2
            if tlv_type == 0x03:  # NDEF Message
                ndef_data = raw[i : i + tlv_len]
                if tlv_len > len(raw) - i:
                    # Need more pages
                    raw2 = self._pn532.ntag_read(8)
                    if raw2:
                        ndef_data = (raw + raw2)[i : i + tlv_len]
                return self._extract_text_record(ndef_data)
            i += tlv_len
        return None

    def _extract_text_record(self, ndef_msg):
        """Extract Text Record payload from an NDEF message.

        NDEF record header: flags, type_len, payload_len, type, payload
        We only support short records (SR=1) with TNF=0x01 (well-known) type "T".
        """
        if len(ndef_msg) < 3:
            return None
        flags = ndef_msg[0]
        tnf = flags & 0x07
        sr = (flags >> 4) & 1
        if tnf != 0x01:  # well-known type
            return None
        type_len = ndef_msg[1]
        if sr:
            payload_len = ndef_msg[2]
            offset = 3
        else:
            if len(ndef_msg) < 6:
                return None
            payload_len = (
                (ndef_msg[2] << 24)
                | (ndef_msg[3] << 16)
                | (ndef_msg[4] << 8)
                | ndef_msg[5]
            )
            offset = 6
        type_data = ndef_msg[offset : offset + type_len]
        offset += type_len
        if type_data != b"T":
            return None
        payload = ndef_msg[offset : offset + payload_len]
        return bytes(payload) if payload else None

    def write(self, data):
        """Write NDEF Text Record to the tag currently in the field.

        *data* should be NDEF Text Record payload bytes (from encode_tag_data).
        Returns True on success, False on failure or no tag present.
        The tag must be an NTAG213/215 (Mifare Ultralight compatible).
        """
        if not self._available or _shed:
            return False

        # Select the tag first — InListPassiveTarget must succeed before writes
        uid = self._pn532.read_passive_target(timeout_ms=200)
        if uid is None:
            return False

        # Build NDEF message: record header + payload
        # Flags: MB=1, ME=1, CF=0, SR=1, IL=0, TNF=0x01 → 0xD1
        type_field = b"T"
        rec_header = bytes([0xD1, len(type_field), len(data)]) + type_field
        ndef_msg = rec_header + data

        # Wrap in TLV: type=0x03, length, data, terminator=0xFE
        tlv = bytes([0x03, len(ndef_msg)]) + ndef_msg + b"\xfe"

        # Pad to 4-byte page boundary
        while len(tlv) % 4:
            tlv += b"\x00"

        # Write pages starting at page 4
        page = 4
        for i in range(0, len(tlv), 4):
            chunk = tlv[i : i + 4]
            if not self._pn532.ntag_write(page, chunk):
                return False
            page += 1
        return True
