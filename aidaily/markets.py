"""Official rates for the front page, the numbers page and the article context box.

Fetched at build time with urllib from the publishers' own endpoints (no key, no third party), kept in
state/markets.json, and shown with the date of the series, never the build date. Each block falls back to the last good
copy on its own, so one publisher being down leaves the others current. Brent and WTI come from the EIA and need
EIA_API_KEY (a GitHub secret); without it, or without a last-good value, the row is not rendered at all.

No equity prices and no index levels appear anywhere: only central-bank reference rates, Treasury par yields and the EIA
spot series. Attribution lines follow brand/research/market-data.md.
"""
import csv
import gzip
import html
import io
import json
import os
import re
import ssl
import subprocess
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone

from . import desk
from .feeds import CTX  # the desk's TLS context (macOS python.org builds ship no CA bundle)

E = lambda s: html.escape(str(s), quote=True)  # noqa: E731
FILE = None  # tests point this elsewhere; otherwise state/markets.json under the desk's state directory


def file():
    return FILE or desk.STATE / "markets.json"

UA = {"User-Agent": "boardread.news build (+https://boardread.news/about/)"}
ECB_DAILY = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
ECB_DFR = "https://data-api.ecb.europa.eu/service/data/FM/B.U2.EUR.4F.KR.DFR.LEV?lastNObservations=1&format=csvdata"
TREASURY = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
            "?data=daily_treasury_yield_curve&field_tdr_date_value_month={ym}")
EIA = ("https://api.eia.gov/v2/petroleum/pri/spt/data/?api_key={key}&frequency=daily&data[0]=value"
       "&facets[series][]=RBRTE&facets[series][]=RWTC&sort[0][column]=period&sort[0][direction]=desc&length=6")
CALC = "Calculated from ECB reference rates"
SRC_ECB = "Source: ECB statistics."
SRC_UST = "Source: U.S. Department of the Treasury."
SRC_EIA = "Source: U.S. Energy Information Administration."
CURVE = [("1M", "1MONTH"), ("3M", "3MONTH"), ("6M", "6MONTH"), ("1Y", "1YEAR"), ("2Y", "2YEAR"), ("3Y", "3YEAR"),
         ("5Y", "5YEAR"), ("7Y", "7YEAR"), ("10Y", "10YEAR"), ("20Y", "20YEAR"), ("30Y", "30YEAR")]


def _text(raw):
    """The ECB data API answers gzip even when it was not asked to."""
    return (gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw).decode("utf-8", "replace")


def _get(url, timeout=20):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout, context=CTX) as r:  # noqa: S310 (fixed https endpoints)
            return _text(r.read())
    except OSError as e:
        print(f"markets: urllib failed for {url.split('?')[0]} ({e!r}); trying curl")
    # a CA file without the ECB's intermediate certificate (the desk's Mac) or a stalled connection: curl takes its own route
    out = subprocess.run(["curl", "-fsS", "--compressed", "--retry", "1", "--max-time", str(timeout), "-A", UA["User-Agent"], url],
                         check=True, capture_output=True, timeout=timeout + 5).stdout
    return _text(out)


def parse_ecb(xml_text):
    """{"date": "YYYY-MM-DD", "rates": {"USD": per-euro rate, ...}} from the ECB daily reference-rate file."""
    day, rates = None, {}
    for el in ET.fromstring(xml_text).iter():
        if el.tag.endswith("Cube"):
            if el.get("time"):
                day = el.get("time")
            elif el.get("currency"):
                rates[el.get("currency")] = float(el.get("rate"))
    if not day or not all(k in rates for k in ("USD", "JPY", "GBP", "CNY")):
        raise ValueError("ECB file lacks the currencies shown")
    return {"date": day, "rates": {k: rates[k] for k in ("USD", "JPY", "GBP", "CNY")}}


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
    """{"brent": {"date", "value", "prev"}, "wti": ...} from the spot-price response (newest rows first)."""
    by = {}
    for row in js["response"]["data"]:
        by.setdefault(row["series"], []).append((row["period"], float(row["value"])))
    out = {}
    for key, name in (("RBRTE", "brent"), ("RWTC", "wti")):
        rows = sorted(by.get(key, []), reverse=True)
        if rows:
            out[name] = {"date": rows[0][0], "value": rows[0][1], "prev": rows[1][1] if len(rows) > 1 else None}
    return out


def fetch():
    """Fresh blocks that could be fetched now; a publisher that fails is simply missing from the result."""
    got = {}
    jobs = {"fx": lambda: parse_ecb(_get(ECB_DAILY)), "dfr": lambda: parse_dfr(_get(ECB_DFR))}

    def treasury():
        today = datetime.now(timezone.utc)
        rows, y, m = [], today.year, today.month
        for _ in range(2):  # a month's first day has no previous day in its own file
            rows = parse_treasury(_get(TREASURY.format(ym=f"{y}{m:02d}"))) + rows
            if len(rows) >= 2:
                break
            y, m = (y, m - 1) if m > 1 else (y - 1, 12)
        if len(rows) < 2:
            raise ValueError("no Treasury rows")
        return rows[-2:]
    jobs["ust"] = treasury
    if os.environ.get("EIA_API_KEY"):
        def oil():
            # the EIA API is slow (a 20 s limit timed out on the Actions runner); one patient try, then one more
            for attempt in (1, 2):
                try:
                    return parse_eia(json.loads(_get(EIA.format(key=os.environ["EIA_API_KEY"]), timeout=50)))
                except (OSError, subprocess.SubprocessError):
                    if attempt == 2:
                        raise
        jobs["oil"] = oil
    for key, job in jobs.items():
        try:
            got[key] = job()
        except Exception as e:  # noqa: BLE001 (any network or format failure means: keep the last good block)
            print(f"markets: {key} not refreshed ({e!r})")
    return got


def load(live=True):
    """The markets data to render: fresh blocks over the last good file, which is rewritten when something was fresh.
    None when there is nothing at all (the market sections are then left out of the pages)."""
    old = desk._load(file(), {})
    new = fetch() if live else {}
    data = {**old, **new}
    if not os.environ.get("EIA_API_KEY"):
        data.pop("oil", None)  # never show an oil price the key did not just fetch or keep
    if new:
        data["fetched"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        file().parent.mkdir(parents=True, exist_ok=True)
        file().write_text(json.dumps({**old, **new, "fetched": data["fetched"]}, indent=1) + "\n")
    return data if data.get("fx") or data.get("ust") else None


def dmy(d):
    return date.fromisoformat(d).strftime("%-d %b %Y")


def signed(x, nd=2):
    return ("+" if x > 0 else "−" if x < 0 else "") + f"{abs(x):.{nd}f}"


def rows(m):
    """Cells for the rates board: dicts with k (label), v (value), d (change or ''), date and src."""
    out = []
    if m.get("fx"):
        r, d = m["fx"]["rates"], dmy(m["fx"]["date"])
        out += [dict(k="EUR/USD", v=f"{r['USD']:.4f}", d="", date=d, src="ECB reference rate"),
                dict(k="USD/JPY", v=f"{r['JPY'] / r['USD']:.2f}", d="", date=d, src=CALC),
                dict(k="GBP/USD", v=f"{r['USD'] / r['GBP']:.4f}", d="", date=d, src=CALC),
                dict(k="USD/CNY", v=f"{r['CNY'] / r['USD']:.4f}", d="", date=d, src=CALC)]
    if m.get("ust"):
        u, u0 = m["ust"][-1], m["ust"][-2] if len(m["ust"]) > 1 else None
        for label, k in (("US 10-year", "10YEAR"), ("US 2-year", "2YEAR")):
            out.append(dict(k=label, v=f"{u[k]:.2f}%", d=signed(u[k] - u0[k]) if u0 and k in u0 else "", date=dmy(u["date"]), src="US Treasury par yield"))
    for k, label in (("brent", "Brent spot"), ("wti", "WTI spot")):
        o = (m.get("oil") or {}).get(k)
        if o:
            out.append(dict(k=label, v=f"${o['value']:.2f}", d=signed(o["value"] - o["prev"]) if o.get("prev") else "", date=dmy(o["date"]), src="EIA daily spot price"))
    return out


def attribution(m):
    parts = ["Sources: ECB statistics; U.S. Department of the Treasury" + ("; U.S. Energy Information Administration" if m.get("oil") else "")
             + ". Data as of the dates shown; for information only."]
    if m.get("fx"):
        parts.append("Currencies: ECB euro reference rates, for information only; USD/JPY, GBP/USD and USD/CNY are calculated from them.")
    if m.get("oil"):
        parts.append(SRC_EIA)
    return " ".join(parts)


def rates_box(m, base="", cls=""):
    """The rates board as a block: one row per series with its date and source, then the curve and the attribution."""
    cells = rows(m or {})
    if not cells:
        return ""
    body = "".join(f'<div class="rt"><span>{E(r["k"])}</span><b>{E(r["v"])}{f"<em>{E(r['d'])}</em>" if r["d"] else ""}</b>'
                   f'<small>{E(r["date"])} &middot; {E(r["src"])}</small></div>' for r in cells)
    return (f'<section class="rates {cls}" aria-label="Rates and currencies"><div class="sec cap"><span>Rates and currencies</span>'
            f'<a class="dm" href="{base}/numbers/">All data</a></div>{body}{curve_svg(m, 420, 200, 11, wrap=True)}'
            f'<p class="attr">{E(attribution(m))}</p></section>')


def curve_svg(m, w=560, h=240, fs=12, wrap=False):
    u = (m or {}).get("ust")
    if not u:
        return ""
    cur, prev = u[-1], u[-2] if len(u) > 1 else None
    pts = [(n, k) for n, k in CURVE if k in cur]
    vals = [cur[k] for _, k in pts] + [prev[k] for _, k in pts if prev and k in prev]
    lo, hi = int(min(vals) * 2) / 2 - 0.5, int(max(vals) * 2 + 1) / 2 + 0.0
    if hi - lo < 1:
        hi = lo + 1
    left, right, top, bot = 40, 64, 16, 28
    X = lambda i: left + (w - left - right) * i / (len(pts) - 1)  # noqa: E731
    Y = lambda v: top + (h - top - bot) * (1 - (v - lo) / (hi - lo))  # noqa: E731
    path = lambda row: " ".join(("M" if i == 0 else "L") + f"{X(i):.1f} {Y(row[k]):.1f}" for i, (_, k) in enumerate(pts) if k in row)  # noqa: E731
    grid, v = "", lo
    while v <= hi + 1e-9:
        grid += (f'<line x1="{left}" x2="{w - right}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="currentColor" stroke-opacity=".18"/>'
                 f'<text x="{left - 8}" y="{Y(v) + 4:.1f}" font-size="{fs}" text-anchor="end" fill="currentColor" fill-opacity=".65">{v:.1f}</text>')
        v += 0.5
    xs = "".join(f'<text x="{X(i):.1f}" y="{h - 8}" font-size="{fs}" text-anchor="middle" fill="currentColor" fill-opacity=".65">{n}</text>'
                 for i, (n, _) in enumerate(pts) if n in ("1M", "6M", "2Y", "5Y", "10Y", "30Y"))
    i10 = next(i for i, (n, _) in enumerate(pts) if n == "10Y") if any(n == "10Y" for n, _ in pts) else None
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


def context_for(p, m, base=""):
    """The official-data box of an article, only when its headline or summary names a region we hold a series for:
    the euro area (ECB deposit rate, EUR/USD) or the United States (Treasury 10-year and 2-year). Else ''."""
    if not m:
        return ""
    text = f'{p["headlines"][0]} {p.get("dek", "")}'
    cells, src = [], []
    if EURO.search(text) and m.get("dfr"):
        d = m["dfr"]
        cells.append(("Euro-area deposit facility rate", f"{d['value']:.2f}%", f"Since {dmy(d['since'])}."))
        if m.get("fx"):
            cells.append(("EUR/USD", f"{m['fx']['rates']['USD']:.4f}", f"ECB reference rate, {dmy(m['fx']['date'])}."))
        src.append(SRC_ECB)
    if US.search(text) and m.get("ust"):
        u = m["ust"][-1]
        cells += [("US 10-year Treasury yield", f"{u['10YEAR']:.2f}%", f"US Treasury par yield, {dmy(u['date'])}."),
                  ("US 2-year Treasury yield", f"{u['2YEAR']:.2f}%", f"US Treasury par yield, {dmy(u['date'])}.")]
        src.append(SRC_UST)
    if not cells:
        return ""
    body = "".join(f'<div class="rt"><span>{E(a)}</span><b>{E(b)}</b><small>{E(c)}</small></div>' for a, b, c in cells)
    return (f'<section class="cxb" aria-labelledby="cxh"><h2 id="cxh">Official data, for context</h2>{body}'
            f'<p class="attr">{E(" ".join(src))} Reference data for information only; it is not part of the article.</p></section>')
