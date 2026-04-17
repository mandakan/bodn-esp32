---
name: wokwi-chip-rebuild
description: Recompile the MCP23017 Wokwi custom chip binary after editing mcp23017.chip.c. The committed mcp23017.chip.wasm must stay in sync with its C source or the Wokwi simulator will behave differently from hardware. Use any time mcp23017.chip.c or mcp23017.chip.json changes.
---

# Wokwi custom chip rebuild

The MCP23017 GPIO expander used in simulation is a Wokwi custom chip. The
binary Wokwi loads is committed to the repo and must match the C source.

## Files in the project root

| File | Purpose |
|---|---|
| `mcp23017.chip.json` | Pin definitions |
| `mcp23017.chip.c` | C source implementing the register-addressed I2C protocol (`IODIRA/B`, `GPPUA/B`, `GPIOA/B`, `OLATA/B`) |
| `mcp23017.chip.wasm` | Compiled binary Wokwi loads (**committed**) |
| `wokwi.toml` | Registers the chip: `[[chip]] name="mcp23017" binary="mcp23017.chip.wasm"` |
| `wokwi-api.h` | Build artefact downloaded by the CLI — **gitignored, do not commit** |

## When to rebuild

Any time `mcp23017.chip.c` changes. The `.wasm` is a checked-in build
artefact, so a stale binary silently diverges sim from hardware.

## Command

```bash
~/bin/wokwi-cli chip compile mcp23017.chip.c -o mcp23017.chip.wasm
```

Commit both the `.c` and the updated `.wasm` in the same commit.

## Diagram wiring invariant

`diagram.json` routes all inputs through the expanders — do **not** bypass
them with direct ESP GPIO connections:

- 8 buttons on `GPA0–7` of `mcp1`
- 2 toggle switches on `GPB0–1` of `mcp1`
- 5 arcade buttons on `GPB2–3, GPB5–7` of `mcp1`
