"""The pages built on top of the article pages: the 60-second brief, the quiz, company pages, feeds per topic and per
company, and how the desk works with live counts. site.build() calls build() once the articles are written.

The quiz questions come from desk.pick_*, the same selection the Instagram quiz articles use, so a question that cannot
be asked honestly (too few companies, no money figures to compare) is simply not on the page."""
import json
import shutil
from datetime import timedelta
from email.utils import format_datetime

from . import desk, entities, markets, outlets, play
from . import site as S
from . import views as V

BRIEF_N = 8
E = S.E


def brief_rows(shown, day):
    """The brief of a day: that day's top articles by news value, the order of the front page (the desk's own score put four politics
    items in a row above the page's lead). Only that day's: the 24 hours before its last article put seven of 26 November's
    articles under a brief dated 27 November."""
    return V.front_rank([p for p in shown if S.day_of(p["published"]) == day])[:BRIEF_N]


def brief_day(shown, days):
    """The day /brief/ shows: the newest with a full brief, so the page is not two articles long just after midnight
    UTC. The newest day when none has BRIEF_N yet."""
    return next((d for d in days if len(brief_rows(shown, d)) >= BRIEF_N), days[0])


def brief_words(rows):
    """Words in the brief and the seconds it takes to read them at a scanning pace (about 205 words a minute)."""
    words = sum(len((p["headlines"][0] + " " + p.get("dek", "")).split()) for p in rows)
    return words, round(words / 3.4)


def brief_page(shown, day, m=None):
    """The brief of a day: a finite column of the top articles, one block each, ending with the closing mark."""
    rows = brief_rows(shown, day)
    words, sec = brief_words(rows)
    items = "".join(f'<article class="bn"><b>{k}</b><div><div class="cap dm">{E(S.topic(p))}</div><h2><a class="hl" href="{S.href(p)}">{E(p["headlines"][0])}</a></h2>'
                    f'<p>{E(p.get("dek", ""))}</p><div class="mt">{S.stamp(p["published"])} &middot; {V.nroom(p)}</div></div></article>'
                    for k, p in enumerate(rows, 1))
    more = len([p for p in shown if S.day_of(p["published"]) == day]) - len(rows)
    stop = (f'<div class="stop"><b>&ndash; 30 &ndash;</b><p>End of the brief. {V.PLURAL(len(rows), "article")}, {words} words, about {sec // 60} minute{"" if sec // 60 == 1 else "s"} '
            f'and {sec % 60} seconds.{f" The other {more} of the day are on the Board." if more > 0 else ""}</p>'
            f'<a class="btn" href="{S.BASE}/board/">The Board</a> {f'<a class="btn alt" href="{S.BASE}/play/">Play today\'s games</a>' if "play" in S.SHIPPED else ""}</div>')
    head = V.head(S.day_label(day), "In brief", f"The top {len(rows)} of the day. About {sec // 60}:{sec % 60:02d} to read.")
    return f'<div class="bf">{head}<div class="bcol">{items}{stop}</div><div class="bside">{markets.rates_box(m, S.BASE) if m else ""}</div></div>'


def quiz_questions(shown):
    """Up to four questions for the day of the newest article; a type with no data is skipped."""
    if not shown:
        return []
    top, day = S.dt(shown[0]["published"]), S.day_of(shown[0]["published"])
    recent = [p for p in shown if top - S.dt(p["published"]) <= timedelta(hours=48)]
    week = [p for p in shown if top - S.dt(p["published"]) <= timedelta(days=7)]
    qs = [desk.pick_company(day, recent, week), desk.pick_fill(day, recent), desk.pick_bigger(day, week),
          desk.pick_whois(day, week, recent, has_photo=lambda p: p.get("_hires"))]
    return [q for q in qs if q]


def _question(i, q):
    posts = q["posts"]
    if q["type"] == "bigger":
        prompt = f'Which is bigger: the {E(q["kind"])} of {E(q["first"][1][0])} or of {E(q["second"][1][0])}?'
    elif q["type"] == "whois":
        prompt = "Who is this?"
    else:
        prompt = E(q["question"])
    photo = (f'<figure class="qpic"><span class="pic sq" style="aspect-ratio:4/3">{S.photo_img(posts[0], False, "4/3", box=False)}</span>'
             f'<figcaption class="meta">{E(entities.clean_credit(q.get("credit") or posts[0].get("credit", "")))}</figcaption></figure>') if q["type"] == "whois" else ""
    opts = "".join(f'<li><button type="button" class="opt">{E(o)}</button></li>' for o in q["options"])
    ans = q["options"][q["answer"]]
    if q["type"] == "bigger":
        ans = f'{ans}: ' + "; ".join(f'{E(p["figure"].strip())} for {E(m[0])}' for p, m in (q["first"], q["second"]))
    else:
        ans = E(ans)
    links = "".join(f'<li><a href="{S.href(p)}"><b>{E(p["headlines"][0])}</b></a><span class="meta">'
                    + "".join(f'<a href="{E(u)}" rel="nofollow noopener" target="_blank">{E(o)}</a>' for o, u in outlets.source_mix(p)[:4])
                    + "</span></li>" for p in posts)
    return (f'<section class="q" data-answer="{q["answer"]}" aria-labelledby="q{i}"><h2 id="q{i}" class="lab">{i}. {E(q["title"])}</h2>'
            f'{photo}<p class="prompt">{prompt}</p><ol class="opts">{opts}</ol>'
            f'<details class="ans"><summary>Show the answer</summary><p class="right">{ans}</p>'
            f'<p class="meta">The article and where it was reported:</p><ul class="from">{links}</ul></details></section>')


def quiz_page(shown):
    qs = quiz_questions(shown)
    if not qs:
        return S.pagehead("Quiz", "Today's questions.") + '<div class="empty">There is no quiz yet. It needs a few more articles with figures and names.</div>'
    day = S.day_label(S.day_of(shown[0]["published"]))
    return (S.pagehead("Today's quiz", f"{day}. {len(qs)} question{'' if len(qs) == 1 else 's'}, each from an article on this site.")
            + f'<div class="quiz" data-quiz>{"".join(_question(i, q) for i, q in enumerate(qs, 1))}'
              f'<p class="tally" aria-live="polite"></p></div>')


def how_page(shown, everything=None):
    """everything: every article on the site, Sport included. An "article on the site" means one of those, on this page and in the archive;
    Latest, the brief and the main feed carry the business ones, and say so."""
    everything = shown if everything is None else everything
    sport = [p for p in everything if S.is_sport(p)]
    c = S.desk_counts(everything)
    share = round(100 * c["three_plus"] / c["stories"]) if c["stories"] else 0
    return S.pagehead("How it works", "How the desk works.") + f"""<div class="prose">
<h2>The numbers now</h2>
<dl>
<dt>Feeds scanned</dt><dd>{c['feeds']} feeds, fetched every 30 minutes</dd>
<dt>Newsrooms on the site</dt><dd>{c['newsrooms']} different newsrooms across {c['stories']} articles{f", {len(sport)} of them Sport" if sport else ""}</dd>
<dt>Articles with three or more newsrooms</dt><dd>{c['three_plus']} of {c['stories']} ({share}%)</dd>
<dt>Companies with a page</dt><dd>{len(S.companies(shown))}, each with at least two articles</dd>
<dt>Articles with a credited photo</dt><dd>{c['photos']}</dd>
</dl>
<h2>From feed to page</h2>
<ol class="steps">
<li><div><b>Scan.</b> The desk fetches the feeds of newsrooms and research labs and groups coverage of the same event into one article.</div></li>
<li><div><b>Score.</b> An article is scored on how many newsrooms carry it and how recent it is. Only articles above a fixed bar go on.</div></li>
<li><div><b>Write.</b> An AI model writes a short report from the source text. It has no other input and no tools.</div></li>
<li><div><b>Check.</b> Fixed code compares the text with the source before anything is public.</div></li>
</ol>
<h2>Checks every published article passes</h2>
<ul>
<li>Every number in the text appears in the source text.</li>
<li>Each sentence is compared with the source text. A sentence whose words are mostly missing from it is rejected.</li>
<li>A photo needs a licence that allows reuse and a credit line, which is shown under it.</li>
<li>A fixed audit of topic, photo, hashtags and stock phrases.</li>
</ul>
<h2>What the coverage bar means</h2>
<p>The bar counts the different newsrooms whose reporting an article draws on. Aggregators and social accounts are not counted. A longer bar means more independent desks reported it. It says nothing about whether the article is right.</p>
<p>See also the <a href="{S.BASE}/standards/">standards and corrections policy</a> and the <a href="{S.BASE}/about/">about page</a>.</p>
</div>"""


def company_logo(out, slug, posts):
    """Copy the first licensed logo a company's articles carry to img/co-<slug>.<ext>; its site path, or ''."""
    for p in posts:
        for name in ("logo.svg", "logo.png", "logo.jpg"):
            f = desk.MEDIA / p["id"] / name
            if f.exists():
                dest = f"co-{slug}{f.suffix}"
                shutil.copy(f, out / "img" / dest)
                return f"{S.BASE}/img/{dest}"
    return ""


def company_page(name, slug, rows, logo):
    items = "".join(f'<li><time datetime="{S.iso(p["published"])}">{S.day_label(S.day_of(p["published"]))}</time>'
                    f'<a href="{S.href(p)}"><span class="h-m">{E(p["headlines"][0])}</span><span class="dek">{E(p.get("dek", ""))}</span>'
                    f'{S.meta(E(S.topic(p)), S.cover(p))}</a></li>' for p in rows)
    head = S.pagehead(name, f"{len(rows)} {'article' if len(rows) == 1 else 'articles'} since {S.day_label(S.day_of(rows[-1]['published']))}, newest first.")
    tks = {(t["exchange"], t["symbol"]) for t in (S.ticker_of(p) for p in rows) if t}
    if len(tks) == 1:  # a company whose articles disagree shows no ticker
        head = head.replace("</h1>", f'</h1><p class="meta">{S.ticker_html(next(t for t in (S.ticker_of(p) for p in rows) if t))}</p>', 1)
    if logo:
        head = head.replace('<div class="pagehead">', f'<div class="pagehead"><img class="cologo" src="{logo}" alt="" height="56">', 1)
    return (head + f'<div class="prose wide"><ol class="timeline">{items}</ol>'
            f'<p class="meta"><a href="{S.BASE}/c/{slug}/feed.xml">Follow {E(name)} by RSS</a></p></div>')


def feed_for(out, shown_rows, path, title, link):
    items = [(p["headlines"][0], f"{S.SITE}/s/{p['id']}/", format_datetime(S.dt(p["published"])), p.get("dek", ""),
              {"category": S.topic(p), "image": f"{S.BASE}/og/{p['id']}.jpg" if p.get("_og") else None,
               "image_bytes": (out / "og" / f"{p['id']}.jpg").stat().st_size if p.get("_og") else 0}) for p in shown_rows[:50]]
    d = out / path.strip("/")
    d.mkdir(parents=True, exist_ok=True)
    (d / "feed.xml").write_text(S.rss(title, link, items, self_path=f"{path}feed.xml"))


def build_views(out, shown, sm, m, days):
    """The Board, the Feed, the weekly cover, the numbers and Yesterday's paper with its dated editions."""
    if not shown:
        return
    latest = S.iso(shown[0]["published"])
    pages = (("/board/", "The Board · boardread.", lambda: V.board(shown, m), "Every article as a departure: the newest first, who reported it, the names in the news and a wire.", "board"),
             ("/feed/", "The Feed · boardread.", lambda: V.feed(shown), "The news as cards: photo cards and text cards, the biggest first.", "feed"),
             ("/cover/", "The weekly cover · boardread.", lambda: V.cover_page(shown), "The week's top articles as one shareable card.", "feed"),
             ("/numbers/", "The numbers · boardread.", lambda: V.numbers_page(shown, m), "The figures in the news and the official rate series behind them.", "numbers"))
    for path, title, body, desc, active in pages:
        if active not in S.SHIPPED:  # a page is built only once it has shipped, so no menu or link points at a missing page
            continue
        S.put(out, path, S.page(title, body(), desc, path, active=active, body_class="v-" + active))
        sm.append((S.SITE + path, latest))
    if "paper" not in S.SHIPPED:
        return
    ed = V.edition_day(shown)
    eds = sorted({S.day_of(p["published"]) for p in shown}, reverse=True)
    # /paper/ is the dated edition it shows under another name: it carries its own title and says so with a canonical, and is left out
    # of the sitemap, so a search engine sees one copy of the page and not two that change places every midnight
    for path, day, main in [("/paper/", ed, True)] + [(f"/paper/{d}/", d, False) for d in eds]:
        label = S.day_label(day)
        title = "Yesterday's paper" if main and day < S.today() else f"The paper, {label}{', so far' if day >= S.today() else ''}"
        desc = (f"Yesterday's news in six pages: the edition of {label}." if main
                else f"The paper of {label}{', so far' if day >= S.today() else ''}, six pages.")
        S.put(out, path, S.page(f"{title} · boardread.", V.paper_page(shown, m, day, eds, main), desc, path, active="paper",
                                styles=("views", "paper"), scripts=("paper",), body_class="v-paper",
                                canonical=f"/paper/{day}/" if main else None))
        if not main:
            sm.append((S.SITE + path, latest))


def build(out, shown, sm, cos, everything=None):
    """Pages: /brief/ and its dated archive, /quiz/, /how-it-works/, /c/<slug>/ and the per-topic and per-company feeds."""
    latest = S.iso(shown[0]["published"]) if shown else None
    m = S.MARKETS
    days = list(dict.fromkeys(S.day_of(p["published"]) for p in shown))
    if shown:
        earlier = ('<div class="prose past-wrap"><h2>Earlier briefs</h2><ul class="past">'
                   + "".join(f'<li><a href="{S.BASE}/brief/{d}/">{S.day_label(d)}</a></li>' for d in days[1:30]) + "</ul></div>") if days[1:] else ""
        S.put(out, "/brief/", S.page("The brief · boardread.", brief_page(shown, brief_day(shown, days), m) + earlier,
              "The day's top articles in about a minute, one block each.", "/brief/", active="brief"))
        for d in days:
            S.put(out, f"/brief/{d}/", S.page(f"The brief, {S.day_label(d)} · boardread.", brief_page(shown, d, m),
                                              f"The top articles of {S.day_label(d)}, one block each.", f"/brief/{d}/", active="brief"))
            sm.append((f"{S.SITE}/brief/{d}/", S.iso(brief_rows(shown, d)[0]["published"])))
    else:
        S.put(out, "/brief/", S.page("The brief · boardread.", S.pagehead("The brief") + '<div class="empty">The first brief is on its way.</div>',
                                     "The day's top articles in about a minute.", "/brief/", active="brief"))
    build_views(out, shown, sm, m, days)
    if "play" in S.SHIPPED:
        play.build(out, shown, sm)
    # the questions of the day keep their address beside the games, so no old link breaks
    S.put(out, "/quiz/", S.page("Today's quiz · boardread.", quiz_page(shown), "Questions built from today's articles, each answer linked to its sources.", "/quiz/", active="play"))
    sm.append((S.SITE + "/quiz/", latest))
    S.put(out, "/how-it-works/", S.page("How it works · boardread.", how_page(shown, everything), "How the desk turns feeds into articles, with live counts.", "/how-it-works/"))
    for path in ("/brief/", "/how-it-works/"):
        sm.append((S.SITE + path, latest))
    (out / "img").mkdir(exist_ok=True)
    for slug, (name, rows) in cos.items():
        S.put(out, f"/c/{slug}/", S.page(f"{name} · boardread.", company_page(name, slug, rows, company_logo(out, slug, rows)),
                                         f"Every Boardread article about {name}, newest first.", f"/c/{slug}/",
                                         feed=(f"boardread. {name}", f"/c/{slug}/feed.xml")))
        feed_for(out, rows, f"/c/{slug}/", f"boardread. {name}", f"{S.SITE}/c/{slug}/")
        sm.append((f"{S.SITE}/c/{slug}/", S.iso(rows[0]["published"])))
    for t in S.NEWS_ORDER:  # Sport is built by site.build, which has its articles
        rows = [p for p in shown if S.topic(p) == t]
        feed_for(out, rows, S.topic_path(t), f"boardread. {t}", f"{S.SITE}{S.topic_path(t)}")
