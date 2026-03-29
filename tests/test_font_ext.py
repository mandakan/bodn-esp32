# tests/test_font_ext.py — extended font glyph tests

from bodn.ui.font_ext import GLYPHS


class TestFontExt:
    def test_all_swedish_chars_present(self):
        for ch in "åäöÅÄÖ":
            assert ch in GLYPHS, "Missing glyph for '{}'".format(ch)

    def test_eth_chars_present(self):
        for ch in "ðÐ":
            assert ch in GLYPHS, "Missing glyph for '{}'".format(ch)

    def test_eth_has_crossbar(self):
        """ð crossbar is row 1 (0x7E); Ð crossbar is row 3 (0xFE)."""
        assert GLYPHS["ð"][1] == 0x7E, "ð missing crossbar"
        assert GLYPHS["Ð"][3] == 0xFE, "Ð missing crossbar"

    def test_glyph_size(self):
        """Each glyph must be exactly 8 bytes (8 rows × 1 byte)."""
        for ch, data in GLYPHS.items():
            assert len(data) == 8, "Glyph '{}' has {} bytes, expected 8".format(
                ch, len(data)
            )

    def test_glyphs_are_not_blank(self):
        """Each glyph should have at least some pixels set."""
        for ch, data in GLYPHS.items():
            total_bits = sum(bin(b).count("1") for b in data)
            assert total_bits > 0, "Glyph '{}' is completely blank".format(ch)

    def test_diaeresis_chars_share_dot_pattern(self):
        """ä/Ä and ö/Ö should have diaeresis dots (0x24 = two dots pattern)."""
        # Row with dots should be 0x24 (bits at positions 2 and 5)
        for ch in ("ä", "ö", "Ä", "Ö"):
            assert GLYPHS[ch][0] == 0x24, "Glyph '{}' missing diaeresis dots".format(ch)

    def test_ring_char_has_ring(self):
        """å and Å should have a ring (0x18 = small circle top)."""
        assert GLYPHS["å"][0] == 0x18, "å missing ring"
        assert GLYPHS["Å"][0] == 0x18, "Å missing ring"
