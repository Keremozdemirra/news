"""The sound under every video: one of Boardread's own music beds, faded in and out, with the end sting.

The beds and the sting in aidaily/audio/ are made by scripts/make_audio.py from arithmetic alone (oscillators,
filters, envelopes, seeded noise): Boardread owns them, nothing in them belongs to anyone else, and no rights
system can claim them. They are stored at -16 LUFS integrated; the mix keeps that level.

track() writes a WAV the renderers take as their audio input, so the AAC encode happens once, in the video.
"""
import subprocess
import zlib
from pathlib import Path

DIR = Path(__file__).with_name("audio")
BED_SECONDS = 64.0


def beds():
    return sorted(DIR.glob("bed-*.m4a"))


def pick(seed):
    """(bed file, start second) for a video: the story picks the bed and where in it to start, so videos in a row
    differ but the same story always sounds the same."""
    h = zlib.crc32(seed.encode())
    files = beds()
    return files[h % len(files)], float((h >> 8) % 24)


def track(out_wav, seconds, seed, sting_at=None):
    """A WAV of `seconds`: the bed with a 0.4 s fade in and a 1 s fade out; with sting_at, the sting there and the bed
    dipped under it. Normalised to -16 LUFS with peaks under -2.5 dBFS."""
    bed, start = pick(seed)
    start = min(start, max(0.0, BED_SECONDS - seconds - 1))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-t", f"{seconds:.2f}", "-i", str(bed)]
    chain = f"[0:a]afade=t=in:st=0:d=0.4,afade=t=out:st={max(0.0, seconds - 1.0):.2f}:d=1.0"
    if sting_at is not None:
        cmd += ["-i", str(DIR / "sting.m4a")]
        ms = int(sting_at * 1000)
        chain += (f",volume='if(gte(t,{sting_at:.2f}),0.45,1)':eval=frame[b];[1:a]adelay={ms}|{ms}[s];"
                  f"[b][s]amix=inputs=2:normalize=0:duration=first")
    # the cut and the fades move the level, so it is set again: -16 LUFS integrated, peaks held under -2 dBFS so the
    # AAC encode cannot push them over
    chain += ",loudnorm=I=-16:TP=-2.5:LRA=11,aresample=48000,alimiter=limit=0.75:level=false[a]"
    cmd += ["-filter_complex", chain, "-map", "[a]", "-ac", "2", "-c:a", "pcm_s16le", str(out_wav)]
    subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
    return Path(out_wav)
