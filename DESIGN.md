# Gyre & Gimble — Design (draft)

*Provisional title. Everything here is open to change.*

## Premise

A tove has to get home to its burrow at the center of the wabe. The wabe is
a set of concentric stone rings, and the tunnels through them don't line up.
The player **gyres** (rotates) the rings until there's an unbroken path from
the gap in the outer rim to the burrow. The tove then **gimbles** (bores)
its way home along that path.

## Core mechanic

- **Board:** 4 concentric rings around a central burrow. Each ring has
  12 cells (30° per step).
- **Cells:** each cell is either solid or tunnel. A tunnel cell can open
  - *inward* and/or *outward* (radial links to the next ring in), and
  - *clockwise* (an arc link to its neighbor in the same ring; that same
    opening is the neighbor's counter-clockwise side).

  Two cells in neighboring rings connect only when they line up after
  rotation and both have the facing side open.
- **Entry and goal:** the outer rim has one fixed entry gap. The burrow
  counts as open on every side.
- **A move:** pick a ring and rotate it one step either way.
- **Win:** a connected path runs from the entry to the burrow. The tove
  then walks it as a short animation.
- **Scoring:** a move counter with a par for each level, giving 1–3 stars.

## Planned twists (introduced level by level)

1. **Gimbals** *(implemented, levels 2–3)*: neighboring rings geared together. Turning the
   driver also turns the follower, the same way (`+`) or the opposite way
   (`-`), but turning the follower alone leaves the driver still. Gimbals
   can chain (3→2→1). The gap shows brass gear teeth, and selecting a ring
   tints the rings it will drag. This is where the "Gimble" half of the
   name pays off. *Later:* gear ratios other than 1:1.
2. **Locked rings:** these can't be turned until the tove passes a key cell.
3. **Borogoves:** hazards sitting in cells that block a path until they're
   rotated out of the way.
4. **Mome raths:** optional collectibles along the path, for bonus stars.

## Controls

| Input | Action |
| --- | --- |
| D-pad up / down | Select ring |
| D-pad left / right | Rotate the selected ring counter-clockwise / clockwise (held: repeats) |
| B | Undo |
| Select | Restart level |
| A / Start | Next level after solving (later: send the tove) |

The keyboard mirrors all of these (see README). SNES pads 1–4 are read
with the KERNAL `joystick_get` call once per frame and translated into the
same key codes as the keyboard, so `handle_key` is the only input handler.
Pad 0 (the keyboard joystick) is skipped so cursor keys don't count twice.
*Later:* a Start menu (choose level, quit).

## Rendering approach

- **Layer 0:** a 320×240 8bpp bitmap of the ring geometry, generated at
  build time by a Python tool and loaded straight into VRAM.
- **Palette trick:** every pixel's color index identifies a fixed *screen
  region*: one region per on-screen cell body, inner half-gate, outer
  half-gate and arc gate (4 rings × 12 cells × 4 regions = 192 entries).
  To show the board, the game writes each region's palette entry as tunnel
  or stone, according to which cell is currently rotated into that position.
  A rotation only rewrites the palette (≤384 bytes), never the bitmap, so
  it's effectively free.
- **Layer 1:** text and tiles for the HUD (level, moves, par, stars).
- **Sprites:** the tove, the ring-selection cursor and hazards. Their
  positions come from a precomputed table of cell centers.
- **Later:** smoother rotation by drawing 24 screen positions per ring
  (cells 2 positions wide), which allows a half-step frame.

## Display: playable on a composite TV

The game has to read well on an NTSC composite CRT, not just VGA.

- **Title-safe area:** all text and gameplay graphics stay inside a 10%
  margin, which is x 32–287 and y 24–215 (text columns 4–35, rows 3–26).
  The board's outer edge is at radius 88, and the HUD uses the four 8×4
  character corners that leaves free. Only background may go outside it.
- **Luma contrast:** composite blurs chroma, so every pair of colors that
  must be told apart (open vs. closed gate, stone vs. selected stone,
  reachable vs. unreachable tunnel) differs in brightness, not only hue.
  The palette in `src/main.asm` lists each color's luma.
- **No fine detail:** lines and gates are at least 3 px wide at 320×240,
  and text uses the standard (not thin) 8×8 font.
- **240p:** `screen_mode` `$80` is 2× scaled, so the KERNAL enables VERA's
  240p progressive mode on NTSC/RGB output: no interlace flicker.

## Data

- Level files are built from a simple text format into packed binary:
  4 rings × 12 cells × 1 byte (direction bits), plus the starting rotation,
  gimbal links and par.
- A Python solver (breadth-first search over ring rotations) checks that
  every level can be solved and computes its par.

## Build

- `tools/`: Python generators for the ring bitmap, cell-center table and
  levels, plus the solver.
- `src/`: ca65 assembly. `make` runs the tools and then `cl65`.
