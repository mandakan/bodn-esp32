#!/usr/bin/env python3
"""
Offline web preview for Bodn — stories and audio assets.

Two views served from one local server:
  /        Story mode preview (navigate branching narratives, play TTS)
  /audio   Audio asset browser (play all WAVs, see usage status)

Usage:
  uv run python tools/story_preview.py            # http://localhost:8033
  uv run python tools/story_preview.py --port 9000
"""

import argparse
import json
import re
import struct
import sys
import wave
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).parent.parent
STORIES_DIR = REPO_ROOT / "assets" / "stories"
BUILTIN_STORIES = REPO_ROOT / "firmware" / "bodn" / "stories" / "__init__.py"
TTS_DIR = REPO_ROOT / "build" / "story_tts"
FIRMWARE_SOUNDS = REPO_ROOT / "firmware" / "sounds"
BUILD_TTS = REPO_ROOT / "build" / "tts"
ASSETS_SOURCE = REPO_ROOT / "assets" / "audio" / "source"
TTS_JSON = REPO_ROOT / "assets" / "audio" / "tts.json"
SOUNDBOARD_JSON = REPO_ROOT / "assets" / "audio" / "soundboard.json"

MOOD_COLORS = {
    "warm": "#ffa028",
    "tense": "#c82800",
    "happy": "#28ff50",
    "wonder": "#3c28c8",
    "calm": "#505050",
}

ARC_COLORS = ["#00dc32", "#1e64fa", "#c8c8c8", "#e6dc00", "#e61e28"]


def discover_stories():
    """Load all stories. Returns dict {id: story_dict}."""
    stories = {}

    # Built-in flash story
    if BUILTIN_STORIES.exists():
        ns = {}
        exec(BUILTIN_STORIES.read_text(), ns)
        s = ns.get("BUILTIN_STORY")
        if s:
            stories[s["id"]] = s

    # SD card stories
    if STORIES_DIR.exists():
        for entry in sorted(STORIES_DIR.iterdir()):
            script = entry / "script.py"
            if script.exists():
                ns = {}
                exec(script.read_text(), ns)
                s = ns.get("STORY")
                if s:
                    stories[s["id"]] = s

    return stories


def story_to_json(story):
    """Convert story dict to JSON-safe format."""
    return {
        "id": story["id"],
        "title": story.get("title", {}),
        "author": story.get("author", ""),
        "age_min": story.get("age_min", 0),
        "age_max": story.get("age_max", 0),
        "estimated_minutes": story.get("estimated_minutes", 0),
        "narrate_choices": story.get("narrate_choices", False),
        "start": story["start"],
        "nodes": story["nodes"],
    }


def build_html(stories):
    """Generate the single-page preview app."""
    stories_json = json.dumps(
        {sid: story_to_json(s) for sid, s in stories.items()},
        ensure_ascii=False,
        indent=2,
    )

    mood_colors_json = json.dumps(MOOD_COLORS)
    arc_colors_json = json.dumps(ARC_COLORS)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bodn Story Preview</title>
<style>
  :root {{
    --bg: #1a1a2e;
    --surface: #16213e;
    --card: #1f3460;
    --text: #e0e0e0;
    --muted: #888;
    --accent: #ffa028;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
  }}
  header {{
    background: var(--surface);
    padding: 12px 20px;
    border-bottom: 2px solid var(--accent);
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
  }}
  header h1 {{
    font-size: 1.2em;
    color: var(--accent);
  }}
  header select, header button {{
    padding: 6px 12px;
    border-radius: 6px;
    border: 1px solid #444;
    background: var(--card);
    color: var(--text);
    font-size: 0.9em;
    cursor: pointer;
  }}
  header button:hover {{ background: #2a4a80; }}
  .lang-toggle {{
    margin-left: auto;
    display: flex;
    gap: 4px;
  }}
  .lang-toggle button.active {{
    background: var(--accent);
    color: #000;
    font-weight: bold;
  }}
  #app {{
    max-width: 900px;
    margin: 0 auto;
    padding: 20px;
  }}

  /* Story info */
  .story-info {{
    background: var(--surface);
    border-radius: 10px;
    padding: 16px;
    margin-bottom: 20px;
  }}
  .story-info h2 {{ color: var(--accent); margin-bottom: 8px; }}
  .story-info .meta {{ color: var(--muted); font-size: 0.85em; }}

  /* Node card */
  .node-card {{
    background: var(--card);
    border-radius: 12px;
    padding: 24px;
    margin-bottom: 16px;
    border-left: 5px solid var(--accent);
    transition: border-color 0.3s;
  }}
  .node-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
  }}
  .node-id {{
    font-size: 0.8em;
    color: #aaa;
    font-family: monospace;
    background: rgba(255,255,255,0.08);
    padding: 2px 8px;
    border-radius: 4px;
  }}
  .mood-badge {{
    font-size: 0.8em;
    padding: 3px 10px;
    border-radius: 12px;
    color: #000;
    font-weight: 700;
  }}
  .narration {{
    font-size: 1.15em;
    line-height: 1.6;
    margin-bottom: 16px;
  }}
  .audio-row {{
    display: flex;
    gap: 8px;
    margin-bottom: 16px;
    flex-wrap: wrap;
  }}
  .audio-row button {{
    padding: 6px 14px;
    border-radius: 6px;
    border: 1px solid #555;
    background: var(--surface);
    color: var(--text);
    cursor: pointer;
    font-size: 0.85em;
  }}
  .audio-row button:hover {{ background: #2a4a80; }}
  .audio-row button.playing {{
    background: var(--accent);
    color: #000;
  }}
  .audio-row button.missing {{
    opacity: 0.4;
    cursor: default;
  }}

  /* Choices */
  .choices {{
    display: flex;
    flex-direction: column;
    gap: 8px;
  }}
  .choice-btn {{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    border-radius: 8px;
    border: 2px solid transparent;
    background: rgba(255,255,255,0.05);
    color: var(--text);
    cursor: pointer;
    font-size: 1em;
    text-align: left;
    transition: all 0.15s;
  }}
  .choice-btn:hover {{
    background: rgba(255,255,255,0.12);
    border-color: rgba(255,255,255,0.2);
  }}
  .choice-dot {{
    width: 18px;
    height: 18px;
    border-radius: 50%;
    flex-shrink: 0;
    border: 2px solid rgba(255,255,255,0.3);
  }}
  .choice-label {{ flex: 1; }}
  .choice-next {{
    font-size: 0.8em;
    color: var(--muted);
    font-family: monospace;
  }}

  /* Ending */
  .ending-badge {{
    display: inline-block;
    padding: 8px 20px;
    border-radius: 8px;
    background: var(--accent);
    color: #000;
    font-weight: bold;
    font-size: 1.1em;
    margin-top: 8px;
  }}

  /* Path history */
  .path-history {{
    background: var(--surface);
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 16px;
  }}
  .path-history h3 {{
    font-size: 0.85em;
    color: var(--muted);
    margin-bottom: 8px;
  }}
  .path-crumbs {{
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
    align-items: center;
  }}
  .path-crumbs span {{
    font-size: 0.8em;
    font-family: monospace;
    padding: 2px 8px;
    background: rgba(255,255,255,0.06);
    border-radius: 4px;
    cursor: pointer;
  }}
  .path-crumbs span:hover {{ background: rgba(255,255,255,0.12); }}
  .path-crumbs .arrow {{ background: none; color: var(--muted); cursor: default; }}
  .path-crumbs .current {{ background: var(--accent); color: #000; }}

  /* Graph view */
  #graph {{
    background: var(--surface);
    border-radius: 10px;
    padding: 16px;
    margin-top: 20px;
  }}
  #graph h3 {{
    color: var(--muted);
    font-size: 0.85em;
    margin-bottom: 12px;
  }}
  .graph-node {{
    display: inline-block;
    font-size: 0.75em;
    font-family: monospace;
    padding: 4px 8px;
    margin: 2px;
    border-radius: 4px;
    cursor: pointer;
    border: 1px solid #444;
  }}
  .graph-node:hover {{ border-color: var(--accent); }}
  .graph-node.active {{ background: var(--accent); color: #000; border-color: var(--accent); }}
  .graph-node.visited {{ border-color: #4a6; }}
  .graph-node.ending {{ border-style: double; border-width: 3px; }}

  .restart-btn {{
    margin-top: 12px;
    padding: 10px 24px;
    border-radius: 8px;
    border: 2px solid var(--accent);
    background: transparent;
    color: var(--accent);
    font-size: 1em;
    cursor: pointer;
    font-weight: bold;
  }}
  .restart-btn:hover {{ background: var(--accent); color: #000; }}

  .sfx-tag {{
    font-size: 0.75em;
    color: var(--accent);
    margin-left: 8px;
    font-family: monospace;
  }}
</style>
</head>
<body>
<header>
  <h1>Bodn Preview</h1>
  <a href="/" style="color:var(--accent);text-decoration:none;font-weight:bold;padding:6px 12px;border:1px solid var(--accent);border-radius:6px">Stories</a>
  <a href="/audio" style="color:var(--text);text-decoration:none;padding:6px 12px;border:1px solid #444;border-radius:6px">Audio</a>
  <select id="story-select"></select>
  <div class="lang-toggle">
    <button data-lang="sv" class="active">SV</button>
    <button data-lang="en">EN</button>
  </div>
</header>
<div id="app"></div>

<script>
const STORIES = {stories_json};
const MOOD_COLORS = {mood_colors_json};
const ARC_COLORS = {arc_colors_json};
const ARC_NAMES = {{ sv: ['gron', 'bla', 'vit', 'gul', 'rod'], en: ['green', 'blue', 'white', 'yellow', 'red'] }};
// WCAG-safe text color per mood background (black for light, white for dark)
const MOOD_TEXT = {{ warm: '#000', tense: '#fff', happy: '#000', wonder: '#fff', calm: '#fff' }};

let currentStory = null;
let currentNode = null;
let lang = 'sv';
let path = [];
let audioEl = null;

// --- Init ---
const sel = document.getElementById('story-select');
Object.entries(STORIES).forEach(([id, s]) => {{
  const opt = document.createElement('option');
  opt.value = id;
  opt.textContent = (s.title[lang] || s.title.en || id);
  sel.appendChild(opt);
}});
sel.addEventListener('change', () => loadStory(sel.value));

document.querySelectorAll('.lang-toggle button').forEach(btn => {{
  btn.addEventListener('click', () => {{
    lang = btn.dataset.lang;
    document.querySelectorAll('.lang-toggle button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    // Update story selector text
    [...sel.options].forEach(opt => {{
      const s = STORIES[opt.value];
      opt.textContent = s.title[lang] || s.title.en || opt.value;
    }});
    if (currentStory) render();
  }});
}});

function loadStory(id) {{
  currentStory = STORIES[id];
  currentNode = currentStory.start;
  path = [currentNode];
  render();
}}

function goToNode(nodeId) {{
  currentNode = nodeId;
  if (!path.includes(nodeId)) path.push(nodeId);
  render();
}}

function jumpToNode(nodeId) {{
  // Jump directly (from graph or breadcrumbs), truncate path
  const idx = path.indexOf(nodeId);
  if (idx >= 0) {{
    path = path.slice(0, idx + 1);
  }} else {{
    path.push(nodeId);
  }}
  currentNode = nodeId;
  render();
}}

function restart() {{
  currentNode = currentStory.start;
  path = [currentNode];
  render();
}}

function stopAudio() {{
  if (audioEl) {{
    audioEl.pause();
    audioEl = null;
    document.querySelectorAll('.audio-row button.playing').forEach(b => b.classList.remove('playing'));
  }}
}}

function playTTS(key, btn) {{
  stopAudio();
  const url = `/tts/${{lang}}/${{key}}.wav`;
  audioEl = new Audio(url);
  btn.classList.add('playing');
  audioEl.addEventListener('ended', () => {{ btn.classList.remove('playing'); audioEl = null; }});
  audioEl.addEventListener('error', () => {{
    btn.classList.remove('playing');
    btn.classList.add('missing');
    btn.title = 'Audio not found — run tools/generate_story_tts.py first';
    audioEl = null;
  }});
  audioEl.play();
}}

function getText(textObj) {{
  if (!textObj) return '';
  let t = textObj[lang] || textObj.en || '';
  return t.replace(/\{{pause(?:\s+[\d.]+)?\}}/g, '');
}}

function render() {{
  stopAudio();
  const app = document.getElementById('app');
  const s = currentStory;
  const node = s.nodes[currentNode];

  const moodColor = MOOD_COLORS[node.mood] || MOOD_COLORS.calm;
  const ttsKey = `story_${{s.id}}_${{currentNode}}`;

  let html = '';

  // Story info
  html += `<div class="story-info">
    <h2>${{getText(s.title)}}</h2>
    <div class="meta">
      ${{s.author ? `By ${{s.author}} · ` : ''}}
      Ages ${{s.age_min}}\u2013${{s.age_max}} · ~${{s.estimated_minutes}} min
    </div>
  </div>`;

  // Path breadcrumbs
  if (path.length > 1) {{
    html += `<div class="path-history"><h3>Path</h3><div class="path-crumbs">`;
    path.forEach((nid, i) => {{
      if (i > 0) html += `<span class="arrow">\u2192</span>`;
      const cls = nid === currentNode ? 'current' : '';
      html += `<span class="${{cls}}" onclick="jumpToNode('${{nid}}')">${{nid}}</span>`;
    }});
    html += `</div></div>`;
  }}

  // Node card
  html += `<div class="node-card" style="border-left-color: ${{moodColor}}">`;
  html += `<div class="node-header">
    <span class="node-id">${{currentNode}}</span>
    <span class="mood-badge" style="background: ${{moodColor}}; color: ${{MOOD_TEXT[node.mood] || '#fff'}}">${{node.mood || 'calm'}}</span>
  </div>`;

  html += `<div class="narration">${{getText(node.text)}}</div>`;

  if (node.sfx) {{
    html += `<span class="sfx-tag">SFX: ${{node.sfx}}</span>`;
  }}

  // Audio buttons
  html += `<div class="audio-row">
    <button onclick="playTTS('${{ttsKey}}', this)">&#9654; Narration</button>`;
  if (node.choices && node.choices.length && s.narrate_choices) {{
    html += `<button onclick="playTTS('${{ttsKey}}_choices', this)">&#9654; Choices</button>`;
  }}
  html += `</div>`;

  // Choices or ending
  if (node.ending) {{
    const typeLabel = (node.ending_type || 'ending').replace('_', ' ');
    html += `<div class="ending-badge">The End (${{typeLabel}})</div>`;
    html += `<br><button class="restart-btn" onclick="restart()">Restart story</button>`;
  }} else if (node.choices) {{
    html += `<div class="choices">`;
    node.choices.forEach((ch, i) => {{
      const color = ARC_COLORS[i] || '#888';
      const btnName = (ARC_NAMES[lang] || ARC_NAMES.en)[i] || '';
      html += `<button class="choice-btn" onclick="goToNode('${{ch.next}}')">
        <span class="choice-dot" style="background: ${{color}}"></span>
        <span class="choice-label">${{getText(ch.label)}}</span>
        <span class="choice-next">${{btnName}} \u2192 ${{ch.next}}</span>
      </button>`;
    }});
    html += `</div>`;
  }}

  html += `</div>`;

  // Graph view
  html += `<div id="graph"><h3>All nodes (${{Object.keys(s.nodes).length}})</h3>`;
  Object.entries(s.nodes).forEach(([nid, n]) => {{
    let cls = 'graph-node';
    if (nid === currentNode) cls += ' active';
    if (path.includes(nid)) cls += ' visited';
    if (n.ending) cls += ' ending';
    const bg = MOOD_COLORS[n.mood] || '';
    html += `<span class="${{cls}}" style="background: ${{nid === currentNode ? '' : bg + '33'}}" `
      + `onclick="jumpToNode('${{nid}}')">${{nid}}${{n.ending ? ' \u2605' : ''}}</span>`;
  }});
  html += `</div>`;

  app.innerHTML = html;
}}

// Load first story
if (sel.options.length) loadStory(sel.options[0].value);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Audio asset browser
# ---------------------------------------------------------------------------

WAV_DIRS = {
    "soundboard": FIRMWARE_SOUNDS,
    "tts_game": BUILD_TTS,
    "tts_story": TTS_DIR,
    "source": ASSETS_SOURCE,
}


def wav_metadata(path):
    """Read WAV header for duration and format info."""
    try:
        with wave.open(str(path), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            channels = w.getnchannels()
            sampwidth = w.getsampwidth()
            duration = frames / rate if rate else 0
            return {
                "duration": round(duration, 2),
                "sample_rate": rate,
                "channels": channels,
                "bits": sampwidth * 8,
            }
    except Exception:
        return {"duration": 0, "sample_rate": 0, "channels": 0, "bits": 0}


def find_code_references():
    """Scan firmware code for audio key references. Returns set of keys."""
    refs = set()
    firmware_dir = REPO_ROOT / "firmware"

    # Scan all .py files for say() calls and play_sound() calls
    for py_file in firmware_dir.rglob("*.py"):
        try:
            content = py_file.read_text()
        except Exception:
            continue

        # say("key", ...) — TTS playback
        for m in re.finditer(r'say\(\s*["\']([^"\']+)["\']', content):
            refs.add(m.group(1))

        # play_sound("key") — procedural sounds
        for m in re.finditer(r'play_sound\(\s*["\']([^"\']+)["\']', content):
            refs.add(m.group(1))

        # TTS key construction: f"story_{...}_{...}" patterns
        for m in re.finditer(r'f["\']story_\{', content):
            refs.add("story_*")  # mark story TTS as used

        # Direct WAV path references
        for m in re.finditer(r'["\'](/sounds/[^"\']+\.wav)["\']', content):
            refs.add(m.group(1))

        # Soundboard wav_path references (bank_N/slot.wav)
        for m in re.finditer(r"bank_\d+/\d+\.wav", content):
            refs.add("soundboard_*")

    return refs


def scan_audio_assets():
    """Scan all audio directories and cross-reference with code usage."""
    assets = []
    code_refs = find_code_references()

    # Load TTS allowlist
    tts_keys = set()
    if TTS_JSON.exists():
        tts_cfg = json.loads(TTS_JSON.read_text())
        tts_keys = set(tts_cfg.get("keys", {}).keys())

    # Load soundboard manifest
    sb_slots = {}
    if SOUNDBOARD_JSON.exists():
        sb_cfg = json.loads(SOUNDBOARD_JSON.read_text())
        for bank_id, bank in sb_cfg.get("banks", {}).items():
            for slot_id, slot in bank.get("slots", {}).items():
                sb_slots[f"bank_{bank_id}/{slot_id}.wav"] = {
                    "sv": slot.get("sv", ""),
                    "en": slot.get("en", ""),
                }

    # Load story scripts to identify story TTS keys
    story_tts_keys = set()
    stories = discover_stories()
    for sid, story in stories.items():
        for node_id, node in story.get("nodes", {}).items():
            story_tts_keys.add(f"story_{sid}_{node_id}")
            if node.get("choices") and story.get("narrate_choices", False):
                story_tts_keys.add(f"story_{sid}_{node_id}_choices")

    # 1. Soundboard banks
    for bank_dir in sorted(FIRMWARE_SOUNDS.glob("bank_*")):
        bank_id = bank_dir.name.split("_")[1]
        for wav in sorted(bank_dir.glob("*.wav")):
            slot_key = f"{bank_dir.name}/{wav.name}"
            labels = sb_slots.get(slot_key, {})
            meta = wav_metadata(wav)
            assets.append(
                {
                    "path": str(wav.relative_to(REPO_ROOT)),
                    "abs_path": str(wav),
                    "category": "soundboard",
                    "label_sv": labels.get("sv", ""),
                    "label_en": labels.get("en", ""),
                    "bank": int(bank_id),
                    "slot": int(wav.stem),
                    "used": True,  # soundboard files are always used
                    "usage": f"Bank {bank_id}, slot {wav.stem}",
                    **meta,
                }
            )

    # 2. TTS flash (firmware/sounds/tts/)
    tts_flash = FIRMWARE_SOUNDS / "tts"
    if tts_flash.exists():
        for lang_dir in sorted(tts_flash.iterdir()):
            if not lang_dir.is_dir():
                continue
            for wav in sorted(lang_dir.glob("*.wav")):
                key = wav.stem
                meta = wav_metadata(wav)
                in_allowlist = key in tts_keys
                in_code = key in code_refs
                assets.append(
                    {
                        "path": str(wav.relative_to(REPO_ROOT)),
                        "abs_path": str(wav),
                        "category": "tts_flash",
                        "label_sv": "",
                        "label_en": key.replace("_", " "),
                        "lang": lang_dir.name,
                        "tts_key": key,
                        "used": in_allowlist or in_code,
                        "usage": f"TTS flash ({lang_dir.name})"
                        + (" — in allowlist" if in_allowlist else "")
                        + (" — in code" if in_code else ""),
                        **meta,
                    }
                )

    # 3. TTS game (build/tts/)
    if BUILD_TTS.exists():
        for lang_dir in sorted(BUILD_TTS.iterdir()):
            if not lang_dir.is_dir():
                continue
            for wav in sorted(lang_dir.glob("*.wav")):
                key = wav.stem
                meta = wav_metadata(wav)
                in_allowlist = key in tts_keys
                in_code = key in code_refs
                assets.append(
                    {
                        "path": str(wav.relative_to(REPO_ROOT)),
                        "abs_path": str(wav),
                        "category": "tts_game",
                        "label_sv": "",
                        "label_en": key.replace("_", " "),
                        "lang": lang_dir.name,
                        "tts_key": key,
                        "used": in_allowlist or in_code,
                        "usage": f"TTS game ({lang_dir.name})"
                        + (" — in allowlist" if in_allowlist else "")
                        + (" — in code" if in_code else ""),
                        **meta,
                    }
                )

    # 4. Story TTS (build/story_tts/)
    if TTS_DIR.exists():
        for lang_dir in sorted(TTS_DIR.iterdir()):
            if not lang_dir.is_dir():
                continue
            for wav in sorted(lang_dir.glob("*.wav")):
                key = wav.stem
                meta = wav_metadata(wav)
                used = key in story_tts_keys
                assets.append(
                    {
                        "path": str(wav.relative_to(REPO_ROOT)),
                        "abs_path": str(wav),
                        "category": "tts_story",
                        "label_sv": "",
                        "label_en": key.replace("_", " "),
                        "lang": lang_dir.name,
                        "tts_key": key,
                        "used": used,
                        "usage": f"Story TTS ({lang_dir.name})"
                        + (" — in story script" if used else " — ORPHAN"),
                        **meta,
                    }
                )

    # 5. Check for expected TTS keys that are MISSING files
    # (referenced in allowlist but no WAV exists)
    existing_tts = set()
    for a in assets:
        if a.get("tts_key"):
            existing_tts.add(a["tts_key"])

    for key in sorted(tts_keys - existing_tts):
        in_code = key in code_refs
        assets.append(
            {
                "path": f"(missing) {key}.wav",
                "abs_path": "",
                "category": "missing",
                "label_sv": "",
                "label_en": key.replace("_", " "),
                "tts_key": key,
                "used": in_code,
                "usage": "In allowlist but NO FILE"
                + (" — referenced in code" if in_code else ""),
                "duration": 0,
                "sample_rate": 0,
                "channels": 0,
                "bits": 0,
            }
        )

    return assets


def build_audio_html(assets):
    """Generate the audio browser HTML page."""
    assets_json = json.dumps(assets, ensure_ascii=False, indent=2)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bodn Audio Browser</title>
<style>
  :root {{
    --bg: #1a1a2e;
    --surface: #16213e;
    --card: #1f3460;
    --text: #e0e0e0;
    --muted: #888;
    --accent: #ffa028;
    --green: #28ff50;
    --red: #e61e28;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
  }}
  nav {{
    background: var(--surface);
    padding: 12px 20px;
    border-bottom: 2px solid var(--accent);
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
  }}
  nav h1 {{ font-size: 1.2em; color: var(--accent); }}
  nav a {{
    color: var(--text);
    text-decoration: none;
    padding: 6px 12px;
    border-radius: 6px;
    border: 1px solid #444;
    font-size: 0.9em;
  }}
  nav a:hover {{ background: #2a4a80; }}
  nav a.active {{ background: var(--accent); color: #000; font-weight: bold; border-color: var(--accent); }}
  #controls {{
    max-width: 1100px;
    margin: 16px auto;
    padding: 0 20px;
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
  }}
  .filter-btn {{
    padding: 6px 14px;
    border-radius: 6px;
    border: 1px solid #444;
    background: var(--card);
    color: var(--text);
    cursor: pointer;
    font-size: 0.85em;
  }}
  .filter-btn:hover {{ background: #2a4a80; }}
  .filter-btn.active {{ background: var(--accent); color: #000; font-weight: bold; }}
  .filter-btn.unused {{ border-color: var(--red); }}
  .stats {{
    margin-left: auto;
    font-size: 0.85em;
    color: var(--muted);
  }}
  #app {{
    max-width: 1100px;
    margin: 0 auto;
    padding: 0 20px 40px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85em;
  }}
  th {{
    text-align: left;
    padding: 10px 8px;
    border-bottom: 2px solid #444;
    color: var(--accent);
    font-size: 0.8em;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    cursor: pointer;
    user-select: none;
  }}
  th:hover {{ color: #fff; }}
  td {{
    padding: 8px;
    border-bottom: 1px solid rgba(255,255,255,0.05);
    vertical-align: middle;
  }}
  tr:hover td {{ background: rgba(255,255,255,0.03); }}
  tr.unused td {{ color: #9a9a9a; }}
  tr.missing td {{ color: #ff8a8a; }}
  .play-btn {{
    width: 32px;
    height: 32px;
    border-radius: 50%;
    border: 1px solid #555;
    background: var(--surface);
    color: var(--text);
    cursor: pointer;
    font-size: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
  }}
  .play-btn:hover {{ background: #2a4a80; }}
  .play-btn.playing {{ background: var(--accent); color: #000; }}
  .play-btn.disabled {{ opacity: 0.35; cursor: default; }}
  .cat-badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.8em;
    font-weight: 600;
  }}
  .cat-soundboard {{ background: #FF6B3533; color: #FF6B35; }}
  .cat-tts_flash {{ background: #8B5CF633; color: #8B5CF6; }}
  .cat-tts_game {{ background: #3B82F633; color: #3B82F6; }}
  .cat-tts_story {{ background: #10B98133; color: #10B981; }}
  .cat-missing {{ background: #ff8a8a22; color: #ff8a8a; }}
  .status-dot {{
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-right: 6px;
  }}
  .status-used {{ background: var(--green); }}
  .status-unused {{ background: var(--red); }}
  .status-missing {{ background: var(--red); animation: pulse 1s infinite; }}
  @keyframes pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: 0.3; }} }}
  .dur {{ font-family: monospace; color: var(--muted); }}
  .meta-detail {{ font-size: 0.75em; color: var(--muted); font-family: monospace; }}
  .usage-text {{ font-size: 0.8em; color: var(--muted); }}
  .file-path {{ font-family: monospace; font-size: 0.8em; word-break: break-all; }}
</style>
</head>
<body>
<nav>
  <h1>Bodn Preview</h1>
  <a href="/">Stories</a>
  <a href="/audio" class="active">Audio</a>
</nav>
<div id="controls">
  <button class="filter-btn active" data-filter="all">All</button>
  <button class="filter-btn" data-filter="soundboard">Soundboard</button>
  <button class="filter-btn" data-filter="tts_flash">TTS Flash</button>
  <button class="filter-btn" data-filter="tts_game">TTS Game</button>
  <button class="filter-btn" data-filter="tts_story">TTS Story</button>
  <button class="filter-btn unused" data-filter="unused">Unused</button>
  <button class="filter-btn unused" data-filter="missing">Missing</button>
  <span class="stats" id="stats"></span>
</div>
<div id="app"></div>

<script>
const ASSETS = {assets_json};
let currentFilter = 'all';
let audioEl = null;
let playingIdx = -1;

const CAT_LABELS = {{
  soundboard: 'Soundboard',
  tts_flash: 'TTS Flash',
  tts_game: 'TTS Game',
  tts_story: 'TTS Story',
  missing: 'Missing',
}};

// Filter buttons
document.querySelectorAll('.filter-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    currentFilter = btn.dataset.filter;
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    render();
  }});
}});

function stopAudio() {{
  if (audioEl) {{
    audioEl.pause();
    audioEl = null;
  }}
  playingIdx = -1;
  document.querySelectorAll('.play-btn.playing').forEach(b => b.classList.remove('playing'));
}}

function playFile(idx, btn) {{
  const a = ASSETS[idx];
  if (!a.abs_path) return;

  if (playingIdx === idx) {{
    stopAudio();
    return;
  }}

  stopAudio();
  const url = `/wav/${{encodeURIComponent(a.path)}}`;
  audioEl = new Audio(url);
  playingIdx = idx;
  btn.classList.add('playing');
  btn.textContent = '\\u25A0';
  audioEl.addEventListener('ended', () => {{
    btn.classList.remove('playing');
    btn.textContent = '\\u25B6';
    playingIdx = -1;
    audioEl = null;
  }});
  audioEl.addEventListener('error', () => {{
    btn.classList.remove('playing');
    btn.textContent = '!';
    playingIdx = -1;
    audioEl = null;
  }});
  audioEl.play();
}}

function fmtDuration(s) {{
  if (!s) return '-';
  if (s < 1) return s.toFixed(2) + 's';
  const m = Math.floor(s / 60);
  const sec = (s % 60).toFixed(1);
  return m > 0 ? m + ':' + sec.padStart(4, '0') : sec + 's';
}}

function fmtSize(path) {{
  // We don't have file size in JS but duration + sample rate gives a rough idea
  return '';
}}

function render() {{
  const filtered = ASSETS.filter(a => {{
    if (currentFilter === 'all') return true;
    if (currentFilter === 'unused') return !a.used && a.category !== 'missing';
    if (currentFilter === 'missing') return a.category === 'missing';
    return a.category === currentFilter;
  }});

  const total = ASSETS.length;
  const used = ASSETS.filter(a => a.used && a.category !== 'missing').length;
  const unused = ASSETS.filter(a => !a.used && a.category !== 'missing').length;
  const missing = ASSETS.filter(a => a.category === 'missing').length;
  document.getElementById('stats').textContent =
    `${{total}} files | ${{used}} used | ${{unused}} unused | ${{missing}} missing`;

  let html = '<table><thead><tr>';
  html += '<th></th><th>File</th><th>Category</th><th>Label</th>';
  html += '<th>Duration</th><th>Format</th><th>Status</th><th>Usage</th>';
  html += '</tr></thead><tbody>';

  filtered.forEach((a, i) => {{
    const realIdx = ASSETS.indexOf(a);
    const rowClass = a.category === 'missing' ? 'missing' : (!a.used ? 'unused' : '');
    const isPlaying = playingIdx === realIdx;
    const canPlay = !!a.abs_path;

    html += `<tr class="${{rowClass}}">`;

    // Play button
    html += `<td><button class="play-btn ${{isPlaying ? 'playing' : ''}} ${{!canPlay ? 'disabled' : ''}}"
      onclick="playFile(${{realIdx}}, this)" ${{!canPlay ? 'disabled' : ''}}>
      ${{isPlaying ? '\\u25A0' : '\\u25B6'}}</button></td>`;

    // File path
    html += `<td class="file-path">${{a.path}}</td>`;

    // Category badge
    html += `<td><span class="cat-badge cat-${{a.category}}">${{CAT_LABELS[a.category] || a.category}}</span></td>`;

    // Label
    const label = a.label_en || a.label_sv || '';
    html += `<td>${{label}}</td>`;

    // Duration
    html += `<td class="dur">${{fmtDuration(a.duration)}}</td>`;

    // Format
    if (a.sample_rate) {{
      html += `<td class="meta-detail">${{a.sample_rate/1000}}kHz ${{a.bits}}bit ${{a.channels === 1 ? 'mono' : 'stereo'}}</td>`;
    }} else {{
      html += `<td class="meta-detail">-</td>`;
    }}

    // Status
    const statusClass = a.category === 'missing' ? 'status-missing' : (a.used ? 'status-used' : 'status-unused');
    const statusLabel = a.category === 'missing' ? 'missing' : (a.used ? 'used' : 'unused');
    html += `<td><span class="status-dot ${{statusClass}}"></span>${{statusLabel}}</td>`;

    // Usage
    html += `<td class="usage-text">${{a.usage || ''}}</td>`;

    html += '</tr>';
  }});

  html += '</tbody></table>';
  document.getElementById('app').innerHTML = html;
}}

render();
</script>
</body>
</html>
"""


class PreviewHandler(SimpleHTTPRequestHandler):
    """Serves story preview, audio browser, and WAV files."""

    def __init__(self, *args, pages=None, **kwargs):
        self._pages = pages or {}
        super().__init__(*args, **kwargs)

    def _serve_html(self, html):
        data = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)

    def _serve_wav(self, wav_path):
        if wav_path.exists() and wav_path.suffix == ".wav":
            data = wav_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", len(data))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_error(404)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path in ("/", "/index.html"):
            self._serve_html(self._pages["story"])
            return

        if parsed.path == "/audio":
            self._serve_html(self._pages["audio"])
            return

        if parsed.path.startswith("/tts/"):
            self._serve_wav(TTS_DIR / parsed.path[5:])
            return

        if parsed.path.startswith("/wav/"):
            # Serve any WAV by repo-relative path
            from urllib.parse import unquote

            rel = unquote(parsed.path[5:])
            self._serve_wav(REPO_ROOT / rel)
            return

        self.send_error(404)

    def log_message(self, format, *args):
        if args and "404" in str(args[0]):
            return
        super().log_message(format, *args)


def make_handler(pages):
    """Create handler class with pages bound."""

    class Handler(PreviewHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, pages=pages, **kwargs)

    return Handler


def main():
    parser = argparse.ArgumentParser(
        description="Bodn preview server — stories and audio assets"
    )
    parser.add_argument("--port", type=int, default=8033, help="Port (default: 8033)")
    args = parser.parse_args()

    stories = discover_stories()
    if not stories:
        print("No stories found!", file=sys.stderr)
        sys.exit(1)

    print(f"Stories: {len(stories)} ({', '.join(stories.keys())})")

    audio_assets = scan_audio_assets()
    used = sum(1 for a in audio_assets if a["used"] and a["category"] != "missing")
    unused = sum(
        1 for a in audio_assets if not a["used"] and a["category"] != "missing"
    )
    missing = sum(1 for a in audio_assets if a["category"] == "missing")
    print(
        f"Audio: {len(audio_assets)} files ({used} used, {unused} unused, {missing} missing)"
    )

    pages = {
        "story": build_html(stories),
        "audio": build_audio_html(audio_assets),
    }
    handler = make_handler(pages)

    server = HTTPServer(("127.0.0.1", args.port), handler)
    print(f"\nServing at http://localhost:{args.port}")
    print(f"  /       Story preview")
    print(f"  /audio  Audio browser")
    print("Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
