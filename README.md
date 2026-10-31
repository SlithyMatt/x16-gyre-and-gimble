# Gyre & Gimble

*Provisional title.* A new game for the [Commander X16](https://www.commanderx16.com/).

## Requirements

- [cc65](https://cc65.github.io/) (`cl65` on your `PATH`)
- [x16-emulator](https://github.com/X16Community/x16-emulator) (`x16emu` on your `PATH`)

## Build & run

```sh
make        # builds build/GYRE.PRG
make run    # builds and launches it in x16emu
make clean
```

## Layout

- `src/` — 65C02 assembly sources (`main.asm` is the entry point)
- `assets/` — graphics, sound and other data
- `build/` — build output (ignored by git)

## Reference

- X16 documentation: https://github.com/X16Community/x16-docs
