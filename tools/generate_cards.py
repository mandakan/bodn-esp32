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
import os
import sys
from io import BytesIO
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
ASSETS_DIR = REPO_ROOT / "assets" / "nfc"
BUILD_DIR = REPO_ROOT / "build" / "cards"


def _resolve_openmoji(explicit: Path | None = None) -> Path | None:
    """Resolve OpenMoji dir from explicit path, $OPENMOJI_DIR, or ~/openmoji."""
    candidates = []
    if explicit is not None:
        candidates.append(explicit)
    env = os.environ.get("OPENMOJI_DIR")
    if env:
        candidates.append(Path(env))
    candidates.append(Path.home() / "openmoji")
    for path in candidates:
        if path.exists():
            return path
    return None


# Card dimensions in mm — sized for 54×86 mm lamination pockets.
# Leave ~3 mm clear plastic on each side for the heat seal.
CARD_W = 48
CARD_H = 80

# A4 page dimensions in mm
PAGE_W = 210
PAGE_H = 297

# Layout: 4 columns × 3 rows = 12 cards per page
COLS = 4
ROWS = 3
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

# Launcher card frame colour (bold teal frame around white interior)
LAUNCHER_FRAME = (41, 128, 185)
LAUNCHER_FRAME_W = 3  # frame thickness in mm

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
    """Find an OpenMoji SVG file by Unicode codepoint.

    Checks both possible directory layouts:
      {openmoji}/color/svg/{CP}.svg  (default clone structure)
      {openmoji}/svg/color/{CP}.svg  (alternative/older layout)
    """
    for variant in (codepoint.upper(), codepoint.lower()):
        for subpath in ("color/svg", "svg/color"):
            svg = openmoji_dir / subpath / f"{variant}.svg"
            if svg.exists():
                return svg
    return None


def render_emoji_png(svg_path: Path, size_px: int) -> bytes:
    """Rasterise an OpenMoji SVG to PNG bytes at the given size."""
    import cairosvg

    return cairosvg.svg2png(
        url=str(svg_path),
        output_width=size_px,
        output_height=size_px,
    )


def _has_quantity_cards(cards: list[dict]) -> bool:
    """Check if any cards have a quantity field (need dot-pattern backs)."""
    return any("quantity" in c for c in cards)


# Dot positions for each quantity (1-10), normalised to a 0-1 square.
# 1-6 follow standard dice face layouts; 7-10 use structured extensions.
_DOT_POSITIONS: dict[int, list[tuple[float, float]]] = {
    1: [(0.5, 0.5)],
    2: [(0.25, 0.25), (0.75, 0.75)],
    3: [(0.25, 0.25), (0.5, 0.5), (0.75, 0.75)],
    4: [(0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75)],
    5: [(0.25, 0.25), (0.75, 0.25), (0.5, 0.5), (0.25, 0.75), (0.75, 0.75)],
    6: [
        (0.25, 0.2),
        (0.25, 0.5),
        (0.25, 0.8),
        (0.75, 0.2),
        (0.75, 0.5),
        (0.75, 0.8),
    ],
    7: [
        (0.25, 0.2),
        (0.25, 0.5),
        (0.25, 0.8),
        (0.5, 0.5),
        (0.75, 0.2),
        (0.75, 0.5),
        (0.75, 0.8),
    ],
    8: [
        (0.25, 0.15),
        (0.25, 0.38),
        (0.25, 0.62),
        (0.25, 0.85),
        (0.75, 0.15),
        (0.75, 0.38),
        (0.75, 0.62),
        (0.75, 0.85),
    ],
    9: [
        (0.2, 0.2),
        (0.2, 0.5),
        (0.2, 0.8),
        (0.5, 0.2),
        (0.5, 0.5),
        (0.5, 0.8),
        (0.8, 0.2),
        (0.8, 0.5),
        (0.8, 0.8),
    ],
    10: [
        # Ten-frame: two rows of 5
        (0.15, 0.35),
        (0.325, 0.35),
        (0.5, 0.35),
        (0.675, 0.35),
        (0.85, 0.35),
        (0.15, 0.65),
        (0.325, 0.65),
        (0.5, 0.65),
        (0.675, 0.65),
        (0.85, 0.65),
    ],
}

# Dot radius scales down for higher quantities to keep patterns readable
_DOT_RADIUS = {
    1: 4.0,
    2: 3.5,
    3: 3.0,
    4: 2.8,
    5: 2.8,
    6: 2.5,
    7: 2.3,
    8: 2.2,
    9: 2.0,
    10: 1.9,
}


def _draw_dot_pattern(pdf, quantity: int, x: float, y: float, w: float, h: float):
    """Draw a dice-style dot pattern for the given quantity within a rectangle."""
    positions = _DOT_POSITIONS.get(quantity)
    if not positions:
        return

    # Draw dots as filled circles in a padded square area
    pad = 6  # mm padding inside the card area
    area_x = x + pad
    area_y = y + pad
    area_w = w - 2 * pad
    area_h = h - 2 * pad

    r = _DOT_RADIUS.get(quantity, 2.0)
    pdf.set_fill_color(44, 62, 80)  # dark dots

    for dx, dy in positions:
        cx = area_x + dx * area_w
        cy = area_y + dy * area_h
        pdf.ellipse(cx - r, cy - r, 2 * r, 2 * r, style="F")


def _draw_dot_card_back(pdf, card: dict, x: float, y: float):
    """Draw the back face of a quantity card (dot pattern)."""
    quantity = card.get("quantity", 0)
    if quantity < 1:
        return

    # Soft white background
    pdf.set_fill_color(245, 245, 240)
    pdf.rect(x, y, CARD_W, CARD_H, style="F")

    # Border (cutting guide)
    pdf.set_draw_color(*BORDER_COLOUR)
    pdf.set_line_width(0.3)
    pdf.rect(x, y, CARD_W, CARD_H, style="D")

    # Dot pattern in a square area centred in the card
    side = CARD_W - 8  # square side = card width minus padding
    dot_x = x + (CARD_W - side) / 2
    dot_y = y + (CARD_H - side) / 2 - 2  # nudge up slightly for label room
    _draw_dot_pattern(pdf, quantity, dot_x, dot_y, side, side)

    # Quantity as subtle small text at bottom
    pdf.set_font("Helvetica", size=7)
    pdf.set_text_color(180, 180, 180)
    pdf.set_xy(x, y + CARD_H - 10)
    pdf.cell(CARD_W, 5, str(quantity), align="C")


def generate_pdf(card_set: dict, openmoji_dir: Path | None, output_path: Path):
    """Generate an A4 PDF with card faces laid out in a grid.

    For card sets with quantity cards (e.g. räkna), generates double-sided
    pages: front (emoji/numeral) then back (dot pattern), with mirrored
    column order on the back for correct alignment when printed duplex.
    """
    from fpdf import FPDF

    cards = card_set["cards"]
    mode = card_set["mode"]
    double_sided = _has_quantity_cards(cards)

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)

    # Embed a clean sans-serif font if available, else use Helvetica
    pdf.set_font("Helvetica")

    cards_per_page = COLS * ROWS
    total_pages = (len(cards) + cards_per_page - 1) // cards_per_page

    for page_idx in range(total_pages):
        # --- Front page (emoji / numeral) ---
        pdf.add_page()
        start = page_idx * cards_per_page
        page_cards = cards[start : start + cards_per_page]

        for i, card in enumerate(page_cards):
            col = i % COLS
            row = i // COLS

            x = MARGIN_X + col * (CARD_W + MARGIN_X)
            y = MARGIN_Y + row * (CARD_H + MARGIN_Y)

            _draw_card(pdf, card, x, y, mode, openmoji_dir)

        # --- Back page (dot patterns, mirrored columns) ---
        if double_sided:
            quantity_cards = [c for c in page_cards if "quantity" in c]
            if quantity_cards:
                pdf.add_page()
                for i, card in enumerate(page_cards):
                    if "quantity" not in card:
                        continue
                    col = i % COLS
                    row = i // COLS

                    # Mirror columns for duplex printing (flip along long edge)
                    mirrored_col = (COLS - 1) - col
                    x = MARGIN_X + mirrored_col * (CARD_W + MARGIN_X)
                    y = MARGIN_Y + row * (CARD_H + MARGIN_Y)

                    _draw_dot_card_back(pdf, card, x, y)

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
    # Background
    is_launcher = mode == "launcher"
    if is_launcher:
        bg = (255, 255, 255)
    else:
        colour = card.get("colour", "")
        bg = COLOUR_MAP.get(colour, DEFAULT_BG)
    pdf.set_fill_color(*bg)
    pdf.rect(x, y, CARD_W, CARD_H, style="F")

    # Border (cutting guide)
    pdf.set_draw_color(*BORDER_COLOUR)
    pdf.set_line_width(0.3)
    pdf.rect(x, y, CARD_W, CARD_H, style="D")

    if is_launcher:
        # Thick coloured frame + dashed inner border
        fw = LAUNCHER_FRAME_W
        pdf.set_fill_color(*LAUNCHER_FRAME)
        # Top
        pdf.rect(x, y, CARD_W, fw, style="F")
        # Bottom
        pdf.rect(x, y + CARD_H - fw, CARD_W, fw, style="F")
        # Left
        pdf.rect(x, y, fw, CARD_H, style="F")
        # Right
        pdf.rect(x + CARD_W - fw, y, fw, CARD_H, style="F")
        # Dashed inner border
        inset = fw + 1.5
        pdf.set_draw_color(*LAUNCHER_FRAME)
        pdf.set_line_width(0.4)
        pdf.set_dash_pattern(dash=2, gap=1.5)
        pdf.rect(
            x + inset, y + inset, CARD_W - 2 * inset, CARD_H - 2 * inset, style="D"
        )
        pdf.set_dash_pattern()

    # Emoji icon
    icon_codepoint = card.get("icon", "")
    emoji_placed = False
    if openmoji_dir and icon_codepoint:
        svg_path = find_openmoji_svg(icon_codepoint, openmoji_dir)
        if svg_path:
            try:
                png_data = render_emoji_png(svg_path, EMOJI_PX)
                # Place emoji centred in the upper portion of the card
                emoji_mm = 32  # display size in mm
                emoji_x = x + (CARD_W - emoji_mm) / 2
                emoji_y = y + 8
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
        pdf.set_font("Helvetica", "B", size=20)
        pdf.set_text_color(*BORDER_COLOUR)
        pdf.set_xy(x, y + 14)
        pdf.cell(CARD_W, 20, f"U+{icon_codepoint}", align="C")

    # Labels — both languages at equal size (dual-language labeling supports
    # bilingual vocabulary bootstrapping; Tan et al. 2024, Byers-Heinlein 2013)
    # Title-case: uppercase first letter aids recognition, lowercase body maps
    # to real text (Piasta, Treiman & Kessler 2006)
    label_sv = card.get("label_sv", "").capitalize()
    label_en = card.get("label_en", "").capitalize()
    brightness = bg[0] * 0.299 + bg[1] * 0.587 + bg[2] * 0.114
    if brightness > 160:
        pdf.set_text_color(*BORDER_COLOUR)
    else:
        pdf.set_text_color(*LABEL_COLOUR)
    # Swedish label
    pdf.set_font("Helvetica", "B", size=10)
    pdf.set_xy(x, y + 46)
    pdf.cell(CARD_W, 6, label_sv, align="C")
    # English label below
    if label_en:
        pdf.set_font("Helvetica", size=8)
        pdf.set_xy(x, y + 54)
        pdf.cell(CARD_W, 6, label_en, align="C")

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
        default=None,
        help="Path to OpenMoji repository (default: $OPENMOJI_DIR or ~/openmoji)",
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
    openmoji_dir = _resolve_openmoji(args.openmoji)
    if not openmoji_dir and not args.dry_run:
        print("Warning: OpenMoji SVGs not found. Cards will show codepoints instead.")
        print(
            "  Set OPENMOJI_DIR or clone once:\n"
            "    git clone --depth 1 https://github.com/hfg-gmuend/openmoji.git ~/openmoji"
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
