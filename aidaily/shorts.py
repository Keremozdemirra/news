"""YouTube Shorts: one top story as a 9:16 video, uploaded to the channel, switched by growth.shorts.

The Short is the video card's Reel shape carried further: the story's own licensed photo moves full-bleed behind
the card text (cardvideo.py), then the same picture carries one or two sentences from the published dek and body,
the outlets the story was reported from, and an end frame with the site. Every word on screen was already published
and checked on the story page: the video adds no new claim. When a vetted archive clip fits the headline
(broll.py), it plays behind the text instead, labelled "Archive footage, not from this event". No generated imagery,
the description carries "Written by AI from the sources listed" (growth.shorts_ai_line, Kerem 2026-11-27) and
containsSyntheticMedia is set as the conservative disclosure; photo and footage are real.

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
                        "kind": post.get("photo_kind") or "photo", "alt": ""}}


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
    # a clip shorter than the Short opens it and hands over to the moving photo; a clip a Short or a feed video
    # used in the last day goes last (broll.MAX_SAME_DAY)
    cut = desk.now() - timedelta(hours=24)
    used = [v["footage"] for v in _state().get("attempted", {}).values()
            if v.get("footage") and v.get("at") and _dt(v["at"]) > cut]
    used += [p["video"]["footage"]["id"] for p, _ in desk.posts()
             if (p.get("video") or {}).get("footage") and (desk._stamp(p.get("created", "")) or cut) > cut]
    clip = broll.pick(post["headlines"][0], used=used, min_seconds=min(seconds, 8), seed=post["id"])
    if not clip:
        return None
    ok, why = broll.still_ok(clip)
    if not ok:
        print(f"shorts: footage {clip['id']} skipped: {why}")
        return None
    return clip


def narrator(folder, narrate=None, voice_id=None, post=None):
    """A voice.Narrator when narration is on (growth.shorts_voice, or narrate=True for a sample) and a key is set;
    else None, and the Short stays silent."""
    from . import voice
    if not (voice.on() if narrate is None else narrate):
        return None
    if narrate is None:  # the plan's monthly credit: shorts_voice_per_day narrated Shorts a day, the rest silent
        day = f"{desk.now():%Y-%m-%d}"
        done = sum(1 for v in _state().get("attempted", {}).values() if v.get("narrated") and (v.get("at") or "").startswith(day))
        if done >= int(cfg("shorts_voice_per_day", 1)):
            return None
    key = voice.api_key()
    if not key:
        print("shorts: narration on but no ElevenLabs key; silent Short")
        return None
    if voice_id:  # a sample with a named voice: no plan check, no rotation
        return voice.Narrator(folder, key, voice_id)
    if not voice.credits_ok(key):
        return None
    last = next((v.get("voice") for v in sorted(_state().get("attempted", {}).values(), key=lambda v: v.get("at", ""),
                                                 reverse=True) if v.get("voice")), None)
    name, vid = voice.choose_voice(post or {}, last)
    return voice.Narrator(folder, key, vid, name=name)


def build(post, out_mp4, fetch=True, clip=None, structure="story", avoid=None, info=None, narrate=None, voice_id=None,
          script=None):
    """Render a post-based Short in `structure` (shortforms.py). Returns (path, credit); raises when the post cannot
    be one or a tool fails. With a clip (choose_footage) the archive footage replaces the moving photo and its credit
    replaces the photo's. The text goes where the picture leaves room (reelcard layouts); `avoid` is the last Short's
    layout. info, when given, receives the structure, layout and length used."""
    from . import reelcard as RC
    from . import shortforms as SF
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found")
    if not post.get("photo_file") or not V.photo_ok({"credit": post.get("credit", "")}):
        raise ValueError("no photo under CC0, CC BY or public domain")
    out_mp4 = Path(out_mp4)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        photo, credit = source_photo(post, tmp / "photo.jpg", fetch)
        if not V.photo_ok({"credit": credit}):
            raise ValueError("photo licence does not allow an edited video")
        story = story_from(post, photo, credit)
        why = CV.eligible(story)
        if why:
            raise ValueError(why)
        clip = clip if clip is not None else choose_footage(post, SF.MAX_SECONDS, fetch)
        footage = None
        if clip:
            from . import broll
            try:
                footage = broll.fetch(clip, tmp / "clip.mp4", min(broll.usable(clip), SF.MAX_SECONDS))
                story, credit = CV.with_footage(story, clip), broll.credit(clip)
            except Exception as e:  # noqa: BLE001  no footage this time: the photo moves instead
                print(f"shorts: footage {clip['id']} not fetched, photo instead: {str(e)[:160]}")
        layout = CV.reel_layout(story, post["id"], footage=bool(footage), avoid=avoid)
        plan = None
        for name in dict.fromkeys([structure, "story"]):
            plan = SF.post_timeline(name, post, story, layout, facts(post, 3), outlets_line(post))
            if plan:
                structure = name
                break
        if not plan:
            raise ValueError("not enough published copy for a 20-second Short")
        # narration: a spoken script (spoken.py), never the screen text read out; a script that fails its gate, or a
        # refused voice, leaves the Short silent
        nar, voice_cues = narrator(tmp, narrate, voice_id, post), None
        if nar:
            try:
                from . import spoken
                text, problems = (script, []) if script else spoken.write(post)
                if problems:
                    raise ValueError("script failed its gate: " + "; ".join(problems)[:200])
                f, secs, timed = nar.say_timed(text)
                # the screen follows the voice: each spoken sentence appears as it is said (word timings from
                # ElevenLabs), the headline holds while the first one is spoken
                plan = SF.narrated_timeline(story, layout, timed, secs + 0.15)
                voice_cues = [(0.15, f)]
            except Exception as e:  # noqa: BLE001
                print(f"shorts: narration skipped, silent Short: {str(e)[:200]}")
                nar = None
        fx, fy = CV.reel_focus(story)[:2] if not footage else (0.5, 0.5)
        cover_html = None
        if desk.growth("hook_covers") and narrate is not False:
            from . import covers
            try:
                cover_html = covers.make_cover(post, story, photo)
            except Exception as e:  # noqa: BLE001  a cover failure costs the cover, never the Short
                print(f"shorts: no cover: {str(e)[:160]}")
        try:
            CV.build_sequence(out_mp4, CV.with_cover(plan[0], cover_html), plan[1], RC.GEO[layout]["band"], photo=photo,
                              focus_xy=(fx, fy), footage=footage, voice=voice_cues)
        except CV.GateFail as e:
            if layout == "plain":
                raise
            # the visual gate refused a frame: the same Short set on black, its timing kept for the voice
            print(f"shorts: gate failed in {layout} ({str(e)[:160]}); set on black instead")
            layout = "plain"
            if voice_cues:
                plan = SF.narrated_timeline(story, layout, timed, secs + 0.15)
            else:
                again = SF.post_timeline(structure, post, story, layout, facts(post, 3), outlets_line(post))
                plan = SF.stretch(again, plan[1]) if again else plan
            CV.build_sequence(out_mp4, CV.with_cover(plan[0], cover_html), plan[1], RC.GEO[layout]["band"], photo=photo,
                              focus_xy=(fx, fy), footage=footage, voice=voice_cues)
        total = plan[1]
    if info is not None:
        info.update(structure=structure, layout=layout, seconds=total, narrated=bool(nar), hook_cover=bool(cover_html),
                    **({"voice": nar.name} if nar and nar.name else {}))
    return out_mp4, credit


def build_plain(job, out_mp4, narrate=None, voice_id=None, info=None):
    """Render a Short with no photo (the brief and the number of the day). Returns (path, "")."""
    from . import shortforms as SF

    def make(say):
        if job["structure"] == "brief":
            return SF.brief_timeline(job["posts"], outlets_line, job["markets"], say=say)[1]
        return SF.data_timeline(job["m"], job["series"], job["why"], say=say)[3]
    with tempfile.TemporaryDirectory() as tmp:
        # no spoken script exists yet for the brief and the number of the day; reading the screen text out sounded
        # generated (Kerem, 2026-11-27), so they stay silent
        nar, plan = None, make(None)
        if not plan:
            raise ValueError("too short")
        pages, total = plan
        CV.build_sequence(out_mp4, pages, total, (0, 0), voice=nar.cues(plan.cues) if nar else None)
    if info is not None:
        info["narrated"] = bool(nar)
    return Path(out_mp4), ""


def entities_clean(credit):
    from . import entities
    return entities.clean_credit(credit)


# metadata

def _clean(s):
    return re.sub(r"[<>]", "", s or "").strip()


TITLE_TARGET = 60  # characters: the whole title shows under a Short on a phone; the news, never a teaser
COMMA = re.compile(r",\s|;\s")
CLAUSE = re.compile(r"\s(?:as|after|amid|while|despite|with|over|following|ahead of|before)\s", re.I)
PHRASE = re.compile(r"\s(?:to|in|for|on|at|by|from|into|against)\s", re.I)


def title(post):
    """The headline as the title, at most TITLE_TARGET characters: when it is longer, the main clause before a trailing
    "as ...", "after ...", ", ..." (what happened, without the context); failing that, cut at a word."""
    t = _clean(post["headlines"][0])
    if len(t) <= TITLE_TARGET:
        return t
    # an aside between two commas goes first: "Hamas says Izzeldeen al-Hayya, son of its chief, survived Israeli
    # strike" keeps its verb as "Hamas says Izzeldeen al-Hayya survived Israeli strike"
    m = re.search(r",\s[^,]{3,40},\s", t)
    if m and len(t) - len(m.group(0)) + 1 <= TITLE_TARGET:
        return (t[:m.start()] + " " + t[m.end():]).strip()
    # then a comma ("..., this time with bacteria" must not leave ", this time"), a linking word, a phrase
    for pattern in (COMMA, CLAUSE, PHRASE):
        cuts = [m.start() for m in pattern.finditer(t) if 20 <= m.start() <= TITLE_TARGET]
        if cuts:
            return t[:max(cuts)].rstrip(",;: ")
    return t[:TITLE_TARGET - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def hashtags(post):
    """#Shorts, the topic and, when the story names one, the company or person: YouTube shows up to three
    description hashtags above the title (support.google.com/youtube/answer/6390658)."""
    topic = re.sub(r"[^A-Za-z0-9]", "", (desk.CONFIG.get("bluesky_topic_tags") or {}).get(post.get("topic") or "", "")
                   or post.get("topic") or "")
    who = re.sub(r"[^A-Za-z0-9]", "", "".join(w[:1].upper() + w[1:] for w in (post.get("company") or post.get("person") or "").split()))
    return " ".join(x for x in ("#Shorts", f"#{topic}" if topic else "", f"#{who}" if 2 < len(who) < 30 else "") if x)


def description(post, credit):
    """The news sentence first (it is what shows under the Short), then who reported it, then the link to the full
    story and sources, then the photo credit and the hashtags; the AI line closes it (_fit_description)."""
    news = _clean(post.get("dek")) or _clean(post["headlines"][0])
    lines = [news]
    if outlets_line(post):
        lines.append(f"Reported by {outlets_line(post)}.")
    lines += ["", f"Full story and sources: {desk.story_url(post['id'], 'youtube')}"]
    if credit:
        from . import entities
        credit = entities.clean_credit(credit)
        edited = re.search(r"\bCC BY\b", credit) and not credit.endswith("Edited")
        lines += ["", _clean(credit) + (". Edited" if edited else "")]
    lines += ["", hashtags(post)]
    return _fit_description("\n".join(lines).strip())


def _fit_description(text):
    """Within DESCRIPTION_MAX bytes, then the AI line as the quiet last line (Kerem, 2026-11-27): the body gives way, never the line."""
    tail = f"\n\n{AI_LINE}" if cfg("shorts_ai_line", False) else ""
    while len((text + tail).encode("utf-8")) > DESCRIPTION_MAX:
        text = text[:-50]
    return text + tail


# Kerem's decision, 2026-11-27: YouTube descriptions say it, in these words (growth.shorts_ai_line)
AI_LINE = "Written by AI from the sources listed."


def metadata(post, credit):
    """The videos resource for insert. containsSyntheticMedia is set although the pictures are real: the text is
    written by AI, and the flag is the conservative choice (YouTube says it does not limit reach,
    support.google.com/youtube/answer/14328491)."""
    tags = [x for x in (post.get("topic"), "business news", "news") if x]
    return {"snippet": {"title": title(post), "description": description(post, credit), "categoryId": NEWS_CATEGORY,
                        "tags": tags, "defaultLanguage": "en", "defaultAudioLanguage": "en"},
            "status": _status()}


def _status():
    return {"privacyStatus": cfg("shorts_privacy", "public"), "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True, "embeddable": True}


def _resource(title_, lines):
    text = _fit_description("\n".join(lines).strip())
    return {"snippet": {"title": _clean(title_)[:TITLE_MAX], "description": text, "categoryId": NEWS_CATEGORY,
                        "tags": ["business news", "news", "markets"], "defaultLanguage": "en", "defaultAudioLanguage": "en"},
            "status": _status()}


def home_url():
    url = desk.CONFIG["site_url"] + "/"
    return url + ("?utm_source=youtube&utm_medium=social" if desk.growth("utm") else "")


def metadata_job(job, credit=""):
    """The videos resource for any Short: the post's own, or the brief's and the number of the day's."""
    if job["structure"] == "brief":
        from . import shortforms as SF
        title_, _ = SF.brief_timeline(job["posts"], outlets_line, job["markets"])
        lines = [f"Full stories and sources: {home_url()}", ""]
        for i, p in enumerate(job["posts"][:3], start=1):
            lines += [f"{i}. {_clean(p['headlines'][0])}", f"   Reported by {outlets_line(p)}. {desk.story_url(p['id'], 'youtube')}"]
        return _resource(f"{title_}: {_clean(job['posts'][0]['headlines'][0])}", lines + ["", "#Shorts #BusinessNews #Markets"])
    if job["structure"] == "data":
        from . import shortforms as SF
        title_, caption, src, _ = SF.data_timeline(job["m"], job["series"], job["why"])
        url = desk.CONFIG["site_url"] + "/numbers/" + ("?utm_source=youtube&utm_medium=social" if desk.growth("utm") else "")
        return _resource(title_, [f"More numbers: {url}", "", caption, f"{src}. Chart drawn by Boardread from the published series.",
                                  "", "#Shorts #Markets #Economy"])
    return metadata(job["post"], credit)


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


def brief_pool():
    """(posts, markets): up to three of the last 12 hours' social stories for the brief, markets ones when there are
    three, else the top three of any topic."""
    since = desk.now() - timedelta(hours=12)
    floor = float(desk.CONFIG.get("social_min_score", 0) or 0)
    rows, seen = [], set()
    for p, _ in desk.posts():
        if p.get("status") not in ("published", "web") or p.get("kind") in desk.NO_CROSSPOST or not desk.social_allowed(p):
            continue
        when = _dt(p["published"]) if p.get("published") else None
        if not when or when < since or (p.get("score") or 0) < floor or _norm(p["headlines"][0]) in seen:
            continue
        seen.add(_norm(p["headlines"][0]))
        rows.append(p)
    rows.sort(key=lambda p: (p.get("score") or 0, p.get("published", "")), reverse=True)
    mk = [p for p in rows if p.get("topic") in ("Markets", "Economy", "Business")]
    return (mk[:3], True) if len(mk) >= 3 else (rows[:3], False)


def _light_story(post):
    return story_from(post, Path("photo.jpg"), post.get("credit", ""))


def plan_jobs(st=None):
    """The Shorts this run may make, in the order to try them: every structure (shortforms.ORDER) that has the
    material, the last Short's at the end, a structure that failed three times today left out, and the plain
    single-story Short of the top candidate last of all. The brief and the number of the day run once a day each."""
    from . import shortforms as SF
    st = st or _state()
    day = f"{desk.now():%Y-%m-%d}"
    avail = {}
    cands = candidates()
    if cands:
        p = cands[0]
        for name in SF.post_structures(p, _light_story(p), facts(p, 3)):
            avail[name] = {"structure": name, "key": p["id"], "post": p}
    if st.get("data_day") != day:
        from . import markets as M
        m = M.load(live=False)
        pick = SF.data_pick(m, used=set(st.get("data_used", [])), today=desk.now().date()) if m else None
        if pick:
            key, why = pick
            d = m["series"][key][-1][0]
            avail["data"] = {"structure": "data", "key": f"data-{key}-{d}", "m": m, "series": key, "why": why}
    if st.get("brief_day") != day:
        posts, markets = brief_pool()
        if len(posts) == 3:
            avail["brief"] = {"structure": "brief", "key": f"brief-{day}", "posts": posts, "markets": markets}
    jobs = [avail[n] for n in SF.ranked(avail, st.get("last_structure")) if not structure_blocked(st, n)]
    if cands and not any(j.get("post") for j in jobs) and not structure_blocked(st, "story"):
        # the last resort: the plain single-story Short of the top candidate, which the gate then sets on black
        jobs.append({"structure": "story", "key": cands[0]["id"], "post": cands[0]})
    return jobs


def structure_blocked(st, name, limit=3):
    """A structure that failed `limit` times today is not tried again today; the others still are."""
    day = f"{desk.now():%Y-%m-%d}"
    return ((st.get("failures") or {}).get(day) or {}).get(name, 0) >= limit


def note_failure(st, name, why):
    day = f"{desk.now():%Y-%m-%d}"
    st["failures"] = {day: {**((st.get("failures") or {}).get(day) or {})}}  # only today's counts are kept
    st["failures"][day][name] = st["failures"][day].get(name, 0) + 1
    st["build_error"] = f"{name}: {str(why)[-300:]}"


def plan_next(st=None):
    """The first job plan_jobs() would try, or None."""
    jobs = plan_jobs(st)
    return jobs[0] if jobs else None


def today_count(st=None):
    day = f"{desk.now():%Y-%m-%d}"
    return sum(1 for v in (st or _state()).get("attempted", {}).values() if (v.get("at") or "").startswith(day))


# when the two Shorts go out (UTC): Europe's evening and America's evening. Evening local time is the playbook's
# default until Studio data says otherwise (Buffer's best-time study is a correlation: buffer.com, read 2026-11-27).
WINDOWS = [[16, 19], [22, 25]]


def in_window(now=None):
    """Inside one of growth.shorts_windows: [start hour, end hour) in UTC, an end past 24 running into the next day."""
    h = (now or desk.now()).hour
    for a, b in cfg("shorts_windows", WINDOWS):
        if a <= h < b or (b > 24 and h < b - 24):
            return True
    return False


def due():
    """(True, "") when a Short should be made now, else (False, why)."""
    if not desk.growth("shorts"):
        return False, "switch off"
    if desk.paused():
        return False, "paused"
    st = _state()
    if not in_window():
        return False, "outside the posting windows"
    if today_count(st) >= per_day():
        return False, "daily cap reached"
    last = max((v.get("at", "") for v in st.get("attempted", {}).values()), default="")
    # the spacing floor plus a fixed 0..30 minutes drawn from the last upload, so Shorts do not land on a beat
    wait = int(cfg("shorts_spacing_minutes", 180)) + desk.zlib.crc32(last.encode()) % 31 if last else 0
    if last and _dt(last) > desk.now() - timedelta(minutes=wait):
        return False, "spacing"
    if not plan_next(st):
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
    st = _state()
    jobs = plan_jobs(st)
    day = f"{desk.now():%Y-%m-%d}"
    try:
        token = access_token(http)
    except P.Missing as e:
        print(f"shorts: {e}")
        return None
    except Rejected as e:
        print(f"shorts: {e}")
        return None
    last_layout = next((v.get("layout") for v in sorted(st.get("attempted", {}).values(), key=lambda v: v.get("at", ""),
                                                          reverse=True) if v.get("layout")), None)
    with tempfile.TemporaryDirectory() as tmp:
        # one structure failing (the gate refusing a frame, a render error) never stops the run: the next structure
        # is tried, the plain single-story Short last; failures are counted per structure (a refused brief at 00:00
        # stopped every Short on 28 Nov when they were counted per day)
        mp4 = job = None
        for job in jobs:
            post, info, clip = job.get("post"), {"structure": job["structure"]}, None
            try:
                out = Path(tmp) / f"short-{job['structure']}.mp4"
                if not post:
                    mp4, credit = build_plain(job, out, info=info)
                    info["layout"] = "plain"
                elif render is build:
                    from . import shortforms as SF
                    clip = choose_footage(post, SF.MAX_SECONDS)
                    mp4, credit = build(post, out, clip=clip, structure=job["structure"], avoid=last_layout, info=info)
                else:
                    mp4, credit = render(post, out)
                spec = CV.audit_file(mp4, "reel") if Path(mp4).stat().st_size else ["empty file"]
                if spec:
                    raise ValueError("; ".join(spec))
                break
            except Exception as e:  # noqa: BLE001
                note_failure(st, job["structure"], e)
                if isinstance(e, CV.GateFail):
                    st.setdefault("gate_skipped", {})[job["key"]] = str(e)[:200]
                _save(st)
                print(f"shorts: {job['structure']} failed, trying the next: {str(e)[-200:]}")
                mp4 = None
        if mp4 is None:
            print("shorts: every structure failed this run")
            return None
        headline = post["headlines"][0] if post else metadata_job(job)["snippet"]["title"]
        rec = {"at": desk.now().isoformat(timespec="seconds"), "headline": headline, "structure": info["structure"],
               **({"narrated": True, "voice": info.get("voice", "")} if info.get("narrated") else {}),
               **({"hook_cover": True} if info.get("hook_cover") else {}),
               **({"layout": info["layout"]} if info.get("layout") else {}), **({"footage": clip["id"]} if clip else {})}
        st.setdefault("attempted", {})[job["key"]] = rec
        st["last_structure"] = info["structure"]
        if job["structure"] == "data":
            st["data_day"] = day
            st.setdefault("data_used", []).append(job["key"][5:])
            st["data_used"] = st["data_used"][-60:]
        if job["structure"] == "brief":
            st["brief_day"] = day
        _save(st)  # on disk before the upload: never twice
        try:
            vid = upload(mp4, metadata_job(job, credit), token, http)
        except Exception as e:  # noqa: BLE001
            rec["error"] = str(e)[:300]
            _save(st)
            print(f"shorts: {job['key']} failed, not retried: {rec['error'][:200]}")
            return None
    rec.update(video_id=vid, url=f"https://youtube.com/shorts/{vid}")
    _save(st)
    print(f"shorts: uploaded {job['key']} ({info['structure']}) as {rec['url']}")
    return vid
