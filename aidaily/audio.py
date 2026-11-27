"""The sound of a video: the footage's own sound when it has any, otherwise silence.

No music is added (Kerem's call, 2026-11-27: the generated bed sounded wrong). A clip keeps its original sound
only when the library marks it `audio: true`: the sound is part of the same Commons file under the same licence,
and a person checked it carries no music and no speech (aidaily/broll.json). It is brought to about -16 LUFS
integrated, but never raised more than MAX_GAIN dB, so a quiet field recording does not turn into loud hiss.

Photo videos and clips without usable sound get digital silence. A silent AAC track stays in the file: the
Instagram and Threads video specs describe the audio stream (AAC, 48 kHz at most, one or two channels) and the
desk has always shipped one; silence costs nothing and removes the question.

track() writes a WAV the renderers take as their audio input, so the AAC encode happens once, in the video.
"""
import json
import re
import subprocess
from pathlib import Path

TARGET, MAX_GAIN = -16.0, 12.0


def has_audio(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "json",
                          str(path)], capture_output=True, text=True).stdout
    return bool(json.loads(out or "{}").get("streams"))


def loudness(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True, timeout=120)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    return float(m[-1]) if m else -70.0


def silence(out_wav, seconds):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t",
                    f"{seconds:.2f}", "-c:a", "pcm_s16le", str(out_wav)], check=True, capture_output=True, timeout=60)
    return Path(out_wav)


def track(out_wav, seconds, source=None):
    """A WAV of `seconds`: the source's own sound (short fades, levelled, padded with silence if the source is
    shorter), or silence when there is no source or it has no sound."""
    if not source or not has_audio(source):
        return silence(out_wav, seconds)
    gain = min(TARGET - loudness(source), MAX_GAIN)
    af = (f"volume={gain:.1f}dB,afade=t=in:st=0:d=0.2,alimiter=limit=0.79:level=false,apad,"
          f"atrim=duration={seconds:.2f},afade=t=out:st={max(0.0, seconds - 0.5):.2f}:d=0.5,aresample=48000")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(source), "-vn", "-af", af, "-ac", "2",
                    "-c:a", "pcm_s16le", str(out_wav)], check=True, capture_output=True, timeout=120)
    return Path(out_wav)
