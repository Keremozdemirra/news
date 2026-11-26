"""Licensed footage for a story: find one video clip we are allowed to reuse, or say there is none.

Prototype, not wired into the pipeline. The rules are in brand/research/video.md; the short version:

  - Only two machine-checkable sources are on the allow-list: the NASA Image and Video Library and Wikimedia
    Commons videos under CC0, CC BY, or "public domain" that credits a US federal author.
  - Never CC BY-SA, ND or NC (a Reel with an edited clip would have to be shared alike, which Instagram's terms
    do not allow), never footage credited to a company or another agency, never press conferences.
  - Relevance is strict like the photo guards: the story's named subject must be in the clip's title or description,
    and the story's other key words must overlap. A clip that fits only the company is archive footage, and the
    Reel says so on screen.
  - Audio is always dropped: licensed music is the one thing Instagram detects and the metadata never states.

match() returns (candidate, why not) so a miss is explained in the log. Standard library only.
"""
import gzip
import json
import re
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

UA = {"User-Agent": "boardread.news build (+https://boardread.news/about/)"}
NASA_API = "https://images-api.nasa.gov"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

EVENT_DAYS = 7  # a clip this young counts as the event; older is archive footage and is labelled as such
ARCHIVE_DAYS = 3 * 365
MIN_SECONDS, MAX_SECONDS = 6, 600
STOP = set("""a an the and or of to in on at for from with by as is are was were be been it its this that these those
says say said after over into than then will would could may might has have had not no new more less up down out off
about across against between per via who what when where why how also one two three four five six seven eight nine ten
his her their our your you they them he she we us""".split())

# NASA's library holds footage that is not NASA's: contractor, partner and foreign-agency material.
# Checked against the creator field: footage credited to these is theirs, even when NASA hosts it.
THIRD_PARTY_CREATOR = re.compile(r"spacex|boeing|lockheed|northrop|blue origin|sierra space|axiom|\besa\b|jaxa|roscosmos|"
                                 r"\bcsa\b|airbus|ula\b|rocket lab|virgin|firefly|intuitive machines", re.I)
# Checked against the description: words that say someone holds rights.
THIRD_PARTY_RIGHTS = re.compile(r"courtesy|copyright|©|licensed|used with permission|all rights reserved|video provided by", re.I)
# a talking head or a meeting is not footage of an event, and it carries speaker likenesses we cannot clear
NOT_BROLL = re.compile(r"news conference|briefing|press conference|hangout|live (?:\w+ )?(?:coverage|stream)|town hall|"
                       r"interview|podcast|trailer|promo|music|song|full replay|webcast", re.I)
# Commons "public domain" is the uploader's claim; we accept it only when the credit names a US federal author
US_GOV = re.compile(r"\bNASA\b|NOAA|U\.?S\.? (?:Navy|Army|Air Force|Marine|Coast Guard|Department|Geological|Forest|"
                    r"Fish|Space Force|Government)|United States (?:Navy|Army|Air Force|Department|Government)|"
                    r"White House|DVIDS|\bUSGS\b|\bNIST\b|\bFEMA\b|Department of (?:Defense|War|Energy|State)", re.I)


def _get(url, timeout=30):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            raw = r.read()
    except OSError:  # a CA file that lacks an intermediate certificate (the desk's Mac): curl takes its own route
        raw = subprocess.run(["curl", "-gfsS", "--compressed", "--max-time", str(timeout), "-A", UA["User-Agent"], url],
                             check=True, capture_output=True, timeout=timeout + 5).stdout
    return gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw


def _json(url):
    return json.loads(_get(url))


def _stem(w):
    return re.sub(r"(?:ing|ed|es|s)$", "", w) if len(w) > 4 else w


def words(text):
    """Content words, lightly stemmed so 'launches' meets 'launch'."""
    return {_stem(w) for w in re.findall(r"[a-z0-9][a-z0-9\-]+", (text or "").lower().replace("’", "'")) if w not in STOP and len(w) > 2}


def subjects(post):
    """Named subjects of the story: company, person, and the capitalised names in the headline."""
    head = post["headlines"][0]
    names = [post.get("company"), post.get("person")]
    names += re.findall(r"(?<![.!?] )\b[A-Z][A-Za-z0-9\-]+(?: [A-Z0-9][A-Za-z0-9\-]*)*", head)
    out = []
    for n in names:
        n = (n or "").strip()
        if len(n) > 2 and n.lower() not in STOP and n not in out and n.lower() not in {"the", "u.s", "us"}:
            out.append(n)
    return out


def relevance(post, title, desc):
    """(ok, why). The named subject must be in the clip's title or description, and at least two of the headline's
    other key words must too: 'SpaceX' alone matches every Crew launch, which is not the story."""
    squash = lambda t: re.sub(r"[\s\-]+", "", t.lower().replace("’", "'"))  # noqa: E731  "Space X" meets "SpaceX"
    text = squash(f"{title} {desc}")
    subs = [s for s in subjects(post) if squash(s) in text]
    if not subs:
        return False, "no named subject of the story appears in the clip's title or description"
    head_words = words(post["headlines"][0]) - words(" ".join(subjects(post)))
    hits = sorted(head_words & words(f"{title} {desc}"))
    if len(hits) < 2:
        return False, f"subject {subs[0]!r} matches but only {len(hits)} other headline word(s) do ({hits})"
    return True, f"subject {subs[0]!r}, words {hits}"


def age_class(date, now):
    days = (now - date).days
    if days < -1:
        return None
    return "event" if days <= EVENT_DAYS else "archive" if days <= ARCHIVE_DAYS else None


def _dt(s):
    s = (s or "").strip()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=timezone.utc)
    m = re.search(r"(\d{1,2}) (\w+) (\d{4})", s)
    if m:
        try:
            return datetime.strptime(f"{m[1]} {m[2][:3]} {m[3]}", "%d %b %Y").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    m = re.search(r"(\d{4})", s)
    return datetime(int(m[1]), 7, 1, tzinfo=timezone.utc) if m else None


def queries(post):
    """Search strings, narrow first: the headline's key words, then each named subject alone. The search engines
    AND their terms, so the long query finds the exact event and the short one finds archive footage of the subject."""
    head = post["headlines"][0]
    ws = [w for w in re.findall(r"[A-Za-z0-9\-]+", head) if w.lower() not in STOP and len(w) > 2]
    subs = subjects(post)
    rest = [w for w in ws if not any(w.lower() in s.lower() for s in subs)]
    out = [" ".join(ws[:4])] + [f"{s} {k}" for s in subs[:1] for k in rest[:3]] + subs[:2]
    return list(dict.fromkeys(q for q in out if q))


# ---- NASA Image and Video Library ------------------------------------------------------------------------------

def nasa_candidates(post, now):
    seen = set()
    for q in queries(post):
        got = _json(f"{NASA_API}/search?q={urllib.parse.quote(q)}&media_type=video&year_start={now.year - 3}")["collection"]["items"]
        for it in got[:25]:
            d = it["data"][0]
            if d["nasa_id"] not in seen:
                seen.add(d["nasa_id"])
                yield _nasa_item(d)


def _nasa_item(d):
    return {"source": "nasa", "id": d["nasa_id"], "title": d.get("title", ""), "desc": d.get("description", ""),
            "date": _dt(d.get("date_created")), "center": d.get("center", ""),
            "creator": " ".join(filter(None, [d.get("photographer"), d.get("secondary_creator")])),
            "licence": "NASA media, not subject to copyright in the US",
            "page": f"https://images.nasa.gov/details/{urllib.parse.quote(d['nasa_id'])}"}


def nasa_check(c):
    """Problems that make a NASA item unusable even when it matches."""
    out = []
    if not c["center"]:
        out.append("no NASA centre code, so not NASA-produced")
    m = THIRD_PARTY_CREATOR.search(c["creator"]) or THIRD_PARTY_RIGHTS.search(f"{c['title']} {c['desc']}")
    if m:
        out.append(f"third-party marker {m.group(0)!r} in the creator or description")
    return out


def nasa_files(c):
    """The MP4 renditions of an item, best first: (url, label)."""
    items = _json(f"{NASA_API}/asset/{urllib.parse.quote(c['id'])}")["collection"]["items"]
    urls = [i["href"] for i in items if i["href"].lower().endswith(".mp4")]
    rank = {"~large": 0, "~medium": 1, "~orig": 2, "~small": 3, "~mobile": 4}  # 1080p first; orig can be 4K and huge
    urls.sort(key=lambda u: next((v for k, v in rank.items() if k in u), 9))
    return [(u.replace("http://", "https://"), "") for u in urls]


# ---- Wikimedia Commons -----------------------------------------------------------------------------------------

COMMONS_META = "LicenseShortName|Artist|Credit|UsageTerms|AttributionRequired|DateTimeOriginal|ImageDescription|Restrictions|ObjectName"


def _strip(h):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h or "")).strip()


def commons_candidates(post, now):
    pages = {}
    for q in queries(post):
        url = (f"{COMMONS_API}?action=query&format=json&generator=search&gsrnamespace=6&gsrlimit=20&gsrsearch="
               f"{urllib.parse.quote('filetype:video ' + q)}&prop=imageinfo&iiprop=url|mime|size|timestamp|mediatype|extmetadata"
               f"&iiextmetadatafilter={COMMONS_META}")
        pages.update(_json(url).get("query", {}).get("pages", {}) or {})
    for p in pages.values():
        ii = (p.get("imageinfo") or [{}])[0]
        m = {k: _strip(v.get("value", "")) for k, v in (ii.get("extmetadata") or {}).items()}
        if ii.get("mediatype") != "VIDEO":
            continue
        yield {"source": "commons", "id": p["title"], "title": p["title"].removeprefix("File:").rsplit(".", 1)[0],
               "desc": m.get("ImageDescription", ""), "date": _dt(m.get("DateTimeOriginal")) or _dt(ii.get("timestamp")),
               "creator": m.get("Artist", ""), "credit": m.get("Credit", ""), "licence": m.get("LicenseShortName", ""),
               "restrictions": m.get("Restrictions", ""), "url": ii.get("url"), "size": ii.get("size", 0),
               "page": "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(p["title"].replace(" ", "_"))}


def commons_check(c):
    out = []
    lic = c["licence"]
    if re.fullmatch(r"CC0.*|CC BY (?:3\.0|4\.0)(?: .*)?|CC BY 2\.\d", lic) and "SA" not in lic and "ND" not in lic and "NC" not in lic:
        pass
    elif re.fullmatch(r"Public domain|PD.*", lic):
        if not US_GOV.search(f"{c['creator']} {c['credit']} {c['desc']}"):
            out.append("'public domain' is the uploader's claim and no US federal author is named")
    else:
        out.append(f"licence {lic!r} is not CC0, CC BY or verified US-government public domain")
    if c["restrictions"]:
        out.append(f"Commons marks a restriction: {c['restrictions']}")
    if THIRD_PARTY_CREATOR.search(f"{c['creator']} {c['credit']}") and not re.search(r"NASA", c["creator"] + c["credit"]):
        out.append("credited to a company or foreign agency")
    return out


# ---- the match -------------------------------------------------------------------------------------------------

def match(post, now=None, sources=("nasa", "commons"), log=None):
    """The best clip for a post, or None. Returns (candidate, rejected) where rejected is a list of
    (title, reason) for the log. Never raises on a network failure: no footage is a normal outcome."""
    now = now or datetime.now(timezone.utc)
    log = log if log is not None else []
    found = []
    gens = {"nasa": nasa_candidates, "commons": commons_candidates}
    for s in sources:
        try:
            cands = list(gens[s](post, now))
        except Exception as e:  # noqa: BLE001
            log.append((s, f"search failed: {str(e)[:80]}"))
            continue
        for c in cands:
            why = None
            if NOT_BROLL.search(c["title"]):
                why = "press conference, briefing, live stream or promo, not footage of an event"
            elif not c["date"] or not age_class(c["date"], now):
                why = "undated, in the future or older than three years"
            else:
                bad = nasa_check(c) if s == "nasa" else commons_check(c)
                if bad:
                    why = "; ".join(bad)
                else:
                    ok, r = relevance(post, c["title"], _strip(c["desc"]))
                    if not ok:
                        why = r
                    else:
                        c["why"], c["age"] = r, age_class(c["date"], now)
                        found.append(c)
            if why:
                log.append((c["title"][:70], why))
    if not found:
        return None, log
    found.sort(key=lambda c: (c["age"] != "event", -c["date"].timestamp()))
    return found[0], log


def credit(c):
    """The on-screen credit line: what the licence needs, nothing more. CC BY asks for the creator, the licence
    and a note that the work was changed; NASA asks to be named as the source."""
    if c["source"] == "nasa":
        return "Video: NASA"
    who = re.sub(r"\s+", " ", c["creator"]).strip() or "unknown author"
    if c["licence"].startswith("CC0"):
        return "Video: Wikimedia Commons, CC0"
    if c["licence"].startswith("CC BY"):
        return f"Video: {who}, {c['licence']}, via Wikimedia Commons. Cropped and edited."
    return f"Video: {who}, public domain, via Wikimedia Commons"


def download(c, dest):
    """Fetch the clip to dest. NASA: the 1080p rendition; Commons: the original WebM."""
    from pathlib import Path
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = nasa_files(c)[0][0] if c["source"] == "nasa" else c["url"]
    subprocess.run(["curl", "-gfsSL", "--max-time", "300", "-A", UA["User-Agent"], "-o", str(dest), url],
                   check=True, capture_output=True, timeout=310)
    return dest
