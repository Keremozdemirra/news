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


TIMED = "https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps?output_format=mp3_44100_128"


def speak_timed(text, out_mp3, key, voice=None, model=None, post=_post):
    """speak(), with the time each character is spoken (the with-timestamps endpoint): returns (path, [(char, start
    seconds)]), so the screen can show each sentence as it is said."""
    import base64
    voice = voice or cfg("shorts_voice_id", "")
    model = model or cfg("shorts_voice_model", "eleven_v4")
    body = json.dumps({"text": deliver(spoken(text), model), "model_id": model, "voice_settings": settings(model)}).encode()
    code, raw = post(TIMED.format(voice=voice), {"xi-api-key": key, "Content-Type": "application/json"}, body)
    try:
        got = json.loads(raw or b"{}")
    except ValueError:
        got = {}
    if code != 200 or not got.get("audio_base64"):
        detail = got.get("detail")
        raise VoiceError(f"text-to-speech refused ({code}): {detail.get('status') if isinstance(detail, dict) else str(detail)[:80]}")
    Path(out_mp3).write_bytes(base64.b64decode(got["audio_base64"]))
    al = got.get("alignment") or got.get("normalized_alignment") or {}
    return Path(out_mp3), list(zip(al.get("characters") or [], al.get("character_start_times_seconds") or []))


def sentence_starts(sentences, timed):
    """When each sentence starts being spoken, from the character timings. Each is found in order by its first
    words, so delivery tags in the spoken text ("[short pause]") do not throw the match off; a sentence not found
    gets None and the caller spaces it evenly."""
    chars = "".join(c for c, _ in timed).lower()
    times = [t for _, t in timed]
    out, pos = [], 0
    for sent in sentences:
        key = re.sub(r"\s+", " ", spoken(sent).lower())[:18]
        i = chars.find(key, pos)
        if i < 0:
            out.append(None)
            continue
        out.append(times[i])
        pos = i + len(key)
    return out


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout
    return float(out or 0)


# Kerem, 2026-11-27: River and Mark, chosen per story, never the same voice twice in a row
VOICES = {"river": "SAz9YHcvj6GT2YYXdXww", "mark": "UgBBYS2sOqTuMpoF3BR0"}
# a story that clearly suits one voice: hard numbers to Mark, lighter or culture stories to River
SUITS = {"Markets": "mark", "Economy": "mark", "Business": "mark", "Culture": "river", "Tech": "river", "AI": "river"}
CREDIT_FLOOR = 0.10  # below a tenth of the month's characters left, Shorts go out silent


def voices():
    return cfg("shorts_voices", VOICES)


def choose_voice(post, last=None):
    """(name, voice id): the voice the story suits unless the last Short used it, else the other one."""
    pool = voices()
    names = list(pool)
    want = SUITS.get(post.get("topic") or "")
    if want in pool and want != last:
        name = want
    else:
        name = next((n for n in names if n != last), names[0])
    return name, pool[name]


def credits_ok(key, need=700, get=None):
    """True when the plan has at least CREDIT_FLOOR of its monthly characters left and room for this script. Any
    failure reading it counts as no: the Short then goes out silent, never held."""
    try:
        if get is None:
            req = urllib.request.Request("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": key})
            with urllib.request.urlopen(req, timeout=20) as r:
                sub = json.loads(r.read())
        else:
            sub = get()
        limit, used = int(sub["character_limit"]), int(sub["character_count"])
    except Exception as e:  # noqa: BLE001
        print(f"voice: plan not readable ({type(e).__name__}); silent Short")
        return False
    left = limit - used
    ok = limit > 0 and left / limit >= CREDIT_FLOOR and left >= need
    if not ok:
        print(f"voice: {left} of {limit} characters left; silent Short")
    return ok


class Narrator:
    """Speaks lines into a folder and remembers each file, so the timeline can be sized to the speech."""

    def __init__(self, folder, key, voice=None, speak_fn=speak, name=""):
        self.folder, self.key, self.voice, self.speak_fn, self.name = Path(folder), key, voice, speak_fn, name
        self.files = {}

    def seconds(self, text):
        if text not in self.files:
            self.files[text] = self.speak_fn(text, self.folder / f"line{len(self.files)}.mp3", self.key, self.voice)
        return duration(self.files[text])

    def say(self, text):
        """One file for the whole script: (file, seconds)."""
        f = self.speak_fn(text, self.folder / "script.mp3", self.key, self.voice)
        return f, duration(f)

    def say_timed(self, text, timed_fn=None):
        """(file, seconds, [(sentence, start)]): the script as one file and when each sentence begins."""
        from . import spoken as SP
        f, chars = (timed_fn or speak_timed)(text, self.folder / "script.mp3", self.key, self.voice)
        secs = duration(f)
        sents = SP.sentences(text)
        starts = sentence_starts(sents, chars)
        # a sentence the timings did not place gets an even share of what is left
        for i, st in enumerate(starts):
            if st is None:
                prev = starts[i - 1] if i else 0.0
                nxt = next((x for x in starts[i + 1:] if x is not None), secs)
                starts[i] = prev + (nxt - prev) / 2
        return f, secs, list(zip(sents, starts))

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
