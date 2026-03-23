# bodn/life_rules.py — Game of Life rule engine (pure logic, testable on host)
#
# Grid is stored as a flat bytearray (1 byte per cell): 0 = dead, 1+ = alive.
# The alive value encodes the flower color index (1–8) for visual variety.
#
# step() evolves one generation and returns a diff of changed cells so the
# screen can redraw only what changed (no full-grid scan each frame).
#
# Pure functions + one class, no hardware imports → full pytest coverage.

from micropython import const

# Default Conway rules
CONWAY_BIRTH = frozenset((3,))
CONWAY_SURVIVE = frozenset((2, 3))

# Friendly rules (easier for young children — cells survive more easily)
FRIENDLY_BIRTH = frozenset((2, 3))
FRIENDLY_SURVIVE = frozenset((1, 2, 3))

# Grid dimensions (coarse for chunky kid-friendly visuals)
GRID_W = const(16)
GRID_H = const(12)

# Color palette — first 8 are button colors (1-indexed: cell value 1–8),
# followed by intermediate mix colors for smoother blending.
CELL_COLORS = [
    # Button colors (indices 1–8)
    (255, 0, 0),  # 1: red
    (0, 255, 0),  # 2: green
    (0, 0, 255),  # 3: blue
    (255, 255, 0),  # 4: yellow
    (0, 255, 255),  # 5: cyan
    (255, 0, 255),  # 6: magenta
    (255, 128, 0),  # 7: orange
    (128, 0, 255),  # 8: purple
    # Mix colors (indices 9+, only produced by blending)
    (255, 128, 128),  # 9: pink (red + white-ish)
    (128, 255, 0),  # 10: lime (green + yellow)
    (0, 128, 255),  # 11: sky blue (blue + cyan)
    (255, 200, 0),  # 12: gold (yellow + orange)
    (0, 255, 128),  # 13: mint (green + cyan)
    (255, 0, 128),  # 14: rose (red + magenta)
    (128, 0, 128),  # 15: plum (blue + red dark)
    (128, 128, 0),  # 16: olive (red + green dark)
    (0, 128, 128),  # 17: teal (green + blue dark)
    (200, 100, 50),  # 18: rust (warm brown-ish)
    (128, 128, 255),  # 19: lavender (blue + white-ish)
    (255, 180, 100),  # 20: peach (orange + light)
]
N_BUTTON_COLORS = 8  # first 8 are directly plantable via buttons

# Preset garden plots — 8 highlighted positions for button planting (tier 1)
GARDEN_PLOTS = [
    (3, 2),
    (6, 2),
    (9, 2),
    (12, 2),
    (3, 9),
    (6, 9),
    (9, 9),
    (12, 9),
]


def _count_neighbours(grid, x, y, w, h, wrap):
    """Count alive neighbours of cell (x, y)."""
    count = 0
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            if wrap:
                nx = (x + dx) % w
                ny = (y + dy) % h
            else:
                nx = x + dx
                ny = y + dy
                if nx < 0 or nx >= w or ny < 0 or ny >= h:
                    continue
            if grid[ny * w + nx]:
                count += 1
    return count


def step(grid, w, h, birth=None, survive=None, wrap=False):
    """Evolve one generation.

    Args:
        grid: bytearray of length w*h. 0 = dead, 1+ = alive (color index).
        w, h: grid dimensions.
        birth: frozenset of neighbour counts that cause birth.
        survive: frozenset of neighbour counts that let a cell survive.
        wrap: if True, edges wrap around.

    Returns:
        (new_grid, births, deaths) where births and deaths are lists of
        (x, y) tuples for changed cells.
    """
    if birth is None:
        birth = CONWAY_BIRTH
    if survive is None:
        survive = CONWAY_SURVIVE

    new = bytearray(w * h)
    births = []
    deaths = []

    for y in range(h):
        row = y * w
        for x in range(w):
            idx = row + x
            alive = grid[idx]
            n = _count_neighbours(grid, x, y, w, h, wrap)
            if alive:
                if n in survive:
                    new[idx] = alive  # stays alive, keep color
                else:
                    deaths.append((x, y))
            else:
                if n in birth:
                    # New cell — color is a mix of parent colors
                    new[idx] = _mixed_color(grid, x, y, w, h, wrap)
                    births.append((x, y))

    return new, births, deaths


def _mixed_color(grid, x, y, w, h, wrap):
    """Mix parent colors: average RGB of alive neighbours, snap to nearest palette color."""
    r_sum, g_sum, b_sum = 0, 0, 0
    count = 0
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            if wrap:
                nx = (x + dx) % w
                ny = (y + dy) % h
            else:
                nx = x + dx
                ny = y + dy
                if nx < 0 or nx >= w or ny < 0 or ny >= h:
                    continue
            c = grid[ny * w + nx]
            if c:
                r, g, b = CELL_COLORS[min(c - 1, len(CELL_COLORS) - 1)]
                r_sum += r
                g_sum += g
                b_sum += b
                count += 1
    if count == 0:
        return 1
    # Average RGB of parents
    mr = r_sum // count
    mg = g_sum // count
    mb = b_sum // count
    # Find nearest palette color (squared distance, no sqrt needed)
    best = 1
    best_dist = 999999
    for i, (cr, cg, cb) in enumerate(CELL_COLORS):
        dr = mr - cr
        dg = mg - cg
        db = mb - cb
        dist = dr * dr + dg * dg + db * db
        if dist < best_dist:
            best_dist = dist
            best = i + 1  # 1-indexed
    return best


def population(grid):
    """Count total alive cells."""
    count = 0
    for c in grid:
        if c:
            count += 1
    return count


def is_empty(grid):
    """Check if all cells are dead."""
    for c in grid:
        if c:
            return False
    return True


def clear(w, h):
    """Create an empty grid."""
    return bytearray(w * h)


def place(grid, x, y, w, color_idx=1):
    """Place a cell at (x, y). color_idx 1–8."""
    grid[y * w + x] = color_idx


def remove(grid, x, y, w):
    """Remove a cell at (x, y)."""
    grid[y * w + x] = 0


def toggle(grid, x, y, w, color_idx=1):
    """Toggle a cell at (x, y). Returns True if cell is now alive."""
    idx = y * w + x
    if grid[idx]:
        grid[idx] = 0
        return False
    else:
        grid[idx] = color_idx
        return True


def load_preset(pattern_data, grid, w, h, ox=0, oy=0):
    """Load a preset pattern into the grid at offset (ox, oy).

    pattern_data: list of (x, y) tuples relative to top-left of pattern.
    """
    for px, py in pattern_data:
        x = ox + px
        y = oy + py
        if 0 <= x < w and 0 <= y < h:
            grid[y * w + x] = 1
