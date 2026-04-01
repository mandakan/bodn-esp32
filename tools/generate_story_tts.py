#!/usr/bin/env python3
"""
TTS audio generator for Bodn Story Mode.

Discovers story scripts from assets/stories/*/script.py, extracts narration
text and choice labels per language, and generates WAV files via Piper TTS.

Output (per-story directories, Piper native sample rate):
  Scene narration → build/story_tts_raw/{story_id}/{lang}/{node_id}.wav
  Choice labels   → build/story_tts_raw/{story_id}/{lang}/{node_id}_choices.wav

These are converted to 16 kHz PCM by convert_audio.py and assembled into
self-contained story packages under build/stories/.

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
import re
import sys
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
STORIES_DIR = REPO_ROOT / "assets" / "stories"
OUTPUT_DIR = REPO_ROOT / "build" / "story_tts_raw"
HASHES_JSON = REPO_ROOT / "build" / "story_tts_hashes.json"
VOICES_DIR = Path.home() / ".cache" / "piper"

# Voice config — same models as the main TTS pipeline
VOICES = {
    "sv": {"model": "sv_SE-alma-medium"},
    "en": {"model": "en_US-amy-medium"},
}

# --- Prosody defaults (storytelling pace for ages 3-5) ---
# length_scale > 1.0 = slower speech.  1.2 is a gentle storytelling pace.
DEFAULT_LENGTH_SCALE = 1.2
# Silence inserted between sentences (seconds).
DEFAULT_SENTENCE_SILENCE = 0.4
# Silence inserted where the author places a {pause} marker (seconds).
DEFAULT_PAUSE_SILENCE = 0.8
# Regex matching {pause} or {pause 1.2} markers in story text.
PAUSE_RE = re.compile(r"\{pause(?:\s+([\d.]+))?\}")

# Arcade button names — must match config.ARCADE_COLORS order:
# green (idx 0), blue (1), white (2), yellow (3), red (4)
ARC_BUTTON_NAMES = {
    "sv": ["grön", "blå", "vit", "gul", "röd"],
    "en": ["green", "blue", "white", "yellow", "red"],
}


def discover_stories():
    """Find all stories in assets/stories/. Returns list of (id, story_dict)."""
    stories = []

    if STORIES_DIR.exists():
        for entry in sorted(STORIES_DIR.iterdir()):
            script = entry / "script.py"
            if script.exists():
                ns = {}
                exec(script.read_text(), ns)
                s = ns.get("STORY")
                if s:
                    stories.append((s["id"], s))

    return stories


def load_hashes():
    if HASHES_JSON.exists():
        return json.loads(HASHES_JSON.read_text())
    return {}


def save_hashes(hashes):
    HASHES_JSON.parent.mkdir(parents=True, exist_ok=True)
    HASHES_JSON.write_text(json.dumps(hashes, indent=2, ensure_ascii=False) + "\n")


def text_hash(text, prosody=None):
    """Hash text + prosody settings so changes to either trigger regeneration."""
    h = hashlib.md5(text.encode())
    if prosody:
        h.update(json.dumps(prosody, sort_keys=True).encode())
    return h.hexdigest()[:12]


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


def make_silence(seconds, sample_rate):
    """Generate silent PCM bytes (16-bit mono)."""
    return b"\x00\x00" * int(sample_rate * seconds)


def split_on_pauses(text):
    """Split text on {pause} markers.

    Returns a list of (segment_text, pause_seconds) tuples.
    The pause after the last segment is 0.
    """
    segments = []
    last_end = 0
    for m in PAUSE_RE.finditer(text):
        seg = text[last_end : m.start()].strip()
        pause = float(m.group(1)) if m.group(1) else DEFAULT_PAUSE_SILENCE
        if seg:
            segments.append((seg, pause))
        last_end = m.end()
    trailing = text[last_end:].strip()
    if trailing:
        segments.append((trailing, 0))
    if not segments:
        segments.append((text, 0))
    return segments


def generate_wav(text, voice, out_path, dry_run, prosody=None):
    """Synthesize text to WAV with storytelling prosody.

    Supports:
    - length_scale: speech rate (> 1.0 = slower, default 1.2)
    - sentence_silence: pause between sentences in seconds (default 0.4)
    - {pause} / {pause 1.5} markers in text for longer dramatic pauses
    """
    if dry_run:
        print(f"  would generate  {out_path.relative_to(REPO_ROOT)}")
        return True

    from piper.config import SynthesisConfig

    prosody = prosody or {}
    length_scale = prosody.get("length_scale", DEFAULT_LENGTH_SCALE)
    sentence_silence = prosody.get("sentence_silence", DEFAULT_SENTENCE_SILENCE)
    syn_cfg = SynthesisConfig(length_scale=length_scale)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    segments = split_on_pauses(text)

    try:
        with wave.open(str(out_path), "wb") as wav_file:
            sr = voice.config.sample_rate
            wav_file.setframerate(sr)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setnchannels(1)  # mono

            for seg_idx, (seg_text, pause_after) in enumerate(segments):
                # Synthesize segment sentence by sentence with inter-sentence silence
                chunks = list(voice.synthesize(seg_text, syn_config=syn_cfg))
                for i, chunk in enumerate(chunks):
                    wav_file.writeframes(chunk.audio_int16_bytes)
                    # Add silence between sentences (not after the last one in segment)
                    if i < len(chunks) - 1 and sentence_silence > 0:
                        wav_file.writeframes(make_silence(sentence_silence, sr))

                # Add the {pause} marker silence between segments
                if pause_after > 0:
                    wav_file.writeframes(make_silence(pause_after, sr))
    except Exception as exc:
        print(f"  ERROR: {exc}", file=sys.stderr)
        return False

    kib = out_path.stat().st_size // 1024
    print(f"  generated  {out_path.relative_to(REPO_ROOT)}  ({kib} KiB)")
    return True


def build_choices_text(node, lang):
    """Build a sentence that reads out the choice labels.

    Swedish: "{Label} genom att trycka på {color}." — imperative label first,
    no conjugation issues.
    English: "Press {color} to {label}." — works since infinitive = imperative.
    """
    choices = node.get("choices", [])
    if not choices:
        return None
    button_names = ARC_BUTTON_NAMES.get(lang, ARC_BUTTON_NAMES["en"])

    parts = []
    for i, ch in enumerate(choices):
        if i >= len(button_names):
            break
        label = ch.get("label", {})
        text = label.get(lang, label.get("en", ""))
        if not text:
            continue
        # Strip trailing punctuation for clean sentence construction
        clean = text.rstrip("!.")
        if lang == "sv":
            # Label first (imperative), then button instruction
            parts.append(f"{clean} genom att trycka på {button_names[i]}.")
        else:
            # Lowercase for "to {verb}" construction
            parts.append(f"Press {button_names[i]} to {clean[0].lower() + clean[1:]}.")
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

    for story_id, story in stories:
        if args.story and story_id != args.story:
            continue
        narrate_choices = story.get("narrate_choices", True)
        prosody = story.get("prosody", {})
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

                # Output: build/story_tts_raw/{story_id}/{lang}/{node_id}.wav
                out_path = OUTPUT_DIR / story_id / lang / f"{node_id}.wav"
                hash_key = f"{story_id}/{lang}/{node_id}"
                h = text_hash(text, prosody)

                if not args.force and hashes.get(hash_key) == h and out_path.exists():
                    skipped += 1
                else:
                    if not args.dry_run and voice is None:
                        voice = ensure_voice(model_name)
                    ok = generate_wav(text, voice, out_path, args.dry_run, prosody)
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
                        ch_path = (
                            OUTPUT_DIR / story_id / lang / f"{node_id}_choices.wav"
                        )
                        ch_hash_key = f"{story_id}/{lang}/{node_id}_choices"
                        ch_h = text_hash(choices_text, prosody)

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
                                choices_text, voice, ch_path, args.dry_run, prosody
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
