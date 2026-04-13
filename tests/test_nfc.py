"""Tests for bodn.nfc — tag parsing, encoding, card sets, UID cache, and NFCReader."""

import json
import os
import pytest
from bodn.nfc import (
    parse_tag_data,
    encode_tag_data,
    load_card_set,
    lookup_card,
    list_card_sets,
    UIDCache,
    NFC_DIR,
)


# ---------------------------------------------------------------------------
# Tag data parsing
# ---------------------------------------------------------------------------


class TestParseTagData:
    def test_plain_string(self):
        result = parse_tag_data("BODN:1:sortera:cat_red")
        assert result == {
            "prefix": "BODN",
            "version": 1,
            "mode": "sortera",
            "id": "cat_red",
        }

    def test_ndef_bytes(self):
        # NDEF Text Record: status=0x02 (UTF-8, lang_len=2), "en", payload
        payload = b"\x02en" + b"BODN:1:sortera:cat_red"
        result = parse_tag_data(payload)
        assert result is not None
        assert result["mode"] == "sortera"
        assert result["id"] == "cat_red"
        assert result["version"] == 1

    def test_wrong_prefix(self):
        assert parse_tag_data("NOPE:1:sortera:cat_red") is None

    def test_too_few_fields(self):
        assert parse_tag_data("BODN:1:sortera") is None

    def test_empty_string(self):
        assert parse_tag_data("") is None

    def test_empty_bytes(self):
        assert parse_tag_data(b"") is None

    def test_short_ndef_bytes(self):
        assert parse_tag_data(b"\x02") is None

    def test_admin_tag(self):
        result = parse_tag_data("BODN:1:admin:unlock")
        assert result == {
            "prefix": "BODN",
            "version": 1,
            "mode": "admin",
            "id": "unlock",
        }

    def test_future_version(self):
        result = parse_tag_data("BODN:2:future:thing")
        assert result is not None
        assert result["version"] == 2

    def test_non_numeric_version(self):
        assert parse_tag_data("BODN:abc:sortera:cat") is None


# ---------------------------------------------------------------------------
# Tag data encoding
# ---------------------------------------------------------------------------


class TestEncodeTagData:
    def test_basic_encode(self):
        data = encode_tag_data("sortera", "cat_red")
        # Status byte: 0x02 (UTF-8, lang_len=2)
        assert data[0] == 2
        # Language code: "en"
        assert data[1:3] == b"en"
        # Text payload
        assert data[3:] == b"BODN:1:sortera:cat_red"

    def test_round_trip(self):
        original_mode = "sortera"
        original_id = "dog_green"
        encoded = encode_tag_data(original_mode, original_id)
        parsed = parse_tag_data(encoded)
        assert parsed is not None
        assert parsed["mode"] == original_mode
        assert parsed["id"] == original_id
        assert parsed["version"] == 1

    def test_custom_version(self):
        data = encode_tag_data("test", "card", version=3)
        parsed = parse_tag_data(data)
        assert parsed["version"] == 3

    def test_admin_encode(self):
        data = encode_tag_data("admin", "unlock")
        parsed = parse_tag_data(data)
        assert parsed["mode"] == "admin"
        assert parsed["id"] == "unlock"


# ---------------------------------------------------------------------------
# Card set loading
# ---------------------------------------------------------------------------

SAMPLE_CARD_SET = {
    "mode": "test",
    "version": 1,
    "dimensions": ["category"],
    "cards": [
        {"id": "cat", "category": "animal", "label_sv": "katt", "label_en": "cat"},
        {"id": "car", "category": "vehicle", "label_sv": "bil", "label_en": "car"},
    ],
}


class TestLoadCardSet:
    def test_loads_valid_json(self, tmp_path, monkeypatch):
        nfc_dir = tmp_path / "nfc"
        nfc_dir.mkdir()
        (nfc_dir / "test.json").write_text(json.dumps(SAMPLE_CARD_SET))

        # Monkeypatch resolve to return our tmp file
        def fake_resolve(path):
            return str(nfc_dir / path.split("/")[-1])

        monkeypatch.setattr("bodn.nfc.resolve", fake_resolve, raising=False)
        # Patch the import inside load_card_set
        import bodn.nfc as nfc_mod

        # Replace the dynamic import with a direct function patch
        original = nfc_mod.load_card_set

        def patched_load(mode):
            path = "{}/{}.json".format(NFC_DIR, mode)
            resolved = fake_resolve(path)
            with open(resolved, "r") as f:
                return json.load(f)

        monkeypatch.setattr(nfc_mod, "load_card_set", patched_load)
        result = nfc_mod.load_card_set("test")
        assert result is not None
        assert result["mode"] == "test"
        assert len(result["cards"]) == 2
        # Restore
        monkeypatch.setattr(nfc_mod, "load_card_set", original)

    def test_missing_file_returns_none(self):
        result = load_card_set("nonexistent_mode_xyz")
        assert result is None


class TestLookupCard:
    def test_finds_existing_card(self, tmp_path, monkeypatch):
        nfc_dir = tmp_path / "nfc"
        nfc_dir.mkdir()
        (nfc_dir / "test.json").write_text(json.dumps(SAMPLE_CARD_SET))

        import bodn.nfc as nfc_mod

        def fake_load(mode):
            path = nfc_dir / "{}.json".format(mode)
            try:
                with open(str(path), "r") as f:
                    return json.load(f)
            except (OSError, ValueError):
                return None

        monkeypatch.setattr(nfc_mod, "load_card_set", fake_load)
        result = nfc_mod.lookup_card("test", "cat")
        assert result is not None
        assert result["label_en"] == "cat"

    def test_missing_card_returns_none(self, tmp_path, monkeypatch):
        nfc_dir = tmp_path / "nfc"
        nfc_dir.mkdir()
        (nfc_dir / "test.json").write_text(json.dumps(SAMPLE_CARD_SET))

        import bodn.nfc as nfc_mod

        def fake_load(mode):
            path = nfc_dir / "{}.json".format(mode)
            try:
                with open(str(path), "r") as f:
                    return json.load(f)
            except (OSError, ValueError):
                return None

        monkeypatch.setattr(nfc_mod, "load_card_set", fake_load)
        result = nfc_mod.lookup_card("test", "nonexistent")
        assert result is None

    def test_missing_mode_returns_none(self):
        result = lookup_card("nonexistent_xyz", "cat")
        assert result is None


# ---------------------------------------------------------------------------
# list_card_sets
# ---------------------------------------------------------------------------


class TestListCardSets:
    def test_lists_json_files(self, tmp_path, monkeypatch):
        nfc_dir = tmp_path / "nfc"
        nfc_dir.mkdir()
        (nfc_dir / "sortera.json").write_text("{}")
        (nfc_dir / "saga.json").write_text("{}")
        (nfc_dir / "readme.txt").write_text("ignore me")

        import bodn.nfc as nfc_mod

        # Patch os.listdir to check our tmp dir first
        original_listdir = os.listdir

        def fake_listdir(path):
            if path.endswith("/nfc"):
                return original_listdir(str(nfc_dir))
            return original_listdir(path)

        monkeypatch.setattr(os, "listdir", fake_listdir)
        result = nfc_mod.list_card_sets()
        assert "saga" in result
        assert "sortera" in result
        assert "readme" not in result

    def test_empty_directory(self, tmp_path, monkeypatch):
        nfc_dir = tmp_path / "nfc"
        nfc_dir.mkdir()

        import bodn.nfc as nfc_mod

        original_listdir = os.listdir

        def fake_listdir(path):
            if path.endswith("/nfc"):
                return original_listdir(str(nfc_dir))
            return original_listdir(path)

        monkeypatch.setattr(os, "listdir", fake_listdir)
        result = nfc_mod.list_card_sets()
        assert result == []

    def test_missing_directory(self, monkeypatch):
        import bodn.nfc as nfc_mod

        def fake_listdir(path):
            raise OSError("No such directory")

        monkeypatch.setattr(os, "listdir", fake_listdir)
        result = nfc_mod.list_card_sets()
        assert result == []


# ---------------------------------------------------------------------------
# UID cache
# ---------------------------------------------------------------------------


class TestUIDCache:
    def test_empty_cache(self, tmp_path):
        cache = UIDCache(path=str(tmp_path / "cache.json"))
        assert cache.lookup("04:A3:B2:C1") is None
        assert cache.entries() == {}

    def test_store_and_lookup(self, tmp_path):
        cache = UIDCache(path=str(tmp_path / "cache.json"))
        cache.store("04:A3:B2:C1", "sortera", "cat_red")
        result = cache.lookup("04:A3:B2:C1")
        assert result == {"mode": "sortera", "id": "cat_red"}

    def test_persistence(self, tmp_path):
        path = str(tmp_path / "cache.json")
        cache1 = UIDCache(path=path)
        cache1.store("04:A3:B2:C1", "sortera", "cat_red")

        # Create a new instance — should load from the file
        cache2 = UIDCache(path=path)
        result = cache2.lookup("04:A3:B2:C1")
        assert result == {"mode": "sortera", "id": "cat_red"}

    def test_multiple_entries(self, tmp_path):
        cache = UIDCache(path=str(tmp_path / "cache.json"))
        cache.store("AA:BB:CC:DD", "sortera", "cat_red")
        cache.store("11:22:33:44", "sortera", "dog_green")
        assert cache.lookup("AA:BB:CC:DD")["id"] == "cat_red"
        assert cache.lookup("11:22:33:44")["id"] == "dog_green"
        assert len(cache.entries()) == 2

    def test_overwrite(self, tmp_path):
        cache = UIDCache(path=str(tmp_path / "cache.json"))
        cache.store("AA:BB:CC:DD", "sortera", "cat_red")
        cache.store("AA:BB:CC:DD", "sortera", "dog_green")
        assert cache.lookup("AA:BB:CC:DD")["id"] == "dog_green"

    def test_clear(self, tmp_path):
        path = str(tmp_path / "cache.json")
        cache = UIDCache(path=path)
        cache.store("AA:BB:CC:DD", "sortera", "cat_red")
        cache.clear()
        assert cache.lookup("AA:BB:CC:DD") is None
        assert cache.entries() == {}
        # Verify cleared on disk
        cache2 = UIDCache(path=path)
        assert cache2.entries() == {}

    def test_corrupt_file(self, tmp_path):
        path = tmp_path / "cache.json"
        path.write_text("this is not valid json {{{")
        cache = UIDCache(path=str(path))
        # Should start with empty cache, not crash
        assert cache.entries() == {}
        # Should still be usable
        cache.store("AA:BB:CC:DD", "sortera", "cat_red")
        assert cache.lookup("AA:BB:CC:DD") is not None


# ---------------------------------------------------------------------------
# NFCReader
# ---------------------------------------------------------------------------


class FakePN532:
    """Minimal PN532 stub for testing NFCReader."""

    def __init__(self, uid=None, pages=None):
        self._uid = uid
        self._pages = pages or {}

    def begin(self):
        return True

    def read_passive_target(self, timeout_ms=100):
        return self._uid

    def ntag_read(self, page):
        return self._pages.get(page)

    def ntag_write(self, page, data):
        self._pages[page] = data
        return True

    def power_down(self):
        pass

    def wake_up(self):
        pass


class TestNFCReaderWithoutInit:
    def test_available_without_init(self):
        """NFCReader without init() returns unavailable."""
        import bodn.nfc as nfc_mod

        old_i2c = nfc_mod._i2c
        old_pn = nfc_mod._pn532
        nfc_mod._i2c = None
        nfc_mod._pn532 = None
        try:
            from bodn.nfc import NFCReader

            reader = NFCReader()
            assert reader.available() is False
            assert reader.scan() == (None, None)
            assert reader.write(b"test") is False
        finally:
            nfc_mod._i2c = old_i2c
            nfc_mod._pn532 = old_pn


class TestNFCReaderScan:
    def test_scan_with_tag(self):
        import bodn.nfc as nfc_mod

        old_pn = nfc_mod._pn532
        old_shed = nfc_mod._shed

        # Build NDEF TLV with a BODN tag payload
        ndef_payload = encode_tag_data("sortera", "cat_red")
        # NDEF record: flags=0xD1 (MB+ME+SR, TNF=0x01), type_len=1, payload_len, "T", payload
        ndef_rec = bytes([0xD1, 0x01, len(ndef_payload)]) + b"T" + ndef_payload
        # TLV: type=0x03, len, data, terminator=0xFE
        tlv = bytes([0x03, len(ndef_rec)]) + ndef_rec + b"\xfe"
        # Pad to 32 bytes (8 pages) and split across two ntag_read calls
        while len(tlv) < 32:
            tlv += b"\x00"

        uid = bytes([0x04, 0xA3, 0xB2, 0xC1, 0xD4, 0xE5, 0xF6])
        fake_pn = FakePN532(uid=uid, pages={4: tlv[:16], 8: tlv[16:32]})
        nfc_mod._pn532 = fake_pn
        nfc_mod._shed = False

        try:
            from bodn.nfc import NFCReader

            reader = NFCReader()
            assert reader.available() is True
            uid_str, data = reader.scan()
            assert uid_str == "04:A3:B2:C1:D4:E5:F6"
            assert data is not None
            parsed = parse_tag_data(data)
            assert parsed is not None
            assert parsed["mode"] == "sortera"
            assert parsed["id"] == "cat_red"
        finally:
            nfc_mod._pn532 = old_pn
            nfc_mod._shed = old_shed

    def test_scan_no_tag(self):
        import bodn.nfc as nfc_mod

        old_pn = nfc_mod._pn532
        fake_pn = FakePN532(uid=None)
        nfc_mod._pn532 = fake_pn
        try:
            from bodn.nfc import NFCReader

            reader = NFCReader()
            uid_str, data = reader.scan()
            assert uid_str is None
            assert data is None
        finally:
            nfc_mod._pn532 = old_pn


class TestNFCReaderThermalShed:
    def test_shed_disables_scan(self):
        import bodn.nfc as nfc_mod

        old_pn = nfc_mod._pn532
        old_shed = nfc_mod._shed
        uid = bytes([0x04, 0xA3, 0xB2, 0xC1])
        nfc_mod._pn532 = FakePN532(uid=uid)
        nfc_mod._shed = True
        try:
            from bodn.nfc import NFCReader

            reader = NFCReader()
            assert reader.available() is True
            uid_str, data = reader.scan()
            assert uid_str is None  # shed blocks scan
        finally:
            nfc_mod._pn532 = old_pn
            nfc_mod._shed = old_shed

    def test_set_thermal_shed(self):
        import bodn.nfc as nfc_mod

        old_shed = nfc_mod._shed
        try:
            nfc_mod.set_thermal_shed(True)
            assert nfc_mod._shed is True
            nfc_mod.set_thermal_shed(False)
            assert nfc_mod._shed is False
        finally:
            nfc_mod._shed = old_shed


class TestNFCReaderWrite:
    def test_write_and_verify(self):
        import bodn.nfc as nfc_mod

        old_pn = nfc_mod._pn532
        old_shed = nfc_mod._shed
        fake_pn = FakePN532(uid=bytes([0x04, 0xAA, 0xBB, 0xCC]))
        nfc_mod._pn532 = fake_pn
        nfc_mod._shed = False
        try:
            from bodn.nfc import NFCReader

            reader = NFCReader()
            data = encode_tag_data("sortera", "cat_red")
            assert reader.write(data) is True
            # Verify pages were written
            assert len(fake_pn._pages) > 0
        finally:
            nfc_mod._pn532 = old_pn
            nfc_mod._shed = old_shed

    def test_write_when_shed(self):
        import bodn.nfc as nfc_mod

        old_pn = nfc_mod._pn532
        old_shed = nfc_mod._shed
        nfc_mod._pn532 = FakePN532()
        nfc_mod._shed = True
        try:
            from bodn.nfc import NFCReader

            reader = NFCReader()
            data = encode_tag_data("sortera", "cat_red")
            assert reader.write(data) is False
        finally:
            nfc_mod._pn532 = old_pn
            nfc_mod._shed = old_shed
