#!/usr/bin/env python3
"""Synthesize the PCM sound effects.

  turn      a ring grinds round, stone on stone, and settles with a thud
  follow    ... dragging a gimbal ring the same way: its gears click
            together in step, and two rings thud down almost as one
  counter   ... dragging one the opposite way: the gears ratchet tick-tock
            against each other, and the two rings thud down apart
  step1/2   the tove's little footsteps, left and right

VERA plays them as 8-bit signed mono at SOUND_RATE (its rate register:
48828 Hz * SOUND_RATE / 128). The game drops a whole sound into the 4 KB
FIFO at once, so each must fit in it. The thuds stay above 90 Hz, so they
carry on a TV speaker.

Outputs:
  SOUNDS.BIN   the samples, packed into 8 KB banks of high RAM (the game
               loads them after the cell pieces); no sound crosses a bank
  sounds.inc   SND_* ids, SOUND_RATE and each sound's bank (relative to
               the first), address and length
  DIR/*.wav    previews, for listening on the host

Usage: gensounds.py SOUNDS.BIN sounds.inc WAVDIR
"""
import math
import os
import random
import struct
import sys

SOUND_RATE = 32                 # VERA rate register: 12207 Hz
SR = 48828.125 * SOUND_RATE / 128
FIFO = 4095
BANK_SIZE = 8192
TAU = 2 * math.pi


def blank(seconds):
    return [0.0] * int(seconds * SR)


def mix(out, sig, at=0.0, gain=1.0):
    i0 = int(at * SR)
    for i, v in enumerate(sig):
        if 0 <= i0 + i < len(out):
            out[i0 + i] += v * gain


def lowpass(sig, cutoff):
    a = 1 - math.exp(-TAU * cutoff / SR)
    y, out = 0.0, []
    for v in sig:
        y += a * (v - y)
        out.append(y)
    return out


def highpass(sig, cutoff):
    low = lowpass(sig, cutoff)
    return [v - w for v, w in zip(sig, low)]


def noise(rng, seconds):
    return [rng.uniform(-1, 1) for _ in range(int(seconds * SR))]


def ping(freq, decay, seconds=None):
    """A struck resonance: a decaying sine."""
    n = int((seconds or decay * 6) * SR)
    return [math.sin(TAU * freq * i / SR) * math.exp(-i / SR / decay) for i in range(n)]


def thud(rng, f0, f1, decay):
    """A heavy stone settling: a falling low sine plus a dull knock."""
    n = int(decay * 6 * SR)
    out, ph = [], 0.0
    for i in range(n):
        t = i / SR
        ph += TAU * (f1 + (f0 - f1) * math.exp(-t / 0.03)) / SR
        out.append(math.sin(ph) * math.exp(-t / decay))
    knock = lowpass(noise(rng, 0.02), 700)
    mix(out, [v * math.exp(-i / SR / 0.005) * 3 for i, v in enumerate(knock)])
    return out


def grind(rng, seconds, gain):
    """Stone on stone: rough low noise, swelling in and dying away."""
    n = int(seconds * SR)
    body = lowpass(lowpass(highpass(noise(rng, seconds), 120), 600), 600)
    rough = lowpass(noise(rng, seconds), 35)
    peak = max(abs(v) for v in rough) or 1
    out = []
    for i in range(n):
        t = i / SR
        env = min(1, t / 0.015) * min(1, (seconds - t) / 0.05)
        out.append(body[i] * (0.6 + 0.4 * rough[i] / peak) * env * gain * 5)
    return out


def click(freq):
    """A gear tooth catching: a bright ping over a tick of noise."""
    out = ping(freq, 0.004)
    mix(out, ping(freq * 1.5, 0.002), gain=0.5)
    return out


def turn(rng, clicks=(), thuds=((0.16, 200, 95),)):
    out = blank(0.30)
    mix(out, grind(rng, 0.19, 0.25 if clicks else 0.3))
    for at, freq, gain in clicks:
        mix(out, click(freq), at, gain)
    for at, f0, f1 in thuds:
        mix(out, thud(rng, f0, f1, 0.035), at, 0.8)
    return out


def step(rng, freq, bright):
    out = blank(0.04)
    pat = lowpass(noise(rng, 0.04), bright)
    mix(out, [v * math.exp(-i / SR / 0.004) * 2 for i, v in enumerate(pat)])
    mix(out, ping(freq, 0.008, 0.04), gain=0.6)
    return out


def sounds():
    rng = random.Random(42)
    return {
        "turn": (turn(rng), 0.9),
        "follow": (turn(rng, clicks=[(0.02 + k * 0.026, 2400, 1.0) for k in range(6)],
                        thuds=((0.16, 200, 95), (0.172, 215, 100))), 0.9),
        "counter": (turn(rng, clicks=[(0.015 + k * 0.019, (1500, 2900)[k % 2] * (1 - 0.02 * k), 1.0)
                                      for k in range(8)],
                         thuds=((0.15, 185, 90), (0.20, 250, 120))), 0.9),
        "step1": (step(rng, 220, 1500), 0.45),
        "step2": (step(rng, 260, 1800), 0.45),
    }


def finish(sig, peak):
    """Normalize to peak, fade the tail to silence, and trim it."""
    top = max(abs(v) for v in sig) or 1
    sig = [v * peak / top for v in sig]
    fade = int(0.005 * SR)
    for i in range(fade):
        sig[-1 - i] *= i / fade
    while sig and abs(sig[-1]) < 1 / 127:
        sig.pop()
    return [max(-127, min(127, round(v * 127))) for v in sig] + [0]


def write_wav(path, samples):
    data = bytes((s + 128) & 0xFF for s in samples)     # WAV 8-bit is unsigned
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt ")
        f.write(struct.pack("<IHHIIHH", 16, 1, 1, round(SR), round(SR), 1, 8))
        f.write(b"data" + struct.pack("<I", len(data)) + data)


def main():
    out_bin, out_inc, wav_dir = sys.argv[1:4]
    os.makedirs(wav_dir, exist_ok=True)
    banks, table = [bytearray()], []
    for name, (sig, peak) in sounds().items():
        samples = finish(sig, peak)
        assert len(samples) <= FIFO, f"{name}: {len(samples)} samples won't fit the FIFO"
        data = bytes(s & 0xFF for s in samples)
        if len(banks[-1]) + len(data) > BANK_SIZE:
            banks.append(bytearray())
        table.append((name, len(banks) - 1, 0xA000 + len(banks[-1]), len(data)))
        banks[-1] += data
        write_wav(os.path.join(wav_dir, name + ".wav"), samples)
    with open(out_bin, "wb") as f:
        f.write(b"".join(bytes(b) + b"\0" * (BANK_SIZE - len(b)) for b in banks[:-1]) + bytes(banks[-1]))
    with open(out_inc, "w") as f:
        f.write("; generated by tools/gensounds.py — do not edit\n")
        f.write(f"SOUND_RATE = {SOUND_RATE}   ; {SR:.0f} Hz\nSOUND_BANKS = {len(banks)}\n")
        for i, (name, *_rest) in enumerate(table):
            f.write(f"SND_{name.upper()} = {i}\n")
        for key, fn in (("bank", lambda e: e[1]), ("lo", lambda e: e[2] & 0xFF),
                        ("hi", lambda e: e[2] >> 8), ("len_lo", lambda e: e[3] & 0xFF),
                        ("len_hi", lambda e: e[3] >> 8)):
            f.write(f"snd_{key}:\n    .byte " + ", ".join(f"${fn(e):02x}" for e in table) + "\n")
    print(f"{out_bin}: " + ", ".join(f"{n} {length}" for n, _, _, length in table))


if __name__ == "__main__":
    main()
