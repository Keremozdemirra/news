"""The sound of a video: the footage's own sound when it has any, otherwise silence.

No music is added (Kerem's call, 2026-11-27: the generated bed sounded wrong). A clip keeps its original sound
only when the library marks it `audio: true`: the sound is part of the same Commons file under the same licence,
and a person checked it carries no music and no speech (aidaily/broll.json). It plays as quiet ambience: high-passed
against wind rumble and levelled with a two-pass loudnorm to about -27 LUFS, true peak under -6 dBTP, so every
clip sits at the same low level.

Photo videos and clips without usable sound get digital silence. A silent AAC track stays in the file: the
Instagram and Threads video specs describe the audio stream (AAC, 48 kHz at most, one or two channels) and the
desk has always shipped one; silence costs nothing and removes the question.

track() writes a WAV the renderers take as their audio input, so the AAC encode happens once, in the video.
"""
import json
import re
import subprocess
from pathlib import Path

# ambience, not foreground (Kerem, 2026-11-27: the wind was too loud): every clip lands at the same quiet level
TARGET, PEAK, LRA, HIGHPASS = -27.0, -6.0, 7.0, 90


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
    """A WAV of `seconds`: the source's own sound as quiet ambience (high-passed at HIGHPASS Hz against wind rumble,
    two-pass loudnorm to TARGET LUFS integrated with true peak under PEAK dBTP, 0.5 s fades, padded with silence if
    the source is shorter), or silence when there is no source or it has no sound."""
    if not source or not has_audio(source):
        return silence(out_wav, seconds)
    pre = f"highpass=f={HIGHPASS}"
    norm = f"loudnorm=I={TARGET}:TP={PEAK}:LRA={LRA}"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(source), "-vn", "-af", f"{pre},{norm}:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True, timeout=120)
    m = json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])
    if float(m["input_i"]) < -60:
        return silence(out_wav, seconds)  # nothing audible after the filter
    second = (f"{norm}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
              f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    af = (f"{pre},{second},aresample=48000,afade=t=in:st=0:d=0.5,apad,atrim=duration={seconds:.2f},"
          f"afade=t=out:st={max(0.0, seconds - 0.5):.2f}:d=0.5")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(source), "-vn", "-af", af, "-ac", "2",
                    "-c:a", "pcm_s16le", str(out_wav)], check=True, capture_output=True, timeout=120)
    return Path(out_wav)
