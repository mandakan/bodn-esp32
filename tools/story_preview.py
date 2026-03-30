#!/usr/bin/env python3
"""
Offline web preview for Bodn Story Mode.

Serves a local web page that lets you navigate branching stories,
play TTS audio, and inspect the node graph — without an ESP32.

Discovers stories from:
  - assets/stories/*/script.py   (SD card stories)
  - firmware/bodn/stories/       (built-in flash story)

TTS audio served from build/story_tts/{lang}/ if available.

Usage:
  uv run python tools/story_preview.py            # http://localhost:8033
  uv run python tools/story_preview.py --port 9000
"""

import argparse
import json
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).parent.parent
STORIES_DIR = REPO_ROOT / "assets" / "stories"
BUILTIN_STORIES = REPO_ROOT / "firmware" / "bodn" / "stories" / "__init__.py"
TTS_DIR = REPO_ROOT / "build" / "story_tts"

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
    color: var(--muted);
    font-family: monospace;
    background: rgba(255,255,255,0.05);
    padding: 2px 8px;
    border-radius: 4px;
  }}
  .mood-badge {{
    font-size: 0.8em;
    padding: 3px 10px;
    border-radius: 12px;
    color: #fff;
    font-weight: 600;
    text-shadow: 0 1px 2px rgba(0,0,0,0.5);
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
  <h1>Bodn Story Preview</h1>
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
    <span class="mood-badge" style="background: ${{moodColor}}">${{node.mood || 'calm'}}</span>
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


class PreviewHandler(SimpleHTTPRequestHandler):
    """Serves the preview HTML and TTS audio files."""

    def __init__(self, *args, stories=None, html=None, **kwargs):
        self._stories = stories
        self._html = html
        super().__init__(*args, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/" or parsed.path == "/index.html":
            data = self._html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(data))
            self.end_headers()
            self.wfile.write(data)
            return

        if parsed.path.startswith("/tts/"):
            # Serve TTS audio from build/story_tts/
            rel = parsed.path[5:]  # strip /tts/
            wav_path = TTS_DIR / rel
            if wav_path.exists() and wav_path.suffix == ".wav":
                data = wav_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", len(data))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(404, f"TTS file not found: {rel}")
            return

        self.send_error(404)

    def log_message(self, format, *args):
        # Suppress 404 noise from missing TTS files
        if args and "404" in str(args[0]):
            return
        super().log_message(format, *args)


def make_handler(stories, html):
    """Create handler class with stories/html bound."""

    class Handler(PreviewHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, stories=stories, html=html, **kwargs)

    return Handler


def main():
    parser = argparse.ArgumentParser(
        description="Bodn Story Mode — offline web preview"
    )
    parser.add_argument("--port", type=int, default=8033, help="Port (default: 8033)")
    args = parser.parse_args()

    stories = discover_stories()
    if not stories:
        print("No stories found!", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {len(stories)} story/stories: {', '.join(stories.keys())}")

    has_tts = TTS_DIR.exists() and any(TTS_DIR.rglob("*.wav"))
    if has_tts:
        n = len(list(TTS_DIR.rglob("*.wav")))
        print(f"TTS audio: {n} WAV files in build/story_tts/")
    else:
        print("TTS audio: not found (run tools/generate_story_tts.py to generate)")

    html = build_html(stories)
    handler = make_handler(stories, html)

    server = HTTPServer(("127.0.0.1", args.port), handler)
    print(f"\nServing at http://localhost:{args.port}")
    print("Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
