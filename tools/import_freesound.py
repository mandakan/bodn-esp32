#!/usr/bin/env python3
"""
Parse a Freesound bookmark-category license file and:
  1. Append new entries to assets/audio/sources.tsv (skipping duplicates).
  2. Print stub JSON entries for soundboard.json so you can paste them in.

Usage:
  uv run python tools/import_freesound.py path/to/license.txt
  uv run python tools/import_freesound.py path/to/license.txt --dry-run
  uv run python tools/import_freesound.py path/to/license.txt --stubs-only

Workflow:
  1. Run this script on the downloaded license.txt.
  2. Drop the audio files (original names, no renaming) into
     assets/audio/source/soundboard/  — for soundboard sounds, or
     assets/audio/source/sfx/         — renamed to a logical name (e.g. click.wav)
     assets/audio/source/music/       — renamed to a logical name
  3. For soundboard sounds: paste the printed stubs into soundboard.json,
     assign each to the right bank slot, and fill in the sv/en labels.
  4. Run: uv run python tools/convert_audio.py
"""

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SOURCES_TSV = REPO_ROOT / "assets" / "audio" / "sources.tsv"
SOUNDBOARD_JSON = REPO_ROOT / "assets" / "audio" / "soundboard.json"

# Maps the license strings Freesound uses to the short canonical form we store.
_LICENSE_MAP = {
    "creative commons 0": "CC0",
    "cc0": "CC0",
    "attribution": "CC-BY 4.0",
    "attribution noncommercial": "CC-BY-NC 4.0",
}


def _normalise_license(raw: str) -> str:
    return _LICENSE_MAP.get(raw.strip().lower(), raw.strip())


def _strip_double_ext(filename: str) -> str:
    """Remove a duplicated extension that Freesound appends in license files.

    'foo.mp3.mp3' -> 'foo.mp3'   'bar.wav.wav' -> 'bar.wav'   'baz.mp3' -> 'baz.mp3'
    """
    p = Path(filename)
    if p.suffix and Path(p.stem).suffix == p.suffix:
        return p.stem
    return filename


def parse_license_file(text: str) -> list[dict]:
    """
    Return a list of dicts with keys: filename, url, license, attribution.

    The Freesound license file format for each sound is:
      * {filename}
        * url: {url}
        * license: {license}
    """
    sounds = []
    # Split on sound entry lines (two leading spaces + "* ")
    blocks = re.split(r"\n  \* ", text)
    for block in blocks[1:]:  # first element is the header
        lines = block.strip().splitlines()
        if not lines:
            continue
        filename = lines[0].strip()

        url = ""
        license_str = ""
        for line in lines[1:]:
            m = re.match(r"\s*\*\s+url:\s*(.+)", line)
            if m:
                url = m.group(1).strip()
            m = re.match(r"\s*\*\s+license:\s*(.+)", line)
            if m:
                license_str = _normalise_license(m.group(1))

        # Freesound's bookmark license file doubles the extension (foo.mp3.mp3).
        # Strip the duplicate so the filename matches what's actually on disk.
        filename = _strip_double_ext(filename)

        # Username is the second __-separated part of the filename.
        # e.g. "848472__elevatorfan2020__vintage-debris-smash.mp3"
        parts = filename.split("__")
        if len(parts) >= 2:
            username = parts[1]
            profile_url = f"https://freesound.org/people/{username}/"
            attribution = f"{username} ({profile_url})"
        else:
            attribution = ""

        if filename and url:
            sounds.append(
                {
                    "filename": filename,
                    "url": url,
                    "license": license_str,
                    "attribution": attribution,
                }
            )

    return sounds


def load_existing_urls(tsv_path: Path) -> set[str]:
    if not tsv_path.exists():
        return set()
    urls = set()
    with open(tsv_path) as f:
        for i, line in enumerate(f):
            if i == 0:
                continue  # header
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and parts[1]:
                urls.add(parts[1].strip())
    return urls


def _already_in_soundboard(filename: str) -> bool:
    """Return True if this source filename is already referenced in soundboard.json."""
    if not SOUNDBOARD_JSON.exists():
        return False
    try:
        with open(SOUNDBOARD_JSON) as f:
            sb = json.load(f)
    except Exception:
        return False

    needle = f"soundboard/{filename}"
    for bank_val in sb.get("banks", {}).values():
        for slot_val in bank_val.get("slots", {}).values():
            if isinstance(slot_val, dict) and slot_val.get("source") == needle:
                return True
    for slot_val in sb.get("arcade", {}).values():
        if isinstance(slot_val, dict) and slot_val.get("source") == needle:
            return True
    return False


def print_soundboard_stubs(sounds: list[dict]) -> None:
    """Print ready-to-paste JSON slot stubs for soundboard.json."""
    unassigned = [s for s in sounds if not _already_in_soundboard(s["filename"])]
    if not unassigned:
        print("\nAll sounds already referenced in soundboard.json.")
        return

    print(
        f"\n── Soundboard stubs ({len(unassigned)} unassigned) ──────────────────────────\n"
        "Paste into the desired bank's 'slots' in assets/audio/soundboard.json.\n"
        "Fill in 'sv' and 'en' labels and assign sequential slot numbers (0–7).\n"
    )
    for s in unassigned:
        stub = {
            "sv": "",
            "en": "",
            "source": f"soundboard/{s['filename']}",
        }
        inner = json.dumps(stub, ensure_ascii=False)
        print(f'        "N": {inner},')


def main():
    parser = argparse.ArgumentParser(
        description="Import Freesound license file into sources.tsv and print soundboard stubs"
    )
    parser.add_argument(
        "license_file", help="Path to the Freesound bookmark license .txt file"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print rows without writing to sources.tsv",
    )
    parser.add_argument(
        "--stubs-only",
        action="store_true",
        help="Only print soundboard stubs, skip sources.tsv",
    )
    args = parser.parse_args()

    license_path = Path(args.license_file)
    if not license_path.exists():
        sys.exit(f"ERROR: file not found: {license_path}")

    text = license_path.read_text(encoding="utf-8", errors="replace")
    sounds = parse_license_file(text)

    if not sounds:
        sys.exit("No sound entries found — is this a Freesound bookmark license file?")

    if not args.stubs_only:
        existing_urls = load_existing_urls(SOURCES_TSV)
        new_sounds = [s for s in sounds if s["url"] not in existing_urls]

        if not new_sounds:
            print(f"All {len(sounds)} entries already in sources.tsv.")
        else:
            print(f"Adding {len(new_sounds)} of {len(sounds)} entries to sources.tsv:")
            for s in new_sounds:
                print(f"  {s['filename']}")

            if not args.dry_run:
                with open(SOURCES_TSV, "a", encoding="utf-8") as f:
                    for s in new_sounds:
                        row = "\t".join(
                            [
                                s["filename"],
                                s["url"],
                                s["license"],
                                s["attribution"],
                                "",
                            ]
                        )
                        f.write(row + "\n")
                print(f"Written to {SOURCES_TSV.relative_to(REPO_ROOT)}")
            else:
                print("--dry-run: sources.tsv not modified.")

    print_soundboard_stubs(sounds)

    if not args.stubs_only and not args.dry_run:
        print(
            "\nNext steps:\n"
            "  1. Drop downloaded files into assets/audio/source/soundboard/ (no renaming)\n"
            "     or into sfx/ / music/ with a logical name (e.g. click.wav)\n"
            "  2. Paste stubs above into soundboard.json, set slot numbers and labels\n"
            "  3. uv run python tools/convert_audio.py"
        )


if __name__ == "__main__":
    main()
