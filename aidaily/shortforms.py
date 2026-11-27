"""The structures a YouTube Short can take, so no two Shorts in a row are built the same way.

YouTube's inauthentic-content policy names templated content that gives "the impression of mass production"
(support.google.com/youtube/answer/1311392, read 2026-11-27). So the Short rotates between structures, each one
built from what Boardread made or checked, and runs 20 to 45 seconds:

  story    the headline, two facts from the published dek and body, who reported it
  figure   the story's number set large first, then the headline and a fact
  quote    the headline, then a quoted line from the published copy set as a quote
  know     the headline, "What we know" with the facts, "What we don't know yet" with what the copy says is open
  brief    three of the day's stories in one Short, on black: one headline each, who reported it
  data     the number of the day from official data (ECB, U.S. Treasury, EIA) against its own recent history, with
           a chart drawn here: the highest or lowest in so many weeks, or the biggest daily move

Every sentence on screen is the published copy or a figure from the publisher's own series; the labels and the
framing are ours. Each Short ends on "Full story on boardread.news" (links in Shorts are not clickable).
The beats use the Reel's geometry and safe area (reelcard.py), so the text sits where the picture leaves room.
"""
import math
import re
from datetime import date, timedelta

from . import reelcard as RC
from . import templates as T

MIN_SECONDS, MAX_SECONDS = 20.0, 45.0
END_SECONDS = 2.6
# a post's structures, tried in this order after the one the last Short used; brief and data once a day each
ORDER = ("quote", "know", "figure", "story", "data", "brief")
UNKNOWN = re.compile(r"\b(did not (?:say|disclose|give|specify|comment)|didn't (?:say|disclose)|declined to (?:comment|say|give)|"
                     r"not (?:yet )?(?:disclosed|known|clear)|unclear|has not (?:said|disclosed)|no details|remains to be seen)\b", re.I)
# a quotation of at least six words with someone saying it: a programme or book title in quotes is not a quote
QUOTE = re.compile(r"[“\"]((?:[^”\"\s]+\s+){5,}[^”\"]*)[”\"]")
SAID = re.compile(r"\b(said|says|told|wrote|added|according to|warned|argued)\b", re.I)
GREY = "#9aa0a8"


# beats: the inner HTML of one layer, set in a layout's text box

def label(text):
    return (f'<div style="font-size:34px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:{GREY};'
            f'margin-bottom:28px">{T.e(text)}</div>')


def line(text, size=88, weight=700, lines=6, room=900, min_px=46):
    return RC._fit(text, size, min_px, lines, room, 1.14, weight=weight, track="-0.01em", wrap="pretty")


def big(text, room=330):
    return RC._fit(text, 300, 110, 1, room, 0.95, track="-0.04em", extra="margin-bottom:24px")


def read_seconds(text, lo=3.5, hi=7.0):
    """About as long as it takes to read twice at a phone's pace."""
    return round(min(max(len(text.split()) / 2.6 + 1.2, lo), hi), 2)


# what a post can carry

def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z“\"'])", text or "") if s.strip()]


def quote_of(post):
    """A quoted line from the published dek or body with what surrounds it, as published, or ""."""
    for s in _sentences(post.get("dek", "")) + _sentences(post.get("body", "")):
        if QUOTE.search(s) and SAID.search(s) and len(s) <= 240:
            return s
    return ""


def unknown_of(post):
    """A published sentence that says what is not yet known, or ""."""
    for s in _sentences(post.get("dek", "")) + _sentences(post.get("body", "")):
        if UNKNOWN.search(s) and len(s) <= 220:
            return s
    return ""


def figure_of(post, story):
    """(figure, sentence it is from): the dek's figure the headline lacks, else the headline's own; ("", "")."""
    big_, sentence = RC.fact(story)
    if big_:
        return big_, sentence
    fig = T._headline_figure(story) if story.get("headline") else ""
    return (fig, story["headline"]) if fig else ("", "")


def post_structures(post, story, facts):
    """The post-based structures this post has the material for."""
    out = []
    if len(facts) >= 2:
        out.append("story")
    if facts and figure_of(post, story)[0]:
        out.append("figure")
    if quote_of(post) and facts:
        out.append("quote")
    if unknown_of(post) and facts:
        out.append("know")
    return out


def choose(available, last):
    """The first structure in ORDER that is available and differs from the last Short's; the last one only when
    nothing else is."""
    for name in ORDER:
        if name in available and name != last:
            return name
    return next((n for n in ORDER if n in available), None)


# timelines: [(html, t_in, t_out, kind)], total

def timeline(base, beats, end):
    """beats: [([html, ...], seconds)]. Stretched up to 1.35x to reach MIN_SECONDS, trailing beats dropped past
    MAX_SECONDS; None when even stretched it is too short (the structure is then not used)."""
    while beats and sum(d for _, d in beats) + END_SECONDS > MAX_SECONDS:
        beats = beats[:-1]
    t = sum(d for _, d in beats)
    need = MIN_SECONDS - END_SECONDS
    if t < need:
        if t * 1.35 < need:
            return None
        beats = [(h, math.ceil(d * need / t * 100) / 100) for h, d in beats]  # up, so the total reaches the floor
    pages, t = [(base, 0.0, None, "base")], 0.0
    for htmls, d in beats:
        for h in htmls:
            pages.append((h, t, t + d, "text"))
        t = round(t + d, 2)
    pages.append((end, t, None, "end"))
    return pages, round(t + END_SECONDS, 2)


def post_timeline(name, post, story, layout, facts, outlets):
    """The beats of a post-based structure on layout `layout`."""
    room = RC.room(layout)
    head = ([RC.layer(story, layout, "meta"), RC.layer(story, layout, "head")], 5.0)
    src = ([RC.page(layout, line(f"Reported by {outlets}", 84, room=room))], 2.8) if outlets else None
    fact_beats = [([RC.page(layout, line(f, room=room))], read_seconds(f)) for f in facts]
    if name == "story":
        beats = [head] + fact_beats[:3]
    elif name == "figure":
        fig, sentence = figure_of(post, story)
        if sentence == story["headline"]:  # the headline follows: the number alone first, with its topic
            first = ([RC.page(layout, label(f"The number · {post.get('topic') or 'News'}") + big(fig))], 3.6)
        else:
            first = ([RC.page(layout, label("The number") + big(fig) + line(sentence, 64, 500, 5, room - 420))],
                     read_seconds(sentence, 4.5, 7.5))
        beats = [first, head] + [b for b, f in zip(fact_beats, facts) if f != sentence][:1]
    elif name == "quote":
        q = quote_of(post)
        beats = [head, ([RC.page(layout, label("In their words") + line(q, 80, 500, 7, room - 80))], read_seconds(q, 4.5, 8))]
        beats += [b for b, f in zip(fact_beats, facts) if f != q][:1]
    elif name == "know":
        u = unknown_of(post)
        known = [f for f in facts if f != u][:2]
        beats = [head] + [([RC.page(layout, label("What we know") + line(f, room=room - 80))], read_seconds(f)) for f in known]
        beats.append(([RC.page(layout, label("What we don't know yet") + line(u, room=room - 80))], read_seconds(u)))
    else:
        raise ValueError(name)
    if src:
        beats.append(src)
    return timeline(RC.layer(story, layout, "base"), beats, RC.layer(story, layout, "end"))


def brief_timeline(posts, outlets_of, markets=False):
    """Three of the day's stories on black: a title, then one headline each with who reported it."""
    title = "3 stories moving markets today" if markets else "3 stories to know today"
    room = RC.room("plain")
    from . import desk
    beats = [([RC.page("plain", label(f"{desk.now():%-d %b %Y}") + line(title, 120, 800, 3, 600))], 3.4)]
    for i, p in enumerate(posts[:3], start=1):
        h = p["headlines"][0]
        who = outlets_of(p)
        inner = (label(f"{i} of 3 · {p.get('topic') or 'News'}") + line(h, 104, 800, 5, room - 260, 60)
                 + (f'<div style="margin-top:36px;font-size:34px;color:{GREY}">Reported by {T.e(who)}</div>' if who else ""))
        beats.append(([RC.page("plain", inner)], read_seconds(h, 5.0, 7.0)))
    story = {"end_line": "Full stories on"}
    return title, timeline(RC.layer(story, "plain", "base"), beats, RC.layer(story, "plain", "end"))


# the number of the day

def data_pick(m, used=(), today=None, max_age_days=4):
    """(key, why) of the daily series whose latest value stands out most against its own history, or None.
    Stands out: the highest or lowest in at least 20 observations, or a daily move of at least 2 standard deviations.
    A series and date already used, or older than max_age_days, is skipped."""
    from . import markets as M
    today = today or date.today()
    best = None
    for key, pts in (m or {}).get("series", {}).items():
        if key not in M.SERIES or M.SERIES[key][3] == "wb" or len(pts) < 30:
            continue
        d, v = pts[-1]
        if f"{key}-{d}" in used or date.fromisoformat(d) < today - timedelta(days=max_age_days):
            continue
        prior = [x for _, x in pts[:-1]]
        run_hi = next((i for i, x in enumerate(reversed(prior)) if x >= v), len(prior))
        run_lo = next((i for i, x in enumerate(reversed(prior)) if x <= v), len(prior))
        moves = [b - a for a, b in zip(prior, prior[1:])]
        mean = sum(moves) / len(moves)
        sd = (sum((x - mean) ** 2 for x in moves) / len(moves)) ** 0.5 or 1e-9
        z = abs((v - prior[-1]) - mean) / sd
        score, why = 0, None
        if max(run_hi, run_lo) >= 20:
            kind = "high" if run_hi >= run_lo else "low"
            n = max(run_hi, run_lo)
            since = pts[-2 - n][0] if n < len(prior) else None
            score, why = n, (kind, since, n)
        if not why and z >= 2:  # a new high or low says more than "a big move"
            score, why = z * 10, ("move", None, z)
        if why and (best is None or score > best[0]):
            best = (score, key, why)
    return (best[1], best[2]) if best else None


def data_text(m, key, why):
    """(big value, caption, title, source line) for the series, every number from the publisher's series."""
    from . import markets as M
    lab, v, d, ch, pct, pts = M.stat(m, key)
    name = {"ust10": "The 10-year Treasury yield", "ust2": "The 2-year Treasury yield", "brent": "Brent crude",
            "wti": "WTI crude"}.get(key, lab)
    nd = M.SERIES[key][2]
    unit = M.SERIES[key][1]
    word = "up" if ch > 0 else "down" if ch < 0 else "unchanged"
    money = "$" if unit.startswith("$") else ""
    step = "" if ch == 0 else (f" {abs(ch):.{nd}f} points" if unit == "%" else f" {money}{abs(ch):.{nd}f}")
    period = "on the week" if "weekly" in M.SERIES[key][4] else "on the day"
    kind, since, n = why
    if kind == "move":
        tail = "one of its biggest moves in the last few months"
        title = f"{name} {word}{step} to {M.fmt(key, v)}"
    else:
        word2 = "highest" if kind == "high" else "lowest"
        tail = f"the {word2} since {M.dmy(since)}" if since else f"the {word2} in data back to {M.dmy(pts[0][0])}"
        title = f"{name} at {M.fmt(key, v)}, {tail}"
    caption = f"{name}, {M.dmy(d)}: {word}{step} {period}, {tail}."
    src = M.SRC_OF.get(M.SERIES[key][3], "").replace("Source: ", "Data: ").rstrip(".")
    return M.fmt(key, v), caption, title[:100], src


def chart_svg(pts, w=760, h=520):
    """The series as one white line with its first and last date and its low and high: drawn here, no library."""
    from . import markets as M
    vals = [v for _, v in pts]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    xy = [(i * w / (len(vals) - 1), 30 + (h - 60) * (1 - (v - lo) / span)) for i, v in enumerate(vals)]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in xy)
    lx, ly = xy[-1]
    return (f'<svg width="{w}" height="{h + 70}" viewBox="0 0 {w} {h + 70}" style="overflow:visible">'
            f'<line x1="0" y1="{h - 30}" x2="{w}" y2="{h - 30}" stroke="#3a3a3a" stroke-width="2"/>'
            f'<polyline points="{poly}" fill="none" stroke="#fff" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="14" fill="#fff"/>'
            f'<text x="0" y="{h + 40}" fill="{GREY}" font-size="30" font-family="Libre Franklin">{M.dmy(pts[0][0])}</text>'
            f'<text x="{w}" y="{h + 40}" fill="{GREY}" font-size="30" font-family="Libre Franklin" text-anchor="end">{M.dmy(pts[-1][0])}</text>'
            f'</svg>')


def data_timeline(m, key, why, n=90):
    from . import markets as M
    value, caption, title, src = data_text(m, key, why)
    pts = M.stat(m, key)[5][-n:]
    lo, hi = min(v for _, v in pts), max(v for _, v in pts)
    beats = [([RC.page("plain", label("Number of the day") + big(value) + line(caption, 64, 500, 5, 500))], read_seconds(caption, 5, 7.5)),
             ([RC.page("plain", label(f"Last {len(pts)} readings") + chart_svg(pts)
                       + f'<div style="margin-top:20px;font-size:34px;color:{GREY}">Low {M.fmt(key, lo)} · High {M.fmt(key, hi)}</div>')], 6.0),
             ([RC.page("plain", line(src, 84))], 3.0)]
    story = {"end_line": "More numbers on"}
    return title, caption, src, timeline(RC.layer(story, "plain", "base"), beats, RC.layer(story, "plain", "end"))
