"""The three views of the same news, and the ritual pages, built on top of the article pages in site.py.

  /               Broadsheet: the main edition (masthead, lead with its text, columns, rates, sections)
  /board/         The Board: a departure-board river, the Names tape and the Wire (articles against newsrooms)
  /feed/          The Feed, printed: a mosaic of cards, photo cards with a scrim and text cards for articles without a photo
  /cover/         the weekly cover, one 4:5 card for the latest week
  /numbers/       the figures in the news beside the official rate series
  /paper/         Yesterday's paper: a six-page edition you turn, and /paper/YYYY-MM-DD/ for every edition

Everything is made from the same published posts; nothing here invents a figure or a name. Pages that need a script name it
(paper.js) and work as plain pages without it.
"""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import markets, outlets
from . import site as S

E = S.E
CODE = {"Business": "BUS", "Economy": "ECO", "Markets": "MKT", "Politics": "POL", "World": "WLD", "Tech": "TEC", "AI": "AI", "Culture": "CUL"}
PLURAL = lambda n, w: f"{n} {w}{'' if n == 1 else 's'}"  # noqa: E731


def nroom(p):
    return PLURAL(S.coverage(p), "newsroom")


def mt(p):
    """Topic, time and newsrooms in the small caps line above a headline."""
    return f'{E(S.topic(p))} &middot; <time datetime="{S.iso(p["published"])}">{S.hhmm(p["published"])}</time> UTC &middot; {nroom(p)}'


def img(p, ratio="3/2", thumb=True):
    if not p.get("_thumb"):
        return ""
    src = f"{S.BASE}/img/{p['id']}-t.jpg" if thumb or not p.get("_hires") else f"{S.BASE}/img/{p['id']}.jpg"
    w, h = (480, 320) if thumb or not p.get("_hires") else (960, 640)
    return f'<img src="{src}" width="{w}" height="{h}" alt="" loading="lazy" decoding="async" style="aspect-ratio:{ratio}">'


def card(p, size="s", photo=False, dek=True, ratio="3/2"):
    """One column item of the broadsheet: a line of caps, the condensed headline, and optionally photo and dek."""
    return (f'<article class="it {size}"><a href="{S.href(p)}">{img(p, ratio) if photo else ""}<div class="mt">{mt(p)}</div>'
            f'<h3 class="hl">{E(p["headlines"][0])}</h3></a>' + (f'<p>{E(p.get("dek", ""))}</p>' if dek else "") + "</article>")


def paras(p):
    return "".join(f"<p>{E(x)}</p>" for x in (p.get("body") or "").split("\n") if x.strip())


def seats(p, cls="mtr"):
    """Six seats, filled for each newsroom that reported the article; the scale stays faint."""
    n = S.coverage(p)
    return (f'<span class="{cls}" role="img" aria-label="Reported by {PLURAL(n, "newsroom")}">'
            + "".join(f'<i class="on"></i>' if k < n else "<i></i>" for k in range(S.COVER_TICKS)) + "</span>")


def head(kicker, title, sub=""):
    return (f'<div class="vh"><div class="cap dm">{kicker}</div><h1 class="cd">{title}</h1>'
            + (f'<p class="vsub">{sub}</p>' if sub else "") + "</div>")


def age_attr(p):
    """What the script turns into "2h 14m ago"; without it the reader sees the date."""
    return f'<time class="age" datetime="{S.iso(p["published"])}" data-age>{S.dt(p["published"]).strftime("%-d %b")}</time>'


# ---------------------------------------------------------------- front page

def front(shown, cos, m):
    today = S.window(shown)
    ranked = S.by_score(today)
    lead = next((p for p in ranked if p.get("_hires")), ranked[0]) if ranked else None
    rest = [p for p in ranked if p is not lead]
    used = {lead["id"]}
    left = [p for p in shown if p is not lead][:6]
    top2 = [p for p in rest if p not in left][:2] or rest[:2]
    used |= {p["id"] for p in left} | {p["id"] for p in top2}
    jump = (f'<a class="jump cap" href="{S.href(lead)}">Full article &middot; {PLURAL(S.coverage(lead), "newsroom")}: '
            f'{S.by(lead)}</a>')
    fig = (f'<figure><img src="{S.BASE}/img/{lead["id"]}.jpg" width="960" height="640" alt="" fetchpriority="high">'
           f'<figcaption>{E(lead.get("credit", ""))}</figcaption></figure>') if lead.get("_hires") else ""
    centre = (f'<div class="zn lead"><div class="cap k">{E(S.topic(lead))} &middot; <time datetime="{S.iso(lead["published"])}">{S.hhmm(lead["published"])}</time> UTC</div>'
              f'<h1 class="lh"><a href="{S.href(lead)}" class="hl">{E(lead["headlines"][0])}</a></h1><p class="dk">{E(lead.get("dek", ""))}</p>'
              f'<div class="by cap dm"><span>By the Boardread desk (AI)</span><span>{S.cover(lead)}</span></div>{fig}'
              f'<div class="tx">{paras(lead)}</div>{jump}</div>')
    ltitle = "Latest"
    lcol = (f'<div class="zn"><div class="sec cap"><span>{ltitle}</span><a class="dm" href="{S.BASE}/latest/">All</a></div>'
            + "".join(card(p, "s", photo=(i in (0, 3) and bool(p.get("_thumb"))), dek=i < 3) for i, p in enumerate(left)) + S.most_covered_block(shown, cos, 5) + "</div>")
    rcol = (f'<div class="zn"><div class="sec cap"><span>Also at the top</span></div>'
            + "".join(card(p, "m", photo=True, ratio="4/3") for p in top2)
            + markets.rates_box(m, S.BASE) + "</div>")
    blocks = ""
    for t in S.TOPIC_ORDER:
        rows = [p for p in shown if S.topic(p) == t]
        fresh = [p for p in rows if p["id"] not in used] or rows
        if not rows:
            continue
        blocks += (f'<div><div class="sec cap"><a href="{S.BASE}/t/{t.lower()}/">{t}</a><span class="dm">{len(rows)}</span></div>'
                   + "".join(card(p, "m" if k == 0 else "s", photo=(k == 0), dek=(k == 0)) for k, p in enumerate(fresh[:3])) + "</div>")
    inside = "".join(f'<a href="{S.BASE}{u}"><b class="cd">{n}</b><span>{d}</span></a>' for k, u, n, d in (
        ("board", "/board/", "Board", "Every article as a departure, with the names in the news and a wire of who reported what."),
        ("feed", "/feed/", "Feed", "The news as cards, the way it runs on Instagram."),
        ("brief", "/brief/", "Brief", f"The day's top articles, one minute. It ends."),
        ("play", "/play/", "Play", "Three daily games built from today's news."),
        ("numbers", "/numbers/", "Numbers", "The figures in the news, and the official rate series."),
        ("paper", "/paper/", "Paper", "The last full day as a printed edition. Turn the pages."))
        if k in S.SHIPPED or k == "brief")
    week = sorted(S.by_score([p for p in shown if S.dt(shown[0]["published"]) - S.dt(p["published"]) <= timedelta(days=7)]), key=S.shared, reverse=True)
    duo = (f'<div class="duo"><section aria-labelledby="wh">{S.sec_head("This week", f"{S.BASE}/week/", "Top 10").replace("<h2", "<h2 id=\"wh\"", 1)}'
           f'{S.ranked(week, 5)}</section>{S.follow_block()}</div>')
    return ('<p class="since" id="since" role="status" hidden></p>' f'<div class="front">{lcol}{centre}{rcol}</div>'
            f'<div class="sects">{blocks}</div><div class="inside">{inside}</div>{duo}')


# ---------------------------------------------------------------- names

STOP_FIRST = {"The", "A", "An", "In", "On", "At", "As", "After", "Before", "How", "Why", "What", "Who", "When", "New", "More", "Most", "Is", "Are",
              "To", "For", "Of", "And", "But", "With", "By", "From", "Over", "Under", "Its", "His", "Her", "Their", "This", "That", "These", "Those", "Will",
              "He", "She", "They", "It", "We", "You", "I", "Not", "No", "Says", "Say"}
NOT_NAMES = {"U.S", "US", "UK", "EU", "AI", "CEO", "GDP", "UN"}  # places and terms, not the people and companies the tape is for
MONTHS = {"January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December",
          "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}
CAPSEQ = re.compile(r"\b(?:[A-Z][A-Za-z0-9'’&.-]*)(?:\s+[A-Z][A-Za-z0-9'’&.-]*){0,2}")
_WORDS = None


def english(w):
    global _WORDS
    if _WORDS is None:
        f = S.ASSETS / "words.txt"
        _WORDS = set(f.read_text().split()) if f.exists() else set()
    return w.lower() in _WORDS


def names(shown, n=10):
    """[(name, [articles], pickups)] the people and companies the articles name, most newsroom pickups first.
    A name is a run of capitalised words in a headline or summary, or a company the post is tagged with. A lone word that is
    plain English ("Global") is not a name unless two articles use it; the sentence's first word is skipped for the same reason."""
    found = {}
    for p in shown:
        text = f'{p["headlines"][0]}. {p.get("dek", "")}'
        cands = {S.co_of(p)} - {""}
        for mm in CAPSEQ.finditer(text):
            toks = mm.group(0).split()
            while toks and toks[0] in STOP_FIRST:
                toks = toks[1:]
            toks = [t.rstrip(".'’-") for t in toks]
            if not toks or any(t in MONTHS for t in toks):
                continue
            name = " ".join(toks)
            if len(name) < 3 or name in NOT_NAMES or (len(toks) == 1 and english(name) and name not in cands):
                continue
            cands.add(name)
        for name in cands:
            if re.search(rf"\b{re.escape(name)}\b", f"{text} {p.get('body', '')}"):
                found.setdefault(name, []).append(p)
    out = []
    for name, ps in found.items():
        pick = sum(S.coverage(p) for p in ps)
        if len(ps) >= 2 or pick >= 3:
            out.append((name, ps, pick))
    # a shorter name inside a longer one ("Trump" in "Donald Trump") is the same name: keep the longer
    out = [o for o in out if not any(o[0] != q[0] and re.search(rf"\b{re.escape(o[0])}\b", q[0]) and len(q[1]) >= len(o[1]) for q in out)]
    return sorted(out, key=lambda o: (-o[2], -len(o[1]), o[0]))[:n]


# ---------------------------------------------------------------- the board

def flaps(text, go=False, inv=False):
    cells = "".join(f'<i>{c}</i>' if c in ":." else '<b class="sp"></b>' if c == " " else f'<b style="--k:{k}">{E(c)}</b>' for k, c in enumerate(text))
    return f'<span class="fl{" go" if go else ""}{" inv" if inv else ""}" aria-hidden="true">{cells}</span>'


def board_rows(rows):
    out = ""
    for p in rows:
        big = bool(p.get("_hires")) and S.coverage(p) >= 4
        th = img(p, "3/2") if p.get("_thumb") else '<span class="th"></span>'
        out += (f'<article class="row{" big" if big else ""}"><span class="tm"><time datetime="{S.iso(p["published"])}">{flaps(S.hhmm(p["published"]), go=True)}'
                f'<span class="sr">{S.hhmm(p["published"])} UTC</span></time></span><span class="sc" title="{E(S.topic(p))}">{CODE[S.topic(p)]}</span>'
                f'<div class="ti"><h3><a href="{S.href(p)}">{E(p["headlines"][0])}</a></h3>'
                + (f'<p class="dk">{E(p.get("dek", ""))}</p>' if big else "") + f'</div><span class="src">{S.by(p)}</span>'
                f'<span class="cv">{seats(p)}</span><span class="agec">{age_attr(p)}</span><span class="imgc">{th}</span></article>')
    return out


def matrix(rows, cap=26):
    """Newsrooms (most articles first) against articles: a filled cell where the newsroom reported the article."""
    cols = {}
    for p in rows:
        for n in outlets.newsrooms(p):
            cols.setdefault(n.lower(), [n, 0])[1] += 1
    order = sorted(cols.values(), key=lambda c: (-c[1], c[0]))[:cap]
    th = "".join(f"<th scope=\"col\"><span>{E(n)}</span></th>" for n, _ in order)
    body = ""
    for p in rows:
        have = {n.lower() for n in outlets.newsrooms(p)}
        cells = "".join(f'<td>{f"<i title=\"{E(n)}\"></i><span class=\"sr\">{E(n)}</span>" if n.lower() in have else ""}</td>' for n, _ in order)
        body += (f'<tr><th scope="row"><small>{S.hhmm(p["published"])} &middot; {CODE[S.topic(p)]}</small><a href="{S.href(p)}">{E(p["headlines"][0])}</a></th>{cells}</tr>')
    foot = "".join(f"<td>{c}</td>" for _, c in order)
    hidden = len({n for p in rows for n in outlets.newsrooms(p)}) - len(order)
    note = f'<p class="attr">{hidden} more newsrooms reported one article each and are not shown.</p>' if hidden > 0 else ""
    return (f'<div class="mx" tabindex="0" role="region" aria-label="Articles against newsrooms, scrolls sideways"><table><thead><tr><th><span class="sr">Article</span></th>{th}</tr></thead>'
            f'<tbody>{body}</tbody><tfoot><tr><th scope="row">Articles per newsroom</th>{foot}</tr></tfoot></table></div>{note}')


def board(shown, m):
    rows = S.window(shown, 36)
    rows = rows if len(rows) >= 6 else shown[:20]
    rows = rows[:40]
    top = max(rows, key=lambda p: (S.coverage(p), p.get("score", 0))) if rows else None
    mix = S.seat_list(top) if top else []
    hero = ""
    if top:
        seat_list = "".join((f'<a class="seat full" href="{E(u)}" rel="nofollow noopener" target="_blank"><span class="n">{k:02d}</span><b>{E(o)}</b><span class="go">Original &nearr;</span></a>' if u
                             else f'<div class="seat full"><span class="n">{k:02d}</span><b>{E(o)}</b><span class="go">Reported it</span></div>') for k, (o, u) in enumerate(mix, 1))
        hero = (f'<section class="hero" aria-label="Top of the board"><div class="ph">{img(top, "4/3", thumb=False)}</div><div class="hg"><div>'
                f'<div class="hm">{flaps(S.hhmm(top["published"]), go=True)}<span class="sec">{CODE[S.topic(top)]}</span><span class="cap dm">Top of the board</span></div>'
                f'<h2><a href="{S.href(top)}">{E(top["headlines"][0])}</a></h2><p class="dek">{E(top.get("dek", ""))}</p></div>'
                f'<div class="seatbox"><div class="seatscale">{seats(top, "mtr big")}<span class="cap dm">{PLURAL(S.coverage(top), "seat")} of {S.COVER_TICKS}</span></div>{seat_list}</div></div></section>')
    nm = names(rows)
    tape = "".join(f'<span class="tk">{E(n)}<small>{PLURAL(len(ps), "article")}</small><em>{k}</em></span>' for n, ps, k in nm)
    nrows = "".join(f'<div class="nm-row"><span class="rk">{i:02d}</span><h3>{E(n)}</h3><ul>'
                    + "".join(f'<li><span>{S.hhmm(x["published"])}</span><a href="{S.href(x)}">{E(x["headlines"][0])}</a></li>' for x in ps)
                    + f'</ul><div class="bars"><div><b>{k}</b>newsroom pickups</div><div><b>{len(ps)}</b>{"article" if len(ps) == 1 else "articles"}</div></div></div>'
                    for i, (n, ps, k) in enumerate(nm, 1))
    names_sec = (f'<section id="names" class="bsec"><div class="sec cap"><span>Names</span><span class="dm">People and companies, by newsroom pickups</span></div>'
                 f'<div class="tape" aria-hidden="true"><div class="tape-in">{tape}{tape}</div></div>{nrows}</section>') if nm else ""
    wire = (f'<section id="wire" class="bsec"><div class="sec cap"><span>The wire</span><span class="dm">A filled square: that newsroom reported it</span></div>'
            f'<p class="vsub">Read across to see how widely an article was reported, down to see what a newsroom led with. The wire shows who reported, not when.</p>'
            f'{matrix(rows)}</section>')
    hdr = ('<div class="vh"><div class="cap dm">Departures, newest first</div><h1 class="cd">The Board</h1>'
           f'<p class="vsub">{PLURAL(len(rows), "article")} from {PLURAL(len({n.lower() for p in rows for n in outlets.newsrooms(p)}), "newsroom")}. '
           'Each seat is one newsroom that reported the article.</p>'
           '<nav class="jumps cap" aria-label="On this page"><a href="#river">River</a><a href="#names">Names</a><a href="#wire">Wire</a></nav></div>')
    head_row = '<div class="bh"><span>Time</span><span>Sec</span><span>Headline</span><span>Newsrooms</span><span>Seats</span><span>Age</span><span></span></div>'
    return hdr + hero + f'<section id="river" class="bsec board" aria-label="Departures">{head_row}{board_rows([p for p in rows if p is not top])}</section>' + names_sec + wire


# ---------------------------------------------------------------- the feed and the cover

def tile(p, cls, cols, photo):
    kind = "sc" if photo else ("w" if int(p["id"][-1:] or 0) % 2 else "k")
    media = f'<img src="{S.BASE}/img/{p["id"]}{"" if cls in ("xl", "l") and p.get("_hires") else "-t"}.jpg" width="{960 if cls in ("xl", "l") else 480}" height="{640 if cls in ("xl", "l") else 320}" alt="" loading="{"eager" if cls == "xl" else "lazy"}" decoding="async">' if photo else ""
    return (f'<a class="tile {cls} {kind}" style="--cols:{cols}" href="{S.href(p)}">{media}<span class="in"><span class="tg">{E(S.topic(p))} &middot; {S.hhmm(p["published"])} UTC</span>'
            f'<h2>{E(p["headlines"][0])}</h2><span class="ft"><span>{S.cover(p)}</span></span></span></a>')


def feed(shown):
    rows = S.by_score(S.window(shown, 48))[:21] if len(S.window(shown, 48)) >= 5 else shown[:21]
    groups, i = [], 0
    for size in [1, 2, 3, 4, 3, 2, 3, 4, 1, 2]:
        if i >= len(rows):
            break
        groups.append(rows[i:i + size])
        i += size
    cls = {1: "xl", 2: "l", 3: "m", 4: "s"}
    tiles = "".join(tile(p, cls[len(g)], 12 // len(g), bool(p.get("_thumb"))) for g in groups for p in g)
    return (f'<div class="fmast"><a href="{S.BASE}/" class="fw" aria-label="boardread. front page">boardread.</a></div>'
            f'<div class="fmrow"><span>The Feed, printed</span><span><a href="{S.BASE}/cover/">This week\'s cover</a></span></div>'
            f'<div class="mos">{tiles}</div>')


def week_rows(shown):
    wk = S.week_of(shown[0]["published"])
    rows = [p for p in shown if S.week_of(p["published"]) == wk]
    return wk, sorted(rows, key=S.shared, reverse=True)


def cover_page(shown):
    wk, rows = week_rows(shown)
    top = rows[:5]
    lead = next((p for p in top if p.get("_hires")), top[0])
    lines = "".join(f'<li><a href="{S.href(p)}">{E(p["headlines"][0])}</a></li>' for p in top if p is not lead)[:4000]
    lines = "".join(f'<li><a href="{S.href(p)}">{E(p["headlines"][0])}</a></li>' for p in [q for q in top if q is not lead][:4])
    photo = f'<img src="{S.BASE}/img/{lead["id"]}.jpg" width="960" height="640" alt="" fetchpriority="high">' if lead.get("_hires") else ""
    unfinished = wk == datetime.now(timezone.utc).strftime("%G-W%V")
    return (head(f"Week {wk[-2:]}, {wk[:4]}" + (", so far" if unfinished else ""), "The cover",
                 "The week's top articles as one card, ready to share.")
            + f'<div class="cover4"><a class="cv-card {"sc" if photo else "k"}" href="{S.href(lead)}">{photo}<span class="cin"><span class="cw">boardread.</span>'
              f'<span class="cg">Week {wk[-2:]} &middot; {wk[:4]}</span><h2>{E(lead["headlines"][0])}</h2></span></a>'
              f'<div class="cside"><div class="sec cap"><span>Also this week</span></div><ol class="cl">{lines}</ol>'
              f'<p class="attr">Chosen by shares and saves, then by the desk\'s ranking. <a href="{S.BASE}/week/{wk}/">The full Top 10 of week {wk[-2:]}</a>.</p></div></div>')


# ---------------------------------------------------------------- numbers

def figures(shown, n=9):
    out = []
    for p in shown:
        fig = (p.get("figure") or "").strip()
        if fig and re.search(r"\d", fig) and S.number_box(p):  # "a million" is a phrase, not a figure to set large
            out.append((fig, p))
    return out[:n]


def numbers_page(shown, m):
    cells = ""
    for fig, p in figures(shown):
        size = "n1" if len(fig) <= 6 else "n2" if len(fig) <= 9 else "n3"
        cells += (f'<a href="{S.href(p)}"><b class="n {size}">{E(fig)}</b><span class="u">{E(p["headlines"][0])}</span>'
                  f'<p>{S.hhmm(p["published"])} UTC &middot; {nroom(p)}</p></a>')
    grid = f'<div class="ng">{cells}</div>' if cells else ""
    official = ""
    if m:
        official = (f'<div class="og"><div><div class="sec cap"><span>Official series</span></div>'
                    f'<p class="olead">The rates behind the headlines, from the central banks and treasuries that publish them. Each value carries the date of its series.</p>'
                    f'{markets.rates_box(m, S.BASE, "plain")}</div>'
                    f'<div><div class="sec cap"><span>US Treasury yield curve</span><span class="dm">{markets.dmy(m["ust"][-1]["date"]) if m.get("ust") else ""}</span></div>'
                    f'<div class="cvbig">{markets.curve_svg(m, 640, 300, 13)}</div></div></div>')
    sub = "The figures in today's news, each linked to its article. Below them, the official series for rates and currencies." if grid else "Official series for rates and currencies."
    return head(S.day_label(S.day_of(shown[0]["published"])), "The numbers", sub) + grid + official


# ---------------------------------------------------------------- yesterday's paper

def edition_day(shown, today=None):
    """The day the paper shows: the latest full UTC day with articles; the newest day when nothing else exists yet."""
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    days = sorted({S.day_of(p["published"]) for p in shown}, reverse=True)
    return next((d for d in days if d < today), days[0] if days else None)


def edition_pages(rows, m, day):
    """Six pages of 620 x 880: the front, three of columns by section, the names and numbers, and a colophon.
    Fewer articles make fewer inside pages; the count stays even so the leaves close."""
    ranked = S.by_score(rows)
    front, rest = ranked[:3], ranked[3:15]
    order = {t: i for i, t in enumerate(S.TOPIC_ORDER)}
    rest = sorted(rest, key=lambda p: (order[S.topic(p)], -p.get("score", 0)))
    chunks = [rest[i:i + 4] for i in range(0, len(rest), 4)]

    def a(p, cls="", photo=False, dek=True, ratio="3/2"):
        im = f'<img src="{S.BASE}/img/{p["id"]}-t.jpg" width="480" height="320" alt="" loading="lazy" style="aspect-ratio:{ratio}">' if photo and p.get("_thumb") else ""
        return (f'<div class="a"><div class="m">{E(S.topic(p))} &middot; {S.hhmm(p["published"])}</div>{im}<h3 class="{cls}"><a href="{S.href(p)}">{E(p["headlines"][0])}</a></h3>'
                + (f'<p>{E(p.get("dek", ""))}</p>' if dek else "") + "</div>")

    def page(n, sect, inner):
        return (f'<div class="pg"><div class="hd"><span>boardread. &middot; {S.day_label(day)}</span><span>{E(sect)}</span></div>{inner}'
                f'<div class="ft"><span>All times UTC</span><span>{n}</span></div></div>')
    pages = []
    x = [p for p in front]
    inner = '<div class="nm">boardread.</div><div class="sc">Front page</div>'
    if x:
        inner += a(x[0], "x", True, True, "3/2")
        if x[1:]:
            inner += '<div class="cl" style="grid-template-columns:' + "1fr " * len(x[1:]) + '">' + "".join(f"<div>{a(p, 'y', True, False, '4/3')}</div>" for p in x[1:]) + "</div>"
    pages.append(("Front page", inner))
    for ch in chunks[:3]:
        sects = list(dict.fromkeys(S.topic(p) for p in ch))
        inner = f'<div class="sc">{" and ".join(sects) if len(sects) < 3 else sects[0] + " and more"}</div><div class="cl" style="grid-template-columns:1fr 1fr">'
        inner += "".join(f"<div>{a(p, 'y' if k < 2 else '', photo=k < 2, dek=True, ratio='16/9')}</div>" for k, p in enumerate(ch)) + "</div>"
        if m and len(pages) == 1:
            inner += '<div class="sc">Rates and currencies</div><div class="cl" style="grid-template-columns:1fr 1fr"><div>' + "".join(
                f'<div class="rt"><span>{E(r["k"])}</span><b>{E(r["v"])}</b><small>{E(r["date"])}</small></div>' for r in markets.rows(m)[:3]
            ) + f'</div><div class="cv-in">{markets.curve_svg(m, 300, 150, 10)}</div></div>'
        pages.append((sects[0], inner))
    nm = names(rows, 4)
    nn = "".join(f'<div><b>{k}</b><span>{E(n)}</span><small>{k} newsroom pickups in {PLURAL(len(ps), "article")}</small></div>' for n, ps, k in nm)
    figs = "".join(f'<div><b>{E(f)}</b><small>{E(p["headlines"][0])}</small></div>' for f, p in figures(rows, 4))
    inner = ((f'<div class="sc">Names in the news</div><div class="nn">{nn}</div>') if nm else "") + ((f'<div class="sc">The numbers</div><div class="nn">{figs}</div>') if figs else "")
    pages.append(("Names and numbers", inner or f'<div class="sc">Inside</div><p>{PLURAL(len(rows), "article")} from {PLURAL(len({n.lower() for p in rows for n in outlets.newsrooms(p)}), "newsroom")}.</p>'))
    if len(pages) % 2:
        pages.append(("Notes", '<div class="sc">About this edition</div><p class="note">Written by AI from the sources listed. Every article links its newsrooms; numbers are checked against the source text before publishing. '
                      'Official data: ECB statistics; U.S. Department of the Treasury. All times UTC.</p>'))
    if len(pages) % 2:
        pages.append(pages.pop())
    return [page(i, sect, inner) for i, (sect, inner) in enumerate(pages, 1)]


def paper_page(shown, m, day, days):
    rows = [p for p in shown if S.day_of(p["published"]) == day]
    pages = edition_pages(rows, m, day)
    leaves = "".join(f'<div class="leaf" style="--i:{i // 2 + 1}"><div class="face r">{pages[i]}</div><div class="face bk">{pages[i + 1]}</div></div>' for i in range(0, len(pages), 2))
    mob = "".join(f'<div class="pgw"><div class="pgi">{p}</div></div>' for p in pages)
    labels = ["Page 1"] + [f"Pages {i} and {i + 1}" for i in range(2, len(pages), 2)] + [f"Page {len(pages)}"]
    arch = "".join(f'<li{" class=\"cur\"" if d == day else ""}><a href="{S.BASE}/paper/{d}/">{S.day_label(d)}</a></li>' for d in days[:30])
    return (f'<div class="pp-wrap"><div class="pp-top"><div><div class="cap dm">Edition of {S.day_label(day)}</div><h1 class="cd">Yesterday\'s<br>paper</h1></div>'
            f'<div class="ctl" role="group" aria-label="Turn pages"><button type="button" data-prev aria-label="Previous page" disabled>&larr;</button>'
            f'<span class="lab" aria-live="polite">{labels[0]}</span><button type="button" data-next aria-label="Next page">&rarr;</button></div></div>'
            f'<div class="stage" data-labels="{E("|".join(labels))}"><div class="book" data-s="0">{leaves}</div><div class="mob" tabindex="0" aria-label="Pages, swipe sideways">{mob}</div></div>'
            f'<div class="arch"><div class="sec cap"><span>Editions</span></div><ul>{arch}</ul>'
            f'<p class="attr">Turn the pages with the arrow keys, the buttons or a swipe. With reduced motion set, pages change without the turn.</p></div></div>')
