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
```

The game loads `RINGS.BIN` from the current device, so keep it next to `GYRE.PRG`.

## Controls

| Key | Action |
| --- | --- |
| Up / Down, W / S | Select the next ring out / in |
| Left / Right, A / D | Rotate the selected ring counter-clockwise / clockwise |
| U or Del | Undo |
| R | Restart the level |
| Q | Quit to BASIC |

## Layout

- `src/`: 65C02 assembly (`main.asm` is the entry point)
- `tools/genrings.py`: generates the board bitmap and its palette-region constants
- `tools/level.py`: compiles a level, checks that it's solvable and computes par.
  `--suggest N` finds starting rotations with par N, and `--keys` prints a
  solution as keystrokes.
- `levels/`: level sources (the format is documented in `level01.txt`)
- `build/`: build output (ignored by git)

## Reference

- X16 documentation: https://github.com/X16Community/x16-docs
