# tests/test_life_rules.py — host-side tests for the Garden of Life rule engine

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "firmware"))

from bodn.life_rules import (
    step,
    population,
    is_empty,
    clear,
    place,
    remove,
    toggle,
    load_preset,
    GRID_W,
    GRID_H,
    CONWAY_SURVIVE,
    FRIENDLY_BIRTH,
    FRIENDLY_SURVIVE,
)


def _make_grid(w, h, cells=None):
    """Helper: create a grid with optional pre-placed cells."""
    g = clear(w, h)
    if cells:
        for x, y in cells:
            place(g, x, y, w)
    return g


# --- Basic grid operations ---


def test_clear_creates_empty_grid():
    g = clear(4, 4)
    assert len(g) == 16
    assert is_empty(g)
    assert population(g) == 0


def test_place_and_remove():
    g = clear(4, 4)
    place(g, 1, 2, 4, color_idx=3)
    assert g[2 * 4 + 1] == 3
    assert population(g) == 1
    remove(g, 1, 2, 4)
    assert g[2 * 4 + 1] == 0
    assert is_empty(g)


def test_toggle():
    g = clear(4, 4)
    alive = toggle(g, 2, 2, 4, color_idx=5)
    assert alive is True
    assert g[2 * 4 + 2] == 5
    alive = toggle(g, 2, 2, 4)
    assert alive is False
    assert g[2 * 4 + 2] == 0


# --- Conway step() ---


def test_empty_grid_stays_empty():
    g = clear(5, 5)
    new, births, deaths = step(g, 5, 5)
    assert is_empty(new)
    assert births == []
    assert deaths == []


def test_block_is_stable():
    """A 2×2 block is a still life — should not change."""
    g = _make_grid(6, 6, [(2, 2), (3, 2), (2, 3), (3, 3)])
    new, births, deaths = step(g, 6, 6)
    assert births == []
    assert deaths == []
    assert population(new) == 4


def test_blinker_oscillates():
    """A horizontal blinker should rotate to vertical and back."""
    # Horizontal: (1,2), (2,2), (3,2)
    g = _make_grid(5, 5, [(1, 2), (2, 2), (3, 2)])
    assert population(g) == 3

    # Step 1: should become vertical
    g1, births1, deaths1 = step(g, 5, 5)
    assert population(g1) == 3
    assert len(births1) == 2  # (2,1) and (2,3) are born
    assert len(deaths1) == 2  # (1,2) and (3,2) die
    # Center cell (2,2) survives
    assert g1[2 * 5 + 2] != 0
    # New cells at (2,1) and (2,3)
    assert g1[1 * 5 + 2] != 0
    assert g1[3 * 5 + 2] != 0

    # Step 2: should return to horizontal
    g2, births2, deaths2 = step(g1, 5, 5)
    assert population(g2) == 3
    # Should match original positions
    assert g2[2 * 5 + 1] != 0
    assert g2[2 * 5 + 2] != 0
    assert g2[2 * 5 + 3] != 0


def test_glider_moves():
    """A glider should move one cell diagonally after 4 generations."""
    g = _make_grid(8, 8, [(1, 0), (2, 1), (0, 2), (1, 2), (2, 2)])
    assert population(g) == 5

    # Run 4 generations
    for _ in range(4):
        g, _, _ = step(g, 8, 8)

    # Should still have 5 cells, shifted by (1, 1)
    assert population(g) == 5
    assert g[1 * 8 + 2] != 0  # (2, 1)
    assert g[2 * 8 + 3] != 0  # (3, 2)
    assert g[3 * 8 + 1] != 0  # (1, 3)
    assert g[3 * 8 + 2] != 0  # (2, 3)
    assert g[3 * 8 + 3] != 0  # (3, 3)


def test_isolated_cell_dies():
    """A single cell with no neighbours should die."""
    g = _make_grid(5, 5, [(2, 2)])
    new, births, deaths = step(g, 5, 5)
    assert is_empty(new)
    assert deaths == [(2, 2)]


def test_full_grid_dies():
    """A fully populated grid should mostly die (overcrowding)."""
    w, h = 5, 5
    g = bytearray(b"\x01" * (w * h))
    new, births, deaths = step(g, w, h)
    # Interior cells have 8 neighbours → die
    # Edge/corner cells have 3–5 → some might survive
    assert population(new) < population(g)


# --- Edge wrapping ---


def test_wrap_around():
    """Cells at edges should wrap around when wrap=True."""
    # Place cells that would interact across boundary
    g = _make_grid(5, 5, [(0, 0), (4, 0), (0, 4)])
    # With wrap, (0,0) has neighbours at (4,4), (4,0), (0,4) — the 3 we placed
    # (0,0) sees (4,0) and (0,4) as neighbours → 2 neighbours → survives
    new, births, deaths = step(g, 5, 5, wrap=True)
    # Cell at (4,4) should be born (has 3 neighbours via wrapping)
    assert new[4 * 5 + 4] != 0


def test_no_wrap_walls():
    """Without wrap, edge cells should not see across boundaries."""
    g = _make_grid(5, 5, [(0, 0), (4, 0), (0, 4)])
    # Without wrap, these cells are far apart — no interaction
    new, births, deaths = step(g, 5, 5, wrap=False)
    # All three should die (isolated)
    assert is_empty(new)


# --- Custom rules ---


def test_friendly_rules():
    """Friendly rules: cells survive with 1 neighbour."""
    # Two adjacent cells — in Conway they'd die, in friendly they survive
    g = _make_grid(5, 5, [(2, 2), (3, 2)])
    new, births, deaths = step(g, 5, 5, birth=FRIENDLY_BIRTH, survive=FRIENDLY_SURVIVE)
    # Both cells should survive (each has 1 neighbour)
    assert new[2 * 5 + 2] != 0
    assert new[2 * 5 + 3] != 0


def test_custom_birth_rule():
    """Custom birth rule: birth with 2 neighbours instead of 3."""
    g = _make_grid(5, 5, [(1, 2), (3, 2)])
    # Cell at (2,2) has 2 neighbours
    birth = frozenset((2,))
    survive = CONWAY_SURVIVE
    new, births, deaths = step(g, 5, 5, birth=birth, survive=survive)
    # (2,2) should be born
    assert new[2 * 5 + 2] != 0


# --- Color inheritance ---


def test_new_cell_inherits_dominant_color():
    """New cells should inherit the most common color of their parents."""
    g = clear(5, 5)
    # Place 3 cells around (2,1) — 2 red, 1 blue
    place(g, 1, 0, 5, 1)  # red
    place(g, 2, 0, 5, 1)  # red
    place(g, 3, 0, 5, 3)  # blue
    new, births, deaths = step(g, 5, 5)
    # (2,1) should be born with color 1 (red, dominant)
    if (2, 1) in births:
        assert new[1 * 5 + 2] == 1


# --- Presets ---


def test_load_preset():
    from bodn.life_presets import BLINKER

    name, pw, ph, cells = BLINKER
    g = clear(6, 6)
    load_preset(cells, g, 6, 6, ox=1, oy=2)
    assert g[2 * 6 + 1] != 0
    assert g[2 * 6 + 2] != 0
    assert g[2 * 6 + 3] != 0
    assert population(g) == 3


def test_all_presets_valid():
    """All presets should have valid coordinates within their stated dimensions."""
    from bodn.life_presets import PRESETS

    for name, pw, ph, cells in PRESETS:
        for x, y in cells:
            assert 0 <= x < pw, "{}: x={} out of range".format(name, x)
            assert 0 <= y < ph, "{}: y={} out of range".format(name, y)
        # Should be loadable into a standard grid (cells outside bounds are clipped)
        g = clear(GRID_W, GRID_H)
        load_preset(cells, g, GRID_W, GRID_H)
        expected = sum(1 for x, y in cells if 0 <= x < GRID_W and 0 <= y < GRID_H)
        assert population(g) == expected, "{}: wrong population".format(name)


# --- Default grid dimensions ---


def test_default_grid_size():
    """Grid should be 16×12 = 192 cells."""
    assert GRID_W == 16
    assert GRID_H == 12
    g = clear(GRID_W, GRID_H)
    assert len(g) == 192
