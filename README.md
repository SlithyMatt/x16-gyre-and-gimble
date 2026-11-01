# Gyre & Gimble

*Provisional title.* A rotating-rings puzzle game for the
[Commander X16](https://www.commanderx16.com/). Turn the rings until a tunnel
runs from the gap in the outer rim to the burrow at the center. See
[DESIGN.md](DESIGN.md).

## Requirements

- [cc65](https://cc65.github.io/) (`cl65` on your `PATH`)
- [x16-emulator](https://github.com/X16Community/x16-emulator) (`x16emu` on your `PATH`)
- Python 3, for the build-time tools

## Build & run

```sh
make        # builds build/GYRE.PRG, RINGS.BIN and CELLS.BIN
make run    # builds, then launches x16emu from build/
make clean
make joytest  # replays a scripted SNES pad through every level
```

The game loads `RINGS.BIN` and `CELLS.BIN` from the current device, so keep them next to `GYRE.PRG`.

## Controls

| Keyboard | SNES pad | Action |
| --- | --- | --- |
| Up / Down, W / S | D-pad up / down | Select the next ring out / in |
| Left / Right, A / D | D-pad left / right | Rotate the selected ring counter-clockwise / clockwise |
| U or Del | B | Undo |
| R | Select | Restart the level |
| Return | A or Start | Next level (after solving) |
| N / P | | Skip to the next / previous level (for testing) |
| Q | | Quit to BASIC |

Any SNES controller in ports 1–4 works, and a held D-pad direction repeats.

When the path connects, the tove walks home along it (Return or A skips
the walk).

Rings whose gear teeth mesh are linked by a **gimbal**: turning the
driving ring also turns the next one. When you select a ring, any ring it
will drag, teeth and all, is tinted blue (same direction) or mauve (opposite).

Each solve earns **stars** against the level's par (the fewest moves
possible): 3 at par, 2 within par plus half again (rounded down), otherwise 1.
Undo takes a move back off the count. Your best rating for each level this
session shows under the level number.

## Layout

- `src/`: 65C02 assembly (`main.asm` is the entry point)
- `tools/genrings.py`: renders the board backdrop and the anti-aliased,
  beveled cell pieces the game draws from
- `tools/shading.py`, `tools/genthemes.py`: the shading model, and the
  per-level color themes (`assets/themes.txt`) built from it
- `tools/level.py`: compiles the levels, checks that each is solvable and
  computes par. `suggest LEVEL N` finds starting rotations with par N, and
  `keys LEVEL` prints a shortest solution as keystrokes.
- `tools/gensprites.py`: compiles text sprite sheets (`assets/tove.txt`)
  into sprite frames and palette
- `tools/genchars.py`: compiles text glyphs (`assets/stars.txt`) into
  charset characters
- `assets/`: sprite and glyph art, as editable text grids
- `tools/joyscript.py`: generates the scripted pad for `make joytest`
- `levels/`: level sources (the format is documented in `level01.txt`)
- `build/`: build output (ignored by git)

## Reference

- X16 documentation: https://github.com/X16Community/x16-docs
