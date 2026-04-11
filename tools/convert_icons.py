#!/usr/bin/env python3
"""
Convert OpenMoji SVGs to Bodn Draw Format (.bdf) sprite files for on-screen use.

Reads the emoji manifest (assets/images/emoji_manifest.json), locates each
OpenMoji SVG by Unicode codepoint, and converts to BDF sprites via the
existing make_asset.py rasterizer.

Usage:
  # Convert all icons (requires OpenMoji SVGs)
  uv run python tools/convert_icons.py --openmoji ~/openmoji

  # Preview without converting
  uv run python tools/convert_icons.py --dry-run

  # Force rebuild all
  uv run python tools/convert_icons.py --openmoji ~/openmoji --force

Setup:
  git clone --depth 1 https://github.com/hfg-gmuend/openmoji.git ~/openmoji
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
MANIFEST_PATH = REPO_ROOT / "assets" / "images" / "emoji_manifest.json"
BUILD_DIR = REPO_ROOT / "build" / "sprites"

# make_asset.py lives in the same directory
sys.path.insert(0, str(REPO_ROOT / "tools"))
from make_asset import rasterize_image  # noqa: E402


def find_svg(codepoint: str, openmoji_dir: Path) -> Path | None:
    """Find an OpenMoji SVG file by Unicode codepoint."""
    for variant in (codepoint.upper(), codepoint.lower()):
        svg = openmoji_dir / "svg" / "color" / f"{variant}.svg"
        if svg.exists():
            return svg
    return None


def load_manifest() -> dict:
    """Load and validate the emoji manifest."""
    with open(MANIFEST_PATH) as f:
        data = json.load(f)
    if "icons" not in data:
        raise ValueError(f"Missing 'icons' in {MANIFEST_PATH}")
    return data


def convert_icons(
    openmoji_dir: Path | None,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    """Convert all manifest icons to BDF. Returns (converted, skipped, missing)."""
    manifest = load_manifest()
    default_bpp = manifest.get("default_bpp", 4)
    default_size = manifest.get("default_size", 48)

    converted = 0
    skipped = 0
    missing = 0

    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    for icon in manifest["icons"]:
        name = icon["name"]
        codepoint = icon["codepoint"]
        size = icon.get("size", default_size)
        bpp = icon.get("bpp", default_bpp)
        label = icon.get("label", "")

        out_name = f"emoji_{name}_{size}.bdf"
        out_path = BUILD_DIR / out_name

        if dry_run:
            status = "exists" if out_path.exists() else "new"
            print(f"  {status:8s}  {out_name:36s}  U+{codepoint:5s}  {label}")
            continue

        if openmoji_dir is None:
            missing += 1
            continue

        svg_path = find_svg(codepoint, openmoji_dir)
        if svg_path is None:
            print(f"  missing   {out_name}  (U+{codepoint} not found)")
            missing += 1
            continue

        # Up-to-date check
        if (
            not force
            and out_path.exists()
            and out_path.stat().st_mtime >= svg_path.stat().st_mtime
        ):
            skipped += 1
            continue

        # Convert SVG → BDF
        try:
            blob = rasterize_image(str(svg_path), size, bpp)
            out_path.write_bytes(blob)
            converted += 1
            print(f"  convert   {out_name} ({len(blob)} bytes)")
        except Exception as e:
            print(f"  ERROR     {out_name}: {e}")
            missing += 1

    return converted, skipped, missing


def main():
    parser = argparse.ArgumentParser(
        description="Convert OpenMoji SVGs to BDF sprites for on-screen display.",
    )
    parser.add_argument(
        "--openmoji",
        type=Path,
        default=Path.home() / "openmoji",
        help="Path to OpenMoji repository (default: ~/openmoji)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List icons without converting",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force rebuild all icons",
    )
    args = parser.parse_args()

    manifest = load_manifest()
    icons = manifest["icons"]
    print(f"Emoji manifest: {len(icons)} icons")

    openmoji_dir = args.openmoji if args.openmoji.exists() else None
    if not openmoji_dir and not args.dry_run:
        print(f"Warning: OpenMoji directory not found at {args.openmoji}")
        print(
            "  To fix: git clone --depth 1 https://github.com/hfg-gmuend/openmoji.git ~/openmoji"
        )
        return

    converted, skipped, missing = convert_icons(
        openmoji_dir, force=args.force, dry_run=args.dry_run
    )

    if not args.dry_run:
        print(f"\nDone: {converted} converted, {skipped} up-to-date, {missing} missing")


if __name__ == "__main__":
    main()
