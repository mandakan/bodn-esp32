# bodn/ui/font_ext.py — extended character bitmaps (8×8, 1bpp)
#
# MicroPython's built-in framebuf font only covers ASCII (0x00–0x7F).
# This module provides 8×8 bitmap glyphs for Swedish characters that
# are missing from the built-in font.
#
# Each glyph is 8 bytes: one byte per row, MSB = leftmost pixel.
# Design based on standard 8×8 bitmap font conventions.

GLYPHS = {
    # å — ring above + lowercase a
    "å": b"\x18\x00\x3c\x02\x3e\x42\x3e\x00",
    # ä — diaeresis + lowercase a
    "ä": b"\x24\x00\x3c\x02\x3e\x42\x3e\x00",
    # ö — diaeresis + lowercase o
    "ö": b"\x24\x00\x3c\x42\x42\x42\x3c\x00",
    # Å — ring above + uppercase A
    "Å": b"\x18\x24\x42\x42\x7e\x42\x42\x00",
    # Ä — diaeresis + uppercase A
    "Ä": b"\x24\x00\x3c\x42\x7e\x42\x42\x00",
    # Ö — diaeresis + uppercase O
    "Ö": b"\x24\x00\x3c\x42\x42\x42\x3c\x00",
    # ð — eth (lowercase); ascender with horizontal crossbar + 'd' bowl
    #   .....##.   ascender tip
    #   .######.   crossbar (the defining eth stroke)
    #   .....##.   lower ascender
    #   ...####.   bowl top
    #   ..#...#.   bowl sides
    #   ..#...#.
    #   ...####.   bowl base
    #   ........
    "ð": b"\x06\x7e\x06\x1e\x22\x22\x1e\x00",
    # Ð — Eth (uppercase); D-shape with full-width crossbar through the middle
    #   .####...   top of D
    #   .#...#..
    #   .#....#.
    #   #######.   crossbar extends left of stem
    #   .#....#.
    #   .#...#..
    #   .####...   base of D
    #   ........
    "Ð": b"\x78\x44\x42\xfe\x42\x44\x78\x00",
}
