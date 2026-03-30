# Story Authoring Guide

How to write branching interactive stories for Bodn Story Mode.

## Quick start

1. Create `assets/stories/{story_id}/script.py` with a `STORY` dict.
2. Generate TTS audio: `uv run python tools/generate_story_tts.py`
3. Preview in browser: `uv run python tools/story_preview.py`
4. Listen to every node in both languages. Fix pronunciation issues. Regenerate.
5. Copy audio to SD card (see [audio.md](audio.md) for the workflow).

## Story script format

A story is a Python file exporting a `STORY` dict describing a directed graph of scenes (nodes). Each node has bilingual narration text, an optional mood, and either a list of choices leading to other nodes or an `ending` flag.

```python
# assets/stories/my_story/script.py
STORY = {
    "id": "my_story",
    "version": 1,
    "title": {"sv": "Min Saga", "en": "My Story"},
    "author": "Your Name",
    "age_min": 3,
    "age_max": 6,
    "estimated_minutes": 3,
    "narrate_choices": True,
    "start": "opening",

    "nodes": {
        "opening": {
            "text": {
                "sv": "Det var en gång...",
                "en": "Once upon a time...",
            },
            "mood": "warm",
            "choices": [
                {
                    "label": {"sv": "Gå vidare", "en": "Continue"},
                    "next": "scene_two",
                },
            ],
        },
        # ...
        "happy_end": {
            "text": {
                "sv": "Och alla levde lyckliga.",
                "en": "And they all lived happily.",
            },
            "mood": "happy",
            "ending": True,
            "ending_type": "happy",
        },
    },
}
```

### Node fields

| Field | Required | Description |
|-------|----------|-------------|
| `text` | yes | `{"sv": "...", "en": "..."}` — narration for this scene |
| `choices` | no* | List of 1-5 choice dicts. *Omit only for endings. |
| `mood` | no | LED colour mood: `warm`, `tense`, `happy`, `wonder`, `calm`. Default `calm`. |
| `ending` | no | `True` marks this as a terminal node. |
| `ending_type` | no | Flavour tag: `gentle`, `happy`, `adventurous`, `classic`. |
| `sfx` | no | Sound effect key to play when entering this node. |

### Choice fields

| Field | Required | Description |
|-------|----------|-------------|
| `label` | yes | `{"sv": "...", "en": "..."}` — short text shown next to the arcade button |
| `next` | yes | Node ID to transition to |

**Choice label language:**

Write labels in **imperative** form — they are button commands:
- "Göm dig!", "Spring!", "Plocka bär", "Follow the path", "Run!"

The TTS generator constructs narrated choice sentences differently per language to ensure correct grammar:

- **Swedish:** "Göm dig genom att trycka på grön." — label first (imperative), then button instruction. No conjugation needed.
- **English:** "Press green to hide." — button first, then label lowercased with "to".

### Structural rules

- **Node IDs** are `snake_case`, unique within a story.
- **1-5 choices** per node — maps to the 5 arcade buttons (green, blue, white, yellow, red).
- **2-3 choices** is the sweet spot for a 4-year-old.
- **1 choice** works as a narrative beat ("continue").
- **No dead ends** — every branch must lead somewhere. Every non-ending node needs choices.
- **Diamonds are fine** — branches can converge at shared nodes.
- **Max depth ~12 nodes per path** — keeps playthrough under 5 minutes.
- **15-30 total nodes** — enough branching for 3-4 distinct paths.

## Writing for TTS

All narration and choice labels are spoken aloud by Piper TTS. The text you write is the exact input to the speech synthesiser. This makes pronunciation a first-class concern.

### Localising names

**This is critical.** TTS voices can only pronounce names that follow their language's phonetic rules. A Swedish voice cannot pronounce "McGregor" — it comes out garbled and incomprehensible to a child.

**The rule: every name in each language version must be pronounceable by that language's TTS voice.**

When adapting source material, map foreign names to native equivalents that preserve the character's tone and feel:

| Principle | Example |
|-----------|---------|
| Use the established translation if one exists | Peter Rabbit → Pelle Kanin (sv) |
| Translate descriptive names | Mr McGregor → herr Grävling (sv) — "badger", fitting for a grumpy gardener |
| Adapt phonetically when no translation exists | "Charlotte" → "Charlotta" (sv) |
| Keep names that already work in both languages | "Mamma", "Anna", "Erik" |

**For famous characters** (e.g. established literary characters with well-known translated names), use the canonical translation for that language. Swedish publishing has a long tradition of localising children's characters — look it up.

**For original characters** you create, pick names that work in both languages from the start. Nordic names like Astrid, Signe, Viggo, Alma are pronounceable in both Swedish and English.

**For names from the source material with no established translation**, create a Swedish name that:
- Has a similar feel (friendly, grumpy, silly, regal)
- Uses only Swedish phonetics (å, ä, ö are fine — they help pronunciation)
- Is simple enough for a 3-5 year old to follow

### How to verify pronunciation

1. Generate TTS: `uv run python tools/generate_story_tts.py`
2. Start the preview: `uv run python tools/story_preview.py`
3. Open `http://localhost:8033` in your browser.
4. Click through every node in **both** SV and EN.
5. Listen for:
   - Names that sound garbled or unrecognisable
   - Sentences that run together without natural pauses
   - Words that are stressed incorrectly
6. Fix the text, regenerate (`--force` to regenerate everything), listen again.

Use `--story my_story` to regenerate only your story during iteration:
```bash
uv run python tools/generate_story_tts.py --force --story my_story
```

### Writing tips for natural TTS

- **Short sentences.** The audience is 3-5 years old and TTS handles short sentences better.
- **Punctuation controls pacing.** A period creates a full pause. A comma creates a brief pause. An exclamation mark adds energy. Use them deliberately.
- **Avoid abbreviations.** Write "herr" not "hr", "doktor" not "dr".
- **Spell out sounds.** "Atjoo!" not "Achoo!" for Swedish. "Brrr" works in both.
- **Test every node.** A sentence that reads well on screen may sound wrong spoken aloud.

### Pacing and prosody

The TTS generator automatically applies storytelling-friendly pacing:

- **Slower speech rate** — 20% slower than default (suitable for ages 3-5)
- **Inter-sentence pauses** — 0.4s of silence between sentences for breathing room
- **Dramatic pause markers** — `{pause}` in text inserts a 0.8s pause

These defaults produce narration that sounds like someone *telling* a story, not reading a text aloud. A child needs time to absorb each sentence before the next one begins.

#### Using `{pause}` markers

Place `{pause}` anywhere in the text to insert a longer pause. This is stripped before synthesis — it never appears on screen or gets spoken.

```python
"text": {
    "sv": "Pelle sprang så fort han kunde! {pause} Han tappade sina skor bland kålhuvudena.",
    "en": "Peter ran as fast as he could! {pause} He lost his shoes among the cabbages.",
}
```

You can specify a custom duration in seconds: `{pause 1.5}` for a 1.5-second pause. Use longer pauses for dramatic moments (a door opening, a sudden sound, a big reveal).

**When to use pauses:**
- Before a surprise or reveal: `"Allt var tyst. {pause} Plötsligt hördes ett ljud!"`
- Before direct speech after a colon: `"En arg röst ropade: {pause} Stanna tjuv!"`
- Between a scene change: `"De gick in i skogen. {pause} Det var mörkt där inne."`
- After a sound effect cue: `"Atjoo! {pause} Herr Grävling vände sig om."`
- Before an emotional beat: `"Pelle såg grinden. {pause} Han var nästan hemma!"`

Colons deserve special attention. TTS engines often rush through a colon without enough pause, making direct speech blend into the preceding sentence. Always add `{pause}` after a colon that introduces spoken words.

**When NOT to use pauses:**
- Between every sentence (the automatic inter-sentence silence handles this)
- In choice labels (these should be concise and direct)

#### Per-story prosody tuning

Each story can override the global defaults via a `prosody` key:

```python
STORY = {
    "id": "my_story",
    # ...
    "prosody": {
        "length_scale": 1.3,        # 30% slower (default: 1.2)
        "sentence_silence": 0.5,     # 500ms between sentences (default: 0.4)
    },
}
```

| Setting | Default | Range | Effect |
|---------|---------|-------|--------|
| `length_scale` | 1.2 | 0.8-1.5 | Speech rate. Higher = slower. 1.0 is normal speed. |
| `sentence_silence` | 0.4 | 0-1.0 | Seconds of silence between sentences. |

Start with the defaults. Only tune if the preview sounds too fast or too slow for your story's mood. A calm bedtime story might use `1.3`; an action sequence could drop to `1.1`.

## Adapting public domain works

Good sources for age-appropriate stories:
- **Beatrix Potter** — short animal tales, simple vocabulary, public domain
- **Aesop's Fables** — very short, clear morals, easy to branch
- **Swedish folk tales** — Elsa Beskow works (check copyright status per work)
- **Grimm's Fairy Tales** — simplify heavily for ages 3-5, soften dark elements

### Adaptation checklist

1. **Read the original.** Identify the core narrative arc and key scenes.
2. **Simplify vocabulary.** Target a 3-5 year old. Short words, concrete concepts.
3. **Map all names** to each language (see [Localising names](#localising-names) above).
4. **Design branches.** Where can the child make a meaningful choice? Aim for 2-3 choices at key moments.
5. **Write all endings as positive.** No punishment, no fail states. Even "short" endings are happy.
6. **Third-person narration.** "Peter ran to the gate" not "You ran to the gate" (more natural for this age group).
7. **Generate TTS and review** every node in both languages before considering the story done.

### Branch design tips

```
        start
       /     \
    path_a   path_b        ← major choice (2-3 options)
      |        |
    scene    scene          ← narrative beats (1 option = "continue")
      |       / \
    merge  opt1  opt2       ← branches can converge (diamonds)
      |      |    |
    climax   |   ending_1   ← some paths are shorter
      |      |
    ending_2 ending_3       ← aim for 3-4 distinct endings
```

- **Give every path a satisfying ending.** The "safe" choice should not feel boring.
- **5-8 nodes per playthrough** keeps it under 5 minutes.
- **Use `mood` to create emotional contrast** — a `tense` chase scene hitting a `happy` ending feels rewarding.
- **Replay value** comes from branches the child hasn't explored yet.

## File structure

```
assets/stories/my_story/
    script.py               # story script (required)
    sfx/                    # optional sound effects
        door_creak.wav
        splash.wav

# After TTS generation:
build/story_tts/
    sv/story_my_story_opening.wav
    sv/story_my_story_opening_choices.wav
    en/story_my_story_opening.wav
    en/story_my_story_opening_choices.wav
    ...
```

## Testing

Run the story rules tests to validate all stories:

```bash
uv run pytest tests/test_story_rules.py -v
```

The test suite checks:
- All nodes are reachable from the start node
- All choice targets exist
- Every non-ending node has choices
- Every ending node has `ending: True`
- Both `sv` and `en` text exist for every node and choice label
