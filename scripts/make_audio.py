#!/usr/bin/env python3
"""Make Boardread's music beds and end sting from nothing but arithmetic.

Every sample is computed here: sine and triangle oscillators, a one-pole filter, exponential envelopes and white
noise from a seeded generator. No sample, loop, preset or recording from anyone else goes in, so Boardread owns
the result outright and no Content ID or rights system can match it to a third-party work.

    python3 scripts/make_audio.py          writes aidaily/audio/bed-1.m4a .. bed-3.m4a and sting.m4a

Three beds, each 64 s, a calm news pulse at 96, 100 and 106 BPM with different chords and arpeggios, so two
videos in a row do not sound the same. Loudness -16 LUFS integrated, true peak -2 dBTP (ffmpeg loudnorm),
AAC 48 kHz stereo at 128 kbps: Instagram and Threads accept AAC up to 48 kHz, one or two channels, 128 kbps;
YouTube asks for AAC-LC stereo at 48 or 96 kHz. Standard library only; ffmpeg does the loudness and the AAC.
"""
import array
import math
import random
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

SR = 48000
OUT = Path(__file__).resolve().parent.parent / "aidaily" / "audio"
A4 = 440.0


def hz(note):
    """MIDI note number to frequency."""
    return A4 * 2 ** ((note - 69) / 12)


def tri(phase):
    p = phase % 1.0
    return 4 * p - 1 if p < 0.5 else 3 - 4 * p


class Lowpass:
    def __init__(self, cutoff):
        self.a = 1 - math.exp(-2 * math.pi * cutoff / SR)
        self.y = 0.0

    def __call__(self, x):
        self.y += self.a * (x - self.y)
        return self.y


# chords as MIDI notes; each bed walks its progression one chord per bar (4 beats)
BEDS = [
    {"bpm": 100, "seed": 1, "chords": [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]],   # Am F C G
     "arp": [0, 1, 2, 1, 0, 2, 1, 2]},
    {"bpm": 96, "seed": 2, "chords": [[50, 53, 57], [46, 50, 53], [53, 57, 60], [48, 52, 55]],    # Dm Bb F C
     "arp": [0, 2, 1, 2, 0, 1, 2, 1]},
    {"bpm": 106, "seed": 3, "chords": [[52, 55, 59], [48, 52, 55], [55, 59, 62], [50, 54, 57]],   # Em C G D
     "arp": [2, 1, 0, 1, 2, 0, 1, 0]},
]


def bed(spec, seconds=64.0):
    rnd = random.Random(spec["seed"])
    beat = 60.0 / spec["bpm"]
    n = int(seconds * SR)
    left, right = array.array("f", bytes(4 * n)), array.array("f", bytes(4 * n))
    pad_lp_l, pad_lp_r, hat_hp = Lowpass(900), Lowpass(900), Lowpass(6000)
    for i in range(n):
        t = i / SR
        b = t / beat                      # position in beats
        bar = int(b // 4)
        chord = spec["chords"][bar % len(spec["chords"])]
        # pad: two detuned triangles per chord note, one each side, softly filtered; it breathes once a bar
        swell = 0.75 + 0.25 * math.sin(2 * math.pi * (b % 4) / 4 - math.pi / 2)
        pl = pr = 0.0
        for note in chord:
            f = hz(note)
            pl += tri(f * 0.998 * t)
            pr += tri(f * 1.002 * t)
        pl, pr = pad_lp_l(pl) * 0.055 * swell, pad_lp_r(pr) * 0.055 * swell
        # arpeggio: eighth notes an octave up, a plucked sine with a fast decay
        step = int(b * 2)
        since = (b * 2 - step) * beat / 2
        note = chord[spec["arp"][step % len(spec["arp"])]] + 12
        pluck = math.sin(2 * math.pi * hz(note) * since) * math.exp(-since * 9) * 0.07
        # bass: the root two octaves down on beats 1 and 3
        half = int(b // 2)
        sb = (b - half * 2) * beat
        bass = math.sin(2 * math.pi * hz(chord[0] - 24) * sb) * math.exp(-sb * 2.2) * 0.16
        # kick on 1 and 3: a short falling sine; hat on the offbeat eighths: filtered noise
        kick = math.sin(2 * math.pi * (55 + 90 * math.exp(-sb * 30)) * sb) * math.exp(-sb * 12) * 0.22
        eighth = b * 2 - step
        noise = rnd.uniform(-1, 1)
        hat = (noise - hat_hp(noise)) * math.exp(-eighth * beat / 2 * 60) * (0.035 if step % 2 else 0.0)
        centre = (bass + kick + hat) * 0.9
        # only the pluck moves: a little left on even steps and right on odd ones; kick and bass stay centred
        pan = 0.15 if step % 2 else -0.15
        left[i] = pl + centre + pluck * (1 - pan) * 0.9
        right[i] = pr + centre + pluck * (1 + pan) * 0.9
    return left, right


def sting(seconds=1.2):
    """A rising two-note bell over a low hit: the sound of the end frame."""
    n = int(seconds * SR)
    left, right = array.array("f", bytes(4 * n)), array.array("f", bytes(4 * n))
    notes = [(0.0, 76), (0.12, 83)]  # E5 then B5
    for i in range(n):
        t = i / SR
        s = 0.0
        for start, note in notes:
            if t >= start:
                d = t - start
                f = hz(note)
                s += (math.sin(2 * math.pi * f * d) + 0.35 * math.sin(2 * math.pi * 2.76 * f * d)) * math.exp(-d * 3.2) * 0.22
        hit = math.sin(2 * math.pi * (45 + 60 * math.exp(-t * 25)) * t) * math.exp(-t * 7) * 0.35
        left[i] = s * 0.95 + hit
        right[i] = s * 1.05 + hit
    return left, right


def write_wav(path, left, right):
    peak = max(max(abs(x) for x in left), max(abs(x) for x in right)) or 1.0
    frames = array.array("h", (0,)) * (2 * len(left))
    for i in range(len(left)):
        frames[2 * i] = int(left[i] / peak * 0.89 * 32767)
        frames[2 * i + 1] = int(right[i] / peak * 0.89 * 32767)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(frames.tobytes())


def encode(wav, out, fade_out=0.0, seconds=None):
    """Loudness to -16 LUFS integrated, -2 dBTP, then AAC 48 kHz stereo 128 kbps."""
    af = "loudnorm=I=-16:TP=-2:LRA=11"
    if fade_out and seconds:
        af = f"afade=t=out:st={seconds - fade_out}:d={fade_out}," + af
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-af", af, "-ar", "48000", "-ac", "2",
                    "-c:a", "aac", "-b:a", "128k", str(out)], check=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for k, spec in enumerate(BEDS, 1):
            wav = Path(tmp) / f"bed-{k}.wav"
            write_wav(wav, *bed(spec))
            encode(wav, OUT / f"bed-{k}.m4a")
            print(f"bed-{k}: {spec['bpm']} BPM", file=sys.stderr)
        wav = Path(tmp) / "sting.wav"
        write_wav(wav, *sting())
        encode(wav, OUT / "sting.m4a", fade_out=0.3, seconds=1.2)
    print(f"written to {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
