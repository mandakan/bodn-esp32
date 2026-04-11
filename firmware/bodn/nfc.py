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
# NFC reader stub (hardware implementation in #121)
# ---------------------------------------------------------------------------


class NFCReader:
    """Stub NFC reader — real PN532 driver replaces this in issue #121.

    Provides the interface that game modes and provisioning code will use.
    """

    def __init__(self):
        self._available = False

    def available(self):
        """Return True if NFC hardware is detected on the I2C bus."""
        return self._available

    def scan(self):
        """Scan for a tag in the field.

        Returns (uid_str, raw_data_bytes) if a tag is present,
        or (None, None) if no tag is detected.

        uid_str format: colon-separated hex, e.g. "04:A3:B2:C1:D4:E5:F6"
        raw_data_bytes: NDEF Text Record payload (status + lang + text)
        """
        return None, None

    def write(self, data):
        """Write data bytes to the tag currently in the field.

        Returns True on success, False on failure or no tag present.
        """
        return False
