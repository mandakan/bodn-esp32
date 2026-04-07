# tests/test_qr.py — QR code encoder tests

import pytest
from bodn.qr import encode


class TestQREncode:
    """Test QR code generation for short URLs."""

    def test_v1_dimensions(self):
        """Version 1 QR code should be 21x21."""
        matrix = encode("http://1.2.3.4")
        assert len(matrix) == 21
        assert all(len(row) == 21 for row in matrix)

    def test_v2_dimensions(self):
        """Version 2 QR code (longer data) should be 25x25."""
        matrix = encode("http://192.168.4.1/settings")
        assert len(matrix) == 25
        assert all(len(row) == 25 for row in matrix)

    def test_too_long_raises(self):
        """Data exceeding V2 capacity should raise ValueError."""
        with pytest.raises(ValueError, match="too long"):
            encode("x" * 33)

    def test_matrix_values_binary(self):
        """All matrix cells should be 0 or 1."""
        matrix = encode("http://192.168.4.1")
        for row in matrix:
            for cell in row:
                assert cell in (0, 1)

    def test_finder_pattern_top_left(self):
        """Top-left finder pattern: 7x7 with alternating border."""
        matrix = encode("HELLO")
        # Top-left corner should have the finder pattern
        # Top row of finder: all 1s for first 7 cells
        assert matrix[0][0:7] == [1, 1, 1, 1, 1, 1, 1]
        # Second row: 1, then 5 zeros, then 1
        assert matrix[1][0] == 1
        assert matrix[1][6] == 1
        assert matrix[1][1:6] == [0, 0, 0, 0, 0]

    def test_finder_pattern_top_right(self):
        """Top-right finder pattern exists."""
        matrix = encode("HELLO")
        size = len(matrix)
        # Top-right corner row 0: last 7 cells all 1
        assert matrix[0][size - 7 : size] == [1, 1, 1, 1, 1, 1, 1]

    def test_finder_pattern_bottom_left(self):
        """Bottom-left finder pattern exists."""
        matrix = encode("HELLO")
        size = len(matrix)
        # Bottom-left row (size-1): first 7 cells all 1
        assert matrix[size - 1][0:7] == [1, 1, 1, 1, 1, 1, 1]

    def test_dark_module(self):
        """The dark module at (size-8, 8) should always be 1."""
        matrix = encode("TEST")
        size = len(matrix)
        assert matrix[size - 8][8] == 1

    def test_deterministic(self):
        """Same input should produce identical output."""
        m1 = encode("http://192.168.4.1")
        m2 = encode("http://192.168.4.1")
        assert m1 == m2

    def test_different_inputs_differ(self):
        """Different inputs should produce different matrices."""
        m1 = encode("http://a.com")
        m2 = encode("http://b.com")
        assert m1 != m2

    def test_bytes_input(self):
        """Should accept bytes as well as str."""
        m1 = encode("TEST")
        m2 = encode(b"TEST")
        assert m1 == m2

    def test_max_v1_length(self):
        """17 bytes should still produce V1 (21x21)."""
        matrix = encode("x" * 17)
        assert len(matrix) == 21

    def test_v1_to_v2_boundary(self):
        """18 bytes should produce V2 (25x25)."""
        matrix = encode("x" * 18)
        assert len(matrix) == 25
