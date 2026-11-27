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
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import desk, markets, outlets
from . import site as S

E = S.E
CODE = {"Business": "BUS", "Economy": "ECO", "Markets": "MKT", "Politics": "POL", "World": "WLD", "Tech": "TEC", "AI": "AI", "Culture": "CUL"}
PLURAL = lambda n, w: f"{n} {w}{'' if n == 1 else 's'}"  # noqa: E731


def nroom(p):
    return PLURAL(S.coverage(p), "newsroom")


def mt(p):
    """Topic, time and newsrooms in the small caps line above a headline."""
    return f'{E(S.topic(p))} &middot; <time datetime="{S.iso(p["published"])}">{S.stamp(p["published"])}</time> &middot; {nroom(p)}'


def img(p, ratio="3/2", thumb=True, fixed=False):
    """fixed: the stylesheet gives the image its own width and height (the board rows), so the shape is kept as asked."""
    if not p.get("_thumb"):
        return ""
    return S.photo_img(p, thumb, ratio, fixed=fixed)


def photo_cap(p):
    """One short line under a picture on a card: what kind of photo it is. The same label the article's caption starts with."""
    from . import entities
    return f'<span class="pcap">{E(entities.archive_label(p.get("photo_kind", ""), p.get("topic", "")))}</span>'


def paras(p):
    return "".join(f"<p>{E(x)}</p>" for x in (p.get("body") or "").split("\n") if x.strip())


def head(kicker, title, sub=""):
    return (f'<div class="vh"><div class="cap">{kicker}</div><h1 class="cd">{title}</h1>'
            + (f'<p class="vsub">{sub}</p>' if sub else "") + "</div>")


def age_attr(p):
    """What the script turns into "2h 14m ago"; without it the reader sees the date."""
    return f'<time class="age" datetime="{S.iso(p["published"])}" data-age>{S.dt(p["published"]).strftime("%-d %b")}</time>'


# ---------------------------------------------------------------- front page

# The front page, the Feed, the brief, the paper and the blocks of every section are ranked by news value, not by the desk's own score. Topic counts for
# most (hard news over brand and culture items), then how many newsrooms reported it, then a small share of the desk score;
# words that mark consequence add, words that mark PR or soft news take it away. A lead must clear this, so "Denny's reshares
# Nvidia origin story" does not lead a day with tariffs, a capsized tanker and a data breach.
TOPIC_WEIGHT = {"Politics": 3, "Economy": 3, "Markets": 3, "World": 3, "Business": 2, "Tech": 1.5, "AI": 1.5, "Culture": 0}
SOFT = re.compile(r"\b(reshares?|celebrat\w+|viral|origin story|anniversar\w+|partners? with|partnerships?|teams? up|honou?rs?|award|unveils?|introduces?|ambassador|fans?)\b", re.I)
HARD = re.compile(r"\b(tariffs?|rates?|inflation|GDP|bans?|halts?|strikes?|sanctions?|breach|hack\w*|job cuts|layoffs?|capsiz\w+|crash\w*|probe|investigat\w+|court|ruling|bankrupt\w*|collapse|default|acquir\w+|acquisition|merger|shortage|recession|deficit|ceasefire|war|suspends?)\b", re.I)


def front_score(p):
    text = f'{p["headlines"][0]} {p.get("dek", "")}'
    return (TOPIC_WEIGHT.get(S.topic(p), 1.5) * 2 + min(S.coverage(p), 5) * 1.2 + 0.15 * p.get("score", 0)
            + (2 if HARD.search(p["headlines"][0]) else 0) - (8 if SOFT.search(text) else 0))


def front_rank(rows, newest=None):
    """News value, then freshness: the page led a morning with an 18-hour-old tariff item while the day's news waited
    below it (2026-11-27); at three points it still led, on four newsrooms against three. Freshness is worth five
    points at most, half gone after about eight hours. newest: the time freshness counts back from (the newest article
    of the page, when rows is only one section of it)."""
    newest = newest or max((S.dt(p["published"]) for p in rows), default=None)
    def fresh(p):
        return 5 * math.exp(-max((newest - S.dt(p["published"])).total_seconds(), 0) / 3600 / 12)
    return sorted(rows, key=lambda p: front_score(p) + fresh(p), reverse=True)


NAME_TOKEN = re.compile(r"[A-Z][A-Za-z0-9]{2,}")


def photo_ok(p):
    """A photo goes on the front page only if it shows what the article names: the person, the company, or another capitalised name
    from the headline or summary appears in the photo's file name. A server corridor under an OpenAI article or a globe under a
    satellite item says nothing, so those articles run as text. (The photo is still on the article's own page.)"""
    if not p.get("_thumb") or not (p.get("photo_file") or "").strip() or S.generic_photo(p):
        return False  # a stand-in photo (photo_kind "scene") belongs on the article's own page, with its caption, not on a card
    return photo_subject(p) is not None


def photo_subject(p):
    """The name that ties the photo to the article (the first one found in the file name), or None. Two photos of the same
    subject never share a front page: the first keeps it, the next article runs as text."""
    if p.get("photo_kind") == "scene":  # a vetted sport scene: its own file is the subject, so it shows once per page
        return Path(p.get("photo_file") or "").stem.lower()
    stem = re.sub(r"[^a-z0-9]+", " ", Path(p.get("photo_file") or "").stem.lower())
    names = [t.lower() for t in NAME_TOKEN.findall(p["headlines"][0]) + NAME_TOKEN.findall(p.get("dek", "")) if (len(t) >= 4 or t.isupper()) and t not in STOP_FIRST]
    names += [w.lower() for w in re.findall(r"[A-Za-z0-9]{3,}", f'{p.get("person") or ""} {S.co_of(p)}')]
    return next((n for n in dict.fromkeys(names) if n not in {"this", "with", "that", "from", "will"} and re.search(rf"\b{re.escape(n)}", stem)), None)


def rel_time(p):
    """A time in a list: "12 min ago" once the script runs, the clock time (with the date, for another day) before it."""
    return f'<time class="rel" datetime="{S.iso(p["published"])}" data-age>{S.stamp(p["published"], utc=False)}</time>'


def latest_list(rows):
    """The Latest row markup: time and headline, no image. Used on the front, the 404 page and the end of an article."""
    return "<ul>" + "".join(f'<li><a href="{S.href(p)}">{rel_time(p)}<span>{E(p["headlines"][0])}</span></a></li>' for p in rows) + "</ul>"


def section_rows(rows, newest, n=4):
    """The n articles a section block shows: the day's by news value, most important first. A section with fewer than n
    in the day is filled from older ones, newest first, so a quiet section still has a block."""
    day = {id(p) for p in S.window(rows)}
    top = front_rank([p for p in rows if id(p) in day], newest)
    return (top + [p for p in rows if id(p) not in day])[:n]


def puzzles_block(cls=""):
    """"Today's puzzles": one link per live game. Static: no state about the visitor. Empty while no game is live."""
    from . import play
    games = play.live() if "play" in S.SHIPPED else []
    if not games:
        return ""
    items = "".join(f'<li><a href="{S.BASE}/play/{slug}/">{E(title)}</a></li>' for slug, title, _, _ in games)
    return f'<section class="puzzles {cls}" aria-label="Today\'s puzzles"><h2 class="sh"><a href="{S.BASE}/play/">Today\'s puzzles</a></h2><ul>{items}</ul></section>'


def top5_list(ranked, n=5):
    """Top 5: five headlines with their age, no pictures. The phone shows ranked[1:6] right after the lead (the rail's two pictured
    articles are in it); the desktop shows ranked[3:8], under the lead, beside the rail that already carries ranked[1:3]."""
    rows = ranked[1:n + 3]
    items = ""
    for i, p in enumerate(rows):
        cls = " ".join(c for c, on in (("ds", i < 2), ("pm", i >= n)) if on)  # ds: not on the desktop, pm: not on the phone
        items += f'<li{f" class=\"{cls}\"" if cls else ""}><a href="{S.href(p)}"><span>{E(p["headlines"][0])}</span>{rel_time(p)}</a></li>'
    return f'<section class="top5" aria-label="Top 5"><h2 class="sh">Top 5</h2><ol>{items}</ol></section>' if items else ""


def front(shown, cos, m, sport=()):
    """The front page: the lead (8 columns) and the rail (4: two seconds, the markets block, Latest), then the sections.
    Each article appears once; the lead and the seconds come from the news-value ranking above."""
    today = S.window(shown)
    ranked = front_rank(today)
    lead = ranked[0]
    used = {lead["id"]}
    seconds = [p for p in ranked[1:] if p["id"] not in used][:2]
    used |= {p["id"] for p in seconds}
    newest = S.dt(shown[0]["published"]) if shown else None
    used |= {p["id"] for p in ranked[1:8]}  # Top 5 (phone: ranked[1:6], desktop: ranked[3:8]): each article is placed once on the page
    latest_rows = [p for p in shown if p["id"] not in used][:8]
    used |= {p["id"] for p in latest_rows}
    seen = set()

    def ph(p):
        """True when p may show its photo: it shows the named subject and no earlier item on the page shows the same one."""
        subj = photo_subject(p) if photo_ok(p) else None
        if subj is None or subj in seen:
            return False
        seen.add(subj)
        return True
    fig = (f'<figure>{S.photo_img(lead, False, "16/9", load="eager")}'
           f'<figcaption>{S.credit_html(lead)}</figcaption></figure>') if ph(lead) and lead.get("_hires") else ""
    first = next((x for x in (lead.get("body") or "").split("\n") if x.strip()), "")
    lead_html = (f'<div class="lead"><a class="kick" href="{S.BASE}{S.topic_path(S.topic(lead))}">{E(S.topic(lead))}</a>'
                 f'<h2 class="lh"><a href="{S.href(lead)}">{E(lead["headlines"][0])}</a></h2><p class="dk">{E(lead.get("dek", ""))}</p>'
                 f'<div class="mt">{rel_time(lead)} &middot; {nroom(lead)}</div>{fig}'
                 f'<p class="tx">{E(first)}</p><a class="more" href="{S.href(lead)}">Read the article</a>{top5_list(ranked)}{puzzles_block("inlead")}{markets.rates_box(m, S.BASE)}</div>')

    def second(p):
        photo = img(p, "3/2") + photo_cap(p) if ph(p) else ""
        return (f'<article class="second"><a href="{S.href(p)}">{photo}<span class="kick">{E(S.topic(p))}</span><h3>{E(p["headlines"][0])}</h3></a>'
                f'<p>{E(p.get("dek", ""))}</p><div class="mt">{rel_time(p)} &middot; {nroom(p)}</div></article>')
    latest = ('<section class="latest"><h2 class="sh"><a href="' + S.BASE + '/latest/">Latest</a></h2>' + latest_list(latest_rows)
              + f'<p class="sportmore"><a href="{S.BASE}/latest/">All latest</a></p></section>') if latest_rows else ""
    seconds_html = [second(p) for p in seconds]
    rail = '<div class="toprail"><h2 class="sh">Also at the top</h2>' + "".join(seconds_html) + latest + "</div>"

    blocks = []  # (html, estimated height at the left column's width) per section, in section order
    for t in S.NEWS_ORDER:
        rows = section_rows([p for p in shown if S.topic(p) == t and p["id"] not in used], newest)
        if not rows:
            continue  # a section without articles leaves no head and no hole
        used.update(p["id"] for p in rows)
        top, rest = rows[0], rows[1:]
        shows = ph(top)
        photo = img(top, "3/2") + photo_cap(top) if shows else ""
        html = (f'<section class="sect"><h2 class="sh"><a href="{S.BASE}{S.topic_path(t)}">{t}</a></h2>'
                f'<article class="slead"><a href="{S.href(top)}">{photo}<h3>{E(top["headlines"][0])}</h3></a><div class="mt">{rel_time(top)} &middot; {nroom(top)}</div></article>'
                + "".join(f'<article class="srow"><a href="{S.href(p)}"><h3>{E(p["headlines"][0])}</h3><div class="mt">{rel_time(p)}</div></a></article>' for p in rest) + "</section>")
        blocks.append((html, _block_height(top, rest, shows)))
    # Desktop: the left column ends where the lead, Top 5 and the markets box end, the rail much lower. The first sections go
    # under the lead, two to a row, as many as bring the two columns level; the rest run full width below.
    left_h = 1124 + (380 if fig else 0)  # measured at 1280 px: lead 370, Top 5 300, markets box 370, gaps
    rail_h = 30 + sum(560 if "<img" in h else 265 for h in seconds_html) + (70 + 80 * len(latest_rows) if latest_rows else 0)
    take, best = 0, abs(rail_h - left_h)
    for k in range(2, len(blocks) + 1, 2):
        h = left_h + 48 + sum(max(blocks[i][1], blocks[i + 1][1] if i + 1 < len(blocks) else 0) + 48 for i in range(0, k, 2)) - 48
        if abs(rail_h - h) < best:
            take, best = k, abs(rail_h - h)
    take = min(take, len(blocks))
    inlead = f'<div class="sects inlead">{"".join(b[0] for b in blocks[:take])}</div>' if take else ""
    left_over = len(blocks) - take
    cols = " c3" if left_over in (5, 6, 9) else ""  # 5 run 3 and 2, never 4 and 1 under a wide gap
    below = f'<div class="sects{cols}">{"".join(b[0] for b in blocks[take:])}</div>' if blocks[take:] else ""
    return (S.updated_line(since=True) + f'<div class="front">{lead_html}{rail}{inlead}</div>' + below
            + sport_block(section_rows(list(sport), S.dt(sport[0]["published"]) if sport else None, 4), ph) + puzzles_block("inrow"))


def _lines(text, per_line):
    return max(1, -(-len(text) // per_line))


def _block_height(top, rest, shows):
    """Rough height in px of a section block in a half-width column of the left side, used only to decide how many go under the lead."""
    h = 60 + 36 + 29 * _lines(top["headlines"][0], 30) + 24 + (260 if shows else 0)
    return h + sum(24 + 24 * _lines(p["headlines"][0], 34) + 22 for p in rest)


def sport_block(rows, ph, n=4):
    """Sport on the front page: one row of the most important articles of the day below the business sections, so the front stays business news.
    A section without articles leaves no head and no hole."""
    rows = rows[:n]
    if not rows:
        return ""
    cells = "".join(f'<article class="slead"><a href="{S.href(p)}">{img(p, "3/2") + photo_cap(p) if ph(p) else ""}<h3>{E(p["headlines"][0])}</h3></a>'
                    f'<p>{E(p.get("dek", ""))}</p><div class="mt">{rel_time(p)}</div></article>' for p in rows)
    return (f'<section class="sportblk" aria-label="Sport"><h2 class="sh"><a href="{S.BASE}/sport/">Sport</a></h2><div class="sportgrid">{cells}</div>'
            f'<p class="sportmore"><a href="{S.BASE}/sport/">More sport</a></p></section>')



# ---------------------------------------------------------------- names

STOP_FIRST = {"The", "A", "An", "In", "On", "At", "As", "After", "Before", "How", "Why", "What", "Who", "When", "New", "More", "Most", "Is", "Are",
              "To", "For", "Of", "And", "But", "With", "By", "From", "Over", "Under", "Its", "His", "Her", "Their", "This", "That", "These", "Those", "Will",
              "He", "She", "They", "It", "We", "You", "I", "Not", "No", "Says", "Say"}
NOT_NAMES = {"U.S", "US", "UK", "EU", "AI", "CEO", "GDP", "UN",
             "Officials", "Analysts", "Investors", "Shares", "Stocks", "Police", "Companies", "Workers", "Employees", "Customers", "Prices",
             "Banks", "Voters", "Lawmakers", "Regulators", "Authorities", "Executives", "Researchers", "Economists", "Traders", "Shoppers"}  # places and terms, not the people and companies the tape is for
TITLES = {"President", "Prime", "Minister", "Secretary", "Senator", "Sen", "Governor", "Gov", "Chancellor", "Chairman", "Chair", "Judge", "Justice",
          "Mr", "Mrs", "Ms", "Dr", "King", "Queen", "Sir", "Lord", "Former", "Vice"}  # "President Donald Trump" is Donald Trump
POSSESSIVE = re.compile(r"['’]s$")
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
            while toks and (toks[0] in STOP_FIRST or toks[0].rstrip(".") in TITLES):
                toks = toks[1:]
            # "Disney's ABC" is Disney: a name ends where its possessive does, and "Nvidia's" is "Nvidia", not a second name
            cut = []
            for t in toks:
                cut.append(POSSESSIVE.sub("", t))
                if POSSESSIVE.search(t):
                    break
            toks = [t.rstrip(".'’-") for t in cut]
            if not toks or toks[0] in TITLES or any(t in MONTHS for t in toks) or (len(toks) == 1 and re.search(r"(ish|ese|ian|ican)$", toks[0]) and toks[0] != S.co_of(p)):
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
        th = img(p, "3/2", fixed=True) if p.get("_thumb") else '<span class="th"></span>'
        out += (f'<article class="row dep{" big" if big else ""}"><span class="tm"><time datetime="{S.iso(p["published"])}">{flaps(S.hhmm(p["published"]), go=True)}'
                f'<span class="sr">{S.stamp(p["published"])}</span></time></span><span class="sc" title="{E(S.topic(p))}">{CODE[S.topic(p)]}</span>'
                f'<div class="ti"><h3><a href="{S.href(p)}">{E(p["headlines"][0])}</a></h3>'
                + (f'<p class="dk">{E(p.get("dek", ""))}</p>' if big else "") + f'</div><span class="src">{S.by(p)}</span>'
                f'<span class="cv">{nroom(p)}</span><span class="agec">{age_attr(p)}</span><span class="imgc">{th}</span></article>')
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
        cells = "".join(f'<td>{f"<span title=\"{E(n)}\" aria-hidden=\"true\">&#9679;</span><span class=\"sr\">{E(n)}</span>" if n.lower() in have else ""}</td>' for n, _ in order)
        body += (f'<tr><th scope="row"><small>{S.stamp(p["published"], utc=False)} &middot; {CODE[S.topic(p)]}</small><a href="{S.href(p)}">{E(p["headlines"][0])}</a></th>{cells}</tr>')
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
                f'<div class="seatbox"><div class="seatscale"><span class="cap dm">Reported by {PLURAL(S.coverage(top), "newsroom")}</span></div>{seat_list}</div></div></section>')
    nm = names(rows)
    tape = "".join(f'<span class="tk">{E(n)}<small>{PLURAL(len(ps), "article")}</small><em>{k}</em></span>' for n, ps, k in nm)
    nrows = "".join(f'<div class="nm-row"><span class="rk">{i:02d}</span><h3>{E(n)}</h3><ul>'
                    + "".join(f'<li><span>{S.stamp(x["published"], utc=False)}</span><a href="{S.href(x)}">{E(x["headlines"][0])}</a></li>' for x in ps)
                    + f'</ul><div class="bars"><div><b>{k}</b>newsroom pickups</div><div><b>{len(ps)}</b>{"article" if len(ps) == 1 else "articles"}</div></div></div>'
                    for i, (n, ps, k) in enumerate(nm, 1))
    names_sec = (f'<section id="names" class="bsec"><div class="sec"><span>Names</span><span class="dm">People and companies, by newsroom pickups</span></div>'
                 f'<div class="tape" aria-hidden="true"><div class="tape-in">{tape}{tape}</div></div>{nrows}</section>') if nm else ""
    wire = (f'<section id="wire" class="bsec"><div class="sec"><span>The wire</span><span class="dm">A dot: that newsroom reported it</span></div>'
            f'<p class="vsub">Read across to see how widely an article was reported, down to see what a newsroom led with. The wire shows who reported, not when.</p>'
            f'{matrix(rows)}</section>')
    hdr = ('<div class="vh"><div class="cap dm">Departures, newest first</div><h1 class="cd">The Board</h1>'
           f'<p class="vsub">{PLURAL(len(rows), "business article")} from {PLURAL(len({n.lower() for p in rows for n in outlets.newsrooms(p)}), "newsroom")}. '
           'Coverage is the newsrooms that reported it.</p>'
           '<nav class="jumps cap" aria-label="On this page"><a href="#river">River</a><a href="#names">Names</a><a href="#wire">Wire</a></nav></div>')
    head_row = '<div class="bh"><span>Time</span><span>Sec</span><span>Headline</span><span>Newsrooms</span><span>Coverage</span><span>Age</span><span></span></div>'
    return hdr + hero + f'<section id="river" class="bsec board" aria-label="Departures">{head_row}{board_rows([p for p in rows if p is not top])}</section>' + names_sec + wire


# ---------------------------------------------------------------- the feed and the cover

def fcard(p, first=False):
    """A feed card: the photo at 4:3 (when it shows its subject), the headline, the plain meta. Without a photo the card is text."""
    media = img(p, "4/3", thumb=False) + photo_cap(p) if photo_ok(p) else ""
    return (f'<article class="fcard{" first" if first else ""}{"" if media else " textonly"}"><a href="{S.href(p)}">{media}'
            f'<div class="mt">{E(S.topic(p))} &middot; {S.stamp(p["published"])} &middot; {nroom(p)}</div><h2>{E(p["headlines"][0])}</h2></a>'
            f'<p>{E(p.get("dek", ""))}</p></article>')


def feed(shown):
    pool = S.window(shown, 48)
    # the very function the front page ranks with, over the same 24 hours first, so the Feed leads with the front page's lead; the day before follows
    day = {id(p) for p in S.window(shown)}
    rows = (front_rank([p for p in pool if id(p) in day]) + front_rank([p for p in pool if id(p) not in day]))[:21] if len(pool) >= 5 else shown[:21]
    return (head("The news as cards", "The Feed", 'The last two days, in front-page order. <a href="' + S.BASE + '/cover/">This week\'s cover</a>.')
            + '<div class="fgrid">' + "".join(fcard(p, i == 0) for i, p in enumerate(rows)) + "</div>")


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
    photo = S.photo_img(lead, False, "4/3", load="eager", box=False) if lead.get("_hires") else ""
    unfinished = wk == datetime.now(timezone.utc).strftime("%G-W%V")
    unfinished = wk == datetime.now(timezone.utc).strftime("%G-W%V")
    photo = S.photo_img(lead, False, "4/3", load="eager", box=False) if photo_ok(lead) and lead.get("_hires") else ""
    return (head(f"Week {wk[-2:]}, {wk[:4]}" + (", so far" if unfinished else ""), "The cover", "The week's top articles as one card, ready to share.")
            + f'<div class="cover4"><a class="cv-card" href="{S.href(lead)}">{photo}<span class="cin"><span class="cg">boardread. &middot; Week {wk[-2:]}</span>'
              f'<h2>{E(lead["headlines"][0])}</h2></span></a>'
              f'<div class="cside"><h2 class="sh">Also this week</h2><ol class="cl">{lines}</ol>'
              f'<p class="attr">Chosen by shares and saves, then by the desk\'s ranking. <a href="{S.BASE}/week/{wk}/">The full Top 10 of week {wk[-2:]}</a>.</p></div></div>')


# ---------------------------------------------------------------- numbers

def figures(shown, n=9):
    out = []
    for p in shown:
        fig = (p.get("figure") or "").strip()
        if fig and re.search(r"\d", fig) and S.figure_stated(p):  # "a million" is a phrase, not a figure to set large
            out.append((fig, p))
    return out[:n]


def figure_sentence(fig, p):
    """The sentence of the summary that states the figure ("Amazon's ad business generates $68.6 billion a year"), so a tile says what
    the number counts; "" when the headline states it (the headline is then the caption)."""
    if desk._in_text(fig, p["headlines"][0]):
        return ""
    return next((x.strip() for x in re.split(r"(?<=[.!?])\s+", p.get("dek") or "") if desk._in_text(fig, x)), "")


def numbers_page(shown, m):
    cells = ""
    for fig, p in figures(shown):
        size = "n1" if len(fig) <= 6 else "n2" if len(fig) <= 9 else "n3"
        what = figure_sentence(fig, p)
        cells += (f'<a href="{S.href(p)}"><b class="n {size}">{E(fig)}</b><span class="u">{E(what or p["headlines"][0])}</span>'
                  + (f'<span class="hl">{E(p["headlines"][0])}</span>' if what else "")
                  + f'<p>{S.stamp(p["published"])} &middot; {nroom(p)}</p></a>')
    grid = f'<div class="ng">{cells}</div>' if cells else ""
    official = ""
    if m:
        curve = markets.curve_svg(m, 640, 300, 13)
        official = (f'<section class="msec"><h2 class="sh">Markets</h2><p class="olead">Prices and rates from the central banks, treasuries and statistics offices that publish them. '
                    f'Every card shows its series date and source.</p>{markets.cards(m)}</section>'
                    + markets.crypto_section(m)  # daily, so it sits above the monthly metals
                    + (f'<section class="msec"><h2 class="sh">Metals</h2><p class="olead">Monthly averages from the World Bank, each against the month before. '
                       f'Daily metal prices are licensed and not shown.</p>{markets.cards(m, markets.METALS)}</section>' if any(k in m.get("series", {}) for k in markets.METALS) else "")
                    + (f'<section class="msec"><h2 class="sh">US Treasury yield curve</h2><div class="cvbig">{curve}</div>'
                       f'<p class="what"><b>What it is.</b> Yields on US government debt from one month to thirty years; a curve that slopes down can signal expected rate cuts or a slowdown.</p>'
                       f'<p class="attr">Solid: {markets.dmy(m["curve"][-1]["date"])}' + (f', dashed: {markets.dmy(m["curve"][-2]["date"])}' if len(m["curve"]) > 1 else "") + f'. Per cent. {markets.SRC_UST}</p></section>' if m.get("curve") else ""))
    sub = "Figures from the news, then the official rate series." if grid else "The official rate series."
    return head(S.day_label(S.day_of(shown[0]["published"])), "The numbers", sub) + grid + official


# ---------------------------------------------------------------- yesterday's paper

def edition_day(shown, today=None):
    """The day the paper shows: the latest full UTC day with articles; the newest day when nothing else exists yet."""
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    days = sorted({S.day_of(p["published"]) for p in shown}, reverse=True)
    return next((d for d in days if d < today), days[0] if days else None)


def edition_split(rows):
    """(the three front-page articles, the twelve inside ones in section order): chosen by the news value the front page ranks with."""
    ranked = front_rank(rows)
    order = {t: i for i, t in enumerate(S.TOPIC_ORDER)}
    return ranked[:3], sorted(ranked[3:15], key=lambda p: (order[S.topic(p)], -front_score(p)))


def edition_list(rows, m):
    """The edition for a phone, as text at reading size: the same articles as the pages, in the same order, one column. The sheets are
    620 px wide and fit a phone only at half size, where the body text is 6 px."""
    front, rest = edition_split(rows)

    def item(p):
        return (f'<article><div class="m">{E(S.topic(p))} &middot; {S.hhmm(p["published"])} UTC &middot; {nroom(p)}</div>'
                f'<h3><a href="{S.href(p)}">{E(p["headlines"][0])}</a></h3><p>{E(p.get("dek", ""))}</p></article>')
    out = ('<h2 class="sh">Front page</h2>' + "".join(item(p) for p in front)) if front else ""
    for t in dict.fromkeys(S.topic(p) for p in rest):
        out += f'<h2 class="sh">{E(t)}</h2>' + "".join(item(p) for p in rest if S.topic(p) == t)
    nm = names(rows, 4)
    if nm:
        out += '<h2 class="sh">Names in the news</h2><ul>' + "".join(f'<li><b>{E(n)}</b>, {PLURAL(len(ps), "article")}, {k} newsroom pickups</li>' for n, ps, k in nm) + "</ul>"
    figs = figures(rows, 4)
    if figs:
        out += '<h2 class="sh">The numbers</h2><ul>' + "".join(f'<li><b>{E(f)}</b> {E(figure_sentence(f, p) or p["headlines"][0])}</li>' for f, p in figs) + "</ul>"
    return f'<div class="mlist" aria-label="The edition as a list">{out}</div>' if out else ""


def edition_pages(rows, m, day):
    """Six pages of 620 x 880: the front, three of columns by section, the names and numbers, and a colophon.
    Fewer articles make fewer inside pages; the count stays even so the leaves close."""
    front, rest = edition_split(rows)
    chunks = [rest[i:i + 4] for i in range(0, len(rest), 4)]

    def a(p, cls="", photo=False, dek=True, ratio="3/2"):
        im = S.photo_img(p, True, ratio) if photo and p.get("_thumb") else ""
        side = ""
        if im and cls == "x" and S.fit(p, True, ratio)[2] != ratio:
            # a face does not fit a wide strip, and the page has no room for a tall one under the headline: the portrait stands beside it
            im, side = S.photo_img(p, True, "3/4", fixed=True), " side"
        return (f'<div class="a{side}"><div class="m">{E(S.topic(p))} &middot; {S.hhmm(p["published"])}</div>{im}<h3 class="{cls}"><a href="{S.href(p)}">{E(p["headlines"][0])}</a></h3>'
                + (f'<p>{E(p.get("dek", ""))}</p>' if dek else "") + "</div>")

    def page(n, sect, inner):
        return (f'<div class="pg"><div class="hd"><span>boardread. &middot; {S.day_label(day)}</span><span>{E(sect)}</span></div>{inner}'
                f'<div class="ft"><span>All times UTC</span><span>{n}</span></div></div>')
    pages = []
    x = [p for p in front]
    inner = '<div class="nm">boardread.</div>'
    if x:
        inner += a(x[0], "x", True, True, "2/1")
        if x[1:]:
            inner += '<div class="cl" style="grid-template-columns:' + "1fr " * len(x[1:]) + '">' + "".join(f"<div>{a(p, 'y', True, False, '2/1')}</div>" for p in x[1:]) + "</div>"
    pages.append(("Front page", inner))
    for ch in chunks[:3]:
        sects = list(dict.fromkeys(S.topic(p) for p in ch))
        inner = f'<div class="sc">{" and ".join(sects) if len(sects) < 3 else sects[0] + " and more"}</div><div class="cl" style="grid-template-columns:1fr 1fr">'
        cols = (ch[0::2], ch[1::2])
        inner += "".join("<div>" + "".join(a(p, "y" if k == 0 else "", photo=k == 0, dek=True, ratio="16/9") for k, p in enumerate(c)) + "</div>" for c in cols if c) + "</div>"
        pages.append((sects[0], inner))
    nm = names(rows, 4)
    nn = "".join(f'<div><b>{k}</b><span>{E(n)}</span><small>{k} newsroom pickups in {PLURAL(len(ps), "article")}</small></div>' for n, ps, k in nm)
    figs = "".join(f'<div><b>{E(f)}</b><small>{E(figure_sentence(f, p) or p["headlines"][0])}</small></div>' for f, p in figures(rows, 4))
    rooms = {}
    for p in rows:
        for o in outlets.newsrooms(p):
            rooms.setdefault(o, 0)
            rooms[o] += 1
    top_rooms = sorted(rooms.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
    src = ('<div class="sc">Where it came from</div><div class="nn">' + "".join(f'<div><b>{c}</b><span>{E(o)}</span></div>' for o, c in top_rooms) + "</div>") if top_rooms else ""
    inner = ((f'<div class="sc">Names in the news</div><div class="nn">{nn}</div>') if nm else "") + ((f'<div class="sc">The numbers</div><div class="nn">{figs}</div>') if figs else "")
    inner += src
    pages.append(("Names and numbers", inner or f'<div class="sc">Inside</div><p>{PLURAL(len(rows), "article")} from {PLURAL(len({n.lower() for p in rows for n in outlets.newsrooms(p)}), "newsroom")}.</p>'))
    if len(pages) % 2:
        rate_rows = "".join(f'<div class="rt"><span>{E(r["k"])}</span><b>{E(r["v"])}</b><small>{E(r["date"])} &middot; {E(r["src"])}</small></div>' for r in markets.rows(m)) if m else ""
        rates = f'<div class="sc">Rates and currencies</div>{rate_rows}<div class="cv-in">{markets.curve_svg(m, 560, 230, 11)}</div><p class="note">{E(markets.attribution(m))}</p>' if rate_rows else ""
        pages.append(("Rates and notes", rates + '<div class="sc">About this edition</div><p class="note">Written by AI from the sources listed. Every article links its newsrooms; numbers are checked '
                      'against the source text before publishing. All times UTC.</p>'))
    if len(pages) % 2:
        pages.append(pages.pop())
    return [page(i, sect, inner) for i, (sect, inner) in enumerate(pages, 1)]


def paper_page(shown, m, day, days, main=False):
    """One edition. main: the page at /paper/, which shows the last full day and carries the name "Yesterday's paper"; every dated
    page is "The paper" of its day, "so far" while the day is still running."""
    rows = [p for p in shown if S.day_of(p["published"]) == day]
    pages = edition_pages(rows, m, day)
    leaves = "".join(f'<div class="leaf" style="--i:{i // 2 + 1}"><div class="face r">{pages[i]}</div><div class="face bk">{pages[i + 1]}</div></div>' for i in range(0, len(pages), 2))
    mob = "".join(f'<div class="pgw"><div class="pgi">{p}</div></div>' for p in pages)
    labels = ["Page 1"] + [f"Pages {i} and {i + 1}" for i in range(2, len(pages), 2)] + [f"Page {len(pages)}"]
    so_far = day >= S.today()
    arch = "".join(f'<li{" class=\"cur\"" if d == day else ""}><a href="{S.BASE}/paper/{d}/">{S.day_label(d)}{", so far" if d >= S.today() else ""}</a></li>' for d in days[:30])
    h1 = paper_title(day, main)
    return (f'<div class="pp-wrap"><div class="pp-top"><div><div class="cap dm">Edition of {S.day_label(day)}{", so far" if so_far else ""}</div><h1 class="cd">{h1}</h1></div>'
            f'<div class="ctl" role="group" aria-label="Turn pages"><button type="button" data-prev aria-label="Previous page" disabled>&larr;</button>'
            f'<span class="lab" aria-live="polite">{labels[0]}</span><button type="button" data-next aria-label="Next page">&rarr;</button></div></div>'
            f'<div class="stage" data-labels="{E("|".join(labels))}"><div class="book" data-s="0">{leaves}</div><div class="mob" tabindex="0" aria-label="Pages, swipe sideways">{mob}</div></div>'
            f'{edition_list(rows, m)}'
            f'<div class="arch"><div class="sec cap"><span>Editions</span></div><ul>{arch}</ul>'
            f'<p class="attr">Turn the pages with the arrow keys, the buttons or a swipe. With reduced motion set, pages change without the turn.</p></div></div>')


def paper_title(day, main=False):
    """The heading of an edition (html): "Yesterday's paper" only on /paper/ and only once its day is over."""
    if main and day < S.today():
        return "Yesterday\'s<br>paper"
    return f'The paper{", so far" if day >= S.today() else ""}'
