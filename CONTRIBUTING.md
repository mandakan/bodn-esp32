# Contributing to Bodn ESP32

## Setup

```bash
# Clone and enter the repo
git clone https://github.com/<you>/bodn-esp32.git
cd bodn-esp32

# Install Python tools (requires uv: https://docs.astral.sh/uv/)
uv sync

# Enable git hooks
git config core.hooksPath .githooks
```

## Project structure

- `firmware/` — MicroPython code that runs on the ESP32-S3
- `tests/` — host-side unit tests (run with `uv run pytest`)
- `tools/` — helper scripts for development
- `docs/` — hardware docs, wiring reference, roadmap

## Day-to-day commands

| Task | Command |
|------|---------|
| Run tests | `uv run pytest` |
| Lint | `uv run ruff check firmware/` |
| Format | `uv run black firmware/` |
| Deploy to device | `./tools/sync.sh` |
| Deploy to Wokwi | `uv run python tools/wokwi-sync.py` |
| Open device REPL | `uv run mpremote connect auto repl` |
| Print wiring reference | `uv run python tools/pinout.py` |
| Regenerate wiring docs | `uv run python tools/pinout.py --md` |

## Changing pin assignments

All GPIO assignments live in one file: `firmware/bodn/config.py`. This is the
single source of truth — never hardcode pin numbers anywhere else.

When you change a pin:

1. Edit `firmware/bodn/config.py`
2. Run `uv run python tools/pinout.py --md` to regenerate `docs/wiring.md`
3. Commit both files together

A pre-commit hook will remind you if you forget step 2.

## Testing

Pure logic (debouncing, UI state machines, audio format parsing) lives in
modules with no hardware imports and is tested with pytest on the host.
Hardware wrappers are tested on-device or in the [Wokwi simulator](https://wokwi.com).

To run tests:

```bash
uv run pytest
```

## Wokwi simulation

The repo includes `diagram.json` for the Wokwi ESP32 simulator.

### Web editor (recommended)

1. Go to https://wokwi.com/projects/new/micropython-esp32-s3
2. Replace the default `diagram.json` with ours
3. Create the files in the editor: `main.py`, `st7735.py`, and folder `bodn/`
   with `__init__.py`, `config.py`, `debounce.py` — paste contents from `firmware/`
4. Press play

### VS Code extension

The repo includes `wokwi.toml` and `diagram.json` for the
[Wokwi VS Code extension](https://marketplace.visualstudio.com/items?itemName=Wokwi.wokwi-vscode).

1. Download the ESP32-S3 MicroPython firmware from https://micropython.org/download/ESP32_GENERIC_S3/
2. Place the `.bin` file in the repo root (it's gitignored) — the filename must match `wokwi.toml`
3. Open the command palette → "Wokwi: Start Simulator"
4. **Keep the simulator tab visible** (VS Code pauses it otherwise)
5. Push firmware files to the simulator:
   ```bash
   uv run python tools/wokwi-sync.py
   ```

> **Note:** The Wokwi extension's RFC 2217 serial port has
> [known issues](https://github.com/wokwi/wokwi-vscode-micropython/issues/2)
> with `mpremote`. The sync script uses raw TCP to work around this.

## Code style

- MicroPython on the device, regular Python 3.12+ for host tools and tests
- Formatted with Black, linted with Ruff
- Keep modules small — separate pure logic from hardware calls
- Prefer clarity over cleverness (a 4-year-old's parent will maintain this)
