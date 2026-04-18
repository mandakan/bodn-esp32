---
name: add-screen
description: Add a new UI screen (game mode, settings page, overlay, secondary content) that plugs into ScreenManager. Use whenever a mode needs its own primary-display view or secondary-display content. Covers the Screen lifecycle, dirty tracking, sprite caching in enter(), section bitmasks for multi-region screens, and the NFC tag hook. Complements add-game-mode (science docs) and perf-review (hot-path rules).
---

# Add a UI screen

Every interactive view in Bodn is a `Screen` subclass managed by
`ScreenManager` (see `firmware/bodn/ui/screen.py`). The manager runs in two
phases: `update()` for logic, `render()` for drawing, and skips the SPI push
entirely when no screen reports dirty state.

## Lifecycle

```python
class MyScreen(Screen):
    def enter(self, manager):        # pre-render sprites, allocate buffers
        ...
    def exit(self):                   # free long-lived allocations
        ...
    def on_reveal(self):              # revealed after pop — default sets _full_clear
        ...
    def update(self, inp, frame):    # state + input; NEVER draw here
        ...
    def needs_redraw(self):           # return True only when something changed
        return self._dirty
    def render(self, tft, theme, frame):  # draw; only called when dirty
        ...
```

`enter()` receives the `ScreenManager` — stash it as `self._manager` if you
need `manager.push/pop/replace/invalidate`.

## Registering the screen

1. **Mode screens** go in `firmware/bodn/ui/<mode>.py`.
2. Register in `firmware/bodn/ui/home.py`'s mode carousel (via the
   `mode_screens` dict passed to `HomeScreen`).
3. If the mode needs an icon on the home carousel, add it to
   `firmware/bodn/ui/icons.py` (`MODE_ICONS`).
4. All user-facing labels go through `i18n.t("key")` — see the
   `add-i18n-string` skill.

## Dirty state

One `_dirty` flag is fine for single-region screens (`home.py`, most
settings pages). **Multi-region screens must use a section bitmask.**
Reference pattern from `firmware/bodn/ui/demo.py:33`:

```python
_D_HEADER  = const(1)
_D_BUTTONS = const(2)
_D_ARCADE  = const(4)
_D_ALL     = const(7)

def enter(self, manager):
    self._dirty_sections = _D_ALL

def needs_redraw(self):
    return self._dirty_sections != 0

def update(self, inp, frame):
    if pressed:
        self._dirty_sections |= _D_BUTTONS   # redraw only that region

def render(self, tft, theme, frame):
    ds = self._dirty_sections
    if ds & _D_HEADER:  self._draw_header(tft, theme)
    if ds & _D_BUTTONS: self._draw_buttons(tft, theme)
    if ds & _D_ARCADE:  self._draw_arcade(tft, theme)
    self._dirty_sections = 0
```

A single boolean forces a full-screen redraw on every button press — that
is the most common perf regression in this codebase (§3.05 in
`docs/PERFORMANCE_GUIDELINES.md`).

## Sprite caching (almost always needed)

Never draw scaled icons or long text pixel-by-pixel inside `render()`.
Pre-render once in `enter()`:

```python
from bodn.ui.widgets import make_icon_sprite, make_label_sprite, blit_sprite

def enter(self, manager):
    self._icon = make_icon_sprite(emoji, scale=4, color=theme.WHITE)
    self._label = make_label_sprite(t("my_screen_title"), scale=2)

def render(self, tft, theme, frame):
    blit_sprite(tft, self._icon, 80, 40)
    blit_sprite(tft, self._label, 40, 120)
```

A scale-4 icon via `fill_rect` costs ~30 ms; `blit_sprite()` costs ~0.1 ms.
Sprite buffers >8 KB go to PSRAM automatically. `home.py` has the
reference pattern with per-mode sprite dicts. See the `sprite-cache-convert`
skill if retrofitting an existing screen.

## Animating in a narrow band

The `_spidma` module pushes 32 KB DMA chunks at 40 MHz. A dirty rect that
fits in **one chunk (≤50 full-width rows on the primary display)** costs
~1 ms; each extra chunk adds ~6.5 ms of blocking. Design animations to
stay within a narrow horizontal band, and call
`manager.request_show(x, y, w, h)` for small partial pushes that don't
need a re-render.

## Secondary display content

The 128×160 ST7735 is split into a 128×128 content zone (`y < 128`) and a
32-row status strip (`y ≥ 128`). Content screens live in
`firmware/bodn/ui/<mode>_secondary.py` and are registered via
`SecondaryManager.set_content(screen)` — see `firmware/bodn/ui/secondary.py`
and `firmware/bodn/ui/garden_secondary.py` for the pattern. Secondary
screens must stay within their zone bounds; crossing into the status strip
corrupts the battery/session indicator.

## NFC tag routing

Screens that react to NFC cards (Sortera, Räkna, launcher-style starts)
override two class attributes and one method:

```python
class MyScreen(Screen):
    nfc_modes = frozenset({"sortera"})   # tag modes this screen consumes
    nfc_low_priority = False             # True → background scanner polls slower

    def on_nfc_tag(self, parsed):
        # parsed = {"prefix": 1, "version": 1, "mode": "sortera", "id": "cat_red"}
        return True                      # True = consumed, False = fall through
```

Cooperative scanning across all modes is wired in the main loop — you only
implement the hook. See PR #143 and `firmware/bodn/nfc.py` for the scanner.

## Verification

- Pytest: pure-logic modules (rules engines, state machines) go in
  `firmware/bodn/<mode>_rules.py` and get unit-tested on the host.
- On-device: `tools/sync.sh` + REPL `import main; main.run()`.
- Perf: enable `manager.debug_perf = True` in `boot.py`; it prints
  drawn/skipped frame ratios every ~1.5 s.

## Invariants (from perf-review)

- State updates belong in `update()`, never `render()`. `render()` can be
  skipped when the frame budget is tight — state written there gets lost.
- No `import` inside hot loops; no per-frame allocations in `update` or
  `render`. Reuse buffers, cache `self.*` and module attributes as locals.
- No `tft.fill(BLACK)` in `render()` — the manager handles full clears on
  transitions. Use `fill_rect()` for the changed sub-region only.
- Multi-region screens → section bitmask, not a single `_dirty`.
- Sprites for anything drawn at >1× scale or with non-trivial glyphs.
- If the mode introduces a new developmental focus, run the
  `add-game-mode` skill to update `docs/science/`.
