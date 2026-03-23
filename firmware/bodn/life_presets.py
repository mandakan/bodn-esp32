# bodn/life_presets.py — preset patterns for Game of Life
#
# Each preset is (name, width, height, cells) where cells is a list of
# (x, y) tuples relative to the pattern's top-left corner.

# Oscillators
BLINKER = ("Blinker", 3, 1, [(0, 0), (1, 0), (2, 0)])

TOAD = (
    "Toad",
    4,
    2,
    [(1, 0), (2, 0), (3, 0), (0, 1), (1, 1), (2, 1)],
)

BEACON = (
    "Beacon",
    4,
    4,
    [(0, 0), (1, 0), (0, 1), (3, 2), (2, 3), (3, 3)],
)

PULSAR = (
    "Pulsar",
    13,
    13,
    [
        (2, 0),
        (3, 0),
        (4, 0),
        (8, 0),
        (9, 0),
        (10, 0),
        (0, 2),
        (5, 2),
        (7, 2),
        (12, 2),
        (0, 3),
        (5, 3),
        (7, 3),
        (12, 3),
        (0, 4),
        (5, 4),
        (7, 4),
        (12, 4),
        (2, 5),
        (3, 5),
        (4, 5),
        (8, 5),
        (9, 5),
        (10, 5),
        (2, 7),
        (3, 7),
        (4, 7),
        (8, 7),
        (9, 7),
        (10, 7),
        (0, 8),
        (5, 8),
        (7, 8),
        (12, 8),
        (0, 9),
        (5, 9),
        (7, 9),
        (12, 9),
        (0, 10),
        (5, 10),
        (7, 10),
        (12, 10),
        (2, 12),
        (3, 12),
        (4, 12),
        (8, 12),
        (9, 12),
        (10, 12),
    ],
)

# Still lifes
BLOCK = ("Block", 2, 2, [(0, 0), (1, 0), (0, 1), (1, 1)])

# Spaceships
GLIDER = (
    "Glider",
    3,
    3,
    [(1, 0), (2, 1), (0, 2), (1, 2), (2, 2)],
)

LWSS = (
    "LWSS",
    5,
    4,
    [(1, 0), (4, 0), (0, 1), (0, 2), (4, 2), (0, 3), (1, 3), (2, 3), (3, 3)],
)

# Methuselahs (long-lived)
R_PENTOMINO = (
    "R-pentomino",
    3,
    3,
    [(1, 0), (2, 0), (0, 1), (1, 1), (1, 2)],
)

ACORN = (
    "Acorn",
    7,
    3,
    [(1, 0), (3, 1), (0, 2), (1, 2), (4, 2), (5, 2), (6, 2)],
)

# Ordered list for menu selection
PRESETS = [
    BLINKER,
    BLOCK,
    TOAD,
    BEACON,
    GLIDER,
    LWSS,
    R_PENTOMINO,
    ACORN,
    PULSAR,
]
