# UX Guidelines for Bodn (ESP32 Learning Box)

These guidelines are for designing interactions, screens, and game modes for **Bodn**, a small battery‑powered learning and play box for a ~4‑year‑old. They are distilled from research on UX for kids, preschool game design, tiny TFT UI design, and tangible interfaces.

## 1. Target user & context

- Primary user: **soon 4‑year‑old child**; can recognize colors, simple shapes, and very simple icons, but not read text reliably.
- Secondary users: parents/caregivers configuring the device, and future‑you extending features.
- Context: child typically plays **at home**, often with a parent nearby, for short sessions (5–20 minutes).

Design priorities:
- Joy and **sense of control** for the child.
- Clarity and **predictability** of what inputs do.
- Low cognitive load; depth comes from repetition and variation, not complex UI.

## 2. Screen design

### Displays

| Display | Size | Resolution | Orientation | Role |
|---------|------|-----------|-------------|------|
| Primary | 2.8" ILI9341 | 320×240 | Landscape | Game UI, menus, all child‑facing interaction |
| Secondary | 1.8" ST7735 | 128×160 | Portrait | Ambient info: clock, session timer, idle animations |

The primary display has generous space in landscape. Use it as a **stage**, not a dashboard — fill with big visuals and leave breathing room.

The secondary display is small and always visible. Keep it simple: one piece of info at a time, large text, no interaction.

### 2.1 General rules

- One **primary concept per screen** (one game mode, one rule, one big feedback animation).
- Use **large, high‑contrast graphics**; no thin lines or small fonts.
- Avoid text for the child; if needed, use **1–2 short words max** with large font (e.g. "GO", "STOP").
- At `font_scale=3` (24 px) the primary fits ~13 characters per line — enough for short labels.
- Prefer **pictograms** (e.g. ear = listen, mouth = speak, star = success, X = fail).
- Never rely on color alone; pair color with shape/icon (e.g. red square, green circle).

### 2.2 Layout patterns — primary display (landscape 320×240)

Use a small set of repeatable layouts so the child learns them by feel:

- **Home / mode select**: icon centered with mode name below. Left/right arrow hints when multiple modes available. The wide format gives room for generous padding around the icon.
- **Game in progress — centered**: a single large graphic fills most of the screen. A narrow status strip at top or bottom for timer/score. Good for focused activities (Rule Follow, success/fail feedback).
- **Game in progress — split**: left half shows visual feedback (the pattern, the cue), right half shows controls or the child's progress. Separated by a clear vertical divide or color change. Good for multi‑step activities (Pattern Copy, Sound Mixer).
- **Success / try again**:
  - Success: big symbol (star, smiley, treasure chest), brief animation, bright colors. Use the full width for impact.
  - Try again: softer symbol (cloud, question mark), muted colors; avoid anything that looks like failure/shame.

### 2.3 Layout patterns — secondary display (portrait 128×160)

The secondary display is passive — the child doesn't interact with it directly.

- **Clock**: large time (HH:MM) centered, date below. Always readable at a glance.
- **Session timer**: countdown or progress bar during active play. Big enough to see from across the room.
- **Idle animation**: gentle breathing colors or slow pattern while waiting. Signals "I'm alive" without demanding attention.

## 3. Physical input & feedback

The **buttons, encoders, and switches are the primary interface**. Design assumes the child often looks at hands first, screen second.

### 3.1 Buttons & encoders

- Map 1–4 **core actions** to physical inputs in each mode; ignore the rest or keep them consistent between modes.
- Use **consistent mapping across modes** where possible:
  - Example: left encoder = "scroll/select", right encoder = "change value".
  - Example: top row buttons = game actions, bottom row = back / confirm.
- For a 4‑year‑old, prefer **single‑press interactions** over complex combos. Long‑presses are acceptable for hidden parent features.

### 3.3 Hold-to-pause (nav encoder)

In game modes, the nav encoder button requires a **~1.5 second hold** to open the pause menu. This prevents accidental exits during play — a 4‑year‑old will press and twist everything constantly.

- **Quick clicks are ignored** during gameplay (no action, no error — just absorbed).
- **During the hold**, a thin cyan progress bar fills across the top of the screen, giving clear feedback that something is happening.
- **On completion**, the bar flashes white and the pause menu opens.
- The **home screen keeps quick-click** for entering modes — hold-to-pause only applies inside game/activity screens.
- Implementation: `PauseMenu` reads hold detection from `GestureDetector` (via `InputState.gestures`), handles the progress bar rendering, and the menu navigation. Game screens call `self._pause.update(inp, frame)` every frame and check `is_open` / `is_holding` to skip game logic. No per-screen hold management needed.
- New game modes **must** use `PauseMenu` for the nav encoder instead of checking `enc_btn_pressed[NAV]` directly.

### 3.2 Feedback

Every meaningful input should trigger **immediate multimodal feedback**:

- Visual: brief color flash, icon change, or small movement.
- Audio: short click, beep, or voiced cue.
- Optional: LED above the button mirrors the action.

No input should feel like it "did nothing".

## 4. Game and interaction design principles

Games should exercise **executive functions** (working memory, inhibition, cognitive flexibility) in age‑appropriate ways.

### 4.1 Working memory

- Use short sequences of 2–5 steps for Pattern Copy games.
- Show and play **one item at a time**; give a brief pause before asking for reproduction.
- Keep the mapping between cue and action simple (color ↔ button, sound ↔ button).

### 4.2 Inhibition control

- Include simple rules like "press only when you see/hear X" ("Simon Says" style).
- Occasionally mix in "no‑go" cues (e.g. red X) where the correct action is **not pressing anything**.
- Give gentle feedback when inhibition fails ("Oops, that was a tricky one!" with a soft sound).

### 4.3 Cognitive flexibility

- Introduce **rule switching** gradually:
  - First rounds: one rule per session.
  - Later: show a big icon on screen that means "new rule" and explain verbally.
- Avoid switching rules mid‑sequence for this age; switch **between rounds**, not inside them.

### 4.4 Sessions & pacing

- Target 5–15 minute play sessions.
- Prefer many **short rounds** with clear win feedback over a single long challenge.
- Offer a gentle "break" suggestion after several rounds (calm animation, softer music).

## 5. Modes (examples for Bodn)

These ideas should follow the above principles.

### 5.1 Pattern Copy ("Simon" style)

- Device plays a sequence of lights/sounds; child reproduces via buttons.
- Difficulty controls:
  - Sequence length.
  - Speed of playback.
  - Whether visual cues on the screen remain visible during reproduction.
- UX specifics:
  - Use 2–4 buttons only for this mode.
  - Show current step index as simple dots or blocks.

### 5.2 Rule Follow

- Screen shows the **current rule** as a big icon (e.g. ear + green dot = "press when you HEAR high beep").
- Child reacts to streams of cues; sometimes the correct action is "do nothing".
- After a few rounds, change the rule and show a big transition (new icon, special sound).

### 5.3 Sound Mixer / Voice Play

- Flow:
  1. Record a short sample (1–2 seconds) when a big mic icon is shown.
  2. Let the child apply effects with encoders (faster/slower, higher/lower, echo).
  3. Visualize effect choice as simple icons (arrow up/down for pitch, clock for speed).
- This mode is **exploratory**: no win/lose state, just playful cause‑and‑effect.

## 6. Parental controls & WiFi

The device should feel offline and toy‑like to the child. WiFi exists mainly for parents.

### 6.1 Access model

- WiFi **off by default** to save battery and reduce exposure.
- Enable WiFi via a hidden gesture (e.g. hold two specific buttons for 5 seconds).
- Show a small, unobtrusive WiFi icon when active; do not change the core kid UX.

### 6.2 Parent web UI

- Served over local network only (no external cloud).
- Simple, single‑page interface with large controls:
  - Toggle which modes are available (Pattern Copy, Rule Follow, etc.).
  - Set difficulty caps (max sequence length, max playback speed).
  - View basic usage info (number of rounds, last session time).
- Optional: a simple PIN to change settings.

## 7. Text and typography

### 7.1 Letter case

Use **title case** (first letter uppercase, rest lowercase) for all child-facing labels: mode names, game feedback, card labels. Examples: "Katt", "Din tur!", "Bra jobbat!".

**Do not use ALL CAPS for labels.** Research shows that 4-year-olds recognize uppercase letters first (Piasta, 2014; Treiman & Kessler, 2006), but 95% of printed text is lowercase. Title case gives the child the uppercase anchor they recognize while building familiarity with the lowercase letterforms they will encounter in books. ALL CAPS builds a habit that must be unlearned.

Exceptions where ALL CAPS is acceptable:
- Single-letter labels (button labels like "A", "B")
- Very short exclamations used as visual impact, not reading practice (e.g. "GO", "STOP" — but prefer icons over text)

The `mode_*` keys in `lang/sv.py` and `lang/en.py` are stored lowercase; the home screen renders them with `.capitalize()` at display time.

### 7.2 Bilingual labels

On **printed materials** (NFC cards, card faces), show both languages simultaneously: "Katt / Cat". Both labels use equal font size. This is supported by dual-language labeling research: translation equivalents bootstrap vocabulary acquisition in both languages (Tan et al., 2024), and bilingual children distinguish their languages from birth (Byers-Heinlein & Lew-Williams, 2013).

On **device screens**, the UI shows one language at a time (switched via settings). Simultaneous dual-language labels would exceed the 13-character line limit at `font_scale=3` and violate the "1-2 short words" rule. The language switch in settings gives the parent control over which language the child is immersed in during a session.

**Consistency rule:** the same word should always appear in the same case and form across cards, device UI, and TTS audio. If a card says "Katt", the device screen should say "Katt" (not "KATT" or "katt").

## 8. Visual and audio style

### 8.1 Visuals

- Bold, flat colors; avoid gradients and visual noise.
- Consistent palette across modes (same color always means the same thing when possible).
- Icons should be **simple silhouettes** recognizable at a glance.

### 8.2 Audio

- Use short, distinctive sounds:
  - Click / soft beep for button presses.
  - Rising chime for success; falling or "question" tone for try‑again.
- Keep volume comfortable and avoid harsh, high‑frequency sounds.

## 9. Accessibility & robustness

- Assume the device will be used with **small hands and limited precision**.
- Physical controls should tolerate "imprecise" presses and spins.
- Software should be robust to spamming: multiple rapid button presses should not break the state machine.

