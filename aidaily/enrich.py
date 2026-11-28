"""Primary-source enrichment: facts the newsrooms' own sources hold, added to the top stories before the copy step.

A newsroom's RSS summary is 100 to 600 characters. The numbers behind a story sit in a primary source: a company's
SEC filing, an official statistic, a regulator's release. This module finds that source for a few top stories an
hour and returns 2 to 4 checked facts with the exact URL each one came from. The writer may print them in a
"By the numbers" or "Context" section, built from these facts and nothing else.

Rules this module keeps (legal answers 2026-11-27, section 5):
- facts only: a fact is our own sentence, never a newsroom's, and never a run of six words from any text;
- no newsroom article is fetched, only a government or company primary source;
- every number in a fact must be in the primary text it names (number_problems), or the fact is dropped;
- the source is named by its agency or company and linked.

Standard library only. The network and the model are passed in (Ctx), so a test never touches either.
"""
import json
import os
import re
import ssl
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlsplit

from . import copy, feeds

HERE = copy.HERE
STATE = HERE / "state" / "enrich.json"
PER_HOUR = 3        # stories enriched per hour: each costs a handful of requests and at most one model call
MIN_FACTS = 2       # a story with fewer solid facts stays as it is
MAX_FACTS = 4
RUN_WORDS = 6       # a run this long, word for word from the newsroom text or the primary text, is copied
MAX_WORDS = 30
PRIMARY_CHARS = 24000
SCALES = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}
MONTHS = ("January February March April May June July August September October November December").split()


# ---------------------------------------------------------------------------------------------------------------
# context: the network, the model and the clock, injected

def _fetch(url, ua="", timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": ua or feeds.UA, "Accept": "*/*"})
    # an explicit CA bundle wins (the macOS one is older than the ECB's certificate chain); verification is never off
    tls = ssl.create_default_context(cafile=os.environ["SSL_CERT_FILE"]) if os.environ.get("SSL_CERT_FILE") else feeds.CTX
    with urllib.request.urlopen(req, timeout=timeout, context=tls) as r:
        return r.read(3_000_000)


class Ctx:
    """get(url, ua) -> bytes; ask(prompt) -> str; contact: a generic address SEC asks every automated client to
    declare (desk.json "contact_email" or DESK_SEC_CONTACT). Without one the SEC data adapter does not run."""

    def __init__(self, get=None, ask=None, now=None, contact=""):
        self.get, self.ask, self.contact = get or _fetch, ask or copy.ask_text, contact
        self.now = now or datetime.now(timezone.utc)
        self.notes, self._memo = [], {}

    def note(self, msg):
        self.notes.append(msg)

    def raw(self, url, ua=""):
        """One request per URL in a run: three stories about the Fed read FRED once."""
        if url not in self._memo:
            self._memo[url] = self.get(url, ua)
        return self._memo[url]

    def text(self, url, ua=""):
        return self.raw(url, ua).decode("utf-8", "replace")

    def json(self, url, ua=""):
        return json.loads(self.raw(url, ua))


def live_ctx():
    from . import desk
    return Ctx(contact=os.environ.get("DESK_SEC_CONTACT") or desk.CONFIG.get("contact_email") or "")


# ---------------------------------------------------------------------------------------------------------------
# the fact gate

NUMTOK = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)(?:\s*(thousand|million|billion|trillion)\b)?", re.I)


def _values(evidence):
    out = set()
    for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", evidence or ""):
        try:
            out.add(float(m.group(0).replace(",", "")))
        except ValueError:
            pass
    return out


def number_problems(text, evidence):
    """Numbers in `text` the evidence does not hold. The existing literal test (copy._numbers) passes a number that
    stands in the evidence as written; "$94.93 billion" also passes when the evidence holds 94930000000, because
    rounding 94930000000 to the two decimals shown gives it. Anything else is returned."""
    have, vals, bad = copy._numbers(evidence), _values(evidence), []
    for m in NUMTOK.finditer(text or ""):
        lit = m.group(1).replace(",", "")
        if lit in have:
            continue
        scale = SCALES.get((m.group(2) or "").lower(), 1)
        dec = len(lit.split(".")[1]) if "." in lit else 0
        if scale > 1 and any(abs(v - float(lit) * scale) <= 0.5 * 10 ** -dec * scale for v in vals):
            continue
        bad.append(m.group(1))
    return bad


def shared_run(a, b, n=RUN_WORDS):
    """The first run of n words that `a` takes word for word from `b`, or "" (the n-gram overlap check)."""
    return copy.copied_run(a, b, n)


GENERIC = set(copy._stems("data official figures statistics published release report survey year years percent number people "
                          "latest first second third found shows show data said says new more most also over under about"))


def relevant(story, text):
    """A fact taken from a document is about the story: it uses a word of the story's headline, or two words of its text,
    beyond the generic ones. "Defra added the datasets on 6 November" under a story about milk sales is padding."""
    mine = copy._stems(text, short=True) - GENERIC
    return bool(mine & copy._stems(story.get("title", ""), short=True)) or len(mine & copy._stems(copy.source_text(story), short=True)) >= 2


def fact_problems(story, fact):
    """Why a fact may not be shown, or []. Every fact must be a sentence of our own: numbers from its evidence,
    no habit of machine copy, no run of the newsroom's words, and something the newsroom text did not say."""
    from . import desk
    text, ev = fact.get("text", ""), fact.get("evidence", "")
    rss = copy.source_text(story)
    out = []
    if not text.strip() or not ev.strip():
        return ["no text or no evidence"]
    if not str(fact.get("url", "")).startswith("https://") or not fact.get("label"):
        out.append("no label or no link")
    if len(text.split()) > MAX_WORDS + 8:
        out.append("too long")
    bad = number_problems(text, ev)
    if bad:
        out.append(f"numbers not in the primary text {bad}")
    out += copy.tells(text)
    for rx, why in ((desk.SLOP, "stock phrase"), (copy.HYPE, "hype"), (copy.NOT_BUT, "not X but Y")):
        if rx.search(text):
            out.append(why)
    if fact.get("kind") == "release" and not relevant(story, text):
        out.append("not about the story")
    run = shared_run(text, rss)
    if run:
        out.append(f"copies the newsroom: {run!r}")
    if copy.repeats(text, rss, share=0.85) and not (copy._numbers(text) - copy._numbers(rss)):
        out.append("says only what the newsroom said")
    return out


def gate_facts(story, facts):
    """(kept, dropped): at most MAX_FACTS, no two alike, each one past fact_problems."""
    kept, dropped = [], []
    for f in facts:
        why = fact_problems(story, f)
        if why:
            dropped.append({"text": f.get("text", "")[:120], "why": why})
        elif any(copy.repeats(f["text"], k["text"], share=0.8) and copy._numbers(f["text"]) == copy._numbers(k["text"]) for k in kept):
            dropped.append({"text": f["text"][:120], "why": ["repeats another fact"]})
        else:
            kept.append(f)
    return kept[:MAX_FACTS], dropped


# ---------------------------------------------------------------------------------------------------------------
# formatting helpers: plain words, numbers as the source holds them

def month_year(period):
    """"2026-11" or "2026-11-01" -> "November 2026"."""
    y, m = period[:4], int(period[5:7])
    return f"{MONTHS[m - 1]} {y}"


def day(date):
    """"2026-11-25" -> "Nov 25, 2026"."""
    d = datetime.strptime(date[:10], "%Y-%m-%d")
    return f"{MONTHS[d.month - 1][:3]} {d.day}, {d.year}"


def money(v):
    sign, v = ("-" if v < 0 else ""), abs(v)
    if v >= 1e9:
        return f"{sign}${v / 1e9:.2f} billion"
    if v >= 1e6:
        return f"{sign}${v / 1e6:.1f} million"
    return f"{sign}${v:,.0f}"


def fresh(period, now, days):
    """The period's first day is no more than `days` before now: an old print is not "latest"."""
    try:
        d = datetime.strptime((period + "-01")[:10] if len(period) == 7 else period[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return (now - d).days <= days


def _fact(text, label, url, evidence, kind, data_url=""):
    f = {"text": text, "label": label, "url": url, "evidence": re.sub(r"\s+", " ", evidence).strip()[:900], "kind": kind}
    if data_url:
        f["data_url"] = data_url
    return f


# ---------------------------------------------------------------------------------------------------------------
# official statistics: deterministic, the sentence is built from the numbers

GEO = {"euro area": ("EA", "the euro area"), "euro zone": ("EA", "the euro area"), "eurozone": ("EA", "the euro area"),
       "france": ("FR", "France"), "french": ("FR", "France"), "germany": ("DE", "Germany"), "german": ("DE", "Germany"),
       "italy": ("IT", "Italy"), "italian": ("IT", "Italy"), "spain": ("ES", "Spain"), "spanish": ("ES", "Spain"),
       "netherlands": ("NL", "the Netherlands"), "dutch": ("NL", "the Netherlands")}
EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{ds}?{q}&lastTimePeriod=2&format=JSON&lang=EN"
EUROSTAT_PAGE = "https://ec.europa.eu/eurostat/databrowser/view/{ds}/default/table?lang=en"


def eurostat(ctx, ds, q, geo, name, what, unit_word):
    url = EUROSTAT.format(ds=ds, q=q)
    d = ctx.json(url)
    times = sorted(d["dimension"]["time"]["category"]["index"], key=lambda t: d["dimension"]["time"]["category"]["index"][t])
    vals = [d["value"].get(str(i)) for i in range(len(times))]
    rows = [(t, v) for t, v in zip(times, vals) if v is not None]
    if len(rows) < 2 or not fresh(rows[-1][0], ctx.now, 130):
        ctx.note(f"eurostat {ds} {geo}: no fresh print")
        return []
    (pt, pv), (t, v) = rows[-2], rows[-1]
    text = f"Eurostat puts {what} in {name} at {v}{unit_word} for {month_year(t)}, against {pv}{unit_word} in {month_year(pt)}."
    ev = f"Eurostat {ds} {geo} {d.get('label', '')}: time {pt} value {pv}; time {t} value {v}; updated {d.get('updated', '')}"
    return [_fact(text, "Eurostat", EUROSTAT_PAGE.format(ds=ds), ev, "stat", url)]


def ecb_rates(ctx):
    out = []
    for key, name in (("MRR_FR", "main refinancing rate"), ("DFR", "deposit facility rate")):
        url = f"https://data-api.ecb.europa.eu/service/data/FM/B.U2.EUR.4F.KR.{key}.LEV?lastNObservations=2&format=jsondata"
        d = ctx.json(url)
        ser = next(iter(d["dataSets"][0]["series"].values()))["observations"]
        dates = [v["id"] for v in d["structure"]["dimensions"]["observation"][0]["values"]]
        rows = [(dates[int(i)], o[0]) for i, o in sorted(ser.items(), key=lambda x: int(x[0]))]
        if len(rows) < 2 or not fresh(rows[-1][0], ctx.now, 400):
            continue
        (pd, pv), (dt, v) = rows[-2], rows[-1]
        text = f"The European Central Bank's {name} has stood at {v}% since {day(dt)}, up from {pv}% on {day(pd)}." if v > pv \
            else f"The European Central Bank's {name} has stood at {v}% since {day(dt)}, down from {pv}% on {day(pd)}." if v < pv \
            else f"The European Central Bank's {name} has stood at {v}% since {day(dt)}."
        ev = f"ECB data portal FM B.U2.EUR.4F.KR.{key}.LEV: {pd} {pv}; {dt} {v}; prepared {d.get('header', {}).get('prepared', '')}"
        out.append(_fact(text, "European Central Bank", f"https://data.ecb.europa.eu/data/datasets/FM/FM.B.U2.EUR.4F.KR.{key}.LEV", ev, "stat", url))
    return out[:2]


BLS_NAMES = {"CUUR0000SA0": "consumer price index", "CUUR0000SAF11": "consumer price index for food at home",
             "LNS14000000": "unemployment rate"}


def _before(year, month):
    return (year - 1, 12) if month == 1 else (year, month - 1)


def bls(ctx, series):
    """BLS public API v1 (no key). An index is given as it is printed plus the change worked out from two printed
    values; the evidence line shows the division, so the gate can read the percentage in it."""
    url = f"https://api.bls.gov/publicAPI/v1/timeseries/data/{series}?startyear={ctx.now.year - 2}&endyear={ctx.now.year}"
    d = ctx.json(url)
    rows = [(r["year"], r["period"], r["value"]) for r in d["Results"]["series"][0]["data"] if r["period"].startswith("M") and r["period"] != "M13"
            and re.fullmatch(r"\d+(?:\.\d+)?", r["value"])]  # a month BLS did not collect reads "-"
    if len(rows) < 2:
        return []
    y, p, v = rows[0]
    period = f"{y}-{p[1:]}"
    if not fresh(period, ctx.now, 100):
        ctx.note(f"bls {series}: no fresh print")
        return []
    name, label, page = BLS_NAMES[series], "U.S. Bureau of Labor Statistics", f"https://data.bls.gov/timeseries/{series}"
    prev = rows[1]
    if series == "LNS14000000":
        text = f"The U.S. unemployment rate was {v}% in {month_year(period)}, against {prev[2]}% in {month_year(prev[0] + '-' + prev[1][1:])}."
        return [_fact(text, label, page, f"BLS {series}: {prev[0]} {prev[1]} {prev[2]}; {y} {p} {v}", "stat", url)]
    out = []
    if (int(prev[0]), int(prev[1][1:])) == _before(int(y), int(p[1:])):
        mom = round((float(v) / float(prev[2]) - 1) * 100, 1)
        text = (f"The U.S. {name} stood at {v} in {month_year(period)}, {abs(mom)}% {'above' if mom >= 0 else 'below'} "
                f"the {month_year(prev[0] + '-' + prev[1][1:])} level of {prev[2]}.")
        out.append(_fact(text, label, page, f"BLS {series} (CPI-U {name}): {prev[0]} {prev[1]} {prev[2]}; {y} {p} {v}; change {v} / {prev[2]} = {mom}%", "stat", url))
    # the newest month with a year-ago value: a month BLS did not collect (October 2025) leaves a gap, and a rate is never worked out across one
    for y2, p2, v2 in rows:
        ago = next((x for x in rows if x[0] == str(int(y2) - 1) and x[1] == p2), None)
        if ago:
            change = round((float(v2) / float(ago[2]) - 1) * 100, 1)
            text = (f"The U.S. {name} was {abs(change)}% {'above' if change >= 0 else 'below'} its level a year earlier in "
                    f"{month_year(y2 + '-' + p2[1:])}, at {v2} against {ago[2]}.")
            out.append(_fact(text, label, page, f"BLS {series} (CPI-U {name}): {ago[0]} {ago[1]} {ago[2]}; {y2} {p2} {v2}; change {v2} / {ago[2]} = {change}%", "stat", url))
            break
    return out


# Daily market prices (yields, oil) are deliberately absent: FRED prints them two to seven days late, and a "latest" price
# from Tuesday beside a story about Friday's session reads as a contradiction (found in the 2026-11-28 samples).
FRED = {  # series -> (agency behind it, what it measures, freshness days)
    "FEDFUNDS": ("Federal Reserve Board via FRED", "The effective federal funds rate", 75),
    "A191RL1Q225SBEA": ("U.S. Bureau of Economic Analysis via FRED", "U.S. real GDP growth at an annual rate", 200),
}


def _fred_rows(ctx, series):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
    return url, [l.split(",")[:2] for l in ctx.text(url).splitlines()[1:] if "," in l and l.split(",")[1] not in (".", "")]


def fred(ctx, series):
    """FRED's public CSV download: no key is needed or stored (checked 2026-11-28: no FRED secret exists)."""
    label, what, days = FRED[series]
    url, rows = _fred_rows(ctx, series)
    if len(rows) < 2 or not fresh(rows[-1][0], ctx.now, days):
        ctx.note(f"fred {series}: no fresh print")
        return []
    (pd, pv), (dt, v) = rows[-2], rows[-1]
    prep, when = ("in", month_year) if series == "FEDFUNDS" else ("for", lambda d: f"the quarter that began {day(d)}")
    text = f"{what} was {v}% {prep} {when(dt)}, against {pv}% {prep} {when(pd)}."
    return [_fact(text, label, f"https://fred.stlouisfed.org/series/{series}", f"FRED {series}: {pd} {pv}; {dt} {v}", "stat", url)]


def fed_target(ctx):
    """The Federal Reserve's target range for the federal funds rate and the day it last moved (FRED DFEDTARL/DFEDTARU:
    the range stands until the FOMC changes it, so a print from a few days ago is still the current one)."""
    (ul, up), (ll, lo) = _fred_rows(ctx, "DFEDTARU"), _fred_rows(ctx, "DFEDTARL")
    if len(up) < 2 or len(lo) < 2 or not fresh(up[-1][0], ctx.now, 10):
        ctx.note("fred DFEDTAR: no fresh print")
        return []
    i = len(up) - 1
    while i > 0 and up[i - 1][1] == up[-1][1]:
        i -= 1
    since, before = up[i][0], (up[i - 1][1] if i else None)
    low_before = next((r[1] for r in lo if r[0] == up[i - 1][0]), None) if i else None
    text = f"The Federal Reserve's target range for the federal funds rate is {lo[-1][1]}% to {up[-1][1]}%, in place since {day(since)}."
    ev = f"FRED DFEDTARL {lo[-1][0]} {lo[-1][1]}; DFEDTARU {up[-1][0]} {up[-1][1]}; the upper limit changed on {since}"
    if before and low_before:
        text = text[:-1] + f", up from {low_before}% to {before}%." if float(up[-1][1]) > float(before) else text[:-1] + f", down from {low_before}% to {before}%."
        ev += f" from {before}; lower limit before {low_before}"
    return [_fact(text, "Federal Reserve Board via FRED", "https://fred.stlouisfed.org/series/DFEDTARU", ev, "stat", f"https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARU")]


def ons_cpi(ctx):
    url = "https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/d7g7/mm23/data"
    d = ctx.json(url)
    rows = d.get("months") or []
    if len(rows) < 2:
        return []
    p, c = rows[-2], rows[-1]
    when = lambda r: f"{r['month']} {r['year']}"  # noqa: E731
    if not fresh(f"{c['year']}-{MONTHS.index(c['month']) + 1:02d}", ctx.now, 100):
        ctx.note("ons cpi: no fresh print")
        return []
    text = f"The Office for National Statistics puts annual consumer price inflation at {c['value']}% for {when(c)}, against {p['value']}% in {when(p)}."
    ev = f"ONS D7G7 {d.get('description', {}).get('title', '')}: {p['date']} {p['value']}; {c['date']} {c['value']}; updated {c.get('updateDate', '')}"
    return [_fact(text, "UK Office for National Statistics", "https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/d7g7/mm23", ev, "stat", url)]


def macro_plan(story):
    """The official series a story is about: [callable(ctx)], at most three. Words decide; a story that names no
    indicator and no region gets nothing."""
    t = f"{story.get('title', '')} {story.get('summary', '')[:300]}"
    low = t.lower()
    geo = next((GEO[k] for k in sorted(GEO, key=len, reverse=True) if re.search(rf"\b{k}\b", low)), None)
    us = re.search(r"\bU\.?S\.?\b|\bAmerica|\bFed\b|Federal Reserve|Treasur|\bWall Street\b", t)
    uk = re.search(r"\bUK\b|\bU\.K\.|\bBritain|\bBritish\b|Bank of England", t)
    plans = {}
    if re.search(r"\binflation\b|consumer prices|\bCPI\b", t, re.I):
        if geo:
            plans["hicp"] = lambda c, g=geo: eurostat(c, "prc_hicp_manr", f"geo={g[0]}&coicop=CP00&unit=RCH_A", g[0], g[1], "annual HICP inflation", "%")
        elif uk:
            plans["ons"] = ons_cpi
        elif us:
            plans["cpi"] = lambda c: bls(c, "CUUR0000SA0")
            if re.search(r"grocer|food prices|food at home|supermarket", t, re.I):
                plans["food"] = lambda c: bls(c, "CUUR0000SAF11")
    if re.search(r"unemployment|jobless|jobs report|payrolls", t, re.I):
        if geo:
            plans["une"] = lambda c, g=geo: eurostat(c, "une_rt_m", f"geo={g[0]}&s_adj=SA&age=TOTAL&sex=T&unit=PC_ACT", g[0], g[1], "the unemployment rate", "%")
        elif us:
            plans["une"] = lambda c: bls(c, "LNS14000000")
    if re.search(r"\bECB\b|European Central Bank|Lagarde", t):
        plans["ecb"] = ecb_rates
    if re.search(r"\bFed\b|Federal Reserve|FOMC|fed funds|Powell", t):
        plans["target"] = fed_target
        plans["fed"] = lambda c: fred(c, "FEDFUNDS")
    if re.search(r"\bGDP\b|economic growth|economy (?:grew|shrank|contracted)", t) and us and not uk:
        plans["gdp"] = lambda c: fred(c, "A191RL1Q225SBEA")
    plans = list(plans.values())
    return plans[:3]


def macro(story, ctx):
    out = []
    for plan in macro_plan(story):
        try:
            out += plan(ctx)
        except Exception as e:  # noqa: BLE001  one dead statistics API never stops the others
            ctx.note(f"macro: {type(e).__name__}: {e}")
    return out


# ---------------------------------------------------------------------------------------------------------------
# SEC EDGAR: a US-listed company's filings and XBRL facts

SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SEC_ITEMS = {"1.01": "an entry into a material agreement", "1.02": "the end of a material agreement", "2.01": "the completion of an acquisition or disposal",
             "2.02": "results of operations", "2.03": "a new financial obligation", "2.05": "exit or disposal costs",
             "2.06": "a material impairment", "3.01": "a listing notice", "5.02": "a change of directors or officers",
             "5.07": "shareholder vote results", "7.01": "a Regulation FD disclosure", "8.01": "other events"}
CORP = re.compile(r"\b(?:inc|corp|corporation|co|company|ltd|limited|plc|holdings|group|the|de|nv|sa|ag|llc|lp|class [a-c])\b\.?", re.I)


def _core(name):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", CORP.sub(" ", name.lower()))).strip()


def match_registrant(story, tickers):
    """The SEC registrant a title names: a capitalised name in the title that is a registrant's whole name (or its
    ticker in brackets in the summary). A word that is also a plain word or surname is not read as a company."""
    rows = list(tickers.values()) if isinstance(tickers, dict) else tickers
    title = story.get("title", "")
    text = f"{title} {story.get('summary', '')}"
    for m in re.finditer(r"\((?:NASDAQ|NYSE|Nasdaq)[:\s]+([A-Z.]{1,5})\)", text):
        for r in rows:
            if r["ticker"] == m.group(1):
                return r
    words = re.findall(r"[A-Za-z0-9&.'-]+", title)
    grams = {}
    for n in (3, 2, 1):
        for i in range(len(words) - n + 1):
            chunk = words[i:i + n]
            if chunk[0][0].isupper() and all(w[0].isupper() or w.lower() in ("of", "and", "&") for w in chunk):
                grams[_core(" ".join(chunk))] = " ".join(chunk)
    best = None
    for r in rows:
        core = _core(r["title"])
        if core in grams and len(core) >= 4 and core not in copy.AMBIGUOUS_BRANDS and core not in copy.FILLER and (best is None or len(core) > len(_core(best["title"]))):
            best = r
    return best


def _days(a, b):
    return (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days


def sec_concept(ctx, cik, tags, ua):
    """(latest, year_ago) rows of the first tag with a quarterly or annual value in a 10-Q or 10-K."""
    for tag in tags:
        try:
            d = ctx.json(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{tag}.json", ua)
        except Exception:  # noqa: BLE001  a company that does not use this tag
            continue
        rows = [r for r in d.get("units", {}).get("USD", []) if r.get("form") in ("10-Q", "10-K") and r.get("start") and r.get("end")
                and (80 <= _days(r["start"], r["end"]) <= 100 or 350 <= _days(r["start"], r["end"]) <= 380)]
        if not rows:
            continue
        last = max(rows, key=lambda r: (r["end"], r["filed"]))
        span = 90 if _days(last["start"], last["end"]) < 200 else 365
        prior = [r for r in rows if abs(_days(r["end"], last["end"]) - 365) <= 12 and abs(_days(r["start"], r["end"]) - span) <= 15]
        return tag, last, (max(prior, key=lambda r: r["filed"]) if prior else None)
    return None, None, None


def sec_company(story, ctx):
    if not ctx.contact:
        ctx.note("sec: no generic contact configured (desk.json contact_email or DESK_SEC_CONTACT); data.sec.gov refuses a client without one")
        return []
    ua = f"Boardread news desk {ctx.contact}"
    reg = match_registrant(story, ctx.json(SEC_TICKERS, ua))
    if not reg:
        return []
    cik, name = int(reg["cik_str"]), reg["title"].title() if reg["title"].isupper() else reg["title"]
    short = re.sub(r",?\s+(?:Inc|Corp|Corporation|Co|Ltd|plc|N\.V\.)\.?$", "", name)
    out = []
    for tags, what in ((("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"), "revenue"),
                       (("NetIncomeLoss", "ProfitLoss"), "net income")):
        tag, last, prior = sec_concept(ctx, cik, tags, ua)
        if not last:
            continue
        span = "quarter" if _days(last["start"], last["end"]) < 200 else "year"
        v = last["val"]
        loss = what == "net income" and v < 0
        noun = "net loss" if loss else what
        text = (f"{short} reported {noun} of {money(abs(v) if loss else v)} for the {span} ended {day(last['end'])}, in its {last['form']} "
                f"filed {day(last['filed'])}")
        ev = f"SEC EDGAR {tag} CIK{cik:010d} {last['form']} filed {last['filed']}: {last['start']} to {last['end']} val {last['val']}"
        if prior:
            pv = prior["val"]
            text += f", against {money(abs(pv) if pv < 0 else pv)} a year earlier"
            ev += f"; year earlier {prior['start']} to {prior['end']} val {prior['val']}"
        acc = last["accn"].replace("-", "")
        page = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{last['accn']}-index.htm"
        out.append(_fact(text + ".", "U.S. Securities and Exchange Commission (EDGAR)", page, ev, "filing",
                         f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{tag}.json"))
    sub = ctx.json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", ua)
    rec = sub.get("filings", {}).get("recent", {})
    pub = (story.get("published") or ctx.now.isoformat())[:10]
    for i, form in enumerate(rec.get("form", [])):
        filed, items = rec["filingDate"][i], rec.get("items", [""] * (i + 1))[i]
        if form == "8-K" and 0 <= _days(filed, pub) <= 4 and items:
            known = [SEC_ITEMS[x] for x in items.split(",") if x in SEC_ITEMS]
            if known:
                acc = rec["accessionNumber"][i]
                text = f"{short} filed an 8-K on {day(filed)} under item{'s' if len(known) > 1 else ''} {', '.join(x for x in items.split(',') if x in SEC_ITEMS)}: {', '.join(known)}."
                ev = f"SEC EDGAR submissions CIK{cik:010d}: form 8-K filed {filed} items {items}"
                out.append(_fact(text, "U.S. Securities and Exchange Commission (EDGAR)",
                                 f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{acc}-index.htm", ev, "filing",
                                 f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
            break
    return out


# ---------------------------------------------------------------------------------------------------------------
# a primary text (a regulator's release, a company's own release): the model extracts, code checks every word

HTML_DROP = re.compile(r"<(script|style|nav|header|footer|form|svg)\b.*?</\1>", re.S | re.I)
WIRES = ("prnewswire.com", "businesswire.com", "globenewswire.com", "accesswire.com")
REGULATORS = (  # name, label, pattern on the story, feed (None: no public feed or it refuses automated clients), host
    ("SEC", "U.S. Securities and Exchange Commission", r"\bSEC\b|Securities and Exchange Commission", "https://www.sec.gov/news/pressreleases.rss", "sec.gov"),
    ("Fed", "Federal Reserve Board", r"\bFed\b|Federal Reserve|FOMC", "https://www.federalreserve.gov/feeds/press_all.xml", "federalreserve.gov"),
    ("EC", "European Commission", r"European Commission|EU Commission|\bBrussels\b|EU antitrust", "https://ec.europa.eu/commission/presscorner/api/rss?language=en", "ec.europa.eu"),
    ("CMA", "UK Competition and Markets Authority", r"\bCMA\b|Competition and Markets Authority",
     "https://www.gov.uk/search/news-and-communications.atom?organisations%5B%5D=competition-and-markets-authority", "gov.uk"),
)
ACTION = re.compile(r"\b(?:charges?|charged|fines?|fined|sues?|sued|settle\w*|probe|investigat\w+|approves?|approved|clears?|cleared|"
                    r"blocks?|blocked|rule[sd]?|ruling|orders?|ordered|opens?|launch\w*|bans?|banned|penalt\w+|enforcement|merger|rate decision|"
                    r"findings?|market study|inquiry|decision|propos\w+|consultation|warns?|finds?)\b", re.I)


def page_text(html):
    h = HTML_DROP.sub(" ", html)
    return re.sub(r"\s+", " ", feeds.html.unescape(feeds.TAG.sub(" ", h))).strip()[:PRIMARY_CHARS]


def release_text(ctx, url):
    """(text, site name) of a primary page. The Commission's press corner is a script-built page: its text comes from the
    public document API behind it. sec.gov refuses a client with no declared contact (see Ctx)."""
    m = re.match(r"https://ec\.europa\.eu/commission/presscorner/detail/(?:en/)?([a-z]+)_(\d+)_(\d+)$", url)
    if m:
        d = ctx.json(f"https://ec.europa.eu/commission/presscorner/api/documents?reference={m.group(1).upper()}/{m.group(2)}/{m.group(3)}&language=en")
        res = d.get("docuLanguageResource") or {}
        return page_text(f"{res.get('title', '')}. {res.get('subtitle', '')}. {res.get('htmlContent', '')}"), "European Commission"
    host = urlsplit(url).hostname or ""
    if host.endswith("sec.gov"):
        if not ctx.contact:
            ctx.note("sec.gov release: no generic contact configured")
            return "", ""
        html = ctx.text(url, f"Boardread news desk {ctx.contact}")
    else:
        html = ctx.text(url)
    main = re.search(r"<main\b.*?</main>", html, re.S | re.I)
    return page_text(main.group(0) if main else html), site_name(html, url)


# how a primary source is named on the page: its agency or company, not its host
NAMES = {"ons.gov.uk": "UK Office for National Statistics", "nrf.com": "National Retail Federation", "sec.gov": "U.S. Securities and Exchange Commission",
         "federalreserve.gov": "Federal Reserve Board", "ecb.europa.eu": "European Central Bank", "ec.europa.eu": "European Commission",
         "ftc.gov": "U.S. Federal Trade Commission", "bafin.de": "BaFin", "bankofengland.co.uk": "Bank of England", "bls.gov": "U.S. Bureau of Labor Statistics",
         "bea.gov": "U.S. Bureau of Economic Analysis", "eurostat.eu": "Eurostat", "gov.uk": "UK government (GOV.UK)"}


def site_name(html, url):
    host = (urlsplit(url).hostname or "").removeprefix("www.")
    for h, name in NAMES.items():
        if host == h or host.endswith("." + h):
            return name
    m = re.search(r'property=["\']og:site_name["\'][^>]*content=["\']([^"\']+)', html) or re.search(r'content=["\']([^"\']+)["\'][^>]*property=["\']og:site_name', html)
    return feeds.html.unescape(m.group(1)).strip() if m else (urlsplit(url).hostname or "").removeprefix("www.")


EXTRACT = """You read one primary document (a regulator's or a company's own release) for a news desk. The desk already has the
story from a newsroom, shown below. Return a JSON array of at most 4 objects {{"fact": ..., "quote": ...}}, or [] when the
document adds nothing solid.
- fact: ONE plain sentence of at most 28 words, in your own words. It adds something the newsroom text lacks: a figure,
  a date, the legal basis, a named party, a stated next step. Never a run of six words copied from the document or from
  the newsroom text. About the story's own subject: skip site furniture, update dates, file formats and anything the
  story is not about. American English, no em or en dashes, no opinion, no adjective the document does not use, no
  "amid", "signals", "underscores".
- quote: the exact words of the document the fact rests on, at most 30 words, copied character for character. Every
  number in the fact is in the quote.

NEWSROOM TEXT:
{story}

DOCUMENT ({label}):
{doc}

Return the JSON array only."""


def _sentences_around(doc, quote):
    """The quote widened to the whole sentence or sentences of the document that hold it (at most 80 words): a model
    quotes the clause and leaves a number in the sentence's other half."""
    squeezed = re.sub(r"\s+", " ", doc)
    i = squeezed.lower().find(re.sub(r"\s+", " ", quote).lower())
    if i < 0:
        return quote
    start = max(squeezed.rfind(". ", 0, i) + 2, 0) if squeezed.rfind(". ", 0, i) >= 0 else 0
    end = squeezed.find(". ", i + len(quote))
    end = len(squeezed) if end < 0 else end + 1
    out = squeezed[start:end].strip()
    return out if len(out.split()) <= 80 else quote


def extract_facts(ctx, story, doc, label, url, kind="release"):
    """Facts from a primary text. The model proposes; a fact stands only when its quote is in the document, every
    number is in the quote, and no run of six words is the document's or the newsroom's."""
    reply = ctx.ask(EXTRACT.format(story=copy.source_text(story)[:1800], label=label, doc=doc[:PRIMARY_CHARS]))
    m = re.search(r"\[.*\]", reply or "", re.S)
    if not m:
        return []
    try:
        rows = json.loads(m.group(0))
    except ValueError:
        return []
    squeeze = lambda x: re.sub(r"\s+", " ", x or "").strip().lower()  # noqa: E731
    low = squeeze(doc)
    out = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict) or not isinstance(r.get("fact"), str) or not isinstance(r.get("quote"), str):
            continue
        fact, quote_ = r["fact"].translate(copy.DASHES).strip(), r["quote"].strip()
        if len(quote_.split()) < 3 or squeeze(quote_) not in low or shared_run(fact, doc) or shared_run(fact, quote_):
            continue
        out.append(_fact(fact, label, url, _sentences_around(doc, quote_), kind))
    return out


def primary_links(hrefs):
    """The links an RSS item carries that lead to a primary source: a wire release, a regulator, a company's own
    investor or newsroom page. Nothing else is ever fetched from an item."""
    from . import outlets
    news = set(outlets._domain_map())  # registrable domains of the newsrooms we read: their pages are never fetched
    out = []
    for u in hrefs or []:
        p = urlsplit(u)
        host = (p.hostname or "").removeprefix("www.")
        first = host.split(".")[0]
        # a regulator or wire whose own feed we also read (the SEC, the Fed, 2026-11-28) is still a primary source
        official = any(host == w or host.endswith("." + w) for w in WIRES) or any(host == r[4] or host.endswith("." + r[4]) for r in REGULATORS)
        if p.scheme != "https" or re.fullmatch(r"[\d.:]+|localhost", host) or (".".join(host.split(".")[-2:]) in news and not official):
            continue
        if official \
                or first in ("investor", "investors", "ir", "newsroom", "pressroom") \
                or re.search(r"/(?:investors?|newsroom|press-?releases?|pressroom|media-center)(?:/|$)", p.path):
            if u not in out:
                out.append(u)
    return out


def press_release(story, ctx):
    out = []
    for u in primary_links(story.get("hrefs"))[:2]:
        doc, name = release_text(ctx, u)
        if doc:
            out += extract_facts(ctx, story, doc, name, u, "release")
    return out


def regulator(story, ctx):
    from . import rank
    t = f"{story.get('title', '')} {story.get('summary', '')[:300]}"
    if not ACTION.search(t):
        return []
    pub = datetime.fromisoformat(story["published"]) if story.get("published") else ctx.now
    for name, label, pat, feed, host in REGULATORS:
        if not feed or not re.search(pat, story.get("title", "") + " " + story.get("summary", "")[:200]):
            continue
        try:
            items = feeds.parse_xml(ctx.raw(feed), name)
        except Exception as e:  # noqa: BLE001
            ctx.note(f"{name}: feed {type(e).__name__}")
            continue
        cands = [i for i in items if i["url"].startswith("https://") and (not i["published"] or abs((pub - i["published"]).days) <= 3)
                 and rank.similar(rank.tokens(story["title"] + " " + story.get("summary", "")), rank.tokens(i["title"] + " " + i.get("summary", "")))]
        if not cands:
            continue
        best = max(cands, key=lambda i: len(rank.tokens(i["title"]) & rank.tokens(story["title"])))
        doc, _ = release_text(ctx, best["url"])
        return extract_facts(ctx, story, doc, label, best["url"], "release") if doc else []
    return []


# ---------------------------------------------------------------------------------------------------------------
# the run: top stories first, a few an hour

ADAPTERS = (press_release, regulator, macro, sec_company)


def _log():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {"runs": []}


def used_this_hour(log, now):
    return sum(1 for r in log.get("runs", []) if datetime.fromisoformat(r["at"]) > now - timedelta(hours=1))


def regulator_wanted(story):
    t = f"{story.get('title', '')} {story.get('summary', '')[:200]}"
    return bool(ACTION.search(t) and any(r[3] and re.search(r[2], t) for r in REGULATORS))


def eligible(story, ctx):
    """A story worth a look: an indicator it is about, a primary link it carries, a regulator it names, or (with a
    SEC contact) a company it names. A story with none of these costs no request and no share of the hour."""
    if macro_plan(story) or primary_links(story.get("hrefs")) or regulator_wanted(story):
        return True
    if not ctx.contact:
        return False
    try:
        return bool(match_registrant(story, ctx.json(SEC_TICKERS, f"Boardread news desk {ctx.contact}")))
    except Exception as e:  # noqa: BLE001
        ctx.note(f"sec tickers: {type(e).__name__}: {e}")
        return False


def enrich_story(story, ctx):
    facts = []
    for adapter in ADAPTERS:
        try:
            facts += adapter(story, ctx)
        except Exception as e:  # noqa: BLE001  a dead source costs its own facts only
            ctx.note(f"{adapter.__name__}: {type(e).__name__}: {e}")
    kept, dropped = gate_facts(story, facts)
    story["enrich_dropped"] = dropped
    if len(kept) >= MIN_FACTS:
        story["enrich"] = {"facts": kept, "at": ctx.now.isoformat(timespec="seconds")}
    return kept


def run(stories, ctx=None, limit=PER_HOUR, log=True):
    """Enrich the highest-scored eligible stories, at most `limit` an hour (state/enrich.json counts every attempt,
    successful or not, so a run that finds nothing still spends its share). Returns [(title, n facts)]."""
    ctx = ctx or live_ctx()
    state = _log() if log else {"runs": []}
    budget = limit - used_this_hour(state, ctx.now)
    done = []
    for s in sorted(stories, key=lambda s: -s.get("score", 0)):
        if budget <= 0:
            break
        if s.get("enrich") or not eligible(s, ctx):
            continue
        kept = enrich_story(s, ctx)
        budget -= 1
        state["runs"].append({"at": ctx.now.isoformat(timespec="seconds"), "url": s.get("url", ""), "facts": len(kept)})
        done.append((s["title"], len(kept)))
    if log:
        state["runs"] = [r for r in state["runs"] if datetime.fromisoformat(r["at"]) > ctx.now - timedelta(hours=48)]
        try:
            STATE.parent.mkdir(exist_ok=True)
            STATE.write_text(json.dumps(state, indent=1))
        except OSError:
            pass
    return done


# ---------------------------------------------------------------------------------------------------------------
# the writer's section

def facts_of(story):
    return (story.get("enrich") or {}).get("facts") or []


def heading(story_or_rows):
    kinds = {r.get("kind") for r in story_or_rows}
    return "By the numbers" if kinds & {"stat", "filing"} else "Context"


def check_context(story, rows):
    """The sentences of the writer's "context" that stand: each one sentence, numbers and words from the story's
    facts only, none copied from the newsroom, none a restatement of the dek or report. Fewer than two valid
    sentences and the facts' own checked sentences stand in; fewer than two facts, nothing. Returns
    [{"text", "label", "url", "evidence", "kind"}]."""
    from . import desk
    facts = facts_of(story)
    if len(facts) < MIN_FACTS:
        return []
    pool = " ".join(f["text"] + " " + f["evidence"] for f in facts)
    rss = copy.source_text(story)
    shown = " ".join([story.get("dek", ""), copy.body_of(story.get("linkedin_post", "")), story.get("headline", "")])
    kept = []
    for x in rows if isinstance(rows, list) else []:
        if not isinstance(x, str):
            continue
        x = x.translate(copy.DASHES).strip()
        words = len(x.split())
        if (not x.endswith(".") or len(copy.sentences(x)) != 1 or words > MAX_WORDS + 6 or words < 6 or number_problems(x, pool)
                or copy.ungrounded(x, pool) or copy.tells(x) or desk.SLOP.search(x) or copy.HYPE.search(x) or copy.NOT_BUT.search(x)
                or shared_run(x, rss) or copy.QUOTE.search(x) or copy.repeats(x, shown, share=0.8)
                or any(copy.repeats(x, k["text"], share=0.8) for k in kept)):
            continue
        mine = copy._stems(x, short=True)
        best = max(facts, key=lambda f: len(mine & copy._stems(f["text"], short=True)) / max(1, len(mine)))
        if len(mine & copy._stems(best["text"], short=True)) / max(1, len(mine)) < 0.3:
            continue
        kept.append({"text": x, "label": best["label"], "url": best["url"], "evidence": pool[:900], "kind": best["kind"]})
    if len(kept) < MIN_FACTS:
        kept = [{"text": f["text"], "label": f["label"], "url": f["url"], "evidence": f["evidence"], "kind": f["kind"]} for f in facts]
    return kept[:MAX_FACTS]


def primary_sources(rows):
    """[(label, url)] one per agency or company, in order of first use; each line of the section links its own page."""
    seen, out = set(), []
    for r in rows or []:
        if r.get("url") and r["label"] not in seen:
            seen.add(r["label"])
            out.append((r["label"], r["url"]))
    return out


def audit(rows):
    """Problems with the context a post carries: each row needs a label, an https link, and numbers its evidence holds."""
    out = []
    for r in rows or []:
        if not r.get("label") or not str(r.get("url", "")).startswith("https://"):
            out.append("context line without a named, linked primary source")
        bad = number_problems(r.get("text", ""), r.get("evidence", ""))
        if bad:
            out.append(f"context numbers not in the primary text {bad}")
    return out
