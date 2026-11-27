"""YouTube Shorts: one top story as a 9:16 video, uploaded to the channel, switched by growth.shorts.

The Short is the video card's Reel shape carried further: the story's own licensed photo moves full-bleed behind
the card text (cardvideo.py), then the same picture carries one or two sentences from the published dek and body,
the outlets the story was reported from, and an end frame with the site. Every word on screen was already published
and checked on the story page: the video adds no new claim. When a vetted archive clip fits the headline
(broll.py), it plays behind the text instead, labelled "Archive footage, not from this event". No generated imagery,
no AI line (the channel bio carries the disclosure); photo and footage are real, so containsSyntheticMedia is false.

Candidates are the stories the desk already picked for the social channels: on the site (status published or web),
on a topic the social channels carry, at or above social_min_score, with a photo under CC0, CC BY or public domain.

Upload is YouTube Data API v3 videos.insert with the resumable protocol, OAuth scope youtube.upload only, an access
token minted per run from a refresh token held in GitHub secrets (scripts/youtube_token.py stores it). Quota checked
2026-11-27 at developers.google.com/youtube/v3/docs/videos/insert: videos.insert costs 1 unit in its own "Video
Uploads" bucket of 100 calls a day; the cap here is a few a day and never more than HARD_CAP.

A post is marked attempted before its upload starts, the way every send here works: a run killed mid-upload can
never upload the same story twice. State lives in state/shorts.json.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from . import cardvideo as CV
from . import desk
from . import platforms as P
from . import templates as T
from . import video as V

UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/youtube.upload"
NEWS_CATEGORY = "25"  # News & Politics
HARD_CAP = 10  # a day, whatever desk.json says: a tenth of the upload bucket
TITLE_MAX, DESCRIPTION_MAX = 100, 5000  # characters, bytes (videos resource, snippet.title / snippet.description)

HEAD_SECONDS, SOURCES_SECONDS, END_SECONDS = 5.5, 3.0, 2.5
FADE_IN, FADE_OUT, RISE = 0.35, 0.3, 24
PUSH = 0.12  # over the whole Short, so the move is slower per second than the 8 s card's
FACT_MAX_CHARS = 220


def cfg(name, default):
    return desk.CONFIG.get("growth", {}).get(name, default)


def _dt(s):
    return datetime.fromisoformat(s)


def _state():
    return desk._load(desk.STATE / "shorts.json", {})


def _save(state):
    desk._save(desk.STATE / "shorts.json", state)


# content

def facts(post, count=2):
    """Up to `count` sentences from the published dek and body that add to the headline, short enough to read."""
    return [s for s in P.why_it_matters(post, count + 2) if len(s) <= FACT_MAX_CHARS][:count]


def outlets_line(post):
    names = [n for n in (post.get("sources") or []) if n][:4]
    if not names:
        return ""
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def beats(post):
    """(name, seconds) in order. A fact holds about as long as it takes to read twice."""
    out = [("head", HEAD_SECONDS)]
    for i, f in enumerate(facts(post)):
        out.append((f"fact{i}", min(max(len(f.split()) / 2.8 + 1.2, 3.5), 6.5)))
    if outlets_line(post):
        out.append(("sources", SOURCES_SECONDS))
    out.append(("end", END_SECONDS))
    return out


def story_from(post, photo, credit):
    """The story dict templates.card() reads, rebuilt from the published post (as scripts/rerender.py does)."""
    return {"title": post["headlines"][0], "headline": post["headlines"][0], "dek": post.get("dek", ""),
            "topic": post.get("topic", ""), "category": (post.get("categories") or ["news"])[0],
            "published": post.get("published") or post.get("created") or desk.now().isoformat(),
            "source": (post.get("sources") or [""])[0], "outlets": post.get("sources") or [],
            "timeline": [0] * max(len(post.get("sources") or []), 1), "person": post.get("person") or "",
            "focus": post.get("focus"), "score": post.get("score"),
            "_assets": {"logo": "", "backer": "", "logos": [], "logo_names": [], "ticker": None,
                        "photo": Path(photo).resolve().as_uri(), "credit": credit, "file": post.get("photo_file", ""),
                        "kind": "photo", "alt": ""}}


def source_photo(post, dest, fetch=True):
    """(path, credit) of the story's photo at a size that fills 1920 px of height. The licence is read again from
    Commons at build time; offline, the media branch's 1400 px copy and the post's recorded credit are used."""
    dest = Path(dest)
    if fetch and post.get("photo_file"):
        from . import entities as E
        try:
            info = E._commons_info(post["photo_file"], width=2400)
            ok, credit = E.photo_ok(info)
            if not ok:
                raise ValueError("photo licence no longer reusable")
            dest.write_bytes(E._get(info.get("thumburl") or info["url"], raw=True))
            return dest, credit
        except (urllib.error.URLError, OSError, KeyError, IndexError):
            pass  # Commons unreachable: fall back to the copy already published with the post
    local = desk.MEDIA / post["id"] / "photo.jpg"
    if not local.exists():
        raise FileNotFoundError(f"{post['id']}: no photo file")
    shutil.copy(local, dest)
    return dest, post.get("credit", "")


def text_layer(story, text, weight=500, size=60):
    """The card's headline slot set with other text: same position, same safe zone, same base and credit."""
    s = dict(story, headline=text, title=text)
    html_ = T.card(s, motion=True, height=CV.HEIGHT["reel"])
    # the fonts load 400, 500, 700 and 800: a weight in between is synthesised and looks heavier than the headline
    css = (f".c-grad,.c-chips,.c-foot,.c-meta{{visibility:hidden}}"
           f".c-head{{font-weight:{weight}!important;font-size:{size}px!important;letter-spacing:-0.01em!important;"
           f"line-height:1.16!important}}")  # !important: the card sets these inline
    return html_.replace("</body>", f"<style>{css}</style></body>")


def end_frame(brand=T.BRAND):
    """The wordmark, the site and what is there, centred in the band no player UI covers."""
    return T._reel_shell(
        '<div style="flex:1;display:flex;flex-direction:column;justify-content:center;padding:0 150px 180px 72px">'
        f'<div style="font-size:150px;font-weight:800;letter-spacing:-6px;line-height:1">{T.e(brand["name"])}</div>'
        f'<div style="margin-top:48px;font-size:64px;font-weight:700;letter-spacing:-1.5px">{T.e(desk.brand_domain())}</div>'
        f'<div style="margin-top:20px;font-size:52px;font-weight:500;color:#9aa0a8;letter-spacing:-1px">'
        'Full story and sources</div></div>')


def overlay(idx, t_in, t_out, rise=RISE, fade_in=FADE_IN):
    """Input idx faded in at t_in (rising `rise` px, easing out) and out at t_out (None: stays)."""
    f = f"format=rgba,fade=t=in:st={t_in:.2f}:d={fade_in}:alpha=1"
    if t_out is not None:
        f += f",fade=t=out:st={t_out - FADE_OUT:.2f}:d={FADE_OUT}:alpha=1"
    p = f"min(max((t-{t_in:.2f})/{fade_in},0),1)"
    return f, (f"{rise}*pow(1-{p},3)" if rise else "0")


def choose_footage(post, seconds, fetch=True):
    """An archive clip that fits the headline and runs long enough, with its licence read again, or None."""
    if not fetch or not (desk.CONFIG.get("video") or {}).get("footage"):
        return None
    from . import broll
    clip = broll.pick(post["headlines"][0], min_seconds=seconds, seed=post["id"])
    if not clip:
        return None
    ok, why = broll.still_ok(clip)
    if not ok:
        print(f"shorts: footage {clip['id']} skipped: {why}")
        return None
    return clip


def build(post, out_mp4, fetch=True, clip=None):
    """Render the Short. Returns (path, credit); raises when the post cannot be one or a tool fails. With a clip
    (choose_footage) the archive footage replaces the moving photo and its credit replaces the photo's."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found")
    if not post.get("photo_file") or not V.photo_ok({"credit": post.get("credit", "")}):
        raise ValueError("no photo under CC0, CC BY or public domain")
    h, out_mp4 = CV.HEIGHT["reel"], Path(out_mp4)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    plan = beats(post)
    total = sum(d for _, d in plan)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        photo, credit = source_photo(post, tmp / "photo.jpg", fetch)
        if not V.photo_ok({"credit": credit}):
            raise ValueError("photo licence does not allow an edited video")
        story = story_from(post, photo, credit)
        why = CV.eligible(story)
        if why:
            raise ValueError(why)
        clip = clip if clip is not None else choose_footage(post, total, fetch)
        footage = None
        if clip:
            from . import broll
            try:
                footage = broll.fetch(clip, tmp / "clip.mp4", total)
                story, credit = CV.with_footage(story, clip), broll.credit(clip)
            except Exception as e:  # noqa: BLE001  no footage this time: the photo moves instead
                print(f"shorts: footage {clip['id']} not fetched, photo instead: {str(e)[:160]}")
        layers = []  # (png, t_in, t_out, rise, fade_in)
        t = 0.0
        for name, d in plan:
            if name == "head":
                for part in CV.LAYERS:
                    png = tmp / f"head-{part}.png"
                    CV.shoot_layer(CV.layer_html(story, "reel", part), png, CV.W, h)
                    if part == "base":  # gradient, wordmark and photo credit: on screen for every photo beat
                        layers.append((png, 0.0, total - END_SECONDS + 0.4, 0, 0.01))
                    else:
                        t0, fd, rise = CV.REVEAL[part]
                        layers.append((png, t0, d, rise, fd))
            elif name.startswith("fact"):
                png = tmp / f"{name}.png"
                CV.shoot_layer(text_layer(story, facts(post)[int(name[4:])]), png, CV.W, h)
                layers.append((png, t, t + d, RISE, FADE_IN))
            elif name == "sources":
                png = tmp / "sources.png"
                CV.shoot_layer(text_layer(story, f"Reported by {outlets_line(post)}", weight=700, size=72), png, CV.W, h)
                layers.append((png, t, t + d + 0.4, RISE, FADE_IN))
            else:
                png = tmp / "end.png"
                from . import render as R
                R.shoot(end_frame(), png, CV.W, h)
                layers.append((png, t - 0.4, None, 0, 0.4))  # a crossfade out of the photo
            t += d
        sw, sh = CV.probe_size(photo)
        fx, fy = CV.focus(story)
        if footage:
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-t", f"{total}", "-i", str(footage)]
        else:
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(CV.FPS), "-t", f"{total}", "-i", str(photo)]
        for png, *_ in layers:
            cmd += ["-loop", "1", "-framerate", str(CV.FPS), "-t", f"{total}", "-i", str(png)]
        cmd += ["-f", "lavfi", "-t", f"{total}", "-i", "anullsrc=r=48000:cl=mono"]
        if footage:
            from . import broll
            chain, last = [broll.background(*CV.probe_size(footage), CV.W, h, total, CV.FPS)], "bg"
        else:
            chain, last = [CV.camera(sw, sh, h, fx, fy, total, PUSH)], "bg"
        for i, (png, t_in, t_out, rise, fade_in) in enumerate(layers, start=1):
            f, y = overlay(i, t_in, t_out, rise, fade_in)
            chain.append(f"[{i}:v]{f}[l{i}];[{last}][l{i}]overlay=x=0:y='{y}':format=auto:eval=frame[v{i}]")
            last = f"v{i}"
        chain.append(f"[{last}]scale=out_color_matrix=bt709:out_range=tv:flags=lanczos,format=yuv420p[v]")
        cmd += ["-filter_complex", ";".join(chain), "-map", "[v]", "-map", f"{len(layers) + 1}:a",
                "-t", f"{total}", "-r", str(CV.FPS)] + CV.ENCODE + [str(out_mp4)]
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=900)
    return out_mp4, credit


# metadata

def _clean(s):
    return re.sub(r"[<>]", "", s or "").strip()


def title(post):
    """The headline, at most 100 characters, cut at a word."""
    t = _clean(post["headlines"][0])
    if len(t) <= TITLE_MAX:
        return t
    return t[:TITLE_MAX - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def description(post, credit):
    lines = [_clean(post.get("dek")), "",
             f"Full story and sources: {desk.story_url(post['id'], 'youtube')}"]
    if outlets_line(post):
        lines.append(f"Reported by {outlets_line(post)}.")
    if credit:
        from . import entities
        credit = entities.clean_credit(credit)
        edited = re.search(r"\bCC BY\b", credit) and not credit.endswith("Edited")
        lines += ["", _clean(credit) + (". Edited" if edited else "")]
    lines += ["", "#Shorts #news #business"]
    text = "\n".join(lines).strip()
    while len(text.encode("utf-8")) > DESCRIPTION_MAX:
        text = text[:-50]
    return text


def metadata(post, credit):
    """The videos resource for insert. Real photographs only, so containsSyntheticMedia is false."""
    tags = [x for x in (post.get("topic"), "business news", "news") if x]
    return {"snippet": {"title": title(post), "description": description(post, credit), "categoryId": NEWS_CATEGORY,
                        "tags": tags, "defaultLanguage": "en", "defaultAudioLanguage": "en"},
            "status": {"privacyStatus": cfg("shorts_privacy", "public"), "selfDeclaredMadeForKids": False,
                       "containsSyntheticMedia": False, "embeddable": True}}


# choice

def per_day():
    return max(0, min(int(cfg("shorts_per_day", 2)), HARD_CAP))


def _norm(headline):
    return re.sub(r"[^a-z0-9]+", " ", headline.casefold()).strip()


def candidates():
    """Posts that may become a Short now, best first."""
    st = _state()
    tried = set(st.get("attempted", {}))
    seen = {_norm(v.get("headline", "")) for v in st.get("attempted", {}).values()}
    since = desk.now() - timedelta(hours=float(cfg("shorts_max_age_hours", 12)))
    floor = float(desk.CONFIG.get("social_min_score", 0) or 0)
    rows = []
    for p, _ in desk.posts():
        if p.get("status") not in ("published", "web") or p.get("kind") in desk.NO_CROSSPOST or not desk.social_allowed(p):
            continue
        if p["id"] in tried or _norm(p["headlines"][0]) in seen or (p.get("score") or 0) < floor:
            continue
        when = _dt(p.get("published")) if p.get("published") else None
        if not when or when < since:
            continue
        if not p.get("photo_file") or not V.photo_ok({"credit": p.get("credit", "")}) or not facts(p):
            continue
        rows.append(p)
    rows.sort(key=lambda p: (p.get("score") or 0, p.get("published", "")), reverse=True)
    return rows


def today_count(st=None):
    day = f"{desk.now():%Y-%m-%d}"
    return sum(1 for v in (st or _state()).get("attempted", {}).values() if (v.get("at") or "").startswith(day))


def due():
    """(True, "") when a Short should be made now, else (False, why)."""
    if not desk.growth("shorts"):
        return False, "switch off"
    if desk.paused():
        return False, "paused"
    st = _state()
    if today_count(st) >= per_day():
        return False, "daily cap reached"
    last = max((v.get("at", "") for v in st.get("attempted", {}).values()), default="")
    if last and _dt(last) > desk.now() - timedelta(minutes=int(cfg("shorts_spacing_minutes", 180))):
        return False, "spacing"
    if st.get("build_date") == f"{desk.now():%Y-%m-%d}" and st.get("build_failures", 0) >= 3:
        return False, "build failed repeatedly today"
    if not candidates():
        return False, "no candidate"
    return True, ""


# upload

class Rejected(P.PlatformError):
    pass


def _http(method, url, headers=None, body=None, timeout=120):
    """(status, headers, body bytes). 308 is the resumable protocol's "keep going", not an error."""
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read()


def access_token(http=_http, env=None):
    env = os.environ if env is None else env
    need = ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")
    if not all(env.get(k) for k in need):
        raise P.Missing("YouTube secrets not set (scripts/youtube_token.py)")
    body = urllib.parse.urlencode({"client_id": env["YT_CLIENT_ID"], "client_secret": env["YT_CLIENT_SECRET"],
                                   "refresh_token": env["YT_REFRESH_TOKEN"], "grant_type": "refresh_token"}).encode()
    code, _, raw = http("POST", TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded"}, body)
    data = json.loads(raw or b"{}")
    if code != 200 or not data.get("access_token"):
        # the error code only ("invalid_grant": the refresh token was revoked or expired); never the body's tokens
        raise Rejected(f"token refresh refused ({code}): {data.get('error', '?')}")
    return data["access_token"]


def _header(headers, name):
    return next((v for k, v in headers.items() if k.lower() == name.lower()), None)


def upload(path, meta, token, http=_http, tries=3):
    """videos.insert, resumable: open a session with the metadata, then send the bytes; after a broken transfer,
    ask how much arrived and send the rest. Returns the video id."""
    data = Path(path).read_bytes()
    size = len(data)
    auth = {"Authorization": f"Bearer {token}"}
    qs = urllib.parse.urlencode({"uploadType": "resumable", "part": "snippet,status"})
    code, h, raw = http("POST", f"{UPLOAD_URL}?{qs}", {**auth, "Content-Type": "application/json; charset=UTF-8",
                                                       "X-Upload-Content-Length": str(size),
                                                       "X-Upload-Content-Type": "video/mp4"},
                        json.dumps(meta).encode())
    session = _header(h, "Location")
    if code != 200 or not session:
        raise Rejected(f"upload session refused ({code}): {_reason(raw)}")
    start = 0
    for _ in range(tries):
        chunk = data[start:]
        headers = {**auth, "Content-Type": "video/mp4", "Content-Length": str(len(chunk))}
        if start:
            headers["Content-Range"] = f"bytes {start}-{size - 1}/{size}"
        try:
            code, h, raw = http("PUT", session, headers, chunk, timeout=600)
        except (urllib.error.URLError, OSError):
            code, h, raw = 0, {}, b""
        if code in (200, 201):
            vid = json.loads(raw).get("id")
            if not vid:
                raise Rejected("upload finished without a video id")
            return vid
        if code and code < 500 and code != 308:
            raise Rejected(f"upload refused ({code}): {_reason(raw)}")
        # interrupted or a server error: ask where the transfer stands, then resume from there
        code, h, raw = http("PUT", session, {**auth, "Content-Length": "0", "Content-Range": f"bytes */{size}"}, b"")
        if code in (200, 201):
            return json.loads(raw).get("id")
        rng = _header(h, "Range")
        start = int(rng.rsplit("-", 1)[1]) + 1 if code == 308 and rng else 0
    raise Rejected("upload did not finish after retries")


def _reason(raw):
    try:
        err = json.loads(raw).get("error", {})
        return (err.get("errors") or [{}])[0].get("reason") or err.get("message", "")[:200]
    except (ValueError, AttributeError):
        return (raw or b"")[:200].decode(errors="replace")


# the run

def run(http=_http, render=build):
    """Make and upload one Short when due. Returns the video id or None. Never raises: a failed Short is logged and
    counted, never fatal to the publish run."""
    ok, why = due()
    if not ok:
        print(f"shorts: not now ({why})")
        return None
    post = candidates()[0]
    st = _state()
    day = f"{desk.now():%Y-%m-%d}"
    try:
        token = access_token(http)
    except P.Missing as e:
        print(f"shorts: {e}")
        return None
    except Rejected as e:
        print(f"shorts: {e}")
        return None
    with tempfile.TemporaryDirectory() as tmp:
        try:
            mp4, credit = render(post, Path(tmp) / "short.mp4")
            spec = CV.audit_file(mp4, "reel") if Path(mp4).stat().st_size else ["empty file"]
            if spec:
                raise ValueError("; ".join(spec))
        except Exception as e:  # noqa: BLE001
            failures = (st.get("build_failures", 0) if st.get("build_date") == day else 0) + 1
            st.update(build_date=day, build_failures=failures, build_error=f"{post['id']}: {str(e)[-300:]}")
            _save(st)
            print(f"shorts: build failed ({failures}): {str(e)[-200:]}")
            return None
        rec = {"at": desk.now().isoformat(timespec="seconds"), "headline": post["headlines"][0]}
        st.setdefault("attempted", {})[post["id"]] = rec
        _save(st)  # on disk before the upload: never twice
        try:
            vid = upload(mp4, metadata(post, credit), token, http)
        except Exception as e:  # noqa: BLE001
            rec["error"] = str(e)[:300]
            _save(st)
            print(f"shorts: {post['id']} failed, not retried: {rec['error'][:200]}")
            return None
    rec.update(video_id=vid, url=f"https://youtube.com/shorts/{vid}")
    _save(st)
    print(f"shorts: uploaded {post['id']} as {rec['url']}")
    return vid
