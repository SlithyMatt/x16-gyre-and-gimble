#!/usr/bin/env python3
"""Render the ring board: a static backdrop plus pre-shaded cell pieces.

The board is a 320x240 8bpp bitmap on VERA layer 0. Each screen cell (ring
r, position p) owns a *footprint*: its band of the ring plus the near half
of each wall around it. The game draws a cell by copying *pieces* into its
footprint, ORing in the cell's class row (see tools/shading.py):

  base    the cell body as a beveled, anti-aliased slab, with its walls
  in/out  a notch for an inward/outward opening, halfway across the wall
  cw/ccw  the body continuing through the separator to its neighbor
  tin/tout   gear teeth on the ring's inner/outer edge, drawn in the ring's
             stone color when a gimbal links it to the ring across that gap

Each half-cell of a gap, between the radial notch and the cell's edge, is
split into slots that alternate between the outer ring's teeth and the inner
ring's. The boundary between the two rings' footprints follows the slots, so
each ring's teeth reach past the middle of the gap between the other's: when
both rings have teeth they mesh, with a sliver of wall as clearance. Around
each radial notch the boundary stays at the middle of the gap.

Two notches that line up make a passage through the wall. The outer ring's
outward openings notch the rim, which only the entry cuts all the way through.
Pixels are supersampled for coverage, and an emboss filter lit from the
top-left gives the bevel.

Outputs:
  RINGS.BIN    headerless bitmap: the garden (tools/garden.py), rim, entry,
               burrow (the footprints start as plain wall; the game draws
               the cells)
  CELLS.BIN    the pieces, packed into 8 KB banks of high RAM from CELLS_BANK.
               A piece is spans of [length, VRAM address (3 bytes), pixels],
               ended by a zero length; no piece crosses a bank.
  board.inc    palette rows and slots, and where the pieces are
  pieces.inc   the piece tables (bank and address of each piece)
  waypoints    screen coordinates the tove walks through: every cell center,
               arc gate and radial gate, plus the entry and the burrow; and
               the critters' bands and waypoints in the garden

Usage: genrings.py RINGS.BIN CELLS.BIN board.inc pieces.inc waypoints.inc
"""
import math
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import shading as sh  # noqa: E402
import garden  # noqa: E402

W, H = 320, 240
CX, CY = 160, 120
RINGS, CELLS = 4, 12
NCELLS = RINGS * CELLS
STEP = 360 / CELLS

# Everything stays inside the CRT title-safe area (10% margins: x 32-287,
# y 24-215). The board's outer edge is at radius 88, leaving 8x4-character
# corners for the HUD.
BURROW_R = 12       # burrow radius
RING_IN0 = 16       # inner radius of ring 0
RING_PITCH = 18     # distance between rings' inner radii
RING_W = 10         # ring band width (the gap is RING_PITCH - RING_W)
GAP_W = RING_PITCH - RING_W     # wide enough that a half-gap notch reads on composite
RADIAL_HALF = 4.0   # max half-width of a radial notch, in pixels
RADIAL_ANG = 12.0   # max half-width of a radial notch, in degrees (inner gaps)
ARC_HALF = 1.5      # half-width of the separator between cells, in pixels
TOOTH_SLOT = 6.0    # target width of a tooth slot along the gap, in pixels
TOOTH_REACH = 2.0   # each ring's teeth reach this far past the middle of the gap
TOOTH_CLEAR = 0.75  # wall left between meshing teeth, in pixels
NOTCH_CLEAR = 1.0   # teeth keep this far from a radial notch
RIM_OUT = RING_IN0 + RINGS * RING_PITCH         # 88

SS = 4              # supersamples per pixel, per axis
EXT = 4.0           # openings run on past the footprint, so their ends shade
EXT_DEG = 15.0      # ... as if they continue (seamless when they meet)
BEVEL = ((1, 1.0), (2, 0.5))    # emboss taps: (pixel offset, weight)
BEVEL_GAIN = 1.4

CELLS_BANK = 1      # bank 0 is the KERNAL's
BANK_SIZE = 8192
KINDS = ("base", "in", "out", "cw", "ccw")
TEETH_KINDS = ("tin", "tout")


def ring_in(r):
    return RING_IN0 + r * RING_PITCH


def polar(x, y):
    dx, dy = x - CX, y - CY
    return math.hypot(dx, dy), math.degrees(math.atan2(dx, -dy)) % 360


def sdiff(a, b):
    return (a - b + 180) % 360 - 180


def gap_mid(k):
    """Radius of the middle of gap k, between rings k-1 and k."""
    return ring_in(k) - GAP_W / 2


def tooth_slots(k):
    """Slot layout of gap k: (notch half-angle, slots per half-cell, slot angle)."""
    m = gap_mid(k)
    notch = math.degrees((min(RADIAL_HALF, m * math.sin(math.radians(RADIAL_ANG)))
                          + NOTCH_CLEAR) / m)
    room = STEP / 2 - notch
    n = max(1, round(m * math.radians(room) / TOOTH_SLOT))
    return notch, n, room / n


def tooth_slot(k, d, a):
    """The tooth slot of gap k at (d, a): (outer ring's?, pixels from the slot's
    center line, slot half-width in pixels), or None by a radial notch."""
    notch, n, width = tooth_slots(k)
    da = sdiff(a, round(a / STEP) * STEP)
    if abs(da) < notch:
        return None
    j = min(n - 1, int((abs(da) - notch) / width))
    index = n - 1 - j if da < 0 else n + j      # counting clockwise across the cell
    center = notch + (j + 0.5) * width
    return index % 2 == 0, d * math.radians(abs(da) - center), d * math.radians(width / 2)


def footprint(x, y):
    """(r, p) of the cell that owns pixel (x, y), or None."""
    d, a = polar(x + 0.5, y + 0.5)
    p = round(a / STEP) % CELLS
    for k in range(1, RINGS):   # the meshing zone: each ring owns its teeth
        m = gap_mid(k)
        if m - TOOTH_REACH <= d < m + TOOTH_REACH:
            slot = tooth_slot(k, d, a)
            if slot:
                return (k if slot[0] else k - 1), p
    for r in range(RINGS):
        lo = BURROW_R if r == 0 else gap_mid(r)
        if lo <= d < ring_in(r) + RING_W + GAP_W / 2:
            return r, p
    return None


def cell_shapes(r, p):
    """Membership tests f(d, da) for the cell body and each opening."""
    lo, hi = ring_in(r), ring_in(r) + RING_W
    sin = math.sin
    rad = math.radians

    def band(d):
        return lo <= d < hi

    def cone(d, da):
        return abs(da) < RADIAL_ANG and d * sin(rad(abs(da))) < RADIAL_HALF

    return {
        "base": lambda d, da: (band(d) and abs(da) < STEP / 2
                               and d * sin(rad(STEP / 2 - abs(da))) >= ARC_HALF),
        "in": lambda d, da: (cone(d, da)
                             and (0 if r == 0 else lo - GAP_W / 2 - EXT) <= d < lo + 2),
        "out": lambda d, da: cone(d, da) and hi - 2 <= d < hi + GAP_W / 2 + EXT,
        "cw": lambda d, da: band(d) and 0 <= da < STEP / 2 + EXT_DEG,
        "ccw": lambda d, da: band(d) and -STEP / 2 - EXT_DEG < da <= 0,
    }


def ring_teeth(r):
    """Membership tests f(d, a) for ring r's teeth on its inner and outer edge."""
    lo, hi = ring_in(r), ring_in(r) + RING_W

    def tooth(k, outer, root, tip):
        def test(d, a):
            if not (min(root, tip) <= d < max(root, tip)):
                return False
            slot = tooth_slot(k, d, a)
            if not slot or slot[0] != outer:
                return False
            t = abs(d - root) / abs(tip - root)     # 0 at the root, 1 at the tip
            return abs(slot[1]) < slot[2] - TOOTH_CLEAR / 2 * (1 + t)  # tapered
        return test

    none = lambda d, a: False  # noqa: E731
    tin = tooth(r, True, lo + 1, gap_mid(r) - TOOTH_REACH + TOOTH_CLEAR) if r > 0 else none
    tout = tooth(r + 1, False, hi - 1, gap_mid(r + 1) + TOOTH_REACH - TOOTH_CLEAR) \
        if r < RINGS - 1 else none
    return tin, tout


def coverage(tests, n, x0, y0, w, h):
    """Supersampled coverage of each of the n shapes tests() reports, over a pixel box."""
    covs = [[0.0] * (w * h) for _ in range(n)]
    inc = 1 / (SS * SS)
    for j in range(h):
        for i in range(w):
            k = j * w + i
            for sy in range(SS):
                for sx in range(SS):
                    flags = tests(x0 + i + (sx + 0.5) / SS, y0 + j + (sy + 0.5) / SS)
                    for v, f in enumerate(flags):
                        if f:
                            covs[v][k] += inc
    return covs


def bucket(c):
    return min(sh.COVERS, key=lambda v: abs(v - c))


def emboss(cov, w, k):
    """Bevel level -2..+2 at index k: + where the top-left side is open."""
    e = sum(wt * (cov[k + o * w + o] - cov[k - o * w - o]) for o, wt in BEVEL)
    return max(-2, min(2, round(e * BEVEL_GAIN)))


def shade_pixel(cov, w, k, literal):
    c = cov[k]
    if c <= 0.1:
        return literal
    b = emboss(cov, w, k)
    if c >= 0.9:
        return sh.full_slot(b)
    return sh.edge_slot(bucket(c), (b > 0) - (b < 0))


def render_cell(r, p, pixels):
    """{kind: {(x, y): value}} for the footprint pixels each piece draws."""
    shapes = cell_shapes(r, p)
    m = 1 + max(o for o, _ in BEVEL)
    xs = [x for x, _ in pixels]
    ys = [y for _, y in pixels]
    x0, y0 = min(xs) - m, min(ys) - m
    w, h = max(xs) - x0 + m + 1, max(ys) - y0 + m + 1
    c = p * STEP
    base, rest = shapes["base"], [shapes[k] for k in KINDS[1:]]
    lo, hi = ring_in(r), ring_in(r) + RING_W
    tin, tout = ring_teeth(r)

    def tests(x, y):
        d, a = polar(x, y)
        da = sdiff(a, c)
        b = base(d, da)
        band = lo <= d < hi
        return [b] + [b or f(d, da) for f in rest] + [band or tin(d, a), band or tout(d, a), band]

    covs = coverage(tests, len(KINDS) + len(TEETH_KINDS) + 1, x0, y0, w, h)
    band_cov = covs[-1]
    wall = sh.ROW_WALL << 4 | sh.WALL_SLOT
    out = {}
    for v, kind in enumerate(KINDS + TEETH_KINDS):
        out[kind] = {(x, y): shade_pixel(covs[v], w, (y - y0) * w + x - x0, wall)
                     for x, y in pixels}
    base_px = out["base"]
    for kind in KINDS[1:]:      # an opening draws only what it changes
        out[kind] = {xy: v for xy, v in out[kind].items() if v != base_px[xy]}
    for kind in TEETH_KINDS:    # teeth draw only in the gap, never over the body
        out[kind] = {(x, y): v for (x, y), v in out[kind].items()
                     if v != wall and band_cov[(y - y0) * w + x - x0] < 0.5}
    return out


def spans(px):
    """Encode {(x, y): value} as row spans, ended by a zero length."""
    data = bytearray()
    keys = sorted(px, key=lambda xy: (xy[1], xy[0]))
    i = 0
    while i < len(keys):
        x, y = keys[i]
        run = [px[keys[i]]]
        i += 1
        while i < len(keys) and keys[i] == (x + len(run), y) and len(run) < 255:
            run.append(px[keys[i]])
            i += 1
        addr = y * W + x
        data += bytes([len(run), addr & 0xFF, addr >> 8 & 0xFF, addr >> 16]) + bytes(run)
    return data + b"\0"


def static_pixel(x, y, burrow_cov, burrow_w, bx0, by0, lawn):
    """Garden, rim, entry and burrow (everything outside the footprints)."""
    if footprint(x, y):
        return sh.ROW_WALL << 4 | sh.WALL_SLOT
    d, a = polar(x + 0.5, y + 0.5)
    fixed = sh.ROW_FIXED << 4
    if d < BURROW_R:
        k = (y - by0) * burrow_w + x - bx0
        c = burrow_cov[k]
        if c <= 0.1:
            return sh.ROW_WALL << 4 | sh.WALL_SLOT
        if c >= 0.9:
            b = max(-1, min(1, emboss(burrow_cov, burrow_w, k)))
            return fixed | sh.BURROW_SLOT + b + 1
        return fixed | sh.BURROW_SLOT + 3 + sh.COVERS[::-1].index(bucket(c))

    def frac(test):
        n = sum(test(*polar(x + (i + 0.5) / SS, y + (j + 0.5) / SS))
                for j in range(SS) for i in range(SS))
        return n / (SS * SS)

    rim = frac(lambda d, a: d < RIM_OUT)
    if rim <= 0.1:
        return lawn[y * W + x]
    entry = frac(lambda d, a: abs(sdiff(a, 0)) < 90
                 and d * math.sin(math.radians(abs(sdiff(a, 0)))) < RADIAL_HALF)
    if entry >= 0.9:
        return fixed | sh.ENTRY_SLOT
    if entry > 0.1:
        return fixed | sh.ENTRY_SLOT + 1 + sh.COVERS[::-1].index(bucket(entry))
    if rim >= 0.9:
        return sh.ROW_WALL << 4 | sh.WALL_SLOT
    return sh.ROW_WALL << 4 | sh.WALL_EDGE[bucket(rim)]


def backdrop(lawn):
    r = BURROW_R + 3
    bx0, by0, bw = CX - r, CY - r, 2 * r
    bcov = coverage(lambda x, y: [polar(x, y)[0] < BURROW_R - 0.5], 1, bx0, by0, bw, bw)[0]
    return bytes(static_pixel(x, y, bcov, bw, bx0, by0, lawn) for y in range(H) for x in range(W))


def pieces():
    """Every cell's pieces, packed into banks; returns (blob, table)."""
    owned = {}
    for y in range(CY - RIM_OUT, CY + RIM_OUT + 1):
        for x in range(CX - RIM_OUT, CX + RIM_OUT + 1):
            fp = footprint(x, y)
            if fp:
                owned.setdefault(fp, []).append((x, y))
    banks = [bytearray()]
    table = [None] * ((len(KINDS) + len(TEETH_KINDS)) * NCELLS)
    for r in range(RINGS):
        for p in range(CELLS):
            rendered = render_cell(r, p, owned[r, p])
            for v, kind in enumerate(KINDS + TEETH_KINDS):
                data = spans(rendered[kind])
                if len(banks[-1]) + len(data) > BANK_SIZE:
                    banks.append(bytearray())
                table[v * NCELLS + r * CELLS + p] = (CELLS_BANK + len(banks) - 1,
                                                     0xA000 + len(banks[-1]))
                banks[-1] += data
    blob = b"".join(bytes(b) + b"\0" * (BANK_SIZE - len(b)) for b in banks[:-1]) + bytes(banks[-1])
    return blob, table


def point(radius, angle):
    a = math.radians(angle)
    return round(CX + radius * math.sin(a)), round(CY - radius * math.cos(a))


def waypoints(f, bands):
    """Byte tables of x/y per cell index r*12+p (the board fits in x < 256)."""
    tables = {"cx": [], "cy": [], "ax": [], "ay": [], "rx": [], "ry": []}
    for r in range(RINGS):
        mid = ring_in(r) + RING_W / 2
        gap = ring_in(r) - GAP_W / 2
        for p in range(CELLS):
            for key, (x, y) in (("c", point(mid, p * STEP)),
                                ("a", point(mid, p * STEP + STEP / 2)),
                                ("r", point(gap, p * STEP))):
                tables[key + "x"].append(x)
                tables[key + "y"].append(y)
    ex, ey = point(ring_in(RINGS) - GAP_W / 2, 0)
    f.write("; generated by tools/genrings.py — do not edit\n")
    f.write(f"ENTRY_X = {ex}\nENTRY_Y = {ey}\nBURROW_X = {CX}\nBURROW_Y = {CY}\n")
    names = {"c": "cell center", "a": "arc gate to the clockwise neighbor",
             "r": "radial gate on the inner side"}
    for key, vals in tables.items():
        assert all(0 <= v < 256 for v in vals)
        f.write(f"wp_{key}:  ; {names[key[0]]}, {key[1]}\n")
        for k in range(0, len(vals), CELLS):
            f.write("    .byte " + ", ".join(map(str, vals[k:k + CELLS])) + "\n")
    f.write(f"; critters: each band's screen x offset, then {garden.TARGETS} waypoints\n"
            f"; per band (sprite corner, x relative to the offset)\n"
            f"CRITTER_TARGETS = {garden.TARGETS}\nNBANDS = {len(bands)}\n")
    f.write("band_x:\n    .word " + ", ".join(str(b[0]) for b in garden.BANDS) + "\n")
    for key, n in (("tx", 0), ("ty", 1)):
        f.write(f"band_{key}:\n")
        for targets in bands:
            f.write("    .byte " + ", ".join(str(t[n]) for t in targets) + "\n")


def main():
    out_bin, out_cells, out_inc, out_pieces, out_wp = sys.argv[1:6]
    lawn, kind = garden.render(CX, CY, RIM_OUT, RADIAL_HALF)
    bands = garden.critter_bands(kind)
    with open(out_bin, "wb") as f:
        f.write(backdrop(lawn))
    blob, table = pieces()
    with open(out_cells, "wb") as f:
        f.write(blob)
    with open(out_inc, "w") as f:
        f.write("; generated by tools/genrings.py — do not edit\n")
        for name in ("ROW_STONE", "ROW_TUNNEL", "ROW_LIT", "ROW_WALL", "ROW_FIXED", "ROW_TOVE",
                     "ROW_GARDEN", "ROW_CRITTER",
                     "BURROW_SLOT", "BURROW_SLOTS", "ENTRY_SLOT", "ENTRY_SLOTS"):
            f.write(f"{name} = {getattr(sh, name)}\n")
        nbanks = (len(blob) + BANK_SIZE - 1) // BANK_SIZE
        f.write(f"CELLS_BANK = {CELLS_BANK}\nCELLS_BANKS = {nbanks}\n")
    with open(out_pieces, "w") as f:
        f.write("; generated by tools/genrings.py — do not edit\n")
        split = len(KINDS) * NCELLS
        for prefix, kinds, entries in (("piece", KINDS, table[:split]),
                                       ("teeth", TEETH_KINDS, table[split:])):
            f.write(f"; {prefix}: index = kind * {NCELLS} + cell, kinds {', '.join(kinds)}\n")
            for name, fn in (("bank", lambda e: e[0]), ("lo", lambda e: e[1] & 0xFF),
                             ("hi", lambda e: e[1] >> 8)):
                f.write(f"{prefix}_{name}:\n")
                for k in range(0, len(entries), CELLS):
                    f.write("    .byte " + ", ".join(f"${fn(e):02x}" for e in entries[k:k + CELLS]) + "\n")
    with open(out_wp, "w") as f:
        waypoints(f, bands)
    print(f"{out_cells}: {len(blob)} bytes in {nbanks} banks")


if __name__ == "__main__":
    main()
