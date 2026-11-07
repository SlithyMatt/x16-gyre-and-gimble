#!/usr/bin/env python3
"""Compile level text files into ca65 data, verifying each is solvable.

Usage:
  level.py build OUT.inc LEVEL.txt...  compile levels in order (fails if any is unsolvable)
  level.py suggest LEVEL.txt PAR       list start offsets whose par is PAR
  level.py keys LEVEL.txt              print a shortest solution as WASD keys

Connectivity here must match `flood` in src/main.asm, and gimbal handling
must match `turn_sel`.

Level file format (# starts a comment):

  ring3: oc c  i  .  .  .  oi .  .  c  oc i
  ring2: ...                  rings outer (ring3) to inner (ring0), 12 cells
  ring1: ...                  each, position 0 at the top, going clockwise
  ring0: ...
  gimbal: 3 > 2 +             optional, repeatable: turning DRIVER (3) also
                              turns its neighbor FOLLOWER (2) the same (+)
                              or opposite (-) way; not the other way round
  start: 3 8 8 3              starting rotation of each ring, outer to inner,
                              in clockwise steps
  theme: noon                 optional color theme (and music) from
                              assets/themes.txt (default: the first)

Cells: . stone, - tunnel with no openings, or a tunnel opening any of
i (inward), o (outward) and c (clockwise), e.g. "oc". The entry gap is
above ring3 position 0; the burrow is inside ring0.
"""
import random
import sys
from collections import deque

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from shading import parse_themes  # noqa: E402

THEMES = list(parse_themes(__file__.rsplit("/", 2)[0] + "/assets/themes.txt"))

RINGS, CELLS = 4, 12
IN, OUT, CW, T = 0x01, 0x02, 0x04, 0x80
BITS = {"i": IN, "o": OUT, "c": CW, "-": 0}

# Level record layout (must match the LV_* uses in src/main.asm)
LV_CELLS, LV_START, LV_SAME, LV_OPP, LV_TEETH, LV_PAR, LV_THEME = 0, 48, 52, 56, 60, 63, 64
LEVEL_SIZE = 65


class Level:
    def __init__(self, path):
        self.path = path
        rings, self.start, self.links, self.theme = {}, None, [], 0
        for line in open(path):
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            key, _, val = line.partition(":")
            toks = val.split()
            if key.startswith("ring"):
                r = int(key[4:])
                if len(toks) != CELLS:
                    self.fail(f"{key} needs {CELLS} cells")
                rings[r] = [self.cell(t) for t in toks]
            elif key == "start":
                self.start = [int(t) % CELLS for t in reversed(toks)]  # listed outer to inner
            elif key == "theme":
                if len(toks) != 1 or toks[0] not in THEMES:
                    self.fail(f"unknown theme {val.strip()} (themes: {' '.join(THEMES)})")
                self.theme = THEMES.index(toks[0])
            elif key == "gimbal":
                # gimbal: DRIVER > FOLLOWER +|-
                if len(toks) != 4 or toks[1] != ">" or toks[3] not in "+-":
                    self.fail(f"bad gimbal line: {val.strip()}")
                a, b = int(toks[0]), int(toks[2])
                if abs(a - b) != 1:
                    self.fail("gimbals must link neighboring rings")
                self.links.append((a, b, 1 if toks[3] == "+" else -1))
            else:
                self.fail(f"unknown key {key}")
        if self.start is None:
            self.fail("missing start:")
        self.cells = [rings[r] for r in range(RINGS)]
        for r in range(RINGS):
            for p in range(CELLS):
                if self.cells[r][p] & CW and not self.cells[r][(p + 1) % CELLS] & T:
                    self.fail(f"ring{r} cell {p} opens clockwise into stone")
        self.same, self.opp = self.masks()
        self.teeth = [int(any({a, b} == {k - 1, k} for a, b, _ in self.links))
                      for k in range(1, RINGS)]

    def fail(self, msg):
        sys.exit(f"{self.path}: {msg}")

    def cell(self, tok):
        if tok == ".":
            return 0
        v = T
        for ch in tok:
            if ch not in BITS:
                self.fail(f"bad cell {tok}")
            v |= BITS[ch]
        return v

    def masks(self):
        """For each driver ring, bitmasks of the rings that turn with it."""
        same, opp = [], []
        for r in range(RINGS):
            sign, todo = {r: 1}, [r]
            while todo:
                a = todo.pop()
                for x, y, s in self.links:
                    if x != a:
                        continue
                    v = sign[a] * s
                    if y in sign:
                        if sign[y] != v:
                            self.fail(f"gimbals conflict when turning ring {r}")
                    else:
                        sign[y] = v
                        todo.append(y)
            same.append(sum(1 << i for i, v in sign.items() if v > 0))
            opp.append(sum(1 << i for i, v in sign.items() if v < 0))
        return same, opp

    def turn(self, off, r, d):
        n = list(off)
        for i in range(RINGS):
            if self.same[r] >> i & 1:
                n[i] = (n[i] + d) % CELLS
            if self.opp[r] >> i & 1:
                n[i] = (n[i] - d) % CELLS
        return tuple(n)

    def solved(self, off):
        cells = self.cells

        def scr(r, p):
            return cells[r][(p - off[r]) % CELLS]

        if not scr(RINGS - 1, 0) & OUT:
            return False
        seen, todo = {(RINGS - 1, 0)}, [(RINGS - 1, 0)]
        while todo:
            r, p = todo.pop()
            c = scr(r, p)
            if r == 0 and c & IN:
                return True
            nbrs = []
            if c & CW:
                nbrs.append((r, (p + 1) % CELLS))
            if scr(r, (p - 1) % CELLS) & CW:
                nbrs.append((r, (p - 1) % CELLS))
            if r > 0 and c & IN and scr(r - 1, p) & OUT:
                nbrs.append((r - 1, p))
            if r < RINGS - 1 and c & OUT and scr(r + 1, p) & IN:
                nbrs.append((r + 1, p))
            for n in nbrs:
                if n not in seen:
                    seen.add(n)
                    todo.append(n)
        return False

    def solve(self, start=None):
        """Shortest list of (ring, dir) moves to a solved board."""
        start = tuple(self.start if start is None else start)
        prev = {start: None}
        q = deque([start])
        while q:
            s = q.popleft()
            if self.solved(s):
                moves = []
                while prev[s]:
                    s, move = prev[s]
                    moves.append(move)
                return moves[::-1]
            for r in range(RINGS):
                for d in (1, -1):
                    n = self.turn(s, r, d)
                    if n not in prev:
                        prev[n] = (s, (r, d))
                        q.append(n)
        return None

    def record(self):
        moves = self.solve()
        if moves is None:
            self.fail("unsolvable")
        if not moves:
            self.fail("already solved at start")
        par = len(moves)
        data = [c for ring in self.cells for c in ring] + self.start + self.same + self.opp + self.teeth + [par, self.theme]
        assert len(data) == LEVEL_SIZE
        return data, par


def keys(moves):
    """Keystrokes (WASD) that play moves, starting with the outer ring selected."""
    out, sel = [], RINGS - 1
    for r, d in moves:
        out.append(("w" if r > sel else "s") * abs(r - sel))
        out.append("d" if d > 0 else "a")
        sel = r
    return "".join(out)


def build(out, paths):
    with open(out, "w") as f:
        f.write("; generated by tools/level.py — do not edit\n")
        for name in ("LV_CELLS", "LV_START", "LV_SAME", "LV_OPP", "LV_TEETH", "LV_PAR", "LV_THEME",
                     "LEVEL_SIZE"):
            f.write(f"{name} = {globals()[name]}\n")
        f.write(f"NLEVELS = {len(paths)}\n\n")
        f.write("level_lo:\n    .byte " + ", ".join(f"<level{i}" for i in range(len(paths))) + "\n")
        f.write("level_hi:\n    .byte " + ", ".join(f">level{i}" for i in range(len(paths))) + "\n")
        for i, path in enumerate(paths):
            lv = Level(path)
            data, par = lv.record()
            f.write(f"\nlevel{i}:  ; {path}, par {par}\n")
            for k in range(0, LEVEL_SIZE, 12):
                f.write("    .byte " + ", ".join(f"${b:02x}" for b in data[k:k + 12]) + "\n")
            print(f"{path}: par {par}")


def main():
    cmd = sys.argv[1]
    if cmd == "build":
        build(sys.argv[2], sys.argv[3:])
    elif cmd == "keys":
        print(keys(Level(sys.argv[2]).solve()))
    elif cmd == "suggest":
        lv, want = Level(sys.argv[2]), int(sys.argv[3])
        rng = random.Random(1)
        found = 0
        for _ in range(5000):
            s = [rng.randrange(CELLS) for _ in range(RINGS)]
            moves = lv.solve(s)
            if moves is not None and len(moves) == want:
                print("start:", " ".join(map(str, reversed(s))))
                found += 1
                if found == 5:
                    break
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
