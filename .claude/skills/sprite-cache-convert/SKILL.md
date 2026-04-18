---
name: sprite-cache-convert
description: Convert a screen from per-frame fill_rect/text drawing into pre-rendered sprites cached in enter() and blit per frame. Use when a screen has visible jank, dropped frames, or when perf logs show it dominating frame time. Apply mechanically — no design decisions, just a recipe with measurable wins.
---

# Sprite cache conversion

The single biggest perf win on the primary display is replacing
per-frame scaled draws (`fill_rect` per pixel, `text()` per char) with a
pre-rendered sprite that blits in one call. A scale-4 icon rendered via
`fill_rect` costs ~30 ms; `blit_sprite()` costs ~0.1 ms.

`firmware/bodn/ui/home.py` is the reference pattern. Apply the recipe to
any screen that draws scaled icons, large text, or repeated bitmap glyphs
every frame.

## When to apply

- Perf report shows a screen with a low drawn-to-skipped ratio or visibly
  stutters during animations.
- `render()` contains any of: `draw_scaled_icon`, `draw_scaled_text`,
  nested loops over pixels, or repeated `tft.text()` at scale>1.
- A screen calls `fill_rect` hundreds of times per frame to build a single
  logical element (icon, label, big counter).

Issue #111 and PR #118 document the pattern being rolled out across the
game screens; the skill exists so the remaining conversions stay
consistent.

## API

```python
from bodn.ui.widgets import (
    make_icon_sprite,
    make_label_sprite,
    make_emoji_sprite,
    blit_sprite,
)

#   make_icon_sprite(bitmap_data, w, h, color, scale=1)
#   make_label_sprite(text, color, scale=1)
#   make_emoji_sprite(name, size=48, pad=4)   # OpenMoji via _draw + SD
#
# All three return (framebuf, pixel_width, pixel_height).
# blit_sprite(tft, sprite, x, y) handles transparency via a magenta key.
```

`blit_sprite()` also calls `tft.mark_dirty(x, y, pw, ph)` for you — no
extra bookkeeping needed.

## Recipe

### 1. Pre-render in `enter()`

Everything that depends only on theme/content goes here. Do it once per
screen push, not once per frame.

```python
def enter(self, manager):
    theme = manager.theme
    self._icon_sprite = make_icon_sprite(
        MODE_ICONS["simon"], 16, 16, theme.CYAN, scale=4,
    )
    self._title_sprite = make_label_sprite(t("simon_title"), theme.WHITE, scale=2)
    # For OpenMoji: falls back to None if _draw/SD unavailable
    self._emoji_sprite = make_emoji_sprite("cat", size=64)
```

### 2. Blit in `render()`

```python
def render(self, tft, theme, frame):
    fb, pw, ph = self._icon_sprite
    blit_sprite(tft, self._icon_sprite, (320 - pw) // 2, 40)
    blit_sprite(tft, self._title_sprite, 20, 120)
```

### 3. Invalidate the cache when inputs change

If the sprite depends on theme, language, selection, or any other input
that can change, rebuild it in response — not every frame.

```python
def _rebuild_sprites(self, theme):
    self._icon_sprite = make_icon_sprite(...)
    self._label_sprite = make_label_sprite(t(self._label_key), ...)

def on_reveal(self):
    super().on_reveal()
    self._rebuild_sprites(self._theme)    # theme or i18n may have changed
```

The home screen lazy-builds per-mode sprites into `self._icon_sprites = {}`
on first render — follow that pattern for carousels.

## Memory cost

Sprite buffers are `pixel_width * pixel_height * 2` bytes (RGB565). A
scale-4 16×16 icon is 64×64 × 2 = 8 KB. Anything over 8 KB goes to PSRAM
automatically via MicroPython's bytearray allocator, but keep an eye on
totals for screens with many pre-rendered variants. Free large buffers in
`exit()` if needed — the default is to let them GC when the screen is
popped.

## Verification

1. Enable `manager.debug_perf = True` in `boot.py` and watch the
   `drawn/total` ratio improve on the converted screen.
2. Check that `render()` has no nested pixel loops and no `fill_rect`
   calls inside a tight per-element loop (outside of the sprite pre-render
   in `enter()`).
3. Scroll or animate the screen on hardware (not just Wokwi — DMA SPI
   timing differs).

## Invariants

- **Never** call `make_*_sprite()` inside `render()` or `update()`. It
  allocates a fresh FrameBuffer each time and undoes the whole point of
  caching.
- `blit_sprite()` uses magenta (`0x1FF8`) as the transparency key. Do not
  use that exact colour in sprite content — it will be punched through.
- Sprites are RGB565. If the display was configured in a different colour
  mode the blit colours will be wrong; ST7735 defaults in this project
  are fine.
- OpenMoji emoji sprites require the `_draw` C module and SD-card BDF
  assets. On stock MicroPython or a device with no SD, `make_emoji_sprite`
  returns `None` — code must handle the fallback (home.py falls back to
  `make_icon_sprite`).
- This conversion never adds features — it is a mechanical perf change.
  Review the `perf-review` skill checklist once done.
