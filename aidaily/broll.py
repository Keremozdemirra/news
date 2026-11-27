"""Archive footage behind the card text: a vetted clip library, like scenes.json for photos.

aidaily/broll.json lists clips a person watched frame by frame: wide B-roll of a kind of place or thing (an oil
field, a wind farm, a container terminal, a harvest, a runway, a motorway), with no identifiable person, no brand
the story does not name, and no event that could be mistaken for the news. Each clip records its source, licence,
author and page, and the second it starts at.

Allowed sources, checked 2026-11-27: Wikimedia Commons under CC0, CC BY (no SA, NC or ND), or public domain that
names a US federal author (footage.commons_check, the same rules as the photo guard), and NASA. Pexels's licence
allows edits and social posts, but its API needs a key and asks for a link back on every use; it is not used.

The clip must fit the headline the way a scene photo must (a rule's `match`, then scenes.fits for place-named or
one-subject clips), so a gas story never gets an oil field and a match report never gets a stadium concert. The
video always says what it is: "Archive footage, not from this event" goes on screen beside the credit. When no
clip fits, the post keeps its photo and the photo moves instead.
"""
import json
import re
import subprocess
import urllib.parse
from pathlib import Path

from . import scenes

DATA = Path(__file__).with_name("broll.json")
LABEL = "Archive footage, not from this event"
UA = "boardread.news build (+https://boardread.news/about/)"


def load():
    return json.loads(DATA.read_text())


def credit(clip):
    """What the licence needs, after the label. CC BY: creator, licence, source, and that it was changed."""
    who = clip.get("author") or "unknown author"
    lic = clip["licence"]
    src = "NASA" if clip["source"] == "nasa" else "Wikimedia Commons"
    if lic.startswith("CC0"):
        tail = f"Video: {who}, CC0, via {src}"
    elif lic.startswith("CC BY"):
        tail = f"Video: {who}, {lic}, via {src}. Edited"
    else:
        tail = f"Video: {who}, public domain, via {src}"
    return f"{LABEL}. {tail}"


def fits(clip, headline, min_seconds=0):
    if clip.get("people"):
        return False  # identifiable people stay out unless a clip is the story's own subject, which this library never is
    if min_seconds and clip.get("seconds", 0) - clip.get("start", 0) < min_seconds:
        return False
    if not re.search(clip["match"], headline or "", re.I):
        return False
    if clip.get("skip") and re.search(clip["skip"], headline or "", re.I):
        return False
    return scenes.fits(clip, headline)


def pick(headline, used=(), min_seconds=0, data=None, seed=""):
    """The clip for a headline, or None. Clips not used recently first, rotated by the story like scene photos."""
    clips = [c for c in (data or load())["clips"] if fits(c, headline, min_seconds)]
    if not clips:
        return None
    ring = scenes.order([dict(c, file=c["id"]) for c in clips], set(used), seed=seed or headline)
    return next(c for c in clips if c["id"] == ring[0]["file"])


def source_url(clip, size="1080p"):
    """Commons serves VP9 transcodes beside the original; a 1080p one is far smaller than a 4K original and is what
    the card needs. NASA clips carry their MP4 URL."""
    if clip["source"] != "commons":
        return clip["url"]
    name = clip["file"].replace(" ", "_")
    path = clip["path"]  # "c/c8": the two hash folders Commons files sit in
    q = urllib.parse.quote(name)
    return f"https://upload.wikimedia.org/wikipedia/commons/transcoded/{path}/{q}/{q}.{size}.vp9.webm"


def still_ok(clip, info_fn=None):
    """The clip's licence read again at render time, like a photo's: (ok, why)."""
    if clip["source"] != "commons":
        return True, ""
    from . import footage as F
    info_fn = info_fn or (lambda f: F._json(f"{F.COMMONS_API}?action=query&format=json&prop=imageinfo&iiprop=extmetadata"
                                              f"&iiextmetadatafilter={F.COMMONS_META}&titles={urllib.parse.quote('File:' + f)}"))
    try:
        page = next(iter(info_fn(clip["file"])["query"]["pages"].values()))
        meta = {k: F._strip(v.get("value", "")) for k, v in page["imageinfo"][0]["extmetadata"].items()}
    except Exception as e:  # noqa: BLE001  unreachable: no footage this time, the photo moves instead
        return False, f"licence could not be read: {str(e)[:80]}"
    c = {"licence": meta.get("LicenseShortName", ""), "creator": meta.get("Artist", ""), "credit": meta.get("Credit", ""),
         "desc": meta.get("ImageDescription", ""), "restrictions": meta.get("Restrictions", "")}
    if c["licence"] != clip["licence"]:
        return False, f"licence now reads {c['licence']!r}, recorded {clip['licence']!r}"
    bad = F.commons_check(c)
    return (not bad), "; ".join(bad)


def fetch(clip, dest, seconds):
    """The clip's working segment as a local file (one request, the needed seconds only)."""
    dest = Path(dest)
    for size in ("1080p", "720p"):
        p = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-user_agent", UA, "-ss", str(clip.get("start", 0)),
                            "-t", f"{seconds + 0.5:.2f}", "-i", source_url(clip, size), "-an", "-c:v", "libx264",
                            "-preset", "veryfast", "-crf", "14", str(dest)], capture_output=True, text=True, timeout=300)
        if p.returncode == 0 and dest.exists() and dest.stat().st_size:
            return dest
    raise RuntimeError(f"footage {clip['id']}: {p.stderr[-200:]}")


def background(src_w, src_h, w, h, seconds, fps=30, fx=0.5, src="[0:v]", out="[bg]"):
    """The filter chain that fills the canvas with input 0: cover-crop around fx, held to `seconds`, RGBA. The
    footage moves on its own; no camera move is added."""
    aw = min(src_w, src_h * w / h)
    ah = aw * h / w
    ax = min(max(fx * src_w - aw / 2, 0), src_w - aw)
    ay = (src_h - ah) / 2
    return (f"{src}crop={int(aw)}:{int(ah)}:{int(ax)}:{int(ay)},fps={fps},scale={w}:{h}:flags=lanczos,setsar=1,"
            f"trim=duration={seconds},setpts=PTS-STARTPTS,format=rgba{out}")


def usable(clip):
    return clip.get("seconds", 0) - clip.get("start", 0)
