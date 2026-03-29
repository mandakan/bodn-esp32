#!/usr/bin/env python3
"""
TTS audio generator for Bodn Story Mode.

Discovers story scripts from assets/stories/*/script.py, extracts narration
text and choice labels per language, and generates WAV files via Piper TTS.

Scene narration → build/story_tts/{lang}/story_{id}_{node}.wav
Choice labels   → build/story_tts/{lang}/story_{id}_{node}_choices.wav

Incremental: text hashes cached in build/story_tts_hashes.json.

Usage:
  uv run python tools/generate_story_tts.py
  uv run python tools/generate_story_tts.py --dry-run
  uv run python tools/generate_story_tts.py --force
  uv run python tools/generate_story_tts.py --lang sv
  uv run python tools/generate_story_tts.py --story peter_rabbit
"""

import argparse
import hashlib
import json
import sys
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
STORIES_DIR = REPO_ROOT / "assets" / "stories"
OUTPUT_DIR = REPO_ROOT / "build" / "story_tts"
HASHES_JSON = REPO_ROOT / "build" / "story_tts_hashes.json"
VOICES_DIR = Path.home() / ".cache" / "piper"

# Voice config — same models as the main TTS pipeline
VOICES = {
    "sv": {"model": "sv_SE-alma-medium"},
    "en": {"model": "en_US-amy-medium"},
}

# Arcade button names for narrating choices
ARC_BUTTON_NAMES = {
    "sv": ["grön", "blå", "vit", "gul", "röd"],
    "en": ["green", "blue", "white", "yellow", "red"],
}


def discover_stories():
    """Find all story scripts under assets/stories/. Returns list of (id, path)."""
    stories = []
    if not STORIES_DIR.exists():
        return stories
    for entry in sorted(STORIES_DIR.iterdir()):
        script = entry / "script.py"
        if script.exists():
            stories.append((entry.name, script))
    return stories


def load_story(path):
    """Load STORY dict from a script.py file."""
    ns = {}
    exec(path.read_text(), ns)
    return ns["STORY"]


def load_hashes():
    if HASHES_JSON.exists():
        return json.loads(HASHES_JSON.read_text())
    return {}


def save_hashes(hashes):
    HASHES_JSON.parent.mkdir(parents=True, exist_ok=True)
    HASHES_JSON.write_text(json.dumps(hashes, indent=2, ensure_ascii=False) + "\n")


def text_hash(text):
    return hashlib.md5(text.encode()).hexdigest()[:12]


def ensure_voice(model_name):
    """Download voice model if not cached. Returns loaded PiperVoice."""
    from piper.download_voices import download_voice
    from piper.voice import PiperVoice

    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    model_path = VOICES_DIR / f"{model_name}.onnx"
    if not model_path.exists():
        print(f"  downloading voice {model_name} → {VOICES_DIR}/")
        download_voice(model_name, VOICES_DIR)
    return PiperVoice.load(model_path)


def generate_wav(text, voice, out_path, dry_run):
    """Synthesize text to WAV. Returns True on success."""
    if dry_run:
        print(f"  would generate  {out_path.relative_to(REPO_ROOT)}")
        return True
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with wave.open(str(out_path), "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)
    except Exception as exc:
        print(f"  ERROR: {exc}", file=sys.stderr)
        return False
    kib = out_path.stat().st_size // 1024
    print(f"  generated  {out_path.relative_to(REPO_ROOT)}  ({kib} KiB)")
    return True


def build_choices_text(node, lang):
    """Build a sentence that reads out the choice labels.

    E.g. "Press green to go to the garden. Press blue to pick berries."
    """
    choices = node.get("choices", [])
    if not choices:
        return None
    button_names = ARC_BUTTON_NAMES.get(lang, ARC_BUTTON_NAMES["en"])
    if lang == "sv":
        template = "Tryck {} för att {}."
    else:
        template = "Press {} to {}."

    parts = []
    for i, ch in enumerate(choices):
        if i >= len(button_names):
            break
        label = ch.get("label", {})
        text = label.get(lang, label.get("en", ""))
        if text:
            # Lowercase the label for a natural sentence
            parts.append(template.format(button_names[i], text[0].lower() + text[1:]))
    return " ".join(parts) if parts else None


def main():
    parser = argparse.ArgumentParser(description="Generate TTS for Bodn Story Mode")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--lang", metavar="LANG", help="Only this language (sv or en)")
    parser.add_argument("--story", metavar="ID", help="Only this story ID")
    args = parser.parse_args()

    stories = discover_stories()
    if not stories:
        print("No stories found in", STORIES_DIR)
        return

    hashes = load_hashes()
    new_hashes = dict(hashes)
    langs = [args.lang] if args.lang else list(VOICES.keys())

    generated = skipped = errors = 0

    for story_id, story_path in stories:
        if args.story and story_id != args.story:
            continue

        story = load_story(story_path)
        narrate_choices = story.get("narrate_choices", True)
        nodes = story.get("nodes", {})

        print(f"\n=== Story: {story_id} ({len(nodes)} nodes) ===")

        for lang in langs:
            if lang not in VOICES:
                print(f"  WARNING: unknown lang '{lang}' — skipping")
                continue

            model_name = VOICES[lang]["model"]
            voice = None  # lazy load

            print(f"\n  --- {lang.upper()} ({model_name}) ---")

            for node_id, node in nodes.items():
                # Scene narration
                text_dict = node.get("text", {})
                text = text_dict.get(lang, text_dict.get("en", ""))
                if not text:
                    continue

                out_key = f"story_{story_id}_{node_id}"
                out_path = OUTPUT_DIR / lang / f"{out_key}.wav"
                hash_key = f"{lang}/{out_key}"
                h = text_hash(text)

                if not args.force and hashes.get(hash_key) == h and out_path.exists():
                    skipped += 1
                else:
                    if not args.dry_run and voice is None:
                        voice = ensure_voice(model_name)
                    ok = generate_wav(text, voice, out_path, args.dry_run)
                    if ok:
                        generated += 1
                        if not args.dry_run:
                            new_hashes[hash_key] = h
                    else:
                        errors += 1

                # Choice narration
                if narrate_choices:
                    choices_text = build_choices_text(node, lang)
                    if choices_text:
                        ch_key = f"{out_key}_choices"
                        ch_path = OUTPUT_DIR / lang / f"{ch_key}.wav"
                        ch_hash_key = f"{lang}/{ch_key}"
                        ch_h = text_hash(choices_text)

                        if (
                            not args.force
                            and hashes.get(ch_hash_key) == ch_h
                            and ch_path.exists()
                        ):
                            skipped += 1
                        else:
                            if not args.dry_run and voice is None:
                                voice = ensure_voice(model_name)
                            ok = generate_wav(
                                choices_text, voice, ch_path, args.dry_run
                            )
                            if ok:
                                generated += 1
                                if not args.dry_run:
                                    new_hashes[ch_hash_key] = ch_h
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
