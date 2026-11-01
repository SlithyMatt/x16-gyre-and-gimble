"""Shared shading model for the board: palette rows, ramp slots and themes.

The board is drawn with a few color *classes* (ring stone, tunnel, lit
tunnel, wall...). Each class owns one 16-entry palette row, and every board
pixel stores a *slot* in that row whose meaning is the same for every class:

  slots 0-4    full coverage, bevel -2..+2 (+ faces the light, top-left)
  slots 5-13   anti-aliased edge: 3 coverage levels x bevel sign (-, 0, +),
               blended toward the wall color

A cell is drawn by ORing its class row into the slot values, so the same
pre-rendered pixels serve stone (raised), tunnel and lit tunnel (recessed:
the ramp inverts the bevel). Wall-row pixels are literal: rows 7 and 15 have
every bit the class OR can set, so the OR leaves them alone.

A theme picks the color for each class. Every theme is built around the
same small set of hues, and on composite video the classes must stay apart
in luma, so build_theme checks their order.
"""

# Palette rows (row r is indices 16r..16r+15). Row 0 is the text layer's.
ROW_STONE = 1           # + ring: each ring's stone, recolored for selection
ROW_TUNNEL = 5
ROW_LIT = 6
ROW_WALL = 7            # literal: walls and the rim
ROW_FIXED = 15          # literal: burrow, entry
ROW_TOVE = 14           # the tove sprite's palette offset

CLASS_ROWS = range(1, 7)
assert all((r << 4) | 0x70 == 0x70 for r in CLASS_ROWS)  # OR can't touch row 7
assert all((r << 4) | 0xF0 == 0xF0 for r in CLASS_ROWS)  # ... or row 15

# Slots in a class row
BEVELS = (-2, -1, 0, 1, 2)
COVERS = (0.25, 0.5, 0.75)
SIGNS = (-1, 0, 1)
CLASS_SLOTS = len(BEVELS) + len(COVERS) * len(SIGNS)    # 14


def full_slot(b):
    return b + 2


def edge_slot(cover, sign):
    return len(BEVELS) + COVERS.index(cover) * len(SIGNS) + sign + 1


# Slots in the wall row: the wall, then its blend toward the black background
WALL_SLOT = 0
WALL_EDGE = {0.75: 1, 0.5: 2, 0.25: 3}
WALL_SLOTS = 4

# Slots in the fixed row
BURROW_SLOT = 0         # 0-2 bevel -1..+1, 3-5 edges blended toward the wall
BURROW_SLOTS = 6
ENTRY_SLOT = 6          # 6 full, 7-9 edges blended toward the wall
ENTRY_SLOTS = 4

# How strongly each class is beveled, and whether it's raised (lit from the
# top-left) or recessed (shadowed there)
STYLE = {
    "stone": (1.0, True), "sel": (1.0, True), "follow": (1.0, True),
    "counter": (1.0, True), "tunnel": (0.6, False), "lit": (0.5, False),
    "burrow": (0.6, False), "home": (0.4, False),
}

CLASSES = ("stone", "sel", "follow", "counter", "tunnel", "lit", "wall",
           "burrow", "home")

# Composite video: these must get brighter in this order (luma, 0-15)
LUMA_ORDER = ("tunnel", "wall", "stone", "sel", "lit")
LUMA_GAP = 1.5


def luma(c):
    r, g, b = c
    return 0.299 * r + 0.587 * g + 0.114 * b


def clamp(c):
    return tuple(max(0, min(15, round(v))) for v in c)


def mix(a, b, t):
    """t of a, the rest b."""
    return tuple(x * t + y * (1 - t) for x, y in zip(a, b))


def shade(c, b, name):
    strength, raised = STYLE[name]
    k = 0.18 * strength * (b if raised else -b)
    if k >= 0:
        return tuple(v + (15 - v) * k for v in c)
    return tuple(v * (1 + k) for v in c)


def class_ramp(c, wall, name):
    ramp = [None] * CLASS_SLOTS
    for b in BEVELS:
        ramp[full_slot(b)] = shade(c, b, name)
    for cover in COVERS:
        for s in SIGNS:
            ramp[edge_slot(cover, s)] = mix(shade(c, s, name), wall, cover)
    return [clamp(v) for v in ramp]


def small_ramp(c, wall, name):
    """Burrow/home: bevel -1..+1, then three edges toward the wall."""
    ramp = [shade(c, b, name) for b in (-1, 0, 1)]
    ramp += [mix(shade(c, 0, name), wall, cover) for cover in COVERS[::-1]]
    return [clamp(v) for v in ramp]


def parse_themes(path):
    """{name: {class: (r, g, b)}} in file order."""
    themes, cur = {}, None
    for raw in open(path):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        toks = line.split()
        if toks[0] == "theme":
            cur = themes[toks[1]] = {}
        elif cur is not None and toks[0] in CLASSES and len(toks) == 4:
            cur[toks[0]] = tuple(int(t) for t in toks[1:])
        else:
            raise SystemExit(f"{path}: bad line {line!r}")
    for name, t in themes.items():
        missing = [c for c in CLASSES if c not in t]
        if missing:
            raise SystemExit(f"{path}: theme {name} lacks {' '.join(missing)}")
        lumas = [luma(t[c]) for c in LUMA_ORDER]
        if any(b - a < LUMA_GAP for a, b in zip(lumas, lumas[1:])):
            raise SystemExit(f"{path}: theme {name}: {' < '.join(LUMA_ORDER)} "
                             f"need luma gaps of {LUMA_GAP} (have "
                             f"{', '.join(f'{v:.1f}' for v in lumas)})")
    return themes


def build_theme(t):
    """The theme's palette data, as lists of (r, g, b) in TH_* order."""
    w = t["wall"]
    black = (0, 0, 0)
    out = {}
    for name in ("stone", "sel", "follow", "counter", "tunnel", "lit"):
        out[name] = class_ramp(t[name], w, name)
    out["wall"] = [clamp(w)] + [clamp(mix(w, black, c)) for c in (0.75, 0.5, 0.25)]
    out["burrow"] = small_ramp(t["burrow"], w, "burrow")
    out["home"] = small_ramp(t["home"], w, "home")
    lit = shade(t["lit"], 0, "lit")
    out["entry"] = [clamp(lit)] + [clamp(mix(lit, w, c)) for c in (0.75, 0.5, 0.25)]
    return out
