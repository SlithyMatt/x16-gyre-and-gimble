#!/usr/bin/env python3
"""Compile the background music (assets/music/*.txt) for the game's sequencer.

Each theme in assets/themes.txt names its tune ("music NAME"). A tune is a
set of voices on one clock: PSG voices make the whole arrangement, and YM2151
voices add to it when the chip is present. Every voice loops on its own, and
they all have the same length, so they stay in step.

Score format (one directive or line of notes per line, # comments):

  title TEXT
  unit FRAMES       frames (1/60 s) per note-length unit
  bar UNITS         units per bar; every bar is checked
  once              play once and stop, rather than loop
  key KEY           C G D A F Am Em Bm Dm: the sharps or flats for the
                    voices that follow (an accidental applies to its note only)
  voice NAME CHIP INSTRUMENT [width N] [transpose N] [copy VOICE] [volume PCT]
                    CHIP is psg or ym; a chord voice of width N takes N
                    channels; copy takes another voice's notes; volume
                    scales the instrument (percent) for this voice

Notes, as in ABC: C D E F G A B from middle C up, c-b an octave higher,
each , an octave down and ' an octave up; ^ sharp, _ flat, = natural; then
a length in units (default 1). z is a rest. [CEG]2 is a chord (one note
per channel of a width-3 voice). | checks a bar. { ... }N repeats N times.

Output: music.inc, with the PSG and YM note tables, the instruments, each
tune's channels and note streams, theme_tune (a tune per theme), and
TUNE_NAME for each extra tune named on the command line.

A stream is (note, frames) pairs: note 0 rests, bit 7 set continues the
previous note without striking it again, $FF loops back to the start, and
$FE stops (the channel stays silent).
Each note ends with its instrument's gap of silence, so repeats articulate.

Usage: genmusic.py THEMES.txt MUSIC_DIR OUT.inc [EXTRA_TUNE...]
"""
import math
import os
import re
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import shading  # noqa: E402

PSG_VOICES = 8          # PSG voices 0-7 (8-15 left free)
YM_CHANNELS = 8
MAX_CHANNELS = 12       # sequencer channels per tune
TIE = 0x80
LOOP = 0xFF
STOP = 0xFE

# PSG instruments: waveform (pulse, saw, triangle, noise), pulse width
# (0-63, 63 = square), volume (0-63) at the strike, decay per frame, the
# volume it decays to, and frames of silence at the end of each note
PSG_WAVES = {"pulse": 0, "saw": 1, "triangle": 2, "noise": 3}
PSG_INSTRUMENTS = {
    #           wave        width vol  decay sustain gap
    "lead":     ("pulse",    40,  42,  0.25,  32,    3),
    "clarinet": ("pulse",    63,  38,  0.10,  32,    2),
    "alberti":  ("triangle",  0,  44,  1.00,  20,    2),
    "arp":      ("triangle",  0,  40,  0.75,  12,    2),
    "pah":      ("pulse",    63,  20,  1.50,   0,    4),
    "brass":    ("saw",       0,  40,  0.20,  30,    1),
    "bass":     ("triangle",  0,  52,  0.50,  36,    3),
}

# YM2151 patches, in the ROM's 26-byte patch order: RL/FB/CONNECT, PMS/AMS,
# then DT1/MUL, TL, KS/AR, AMS-EN/D1R, DT2/D2R, D1L/RR for operators M1, M2,
# C1, C2. All use algorithm 4: two modulator -> carrier pairs.
def ym_patch(fb, ops, gap):
    """ops: M1, M2, C1, C2 as (dt1, mul, tl, ar, d1r, d2r, d1l, rr)."""
    data = [0xC0 | fb << 3 | 4, 0]
    for field in range(6):
        for dt1, mul, tl, ar, d1r, d2r, d1l, rr in ops:
            data.append((dt1 << 4 | mul, tl, ar, d1r, d2r, d1l << 4 | rr)[field])
    return data, gap


YM_INSTRUMENTS = {
    # Soft strings: a slow swell, two pairs detuned against each other
    "pad": ym_patch(2, [(0, 1, 34, 14, 0, 0, 0, 6), (3, 1, 36, 14, 0, 0, 0, 6),
                        (0, 1, 30, 12, 1, 0, 1, 6), (3, 1, 30, 12, 1, 0, 1, 6)], 2),
    # A music-box bell, an octave up (the carriers' MUL 2), dying away
    "bell": ym_patch(0, [(0, 7, 56, 31, 10, 4, 15, 6), (0, 2, 66, 31, 6, 2, 15, 6),
                         (0, 2, 22, 31, 7, 3, 15, 6), (0, 2, 30, 31, 5, 3, 15, 6)], 2),
    # A breathy flute at pitch
    "flute": ym_patch(1, [(0, 1, 46, 20, 0, 0, 0, 7), (0, 2, 62, 20, 0, 0, 0, 7),
                          (0, 1, 26, 18, 1, 0, 1, 7), (0, 2, 44, 18, 1, 0, 1, 7)], 2),
    # A round plucked bass (one pair; the other is silent)
    "bass": ym_patch(4, [(0, 1, 30, 31, 6, 2, 3, 8), (0, 1, 127, 31, 0, 0, 0, 15),
                         (0, 1, 20, 31, 3, 1, 4, 8), (0, 1, 127, 31, 0, 0, 0, 15)], 3),
}

KEYS = {
    "C": {}, "Am": {},
    "G": {"F": 1}, "Em": {"F": 1},
    "D": {"F": 1, "C": 1}, "Bm": {"F": 1, "C": 1},
    "A": {"F": 1, "C": 1, "G": 1},
    "F": {"B": -1}, "Dm": {"B": -1},
}
LETTER = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
NOTE_RE = re.compile(r"([\^_=]?)([A-Ga-g])([,']*)")
TOKEN_RE = re.compile(r"\{|\}(\d*)|\||\[([^\]]+)\](\d*)|([\^_=]?[A-Ga-gz][,']*)(\d*)|(\S)")


def pitch(acc, letter, marks, key):
    """MIDI note: C (middle C) is 60."""
    n = 60 + LETTER[letter.upper()] + (12 if letter.islower() else 0)
    n += 12 * marks.count("'") - 12 * marks.count(",")
    if acc:
        n += {"^": 1, "_": -1, "=": 0}[acc]
    else:
        n += KEYS[key].get(letter.upper(), 0)
    return n


CARRIER_TL = (8, 9)     # algorithm 4: C1 and C2's TL bytes in a patch


def scaled(chip, instr, pct):
    """The name of instrument instr at pct volume, adding it if it's new."""
    if pct == 100:
        return instr
    name = f"{instr}@{pct}"
    if chip == "psg" and name not in PSG_INSTRUMENTS:
        wave, width, vol, decay, sustain, gap = PSG_INSTRUMENTS[instr]
        PSG_INSTRUMENTS[name] = (wave, width, round(vol * pct / 100), decay * pct / 100,
                                 round(sustain * pct / 100), gap)
    elif chip == "ym" and name not in YM_INSTRUMENTS:
        data, gap = YM_INSTRUMENTS[instr]
        data = list(data)
        att = round(-20 * math.log10(pct / 100) / 0.75)     # TL steps are 0.75 dB
        for k in CARRIER_TL:
            data[k] = min(127, data[k] + att)
        YM_INSTRUMENTS[name] = (data, gap)
    return name


class Voice:
    def __init__(self, name, chip, instr, width, transpose):
        self.name, self.chip, self.instr = name, chip, instr
        self.width, self.transpose = width, transpose
        self.events = []        # (notes tuple or None, units), or "|"
        self.text = []          # lines of notes, parsed at the voice's end


def parse(path):
    tune = {"title": "", "unit": None, "bar": None, "voices": {}, "once": False}
    key = "C"
    voice = None
    where = path

    def fail(msg):
        sys.exit(f"{where}: {msg}")

    def notes(text, key):
        """Events from a voice's notes, with { }N repeats."""
        stack = [[]]
        for m in TOKEN_RE.finditer(text):
            if m.group(0) == "{":
                stack.append([])
            elif m.group(0).startswith("}"):
                if len(stack) < 2:
                    fail("unmatched }")
                body = stack.pop()
                stack[-1] += body * int(m.group(1) or 2)
            elif m.group(0) == "|":
                stack[-1].append("|")
            elif m.group(2):
                ns = tuple(pitch(*n.groups(), key) for n in NOTE_RE.finditer(m.group(2)))
                stack[-1].append((ns, int(m.group(3) or 1)))
            elif m.group(4):
                length = int(m.group(5) or 1)
                if m.group(4) == "z":
                    stack[-1].append((None, length))
                else:
                    n = NOTE_RE.fullmatch(m.group(4))
                    stack[-1].append(((pitch(*n.groups(), key),), length))
            else:
                fail(f"bad token {m.group(0)!r}")
        if len(stack) != 1:
            fail("unmatched {")
        return stack[0]

    def finish(v):
        if v and v.text:
            for ev in notes(" ".join(v.text), v.key):
                if ev != "|" and ev[0] and len(ev[0]) != v.width:
                    fail(f"voice {v.name} has width {v.width}")
                v.events.append(ev)

    for lineno, raw in enumerate(open(path), 1):
        where = f"{path}:{lineno}"
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        word, _, rest = line.partition(" ")
        if word == "title":
            tune["title"] = rest.strip()
        elif word == "once":
            tune["once"] = True
        elif word in ("unit", "bar"):
            tune[word] = int(rest)
        elif word == "key":
            key = rest.strip()
            if key not in KEYS:
                fail(f"unknown key {key}")
        elif word == "voice":
            toks = rest.split()
            name, chip, instr = toks[:3]
            opts = dict(zip(toks[3::2], toks[4::2]))
            table = PSG_INSTRUMENTS if chip == "psg" else YM_INSTRUMENTS if chip == "ym" else None
            if table is None or instr not in table:
                fail(f"unknown {chip} instrument {instr}")
            finish(voice)
            instr = scaled(chip, instr, int(opts.get("volume", 100)))
            voice = Voice(name, chip, instr, int(opts.get("width", 1)), int(opts.get("transpose", 0)))
            voice.key = key
            if "copy" in opts:
                src = tune["voices"].get(opts["copy"])
                if not src or src.width != voice.width:
                    fail(f"can't copy voice {opts['copy']}")
                voice.events = list(src.events)
            tune["voices"][name] = voice
        elif voice is None:
            fail("notes before any voice")
        else:
            voice.text.append(line)
    where = path
    finish(voice)
    if not tune["unit"] or not tune["bar"]:
        sys.exit(f"{path}: needs unit and bar")

    # Check every bar
    for v in tune["voices"].values():
        units, bar = 0, 1
        for ev in v.events:
            if ev == "|":
                if units != tune["bar"]:
                    sys.exit(f"{path}: voice {v.name} bar {bar} has {units} units, not {tune['bar']}")
                units, bar = 0, bar + 1
            else:
                units += ev[1]
        if units:
            sys.exit(f"{path}: voice {v.name} ends mid-bar")
        v.events = [ev for ev in v.events if ev != "|"]
    return tune


def streams(tune):
    """[(chip, instrument, [(note, frames)])] per channel."""
    out = []
    for v in tune["voices"].values():
        gap = PSG_INSTRUMENTS[v.instr][5] if v.chip == "psg" else YM_INSTRUMENTS[v.instr][1]
        for ch in range(v.width):
            evs = []
            for ns, units in v.events:
                frames = units * tune["unit"]
                if ns is None:
                    evs.append((0, frames))
                    continue
                n = ns[ch] + v.transpose
                assert 12 <= n < 120, f"{v.name}: note {n} out of range"
                evs += [(n, frames - gap), (0, gap)] if gap else [(n, frames)]
            merged = []         # join rests, then split anything over 255 frames
            for n, f in evs:
                if n == 0 and merged and merged[-1][0] == 0:
                    merged[-1] = (0, merged[-1][1] + f)
                elif f > 0:
                    merged.append((n, f))
            split = []
            for n, f in merged:
                first = True
                while f > 0:
                    chunk = min(f, 255)
                    split.append((n if first or n == 0 else n | TIE, chunk))
                    f -= chunk
                    first = False
            out.append((v.chip, v.instr, split))
    totals = {sum(f for _, f in s) for _, _, s in out}
    if len(totals) != 1:
        raise SystemExit(f"{tune['title']}: voices differ in length ({sorted(totals)} frames)")
    return out


def label(name):
    """An assembler label for an instrument name (bell@50 -> bell_50)."""
    return name.replace("@", "_")


def main():
    themes_path, music_dir, out = sys.argv[1:4]
    extras = sys.argv[4:]
    themes = shading.parse_themes(themes_path)
    names = []
    for t in themes.values():
        if t["music"] not in names:
            names.append(t["music"])
    names += [n for n in extras if n not in names]
    tunes = {}
    for name in names:          # first, as voices may add scaled instruments
        tune = parse(os.path.join(music_dir, name + ".txt"))
        tunes[name] = (tune, streams(tune))
    psg_names, ym_names = list(PSG_INSTRUMENTS), list(YM_INSTRUMENTS)

    with open(out, "w") as f:
        f.write(f"; generated by tools/genmusic.py from {music_dir} — do not edit\n")
        f.write(f"NTUNES = {len(names)}\nMUSIC_CHANNELS = {MAX_CHANNELS}\n")
        f.write(f"MUSIC_PSG_VOICES = {PSG_VOICES}\nMUSIC_TIE = ${TIE:02x}\n"
                f"MUSIC_LOOP = ${LOOP:02x}\nMUSIC_STOP = ${STOP:02x}\n")
        for n in extras:
            f.write(f"TUNE_{n.upper()} = {names.index(n)}\n")
        f.write("theme_tune:  ; " + ", ".join(themes) + "\n    .byte "
                + ", ".join(str(names.index(t["music"])) for t in themes.values()) + "\n")

        # Note tables, by MIDI note
        psg = [round(440 * 2 ** ((n - 69) / 12) * 2 ** 17 / 48828.125) for n in range(128)]
        psg = [min(v, 0xFFFF) for v in psg]
        codes = [14, 0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13]       # C is the octave below's top
        kc = []
        for n in range(128):
            octave = n // 12 - 1 - (1 if n % 12 == 0 else 0)
            kc.append(max(0, min(7, octave)) << 4 | codes[n % 12])
        for name, vals in (("psg_freq_lo", [v & 0xFF for v in psg]), ("psg_freq_hi", [v >> 8 for v in psg]),
                           ("ym_kc", kc)):
            f.write(f"{name}:\n")
            for k in range(0, 128, 16):
                f.write("    .byte " + ", ".join(f"${v:02x}" for v in vals[k:k + 16]) + "\n")

        # Instruments
        f.write("; PSG instruments: " + ", ".join(psg_names) + "\n")
        cols = {"psg_wave": [], "psg_peak": [], "psg_decay_lo": [], "psg_decay_hi": [], "psg_sustain": []}
        for name in psg_names:
            wave, width, vol, decay, sustain, _ = PSG_INSTRUMENTS[name]
            d = round(decay * 256)
            cols["psg_wave"].append(PSG_WAVES[wave] << 6 | width)
            cols["psg_peak"].append(vol)
            cols["psg_decay_lo"].append(d & 0xFF)
            cols["psg_decay_hi"].append(d >> 8)
            cols["psg_sustain"].append(sustain)
        for name, vals in cols.items():
            f.write(f"{name}:\n    .byte " + ", ".join(f"${v:02x}" for v in vals) + "\n")
        f.write("; YM instruments: " + ", ".join(ym_names) + "\n")
        f.write("ym_patch_lo:\n    .byte " + ", ".join(f"<ym_patch_{label(n)}" for n in ym_names) + "\n")
        f.write("ym_patch_hi:\n    .byte " + ", ".join(f">ym_patch_{label(n)}" for n in ym_names) + "\n")
        for name in ym_names:
            f.write(f"ym_patch_{label(name)}:\n    .byte " + ", ".join(f"${v:02x}" for v in YM_INSTRUMENTS[name][0]) + "\n")

        # Tunes
        f.write("tune_lo:\n    .byte " + ", ".join(f"<tune_{n}" for n in names) + "\n")
        f.write("tune_hi:\n    .byte " + ", ".join(f">tune_{n}" for n in names) + "\n")
        report = []
        for name in names:
            tune, chans = tunes[name]
            if len(chans) > MAX_CHANNELS:
                sys.exit(f"{name}: {len(chans)} channels, at most {MAX_CHANNELS}")
            npsg = sum(c == "psg" for c, _, _ in chans)
            nym = len(chans) - npsg
            if npsg > PSG_VOICES or nym > YM_CHANNELS:
                sys.exit(f"{name}: too many PSG voices or YM channels")
            f.write(f"\n; {tune['title']}\n; channel: chip (bit 7 = YM) | voice, instrument, stream\n")
            f.write(f"tune_{name}:\n    .byte {len(chans)}\n")
            nums = {"psg": 0, "ym": 0}
            for i, (chip, instr, _) in enumerate(chans):
                hw = nums[chip]
                nums[chip] += 1
                inst = (psg_names if chip == "psg" else ym_names).index(instr)
                f.write(f"    .byte ${(0x80 if chip == 'ym' else 0) | hw:02x}, {inst}\n"
                        f"    .word tune_{name}_{i}  ; {chip} {instr}\n")
            size = 0
            for i, (_, _, evs) in enumerate(chans):
                f.write(f"tune_{name}_{i}:\n")
                flat = [b for ev in evs for b in ev] + [STOP if tune["once"] else LOOP]
                size += len(flat)
                for k in range(0, len(flat), 24):
                    f.write("    .byte " + ", ".join(f"${b:02x}" for b in flat[k:k + 24]) + "\n")
            secs = sum(fr for _, fr in chans[0][2]) / 60
            report.append(f"{name} {secs:.0f}s {npsg} psg + {nym} ym, {size} bytes")
    print("music: " + "; ".join(report))


if __name__ == "__main__":
    main()
