---
name: perf-review
description: Apply the Bodn performance checklist to code changes (especially UI screens, game loops, audio, LED, and display code). Use when writing or reviewing any firmware change that touches render paths, main loops, input handling, audio streaming, or LED patterns. Mirrors docs/PERFORMANCE_GUIDELINES.md §10 and flags the three most common pitfalls upfront.
---

# Performance review (ESP32-S3 MicroPython)

The full rules live in `docs/PERFORMANCE_GUIDELINES.md`. This skill is the
review checklist from §10 plus the critical pitfalls from §3. Apply it to any
new or modified firmware code.

## Three pitfalls that cause most regressions

1. **Single `_dirty` flag on multi-region screens** (§3.05) — screens with
   multiple independent regions must use a **section-level dirty bitmask**,
   not a single boolean. A global flag forces full redraws.
2. **Bundling cheap + expensive I/O** (§3.2) — PCA9685 I2C LED writes and
   NeoPixel writes have very different costs; throttle them separately.
3. **Game state updated in `render()`** (§3.3) — state belongs in `update()`.
   Skipped renders drop state, causing drift and timing bugs.

## DMA display budget (§3.0)

The `_spidma` module pushes 32 KB chunks at 40 MHz SPI. If the dirty rect
fits in **one chunk (≤50 full-width rows on the primary display)**, the push
costs ~1 ms. Each additional chunk adds ~6.5 ms of blocking. Design
animations to stay within a narrow horizontal band.

If the display glitches, drop `TFT_SPI_BAUDRATE` to `26_000_000` in
`config.py` — no firmware rebuild needed.

## Sprites over pixel-by-pixel draws

Never draw scaled icons or text pixel-by-pixel in `render()`. Pre-render
once in `enter()`:

```python
self._icon = make_icon_sprite(emoji, scale=4)   # enter()
blit_sprite(tft, self._icon, x, y)              # render()
```

A scale-4 icon costs ~30 ms via `fill_rect`; a `blit_sprite()` costs ~0.1 ms.
See `bodn/ui/widgets.py` and the reference pattern in `bodn/ui/home.py`.
Sprite buffers >8 KB go to PSRAM automatically.

## Review checklist (from §10)

**Loops**
- Every `while True` / long loop yields with `sleep` or `await`.

**Display**
- `needs_redraw()` implemented; dirty state tracked.
- Multi-region screens use a section bitmask (not a single `_dirty`).
- `render()` + `show()` skipped when nothing changed.
- No full `fill()` in fast loops; `tft.fill(BLACK)` only at transitions,
  gated by `_full_clear`.
- Animations clear only the changed sub-region with `fill_rect()`.
- Animated dirty rect ≤ 50 full-width rows (1 DMA chunk).
- Scaled icons/text are pre-rendered sprites.
- Small frequent updates use `manager.request_show(x, y, w, h)` partial push.
- Secondary display clears only its changed sub-region; stays within zone
  bounds (content: `y<128`, status: `y≥128`).

**Input & output coupling**
- Debouncing implemented; no insane polling rates.
- Hold-to-pause uses `PauseMenu.update()` (reads `GestureDetector`) — not a
  custom hold loop. No per-frame allocations in the hold path.
- Cheap I2C LED writes (PCA9685) decoupled from expensive NeoPixel writes.
- All game/timing state updated in `update()`, never `render()`.

**Audio**
- Reasonable sample rate / buffer size. No per-sample Python loops.

**WiFi**
- Disabled when not in use. Handlers are short and non-blocking.

**Logging**
- `print()` only on meaningful events, not every iteration.

**Allocations**
- Buffers reused. No big lists created in tight loops.
- `memoryview` for buffer slices passed to I/O (I2S, SPI, file).

**MicroPython idioms**
- Module-level numeric constants use `const()`.
- Hot loops / long-running coroutines cache `self.*` and module attributes
  as locals.
- No `file.read(n)` in loops — use `readinto(buf)` with a pre-allocated
  buffer.
- Tuples for immutable data; `__slots__` on data classes when helpful.
- Avoid `import` inside hot loops.
- Escalate to `@micropython.native` / `@micropython.viper` only where
  measured necessary.

**Thermal safety**
- Does the new peripheral draw significant power (LEDs, motors, heaters,
  RF)?
- If yes, register it in `main.py` `housekeeping_task()` power-shedding.
  Non-critical loads disabled at **≥ 50 °C** (critical), device deep-sleeps
  at **≥ 60 °C** (emergency). See `docs/hardware.md` § "Thermal protection".
- BL4054B + LiPo have **no hardware thermal cutoff** — software is the only
  protection.

If any rule is violated, prefer a simpler, event-driven, low-refresh design
over "desktop style" code.
