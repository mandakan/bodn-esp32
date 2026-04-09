#!/usr/bin/env python3
"""make_asset.py — Convert fonts and images to Bodn Draw Format (.bdf).

Usage:
  # Rasterize a TTF font to BDF
  uv run python tools/make_asset.py \\
    --font assets/fonts/PixelOperator.ttf --size 16 \\
    --charset ascii+swedish --bpp 1 --output build/fonts/pixel16.bdf

  # Convert an SVG/PNG image to a single-frame sprite
  uv run python tools/make_asset.py \\
    --image assets/images/source/lo-logo.svg --width 120 \\
    --bpp 4 --output build/sprites/lo-logo.bdf

  # Generate the built-in 8x8 font as a C header
  uv run python tools/make_asset.py --font-embed \\
    --output cmodules/draw/fonts/builtin_8x8.h

The BDF (Bodn Draw Format) is a compact binary format for bitmap fonts and
sprite sheets.  See cmodules/draw/draw.h for the specification.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

BDF_MAGIC = 0x4442  # 'BD' little-endian
BDF_VERSION = 1
TYPE_FONT = 0
TYPE_SPRITESHEET = 1

# Standard charset definitions
CHARSET_ASCII = list(range(0x20, 0x7F))  # space through ~
CHARSET_SWEDISH = [
    0xC4,  # Ä
    0xC5,  # Å
    0xD0,  # Ð
    0xD6,  # Ö
    0xE4,  # ä
    0xE5,  # å
    0xF0,  # ð
    0xF6,  # ö
]


def parse_charset(spec: str) -> list[int]:
    """Parse a charset specification into a sorted list of codepoints."""
    parts = spec.lower().split("+")
    cps: set[int] = set()
    for part in parts:
        if part == "ascii":
            cps.update(CHARSET_ASCII)
        elif part == "swedish":
            cps.update(CHARSET_SWEDISH)
        else:
            raise ValueError(f"Unknown charset component: {part!r}")
    return sorted(cps)


def pack_bitmap_row(pixels: list[int], bpp: int) -> bytes:
    """Pack a row of pixel intensity values into bytes (MSB-first)."""
    bits_per_px = bpp
    buf = []
    current_byte = 0
    bit_pos = 0

    for px in pixels:
        current_byte = (current_byte << bits_per_px) | (px & ((1 << bits_per_px) - 1))
        bit_pos += bits_per_px
        if bit_pos >= 8:
            buf.append(current_byte)
            current_byte = 0
            bit_pos = 0

    # Flush partial byte (pad with zeros on the right / LSB side)
    if bit_pos > 0:
        current_byte <<= 8 - bit_pos
        buf.append(current_byte)

    return bytes(buf)


FLAG_COLOR = 0x01  # RGB565 color data + alpha


def build_bdf(
    entries: list[tuple[int, int, int, bytes]],  # (id, width, height, packed_bitmap)
    asset_type: int,
    bpp: int,
    max_width: int,
    height: int,
    baseline: int = 0,
    flags: int = 0,
) -> bytes:
    """Assemble a complete BDF binary blob from entries."""
    # Sort by id
    entries = sorted(entries, key=lambda e: e[0])
    num = len(entries)

    bitmap_offset = 20 + num * 10
    header = struct.pack(
        "<HBBBBHHHHIH",
        BDF_MAGIC,
        BDF_VERSION,
        asset_type,
        bpp,
        flags,
        num,
        max_width,
        height,
        baseline,
        bitmap_offset,
        0,  # reserved
    )
    assert len(header) == 20

    index_data = b""
    bitmap_data = b""
    for entry_id, w, h, bitmap in entries:
        index_data += struct.pack("<IBBI", entry_id, w, h, len(bitmap_data))
        bitmap_data += bitmap

    return header + index_data + bitmap_data


# ── Font mode ─────────────────────────────────────────────────────


def rasterize_font(font_path: str, size: int, codepoints: list[int], bpp: int) -> bytes:
    """Rasterize a TTF/OTF font into BDF format."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Error: Pillow is required for font rasterization.", file=sys.stderr)
        print("  Install with: uv pip install Pillow", file=sys.stderr)
        sys.exit(1)

    font = ImageFont.truetype(font_path, size)
    max_val = (1 << bpp) - 1
    entries = []
    max_width = 0

    for cp in codepoints:
        ch = chr(cp)

        # Get glyph bounding box
        bbox = font.getbbox(ch)
        if bbox is None:
            continue

        # Render glyph to grayscale image
        left, top, right, bottom = bbox
        gw = right - left
        gh = bottom - top
        if gw <= 0 or gh <= 0:
            continue

        img = Image.new("L", (gw, gh), 0)
        draw = ImageDraw.Draw(img)
        draw.text((-left, -top), ch, fill=255, font=font)

        # Quantize to target bpp levels
        packed = b""
        for y in range(gh):
            row = []
            for x in range(gw):
                val = img.getpixel((x, y))
                # Map 0-255 to 0-max_val
                quantized = (val * max_val + 127) // 255
                row.append(quantized)
            packed += pack_bitmap_row(row, bpp)

        entries.append((cp, gw, gh, packed))
        if gw > max_width:
            max_width = gw

    # Use the font's declared size as line height
    return build_bdf(entries, TYPE_FONT, bpp, max_width, size)


# ── Image mode ────────────────────────────────────────────────────


def rgb_to_rgb565_le(r: int, g: int, b: int) -> int:
    """Convert 8-bit RGB to byte-swapped RGB565 (matching MicroPython framebuf)."""
    r5 = (r >> 3) & 0x1F
    g6 = (g >> 2) & 0x3F
    b5 = (b >> 3) & 0x1F
    be = (r5 << 11) | (g6 << 5) | b5
    # Byte-swap for framebuf LE storage
    return ((be & 0xFF) << 8) | (be >> 8)


def rasterize_image(image_path: str, width: int, bpp: int) -> bytes:
    """Convert an SVG/PNG image to a color+alpha BDF sprite.

    Stores full RGB565 pixel data + separate alpha plane (DRAW_FLAG_COLOR).
    """
    try:
        from PIL import Image
    except ImportError:
        print("Error: Pillow is required for image conversion.", file=sys.stderr)
        print("  Install with: uv pip install Pillow", file=sys.stderr)
        sys.exit(1)

    path = Path(image_path)

    if path.suffix.lower() == ".svg":
        try:
            import cairosvg
        except ImportError:
            print("Error: cairosvg is required for SVG conversion.", file=sys.stderr)
            print("  Install with: uv pip install cairosvg", file=sys.stderr)
            sys.exit(1)

        import io

        png_data = cairosvg.svg2png(url=str(path), output_width=width)
        img = Image.open(io.BytesIO(png_data))
    else:
        img = Image.open(path)
        if width:
            ratio = width / img.width
            new_h = int(img.height * ratio)
            img = img.resize((width, new_h), Image.LANCZOS)

    img = img.convert("RGBA")
    w, h = img.size
    max_val = (1 << bpp) - 1

    # Build RGB565 plane + alpha plane
    rgb_data = bytearray()
    alpha_rows: list[list[int]] = []

    for y in range(h):
        row_alpha = []
        for x in range(w):
            r, g, b, a = img.getpixel((x, y))
            # Pre-multiply: if alpha is 0, color doesn't matter (store black)
            rgb565 = rgb_to_rgb565_le(r, g, b) if a > 0 else 0
            rgb_data.append(rgb565 & 0xFF)
            rgb_data.append((rgb565 >> 8) & 0xFF)
            row_alpha.append((a * max_val + 127) // 255)
        alpha_rows.append(row_alpha)

    # Pack alpha plane
    alpha_data = b""
    for row in alpha_rows:
        alpha_data += pack_bitmap_row(row, bpp)

    # Combined: RGB565 plane + alpha plane
    packed = bytes(rgb_data) + alpha_data

    entries = [(0, w, h, packed)]
    return build_bdf(entries, TYPE_SPRITESHEET, bpp, w, h, flags=FLAG_COLOR)


# ── Font-embed mode ──────────────────────────────────────────────


def generate_font_embed() -> bytes:
    """Generate the built-in 8x8 font BDF blob from MicroPython's font + font_ext.py.

    This reimplements the font generation so make_asset.py is self-contained.
    """
    # MicroPython's font_petme128_8x8: column-major, 8 bytes per glyph
    # bit 0 = top row, bit 7 = bottom row
    # fmt: off
    font_col = [
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x4f,0x4f,0x00,0x00,0x00,
        0x00,0x07,0x07,0x00,0x00,0x07,0x07,0x00,
        0x14,0x7f,0x7f,0x14,0x14,0x7f,0x7f,0x14,
        0x00,0x24,0x2e,0x6b,0x6b,0x3a,0x12,0x00,
        0x00,0x63,0x33,0x18,0x0c,0x66,0x63,0x00,
        0x00,0x32,0x7f,0x4d,0x4d,0x77,0x72,0x50,
        0x00,0x00,0x00,0x04,0x06,0x03,0x01,0x00,
        0x00,0x00,0x1c,0x3e,0x63,0x41,0x00,0x00,
        0x00,0x00,0x41,0x63,0x3e,0x1c,0x00,0x00,
        0x08,0x2a,0x3e,0x1c,0x1c,0x3e,0x2a,0x08,
        0x00,0x08,0x08,0x3e,0x3e,0x08,0x08,0x00,
        0x00,0x00,0x80,0xe0,0x60,0x00,0x00,0x00,
        0x00,0x08,0x08,0x08,0x08,0x08,0x08,0x00,
        0x00,0x00,0x00,0x60,0x60,0x00,0x00,0x00,
        0x00,0x40,0x60,0x30,0x18,0x0c,0x06,0x02,
        0x00,0x3e,0x7f,0x49,0x45,0x7f,0x3e,0x00,
        0x00,0x40,0x44,0x7f,0x7f,0x40,0x40,0x00,
        0x00,0x62,0x73,0x51,0x49,0x4f,0x46,0x00,
        0x00,0x22,0x63,0x49,0x49,0x7f,0x36,0x00,
        0x00,0x18,0x18,0x14,0x16,0x7f,0x7f,0x10,
        0x00,0x27,0x67,0x45,0x45,0x7d,0x39,0x00,
        0x00,0x3e,0x7f,0x49,0x49,0x7b,0x32,0x00,
        0x00,0x03,0x03,0x79,0x7d,0x07,0x03,0x00,
        0x00,0x36,0x7f,0x49,0x49,0x7f,0x36,0x00,
        0x00,0x26,0x6f,0x49,0x49,0x7f,0x3e,0x00,
        0x00,0x00,0x00,0x24,0x24,0x00,0x00,0x00,
        0x00,0x00,0x80,0xe4,0x64,0x00,0x00,0x00,
        0x00,0x08,0x1c,0x36,0x63,0x41,0x41,0x00,
        0x00,0x14,0x14,0x14,0x14,0x14,0x14,0x00,
        0x00,0x41,0x41,0x63,0x36,0x1c,0x08,0x00,
        0x00,0x02,0x03,0x51,0x59,0x0f,0x06,0x00,
        0x00,0x3e,0x7f,0x41,0x4d,0x4f,0x2e,0x00,
        0x00,0x7c,0x7e,0x0b,0x0b,0x7e,0x7c,0x00,
        0x00,0x7f,0x7f,0x49,0x49,0x7f,0x36,0x00,
        0x00,0x3e,0x7f,0x41,0x41,0x63,0x22,0x00,
        0x00,0x7f,0x7f,0x41,0x63,0x3e,0x1c,0x00,
        0x00,0x7f,0x7f,0x49,0x49,0x41,0x41,0x00,
        0x00,0x7f,0x7f,0x09,0x09,0x01,0x01,0x00,
        0x00,0x3e,0x7f,0x41,0x49,0x7b,0x3a,0x00,
        0x00,0x7f,0x7f,0x08,0x08,0x7f,0x7f,0x00,
        0x00,0x00,0x41,0x7f,0x7f,0x41,0x00,0x00,
        0x00,0x20,0x60,0x41,0x7f,0x3f,0x01,0x00,
        0x00,0x7f,0x7f,0x1c,0x36,0x63,0x41,0x00,
        0x00,0x7f,0x7f,0x40,0x40,0x40,0x40,0x00,
        0x00,0x7f,0x7f,0x06,0x0c,0x06,0x7f,0x7f,
        0x00,0x7f,0x7f,0x0e,0x1c,0x7f,0x7f,0x00,
        0x00,0x3e,0x7f,0x41,0x41,0x7f,0x3e,0x00,
        0x00,0x7f,0x7f,0x09,0x09,0x0f,0x06,0x00,
        0x00,0x1e,0x3f,0x21,0x61,0x7f,0x5e,0x00,
        0x00,0x7f,0x7f,0x19,0x39,0x6f,0x46,0x00,
        0x00,0x26,0x6f,0x49,0x49,0x7b,0x32,0x00,
        0x00,0x01,0x01,0x7f,0x7f,0x01,0x01,0x00,
        0x00,0x3f,0x7f,0x40,0x40,0x7f,0x3f,0x00,
        0x00,0x1f,0x3f,0x60,0x60,0x3f,0x1f,0x00,
        0x00,0x7f,0x7f,0x30,0x18,0x30,0x7f,0x7f,
        0x00,0x63,0x77,0x1c,0x1c,0x77,0x63,0x00,
        0x00,0x07,0x0f,0x78,0x78,0x0f,0x07,0x00,
        0x00,0x61,0x71,0x59,0x4d,0x47,0x43,0x00,
        0x00,0x00,0x7f,0x7f,0x41,0x41,0x00,0x00,
        0x00,0x02,0x06,0x0c,0x18,0x30,0x60,0x40,
        0x00,0x00,0x41,0x41,0x7f,0x7f,0x00,0x00,
        0x00,0x08,0x0c,0x06,0x06,0x0c,0x08,0x00,
        0xc0,0xc0,0xc0,0xc0,0xc0,0xc0,0xc0,0xc0,
        0x00,0x00,0x01,0x03,0x06,0x04,0x00,0x00,
        0x00,0x20,0x74,0x54,0x54,0x7c,0x78,0x00,
        0x00,0x7f,0x7f,0x44,0x44,0x7c,0x38,0x00,
        0x00,0x38,0x7c,0x44,0x44,0x6c,0x28,0x00,
        0x00,0x38,0x7c,0x44,0x44,0x7f,0x7f,0x00,
        0x00,0x38,0x7c,0x54,0x54,0x5c,0x58,0x00,
        0x00,0x08,0x7e,0x7f,0x09,0x03,0x02,0x00,
        0x00,0x98,0xbc,0xa4,0xa4,0xfc,0x7c,0x00,
        0x00,0x7f,0x7f,0x04,0x04,0x7c,0x78,0x00,
        0x00,0x00,0x00,0x7d,0x7d,0x00,0x00,0x00,
        0x00,0x40,0xc0,0x80,0x80,0xfd,0x7d,0x00,
        0x00,0x7f,0x7f,0x30,0x38,0x6c,0x44,0x00,
        0x00,0x00,0x41,0x7f,0x7f,0x40,0x00,0x00,
        0x00,0x7c,0x7c,0x18,0x30,0x18,0x7c,0x7c,
        0x00,0x7c,0x7c,0x04,0x04,0x7c,0x78,0x00,
        0x00,0x38,0x7c,0x44,0x44,0x7c,0x38,0x00,
        0x00,0xfc,0xfc,0x24,0x24,0x3c,0x18,0x00,
        0x00,0x18,0x3c,0x24,0x24,0xfc,0xfc,0x00,
        0x00,0x7c,0x7c,0x04,0x04,0x0c,0x08,0x00,
        0x00,0x48,0x5c,0x54,0x54,0x74,0x20,0x00,
        0x04,0x04,0x3f,0x7f,0x44,0x64,0x20,0x00,
        0x00,0x3c,0x7c,0x40,0x40,0x7c,0x3c,0x00,
        0x00,0x1c,0x3c,0x60,0x60,0x3c,0x1c,0x00,
        0x00,0x1c,0x7c,0x30,0x18,0x30,0x7c,0x1c,
        0x00,0x44,0x6c,0x38,0x38,0x6c,0x44,0x00,
        0x00,0x9c,0xbc,0xa0,0xa0,0xfc,0x7c,0x00,
        0x00,0x44,0x64,0x74,0x5c,0x4c,0x44,0x00,
        0x00,0x08,0x08,0x3e,0x77,0x41,0x41,0x00,
        0x00,0x00,0x00,0xff,0xff,0x00,0x00,0x00,
        0x00,0x41,0x41,0x77,0x3e,0x08,0x08,0x00,
        0x00,0x02,0x03,0x01,0x03,0x02,0x03,0x01,
    ]
    # fmt: on

    def transpose(col_data: list[int]) -> bytes:
        rows = []
        for r in range(8):
            byte = 0
            for c in range(8):
                if col_data[c] & (1 << r):
                    byte |= 0x80 >> c
            rows.append(byte)
        return bytes(rows)

    # Extended glyphs (already row-major MSB-first)
    ext_glyphs = {
        0xC4: b"\x24\x00\x3c\x42\x7e\x42\x42\x00",  # Ä
        0xC5: b"\x18\x24\x42\x42\x7e\x42\x42\x00",  # Å
        0xD0: b"\x78\x44\x42\xfe\x42\x44\x78\x00",  # Ð
        0xD6: b"\x24\x00\x3c\x42\x42\x42\x3c\x00",  # Ö
        0xE4: b"\x24\x00\x3c\x02\x3e\x42\x3e\x00",  # ä
        0xE5: b"\x18\x00\x3c\x02\x3e\x42\x3e\x00",  # å
        0xF0: b"\x06\x7e\x06\x1e\x22\x22\x1e\x00",  # ð
        0xF6: b"\x24\x00\x3c\x42\x42\x42\x3c\x00",  # ö
    }

    entries = []

    # ASCII range from MicroPython font
    for i in range(95):
        cp = 0x20 + i
        col = font_col[i * 8 : (i + 1) * 8]
        packed = transpose(col)
        # Each row is 1 byte (8 pixels at 1bpp) — already correctly packed
        entries.append((cp, 8, 8, packed))

    # Extended glyphs
    for cp, data in ext_glyphs.items():
        entries.append((cp, 8, 8, data))

    return build_bdf(entries, TYPE_FONT, 1, 8, 8)


def write_c_header(blob: bytes, output_path: str) -> None:
    """Write a BDF blob as a C header file."""
    num_entries = struct.unpack_from("<H", blob, 6)[0]
    lines = [
        f"/* builtin_8x8.h — auto-generated built-in 8x8 font"
        f" ({num_entries} glyphs, {len(blob)} bytes) */",
        "",
        "#ifndef DRAW_BUILTIN_8X8_H",
        "#define DRAW_BUILTIN_8X8_H",
        "",
        "#include <stdint.h>",
        "",
        f"static const uint8_t builtin_8x8_data[{len(blob)}] = {{",
    ]

    for i in range(0, len(blob), 16):
        chunk = blob[i : i + 16]
        hex_str = ", ".join(f"0x{b:02x}" for b in chunk)
        lines.append(f"    {hex_str},")

    lines.extend(["};", "", "#endif /* DRAW_BUILTIN_8X8_H */", ""])

    Path(output_path).write_text("\n".join(lines))
    print(f"Wrote {output_path} ({len(blob)} bytes, {num_entries} glyphs)")


# ── CLI ───────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Convert fonts and images to Bodn Draw Format (.bdf)"
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--font", help="TTF/OTF font file to rasterize")
    group.add_argument("--image", help="SVG/PNG image to convert to sprite")
    group.add_argument(
        "--font-embed",
        action="store_true",
        help="Generate built-in 8x8 font as C header",
    )

    parser.add_argument(
        "--size", type=int, default=16, help="Font size in pixels (default: 16)"
    )
    parser.add_argument(
        "--charset",
        default="ascii+swedish",
        help="Charset spec: ascii, swedish, ascii+swedish (default: ascii+swedish)",
    )
    parser.add_argument(
        "--bpp", type=int, default=1, choices=[1, 2, 4, 8], help="Bits per pixel"
    )
    parser.add_argument("--width", type=int, help="Target width for image sprites")
    parser.add_argument("--output", "-o", required=True, help="Output file path")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without writing"
    )

    args = parser.parse_args()

    if args.font_embed:
        blob = generate_font_embed()
        if args.dry_run:
            print(f"Would write C header: {args.output} ({len(blob)} bytes)")
            return
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        write_c_header(blob, args.output)

    elif args.font:
        codepoints = parse_charset(args.charset)
        if args.dry_run:
            print(f"Would rasterize {args.font} at {args.size}px, {args.bpp}bpp")
            print(f"  {len(codepoints)} codepoints from charset '{args.charset}'")
            print(f"  Output: {args.output}")
            return
        blob = rasterize_font(args.font, args.size, codepoints, args.bpp)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_bytes(blob)
        num = struct.unpack_from("<H", blob, 6)[0]
        print(f"Wrote {args.output} ({len(blob)} bytes, {num} glyphs, {args.bpp}bpp)")

    elif args.image:
        if not args.width:
            parser.error("--width is required for --image mode")
        if args.dry_run:
            print(f"Would convert {args.image} at width={args.width}, {args.bpp}bpp")
            print(f"  Output: {args.output}")
            return
        blob = rasterize_image(args.image, args.width, args.bpp)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_bytes(blob)
        w = struct.unpack_from("<H", blob, 8)[0]
        h = struct.unpack_from("<H", blob, 10)[0]
        print(f"Wrote {args.output} ({len(blob)} bytes, {w}x{h}, {args.bpp}bpp)")


if __name__ == "__main__":
    main()
