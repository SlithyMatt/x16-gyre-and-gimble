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
make        # builds build/GYRE.PRG and build/RINGS.BIN
make run    # builds, then launches x16emu from build/
make clean
make joytest  # replays a scripted SNES pad through every level
```

The game loads `RINGS.BIN` from the current device, so keep it next to `GYRE.PRG`.

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

Rings joined by brass gear teeth are linked by a **gimbal**: turning the
driving ring also turns the next one. When you select a ring, any ring it
will drag is tinted blue-grey (same direction) or mauve (opposite).

## Layout

- `src/`: 65C02 assembly (`main.asm` is the entry point)
- `tools/genrings.py`: generates the board bitmap and its palette-region constants
- `tools/level.py`: compiles the levels, checks that each is solvable and
  computes par. `suggest LEVEL N` finds starting rotations with par N, and
  `keys LEVEL` prints a shortest solution as keystrokes.
- `tools/joyscript.py`: generates the scripted pad for `make joytest`
- `levels/`: level sources (the format is documented in `level01.txt`)
- `build/`: build output (ignored by git)

## Reference

- X16 documentation: https://github.com/X16Community/x16-docs
