"""Official rates and prices for the markets strip, the front-page block, the numbers page and the article context box.

Fetched at build time with urllib (curl as the second route) from the publishers' own endpoints, no key except the EIA's and
no third party, and kept in state/markets.json with the last good copy of each source: one publisher being down leaves the
others current. Every value is shown with the date of its series, never the build date.

  ECB reference rates, 90 days (EUR/USD; USD/JPY, GBP/USD and USD/CNY calculated from them)
  U.S. Treasury daily par yield curve, four months (10-year, 2-year, and the curve itself)
  EIA (needs EIA_API_KEY, a GitHub secret): Brent and WTI spot, US regular gasoline retail (weekly, $/gal), Henry Hub gas
  ECB deposit facility rate

No equity prices and no index levels appear anywhere. EIA rows exist only when the key fetched them: without it they are not
rendered at all, never "Pending". The euro-area fuel price of the Commission's Weekly Oil Bulletin is not included: its
reuse notice was not confirmed.
"""
import csv
import gzip
import html
import io
import json
import os
import re
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from . import desk
from .feeds import CTX  # the desk's TLS context (macOS python.org builds ship no CA bundle)

E = lambda s: html.escape(str(s), quote=True)  # noqa: E731
FILE = None  # tests point this elsewhere; otherwise state/markets.json under the desk's state directory


def file():
    return FILE or desk.STATE / "markets.json"


UA = {"User-Agent": "boardread.news build (+https://boardread.news/about/)"}
ECB_HIST = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"
ECB_DFR = "https://data-api.ecb.europa.eu/service/data/FM/B.U2.EUR.4F.KR.DFR.LEV?lastNObservations=1&format=csvdata"
TREASURY = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
            "?data=daily_treasury_yield_curve&field_tdr_date_value_month={ym}")
# the brackets are percent-encoded: an unencoded query stalled on the Actions runner while the API root answered at once
EIA = ("https://api.eia.gov/v2/{route}/data/?api_key={key}&frequency={freq}&data%5B0%5D=value&{facets}"
       "&start={start}&sort%5B0%5D%5Bcolumn%5D=period&sort%5B0%5D%5Bdirection%5D=desc&length={n}")
EIA_GROUPS = (  # route, frequency, series ids, days of history, rows
    ("petroleum/pri/spt", "daily", ("RBRTE", "RWTC"), 130, 200),
    ("petroleum/pri/gnd", "weekly", ("EMM_EPMR_PTE_NUS_DPG",), 330, 60),
    ("natural-gas/pri/fut", "daily", ("RNGWHHD",), 130, 120),
)
CALC = "Calculated from ECB reference rates"
SRC_ECB = "Source: ECB statistics."
SRC_UST = "Source: U.S. Department of the Treasury."
SRC_EIA = "Source: U.S. Energy Information Administration."
CURVE = [("1M", "1MONTH"), ("3M", "3MONTH"), ("6M", "6MONTH"), ("1Y", "1YEAR"), ("2Y", "2YEAR"), ("3Y", "3YEAR"),
         ("5Y", "5YEAR"), ("7Y", "7YEAR"), ("10Y", "10YEAR"), ("20Y", "20YEAR"), ("30Y", "30YEAR")]

# key: (label, unit, decimals, source tag, what it is, EIA series id)
SERIES = {
    "eurusd": ("EUR/USD", "", 4, "ecb", "How many US dollars one euro buys, the ECB's daily reference rate.", ""),
    "usdjpy": ("USD/JPY", "", 2, "calc", "How many Japanese yen one US dollar buys.", ""),
    "gbpusd": ("GBP/USD", "", 4, "calc", "How many US dollars one pound sterling buys.", ""),
    "usdcny": ("USD/CNY", "", 4, "calc", "How many Chinese yuan one US dollar buys.", ""),
    "brent": ("Brent", "$/bbl", 2, "eia", "The spot price of Brent crude, the benchmark for oil sold outside the United States.", "RBRTE"),
    "wti": ("WTI", "$/bbl", 2, "eia", "The spot price of West Texas Intermediate, the main US oil benchmark.", "RWTC"),
    "gasoline": ("US gasoline", "$/gal", 3, "eia", "The average US retail price of regular gasoline, weekly.", "EMM_EPMR_PTE_NUS_DPG"),
    "henryhub": ("Natural gas", "$/MMBtu", 2, "eia", "The Henry Hub spot price, the US benchmark for natural gas.", "RNGWHHD"),
    "ust10": ("US 10-year", "%", 2, "ust", "The yield on US government debt due in ten years, a base for borrowing costs.", ""),
    "ust2": ("US 2-year", "%", 2, "ust", "The yield on two-year US government debt, sensitive to expected interest rates.", ""),
}
RAIL = ("eurusd", "usdjpy", "gbpusd", "brent", "wti", "gasoline", "ust10")
STRIP = ("eurusd", "usdjpy", "brent", "gasoline", "ust10")
SOURCE_NAME = {"ecb": "ECB reference rate", "calc": CALC, "eia": "EIA", "ust": "US Treasury par yield"}
HISTORY = 100  # observations kept per series


def _text(raw):
    """The ECB data API answers gzip even when it was not asked to."""
    return (gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw).decode("utf-8", "replace")


def _get(url, timeout=20, retry_curl=True):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout, context=CTX) as r:  # noqa: S310 (fixed https endpoints)
            return _text(r.read())
    except OSError as e:
        print(f"markets: urllib failed for {url.split('?')[0]} ({e!r})" + ("; trying curl" if retry_curl else ""))
        if not retry_curl:
            raise
    # a CA file without the ECB's intermediate certificate (the desk's Mac) or a stalled connection: curl takes its own route
    out = subprocess.run(["curl", "-gfsS", "--compressed", "--max-time", str(timeout), "-A", UA["User-Agent"], url],
                         check=True, capture_output=True, timeout=timeout + 5).stdout
    return _text(out)


def parse_ecb_hist(xml_text):
    """{key: [(date, value), ...] oldest first} for the four currency series, from the ECB's daily reference-rate history."""
    days, day = {}, None
    for el in ET.fromstring(xml_text).iter():
        if el.tag.endswith("Cube"):
            if el.get("time"):
                day = el.get("time")
                days[day] = {}
            elif el.get("currency") and day:
                days[day][el.get("currency")] = float(el.get("rate"))
    out = {"eurusd": [], "usdjpy": [], "gbpusd": [], "usdcny": []}
    for d in sorted(days):
        r = days[d]
        if all(k in r for k in ("USD", "JPY", "GBP", "CNY")):
            out["eurusd"].append((d, r["USD"]))
            out["usdjpy"].append((d, r["JPY"] / r["USD"]))
            out["gbpusd"].append((d, r["USD"] / r["GBP"]))
            out["usdcny"].append((d, r["CNY"] / r["USD"]))
    if not out["eurusd"]:
        raise ValueError("ECB file lacks the currencies shown")
    return out


def parse_treasury(xml_text):
    """[{"date", "1MONTH": per cent, ...}] oldest first from the Treasury daily par yield curve feed."""
    rows = []
    for props in ET.fromstring(xml_text).iter():
        if not props.tag.endswith("}properties"):
            continue
        row = {}
        for c in props:
            name = c.tag.split("}")[-1]
            if name == "NEW_DATE" and c.text:
                row["date"] = c.text[:10]
            elif name.startswith("BC_") and not name.endswith("DISPLAY") and c.text:
                row[name[3:]] = float(c.text)
        if row.get("date") and "10YEAR" in row and "2YEAR" in row:
            rows.append(row)
    return sorted(rows, key=lambda r: r["date"])


def parse_dfr(csv_text):
    r = next(csv.DictReader(io.StringIO(csv_text)))
    return {"value": float(r["OBS_VALUE"]), "since": r["TIME_PERIOD"]}


def parse_eia(js):
    """{EIA series id: [(date, value), ...] oldest first} from an EIA v2 response."""
    by = {}
    for row in js["response"]["data"]:
        if row.get("value") not in (None, ""):
            by.setdefault(row["series"], []).append((row["period"], float(row["value"])))
    return {k: sorted(v) for k, v in by.items()}


def eia_url(route, freq, ids, days, n):
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    facets = "&".join(f"facets%5Bseries%5D%5B%5D={i}" for i in ids)
    return EIA.format(route=route, key=os.environ["EIA_API_KEY"], freq=freq, facets=facets, start=start, n=n)


def fetch():
    """Fresh blocks that could be fetched now: {"series": {key: [[date, value], ...]}, "curve": [...], "dfr": {...}}.
    A publisher that fails is simply missing from the result."""
    jobs = {"ecb": lambda: parse_ecb_hist(_get(ECB_HIST)), "dfr": lambda: parse_dfr(_get(ECB_DFR))}

    def treasury():
        now = datetime.now(timezone.utc)
        months, y, m = [], now.year, now.month
        for _ in range(4):
            months.append(f"{y}{m:02d}")
            y, m = (y, m - 1) if m > 1 else (y - 1, 12)
        with ThreadPoolExecutor(max_workers=4) as pool:
            rows = sorted((r for part in pool.map(lambda ym: parse_treasury(_get(TREASURY.format(ym=ym))), months) for r in part), key=lambda r: r["date"])
        if len(rows) < 2:
            raise ValueError("no Treasury rows")
        return rows
    jobs["ust"] = treasury
    if os.environ.get("EIA_API_KEY"):
        for i, (route, freq, ids, days, n) in enumerate(EIA_GROUPS):
            def one(route=route, freq=freq, ids=ids, days=days, n=n):
                url = eia_url(route, freq, ids, days, n)
                for attempt in (1, 2):  # the EIA data API answers slowly or with 504 at times: two tries of 30 s, no curl (it is the server, not TLS)
                    try:
                        return parse_eia(json.loads(_get(url, timeout=30, retry_curl=False)))
                    except (OSError, subprocess.SubprocessError, ValueError):
                        if attempt == 2:
                            raise
            jobs[f"eia{i}"] = one

    def run(item):
        key, job = item
        try:
            return key, job()
        except Exception as e:  # noqa: BLE001 (any network or format failure means: keep the last good block)
            print(f"markets: {key} not refreshed ({e!r})")
            return key, None
    with ThreadPoolExecutor(max_workers=8) as pool:  # a slow publisher delays the build by its own timeout, not the sum of all
        got = {k: v for k, v in pool.map(run, jobs.items()) if v is not None}
    series, out = dict(got.get("ecb") or {}), {}
    if got.get("ust"):
        series["ust10"] = [(r["date"], r["10YEAR"]) for r in got["ust"]]
        series["ust2"] = [(r["date"], r["2YEAR"]) for r in got["ust"]]
        out["curve"] = got["ust"][-2:]
    by_id = {}
    for k, v in got.items():
        if k.startswith("eia"):
            by_id.update(v)
    for key, spec in SERIES.items():
        if spec[5] and by_id.get(spec[5]):
            series[key] = by_id[spec[5]]
    out["series"] = {k: [[d, x] for d, x in v[-HISTORY:]] for k, v in series.items()}
    if got.get("dfr"):
        out["dfr"] = got["dfr"]
    return out


def load(live=True):
    """The markets data to render: fresh blocks over the last good file, which is rewritten when something was fresh.
    None when there is nothing at all (the market sections are then left out of the pages)."""
    old = desk._load(file(), {})
    new = fetch() if live else {}
    data = {**old, **{k: v for k, v in new.items() if k != "series"}}
    data["series"] = {**old.get("series", {}), **new.get("series", {})}
    stored = {**data, "series": dict(data["series"])}
    if not os.environ.get("EIA_API_KEY"):  # never show an energy price the key did not just fetch or keep
        data["series"] = {k: v for k, v in data["series"].items() if SERIES.get(k, ("", "", 0, ""))[3] != "eia"}
    if new:
        data["fetched"] = stored["fetched"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        file().parent.mkdir(parents=True, exist_ok=True)
        file().write_text(json.dumps(stored, indent=1) + "\n")
    return data if data["series"] else None


# ---------------------------------------------------------------- numbers and markup

def dmy(d):
    return date.fromisoformat(d).strftime("%-d %b %Y")


def sign_arrow(x):
    return "▲" if x > 0 else "▼" if x < 0 else "▬"


def fmt(key, v):
    unit, nd = SERIES[key][1], SERIES[key][2]
    return f"{v:.{nd}f}%" if unit == "%" else f"${v:.{nd}f}" if unit.startswith("$") else f"{v:.{nd}f}"


def stat(m, key):
    """(label, last value, date, change, percent change, history) of a series, or None. Change is against the previous observation."""
    pts = (m or {}).get("series", {}).get(key)
    if not pts:
        return None
    d, v = pts[-1]
    prev = pts[-2][1] if len(pts) > 1 else None
    ch = (v - prev) if prev is not None else None
    return SERIES[key][0], v, d, ch, (100 * ch / prev) if prev else None, pts


def change_html(key, ch, pct):
    if ch is None:
        return ""
    nd = SERIES[key][2]
    cls = "up" if ch > 0 else "down" if ch < 0 else "flat"
    pcs = "" if SERIES[key][1] == "%" or pct is None else f" ({abs(pct):.2f}%)"
    word = "up" if ch > 0 else "down" if ch < 0 else "unchanged"
    return f'<span class="chg {cls}"><span aria-hidden="true">{sign_arrow(ch)}</span><span class="sr">{word} </span>{abs(ch):.{nd}f}{pcs}</span>'


def spark(pts, w=96, h=24, n=30):
    """A minimal sparkline: the last n observations as one 1.5 px ink line with a dot on the last point. No fill, no axes."""
    vals = [v for _, v in pts[-n:]]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    X = lambda i: 2 + (w - 4) * i / (len(vals) - 1)  # noqa: E731
    Y = lambda v: 3 + (h - 6) * (1 - (v - lo) / span)  # noqa: E731
    path = " ".join(("M" if i == 0 else "L") + f"{X(i):.1f} {Y(v):.1f}" for i, v in enumerate(vals))
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" '
            f'stroke-width="1.5" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg"><path d="{path}"/>'
            f'<circle cx="{X(len(vals) - 1):.1f}" cy="{Y(vals[-1]):.1f}" r="2.2" fill="currentColor" stroke="none"/></svg>')


def rows(m, keys=RAIL):
    """The rows of a block in order: dicts with k (label), v (value text), unit, chg (markup), date, src, pts, what."""
    out = []
    for k in keys:
        s = stat(m, k)
        if s:
            label, v, d, ch, pct, pts = s
            unit = SERIES[k][1]
            out.append(dict(key=k, k=label, v=fmt(k, v), unit=unit if unit not in ("", "%") else "", chg=change_html(k, ch, pct), date=dmy(d),
                            src=SOURCE_NAME[SERIES[k][3]], pts=pts, what=SERIES[k][4], d=ch))
    return out


def attribution(m, keys=None):
    """One combined source line for the series shown."""
    have_series = (m or {}).get("series", {})
    tags = {SERIES[k][3] for k in (keys or have_series) if k in SERIES and k in have_series}
    names = [n for t, n in (("ecb", "ECB statistics"), ("ust", "U.S. Department of the Treasury"), ("eia", "U.S. Energy Information Administration"))
             if t in tags or (t == "ecb" and "calc" in tags)]
    line = ("Sources: " + "; ".join(names) + ". Series dates as shown; for information only.") if names else ""
    crosses = [SERIES[k][0] for k in ("usdjpy", "gbpusd", "usdcny") if k in have_series and (not keys or k in keys)]
    if crosses:
        line += f" {', '.join(crosses[:-1])}{' and ' if len(crosses) > 1 else ''}{crosses[-1]}: calculated from ECB reference rates."
    return line


def one_line(m):
    return attribution(m, RAIL)


def rates_box(m, base="", cls="", compact=False):
    """The block in the front-page rail: value, change with an arrow and a sparkline per row; one source line under it."""
    rs = rows(m, RAIL)
    if not rs:
        return ""
    body = "".join(f'<div class="rt"><span class="rl">{E(r["k"])}</span><b>{E(r["v"])}<small>{E(r["unit"])}</small></b><span class="rc">{r["chg"]}</span>'
                   f'<span class="rs">{spark(r["pts"])}</span><small class="rd">{E(r["date"])}</small></div>' for r in rs)
    return (f'<section class="rates {cls}" aria-label="Markets"><div class="sec"><span>Markets</span><a class="dm" href="{base}/numbers/">All data</a></div>'
            f'<div class="rtgrid">{body}</div><p class="attr">{E(attribution(m, RAIL))}</p></section>')


def strip(m, base=""):
    """The one-line markets strip under the sections row: five series with their change, and a link to all data. No indices."""
    items = []
    for k in STRIP:
        s = stat(m, k)
        if s:
            label, v, d, ch, pct, pts = s
            items.append(f'<li><span class="sl">{E(label)}</span> <b>{E(fmt(k, v))}</b> {change_html(k, ch, None)}</li>')
    if not items:
        return ""
    return f'<div class="mstrip"><ul aria-label="Markets">{"".join(items)}</ul><a href="{base}/numbers/">All data</a></div>'


def chart(pts, w=360, h=120, n=90):
    """A card chart: the last n observations as one line with the first and last date, no fill."""
    pts = pts[-n:]
    if len(pts) < 2:
        return ""
    vals = [v for _, v in pts]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    left, right, top, bot = 4, 4, 8, 22
    X = lambda i: left + (w - left - right) * i / (len(vals) - 1)  # noqa: E731
    Y = lambda v: top + (h - top - bot) * (1 - (v - lo) / span)  # noqa: E731
    path = " ".join(("M" if i == 0 else "L") + f"{X(i):.1f} {Y(v):.1f}" for i, v in enumerate(vals))
    return (f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="Last {len(pts)} observations, from {dmy(pts[0][0])} to {dmy(pts[-1][0])}" '
            f'fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">'
            f'<path d="{path}"/><circle cx="{X(len(vals) - 1):.1f}" cy="{Y(vals[-1]):.1f}" r="3" fill="currentColor" stroke="none"/>'
            f'<text x="{left}" y="{h - 5}" font-size="11" fill="currentColor" stroke="none" opacity=".75">{dmy(pts[0][0])}</text>'
            f'<text x="{w - right}" y="{h - 5}" font-size="11" text-anchor="end" fill="currentColor" stroke="none" opacity=".75">{dmy(pts[-1][0])}</text></svg>')


def cards(m):
    """The numbers page: one chart card per series with a one-line explanation, the series date and the source."""
    out = ""
    for k in ("brent", "wti", "gasoline", "henryhub", "eurusd", "usdjpy", "gbpusd", "usdcny", "ust10", "ust2"):
        s = stat(m, k)
        if not s:
            continue
        label, v, d, ch, pct, pts = s
        last90 = [x for _, x in pts[-90:]]
        unit = SERIES[k][1]
        out += (f'<article class="mcard"><h2>{E(label)}</h2><p class="mv"><b>{E(fmt(k, v))}</b>{f"<small>{E(unit)}</small>" if unit not in ("", "%") else ""} {change_html(k, ch, pct)}</p>'
                f'<div class="mch">{chart(pts)}</div><p class="what"><b>What it is.</b> {E(SERIES[k][4])}</p>'
                f'<p class="meta">Last {len(last90)} observations: low {E(fmt(k, min(last90)))}, high {E(fmt(k, max(last90)))}. Series date {dmy(d)}. {E(SOURCE_NAME[SERIES[k][3]])}.</p></article>')
    return f'<div class="mcards">{out}</div><p class="attr">{E(attribution(m))}</p>' if out else ""


def curve_svg(m, w=560, h=240, fs=12, wrap=False):
    u = (m or {}).get("curve")
    if not u:
        return ""
    cur, prev = u[-1], u[-2] if len(u) > 1 else None
    pts = [(n, k) for n, k in CURVE if k in cur]
    vals = [cur[k] for _, k in pts] + [prev[k] for _, k in pts if prev and k in prev]
    lo, hi = int(min(vals) * 2) / 2 - 0.5, int(max(vals) * 2 + 1) / 2
    if hi - lo < 1:
        hi = lo + 1
    left, right, top, bot = 40, 64, 16, 28
    X = lambda i: left + (w - left - right) * i / (len(pts) - 1)  # noqa: E731
    Y = lambda v: top + (h - top - bot) * (1 - (v - lo) / (hi - lo))  # noqa: E731
    path = lambda row: " ".join(("M" if i == 0 else "L") + f"{X(i):.1f} {Y(row[k]):.1f}" for i, (_, k) in enumerate(pts) if k in row)  # noqa: E731
    grid, v = "", lo
    while v <= hi + 1e-9:
        grid += (f'<line x1="{left}" x2="{w - right}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="currentColor" stroke-opacity=".18"/>'
                 f'<text x="{left - 8}" y="{Y(v) + 4:.1f}" font-size="{fs}" text-anchor="end" fill="currentColor" fill-opacity=".7">{v:.1f}</text>')
        v += 0.5
    xs = "".join(f'<text x="{X(i):.1f}" y="{h - 8}" font-size="{fs}" text-anchor="middle" fill="currentColor" fill-opacity=".7">{n}</text>'
                 for i, (n, _) in enumerate(pts) if n in ("1M", "6M", "2Y", "5Y", "10Y", "30Y"))
    i10 = next((i for i, (n, _) in enumerate(pts) if n == "10Y"), None)
    dot = f'<circle cx="{X(i10):.1f}" cy="{Y(cur["10YEAR"]):.1f}" r="3.5" fill="currentColor"/>' if i10 is not None else ""
    last = f'<text x="{X(len(pts) - 1) + 8:.1f}" y="{Y(cur[pts[-1][1]]) + 4:.1f}" font-size="{fs + 1}" font-weight="700" fill="currentColor">{cur[pts[-1][1]]:.2f}%</text>'
    dashed = (f'<path d="{path(prev)}" fill="none" stroke="currentColor" stroke-opacity=".55" stroke-width="1.5" stroke-dasharray="4 4"/>') if prev else ""
    svg = (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="US Treasury par yield curve, {dmy(cur["date"])}, previous day dashed. '
           f'10-year {cur.get("10YEAR", 0):.2f} percent." xmlns="http://www.w3.org/2000/svg" class="curve">{grid}{dashed}'
           f'<path d="{path(cur)}" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linejoin="round"/>{dot}{last}{xs}</svg>')
    note = f'<p class="attr">Yield curve: solid {dmy(cur["date"])}' + (f", dashed {dmy(prev['date'])}" if prev else "") + ". Per cent. " + SRC_UST + "</p>"
    return f'<div class="cvsvg">{svg}</div>{note}' if wrap else svg


EURO = re.compile(r"\b(ECB|European Central Bank|euro ?zone|euro area|Lagarde)\b", re.I)
US = re.compile(r"\b(Federal Reserve|the Fed|Fed rate|Fed chair|Treasury yields?|Treasuries|Powell|FOMC)\b", re.I)
OIL = re.compile(r"\b(oil|crude|Brent|OPEC|petrol|gasoline|fuel prices?)\b", re.I)


def context_for(p, m, base=""):
    """The official-data box of an article, only when its headline or summary names a region or commodity we hold a series for:
    the euro area (ECB deposit rate, EUR/USD), the United States (Treasury yields) or oil. Else ''."""
    if not m or not m.get("series"):
        return ""
    text = f'{p["headlines"][0]} {p.get("dek", "")}'
    cells, src = [], []

    def add(key):
        s = stat(m, key)
        if not s:
            return False
        label, v, d, ch, pct, pts = s
        unit = SERIES[key][1]
        cells.append((label, fmt(key, v) + (f" {unit}" if unit not in ("", "%") else ""), f"{SOURCE_NAME[SERIES[key][3]]}, {dmy(d)}."))
        return True
    if EURO.search(text):
        if m.get("dfr"):
            d = m["dfr"]
            cells.append(("Euro-area deposit facility rate", f"{d['value']:.2f}%", f"Since {dmy(d['since'])}."))
            src.append(SRC_ECB)
        if add("eurusd"):
            src.append(SRC_ECB)
    if US.search(text) and add("ust10") and add("ust2"):
        src.append(SRC_UST)
    if OIL.search(text) and add("brent") and add("wti"):
        src.append(SRC_EIA)
    if not cells:
        return ""
    body = "".join(f'<div class="rt"><span class="rl">{E(a)}</span><b>{E(b)}</b><small class="rd">{E(c)}</small></div>' for a, b, c in cells)
    return (f'<section class="cxb" aria-labelledby="cxh"><h2 id="cxh">Official data, for context</h2>{body}'
            f'<p class="attr">{E(" ".join(dict.fromkeys(src)))} Reference data for information only; it is not part of the article.</p></section>')
