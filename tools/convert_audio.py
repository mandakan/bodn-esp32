#!/usr/bin/env python3
"""
Audio asset conversion pipeline for Bodn ESP32.

Source (high-quality) files live in assets/audio/source/:
  soundboard/bank_N/   — numbered slot files for each bank (0.wav – 7.wav)
  soundboard/arcade/   — shared arcade button sounds (0.wav – 4.wav)
  sfx/                 — UI and game sound effects
  music/               — background music

Converted device-ready files (16 kHz mono PCM) go to firmware/sounds/.
This directory is committed; source/ is not (re-download CC0 via sources.tsv,
commit your own recordings with git add -f or via git-lfs).

The soundboard manifest (firmware/sounds/manifest.json) is generated from
assets/audio/soundboard.json — never edit the device manifest by hand.

Usage:
  uv run python tools/convert_audio.py            # convert everything
  uv run python tools/convert_audio.py --dry-run  # show what would be done
  uv run python tools/convert_audio.py --force    # reconvert even if up-to-date
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
ASSETS_DIR = REPO_ROOT / "assets" / "audio"
SOURCE_DIR = ASSETS_DIR / "source"
SOUNDBOARD_JSON = ASSETS_DIR / "soundboard.json"
FIRMWARE_SOUNDS = REPO_ROOT / "firmware" / "sounds"
DEVICE_MANIFEST = FIRMWARE_SOUNDS / "manifest.json"

# Target device format
FFMPEG_CONVERT = [
    "-ar",
    "16000",
    "-ac",
    "1",
    "-sample_fmt",
    "s16",
    "-acodec",
    "pcm_s16le",
]

_converted = 0
_skipped = 0
_missing = 0
_errors = 0


def check_ffmpeg():
    if not shutil.which("ffmpeg"):
        sys.exit("ERROR: ffmpeg not found. Install it: brew install ffmpeg")


def _convert_file(src: Path, dst: Path, dry_run: bool, force: bool) -> str:
    """
    Convert src → dst.  Returns 'converted', 'skipped', 'missing', or 'error'.
    """
    global _converted, _skipped, _missing, _errors

    if not src.exists():
        print(f"  missing   {src.relative_to(REPO_ROOT)}")
        _missing += 1
        return "missing"

    if not force and dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        _skipped += 1
        return "skipped"

    rel_src = src.relative_to(REPO_ROOT)
    rel_dst = dst.relative_to(REPO_ROOT)
    if dry_run:
        print(f"  would convert  {rel_src}  →  {rel_dst}")
        _converted += 1
        return "converted"

    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = (
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src)]
        + FFMPEG_CONVERT
        + [str(dst)]
    )
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        err = result.stderr.decode(errors="replace").strip()[-300:]
        print(f"  ERROR  {src.name}: {err}", file=sys.stderr)
        _errors += 1
        return "error"

    kib = dst.stat().st_size // 1024
    print(f"  converted  {rel_src}  →  {rel_dst}  ({kib} KiB)")
    _converted += 1
    return "converted"


def process_soundboard(dry_run: bool, force: bool):
    """Convert soundboard source files and regenerate firmware/sounds/manifest.json."""
    if not SOUNDBOARD_JSON.exists():
        print("assets/audio/soundboard.json not found — skipping soundboard.")
        return

    with open(SOUNDBOARD_JSON) as f:
        raw = f.read()
    # Strip trailing commas before closing braces/brackets — JSON doesn't allow
    # them, but they're easy to leave when pasting stubs.
    raw = re.sub(r",(\s*[}\]])", r"\1", raw)
    try:
        sb = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.exit(f"ERROR: soundboard.json is not valid JSON: {e}")

    manifest_banks = {}

    # --- Banks ---
    for bank_key, bank_val in sb.get("banks", {}).items():
        try:
            bank_idx = int(bank_key)
        except (ValueError, TypeError):
            continue

        # Build the device manifest entry: keep display fields, drop 'source'.
        manifest_bank = {}
        for field in ("name", "name_sv", "name_en", "color"):
            if bank_val.get(field):
                manifest_bank[field] = bank_val[field]

        manifest_slots = {}
        for slot_key, slot_val in bank_val.get("slots", {}).items():
            try:
                slot_idx = int(slot_key)
            except (ValueError, TypeError):
                continue

            # Convert source WAV if specified
            src_rel = slot_val.get("source") if isinstance(slot_val, dict) else None
            if src_rel:
                src = SOURCE_DIR / src_rel
                dst = FIRMWARE_SOUNDS / f"bank_{bank_idx}" / f"{slot_idx}.wav"
                _convert_file(src, dst, dry_run, force)

            # Collect non-empty display labels for the manifest
            if isinstance(slot_val, dict):
                label = {k: v for k, v in slot_val.items() if k != "source" and v}
                if label:
                    manifest_slots[slot_key] = label
            elif isinstance(slot_val, str) and slot_val:
                manifest_slots[slot_key] = slot_val

        if manifest_slots:
            manifest_bank["slots"] = manifest_slots
        manifest_banks[bank_key] = manifest_bank

    # --- Arcade ---
    for slot_key, slot_val in sb.get("arcade", {}).items():
        try:
            slot_idx = int(slot_key)
        except (ValueError, TypeError):
            continue

        src_rel = slot_val.get("source") if isinstance(slot_val, dict) else None
        if src_rel:
            src = SOURCE_DIR / src_rel
            dst = FIRMWARE_SOUNDS / "arcade" / f"{slot_idx}.wav"
            _convert_file(src, dst, dry_run, force)

    # --- Write device manifest ---
    manifest = {"banks": manifest_banks}
    if dry_run:
        print(f"  would write  firmware/sounds/manifest.json")
    else:
        DEVICE_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        with open(DEVICE_MANIFEST, "w") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"  wrote  firmware/sounds/manifest.json")


def process_directory(category: str, dry_run: bool, force: bool):
    """Convert all WAVs in assets/audio/source/<category>/."""
    src_dir = SOURCE_DIR / category
    if not src_dir.exists():
        print(f"  assets/audio/source/{category}/ not found — skipping.")
        return

    wavs = sorted(src_dir.rglob("*.wav"))
    if not wavs:
        print(f"  no WAV files in assets/audio/source/{category}/")
        return

    dst_dir = FIRMWARE_SOUNDS / category
    for src in wavs:
        rel = src.relative_to(src_dir)
        dst = dst_dir / rel
        _convert_file(src, dst, dry_run, force)


def print_summary(dry_run: bool):
    label = "Would convert" if dry_run else "Converted"
    print(
        f"\n{label}: {_converted}  |  Up-to-date: {_skipped}  |  Missing source: {_missing}  |  Errors: {_errors}"
    )
    if _errors:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Convert audio assets for Bodn ESP32")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be converted without doing it",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reconvert even if output is already up-to-date",
    )
    args = parser.parse_args()

    check_ffmpeg()

    print("=== Soundboard ===")
    process_soundboard(args.dry_run, args.force)

    print("\n=== SFX ===")
    process_directory("sfx", args.dry_run, args.force)

    print("\n=== Music ===")
    process_directory("music", args.dry_run, args.force)

    print_summary(args.dry_run)


if __name__ == "__main__":
    main()
