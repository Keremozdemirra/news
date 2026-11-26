"""The pages built on top of the article pages: the 60-second brief, the quiz, company pages, feeds per topic and per
company, and how the desk works with live counts. site.build() calls build() once the articles are written.

The quiz questions come from desk.pick_*, the same selection the Instagram quiz articles use, so a question that cannot
be asked honestly (too few companies, no money figures to compare) is simply not on the page."""
import json
import shutil
from datetime import timedelta
from email.utils import format_datetime

from . import desk, outlets
from . import site as S

BRIEF_N = 8
E = S.E


def brief_rows(shown, day):
    """The brief of a day: the top articles by score in the 24 hours up to the day's last article."""
    ps = [p for p in shown if S.day_of(p["published"]) == day]
    if not ps:
        return []
    end = S.dt(ps[0]["published"])
    pool = [p for p in shown if timedelta(0) <= end - S.dt(p["published"]) <= timedelta(hours=24)]
    return S.by_score(pool)[:BRIEF_N]


def brief_page(shown, day):
    rows = brief_rows(shown, day)
    items = "".join(f'<li><a href="{S.href(p)}"><span class="h-m">{E(p["headlines"][0])}</span>'
                    f'{S.meta(E(S.topic(p)), S.t_tag(p), S.cover(p))}</a></li>' for p in rows)
    return (S.pagehead("The brief", f"{S.day_label(day)}. The day's top {len(rows)} articles, one line each, about a minute.")
            + f'<div class="brief"><ol>{items}</ol><p class="end">That\'s the brief.</p>'
              f'<p class="after"><a href="{S.BASE}/quiz/">Play today\'s quiz</a><a href="{S.BASE}/latest/">Everything else, newest first</a></p></div>')


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
    photo = (f'<figure class="qpic"><span class="pic sq"><img src="{S.BASE}/img/{posts[0]["id"]}.jpg" width="960" height="640" alt=""></span>'
             f'<figcaption class="meta">{E(q.get("credit") or posts[0].get("credit", ""))}</figcaption></figure>') if q["type"] == "whois" else ""
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


def how_page(shown):
    c = S.desk_counts(shown)
    share = round(100 * c["three_plus"] / c["stories"]) if c["stories"] else 0
    return S.pagehead("How it works", "What the desk does, with numbers computed when this page was built.") + f"""<div class="prose">
<h2>The numbers now</h2>
<dl>
<dt>Feeds scanned</dt><dd>{c['feeds']} feeds, fetched every 30 minutes</dd>
<dt>Newsrooms on the site</dt><dd>{c['newsrooms']} different newsrooms across {c['stories']} articles</dd>
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


def build(out, shown, sm, cos):
    """Pages: /brief/ and its dated archive, /quiz/, /how-it-works/, /c/<slug>/ and the per-topic and per-company feeds."""
    latest = S.iso(shown[0]["published"]) if shown else None
    days = list(dict.fromkeys(S.day_of(p["published"]) for p in shown))
    if shown:
        earlier = ('<div class="prose"><h2>Earlier briefs</h2><ul class="past">'
                   + "".join(f'<li><a href="{S.BASE}/brief/{d}/">{S.day_label(d)}</a></li>' for d in days[1:30]) + "</ul></div>") if days[1:] else ""
        S.put(out, "/brief/", S.page("The brief · boardread.", brief_page(shown, days[0]) + earlier,
              "The day's top articles in about a minute, one line each.", "/brief/", active="brief"))
        for d in days:
            S.put(out, f"/brief/{d}/", S.page(f"The brief, {S.day_label(d)} · boardread.", brief_page(shown, d),
                                              f"The top articles of {S.day_label(d)}, one line each.", f"/brief/{d}/", active="brief"))
            sm.append((f"{S.SITE}/brief/{d}/", S.iso(brief_rows(shown, d)[0]["published"])))
    else:
        S.put(out, "/brief/", S.page("The brief · boardread.", S.pagehead("The brief") + '<div class="empty">The first brief is on its way.</div>',
                                     "The day's top articles in about a minute.", "/brief/", active="brief"))
    S.put(out, "/quiz/", S.page("Today's quiz · boardread.", quiz_page(shown), "Questions built from today's articles, each answer linked to its sources.", "/quiz/"))
    S.put(out, "/how-it-works/", S.page("How it works · boardread.", how_page(shown), "How the desk turns feeds into articles, with live counts.", "/how-it-works/"))
    for path in ("/brief/", "/quiz/", "/how-it-works/"):
        sm.append((S.SITE + path, latest))
    (out / "img").mkdir(exist_ok=True)
    for slug, (name, rows) in cos.items():
        S.put(out, f"/c/{slug}/", S.page(f"{name} · boardread.", company_page(name, slug, rows, company_logo(out, slug, rows)),
                                         f"Every Boardread article about {name}, newest first.", f"/c/{slug}/",
                                         feed=(f"boardread. {name}", f"/c/{slug}/feed.xml")))
        feed_for(out, rows, f"/c/{slug}/", f"boardread. {name}", f"{S.SITE}/c/{slug}/")
        sm.append((f"{S.SITE}/c/{slug}/", S.iso(rows[0]["published"])))
    for t in S.TOPIC_ORDER:
        rows = [p for p in shown if S.topic(p) == t]
        feed_for(out, rows, f"/t/{t.lower()}/", f"boardread. {t}", f"{S.SITE}/t/{t.lower()}/")
