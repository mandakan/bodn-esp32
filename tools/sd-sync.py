#!/usr/bin/env python3
"""
Build and sync SD card assets for Bodn ESP32.

Combines the TTS generation + audio conversion pipeline into a single command,
then copies the resulting files to a mounted SD card (or any target directory).

Usage:
  # Build all SD assets (generate TTS + convert audio), then sync to SD card
  uv run python tools/sd-sync.py /Volumes/BODN_SD

  # Build only (no copy)
  uv run python tools/sd-sync.py --build-only

  # Sync previously built assets without rebuilding
  uv run python tools/sd-sync.py --no-build /Volumes/BODN_SD

  # Preview what would be synced
  uv run python tools/sd-sync.py --dry-run /Volumes/BODN_SD

  # Force rebuild everything
  uv run python tools/sd-sync.py --force /Volumes/BODN_SD

  # Auto-detect SD card (looks for /Volumes/BODN* on macOS)
  uv run python tools/sd-sync.py
"""

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
BUILD_DIR = REPO_ROOT / "build"
TOOLS_DIR = REPO_ROOT / "tools"

# SD card asset sources (build output → SD card subdirectory)
SD_ASSETS = [
    # (source dir relative to repo, destination dir relative to SD root)
    (BUILD_DIR / "sounds", "sounds"),
    (BUILD_DIR / "tts_converted", "sounds/tts"),
]


def find_sd_card() -> Path | None:
    """Auto-detect a mounted SD card on macOS."""
    if platform.system() != "Darwin":
        return None
    volumes = Path("/Volumes")
    if not volumes.exists():
        return None
    for vol in sorted(volumes.iterdir()):
        if vol.name.upper().startswith("BODN"):
            return vol
    return None


def run_tool(script: str, extra_args: list[str] | None = None) -> bool:
    """Run a Python tool script, returning True on success."""
    cmd = [sys.executable, str(TOOLS_DIR / script)] + (extra_args or [])
    print(f"\n{'=' * 60}")
    print(f"Running: {' '.join(cmd)}")
    print(f"{'=' * 60}\n")
    result = subprocess.run(cmd)
    return result.returncode == 0


def build_sd_assets(force: bool = False) -> bool:
    """Run the full SD asset build pipeline."""
    ok = True

    # Step 1: Generate TTS audio from i18n strings
    print("\n>>> Step 1/3: Generate TTS audio")
    if not run_tool("generate_tts.py"):
        print("WARNING: TTS generation had errors (continuing anyway)")
        ok = False

    # Step 2: Generate story TTS audio from story scripts
    print("\n>>> Step 2/3: Generate story TTS audio")
    if not run_tool("generate_story_tts.py"):
        print("WARNING: Story TTS generation had errors (continuing anyway)")
        ok = False

    # Step 3: Convert all audio (includes SD TTS staging → build/tts_converted/)
    print("\n>>> Step 3/3: Convert audio assets")
    extra = ["--force"] if force else []
    if not run_tool("convert_audio.py", extra):
        print("WARNING: Audio conversion had errors (continuing anyway)")
        ok = False

    return ok


def sync_to_target(target: Path, dry_run: bool = False) -> int:
    """Copy built SD assets to the target directory. Returns number of files copied."""
    copied = 0

    for src_dir, dest_rel in SD_ASSETS:
        if not src_dir.exists():
            print(f"  skip  {src_dir.relative_to(REPO_ROOT)} (not built yet)")
            continue

        dest_dir = target / dest_rel

        for src_file in sorted(src_dir.rglob("*")):
            if not src_file.is_file():
                continue
            # Skip hidden files
            if any(part.startswith(".") for part in src_file.parts):
                continue

            rel = src_file.relative_to(src_dir)
            dst_file = dest_dir / rel

            # Skip if destination is already up-to-date
            if (
                dst_file.exists()
                and dst_file.stat().st_size == src_file.stat().st_size
                and dst_file.stat().st_mtime >= src_file.stat().st_mtime
            ):
                continue

            if dry_run:
                print(f"  would copy  {rel}  →  {dest_rel}/{rel}")
            else:
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
                kib = dst_file.stat().st_size // 1024
                print(f"  copied  {rel}  →  {dest_rel}/{rel}  ({kib} KiB)")
            copied += 1

    return copied


def main():
    parser = argparse.ArgumentParser(
        description="Build and sync SD card assets for Bodn ESP32"
    )
    parser.add_argument(
        "target",
        nargs="?",
        help="SD card mount point or target directory (auto-detects /Volumes/BODN* on macOS)",
    )
    parser.add_argument(
        "--build-only",
        action="store_true",
        help="Build assets without copying to SD card",
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="Skip build, only sync previously built assets",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be built and copied",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force rebuild all assets even if up-to-date",
    )
    args = parser.parse_args()

    if args.build_only and args.no_build:
        sys.exit("ERROR: --build-only and --no-build are mutually exclusive")

    # --- Build phase ---
    if not args.no_build:
        if args.dry_run:
            print("Build phase: would run generate_tts.py + convert_audio.py")
        else:
            if not build_sd_assets(force=args.force):
                print("\nBuild completed with warnings (see above)")

    if args.build_only:
        print("\nDone (build only). Use --no-build to sync without rebuilding.")
        return

    # --- Resolve target ---
    target = None
    if args.target:
        target = Path(args.target)
    else:
        target = find_sd_card()
        if target:
            print(f"\nAuto-detected SD card: {target}")

    if target is None:
        print("\nNo SD card target specified or detected.")
        print("  Usage: uv run python tools/sd-sync.py /Volumes/BODN_SD")
        print("  Tip:   name your SD card 'BODN' for auto-detection on macOS")
        if args.no_build:
            sys.exit(1)
        else:
            print(
                "\nBuild completed. Insert SD card and re-run with --no-build to sync."
            )
            return

    if not target.exists():
        sys.exit(f"ERROR: target path does not exist: {target}")

    # --- Sync phase ---
    print(f"\n{'=' * 60}")
    label = "Previewing" if args.dry_run else "Syncing"
    print(f"{label} SD assets → {target}")
    print(f"{'=' * 60}")

    copied = sync_to_target(target, dry_run=args.dry_run)

    if copied == 0:
        print("\nAll SD assets are up-to-date.")
    elif args.dry_run:
        print(f"\nWould copy {copied} file(s).")
    else:
        print(f"\nCopied {copied} file(s) to {target}")
        # macOS: remind to eject
        if platform.system() == "Darwin":
            print("\nRemember to eject the SD card before removing it:")
            print(f"  diskutil eject {target}")


if __name__ == "__main__":
    main()
