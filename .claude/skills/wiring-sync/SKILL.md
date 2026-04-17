---
name: wiring-sync
description: Regenerate docs/wiring.md after editing firmware/bodn/config.py. Use whenever pin assignments, GPIO numbers, encoder sensitivity, or any constant in config.py changes. The pre-commit hook will reject a commit that stages config.py without a matching wiring.md update, so run this before committing.
---

# Wiring sync

`firmware/bodn/config.py` is the single source of truth for pin assignments.
`docs/wiring.md` is auto-generated from it. When you change `config.py`, the
markdown must be regenerated and committed alongside it — the `.githooks/pre-commit`
hook enforces this.

## Procedure

1. Confirm `firmware/bodn/config.py` has the intended edits.
2. Regenerate the markdown:
   ```bash
   uv run python tools/pinout.py --md
   ```
3. Verify both files are staged together:
   ```bash
   git status firmware/bodn/config.py docs/wiring.md
   git diff --staged docs/wiring.md
   ```
4. If you only want a terminal preview (no file write), run `uv run python tools/pinout.py` without `--md`.

## Invariants

- Never hand-edit `docs/wiring.md` — it is overwritten by `tools/pinout.py`.
- Never hardcode GPIO numbers outside `config.py`. If a module needs a pin,
  import it from `bodn.config`.
- Non-time-critical I/O (buttons, toggles, status LEDs) belongs on the
  MCP23017 expanders (`MCP1` at `0x23`, `MCP2` at `0x21`). Latency-sensitive
  peripherals (encoder CLK/DT, SPI, I2S) stay on native GPIOs.
- See `docs/hardware.md` for reserved pins and the full GPIO budget before
  assigning new ones.

## When the hook fails

If `git commit` fails with a wiring.md mismatch:
1. Run the regeneration command above.
2. `git add docs/wiring.md`
3. Create a **new** commit (do not `--amend` — the failed commit did not happen).
