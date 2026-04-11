#!/usr/bin/env python3
"""
Generate printable card face PDFs from NFC card set templates.

Reads card set definitions from assets/nfc/{mode}.json, pulls matching
OpenMoji SVGs by Unicode codepoint, and renders A4 PDF sheets with
credit-card-sized card faces ready for printing, cutting, and laminating.

Usage:
  # Generate all card sets (requires OpenMoji SVGs)
  uv run python tools/generate_cards.py --openmoji ~/openmoji

  # Specific card set only
  uv run python tools/generate_cards.py --set sortera --openmoji ~/openmoji

  # Custom output directory
  uv run python tools/generate_cards.py --openmoji ~/openmoji --output build/cards

  # Preview mode (list cards without generating)
  uv run python tools/generate_cards.py --dry-run

Setup:
  # Clone OpenMoji SVGs (one-time, ~200 MB)
  git clone --depth 1 https://github.com/hfg-gmuend/openmoji.git ~/openmoji
"""

import argparse
import json
import sys
from io import BytesIO
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
ASSETS_DIR = REPO_ROOT / "assets" / "nfc"
BUILD_DIR = REPO_ROOT / "build" / "cards"

# Card dimensions in mm (credit card size)
CARD_W = 85
CARD_H = 54

# A4 page dimensions in mm
PAGE_W = 210
PAGE_H = 297

# Layout: 2 columns × 4 rows = 8 cards per page
COLS = 2
ROWS = 4
MARGIN_X = (PAGE_W - COLS * CARD_W) / (COLS + 1)
MARGIN_Y = (PAGE_H - ROWS * CARD_H) / (ROWS + 1)

# Emoji render size in pixels (rasterised from SVG, then placed in PDF)
EMOJI_PX = 256

# Colour palette for card backgrounds (soft, child-friendly tones)
COLOUR_MAP = {
    "red": (233, 69, 96),
    "blue": (52, 152, 219),
    "green": (46, 204, 113),
    "yellow": (241, 196, 15),
    "orange": (230, 126, 34),
    "purple": (155, 89, 182),
    "pink": (232, 67, 147),
    "white": (236, 240, 241),
}

# Default background for cards without a colour dimension
DEFAULT_BG = (236, 240, 241)

# Border and text colours
BORDER_COLOUR = (44, 62, 80)
LABEL_COLOUR = (255, 255, 255)
ID_COLOUR = (200, 200, 200)


def load_card_set(path: Path) -> dict:
    """Load and validate a card set JSON file."""
    with open(path) as f:
        data = json.load(f)
    if "cards" not in data or "mode" not in data:
        raise ValueError(f"Invalid card set: missing 'cards' or 'mode' in {path}")
    return data


def find_openmoji_svg(codepoint: str, openmoji_dir: Path) -> Path | None:
    """Find an OpenMoji SVG file by Unicode codepoint."""
    svg_path = openmoji_dir / "svg" / "color" / f"{codepoint.upper()}.svg"
    if svg_path.exists():
        return svg_path
    # Try lowercase
    svg_path = openmoji_dir / "svg" / "color" / f"{codepoint.lower()}.svg"
    if svg_path.exists():
        return svg_path
    return None


def render_emoji_png(svg_path: Path, size_px: int) -> bytes:
    """Rasterise an OpenMoji SVG to PNG bytes at the given size."""
    import cairosvg

    return cairosvg.svg2png(
        url=str(svg_path),
        output_width=size_px,
        output_height=size_px,
    )


def generate_pdf(card_set: dict, openmoji_dir: Path | None, output_path: Path):
    """Generate an A4 PDF with card faces laid out in a grid."""
    from fpdf import FPDF

    cards = card_set["cards"]
    mode = card_set["mode"]

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)

    # Embed a clean sans-serif font if available, else use Helvetica
    pdf.set_font("Helvetica")

    cards_per_page = COLS * ROWS
    total_pages = (len(cards) + cards_per_page - 1) // cards_per_page

    for page_idx in range(total_pages):
        pdf.add_page()
        start = page_idx * cards_per_page
        page_cards = cards[start : start + cards_per_page]

        for i, card in enumerate(page_cards):
            col = i % COLS
            row = i // COLS

            x = MARGIN_X + col * (CARD_W + MARGIN_X)
            y = MARGIN_Y + row * (CARD_H + MARGIN_Y)

            _draw_card(pdf, card, x, y, mode, openmoji_dir)

    # Footer with attribution
    pdf.set_y(-15)
    pdf.set_font("Helvetica", size=6)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(
        0,
        5,
        f"Bodn {mode} cards | Icons: OpenMoji (CC-BY-SA 4.0, openmoji.org)",
        align="C",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(output_path))


def _draw_card(pdf, card: dict, x: float, y: float, mode: str, openmoji_dir):
    """Draw a single card face at the given position."""
    # Background colour
    colour = card.get("colour", "")
    bg = COLOUR_MAP.get(colour, DEFAULT_BG)
    pdf.set_fill_color(*bg)
    pdf.rect(x, y, CARD_W, CARD_H, style="F")

    # Border (cutting guide)
    pdf.set_draw_color(*BORDER_COLOUR)
    pdf.set_line_width(0.3)
    pdf.rect(x, y, CARD_W, CARD_H, style="D")

    # Emoji icon
    icon_codepoint = card.get("icon", "")
    emoji_placed = False
    if openmoji_dir and icon_codepoint:
        svg_path = find_openmoji_svg(icon_codepoint, openmoji_dir)
        if svg_path:
            try:
                png_data = render_emoji_png(svg_path, EMOJI_PX)
                # Place emoji centred in the upper portion of the card
                emoji_mm = 28  # display size in mm
                emoji_x = x + (CARD_W - emoji_mm) / 2
                emoji_y = y + 3
                pdf.image(
                    BytesIO(png_data),
                    x=emoji_x,
                    y=emoji_y,
                    w=emoji_mm,
                    h=emoji_mm,
                )
                emoji_placed = True
            except Exception as e:
                print(f"  Warning: failed to render {icon_codepoint}: {e}")

    if not emoji_placed:
        # Fallback: show codepoint text
        pdf.set_font("Helvetica", "B", size=24)
        pdf.set_text_color(*BORDER_COLOUR)
        pdf.set_xy(x, y + 8)
        pdf.cell(CARD_W, 20, f"U+{icon_codepoint}", align="C")

    # Swedish label (primary, larger)
    label_sv = card.get("label_sv", "")
    label_y = y + 34
    pdf.set_font("Helvetica", "B", size=14)
    # Use dark text on light backgrounds, white on dark
    brightness = bg[0] * 0.299 + bg[1] * 0.587 + bg[2] * 0.114
    if brightness > 160:
        pdf.set_text_color(*BORDER_COLOUR)
    else:
        pdf.set_text_color(*LABEL_COLOUR)
    pdf.set_xy(x, label_y)
    pdf.cell(CARD_W, 7, label_sv, align="C")

    # English label (secondary, smaller)
    label_en = card.get("label_en", "")
    pdf.set_font("Helvetica", size=9)
    pdf.set_xy(x, label_y + 7)
    pdf.cell(CARD_W, 5, label_en, align="C")

    # Card ID in small text (bottom-right corner, for parent reference)
    pdf.set_font("Helvetica", size=5)
    pdf.set_text_color(*(ID_COLOUR if brightness < 160 else (120, 120, 120)))
    pdf.set_xy(x, y + CARD_H - 6)
    pdf.cell(CARD_W - 2, 4, card.get("id", ""), align="R")


def main():
    parser = argparse.ArgumentParser(
        description="Generate printable NFC card face PDFs from card set templates.",
        epilog=(
            "OpenMoji SVGs can be obtained by cloning:\n"
            "  git clone --depth 1 https://github.com/hfg-gmuend/openmoji.git ~/openmoji"
        ),
    )
    parser.add_argument(
        "--set",
        help="Generate for a specific card set only (e.g., 'sortera')",
    )
    parser.add_argument(
        "--openmoji",
        type=Path,
        default=Path.home() / "openmoji",
        help="Path to OpenMoji repository (default: ~/openmoji)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=BUILD_DIR,
        help="Output directory (default: build/cards)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List cards without generating PDFs",
    )
    args = parser.parse_args()

    # Find card set files
    if not ASSETS_DIR.exists():
        print(f"Error: assets directory not found: {ASSETS_DIR}")
        sys.exit(1)

    if args.set:
        json_files = [ASSETS_DIR / f"{args.set}.json"]
        if not json_files[0].exists():
            print(f"Error: card set not found: {json_files[0]}")
            sys.exit(1)
    else:
        json_files = sorted(ASSETS_DIR.glob("*.json"))

    if not json_files:
        print("No card set files found in assets/nfc/")
        sys.exit(0)

    # Check OpenMoji availability
    openmoji_dir = args.openmoji if args.openmoji.exists() else None
    if not openmoji_dir and not args.dry_run:
        print(f"Warning: OpenMoji directory not found at {args.openmoji}")
        print("         Cards will show Unicode codepoints instead of emoji.")
        print(
            "         To fix: git clone --depth 1 https://github.com/hfg-gmuend/openmoji.git ~/openmoji"
        )
        print()

    for json_file in json_files:
        card_set = load_card_set(json_file)
        mode = card_set["mode"]
        cards = card_set["cards"]
        dims = card_set.get("dimensions", [])

        print(f"\n{mode}: {len(cards)} cards, dimensions: {', '.join(dims)}")

        if args.dry_run:
            for card in cards:
                labels = f"{card.get('label_sv', '')} / {card.get('label_en', '')}"
                colour = card.get("colour", "-")
                print(
                    f"  {card['id']:20s}  {labels:20s}  colour={colour:8s}  icon=U+{card.get('icon', '?')}"
                )
            continue

        output_path = args.output / f"{mode}_cards.pdf"
        print(f"  Generating {output_path} ...")
        generate_pdf(card_set, openmoji_dir, output_path)
        print(f"  Done: {output_path}")

    if not args.dry_run:
        print(f"\nAll PDFs saved to {args.output}/")


if __name__ == "__main__":
    main()
