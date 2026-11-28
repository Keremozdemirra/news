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

MIN_SECONDS, MAX_SECONDS = 15.0, 45.0  # tighter since 2026-11-27: a beat holds as long as it takes to read
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
    """A figure set large, sized from its length so it never runs past x 880 (a fitted "$3.642" did, under the
    Shorts buttons, gate 2026-11-28): Franklin 800 figures are about 0.62 em wide, the text box 760 px."""
    px = max(72, min(240, int((RC.RIGHT - RC.LEFT) / (0.64 * max(len(text), 1)))))
    return (f'<div style="font-size:{px}px;font-weight:800;line-height:0.95;letter-spacing:-0.04em;white-space:nowrap;'
            f'margin-bottom:24px">{T.t(text)}</div>')


def read_seconds(text, lo=3.0, hi=6.0):
    """About as long as it takes to read once at a phone's pace, with a beat to take it in."""
    return round(min(max(len(text.split()) / 3.2 + 0.9, lo), hi), 2)


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


def ranked(available, last):
    """Every available structure in ORDER, the last Short's moved to the end: the order a run tries them in."""
    return [n for n in ORDER if n in available and n != last] + [n for n in ORDER if n in available and n == last]


def choose(available, last):
    """The first structure in ORDER that is available and differs from the last Short's; the last one only when
    nothing else is."""
    for name in ORDER:
        if name in available and name != last:
            return name
    return next((n for n in ORDER if n in available), None)


# timelines: [(html, t_in, t_out, kind)], total

class Plan(tuple):
    """(pages, total), with .cues: [(t, spoken line)] for the narration, empty when nothing is spoken."""
    cues = ()


def timeline(base, beats, end, say=None, end_said=""):
    """beats: [([html, ...], seconds)] or [([html, ...], seconds, spoken line)]. With `say` (a spoken line -> its
    length in seconds) each beat holds at least as long as its line plus a breath. Then trailing beats are dropped
    past MAX_SECONDS and short ones stretched up to 1.15x to reach MIN_SECONDS; None when even stretched it is too
    short (the structure is then not used)."""
    beats = [(b[0], b[1], b[2] if len(b) > 2 else "") for b in beats]
    end_len = END_SECONDS
    if say:
        from . import voice
        beats = [(h, max(d, say(w) + voice.GAP) if w else d, w) for h, d, w in beats]
        if end_said:
            end_len = max(END_SECONDS, say(end_said) + 0.5)
    while beats and sum(d for _, d, _ in beats) + end_len > MAX_SECONDS:
        beats = beats[:-1]
    t = sum(d for _, d, _ in beats)
    need = MIN_SECONDS - end_len
    if t < need:
        if t * 1.15 < need:
            return None
        beats = [(h, math.ceil(d * need / t * 100) / 100, w) for h, d, w in beats]  # up, so the total reaches the floor
    pages, cues, t = [(base, 0.0, None, "base")], [], 0.0
    for htmls, d, w in beats:
        for h in htmls:
            pages.append((h, t, t + d, "text"))
        if say and w:
            cues.append((round(t + 0.25, 2), w))
        t = round(t + d, 2)
    pages.append((end, t, None, "end"))
    if say and end_said:
        cues.append((round(t + 0.2, 2), end_said))
    plan = Plan((pages, round(t + end_len, 2)))
    plan.cues = cues
    return plan


def stretch(plan, total):
    """The plan running `total` seconds: its text beats and end frame moved in proportion, so a narration that runs
    longer than the beats is never cut off. A plan already long enough is returned as it is."""
    pages, old = plan
    if total <= old:
        return plan
    f = (total - END_SECONDS) / (old - END_SECONDS)
    out = [(h, 0.0 if k == "base" else round(a * f, 2), None if b is None else round(b * f, 2), k) for h, a, b, k in pages]
    new = Plan((out, round(total, 2)))
    new.cues = [(round(t * f, 2), w) for t, w in getattr(plan, "cues", ())]
    return new


def narrated_timeline(story, layout, timed, secs):
    """The Short as its narration says it: the headline and meta line on screen from the first frame while the first
    sentence is spoken, then each later sentence set on screen as it starts, and the end frame half a second after
    the voice stops. timed: [(sentence, start seconds)] from voice.Narrator.say_timed."""
    room = RC.room(layout)
    end_at = round(secs + 0.5, 2)
    starts = [round(t, 2) for _, t in timed] + [end_at]
    pages = [(RC.layer(story, layout, "base"), 0.0, None, "base")]
    first_out = starts[1] if len(timed) > 1 else end_at
    pages += [(RC.layer(story, layout, "meta"), 0.0, first_out, "text"), (RC.layer(story, layout, "head"), 0.0, first_out, "text")]
    for (sent, _), a, b in zip(timed[1:], starts[1:-1], starts[2:]):
        pages.append((RC.page(layout, line(sent, 84, 700, 6, room)), a, max(b, a + 1.2), "text"))
    pages.append((RC.layer(story, layout, "end"), end_at, None, "end"))
    plan = Plan((pages, round(end_at + END_SECONDS, 2)))
    plan.cues = []
    return plan


def post_timeline(name, post, story, layout, facts, outlets, say=None):
    """The beats of a post-based structure on layout `layout`; `say` sizes the beats to a narration of the same words."""
    room = RC.room(layout)
    head = ([RC.layer(story, layout, "meta"), RC.layer(story, layout, "head")], 4.0, story["headline"])
    src = ([RC.page(layout, line(f"Reported by {outlets}", 84, room=room))], 2.8, f"Reported by {outlets}.") if outlets else None
    fact_beats = [([RC.page(layout, line(f, room=room))], read_seconds(f), f) for f in facts]
    # a structure without its material is refused (build() then falls back to story), never shown half empty
    if (name == "know" and not unknown_of(post)) or (name == "quote" and not quote_of(post)) or \
            (name == "figure" and not figure_of(post, story)[0]):
        return None
    if name == "story":
        beats = [head] + fact_beats[:3]
    elif name == "figure":
        fig, sentence = figure_of(post, story)
        if sentence == story["headline"]:
            # the number with the headline under it in one frame: the claim and its figure land together, and the
            # opening frame has no empty band (the number alone left 25% of it empty)
            first = ([RC.page(layout, label(f"The number · {post.get('topic') or 'News'}") + big(fig)
                              + line(sentence, 96, 800, 4, room - 420, 56))], read_seconds(sentence, 4.5, 6.5), sentence)
            beats = [first] + [b for b, f in zip(fact_beats, facts) if f != sentence][:2]
        else:
            first = ([RC.page(layout, label("The number") + big(fig) + line(sentence, 80, 500, 5, room - 420, 50))],
                     read_seconds(sentence, 4.5, 7.5), sentence)
            beats = [first, head] + [b for b, f in zip(fact_beats, facts) if f != sentence][:1]
    elif name == "quote":
        q = quote_of(post)
        beats = [head, ([RC.page(layout, label("In their words") + line(q, 80, 500, 7, room - 80))], read_seconds(q, 4.5, 8), q)]
        beats += [b for b, f in zip(fact_beats, facts) if f != q][:1]
    elif name == "know":
        u = unknown_of(post)
        known = [f for f in facts if f != u][:2]
        beats = [head] + [([RC.page(layout, label("What we know") + line(f, room=room - 80))], read_seconds(f),
                           ("What we know. " if i == 0 else "") + f) for i, f in enumerate(known)]
        beats.append(([RC.page(layout, label("What we don't know yet") + line(u, room=room - 80))], read_seconds(u),
                      f"What we don't know yet. {u}"))
    else:
        raise ValueError(name)
    if src:
        beats.append(src)
    return timeline(RC.layer(story, layout, "base"), beats, RC.layer(story, layout, "end"), say,
                    "Full story on boardread.news.")


def brief_timeline(posts, outlets_of, markets=False, say=None):
    """Three of the day's stories on black: a title, then one headline each with who reported it."""
    title = "3 stories moving markets today" if markets else "3 stories to know today"
    room = RC.room("plain")
    from . import desk
    # the opening frame is the one the visual gate measures (an empty band deeper than 15% fails): the title fills it
    beats = [([RC.page("plain", label(f"{desk.now():%-d %b %Y}") + line(title, 190, 800, 4, room - 120, 90))], 3.4, title + ".")]
    for i, p in enumerate(posts[:3], start=1):
        h = p["headlines"][0]
        who = outlets_of(p)
        inner = (label(f"{i} of 3 · {p.get('topic') or 'News'}") + line(h, 104, 800, 5, room - 260, 60)
                 + (f'<div style="margin-top:36px;font-size:34px;color:{GREY}">Reported by {T.e(who)}</div>' if who else ""))
        beats.append(([RC.page("plain", inner)], read_seconds(h, 5.0, 7.0), h))
    story = {"end_line": "Full stories:"}
    return title, timeline(RC.layer(story, "plain", "base"), beats, RC.layer(story, "plain", "end"), say,
                           "Full stories on boardread.news.")


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


def data_timeline(m, key, why, n=90, say=None):
    from . import markets as M
    value, caption, title, src = data_text(m, key, why)
    pts = M.stat(m, key)[5][-n:]
    lo, hi = min(v for _, v in pts), max(v for _, v in pts)
    beats = [([RC.page("plain", label("Number of the day") + big(value) + line(caption, 92, 500, 6, 640, 60))],
              read_seconds(caption, 5, 7.5), caption),
             ([RC.page("plain", label(f"Last {len(pts)} readings") + chart_svg(pts)
                       + f'<div style="margin-top:20px;font-size:34px;color:{GREY}">Low {M.fmt(key, lo)} · High {M.fmt(key, hi)}</div>')], 6.0,
              f"Over the last {len(pts)} readings, the low was {M.fmt(key, lo)} and the high {M.fmt(key, hi)}."),
             ([RC.page("plain", line(src, 84))], 3.0, src + ".")]
    story = {"end_line": "More numbers:"}
    return title, caption, src, timeline(RC.layer(story, "plain", "base"), beats, RC.layer(story, "plain", "end"), say,
                                         "More numbers on boardread.news.")
