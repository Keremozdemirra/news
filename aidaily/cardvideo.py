"""Video cards: the post's own photo card with the photo moving full-bleed behind the same text.

The card is templates.card() unchanged in look; only its photo is replaced. The text layers are shot once by
headless Chrome on a transparent ground (templates.card(motion=True)), and ffmpeg does the rest: an authored camera
move on the still photo (a slow push toward the focal point with a slight drift), then the meta line, the headline
and the logo chips settle in over the first second. Five Chrome shots and one ffmpeg pass take seconds, where a
frame-by-frame Chrome render takes minutes.

Two shapes from the same template:
  card  1080x1350, the first child of the carousel (media_type=VIDEO, is_carousel_item); the detail slide follows
  reel  1080x1920, a Reel (media_type=REELS), the text kept clear of the bands Instagram draws its own UI over

No footage, no generated imagery: the only picture is the post's own licensed photo, under CC0, CC BY or public
domain (video.photo_ok). The camera move is ours; nothing is added to the photo.
"""
import json
import re
import shutil
import subprocess
import tempfile
import urllib.parse
from pathlib import Path

from . import render as R
from . import templates as T
from . import video as V

W, FPS, SECONDS = 1080, 30, 8.0
HEIGHT = {"card": 1350, "reel": 1920}
SS = 2  # the camera works on a 2x canvas so a move of a fraction of a pixel per frame does not stair-step
# a push of 7% over 8 s reads as a camera move; 12% and over starts to look like a zoom effect
PUSH = 0.07
ENCODE = ["-c:v", "libx264", "-profile:v", "high", "-preset", "slow", "-crf", "18", "-maxrate", "8M", "-bufsize", "16M",
          "-g", "60", "-keyint_min", "60", "-sc_threshold", "0", "-flags", "+cgop", "-pix_fmt", "yuv420p",
          "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
          "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "1",
          "-movflags", "+faststart", "-use_editlist", "0"]
LAYERS = ("base", "meta", "head", "chips")
# (layer, start s, duration s, rise px): everything readable by 0.8 s, inside the first-three-seconds window
REVEAL = {"meta": (0.0, 0.35, 14), "head": (0.08, 0.50, 30), "chips": (0.35, 0.40, 0)}


def photo_path(story):
    uri = (story.get("_assets") or {}).get("photo", "")
    if not uri.startswith("file://"):
        return None
    p = Path(urllib.parse.unquote(urllib.parse.urlparse(uri).path))
    return p if p.exists() else None


def eligible(story):
    """Why this story cannot be a video card, or "" when it can. A video needs the photo layout, a local photo file
    and a licence that allows an adaptation the platform can sublicense."""
    if T.layout(story) != "photo":
        return "no photo layout"
    if not photo_path(story):
        return "photo file missing"
    if not V.photo_ok({"credit": (story.get("_assets") or {}).get("credit", "")}):
        return "photo licence does not allow an edited video (share-alike, no-derivatives or non-commercial)"
    return ""


def focus(story):
    """The point the camera moves toward, as fractions of the photo's width and height. The face agent's focal point
    (`focus` on the story or its assets) when present; else the card's own crop point: a person's head sits high."""
    f = story.get("focus") or (story.get("_assets") or {}).get("focus")
    if isinstance(f, dict):
        f = (f.get("x"), f.get("y"))
    try:
        x, y = float(f[0]), float(f[1])
        if 0 <= x <= 1 and 0 <= y <= 1:
            return x, y
    except (TypeError, ValueError, IndexError):
        pass
    return (0.5, 0.25) if story.get("person") else (0.5, 0.5)


def probe_size(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    return int(s["width"]), int(s["height"])


def camera(src_w, src_h, h, fx, fy, seconds=SECONDS, push=PUSH):
    """The ffmpeg filter chain that turns the still into the moving background, on input 0.

    The photo is cropped to the canvas aspect around the focal point (as the still card crops it) and scaled to a
    canvas SS times the output. A window then narrows by `push` and its centre travels a third of the way toward the
    focal point. The `perspective` filter samples the window with sub-pixel precision; zoompan rounds its window to
    whole pixels and judders when the move is slower than a pixel a frame, which a calm push always is. The move
    eases out but never stops (a third of it is linear), so the picture is still alive in the last second."""
    cw, ch = W * SS, h * SS
    n = int(round(seconds * FPS))
    # the largest canvas-aspect crop of the photo, centred on the focal point as far as the photo allows
    aw = min(src_w, src_h * cw / ch)
    ah = aw * ch / cw
    ax = min(max(fx * src_w - aw / 2, 0), src_w - aw)
    ay = min(max(fy * src_h - ah / 2, 0), src_h - ah)
    r = cw / aw
    # the focal point in canvas coordinates, and where the window's centre ends: a third of the way to it
    dx = ((fx * src_w - ax) * r - cw / 2) / 3
    dy = ((fy * src_h - ay) * r - ch / 2) / 3
    e = f"(0.35*in/{n - 1}+0.65*(1-pow(1-in/{n - 1},2)))"
    ww, wh = f"({cw}/(1+{push}*{e}))", f"({ch}/(1+{push}*{e}))"
    cx = f"max({ww}/2,min({cw}-{ww}/2,{cw / 2}+{dx:.2f}*{e}))"
    cy = f"max({wh}/2,min({ch}-{wh}/2,{ch / 2}+{dy:.2f}*{e}))"
    x0, x1 = f"{cx}-{ww}/2", f"{cx}+{ww}/2"
    y0, y1 = f"{cy}-{wh}/2", f"{cy}+{wh}/2"
    return (f"[0:v]crop={int(aw)}:{int(ah)}:{int(ax)}:{int(ay)},scale={cw}:{ch}:flags=lanczos,setsar=1,fps={FPS},"
            f"perspective=x0='{x0}':y0='{y0}':x1='{x1}':y1='{y0}':x2='{x0}':y2='{y1}':x3='{x1}':y3='{y1}'"
            f":interpolation=cubic:eval=frame,scale={W}:{h}:flags=lanczos,format=rgba[bg]")


def layer_html(story, shape, only):
    """The card's text in one layer: every other part hidden (visibility keeps the layout, so the layers line up)."""
    html_ = T.card(story, motion=True, height=HEIGHT[shape])
    parts = {"base": (".c-meta", ".c-head", ".c-chips"), "meta": (".c-grad", ".c-head", ".c-chips", ".c-foot"),
             "head": (".c-grad", ".c-meta", ".c-chips", ".c-foot"), "chips": (".c-grad", ".c-meta", ".c-head", ".c-foot"),
             "foot": (".c-grad", ".c-meta", ".c-head", ".c-chips")}[only]
    css = ",".join(parts) + "{visibility:hidden}"
    return html_.replace("</body>", f"<style>{css}</style></body>")


def shoot_layer(html_text, png, w, h):
    """render.shoot() on a transparent ground."""
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(html_text)
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run([R.CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={profile}",
                        f"--window-size={w},{h}", "--default-background-color=00000000", "--virtual-time-budget=6000",
                        f"--screenshot={png}", f"file://{f.name}"], check=True, capture_output=True, timeout=60)
    Path(f.name).unlink()


def reveal(name, idx):
    """Overlay of layer input idx onto the running picture: an alpha fade and a rise, both easing out."""
    t0, d, rise = REVEAL[name]
    p = f"min(max((t-{t0})/{d},0),1)"
    fade = f"format=rgba,fade=t=in:st={t0}:d={d}:alpha=1"
    y = f"{rise}*pow(1-{p},3)" if rise else "0"
    return fade, y


def with_footage(story, clip):
    """The story as the footage card shows it: the clip's label and credit in place of the photo's (the photo is not
    on screen, so its credit would name the wrong work)."""
    from . import broll
    a = dict(story.get("_assets") or {}, credit=broll.credit(clip))
    return dict(story, _assets=a)


def build(story, out_mp4, shape="card", seconds=SECONDS, footage=None):
    """Render one video card. Returns the output path; raises when ffmpeg or Chrome fail. footage: a local clip file
    (broll.fetch) that replaces the moving photo; the story must already carry its credit (with_footage)."""
    why = eligible(story)
    if why:
        raise ValueError(why)
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found")
    h = HEIGHT[shape]
    src = photo_path(story)
    sw, sh = probe_size(src)
    fx, fy = focus(story)
    out_mp4 = Path(out_mp4)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        pngs = {}
        for name in LAYERS:
            pngs[name] = Path(tmp) / f"{name}.png"
            shoot_layer(layer_html(story, shape, name), pngs[name], W, h)
        if footage:
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-t", f"{seconds}", "-i", str(footage)]
        else:
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(FPS), "-t", f"{seconds}", "-i", str(src)]
        for name in LAYERS:
            cmd += ["-loop", "1", "-framerate", str(FPS), "-t", f"{seconds}", "-i", str(pngs[name])]
        cmd += ["-f", "lavfi", "-t", f"{seconds}", "-i", "anullsrc=r=48000:cl=mono"]
        if footage:
            from . import broll
            chain = [broll.background(*probe_size(footage), W, h, seconds, FPS)]
        else:
            chain = [camera(sw, sh, h, fx, fy, seconds)]
        chain.append("[1:v]format=rgba[l1];[bg][l1]overlay=0:0:format=auto[v1]")
        last = "v1"
        for i, name in enumerate(LAYERS[1:], start=2):
            fade, y = reveal(name, i)
            chain.append(f"[{i}:v]{fade}[l{i}];[{last}][l{i}]overlay=x=0:y='{y}':format=auto:eval=frame[v{i}]")
            last = f"v{i}"
        chain.append(f"[{last}]scale=out_color_matrix=bt709:out_range=tv:flags=lanczos,format=yuv420p[v]")
        cmd += ["-filter_complex", ";".join(chain), "-map", "[v]", "-map", f"{len(LAYERS) + 1}:a",
                "-t", f"{seconds}", "-r", str(FPS)] + ENCODE + [str(out_mp4)]
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
    return out_mp4


def cover(mp4, out_jpg, at=1.6):
    """A frame once the headline has settled: the Reel's cover_url and the grid thumbnail."""
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(at), "-i", str(mp4), "-frames:v", "1", "-q:v", "2",
                    str(out_jpg)], check=True, capture_output=True, timeout=60)
    return out_jpg


def audit_file(path, shape="card"):
    """Instagram's video spec on the file (codec, size, rate, audio, length, moov first, no edit list), for both
    shapes. Returns the problems; empty passes. Carousel videos: 3 to 60 s, 100 MB; Reels: 3 s to 15 min, 300 MB;
    both H.264 or HEVC, closed GOP, 4:2:0, AAC at most 48 kHz, 23 to 60 fps, width at most 1920.
    https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media (read 2026-11-27)"""
    out = []
    try:
        j = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                                      capture_output=True, text=True, timeout=60).stdout or "{}")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        return [f"video unreadable: {e}"]
    streams = j.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    a = next((s for s in streams if s.get("codec_type") == "audio"), {})
    if not v:
        return ["no video stream"]
    if v.get("codec_name") != "h264" or v.get("profile") != "High" or v.get("pix_fmt") != "yuv420p":
        out.append(f"video is {v.get('codec_name')}/{v.get('profile')}/{v.get('pix_fmt')}, not h264/High/yuv420p")
    if (v.get("width"), v.get("height")) != (W, HEIGHT[shape]):
        out.append(f"size {v.get('width')}x{v.get('height')}, not {W}x{HEIGHT[shape]}")
    if v.get("r_frame_rate") != f"{FPS}/1":
        out.append(f"frame rate {v.get('r_frame_rate')}")
    if a.get("codec_name") != "aac" or int(a.get("sample_rate") or 0) > 48000:
        out.append("no AAC audio at 48 kHz or less")
    dur = float((j.get("format") or {}).get("duration") or 0)
    if not 3 <= dur <= 60:
        out.append(f"duration {dur:.1f} s outside 3 to 60 s")
    if int((j.get("format") or {}).get("size") or 0) > 50 * 1024 * 1024:
        out.append("file over 50 MB")
    head = Path(path).read_bytes()[:128 * 1024]
    mdat, moov = head.find(b"mdat"), head.find(b"moov")
    if moov < 0 or (0 <= mdat < moov):
        out.append("moov atom not before the media data (no +faststart)")
    if b"elst" in head[: moov + 4096] if moov >= 0 else False:
        out.append("edit list present")
    return out


def sheet(mp4, out_jpg, per_second=2, cols=8, width=270):
    """Contact sheet for review, phone-sized frames."""
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)],
                               capture_output=True, text=True).stdout)
    rows = -(-int(dur * per_second) // cols)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-vf",
                    f"fps={per_second},scale={width}:-2,tile={cols}x{rows}:padding=4:color=0x333333", "-frames:v", "1",
                    "-q:v", "3", str(out_jpg)], check=True, capture_output=True)
    return out_jpg
