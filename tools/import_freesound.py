#!/usr/bin/env python3
"""
Parse a Freesound bookmark-category license file and append new entries to
assets/audio/sources.tsv, skipping any URLs already present.

Usage:
  uv run python tools/import_freesound.py path/to/license.txt
  uv run python tools/import_freesound.py path/to/license.txt --dry-run
"""

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SOURCES_TSV = REPO_ROOT / "assets" / "audio" / "sources.tsv"

# Maps the license strings Freesound uses to the short canonical form we store.
_LICENSE_MAP = {
    "creative commons 0": "CC0",
    "cc0": "CC0",
    "attribution": "CC-BY 4.0",
    "attribution noncommercial": "CC-BY-NC 4.0",
}


def _normalise_license(raw: str) -> str:
    return _LICENSE_MAP.get(raw.strip().lower(), raw.strip())


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

        # Username is the second __-separated part of the filename.
        # e.g. "848472__elevatorfan2020__vintage-debris-smash.mp3.mp3"
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


def main():
    parser = argparse.ArgumentParser(
        description="Import Freesound license file into sources.tsv"
    )
    parser.add_argument(
        "license_file", help="Path to the Freesound bookmark license .txt file"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print rows without writing"
    )
    args = parser.parse_args()

    license_path = Path(args.license_file)
    if not license_path.exists():
        sys.exit(f"ERROR: file not found: {license_path}")

    text = license_path.read_text(encoding="utf-8", errors="replace")
    sounds = parse_license_file(text)

    if not sounds:
        sys.exit("No sound entries found — is this a Freesound bookmark license file?")

    existing_urls = load_existing_urls(SOURCES_TSV)
    new_sounds = [s for s in sounds if s["url"] not in existing_urls]

    if not new_sounds:
        print(f"All {len(sounds)} entries already in sources.tsv — nothing to add.")
        return

    print(f"Found {len(sounds)} entries, {len(new_sounds)} new:")
    for s in new_sounds:
        print(f"  {s['filename']}")
        print(f"    url:         {s['url']}")
        print(f"    license:     {s['license']}")
        print(f"    attribution: {s['attribution']}")

    if args.dry_run:
        print("\n--dry-run: sources.tsv not modified.")
        return

    with open(SOURCES_TSV, "a", encoding="utf-8") as f:
        for s in new_sounds:
            row = "\t".join(
                [s["filename"], s["url"], s["license"], s["attribution"], ""]
            )
            f.write(row + "\n")

    print(f"\nAppended {len(new_sounds)} rows to {SOURCES_TSV.relative_to(REPO_ROOT)}")
    print(
        "Remember to add the downloaded files to assets/audio/source/ and run convert_audio.py."
    )


if __name__ == "__main__":
    main()
