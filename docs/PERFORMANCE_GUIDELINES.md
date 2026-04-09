# ESP32-S3 Performance Guidelines (Bodn)

Short, practical rules for writing efficient code for Bodn on ESP32-S3 (and for keeping the Wokwi simulation usable).

## 1. General mindset

- Think in **events and states**, not continuous polling.
- Prefer **simple state machines** over deep call stacks.
- Optimize for **responsiveness** and **battery**, not raw throughput.

---

## 2. Main loop & scheduling

- **Never** run a tight `while True:` loop without a delay.
  - Always include `time.sleep_ms(5-10)` or use `uasyncio` with `await asyncio.sleep_ms(0)` inside long-running loops.
- If using `uasyncio`:
  - Make each task **cooperative**: no blocking I/O or long CPU bursts.
  - Break work into small chunks and `await` frequently.
- Separate responsibilities:
  - One task for **input handling** (buttons/encoders).
  - One for **UI updates** (screen + LEDs).
  - One for **game logic** (state transitions, scoring, sequences).
  - Optional task(s) for **audio** and **WiFi/web UI**.

---

## 3. Display (ST7735/ILI9341)

Drawing is one of the slowest operations, especially in simulation.
The SPI push for the primary 240×320 display sends ~150 KB over SPI.
With the `_spidma` DMA driver, transfers are pipelined via 32 KB chunks
through internal DRAM staging buffers. **The amount of data pushed
directly determines how long Python is blocked.**

The SPI clock is configured via `TFT_SPI_BAUDRATE` in `config.py`
(default: 80 MHz with custom firmware, 26 MHz stock). The `_spidma`
module uses `SPI_DEVICE_NO_DUMMY` to remove the ~27 MHz cap that
stock MicroPython imposes (dummy cycles are for SPI reads — displays
are write-only). The timings below assume 80 MHz. If you see display
glitches (corrupted pixels, colour shifts), lower to 40 MHz — no
firmware rebuild needed, just change `config.py` and sync.

### 3.0 DMA chunk budget — the most important rule

The SPI DMA hardware limit is 32 KB per transaction. The `_spidma` driver
pipelines chunks using ping-pong buffers, and the **last chunk runs
asynchronously** — Python returns immediately while DMA finishes in the
background. This creates a massive performance cliff:

| Dirty region | Bytes | DMA chunks | Python blocked | Async (free) |
|---|---|---|---|---|
| ≤50 rows (320×50) | 32,000 | **1** | **~1 ms** | ~3 ms |
| 120 rows (half screen) | 76,800 | 3 | ~7 ms | ~3 ms |
| Full screen (240 rows) | 153,600 | 5 | ~13 ms | ~3 ms |

**Key insight: if your dirty rect fits in one 32 KB chunk (≤50 full-width
rows on the primary display), the push is essentially free (~1 ms memcpy,
then Python continues while DMA runs).** Every additional chunk adds ~3 ms
of blocking at 80 MHz.

**Design animations to stay within ≤50 rows whenever possible.** This means:
- Keep animated content in a narrow horizontal band
- Slide/scroll within a bounded region, not full-screen
- Static chrome (title, footer, status dots) should not be redrawn during animation
- If the whole screen must change (screen transition), accept the ~41 ms cost
  — but this should be a rare event, not a per-frame occurrence

Without `_spidma` (stock firmware fallback), the full push blocks Python for
~47 ms regardless of dirty rect size, so these guidelines also help by
reducing the total data transferred.

### 3.1 General display rules

- **Skip the entire render + show cycle when nothing changed.**
  - Screens should track a `_dirty` flag. Set it on input events or state transitions.
  - `ScreenManager` checks `needs_redraw()` and skips `render()` + `show()` when clean.
  - This is the single most impactful optimization — an idle screen costs near zero.
- **Use partial pushes for small, frequent updates** (preferred pattern):
  - Instead of triggering a full render cycle, write pixels directly to the framebuffer
    and call `manager.request_show(x, y, w, h)`. This calls `tft.show_rect()` on the
    next tick, pushing only that rectangle over SPI.
  - Use `manager.invalidate_rect(x, y, w, h)` to accumulate multiple regions —
    they are merged into a bounding box and pushed as one `show_rect()` call.
  - Example speedups: a 320×4 hold bar costs ~0.8 ms instead of ~47 ms (~60×).
  - **`tft.show_rect(x, y, w, h)`** is available on both displays and handles CASET/RASET
    windowing and row extraction automatically.
- **Do not redraw the whole screen every frame.**
  - Only update regions that actually changed (`fill_rect`, partial redraws).
  - In `render()`, prefer `tft.fill_rect(x, y, w, h, BLACK)` over `tft.fill(BLACK)`.
    Clear only the region you are about to redraw, not the whole screen.
  - Reserve `tft.fill(BLACK)` for screen transitions (entering a new screen / mode).
- **Automatic dirty rect tracking** — the ST7735 driver tracks a bounding box of all
  draw operations (`fill_rect`, `text`, `pixel`, `line`, etc.) per frame. After
  `render()`, `ScreenManager` calls `tft.show_dirty()` which pushes only the changed
  region via `show_rect()`. This is automatic — no screen code changes needed.
  - Screens that call `tft.fill(BLACK)` mark the entire screen dirty → full push.
  - Screens that only redraw changed areas (garden cells, flöde segments) get partial
    pushes automatically, reducing SPI data from ~150 KB to a few KB — and with DMA,
    small dirty rects (≤32 KB) return to Python in ~1 ms.
  - **To benefit**: avoid `tft.fill(BLACK)` per frame. Instead, clear only the changed
    sub-region with `tft.fill_rect()`. Use a `_full_clear` flag for transitions.
  - **Pattern for animation screens** (see Flöde as reference):
    ```python
    def render(self, tft, theme, frame):
        if self._dirty:
            self._dirty = False
            if self._full_clear:           # only on state transitions
                tft.fill(theme.BLACK)
                self._full_clear = False
            self._render_game(tft, theme, frame)  # draws only changed areas
    ```
- **Never call `tft.show()` or `tft.show_rect()` directly** from screens or UI components.
  Always route through `manager.request_show()` or `manager.request_show(x, y, w, h)`.
  Only `ScreenManager.tick()` and `SecondaryDisplay.tick()` issue the actual SPI push.
- **Extended glyph cost**: non-ASCII characters (å, ä, ö) in `st7735.py` are
  drawn pixel-by-pixel (up to 64 `pixel()` calls per glyph), each expanding
  the dirty rect. This is acceptable for static labels but avoid rendering
  extended characters in per-frame animation paths.
- Pre-compute and cache:
  - Fonts, color constants, simple icon bitmaps.
  - Layout positions (e.g. button hint coordinates) as constants, not recomputed every loop.
  - RGB565 colour values — call `theme.rgb()` once in `enter()` and cache the
    result rather than calling it per-frame in `render()`.
- Use **integer math** for coordinates and layout; avoid floats.
- Keep your "frame rate" low but responsive:
  - UI update loop around **10-20 Hz** (50-100 ms between updates) is fine for a kid's toy.

### 3a. Secondary display (two-zone layout)

The 128×160 secondary display is split into a **content zone** (128×128, y=0..127) and a **status strip** (128×32, y=128..159). `SecondaryDisplay` manages them independently. Follow these rules when writing a content or status screen:

- **Track `_dirty` state** and implement `needs_redraw()` — same as primary screens. `SecondaryDisplay` skips `render()` + `show()` entirely when both zones are clean.
- **Clear only what you draw.** `SecondaryDisplay` only does a full `fill_rect` clear on transitions (`set_content()` / `set_status()`). On normal redraws, clear only the sub-region you are about to repaint — not the whole zone. This keeps the SPI push small.
  - Content screens: clear only the changed sub-region, e.g. `tft.fill_rect(0, text_y, w, text_h, BLACK)`. Only use a full zone clear (`fill_rect(0, 0, w, CONTENT_H, BLACK)`) when the entire zone changes.
  - Status screens: same principle; `fill_rect(0, STATUS_Y, w, STATUS_H, BLACK)` only when everything changes.
- **Zone-aware partial push is automatic.** `SecondaryDisplay.tick()` already calls `show_rect()` for just the dirty zone (content or status) when only one zone changed. Tight `fill_rect` calls in `render()` ensure those zone-level SPI transfers stay small.
- **Stay within your zone bounds.** Content screens must not draw below y=127. Status screens draw only at y=128..159. There is no clip guard — drawing outside your zone will overwrite the other zone and cause visual glitches.
- **`show()` / `show_rect()` are never called by the screen** — `SecondaryDisplay.tick()` issues the SPI push. Do not call `tft.show()` from `render()`.
- **Tick rate is ~50 ms with DMA (20 Hz), ~200 ms without (5 Hz).** Design for state-change-driven redraws. The secondary display buffer (40 KB) fits in 2 DMA chunks, so full pushes are affordable.

---

## 4. MicroPython-specific optimizations

These apply across all modules. See the [official guide](https://docs.micropython.org/en/latest/reference/speed_python.html).

### `const()` for module-level numeric constants

```python
from micropython import const
_BUF_SIZE = const(1024)
CH_UI = const(2)
```

The compiler inlines the value at each use site, avoiding a global dictionary
lookup every time the name appears. Use for any numeric constant accessed in
loops or frequently called functions.

### Tuples over lists for immutable data

Pin assignments, color tables, option lists, and similar **fixed data** should
be tuples, not lists. Tuples are smaller in RAM (no over-allocation for
growth), signal immutability, and can be stored in ROM on frozen builds.

```python
MCP_BTN_PINS = (0, 1, 2, 3, 4, 5, 6, 7)   # tuple — good
BUTTON_COLORS = ("green", "blue", "white")  # tuple — good
# NOT: MCP_BTN_PINS = [0, 1, 2, 3, ...]    # list — wastes RAM
```

### `__slots__` on classes

Classes without `__slots__` allocate a `__dict__` per instance (~40–60 bytes
overhead). For classes instantiated at startup (drivers, engines, screens),
declare `__slots__` to save RAM:

```python
class _Voice:
    __slots__ = ("source", "loop", "file_obj", "mono_buf", "gain_mult")
```

This also catches typo bugs — assigning to an undeclared attribute raises
`AttributeError`.

### Cache attribute lookups in locals

Each dot access (`self._buf`, `asyncio.sleep_ms`) is a dictionary lookup in
MicroPython bytecode. In hot loops or long-running coroutines, cache them once:

```python
async def run(self):
    buf = self._buf          # one lookup instead of N
    sleep_ms = asyncio.sleep_ms
    while True:
        process(buf)
        await sleep_ms(10)
```

### Prefer `bytearray`, `memoryview`, `array` over lists

- `bytearray` / `array.array` for numeric buffers — compact, no per-element
  object overhead.
- `memoryview` for zero-copy slicing — `buf_view[:n]` does not allocate a new
  object, unlike `buf[:n]` on a `bytearray`.

### Use `readinto()` over `read()`

`file.read(n)` allocates a new `bytes` object each call. Where the API
supports it, use `file.readinto(buf)` with a pre-allocated buffer. This is
especially important for I2S audio streaming and SPI transfers — the canonical
pattern is `readinto()` + `memoryview` slicing:

```python
buf = bytearray(1024)
view = memoryview(buf)
while True:
    n = f.readinto(buf)
    if n == 0:
        break
    i2s.write(view[:n])   # zero-copy slice
```

### Avoid `import` inside hot loops

Deferred imports are fine for one-shot operations (screen enter, mode switch)
but must not appear inside `update()`, `render()`, or any per-frame path.
Python's import machinery does module-dict lookups and can trigger GC. Move
imports to module level or cache the result in `enter()` / `__init__`.

### Escalation: `@micropython.native` and `@micropython.viper`

When a pure-Python hot loop is too slow after applying the above:

1. **`@micropython.native`** — emits native CPU opcodes instead of bytecode.
   ~2× speedup, minimal restrictions. Try this first.
2. **`@micropython.viper`** — more aggressive; uses type hints (`int`, `ptr8`)
   for near-C speed. Restrictions: no floats, limited argument types, no
   context managers.

Both are built into MicroPython — no custom firmware build needed. Keep the
decorated function small and self-contained.

---



- **Debounce in software** with minimal overhead:
  - Sample inputs at a fixed interval (e.g. every 5-10 ms).
  - Treat a change as "real" after it has been stable for N samples.
- For encoders:
  - Use simple **state table** decoding; avoid heavy math.
  - Only emit events on actual step changes, not every raw transition.
- Prefer **edge/event-based** handling over continuously using raw values:
  - Expose "BUTTON_X_PRESSED", "ENCODER_L_STEP(+1)" to the rest of the code.

---

## 5. Audio (INMP441 + MAX98357A)

Audio can be CPU- and memory-intensive if handled carelessly.

- Choose **modest sample rates and bit depth**:
  - Example: 16 kHz, 16-bit mono is enough for voice snippets.
- Record/play in **chunks**, not one sample at a time:
  - Use small buffers; avoid per-sample Python loops if possible.
- Keep recordings **short** (1-3 seconds) for now to avoid memory pressure on PSRAM and flash wear.
- When not recording or playing:
  - **Stop or pause I2S** and keep amplifier in a low-power/idle state if supported.
- **Multi-voice mixing**: The AudioEngine mixes up to 6 simultaneous voices
  (1 music + 4 SFX pool + 1 UI). Each voice has its own 1024-byte mono read
  buffer plus a shared 1024-byte mix buffer = **~7 KB** total audio RAM.
  Per-voice gain staging keeps the mix within int16 range; a viper-accelerated
  `_mix_add` kernel sums voices with saturation clipping as a safety net.

---

## 6. WiFi & web UI

WiFi is one of the largest power and latency contributors.

- Keep WiFi **off by default**. Only enable for parental web UI / updates.
- When WiFi is enabled:
  - Use a **simple HTTP server** with minimal processing.
  - Avoid long blocking handlers -- use small async handlers instead.
  - Consider auto-disabling WiFi after a period of web inactivity.
- Do not constantly scan for networks or reconnect in a tight loop.

---

## 7. Memory & allocations

- Avoid per-frame allocations:
  - Reuse buffers and lists where possible (`buf[:] = ...` instead of creating new lists).
  - Pre-allocate audio and display buffers during init.
- Keep global state **small and simple**:
  - Prefer simple dicts, tuples, and small classes over deeply nested objects.
- Cleanly separate **configuration data** from runtime state so saving/loading settings is cheap.

---

## 8. Logging & debugging

- `print()` is slow on microcontrollers and in Wokwi; use it sparingly.
  - Log only on state changes, errors, or occasionally in debug builds.
- Consider a simple `DEBUG` flag:
  - When `DEBUG = False`, skip detailed logging.

---

## 9. Wokwi-specific tips

These are about keeping the simulator responsive, but they correlate with good on-device performance:

- Avoid full-screen redraws and excessive printing -- they **kill sim performance**.
- Use **cooperative loops** (with `sleep` or `await`) so the sim doesn't peg a core.
- If a change makes the sim noticeably slower, question:
  - "Did I add a redraw in a fast loop?"
  - "Did I add logging every iteration?"
  - "Did I block inside an async task?"

---

## 10. Review checklist for Claude / code reviews

When generating or reviewing code, check:

1. **Loops**:
   - Does every `while True` or long loop yield (`sleep` / `await`) regularly?
2. **Display**:
   - Does the screen implement `needs_redraw()` and track `_dirty` state?
   - Is `render()` + `show()` skipped entirely when nothing changed?
   - No full `fill()` calls inside fast loops?
   - Is `tft.fill(BLACK)` reserved for screen transitions (guarded by a `_full_clear` flag)?
     Every `fill()` marks the full screen dirty, defeating partial-push optimization.
   - For animations: does the screen clear only the changed sub-region with `fill_rect()`
     instead of clearing the whole screen? (dirty rect tracking handles the rest automatically)
   - **DMA chunk budget**: does the animation's dirty rect fit within ≤50 full-width rows
     (32 KB = 1 DMA chunk = ~1 ms blocking)? If it exceeds this, each extra chunk adds
     ~3 ms of blocking at 80 MHz. Keep animated content in a narrow horizontal band.
   - For small, frequent updates (progress bars, timers, counters): does the screen use
     `manager.request_show(x, y, w, h)` (partial push) instead of triggering a full render?
   - Secondary display: does the screen clear only its changed sub-region (not the full zone)?
     Does it stay within zone bounds (content: y<128, status: y≥128)?
3. **Input**:
   - Debouncing implemented? No polling at insane rates?
   - Hold-to-pause: does the game screen use `PauseMenu.update()` (which reads from `GestureDetector`) instead of rolling its own hold logic? No per-frame allocations in the hold path?
4. **Audio**:
   - Reasonable sample rate & buffer size? No per-sample Python loops?
5. **WiFi**:
   - Disabled when not in use? Handlers short and non-blocking?
6. **Logging**:
   - `print()` only on meaningful events, not every iteration.
7. **Allocations**:
   - Buffers reused; no big lists created in tight loops.
   - `memoryview` used for buffer slices passed to I/O (I2S, SPI, file).
8. **MicroPython idioms**:
   - Module-level numeric constants use `const()`.
   - Hot loops / long-running coroutines cache `self.*` and module attributes as locals.
   - No `file.read(n)` in loops — use `readinto(buf)` with pre-allocated buffer.

9. **Thermal safety**:
   - Does the new peripheral draw significant power (LEDs, motors, heaters, RF)?
   - If yes, is it registered in the power-shedding logic in `main.py`
     `housekeeping_task()`? Non-critical loads must be disabled at the
     **critical** threshold (≥ 50 °C) and killed before **emergency** deep
     sleep (≥ 60 °C). See `docs/hardware.md` § "Thermal protection" for the
     full escalation table.
   - The BL4054B charger and the LiPo cell have **no hardware thermal cutoff**.
     Software is the only protection.

If any of these are violated, prefer a simpler, event-driven, low-refresh design over "desktop style" code.
