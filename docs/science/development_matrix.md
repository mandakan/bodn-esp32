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
| Mystery Box | | | | No memory or inhibition demands — pure exploration |
| Flöde | ○ | | | Mild WM for remembering gap positions |
| Garden of Life | | | | Observation-only; no EF demand |
| Soundboard | | | | Free-form; no EF demand |
| Spaceship | ● | ● | ◉ | Hold scenario in mind (WM), wait for right input (IC), different scenarios need different actions (CF) |
| Story Mode | ● | | | Remember earlier scenes to inform choices (WM) |
| High-Five Friends | ○ | ● | | Resist premature taps (IC); mild WM for tracking score/rhythm |
| Sequencer | ◉ | | ● | Build and hold patterns in mind (WM), switch between edit/play modes (CF) |
| *Record & Replay* | ● | | | Remember what to record and play back |

### Cognitive Development

| Feature | CE | PR | SR | ST | PS | Notes |
|---------|:--:|:--:|:--:|:--:|:--:|-------|
| Simon | | ● | | ◉ | | Reproduce sequence in exact order |
| Rule Follow | | | | | | Rule-based, not pattern/spatial |
| Mystery Box | ◉ | ● | | | | "I press these → that happens"; discover combo patterns |
| Flöde | | | ◉ | ● | ◉ | Align gaps spatially; sequential segment adjustment; trial-and-error |
| Garden of Life | ● | ◉ | | | | Watch patterns emerge; placement affects evolution |
| Soundboard | ● | | | | | Button → sound (cause-effect) |
| Spaceship | | | | | ○ | Mild problem-solving when matching scenario to action |
| Story Mode | ● | | | ● | | Choices have narrative consequences (CE); story arc is sequential (ST) |
| High-Five Friends | ● | | | | | Button → sound/animation (CE); no pattern or spatial element |
| Sequencer | ● | ◉ | | ◉ | ● | Build patterns step by step; debug sequences |
| *Record & Replay* | ● | | | ○ | | Voice causes recording; sequential playback |

### Sensorimotor Development

| Feature | FM | HC | AP | VP | Notes |
|---------|:--:|:--:|:--:|:--:|-------|
| Simon | ○ | ● | ● | ● | Map screen colors to physical buttons; each step has a distinct tone |
| Rule Follow | ○ | ● | | ● | Watch stimulus, press matching button |
| Mystery Box | ○ | | | ◉ | Rich color feedback fills the screen |
| Flöde | ● | ● | | ● | Encoder precision needed; watch gap alignment |
| Garden of Life | ○ | | | ◉ | Rich visual tracking of evolving grid |
| Soundboard | ○ | | ◉ | | Core mechanic is listening to and distinguishing sounds |
| Spaceship | ● | ● | ● | ● | Multiple input types + visual cues + audio TTS |
| Story Mode | ○ | | ◉ | ● | Simple button press (FM); listen to narration (AP); mood colour wash + text (VP) |
| High-Five Friends | ○ | ◉ | ● | ● | Target-press coordination (HC); celebration/miss sounds (AP); track lit button (VP) |
| Sequencer | ● | ● | ● | ● | Precise input, visual-audio feedback loop |
| *Record & Replay* | ○ | | ◉ | | Listen to own voice, discriminate recordings |

### Language & Communication

| Feature | LC | BL | Notes |
|---------|:--:|:--:|-------|
| Simon | | ○ | UI labels in selected language |
| Rule Follow | | ○ | Rule names in selected language |
| Mystery Box | | | Wordless interaction |
| Flöde | | ○ | UI labels only |
| Garden of Life | | ○ | UI labels only |
| Soundboard | ○ | ○ | Themed sound banks may include words |
| Spaceship | ◉ | ○ | TTS instructions drive gameplay; must listen and understand |
| Story Mode | ◉ | ◉ | Full narration + choices in both languages; must listen to choose meaningfully |
| High-Five Friends | | ○ | Animal names in selected language; UI labels |
| Sequencer | | ○ | UI labels only |
| *Record & Replay* | ● | ● | Hear and produce speech in both languages |

### Social-Emotional Development

| Feature | SReg | PE | IP | Notes |
|---------|:----:|:--:|:--:|-------|
| Simon | ● | ● | | Handle wrong-answer frustration; try again |
| Rule Follow | ◉ | ○ | | Manage impulse to press "obvious" button |
| Mystery Box | | | | No frustration possible — everything works |
| Flöde | | ◉ | | Puzzles require sustained effort through difficulty |
| Garden of Life | ○ | | | Patience in watching slow evolution |
| Soundboard | | | | Free-form, no emotional challenge |
| Spaceship | ● | ○ | ◉ | Wait for right moment; pretend to be a captain |
| Story Mode | ○ | ○ | ◉ | Wait through narration (SReg); replay for all endings (PE); guide character through narrative world (IP) |
| High-Five Friends | ● | ● | | Handle misses gracefully (SReg); keep trying to beat high score (PE) |
| Sequencer | | ● | ● | Debug patience; pretend to be a musician/programmer |
| *Record & Replay* | | | ○ | Mild pretend-play with voice |

### Creative & Exploratory

| Feature | OE | DT | CX | Notes |
|---------|:--:|:--:|:--:|-------|
| Simon | | | | Fixed goal, no creative latitude |
| Rule Follow | | | | Fixed rules, no creative latitude |
| Mystery Box | ◉ | ◉ | | Unlimited combos to discover; no right answer |
| Flöde | | | | Goal-directed puzzle |
| Garden of Life | ◉ | ● | ● | Endless seed placements; emergent "art" |
| Soundboard | ◉ | | ◉ | Browse freely; create sound combinations |
| Spaceship | | | | Narrative-driven, not open-ended |
| Story Mode | | | | Goal-directed narrative; no creative latitude |
| High-Five Friends | | | | Fixed goal (tap the lit button); no creative latitude |
| Sequencer | | ◉ | ◉ | Compose original patterns; divergent solutions |
| *Record & Replay* | ● | | ◉ | Record anything; creative voice play |

---

## Coverage Analysis

### Well-Covered Aspects (3+ features at ● or ◉)

| Aspect | Primary (◉) | Significant (●) | Total strong |
|--------|:-----------:|:----------------:|:------------:|
| Visual Processing (VP) | 2 | 6 | 8 |
| Working Memory (WM) | 2 | 3 | 5 |
| Cause & Effect (CE) | 1 | 5 | 6 |
| Pattern Recognition (PR) | 1 | 3 | 4 |
| Hand-Eye Coordination (HC) | 1 | 4 | 5 |
| Open Exploration (OE) | 3 | 0 | 3 |
| Self-Regulation (SReg) | 1 | 3 | 4 |
| Cognitive Flexibility (CF) | 2 | 1 | 3 |
| Inhibitory Control (IC) | 1 | 2 | 3 |
| Listening Comprehension (LC) | 2 | 0 | 2 |
| Bilingual Exposure (BL) | 1 | 0 | 1+ |
| Imaginative Play (IP) | 2 | 1 | 3 |
| Auditory Processing (AP) | 1 | 3 | 4 |
| Sequential Thinking (ST) | 2 | 2 | 4 |
| Persistence (PE) | 1 | 3 | 4 |

### Gaps (1 or fewer features at ◉ or ●)

| Aspect | Current state | Suggested feature |
|--------|---------------|-------------------|
| **Spatial Reasoning (SR)** | Only Flöde | Building/construction mode; tangram puzzles |
| **Problem Solving (PS)** | Only Flöde + Sequencer (debugging) | More puzzle types; NFC scavenger hunts |
| **Bilingual Exposure (BL)** | Story Mode + passive UI labels; NFC cards use dual-language labels (sv/en) | Language-switch game; more card sets with dual labels |
| **Fine Motor (FM)** | Mostly incidental (Flöde, Sequencer significant) | NFC card manipulation/sorting; tracing mode |

---

## Developmental Timeline

How Böðn serves the child as they grow.

### Age 3–4: Exploration & Cause-Effect

The foundation — everything should produce immediate, rewarding feedback.

| Feature | Role | Difficulty |
|---------|------|------------|
| Mystery Box | **Core** — endless safe exploration | No difficulty; everything works |
| Soundboard | **Core** — button → sound mapping | Free-form |
| Garden of Life | **Core** — watch pretty patterns emerge | Just press and observe |
| High-Five Friends | **Core** — tap the lit button for animal friends | Easy; long reaction windows |
| Simon | Introduce gently — 2-step sequences | Easiest |
| Spaceship | Exposure — long timeouts, few scenarios | Easiest |
| Story Mode | **Introduce** — simple stories, 2 choices, short paths | Easy |

### Age 4–5: Executive Functions Emerge

The child can follow rules, hold short sequences, and switch between ideas.

| Feature | Role | Difficulty |
|---------|------|------------|
| Simon | **Growing challenge** — 3–4 step sequences | Medium |
| Rule Follow | **Introduce** — start with mostly MATCH rule | Easy |
| Spaceship | **Growing challenge** — 5 scenario types, medium timeouts | Medium |
| Story Mode | **Growing** — longer stories, 3 choices, remember plot points | Medium |
| Flöde | **Introduce** — levels 1–2 (1–2 segments) | Easy |
| Mystery Box | Still engaging — modifier discovery deepens | Same |

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

### Age 6–7+: Mastery & Creativity

Features shift from guided challenge toward creative expression and composition.

| Feature | Role | Difficulty |
|---------|------|------------|
| Sequencer | **Core** — complex patterns, programming concepts | Growing |
| Flöde | Levels 5–6 (full difficulty) | Hard |
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

#### NFC-1. Sortera — Classification Game

**Primary targets:** CF, IC, PR, BL
**Fills gaps in:** Cognitive flexibility (tangible DCCS), bilingual exposure, fine motor
**Concept:** Scan NFC cards to sort by announced categories; rules switch mid-game
(colour → shape → animal). Direct tangible implementation of the DCCS task.
**References:** Zelazo (2006) DCCS; Diamond (2013) EF training; Antle (2013) TUI for children

#### NFC-2. Saga Builder — Tangible Storytelling

**Primary targets:** ST, IP, LC, BL, CX
**Fills gaps in:** Bilingual exposure, sequential thinking, creative expression
**Concept:** Scan character/setting/object NFC cards to build stories. Order matters;
each combination triggers different narration in Swedish or English.
**References:** Sylla et al. (2012) TinkRBook; Kumpulainen & Lipponen (2012) physical story props

#### NFC-3. NFC Soundboard Extension

**Primary targets:** AP, CE, CX, OE
**Fills gaps in:** Auditory processing (tangible layer), creative expression
**Concept:** NFC cards as physical instrument/sound collection. Scan to trigger,
layer multiple cards for composition.
**References:** Paivio (1986) dual coding theory; multisensory association

#### NFC-4. Memory Match

**Primary targets:** WM, HC, FM, VP
**Fills gaps in:** Fine motor (physical card retrieval), working memory (extended action sequence)
**Concept:** Device plays a stimulus; child finds and scans the matching card from
a physical spread. Physical search adds motor planning to the memory task.
**References:** Manches & O'Malley (2012) tangible manipulation and learning

#### NFC-5. Vocabulary Explorer — Bilingual Word Cards

**Primary targets:** BL, LC, AP
**Fills gaps in:** Bilingual exposure (primary-level), listening comprehension
**Concept:** Picture cards with NFC tags. Scan to hear the word in Swedish; scan
again for English. Quiz mode: device says a word, child scans the right card.
**References:** Wohlwend (2015) physical-digital literacy; Bialystok (2011) bilingual EF advantage

#### NFC-6. Free Discovery / Tag Registry

**Primary targets:** OE, CE, DT
**Concept:** First-time tags get a random colour + sound + animation. Child builds
a personal collection by tagging household objects, toys, and drawings.
**References:** Bonawitz et al. (2011) exploration-driven discovery

#### NFC-7. Räkna — Progressive Math with Tangible Numbers

**Primary targets:** WM, ST, PR, PS, LC, BL, FM
**Fills gaps in:** Problem solving (tangible math), fine motor, bilingual exposure
**Concept:** Dot-pattern NFC cards (1--10) for progressive number sense: subitising
→ quantity matching → more/less → addition → subtraction → symbolic equations.
Follows Bruner's CPA progression (concrete tokens → pictorial dots → abstract
numerals). Six levels spanning ages 3--7. Self-paced, never timed.
**References:** Duncan et al. (2007) early math as #1 achievement predictor;
Clements & Sarama (2014) learning trajectories; Siegler & Ramani (2009) linear
number board games; Jordan et al. (2009) kindergarten number sense; Gelman &
Gallistel (1978) counting principles; Bruner (1966) CPA; Willingham (2017)
manipulatives and concreteness fading

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
