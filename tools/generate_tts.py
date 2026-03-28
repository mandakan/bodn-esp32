#!/usr/bin/env python3
"""
TTS audio asset generator for Bodn ESP32.

Reads assets/audio/tts.json (key allowlist + voice config), pulls text from
firmware/bodn/lang/{sv,en}.py STRINGS dicts, and generates WAV files via Piper TTS.

Flash keys → assets/audio/source/tts/{lang}/{key}.wav  (picked up by convert_audio.py)
SD keys    → build/tts/{lang}/{key}.wav                 (copy to SD card after converting)

Voice models are downloaded automatically to ~/.cache/piper/ on first use.

Incremental: text hashes cached in assets/audio/tts_hashes.json — unchanged
keys are skipped unless --force is given.

Keys whose i18n text contains {} format placeholders are skipped automatically
(spoken audio cannot contain variable content).

Usage:
  uv run python tools/generate_tts.py
  uv run python tools/generate_tts.py --dry-run
  uv run python tools/generate_tts.py --force
  uv run python tools/generate_tts.py --lang sv
  uv run python tools/generate_tts.py --key simon_watch
"""

import argparse
import hashlib
import json
import sys
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
FIRMWARE_DIR = REPO_ROOT / "firmware"
ASSETS_AUDIO = REPO_ROOT / "assets" / "audio"
TTS_JSON = ASSETS_AUDIO / "tts.json"
HASHES_JSON = ASSETS_AUDIO / "tts_hashes.json"
FLASH_SOURCE_DIR = ASSETS_AUDIO / "source" / "tts"
SD_STAGING_DIR = REPO_ROOT / "build" / "tts"
VOICES_DIR = Path.home() / ".cache" / "piper"

# Add firmware/ to sys.path so we can import bodn.lang.{sv,en}
sys.path.insert(0, str(FIRMWARE_DIR))


def load_manifest():
    if not TTS_JSON.exists():
        sys.exit(f"ERROR: {TTS_JSON} not found.")
    with open(TTS_JSON) as f:
        return json.load(f)


def load_strings(lang):
    """Import STRINGS dict for the given language from firmware/bodn/lang/."""
    if lang == "sv":
        from bodn.lang.sv import STRINGS
    elif lang == "en":
        from bodn.lang.en import STRINGS
    else:
        sys.exit(f"ERROR: Unknown language '{lang}'")
    return STRINGS


def load_hashes():
    if HASHES_JSON.exists():
        with open(HASHES_JSON) as f:
            return json.load(f)
    return {}


def save_hashes(hashes):
    HASHES_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(HASHES_JSON, "w") as f:
        json.dump(hashes, f, indent=2, ensure_ascii=False)
        f.write("\n")


def text_hash(text):
    return hashlib.md5(text.encode()).hexdigest()[:12]


def ensure_voice(model_name):
    """Download voice model if not already cached. Returns loaded PiperVoice."""
    from piper.download_voices import download_voice
    from piper.voice import PiperVoice

    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    model_path = VOICES_DIR / f"{model_name}.onnx"

    if not model_path.exists():
        print(f"  downloading voice {model_name} → {VOICES_DIR}/")
        download_voice(model_name, VOICES_DIR)

    return PiperVoice.load(model_path)


def generate_one(key, text, voice, out_path, dry_run):
    """Synthesize text to a WAV file using a loaded PiperVoice. Returns True on success."""
    if dry_run:
        print(f"  would generate  {out_path.relative_to(REPO_ROOT)}")
        return True
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with wave.open(str(out_path), "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)
    except Exception as exc:
        print(f"  ERROR  {key}: {exc}", file=sys.stderr)
        return False
    kib = out_path.stat().st_size // 1024
    print(f"  generated  {out_path.relative_to(REPO_ROOT)}  ({kib} KiB)")
    return True


def main():
    parser = argparse.ArgumentParser(description="Generate TTS audio for Bodn ESP32")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without generating",
    )
    parser.add_argument(
        "--force", action="store_true", help="Regenerate even if text is unchanged"
    )
    parser.add_argument(
        "--lang", metavar="LANG", help="Only generate for this language (sv or en)"
    )
    parser.add_argument("--key", metavar="KEY", help="Only generate for this i18n key")
    args = parser.parse_args()

    manifest = load_manifest()
    voices_cfg = manifest["voices"]
    keys = manifest["keys"]
    overrides = manifest.get("overrides", {})

    hashes = load_hashes()
    new_hashes = dict(hashes)

    langs = [args.lang] if args.lang else list(voices_cfg.keys())
    filter_key = args.key

    generated = skipped = errors = 0

    for lang in langs:
        if lang not in voices_cfg:
            print(f"WARNING: lang '{lang}' not in manifest voices — skipping.")
            continue
        model_name = voices_cfg[lang]["model"]
        strings = load_strings(lang)
        lang_overrides = overrides.get(lang, {})

        print(f"\n=== TTS {lang.upper()} ({model_name}) ===")

        voice = None  # loaded lazily so --dry-run never downloads

        for key, meta in keys.items():
            if filter_key and key != filter_key:
                continue

            # Resolve text: per-language override takes priority over i18n strings
            if key in lang_overrides:
                text = lang_overrides[key]
            elif key in strings:
                text = strings[key]
            else:
                print(f"  skip  {key}  (not in {lang} strings)")
                continue

            # Keys with format placeholders cannot be spoken verbatim
            if "{" in text:
                print(f"  skip  {key}  (contains placeholder: {text!r})")
                continue

            storage = meta.get("storage", "sd")
            if storage == "flash":
                out_path = FLASH_SOURCE_DIR / lang / f"{key}.wav"
            else:
                out_path = SD_STAGING_DIR / lang / f"{key}.wav"

            # Incremental: skip if text hash unchanged and output exists
            hash_key = f"{lang}/{key}"
            h = text_hash(text)
            if not args.force and hashes.get(hash_key) == h and out_path.exists():
                skipped += 1
                continue

            if not args.dry_run and voice is None:
                voice = ensure_voice(model_name)

            ok = generate_one(key, text, voice, out_path, args.dry_run)
            if ok:
                generated += 1
                if not args.dry_run:
                    new_hashes[hash_key] = h
            else:
                errors += 1

    if not args.dry_run and new_hashes != hashes:
        save_hashes(new_hashes)

    label = "Would generate" if args.dry_run else "Generated"
    print(f"\n{label}: {generated}  |  Up-to-date: {skipped}  |  Errors: {errors}")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
