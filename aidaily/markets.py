"""Official rates and prices for the markets strip, the front-page block, the numbers page and the article context box.

Fetched at build time with urllib (curl as the second route) from the publishers' own endpoints, no key except the EIA's and
no third party, and kept in state/markets.json with the last good copy of each source: one publisher being down leaves the
others current. Every value is shown with the date of its series, never the build date.

  ECB reference rates, 90 days (EUR/USD; USD/JPY, GBP/USD and USD/CNY calculated from them)
  U.S. Treasury daily par yield curve, four months (10-year, 2-year, and the curve itself)
  EIA: Brent and WTI spot, US regular gasoline retail (weekly, $/gal), Henry Hub gas. The v2 data API is tried first when
  EIA_API_KEY is set (one try, 15 s; it times out from GitHub runners at times); otherwise, or when it fails, the keyless
  history pages under https://www.eia.gov/dnav/ carry the same published values.
  ECB deposit facility rate
  World Bank Commodity Price Data (The Pink Sheet), CC BY 4.0: monthly average prices of gold, silver, platinum, copper, aluminium,
  nickel, zinc, lead, tin and iron ore, always shown as "Oct 2026 avg". No keyless daily metals source with terms that allow
  redistribution exists (LBMA/ICE, LME and CME data are licensed), so there is no daily metal price; decisions in brand/research/market-data.md.

No equity prices and no index levels appear anywhere. A series with no data is not rendered at all, never "Pending". The euro-area fuel price of the Commission's Weekly Oil Bulletin is not included: its
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
import zipfile
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
# the keyless history pages: series id -> (path under /dnav/, frequency). The daily pages list weeks as "2026 Nov-16 to Nov-20", Mon-Fri.
DNAV = {
    "RBRTE": ("pet/hist/RBRTED.htm", "daily"),
    "RWTC": ("pet/hist/RWTCD.htm", "daily"),
    "RNGWHHD": ("ng/hist/RNGWHHDD.htm", "daily"),
    "EMM_EPMR_PTE_NUS_DPG": ("pet/hist/LeafHandler.ashx?n=PET&s=EMM_EPMR_PTE_NUS_DPG&f=W", "weekly"),
}
DNAV_BASE = "https://www.eia.gov/dnav/"
WB_PAGE = "https://www.worldbank.org/en/research/commodity-markets"  # the xlsx link carries a hash that changes every month: read it from here
WB_LINK = re.compile(r'https://thedocs\.worldbank\.org/[^"\s]*CMO-Historical-Data-Monthly\.xlsx')
WB_MONTHS = 60
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
    "eurgbp": ("EUR/GBP", "", 4, "ecb", "How many pounds sterling one euro buys, the ECB's daily reference rate.", ""),
    "eurtry": ("EUR/TRY", "", 4, "ecb", "How many Turkish lira one euro buys, the ECB's daily reference rate.", ""),
    "brent": ("Brent", "$/bbl", 2, "eia", "The spot price of Brent crude, the benchmark for oil sold outside the United States.", "RBRTE"),
    "wti": ("WTI", "$/bbl", 2, "eia", "The spot price of West Texas Intermediate, the main US oil benchmark.", "RWTC"),
    "gasoline": ("US gasoline", "$/gal", 3, "eia", "The average US retail price of regular gasoline, weekly.", "EMM_EPMR_PTE_NUS_DPG"),
    "henryhub": ("Natural gas", "$/MMBtu", 2, "eia", "The Henry Hub spot price, the US benchmark for natural gas.", "RNGWHHD"),
    "gold": ("Gold", "$/oz", 0, "wb", "The average price of gold for the month, per troy ounce; before June 2025 the London afternoon fixing.", "Gold"),
    "silver": ("Silver", "$/oz", 2, "wb", "The average price of silver for the month, per troy ounce, 99.9% refined.", "Silver"),
    "platinum": ("Platinum", "$/oz", 0, "wb", "The average price of platinum for the month, per troy ounce, 99.95% minimum purity.", "Platinum"),
    "copper": ("Copper", "$/t", 0, "wb", "The average price of copper for the month, per tonne: LME grade A cathodes, the bellwether for industrial demand.", "Copper"),
    "aluminium": ("Aluminium", "$/t", 0, "wb", "The average price of aluminium for the month, per tonne: LME high-grade primary ingots.", "Aluminum"),
    "nickel": ("Nickel", "$/t", 0, "wb", "The average price of nickel for the month, per tonne, an input to stainless steel and batteries.", "Nickel"),
    "zinc": ("Zinc", "$/t", 0, "wb", "The average price of zinc for the month, per tonne, mainly used to galvanise steel.", "Zinc"),
    "lead": ("Lead", "$/t", 0, "wb", "The average price of lead for the month, per tonne, mainly used in batteries.", "Lead"),
    "tin": ("Tin", "$/t", 0, "wb", "The average price of tin for the month, per tonne, used in solder and electronics.", "Tin"),
    "ironore": ("Iron ore", "$/dmtu", 2, "wb", "The average spot price of iron ore for the month: 62% Fe fines delivered to China, the steel industry's benchmark.", "Iron ore, cfr spot"),
    "ust10": ("US 10-year", "%", 2, "ust", "The yield on US government debt due in ten years, a base for borrowing costs.", ""),
    "ust2": ("US 2-year", "%", 2, "ust", "The yield on two-year US government debt, sensitive to expected interest rates.", ""),
}
# One order of importance for every list of daily series on the site, so the strip, the front-page block and /numbers/
# never disagree: the euro-dollar, oil, the US 10-year, the other majors, US crude and gas, the yuan, then the rest.
IMPORTANCE = ("eurusd", "brent", "ust10", "usdjpy", "gbpusd", "wti", "henryhub", "usdcny", "ust2", "eurgbp", "eurtry", "gasoline")
RAIL = IMPORTANCE[:7]  # the front-page block; the yuan stays on the strip and /numbers/
METALS = ("gold", "silver", "platinum", "copper", "aluminium", "nickel", "zinc", "lead", "tin", "ironore")
# most watched first: the euro-dollar, oil, the US 10-year, then the other majors and gas. Daily series only: gold was
# here as the World Bank's monthly average ($4,105 for October) while spot traded near $3,600 (2026-11-27); next to
# daily prices a monthly average reads as today's price whatever its label, so the metals stay on /numbers/
STRIP = IMPORTANCE[:8]
SOURCE_NAME = {"ecb": "ECB reference rate", "calc": CALC, "eia": "EIA", "ust": "US Treasury par yield", "wb": "World Bank Pink Sheet, monthly average"}
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


def _get_bytes(url, timeout=60):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout, context=CTX) as r:  # noqa: S310 (fixed https endpoint)
            return r.read()
    except OSError as e:
        print(f"markets: urllib failed for {url.split('?')[0]} ({e!r}); trying curl")
    return subprocess.run(["curl", "-gfsS", "--max-time", str(timeout), "-A", UA["User-Agent"], url], check=True, capture_output=True, timeout=timeout + 5).stdout


def pink():
    link = WB_LINK.search(_get(WB_PAGE))
    if not link:
        raise ValueError("no Pink Sheet link on the World Bank page")
    return parse_pink(_get_bytes(link.group(0)))


def parse_ecb_hist(xml_text):
    """{key: [(date, value), ...] oldest first} for the currency series, from the ECB's daily reference-rate history."""
    days, day = {}, None
    for el in ET.fromstring(xml_text).iter():
        if el.tag.endswith("Cube"):
            if el.get("time"):
                day = el.get("time")
                days[day] = {}
            elif el.get("currency") and day:
                days[day][el.get("currency")] = float(el.get("rate"))
    out = {"eurusd": [], "usdjpy": [], "gbpusd": [], "usdcny": [], "eurgbp": [], "eurtry": []}
    for d in sorted(days):
        r = days[d]
        for key, cur in (("eurgbp", "GBP"), ("eurtry", "TRY")):  # direct ECB rates, as published: no cross needed
            if cur in r:
                out[key].append((d, r[cur]))
        if all(k in r for k in ("USD", "JPY", "GBP", "CNY")):
            out["eurusd"].append((d, r["USD"]))
            out["usdjpy"].append((d, r["JPY"] / r["USD"]))
            out["gbpusd"].append((d, r["USD"] / r["GBP"]))
            out["usdcny"].append((d, r["CNY"] / r["USD"]))
    if not out["eurusd"]:
        raise ValueError("ECB file lacks the currencies shown")
    return {k: v for k, v in out.items() if v}


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


def _cell_text(si):
    return "".join(t.text or "" for t in si.iter() if t.tag.endswith("}t"))


def parse_pink(xlsx_bytes):
    """{key: [("2026-10-01", value), ...] oldest first} for the metals, from the Pink Sheet's "Monthly Prices" sheet. The columns are found
    by their header names, not their letters, and "…" cells (not published) are skipped."""
    z = zipfile.ZipFile(io.BytesIO(xlsx_bytes))
    sst = [_cell_text(si) for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rid = next(s.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id") for s in wb.iter()
               if s.tag.endswith("}sheet") and s.get("name") == "Monthly Prices")
    target = next(r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")) if r.get("Id") == rid)
    rows = []
    for r in ET.fromstring(z.read("xl/" + target.lstrip("/").removeprefix("xl/"))).iter():
        if not r.tag.endswith("}row"):
            continue
        row = {}
        for c in r:
            v = next((x for x in c if x.tag.endswith("}v")), None)
            if v is not None and v.text:
                row[re.match("[A-Z]+", c.get("r")).group()] = sst[int(v.text)] if c.get("t") == "s" else v.text
        rows.append(row)
    names = {spec[5]: k for k, spec in SERIES.items() if spec[3] == "wb"}
    cols = {}
    for row in rows:
        if sum(1 for v in row.values() if v in names) >= 3:
            cols = {col: names[v] for col, v in row.items() if v in names}
            break
    out = {k: [] for k in names.values()}
    for row in rows:
        m = re.match(r"(\d{4})M(\d\d)$", row.get("A", ""))
        if not m or not cols:
            continue
        for col, key in cols.items():
            try:
                out[key].append((f"{m.group(1)}-{m.group(2)}-01", float(row[col])))
            except (KeyError, ValueError):
                pass
    out = {k: sorted(v)[-WB_MONTHS:] for k, v in out.items() if v}
    if not out:
        raise ValueError("Pink Sheet lacks the metals shown")
    return out


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


_MONTHS = {m: i for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)


def _cells(row):
    return [html.unescape(re.sub(r"<[^>]+>", "", c)).replace("\xa0", " ").strip() for c in _CELL.findall(row)]


def _num(t):
    try:
        return float(t)
    except ValueError:
        return None


def parse_dnav(page, freq):
    """[(date, value), ...] oldest first from an EIA dnav history page: daily pages carry one row per week
    ("2026 Nov-16 to Nov-20", then Mon to Fri), the weekly page one row per month (label "2026-Nov", then pairs of week-ending
    date "11/23" and value). Empty cells are skipped; values are taken as published."""
    out = []
    for row in _ROW.findall(page):
        c = _cells(row)
        if freq == "daily":
            m = c and re.match(r"(\d{4}) ([A-Z][a-z]{2})-\s*(\d{1,2}) to ", c[0])
            if not m or len(c) < 6 or m.group(2) not in _MONTHS:
                continue
            monday = date(int(m.group(1)), _MONTHS[m.group(2)], int(m.group(3)))
            for i, t in enumerate(c[1:6]):
                if _num(t) is not None:
                    out.append(((monday + timedelta(days=i)).isoformat(), _num(t)))
        else:
            m = c and re.match(r"(\d{4})-([A-Z][a-z]{2})$", c[0])
            if not m or m.group(2) not in _MONTHS:
                continue
            for d, t in zip(c[1::2], c[2::2]):
                dm = re.match(r"(\d\d)/(\d\d)$", d)
                if dm and _num(t) is not None:
                    out.append((f"{m.group(1)}-{dm.group(1)}-{dm.group(2)}", _num(t)))
    return sorted(set(out))


def eia_dnav(ids):
    """{series id: [(date, value), ...]} from the dnav history pages for the ids that fetch; one that fails is left out."""
    got = {}
    for i in ids:
        path, freq = DNAV[i]
        try:
            pts = parse_dnav(_get(DNAV_BASE + path, timeout=30), freq)
        except Exception as e:  # noqa: BLE001 (one series failing must not take the others with it)
            print(f"markets: dnav {i} not fetched ({e!r})")
            continue
        if pts:
            got[i] = pts[-HISTORY * 2:]
    return got


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
    jobs["wb"] = pink
    for i, (route, freq, ids, days, n) in enumerate(EIA_GROUPS):
        def one(route=route, freq=freq, ids=ids, days=days, n=n):
            got = {}
            if os.environ.get("EIA_API_KEY"):
                try:  # one try of 15 s: the EIA data API answers slowly or with 504 from the runners, and the dnav pages carry the same values
                    got = parse_eia(json.loads(_get(eia_url(route, freq, ids, days, n), timeout=15, retry_curl=False)))
                except (OSError, subprocess.SubprocessError, ValueError, KeyError) as e:
                    print(f"markets: EIA API not used for {','.join(ids)} ({e!r}); trying the dnav pages")
            missing = [x for x in ids if not got.get(x)]
            return {**got, **eia_dnav(missing)} if missing else got
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
    series.update(got.get("wb") or {})
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
    data["series"] = dict(old.get("series", {}))
    for k, pts in new.get("series", {}).items():  # a fresh series replaces the kept one unless it ends earlier
        if not data["series"].get(k) or pts[-1][0] >= data["series"][k][-1][0]:
            data["series"][k] = pts
    stored = {**data, "series": dict(data["series"])}
    if new and {k: v for k, v in stored.items() if k != "fetched"} != {k: v for k, v in old.items() if k != "fetched"}:
        # written only when the data moved, so the hourly desk run commits nothing on a day the publishers did not update
        data["fetched"] = stored["fetched"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        file().parent.mkdir(parents=True, exist_ok=True)
        file().write_text(json.dumps(stored, indent=1) + "\n")
    return data if data["series"] else None


# ---------------------------------------------------------------- numbers and markup

def dmy(d):
    return date.fromisoformat(d).strftime("%-d %b %Y")


def dlabel(key, d):
    """The date of a series as shown: monthly averages read "Oct 2026 avg", never a day that is not theirs."""
    return date.fromisoformat(d).strftime("%b %Y") + " avg" if SERIES[key][3] == "wb" else dmy(d)


def sign_arrow(x):
    return "▲" if x > 0 else "▼" if x < 0 else "▬"


def fmt(key, v):
    unit, nd = SERIES[key][1], SERIES[key][2]
    return f"{v:.{nd}f}%" if unit == "%" else f"${v:,.{nd}f}" if unit.startswith("$") else f"{v:.{nd}f}"


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
            out.append(dict(key=k, k=label, v=fmt(k, v), unit=unit if unit not in ("", "%") else "", chg=change_html(k, ch, pct), date=dlabel(k, d),
                            src=SOURCE_NAME[SERIES[k][3]], pts=pts, what=SERIES[k][4], d=ch))
    return out


def attribution(m, keys=None):
    """One combined source line for the series shown."""
    have_series = (m or {}).get("series", {})
    tags = {SERIES[k][3] for k in (keys or [x for x in have_series if x not in METALS]) if k in SERIES and k in have_series}
    names = [n for t, n in (("ecb", "ECB statistics"), ("ust", "U.S. Department of the Treasury"), ("eia", "U.S. Energy Information Administration"),
                    ("wb", "World Bank, Commodity Price Data (The Pink Sheet), CC BY 4.0"))
             if t in tags or (t == "ecb" and "calc" in tags)]
    line = ("Sources: " + "; ".join(names) + ". Series dates as shown; for information only.") if names else ""
    if "wb" in tags:
        line += " Metals: monthly averages as published; changes are against the previous month and calculated by Boardread."
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


# Crypto: CoinMarketCap API, free Basic plan. Commercial User Agreement (pro.coinmarketcap.com/user-agreement-commercial,
# read 2026-11-27): the licence covers one product (this website, not the social accounts), and the product "shall
# prominently provide attribution to CoinMarketCap as follows: "Data provided by CoinMarketCap.com"" with a link. So the
# prices appear on the site only, and every page that shows them carries that line in its footer, as does the Crypto
# section of /numbers/; they are fetched at build time and never stored or re-served.
CMC_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest?start=1&limit=20&convert=USD"
CMC_CREDIT = "Data provided by CoinMarketCap.com"
CMC_HOME = "https://coinmarketcap.com/"
COINS = 5


def crypto(key=None, opener=urllib.request.urlopen):
    """The five largest coins by market value, stablecoins and wrapped tokens left out (a dollar token at $1.00 says
    nothing): {"at": ISO time, "coins": [{"sym", "name", "price", "pct"}]}, or None without a key or on any failure."""
    key = key if key is not None else os.environ.get("CMC_API_KEY", "")
    if not key:
        return None
    try:
        req = urllib.request.Request(CMC_URL, headers={**UA, "Accept": "application/json", "X-CMC_PRO_API_KEY": key})
        with opener(req, timeout=20) as r:
            js = json.loads(_text(r.read()))
    except Exception as e:  # noqa: BLE001
        print(f"markets: crypto not fetched ({type(e).__name__})")  # the key never reaches the log
        return None
    coins = []
    for c in js.get("data") or []:
        tags = {str(t).lower() for t in (c.get("tags") or [])}
        if "stablecoin" in tags or "wrapped-tokens" in tags:
            continue
        q = ((c.get("quote") or {}).get("USD") or {})
        if q.get("price") is None:
            continue
        coins.append({"sym": c.get("symbol", ""), "name": c.get("name", ""), "price": float(q["price"]),
                      "pct": float(q["percent_change_24h"]) if q.get("percent_change_24h") is not None else None})
        if len(coins) == COINS:
            break
    if not coins:
        return None
    return {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "coins": coins}


def coin_price(v):
    return f"${v:,.0f}" if v >= 1000 else f"${v:,.2f}" if v >= 1 else f"${v:,.4f}"


def coin_change(pct):
    if pct is None:
        return ""
    cls = "up" if pct > 0 else "down" if pct < 0 else "flat"
    word = "up" if pct > 0 else "down" if pct < 0 else "unchanged"
    return (f'<span class="chg {cls}"><span aria-hidden="true">{sign_arrow(pct)}</span><span class="sr">{word} </span>'
            f'{abs(pct):.2f}%<span class="sr"> in 24 hours</span></span>')


def crypto_items(m):
    """Strip items for the coins. Their credit is in the footer of every page and on /numbers/ (see CMC_URL)."""
    cr = (m or {}).get("crypto") or {}
    if not cr.get("coins"):
        return []
    at = cr.get("at", "")[11:16]
    out = [f'<li title="{E(c["name"])}, CoinMarketCap, {E(at)} UTC"><span class="sl">{E(c["sym"])}</span> <b>{E(coin_price(c["price"]))}</b> {coin_change(c["pct"])}</li>'
           for c in cr["coins"]]
    return out


def crypto_section(m):
    """The coins on the numbers page: price, 24-hour change, the time it was read, and the credit."""
    cr = (m or {}).get("crypto") or {}
    if not cr.get("coins"):
        return ""
    rows_html = "".join(f'<div class="rt"><span class="rl">{E(c["name"])} <small>{E(c["sym"])}</small></span><b>{E(coin_price(c["price"]))}</b>'
                        f'<span class="rc">{coin_change(c["pct"])}</span></div>' for c in cr["coins"])
    return (f'<section class="msec" id="crypto"><h2 class="sh">Crypto</h2><p class="olead">The five largest coins by market value, stablecoins left out. '
            f'Price in US dollars and change over 24 hours, read at {E(cr.get("at", "")[11:16])} UTC when this page was built.</p>'
            f'<div class="rtgrid cxb">{rows_html}</div><p class="attr"><a href="{CMC_HOME}" rel="noopener">{CMC_CREDIT}</a></p></section>')


def _linked(li, href):
    """The items of the strip as links: the whole item goes to its place on /numbers/."""
    return re.sub(r"^(<li[^>]*>)(.*)</li>$", lambda g: f'{g.group(1)}<a class="si" href="{href}">{g.group(2)}</a></li>', li, flags=re.S)


def strip(m, base="", today=None):
    """The one-line markets strip under the sections row: the series in STRIP with their change, and a link to all data.
    No indices. A monthly average says so, so it is never read as today's price."""
    items = []
    today = today or datetime.now(timezone.utc).date()
    for k in STRIP:
        s = stat(m, k)
        if s:
            label, v, d, ch, pct, pts = s
            when = f' <small class="sd">{E(date.fromisoformat(d).strftime("%b"))} avg</small>' if SERIES[k][3] == "wb" else ""
            if not when and date.fromisoformat(d) < today - timedelta(days=1):  # a price older than yesterday says which day it is
                when = f' <small class="sd">{date.fromisoformat(d).strftime("%-d %b")}</small>'
            items.append(_linked(f'<li><span class="sl">{E(label)}</span> <b>{E(fmt(k, v))}</b>{when} {change_html(k, ch, None)}</li>', f"{base}/numbers/#{k}"))
    # the coins follow the three most watched series
    items[3:3] = [_linked(c, f"{base}/numbers/#crypto") for c in crypto_items(m)]
    if not items:
        return ""
    # the list runs twice in one track that slides left by half its width, so the loop has no seam; the copy is hidden
    # from screen readers. All data stays put on the right. Reduced motion: no sliding, one copy, scroll by hand.
    copy = "".join(i.replace("<li", '<li aria-hidden="true" class="dup"', 1).replace("<a ", '<a tabindex="-1" ', 1) for i in items)
    # the pause button is the way to stop the motion on a touch screen, where there is no hover to do it (WCAG 2.2.2)
    pause = ('<button type="button" class="mpause" aria-pressed="false" aria-label="Pause the ticker"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" '
             'stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" aria-hidden="true" focusable="false"><path class="pa" d="M5 3v10M11 3v10"/><path class="pl" d="M5 3l8 5-8 5z"/></svg></button>')
    return (f'<div class="mstrip"><div class="mtrack"><ul aria-label="Markets">{"".join(items)}{copy}</ul></div>{pause}'
            f'<a href="{base}/numbers/">All data</a></div>')


def chart(pts, w=360, h=120, n=90, monthly=False):
    """A card chart: the last n observations as one line with the first and last date, no fill."""
    pts = pts[-n:]
    if len(pts) < 2:
        return ""
    D = (lambda d: date.fromisoformat(d).strftime("%b %Y")) if monthly else dmy  # noqa: E731
    vals = [v for _, v in pts]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    left, right, top, bot = 4, 4, 8, 22
    X = lambda i: left + (w - left - right) * i / (len(vals) - 1)  # noqa: E731
    Y = lambda v: top + (h - top - bot) * (1 - (v - lo) / span)  # noqa: E731
    path = " ".join(("M" if i == 0 else "L") + f"{X(i):.1f} {Y(v):.1f}" for i, v in enumerate(vals))
    return (f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="Last {len(pts)} observations, from {D(pts[0][0])} to {D(pts[-1][0])}" '
            f'fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">'
            f'<path d="{path}"/><circle cx="{X(len(vals) - 1):.1f}" cy="{Y(vals[-1]):.1f}" r="3" fill="currentColor" stroke="none"/>'
            f'<text x="{left}" y="{h - 5}" font-size="11" fill="currentColor" stroke="none" opacity=".75">{D(pts[0][0])}</text>'
            f'<text x="{w - right}" y="{h - 5}" font-size="11" text-anchor="end" fill="currentColor" stroke="none" opacity=".75">{D(pts[-1][0])}</text></svg>')


MARKET_CARDS = IMPORTANCE


def cards(m, keys=MARKET_CARDS):
    """The numbers page: one chart card per series with a one-line explanation, the series date and the source."""
    out = ""
    for k in keys:
        s = stat(m, k)
        if not s:
            continue
        label, v, d, ch, pct, pts = s
        monthly = SERIES[k][3] == "wb"
        weekly = any(SERIES[k][5] in g[2] and g[1] == "weekly" for g in EIA_GROUPS)
        # a monthly average is a change on the month before, not on yesterday: the card says so beside the number
        vs = f' <small class="vs">vs {date.fromisoformat(pts[-2][0]).strftime("%b")}</small>' if monthly and len(pts) > 1 and ch is not None else ""
        last90 = [x for _, x in pts[-(36 if monthly else 90):]]
        unit = SERIES[k][1]
        out += (f'<article class="mcard" id="{k}"><h2>{E(label)}</h2><p class="mv"><b>{E(fmt(k, v))}</b>{f"<small>{E(unit)}</small>" if unit not in ("", "%") else ""} {change_html(k, ch, pct)}{vs}</p>'
                f'<div class="mch">{chart(pts, n=36, monthly=True) if monthly else chart(pts)}</div><p class="what"><b>What it is.</b> {E(SERIES[k][4])}</p>'
                f'<p class="meta">Last {len(last90)} {"monthly averages" if monthly else "weekly observations" if weekly else "daily observations"}: low {E(fmt(k, min(last90)))}, high {E(fmt(k, max(last90)))}. {E(dlabel(k, d)) if monthly else "Series date " + dmy(d)}{", changes against the previous month" if monthly else ", change against the previous week" if weekly else ""}. {E(SOURCE_NAME[SERIES[k][3]])}.</p></article>')
    return f'<div class="mcards">{out}</div><p class="attr">{E(attribution(m, keys))}</p>' if out else ""


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
