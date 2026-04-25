# Böðn Development Matrix

*Mapping features to developmental domains for ages 3–7*

## How to Read This Document

This matrix tracks how each Böðn feature supports established child development
domains. Use it to evaluate coverage, identify gaps, and plan new features.

**Coverage levels:**

| Symbol | Meaning |
|--------|---------|
| ◉ | **Primary** — this aspect drove the feature's design |
| ● | **Significant** — meaningfully exercised during play |
| ○ | **Incidental** — present but not a deliberate design goal |
| | Not applicable or negligible |

*Italic* features are planned (not yet implemented).

---

## Developmental Aspects

### A. Executive Functions

The "air traffic control system" of the brain — the strongest predictor of school
readiness, outperforming IQ (Diamond, 2013; Moffitt et al., 2011).

| Code | Aspect | Description |
|------|--------|-------------|
| **WM** | Working Memory | Hold and manipulate information in mind (e.g., remember a 4-step sequence) |
| **IC** | Inhibitory Control | Suppress automatic responses (e.g., resist pressing the obvious button) |
| **CF** | Cognitive Flexibility | Switch between rules or perspectives (e.g., "match" vs "opposite") |

### B. Cognitive Development

| Code | Aspect | Description |
|------|--------|-------------|
| **CE** | Cause & Effect | Understand that actions produce outcomes |
| **PR** | Pattern Recognition | Identify regularities, sequences, and emergent structures |
| **SR** | Spatial Reasoning | Understand position, alignment, and spatial relationships |
| **ST** | Sequential Thinking | Understand and reproduce ordered steps |
| **PS** | Problem Solving | Plan, attempt, and adjust strategies toward a goal |

### C. Sensorimotor Development

| Code | Aspect | Description |
|------|--------|-------------|
| **FM** | Fine Motor Skills | Precise finger/hand movements (buttons, encoders) |
| **HC** | Hand-Eye Coordination | Coordinate visual input with motor output |
| **AP** | Auditory Processing | Discriminate, categorize, and respond to sounds |
| **VP** | Visual Processing | Track, distinguish, and interpret visual information |

### D. Language & Communication

| Code | Aspect | Description |
|------|--------|-------------|
| **LC** | Listening Comprehension | Understand spoken instructions and narratives |
| **BL** | Bilingual Exposure | Engagement with two languages (Swedish + English) |

### E. Social-Emotional Development

| Code | Aspect | Description |
|------|--------|-------------|
| **SReg** | Self-Regulation | Manage emotions, wait, and tolerate frustration |
| **PE** | Persistence | Continue effort despite difficulty or initial failure |
| **IP** | Imaginative Play | Engage in pretend scenarios and role-play |

### F. Creative & Exploratory

| Code | Aspect | Description |
|------|--------|-------------|
| **OE** | Open Exploration | Self-directed discovery without fixed goals |
| **DT** | Divergent Thinking | Generate multiple approaches or ideas |
| **CX** | Creative Expression | Produce original auditory, visual, or kinetic output |

---

## Feature × Aspect Matrix

### Executive Functions

| Feature | WM | IC | CF | Notes |
|---------|:--:|:--:|:--:|-------|
| Simon | ◉ | ○ | | Sequence recall is pure WM; waiting for turn is mild IC |
| Rule Follow | ● | ◉ | ◉ | Fight the impulse (IC), switch rules mid-game (CF) |
| Mystery Box | ○ | | ○ | Recipe book invites planning ("which two haven't I tried?", WM); modifier toggles unlock at 5 / 10 / all-singles and reframe the rules (CF) |
| Flöde | ○ | | | Mild WM for remembering gap positions |
| Garden of Life | | | | Observation-only; no EF demand |
| Soundboard | | | | Free-form; no EF demand |
| Tone Lab | ○ | | ○ | Hold current sound-shape in mind while layering effects (WM); switch focus between pitch, timbre, and effect buttons (CF) |
| Spaceship | ● | ● | ◉ | Hold scenario in mind (WM), wait for right input (IC), different scenarios need different actions (CF) |
| Story Mode | ● | | | Remember earlier scenes to inform choices (WM) |
| High-Five Friends | ○ | ● | | Resist premature taps (IC); mild WM for tracking score/rhythm |
| Sequencer | ◉ | | ● | Build and hold patterns in mind (WM), switch between edit/play modes (CF) |
| *Record & Replay* | ● | | | Remember what to record and play back |
| Sortera | ○ | ● | ◉ | Remember current rule (WM); resist sorting by previous dimension (IC); rule switches demand flexibility (CF) — tangible DCCS |
| Räkna | ● | ○ | ○ | Hold equation state across multiple card scans (WM); level progression from counting to symbolic equations nudges CF |
| Blippa | | | | No EF demand — every tap succeeds, nothing to hold in mind |

### Cognitive Development

| Feature | CE | PR | SR | ST | PS | Notes |
|---------|:--:|:--:|:--:|:--:|:--:|-------|
| Simon | | ● | | ◉ | | Reproduce sequence in exact order |
| Rule Follow | | | | | | Rule-based, not pattern/spatial |
| Mystery Box | ◉ | ● | | ○ | | "I press these → that happens"; magic combos are two-button sequences; recipe book reinforces pattern reliability |
| Flöde | | | ◉ | ● | ◉ | Align gaps spatially; sequential segment adjustment; trial-and-error |
| Garden of Life | ● | ◉ | | | | Watch patterns emerge; placement affects evolution |
| Soundboard | ● | | | | | Button → sound (cause-effect) |
| Tone Lab | ◉ | ○ | | | | Every input produces an immediate, reliable audible+visual change (CE); children notice which combinations make "round" vs "spiky" sounds (PR) |
| Spaceship | | | | | ○ | Mild problem-solving when matching scenario to action |
| Story Mode | ● | | | ● | | Choices have narrative consequences (CE); story arc is sequential (ST) |
| High-Five Friends | ● | | | | | Button → sound/animation (CE); no pattern or spatial element |
| Sequencer | ● | ◉ | | ◉ | ● | Build patterns step by step; debug sequences |
| *Record & Replay* | ● | | | ○ | | Voice causes recording; sequential playback |
| Sortera | ● | ◉ | | | | Card scan → feedback (CE); categorise by matching dimension (PR) |
| Räkna | ● | ◉ | ○ | ◉ | ● | Dot-pattern subitising (PR); counting and equation order (ST); build solutions step by step (PS); left-to-right number path (SR) |
| Blippa | ◉ | ○ | | | | Tightest possible tap → response loop (CE); incidental recognition of repeating card attributes across the set (PR) |

### Sensorimotor Development

| Feature | FM | HC | AP | VP | Notes |
|---------|:--:|:--:|:--:|:--:|-------|
| Simon | ○ | ● | ● | ● | Map screen colors to physical buttons; each step has a distinct tone |
| Rule Follow | ○ | ● | | ● | Watch stimulus, press matching button |
| Mystery Box | ○ | | | ◉ | Rich color feedback fills the screen |
| Flöde | ● | ● | | ● | Encoder precision needed; watch gap alignment |
| Garden of Life | ○ | | | ◉ | Rich visual tracking of evolving grid |
| Soundboard | ○ | | ◉ | | Core mechanic is listening to and distinguishing sounds |
| Tone Lab | ● | ○ | ◉ | ● | Two encoders + 13 buttons + 4 toggles = precise fingertip control (FM); pitch discrimination, timbre recognition, effect-rhythm tracking (AP); oscilloscope + morphing blob reinforce cross-modal sound-shape binding (VP, Bouba/Kiki) |
| Spaceship | ● | ● | ● | ● | Multiple input types + visual cues + audio TTS |
| Story Mode | ○ | | ◉ | ● | Simple button press (FM); listen to narration (AP); mood colour wash + text (VP) |
| High-Five Friends | ○ | ◉ | ● | ● | Target-press coordination (HC); celebration/miss sounds (AP); track lit button (VP) |
| Sequencer | ● | ● | ● | ● | Precise input, visual-audio feedback loop |
| *Record & Replay* | ○ | | ◉ | | Listen to own voice, discriminate recordings |
| Sortera | ● | | ● | ● | Card manipulation (FM); bilingual TTS reinforces audio (AP); emoji + label display (VP) |
| Räkna | ● | ○ | ● | ◉ | Handling multiple dot/numeral/operator cards (FM); bilingual number names (AP); dot patterns and numerals are the core stimulus (VP) |
| Blippa | ● | ○ | ● | ● | Card retrieval and presentation (FM); per-card blip + optional sample (AP); full-screen emoji + bilingual label (VP) |

### Language & Communication

| Feature | LC | BL | Notes |
|---------|:--:|:--:|-------|
| Simon | | ○ | UI labels in selected language |
| Rule Follow | | ○ | Rule names in selected language |
| Mystery Box | | | Wordless interaction |
| Flöde | | ○ | UI labels only |
| Garden of Life | | ○ | UI labels only |
| Soundboard | ○ | ○ | Themed sound banks may include words |
| Tone Lab | | ○ | Wordless; UI labels in selected language only |
| Spaceship | ◉ | ○ | TTS instructions drive gameplay; must listen and understand |
| Story Mode | ◉ | ◉ | Full narration + choices in both languages; must listen to choose meaningfully |
| High-Five Friends | | ○ | Animal names in selected language; UI labels |
| Sequencer | | ○ | UI labels only |
| *Record & Replay* | ● | ● | Hear and produce speech in both languages |
| Sortera | ○ | ● | Bilingual TTS says both languages on correct scan; dual-language labels on screen match physical cards |
| Räkna | ● | ● | Number names and instructions spoken in both languages; child hears quantities as well as sees them |
| Blippa | ○ | ● | Dual-language label shown on every scan; leverages the whole card stock for passive vocabulary exposure |

### Social-Emotional Development

| Feature | SReg | PE | IP | Notes |
|---------|:----:|:--:|:--:|-------|
| Simon | ● | ● | | Handle wrong-answer frustration; try again |
| Rule Follow | ◉ | ○ | | Manage impulse to press "obvious" button |
| Mystery Box | | ○ | | No failure state; collect-them-all recipe book gives a soft carrot for sustained attention without pressure |
| Flöde | | ◉ | | Puzzles require sustained effort through difficulty |
| Garden of Life | ○ | | | Patience in watching slow evolution |
| Soundboard | | | | Free-form, no emotional challenge |
| Tone Lab | | | ○ | No failure state; natural "tiny musician / sound scientist" pretend play (IP) |
| Spaceship | ● | ○ | ◉ | Wait for right moment; pretend to be a captain |
| Story Mode | ○ | ○ | ◉ | Wait through narration (SReg); replay for all endings (PE); guide character through narrative world (IP) |
| High-Five Friends | ● | ● | | Handle misses gracefully (SReg); keep trying to beat high score (PE) |
| Sequencer | | ● | ● | Debug patience; pretend to be a musician/programmer |
| *Record & Replay* | | | ○ | Mild pretend-play with voice |
| Sortera | ● | ○ | | Wait through the rule announcement (SReg); try again after a mis-sort |
| Räkna | ○ | ● | | Self-paced and never timed keeps frustration low (SReg); multi-card equations reward sustained effort (PE) |
| Blippa | | | ● | No failure state eliminates frustration; naturally invites cashier / transit-gate pretend play (IP) |

### Creative & Exploratory

| Feature | OE | DT | CX | Notes |
|---------|:--:|:--:|:--:|-------|
| Simon | | | | Fixed goal, no creative latitude |
| Rule Follow | | | | Fixed rules, no creative latitude |
| Mystery Box | ◉ | ◉ | | 16-tile recipe book + modifier unlocks shape exploration as guided play; no right answer |
| Flöde | | | | Goal-directed puzzle |
| Garden of Life | ◉ | ● | ● | Endless seed placements; emergent "art" |
| Soundboard | ◉ | | ◉ | Browse freely; create sound combinations |
| Tone Lab | ◉ | ● | ◉ | Unbounded sonic exploration (OE); pentatonic + effect stacking gives many right answers (DT); expressive sound-design as creative output (CX) |
| Spaceship | | | | Narrative-driven, not open-ended |
| Story Mode | | | | Goal-directed narrative; no creative latitude |
| High-Five Friends | | | | Fixed goal (tap the lit button); no creative latitude |
| Sequencer | | ◉ | ◉ | Compose original patterns; divergent solutions |
| *Record & Replay* | ● | | ◉ | Record anything; creative voice play |
| Sortera | ○ | | | Free-scan mode invites incidental exploration of the card set |
| Räkna | ○ | ○ | | Low-level free exploration of quantities; multiple card paths to the same total |
| Blippa | ◉ | ○ | | Any card the child owns works, with no goal — self-directed discovery is the entire mode |

---

## Coverage Analysis

Counts exclude the planned *Record & Replay* mode (italic in the tables above).
"Strong" = primary (◉) + significant (●); incidentals (○) are noted in notes but
not counted here.

### Well-Covered Aspects (3+ features at ● or ◉)

| Aspect | Primary (◉) | Significant (●) | Total strong |
|--------|:-----------:|:----------------:|:------------:|
| Visual Processing (VP) | 3 | 10 | 13 |
| Auditory Processing (AP) | 3 | 7 | 10 |
| Cause & Effect (CE) | 3 | 7 | 10 |
| Fine Motor (FM) | 0 | 7 | 7 |
| Working Memory (WM) | 2 | 4 | 6 |
| Pattern Recognition (PR) | 4 | 2 | 6 |
| Hand-Eye Coordination (HC) | 1 | 5 | 6 |
| Open Exploration (OE) | 5 | 0 | 5 |
| Self-Regulation (SReg) | 1 | 4 | 5 |
| Sequential Thinking (ST) | 3 | 2 | 5 |
| Persistence (PE) | 1 | 4 | 5 |
| Bilingual Exposure (BL) | 1 | 3 | 4 |
| Cognitive Flexibility (CF) | 3 | 1 | 4 |
| Inhibitory Control (IC) | 1 | 3 | 4 |
| Imaginative Play (IP) | 2 | 2 | 4 |
| Divergent Thinking (DT) | 2 | 2 | 4 |
| Creative Expression (CX) | 3 | 1 | 4 |
| Listening Comprehension (LC) | 2 | 1 | 3 |
| Problem Solving (PS) | 1 | 2 | 3 |

### Remaining Gaps (≤ 1 feature at ◉ or ●)

| Aspect | Current state | Suggested feature |
|--------|---------------|-------------------|
| **Spatial Reasoning (SR)** | Flöde (◉) only; Räkna's left-to-right number path is incidental | Tangram / construction puzzle mode; tangible building blocks with NFC |

Spatial reasoning is now the single under-covered domain. Every other aspect
has at least 3 features at ● or ◉ — a meaningful shift from the state before
Tone Lab and Blippa shipped, when auditory processing, cognitive flexibility,
fine motor, and bilingual exposure were all weakly covered.

---

## Developmental Timeline

How Böðn serves the child as they grow.

### Age 3–4: Exploration & Cause-Effect

The foundation — everything should produce immediate, rewarding feedback.

| Feature | Role | Difficulty |
|---------|------|------------|
| Mystery Box | **Core** — endless safe exploration | No difficulty; recipe book makes "what's left" visible without pressure |
| Soundboard | **Core** — button → sound mapping | Free-form |
| Tone Lab | **Introduce** — use only the arcade buttons and the pitch encoder | Free-form; strict pentatonic means nothing sounds wrong |
| Garden of Life | **Core** — watch pretty patterns emerge | Just press and observe |
| High-Five Friends | **Core** — tap the lit button for animal friends | Easy; long reaction windows |
| Simon | Introduce gently — 2-step sequences | Easiest |
| Spaceship | Exposure — long timeouts, few scenarios | Easiest |
| Story Mode | **Introduce** — simple stories, 2 choices, short paths | Easy |
| Sortera | **Introduce** — single-dimension sorting, no rule switches | Easiest |
| Räkna | **Introduce** — Level 1 free exploration of dot cards 1–5 | Easiest |
| Blippa | **Core** — tap any card, always works, always a response | No difficulty |

### Age 4–5: Executive Functions Emerge

The child can follow rules, hold short sequences, and switch between ideas.

| Feature | Role | Difficulty |
|---------|------|------------|
| Simon | **Growing challenge** — 3–4 step sequences | Medium |
| Rule Follow | **Introduce** — start with mostly MATCH rule | Easy |
| Spaceship | **Growing challenge** — 5 scenario types, medium timeouts | Medium |
| Story Mode | **Growing** — longer stories, 3 choices, remember plot points | Medium |
| Flöde | **Introduce** — levels 1–2 (1–2 segments) | Easy |
| Mystery Box | **Growing** — chase the recipe book; modifier toggles unlock at 5 / 10 finds, hue at all 8 singles | Easy carrot, persistent across reboots |
| Sortera | **Growing** — rule switches between colour, shape, and animal dimensions | Medium |
| Räkna | **Growing** — Levels 2–3 (quantity matching, more/less) | Easy–Medium |
| Blippa | Still engaging — card vocabulary grows with the collection | Same |
| Tone Lab | **Growing** — layer one effect at a time (vibrato, tremolo, bend) | Discover named sound-shapes |

### Age 5–6: Increasing Challenge

Longer sequences, faster rule switches, real problem-solving.

| Feature | Role | Difficulty |
|---------|------|------------|
| Simon | 5+ step sequences; speed increases | Hard |
| Rule Follow | Frequent rule switches; shorter response windows | Medium-Hard |
| Spaceship | Shorter timeouts; adaptive difficulty climbs | Medium-Hard |
| Flöde | Levels 3–4 (3–4 segments, more snap positions) | Medium |
| High-Five Friends | Faster reaction windows; longer rounds | Medium-Hard |
| Sequencer | **Introduce** — simple 4-step patterns | Easy |
| Sortera | Faster rule switches; full 16-card deck with four colour variants | Medium–Hard |
| Räkna | **Core** — Level 4 addition with dot tokens | Medium |

### Age 6–7+: Mastery & Creativity

Features shift from guided challenge toward creative expression and composition.

| Feature | Role | Difficulty |
|---------|------|------------|
| Sequencer | **Core** — complex patterns, programming concepts | Growing |
| Tone Lab | **Core** — compose expressively; stack several effects for sonic sculpting | Open-ended |
| Flöde | Levels 5–6 (full difficulty) | Hard |
| Räkna | Levels 5–6 — subtraction and symbolic equations with numerals | Growing |
| *Record & Replay* | Creative voice compositions | Open-ended |
| Rule Follow | Near-instant switches; scoring/competition | Expert |
| Garden of Life | Deliberate pattern engineering | Advanced |

---

## Future Feature Opportunities

Features that would fill developmental gaps, ordered by coverage impact.

### NFC Tangible Modes (PN532 reader + programmable tags)

NFC-tagged cards and stickers add a **tangible manipulation layer** backed by
extensive research on Tangible User Interfaces (TUI) for early childhood
(Marshall, 2007; Antle, 2013; Horn et al., 2009). The scan-and-discover
interaction requires a deliberate, embodied action sequence (find → pick up →
bring to reader → hold) that exercises fine motor skills and reinforces
intentionality. See `docs/science/nfc_tangible_learning.md` for the full research
summary.

Three NFC modes have shipped and appear in the aspect matrices above:
**Sortera** (tangible DCCS classification), **Räkna** (progressive math with
dot-pattern cards), and **Blippa** (free-play — every owned card blips with
audio + full-screen emoji, no goal, no failure state). The ideas below
remain on the wishlist.

#### NFC-1. Saga Builder — Tangible Storytelling

**Primary targets:** ST, IP, LC, BL, CX
**Fills gaps in:** Bilingual exposure, sequential thinking, creative expression
**Concept:** Scan character/setting/object NFC cards to build stories. Order matters;
each combination triggers different narration in Swedish or English.
**References:** Sylla et al. (2012) TinkRBook; Kumpulainen & Lipponen (2012) physical story props

#### NFC-2. NFC Soundboard Extension

**Primary targets:** AP, CE, CX, OE
**Fills gaps in:** Auditory processing (tangible layer), creative expression
**Concept:** NFC cards as physical instrument/sound collection. Scan to trigger,
layer multiple cards for composition.
**References:** Paivio (1986) dual coding theory; multisensory association

#### NFC-3. Memory Match

**Primary targets:** WM, HC, FM, VP
**Fills gaps in:** Fine motor (physical card retrieval), working memory (extended action sequence)
**Concept:** Device plays a stimulus; child finds and scans the matching card from
a physical spread. Physical search adds motor planning to the memory task.
**References:** Manches & O'Malley (2012) tangible manipulation and learning

#### NFC-4. Vocabulary Explorer — Bilingual Word Cards

**Primary targets:** BL, LC, AP
**Fills gaps in:** Bilingual exposure (primary-level), listening comprehension
**Concept:** Picture cards with NFC tags. Scan to hear the word in Swedish; scan
again for English. Quiz mode: device says a word, child scans the right card.
**References:** Wohlwend (2015) physical-digital literacy; Bialystok (2011) bilingual EF advantage

#### NFC-5. Foreign-Tag Blippa Extension

**Primary targets:** OE, CE, DT
**Concept:** Extend Blippa to react to non-BODN tags (hotel keys, bus passes,
household NFC stickers) with a UID-hashed colour/sound/animation — the child
"discovers" that their things have hidden identities.  Blippa v1 is scoped to
BODN-programmed cards only; this extension adds the tag-registry angle.
**References:** Bonawitz et al. (2011) exploration-driven discovery

---

### Other Future Opportunities

### 1. Rhythm Game

**Primary targets:** ST, AP, FM, PR
**Fills gaps in:** Fine motor (dedicated challenge), auditory processing (rhythmic)
**Concept:** Follow a beat pattern with buttons; create own rhythms.
**References:** Kraus & Chandrasekaran (2010) music and auditory development

### 2. Tangram / Construction Puzzle

**Primary targets:** SR, PS, FM, HC
**Fills gaps in:** Spatial reasoning (second source), problem solving
**Concept:** Arrange shapes on screen using encoder + buttons to match a target pattern.
**References:** Verdine et al. (2014) spatial assembly and math readiness

### 3. Record & Replay (planned)

**Primary targets:** CX, AP, LC, BL
**Fills gaps in:** Creative expression, listening comprehension, bilingual exposure
**Concept:** Record short voice clips, play them back with effects (pitch shift, echo).
**References:** Trainor (2005) auditory development; Gopnik (2012) scientific thinking in young children

---

## Checklist: Feature Development Review

When adding or modifying a feature, verify:

- [ ] Which developmental aspects does this feature primarily target? (Should have at least one ◉)
- [ ] Does it fill a gap in the current matrix, or duplicate existing coverage?
- [ ] Is the difficulty appropriate for the target age range?
- [ ] Does it follow the "no failure" principle for exploration modes?
- [ ] Does it provide multimodal feedback (visual + auditory + tactile)?
- [ ] Is there a clear progression path as the child grows?
- [ ] Has the matrix been updated with the new feature's row?
