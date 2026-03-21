#!/usr/bin/env python3
"""Generate a wiring reference from firmware/bodn/config.py.

Run:
  uv run python tools/pinout.py           # terminal output
  uv run python tools/pinout.py --md      # update docs/wiring.md (mermaid + tables)
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "firmware" / "bodn" / "config.py"
WIRING_MD = ROOT / "docs" / "wiring.md"

# Markers in wiring.md for the auto-generated section
MARKER_START = "<!-- pinout:start -->"
MARKER_END = "<!-- pinout:end -->"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

Group = tuple[str, list[tuple[str, int]]]  # (comment, [(var_name, gpio)])


def parse_config(path: Path) -> list[Group]:
    """Parse config.py into groups of (section_comment, [(name, gpio)])."""
    groups: list[Group] = []
    current_comment = ""
    current_pins: list[tuple[str, int]] = []

    for line in path.read_text().splitlines():
        line = line.strip()

        # Section comment
        if line.startswith("# ") and not current_pins and "=" not in line:
            current_comment = line.lstrip("# ")
            continue

        # Skip non-pin constants, MCP23017 expander pins, and import lines
        if line.startswith("from ") or line.startswith("import "):
            continue
        if (
            re.match(
                r"^[A-Z][A-Z0-9_]*(WIDTH|HEIGHT|RATE|SIZE|LEN|COUNT|MAX|MIN|MADCTL|OFFSET|BRIGHTNESS|ADDR|TIMEOUT[A-Z0-9_]*|_NAV|_A\b|_B\b)\s*=",
                line,
            )
            or re.match(r"^MCP", line)
            or re.match(r"^ENC_(NAV|A|B)\s*=", line)
        ):
            continue

        # Single assignment: NAME = 42  or  NAME = const(42)  (optional trailing inline comment)
        m = re.match(
            r"^([A-Z][A-Z0-9_]+)\s*=\s*(?:const\()?\s*(\d+)\s*\)?\s*(?:#.*)?$", line
        )
        if m:
            current_pins.append((m.group(1), int(m.group(2))))
            continue

        # Tuple assignment: A, B, C = 1, 2, 3  or  A, B, C = const(1), const(2), const(3)
        m = re.match(r"^([A-Z][A-Z0-9_,\s]+?)\s*=\s*([\d,\s]+?)\s*(?:#.*)?$", line)
        if m:
            names = [n.strip() for n in m.group(1).split(",")]
            vals = [int(v.strip()) for v in m.group(2).split(",")]
            for n, v in zip(names, vals):
                current_pins.append((n, v))
            continue

        # List assignment: NAME = [1, 2, 3]
        m = re.match(r"^([A-Z][A-Z0-9_]+)\s*=\s*\[([^\]]+)\]", line)
        if m:
            name_base = m.group(1)
            vals = [int(v.strip()) for v in m.group(2).split(",")]
            for i, v in enumerate(vals):
                current_pins.append((f"{name_base}[{i}]", v))
            continue

        # Blank line or other comment = end of group
        if not line or (line.startswith("#") and current_pins):
            if current_pins:
                groups.append((current_comment, current_pins))
                current_pins = []
            if line.startswith("#"):
                current_comment = line.lstrip("# ")
            else:
                current_comment = ""

    if current_pins:
        groups.append((current_comment, current_pins))

    return groups


def friendly_name(var_name: str) -> str:
    """TFT_SCK -> SCK, I2S_MIC_WS -> WS, BTN_PINS[0] -> BTN 0."""
    m = re.match(r"([A-Z_]+)\[(\d+)\]", var_name)
    if m:
        prefix = m.group(1).replace("_PINS", "").replace("_", " ")
        return f"{prefix} {m.group(2)}"
    for prefix in (
        "TFT_",
        "I2S_MIC_",
        "I2S_SPK_",
        "ENC1_",
        "ENC2_",
        "ENC3_",
        "SW_",
        "NEOPIXEL_",
    ):
        if var_name.startswith(prefix):
            return var_name[len(prefix) :]
    return var_name


def short_label(comment: str) -> str:
    """'Display: 1.8\" ST7735 TFT (SPI bus 2)' -> 'ST7735 TFT'."""
    # Take the part after the colon, strip parenthesised suffixes
    if ":" in comment:
        comment = comment.split(":", 1)[1].strip()
    comment = re.sub(r"\s*\(.*?\)\s*", " ", comment).strip()
    # Remove size prefixes like '1.8"'
    comment = re.sub(r'^[\d.]+"?\s*', "", comment)
    return comment


def node_id(comment: str) -> str:
    """Generate a mermaid-safe node id from a section comment."""
    return re.sub(r"[^a-zA-Z0-9]", "", short_label(comment).replace(" ", ""))


# ---------------------------------------------------------------------------
# Terminal output
# ---------------------------------------------------------------------------


def print_terminal(groups: list[Group]) -> None:
    print("=" * 60)
    print("BODN ESP32-S3 — WIRING REFERENCE")
    print("Generated from firmware/bodn/config.py")
    print("=" * 60)

    all_gpios: dict[int, str] = {}

    for comment, pins in groups:
        print()
        print(f"  {comment}")
        print(f"  {'-' * len(comment)}")
        for var_name, gpio in pins:
            label = friendly_name(var_name)
            print(f"    {label:<12s}  →  GPIO {gpio}")
            if gpio in all_gpios:
                print(f"    ⚠️  CONFLICT: GPIO {gpio} also used by {all_gpios[gpio]}")
            all_gpios[gpio] = f"{comment}: {label}"

    print()
    print("  All GPIOs (sorted)")
    print("  ------------------")
    for gpio in sorted(all_gpios):
        print(f"    GPIO {gpio:<3d}  →  {all_gpios[gpio]}")
    print()


# ---------------------------------------------------------------------------
# Markdown / Mermaid output
# ---------------------------------------------------------------------------


def generate_markdown(groups: list[Group]) -> str:
    lines: list[str] = []

    # Mermaid block diagram
    lines.append("```mermaid")
    lines.append("graph LR")
    lines.append('    ESP["ESP32-S3<br/>DevKit-Lipo"]')
    lines.append("")

    for comment, pins in groups:
        nid = node_id(comment)
        label = short_label(comment)
        pin_lines = "<br/>".join(
            f"GPIO {gpio} → {friendly_name(var)}" for var, gpio in pins
        )
        lines.append(f'    {nid}["{label}<br/><sub>{pin_lines}</sub>"]')
        # Pick a link style based on interface type
        if "SPI" in comment:
            lines.append(f"    ESP -- SPI --> {nid}")
        elif "I2S" in comment and "IN" in comment:
            lines.append(f"    {nid} -- I2S --> ESP")
        elif "I2S" in comment:
            lines.append(f"    ESP -- I2S --> {nid}")
        else:
            lines.append(f"    {nid} -.- ESP")
        lines.append("")

    lines.append("```")
    lines.append("")

    # Markdown tables per group
    for comment, pins in groups:
        lines.append(f"### {short_label(comment)}")
        lines.append("")
        lines.append("| Signal | GPIO | Config variable |")
        lines.append("|--------|------|-----------------|")
        for var_name, gpio in pins:
            lines.append(f"| {friendly_name(var_name)} | {gpio} | `{var_name}` |")
        lines.append("")

    # Full GPIO map
    all_gpios: dict[int, str] = {}
    conflicts: list[str] = []
    for comment, pins in groups:
        for var_name, gpio in pins:
            label = f"{short_label(comment)}: {friendly_name(var_name)}"
            if gpio in all_gpios:
                conflicts.append(f"**GPIO {gpio}**: {all_gpios[gpio]} / {label}")
            all_gpios[gpio] = label

    lines.append("### All GPIOs")
    lines.append("")
    lines.append("| GPIO | Component | Signal |")
    lines.append("|------|-----------|--------|")
    for gpio in sorted(all_gpios):
        comp, sig = all_gpios[gpio].rsplit(": ", 1)
        lines.append(f"| {gpio} | {comp} | {sig} |")
    lines.append("")

    if conflicts:
        lines.append("> **Pin conflicts detected:**")
        for c in conflicts:
            lines.append(f"> - {c}")
        lines.append("")

    return "\n".join(lines)


def update_wiring_md(content: str) -> None:
    """Write or update docs/wiring.md with generated content between markers."""
    header = (
        "# Wiring reference\n\n"
        "Auto-generated from `firmware/bodn/config.py`. "
        "Do not edit between the markers.\n\n"
        "Regenerate: `uv run python tools/pinout.py --md`\n\n"
    )

    wrapped = f"{MARKER_START}\n{content}{MARKER_END}\n"

    if WIRING_MD.exists():
        existing = WIRING_MD.read_text()
        if MARKER_START in existing and MARKER_END in existing:
            # Replace between markers
            before = existing[: existing.index(MARKER_START)]
            after = existing[existing.index(MARKER_END) + len(MARKER_END) :].lstrip(
                "\n"
            )
            WIRING_MD.write_text(before + wrapped + "\n" + after)
            return

    WIRING_MD.write_text(header + wrapped)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Bodn wiring reference generator")
    parser.add_argument(
        "--md",
        action="store_true",
        help="Generate docs/wiring.md with mermaid diagram and tables",
    )
    args = parser.parse_args()

    if not CONFIG.exists():
        print(f"Error: {CONFIG} not found", file=sys.stderr)
        sys.exit(1)

    groups = parse_config(CONFIG)

    if args.md:
        content = generate_markdown(groups)
        update_wiring_md(content)
        print(f"Updated {WIRING_MD}")
    else:
        print_terminal(groups)


if __name__ == "__main__":
    main()
