"""The garden around the board: lawn, hedged text panels, flower beds, a path.

The board sits on a mown lawn, casting a shadow down and to the right (the
light is top-left, as on the board). Each block of HUD text sits on dark
paving inside a stone kerb, bordered by a flowering hedge; where a panel
meets the board, its kerb follows the rim. Flower beds edge the screen,
outside the title-safe area, and a gravel path leads in to the entry gap.

Every pixel is a slot in one of the garden materials' ramps (see
GARDEN_LAYOUT in tools/shading.py), so each level's theme recolors it.

Composite TV: the lawn texture is broad and low in contrast; the paving
under the text is dark and nearly flat. Fine detail (flowers, leaves) stays
in the hedges and beds.

Critters (borogoves and mome raths) wander the two lawns beside the board;
critter_bands() says where.
"""
import math
import random

import shading as sh

W, H = 320, 240

# HUD text blocks as character cells (col0, row0, col1, row1), inclusive.
# Keep in step with draw_hud and draw_status in src/main.asm.
PANELS = ((4, 3, 11, 8), (27, 3, 35, 8), (4, 23, 11, 26), (28, 24, 35, 26))
PAD = 3             # paving beyond the text
CORNER = 3          # paving corner radius
KERB = 2
HEDGE = 6.0         # hedge depth, plus up to HEDGE_BUMP
HEDGE_BUMP = 3.0
BED = 8.0           # flower bed depth at the screen edge, plus up to BED_BUMP
BED_BUMP = 4.0
PATH_HALF = 6.0     # half-width of the path to the entry
SHADOW = (3, 4)     # the board's shadow offset
STRIPE = 16         # lawn mowing stripe width

# Critter bands: the rectangles critters' sprite corners stay in, as
# (screen x of the band's x = 0, x0, y0, x1, y1). Checked against the garden.
BANDS = ((0, 12, 84, 52, 152), (240, 12, 84, 52, 152))
TARGETS = 16        # waypoints per band


def mat(name):
    for n, first, count in sh.GARDEN_LAYOUT:
        if n == name:
            return first, count
    raise KeyError(name)


def slot(name, b):
    """Palette index for material name at brightness b (-1 shadow .. +1 light)."""
    first, n = mat(name)
    s = round((max(-1.0, min(1.0, b)) + 1) / 2 * (n - 1))
    return (sh.ROW_GARDEN << 4) + first + s


def bloom_slot(k, s):
    first, _ = mat(f"bloom{k + 1}")
    return (sh.ROW_GARDEN << 4) + first + s


class Noise:
    """Smooth value noise in [0, 1]."""

    def __init__(self, seed):
        self.seed = seed

    def lattice(self, i, j):
        h = (i * 374761393 + j * 668265263 + self.seed * 2147483647) & 0xFFFFFFFF
        h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
        return (h ^ (h >> 16)) / 0xFFFFFFFF

    def __call__(self, x, y):
        i, j = math.floor(x), math.floor(y)
        fx, fy = x - i, y - j
        fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
        a, b = self.lattice(i, j), self.lattice(i + 1, j)
        c, d = self.lattice(i, j + 1), self.lattice(i + 1, j + 1)
        return (a + (b - a) * fx) + ((c + (d - c) * fx) - (a + (b - a) * fx)) * fy


def panel_rect(p):
    c0, r0, c1, r1 = p
    return c0 * 8 - PAD, r0 * 8 - PAD, (c1 + 1) * 8 + PAD, (r1 + 1) * 8 + PAD


def panel_sdf(x, y, cx, cy, clear):
    """Signed distance outside the nearest panel (negative inside). A panel
    is its rounded rectangle less the disc of radius clear around the board."""
    best = 1e9
    for p in PANELS:
        x0, y0, x1, y1 = panel_rect(p)
        hx, hy = (x1 - x0) / 2 - CORNER, (y1 - y0) / 2 - CORNER
        qx = abs(x - (x0 + x1) / 2) - hx
        qy = abs(y - (y0 + y1) / 2) - hy
        rect = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - CORNER
        best = min(best, max(rect, clear - math.hypot(x - cx, y - cy)))
    return best


def render(cx, cy, rim, entry_half):
    """The garden as a W*H list of palette indices (the caller draws the
    board over it)."""
    rng = random.Random(16)
    lawn_n, leaf_n, bump_n, bed_n = Noise(1), Noise(2), Noise(3), Noise(4)
    clear = rim + KERB + 1

    sdf = [[panel_sdf(x + 0.5, y + 0.5, cx, cy, clear) for x in range(W)] for y in range(H)]

    def hedge_depth(x, y):
        return HEDGE + HEDGE_BUMP * bump_n(x / 5, y / 5)

    def bed_depth(x, y):
        return BED + BED_BUMP * bed_n(x / 7, y / 7)

    def on_path(x, y):
        return y < cy - rim + 3 and abs(x + 0.5 - cx) < PATH_HALF + 1.5 * bed_n(y / 6, 9)

    kind = [[None] * W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            s = sdf[y][x]
            edge = min(x, y, W - 1 - x, H - 1 - y)
            if s <= 0:
                kind[y][x] = "paving"
            elif s <= KERB:
                kind[y][x] = "kerb"
            elif s <= KERB + hedge_depth(x, y):
                kind[y][x] = "hedge"
            elif on_path(x, y):
                kind[y][x] = "path"
            elif edge < bed_depth(x, y):
                kind[y][x] = "bed"
            else:
                kind[y][x] = "lawn"

    def at(x, y):
        return kind[y][x] if 0 <= x < W and 0 <= y < H else "bed"

    # Hedge height: a rounded profile across its depth, plus leafy lumps
    def hedge_h(x, y):
        if at(x, y) != "hedge":
            return 0.0
        t = (sdf[y][x] - KERB) / hedge_depth(x, y)
        return 4 * t * (1 - t) + 0.6 * leaf_n(x / 2.2, y / 2.2)

    hh = [[hedge_h(x, y) for x in range(W)] for y in range(H)]

    def h_at(x, y):
        return hh[y][x] if 0 <= x < W and 0 <= y < H else 0.0

    # Paving stones: staggered courses, each stone a slightly different shade
    def paving(x, y):
        course = y // 9
        off = 6 if course % 2 else 0
        if y % 9 == 0 or (x + off) % 13 == 0:
            return slot("paving", -0.45)
        stone = random.Random(course * 1000 + (x + off) // 13).uniform(-0.2, 0.05)
        return slot("paving", stone)

    out = [0] * (W * H)
    for y in range(H):
        for x in range(W):
            k = kind[y][x]
            if k == "paving":
                v = paving(x, y)
            elif k == "kerb":
                # Lit where its outward face turns toward the top-left
                gx = sdf[y][min(W - 1, x + 1)] - sdf[y][max(0, x - 1)]
                gy = sdf[min(H - 1, y + 1)][x] - sdf[max(0, y - 1)][x]
                n = math.hypot(gx, gy) or 1
                face = -(gx + gy) / (n * math.sqrt(2))
                if sdf[y][x] <= KERB / 2:
                    face = -face     # inner half faces in
                v = slot("kerb", 0.15 + 0.7 * face)
            elif k == "hedge":
                e = h_at(x - 1, y - 1) - h_at(x + 1, y + 1)
                b = 0.1 + 1.1 * e + 0.6 * (leaf_n(x / 1.3, y / 1.3) - 0.5)
                if at(x + 1, y + 1) != "hedge" and at(x + 1, y + 1) != "kerb":
                    b -= 0.4    # underside
                v = slot("hedge", b)
            elif k == "path":
                b = 0.1 + 0.35 * (lawn_n(x / 1.5, y / 1.5) - 0.5)
                if abs(x + 0.5 - cx) > PATH_HALF - 0.5:
                    b -= 0.35
                v = slot("path", b)
            elif k == "bed":
                lv = leaf_n(x / 3, y / 3)
                if lv > 0.55:
                    v = slot("hedge", -0.4 + 1.6 * (lv - 0.55) + 0.3 * (leaf_n(x, y) - 0.5))
                else:
                    v = slot("soil", -0.3 + 0.5 * (lawn_n(x / 2, y / 2) - 0.5))
            else:
                stripe = 0.12 if ((x + y) // STRIPE) % 2 else -0.12
                b = stripe + 0.45 * (lawn_n(x / 9, y / 9) - 0.5) + 0.15 * (leaf_n(x / 1.7, y / 1.7) - 0.5)
                sx, sy = x - SHADOW[0] + 0.5, y - SHADOW[1] + 0.5
                d = math.hypot(sx - cx, sy - cy)
                b -= 0.6 * max(0.0, min(1.0, rim + 1 - d))
                if any(at(x - i, y - i) in ("hedge", "kerb") for i in (2, 3)):
                    b -= 0.45
                v = slot("grass", b)
            out[y * W + x] = v

    # Flowers: in the hedges and the beds, on a jittered grid
    def flowers(where, pitch, chance, kinds):
        for gy in range(0, H, pitch):
            for gx in range(0, W, pitch):
                if rng.random() > chance:
                    continue
                fx, fy = gx + rng.randrange(pitch), gy + rng.randrange(pitch)
                if not all(0 <= fx + i < W and 0 <= fy + j < H and kind[fy + j][fx + i] in where
                           for i in (-1, 0, 1) for j in (-1, 0, 1)):
                    continue
                k = kinds(fx, fy)
                for i, j, s in ((0, 0, 3), (-1, 0, 2), (0, -1, 2), (1, 0, 1), (0, 1, 0)):
                    out[(fy + j) * W + fx + i] = bloom_slot(k, s)

    def panel_kinds(x, y):
        # each panel's hedge has two kinds of flower
        p = min(range(len(PANELS)), key=lambda i: abs(x - sum(panel_rect(PANELS[i])[::2]) / 2)
                + abs(y - sum(panel_rect(PANELS[i])[1::2]) / 2))
        return (p + rng.randrange(2)) % 4

    flowers({"hedge"}, 5, 0.8, panel_kinds)
    flowers({"bed"}, 5, 0.7, lambda x, y: rng.randrange(4))
    return out, kind


def critter_bands(kind):
    """Check the critter bands lie on open lawn; returns each band's targets
    as (x, y) lists, x relative to the band's screen offset."""
    rng = random.Random(7)
    bands = []
    for base, x0, y0, x1, y1 in BANDS:
        for y in range(y0 + 8, y1 + 16):     # the critter's body (a head may
            for x in range(base + x0 + 2, base + x1 + 14):     # overlap a hedge)
                assert kind[y][x] == "lawn", f"critter band at {x},{y} is {kind[y][x]}"
        bands.append([(rng.randint(x0, x1), rng.randint(y0, y1)) for _ in range(TARGETS)])
    return bands
