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
The SPI push (`show()`) for the primary 240x320 display sends ~150 KB — at 26 MHz
that alone takes ~47 ms, exceeding a 30 ms frame budget.

- **Skip the entire render + show cycle when nothing changed.**
  - Screens should track a `_dirty` flag. Set it on input events or state transitions.
  - `ScreenManager` checks `needs_redraw()` and skips `render()` + `show()` when clean.
  - This is the single most impactful optimization — an idle screen costs near zero.
- **Do not redraw the whole screen every frame.**
  - Only update regions that actually changed (`fill_rect`, partial redraws).
- Avoid frequent `fill()` of the entire screen.
  - Use it mainly when entering a new screen / mode.
- Pre-compute and cache:
  - Fonts, color constants, simple icon bitmaps.
  - Layout positions (e.g. button hint coordinates) as constants, not recomputed every loop.
- Use **integer math** for coordinates and layout; avoid floats.
- Keep your "frame rate" low but responsive:
  - UI update loop around **10-20 Hz** (50-100 ms between updates) is fine for a kid's toy.

---

## 4. Input (buttons & encoders)

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
3. **Input**:
   - Debouncing implemented? No polling at insane rates?
4. **Audio**:
   - Reasonable sample rate & buffer size? No per-sample Python loops?
5. **WiFi**:
   - Disabled when not in use? Handlers short and non-blocking?
6. **Logging**:
   - `print()` only on meaningful events, not every iteration.
7. **Allocations**:
   - Buffers reused; no big lists created in tight loops.

If any of these are violated, prefer a simpler, event-driven, low-refresh design over "desktop style" code.
