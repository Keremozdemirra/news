"""Narration for the YouTube Short: one spoken line per beat, by ElevenLabs text-to-speech, switched by
growth.shorts_voice (off until Kerem has heard the samples and the plan's terms are confirmed for commercial use).

The key: ELEVENLABS_API_KEY from the environment (a GitHub secret in CI). On a Mac, for local samples only, the
keychain item `security find-generic-password -s elevenlabs -a boardread -w`. The key is never printed, logged,
written to a file or put in an error message; a refusal reports the HTTP status and the API's error code only.

The voice speaks exactly the words on screen (the published copy, the labels), nothing added. It sits at about -16
LUFS over the clip's ambience, which stays at its quiet -27 LUFS (audio.py). No music.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128"
VOICE_LUFS, VOICE_PEAK = -16.0, -1.5
GAP = 0.7  # seconds of quiet after a line before the next beat


class VoiceError(RuntimeError):
    pass


def cfg(name, default):
    from . import desk
    return desk.CONFIG.get("growth", {}).get(name, default)


def api_key(env=None, keychain=True):
    """The key, or "" when none is set. Never logged."""
    env = os.environ if env is None else env
    if env.get("ELEVENLABS_API_KEY"):
        return env["ELEVENLABS_API_KEY"].strip()
    if keychain and sys.platform == "darwin" and shutil.which("security"):
        r = subprocess.run(["security", "find-generic-password", "-s", "elevenlabs", "-a", "boardread", "-w"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout.strip()
    return ""


def on():
    return bool(cfg("shorts_voice", False))


def spoken(text):
    """The line as it should be read: the domain spelled out, symbols the voice might misread written as words."""
    t = re.sub(r"\bboardread\.news\b", "boardread dot news", text)
    t = re.sub(r"(\d)\s?%", r"\1 percent", t)
    return t.replace("&", " and ").replace("·", ",").strip()


def _post(url, headers, body, timeout=60):
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def speak(text, out_mp3, key, voice=None, model=None, post=_post):
    """Synthesize `text` to out_mp3. Raises VoiceError with the status and the API's error code, never the key."""
    voice = voice or cfg("shorts_voice_id", "")
    if not voice:
        raise VoiceError("no voice id (growth.shorts_voice_id)")
    model = model or cfg("shorts_voice_model", "eleven_v3")
    body = json.dumps({"text": deliver(spoken(text), model), "model_id": model, "voice_settings": settings(model)}).encode()
    code, raw = post(API.format(voice=voice), {"xi-api-key": key, "Content-Type": "application/json",
                                               "Accept": "audio/mpeg"}, body)
    if code != 200 or not raw or raw[:1] == b"{":
        try:
            detail = json.loads(raw or b"{}").get("detail")
            reason = detail.get("status") if isinstance(detail, dict) else str(detail)[:80]
        except (ValueError, AttributeError):
            reason = "?"
        raise VoiceError(f"text-to-speech refused ({code}): {reason}")
    Path(out_mp3).write_bytes(raw)
    return Path(out_mp3)


NUMBER_START = re.compile(r"\b(?:zero point|about|roughly|nearly|more than|over|some )?\s?(?:zero|one|two|three|four|five|six|seven|"
                          r"eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|a hundred|"
                          r"hundred)\b", re.I)


def deliver(text, model):
    """The script with one light delivery cue for the v3/v4 models (elevenlabs.io/docs best practices, read
    2026-11-27): a [short pause] before the first number after the opening words, so the key figure lands instead of
    running on. Nothing else: more tags make it sound acted. Other models get the text as it is."""
    if model not in ("eleven_v3", "eleven_v4"):
        return text
    m = next((m for m in NUMBER_START.finditer(text) if m.start() > 25), None)
    return text if not m else text[:m.start()].rstrip() + " [short pause] " + text[m.start():].lstrip()


def settings(model):
    """Natural delivery: v3 takes stability in three steps (0 creative, 0.5 natural, 1 robust) and reads the text's
    own rhythm; multilingual_v2 needs lower stability and some style to stop sounding read (Kerem's review, 2026-11-27)."""
    if model in ("eleven_v3", "eleven_v4"):
        return {"stability": 0.5, "similarity_boost": 0.75, "speed": 1.0}  # "Natural": tags still work, no drift
    return {"stability": 0.35, "similarity_boost": 0.75, "style": 0.3, "use_speaker_boost": True}


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout
    return float(out or 0)


class Narrator:
    """Speaks lines into a folder and remembers each file, so the timeline can be sized to the speech."""

    def __init__(self, folder, key, voice=None, speak_fn=speak):
        self.folder, self.key, self.voice, self.speak_fn = Path(folder), key, voice, speak_fn
        self.files = {}

    def seconds(self, text):
        if text not in self.files:
            self.files[text] = self.speak_fn(text, self.folder / f"line{len(self.files)}.mp3", self.key, self.voice)
        return duration(self.files[text])

    def say(self, text):
        """One file for the whole script: (file, seconds)."""
        f = self.speak_fn(text, self.folder / "script.mp3", self.key, self.voice)
        return f, duration(f)

    def cues(self, timed):
        """[(t, file)] for [(t, text)]."""
        return [(t, self.files[text]) for t, text in timed if text in self.files]


def mix(bed_wav, cues, out_wav, seconds):
    """The bed (ambience or silence) with each cue file starting at its time, the voice levelled to VOICE_LUFS."""
    if not cues:
        return Path(bed_wav)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(bed_wav)]
    parts = []
    for i, (t, f) in enumerate(cues, start=1):
        cmd += ["-i", str(f)]
        ms = int(t * 1000)
        parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[c{i}]")
    n = len(cues)
    parts.append("".join(f"[c{i}]" for i in range(1, n + 1)) + f"amix=inputs={n}:normalize=0,apad,atrim=0:{seconds:.2f},"
                 f"loudnorm=I={VOICE_LUFS}:TP={VOICE_PEAK}:LRA=7[v]")
    parts.append(f"[0:a]aresample=48000,aformat=channel_layouts=stereo[b];[b][v]amix=inputs=2:normalize=0,"
                 f"atrim=0:{seconds:.2f}[out]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[out]", "-c:a", "pcm_s16le", str(out_wav)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=180)
    return Path(out_wav)
