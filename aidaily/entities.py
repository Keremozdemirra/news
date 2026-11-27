"""Logos and photos for the companies and people a story names.

Logo order: the company's current logo on Wikidata (Commons file), then the
square icon on the company's own site once the site's title names the
company, then nothing (the card prints the name). Photos come only from
Wikimedia Commons under a licence that allows reuse with credit, and a file
whose metadata names a photo agency is skipped even when Commons lists it as
free: on 2026-09-28 every TechCrunch photo of Dario Amodei on Commons said
CC BY 2.0 while its EXIF said "2023 Getty Images".
"""
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .feeds import CTX, UA as UA_STRING

CACHE = Path(__file__).resolve().parent.parent / "assets" / "cache"
UA = {"User-Agent": UA_STRING}
# No ShareAlike: a card with the headline set over a photo is an adaptation, and BY-SA would bind the card to the
# photo's licence, which Instagram's terms do not allow. CC BY, CC0 and public domain only.
OK_LICENCES = re.compile(r"^(CC BY [\d.]+|CC0|Public domain|OGL|Open Government Licence)", re.I)
# a made-up picture is not a photo, whatever the file is called: the title, description or a category says so
AI_MADE = re.compile(r"ai[- ]generated|generated (by|with|using) (an? )?(ai|artificial)|midjourney|dall[-· ]?e|stable diffusion|"
                     r"\bflux\b|\bimagen\b|firefly|\bai art\b|ai-art|artificial intelligence art|text-to-image", re.I)
AGENCIES = re.compile(r"getty|shutterstock|reuters|associated press|\bap photo|afp|alamy|bloomberg|epa\b|imago", re.I)


def _get(url, raw=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=15, context=CTX) as r:
        body = r.read()
    return body if raw else json.loads(body)


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _entity(name):
    q = urllib.parse.quote(name)
    hits = _get(f"https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&language=en&type=item&limit=1&search={q}")["search"]
    if not hits:
        return None, {}
    qid = hits[0]["id"]
    ent = _get(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json")["entities"][qid]
    return ent.get("labels", {}).get("en", {}).get("value", name), ent.get("claims", {})


ROLE_STOP = set("the of and for a an in at to who is was former current born american british politician person "
                "businessman businesswoman people official".split())


def _role_words(text):
    return {w[:6] for w in re.findall(r"[a-z]+", (text or "").lower()) if len(w) > 2 and w not in ROLE_STOP}


def person_entity(name, role):
    """(label, claims) of the person the story means, or (None, {}). Several people share a name: the top search
    hit for "Andrew Bailey" is an FBI deputy director, and his portrait once ran on a Bank of England governor's
    post. A hit is taken only when its Wikidata description shares a word with the role the copy step gives
    ("Bank of England governor"); with no role, or no hit that matches it, there is no photo."""
    want = _role_words(role)
    if not want:
        return None, {}
    q = urllib.parse.quote(name)
    hits = _get(f"https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&language=en&type=item&limit=7&search={q}")["search"]
    for h in hits:
        label = h.get("label") or h.get("display", {}).get("label", {}).get("value", "")
        if not _role_words(name) <= _role_words(label):
            continue  # another name altogether
        if want & _role_words(h.get("description", "")):
            qid = h["id"]
            ent = _get(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json")["entities"][qid]
            return ent.get("labels", {}).get("en", {}).get("value", name), ent.get("claims", {})
    return None, {}


# files a free-text search found for a person, which may show a namesake: each must prove itself (see fresh_photo)
SEARCHED = set()


def company_entity(name):
    """(label, claims) of the Wikidata entity for a company name, or LookupError when the top hit is not it.

    The top search hit can be a neighbour of the company: "S&P" finds the S&P 500 index. Logos and tickers
    both come from this one lookup, so they can never disagree about which entity is the company."""
    label, claims = _entity(name)
    extra = (label or "").lower().replace(name.lower(), "", 1) if label and name.lower() in label.lower() else None
    # words may follow the name ("Norse Atlantic Airways", "Meta Platforms") but not precede it, unless they are a
    # legal form: "Congress" found the United States Congress and its seal went on a car-import post as a logo
    starts = (label or "").lower().startswith(name.lower())
    if extra is None or re.search(r"\d", extra) or not (starts or LEGAL_FORM.match(extra)):
        raise LookupError(f"Wikidata's {label!r} is not {name!r}")
    return label, claims


def pick_logo(label, claims):
    """The current logo: no end date, preferred rank first, then a file named after the current label."""
    rows = []
    for c in claims.get("P154", []):
        v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        if not v or "P582" in c.get("qualifiers", {}):
            continue
        rows.append((c.get("rank") == "preferred", label.lower() in v.lower(), v))
    if not rows:
        return None
    rows.sort(key=lambda r: (r[1], r[0]), reverse=True)
    return rows[0][2]


def _commons_info(filename, width=None):
    extra = f"&iiurlwidth={width}" if width else ""
    t = urllib.parse.quote("File:" + filename)
    pages = _get(f"https://commons.wikimedia.org/w/api.php?action=query&format=json&prop=imageinfo"
                 f"&iiprop=url|size|extmetadata|metadata{extra}&titles={t}")["query"]["pages"]
    return list(pages.values())[0]["imageinfo"][0]


# Commons authors sometimes write the label into the author field ("Foto: Nebojša Tejić/STA"), which made the card
# read "Photo: Foto: ...". The label is ours to add once.
CREDIT_LABEL = re.compile(r"^\s*(?:photo(?:graph)?|foto(?:grafie|grafia|graf)?|bild)(?:\s+by)?\s*[:：]\s*", re.I)


def strip_label(author):
    while CREDIT_LABEL.match(author or ""):
        author = CREDIT_LABEL.sub("", author, count=1)
    return (author or "").strip()


def clean_credit(credit):
    """A stored credit line with the label once: "Photo: Foto: X, CC0" becomes "Photo: X, CC0"."""
    m = re.match(r"^(Photo|Video|Footage):\s*(.*)$", credit or "", re.S)
    return f"{m.group(1)}: {strip_label(m.group(2))}" if m else (credit or "")


def photo_ok(info):
    """(ok, credit). Reuse needs a free licence and no agency in author, credit or EXIF copyright."""
    meta = info.get("extmetadata", {})
    lic = meta.get("LicenseShortName", {}).get("value", "")
    artist = strip_label(re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")))
    exif = " ".join(str(m.get("value", "")) for m in (info.get("metadata") or []) if m.get("name") in ("Copyright", "Artist"))
    credit_line = re.sub(r"<[^>]+>", "", meta.get("Credit", {}).get("value", ""))
    if not OK_LICENCES.match(lic) or AGENCIES.search(" ".join((artist, exif, credit_line))):
        return False, ""
    said = " ".join(re.sub(r"<[^>]+>", " ", meta.get(k, {}).get("value", "")) for k in ("ImageDescription", "ObjectName", "Categories"))
    if AI_MADE.search(said):
        return False, ""
    return True, f"Photo: {artist or 'Wikimedia Commons'}, {lic}, via Wikimedia Commons"


def _site_icon(site, name):
    html = _get(site, raw=True).decode("utf-8", "ignore")
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    if not title or name.split()[0].lower() not in title.group(1).lower():
        return None  # the domain does not say it belongs to this company
    links = re.findall(r'<link[^>]+rel=["\'][^"\']*(?:apple-touch-icon|icon)[^"\']*["\'][^>]*>', html, re.I)
    hrefs = [re.search(r'href=["\']([^"\']+)', l).group(1) for l in links if "href" in l]
    # the largest square icon a site offers is its webclip / apple-touch-icon
    hrefs.sort(key=lambda h: ("webclip" in h.lower() or "apple" in h.lower() or "180" in h, h.endswith(".svg")), reverse=True)
    return urllib.parse.urljoin(site, hrefs[0]) if hrefs else None


def logo(name, domain="", fetch=True):
    """Path to a cached logo file, or None."""
    if not name:
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    for ext in ("svg", "png", "jpg", "none"):
        p = CACHE / f"logo-{_slug(name)}.{ext}"
        if p.exists():
            return None if ext == "none" else p
    if not fetch:
        return None
    try:
        label, claims = company_entity(name)
        # a place has a population; its coat of arms is not a company logo ("Alberta", "New York" on 2026-11-27).
        # Wikidata then says nothing about the company; only the company's own site, if the copy gave it, may
        if "P1082" in claims:
            label, claims = name, {}
            if not domain:
                raise LookupError(f"{name!r} is a place on Wikidata")
        f = pick_logo(label or name, claims)
        if f:
            url = _commons_info(f, width=600 if not f.lower().endswith(".svg") else None)
            src = url.get("thumburl") or url["url"]
            ext = "svg" if f.lower().endswith(".svg") else "png"
        else:
            site = domain and f"https://{domain}" or next(
                (c["mainsnak"]["datavalue"]["value"] for c in claims.get("P856", []) if "datavalue" in c["mainsnak"]), "")
            src = _site_icon(site, name) if site else None
            ext = "svg" if src and src.lower().endswith(".svg") else "png"
        if not src:
            raise LookupError("no logo")
        data = _get(src, raw=True)
        if ext == "svg":  # strip styles and scripts from a file we embed
            s = data.decode("utf-8", "ignore")
            s = re.sub(r"<script.*?</script>", "", s, flags=re.S)
            data = s.encode()
        p = CACHE / f"logo-{_slug(name)}.{ext}"
        p.write_bytes(data)
        return p
    except Exception:  # noqa: BLE001  a miss is recorded so the next run does not ask again
        (CACHE / f"logo-{_slug(name)}.none").write_text("")
        return None


# Wikidata exchange item -> (name shown, Google Finance suffix). Frankfurt and Xetra are one German listing.
EXCHANGES = {
    "Q82059": ("NASDAQ", "NASDAQ"), "Q13677": ("NYSE", "NYSE"), "Q171240": ("LSE", "LON"),
    "Q151139": ("Xetra", "ETR"), "Q819468": ("Xetra", "ETR"), "Q2385849": ("Euronext Paris", "EPA"),
    "Q478720": ("Euronext Amsterdam", "AMS"), "Q661834": ("SIX", "SWX"), "Q217475": ("TSE Tokyo", "TYO"),
    "Q496672": ("HKEX", "HKG"), "Q739514": ("SSE", "SHA"), "Q517750": ("SZSE", "SHE"),
    "Q495364": ("KRX", "KRX"), "Q495372": ("KRX", "KRX"), "Q818723": ("TSX", "TSE"), "Q732670": ("ASX", "ASX"),
}
GOOGLE_SUFFIX = {name: suffix for name, suffix in EXCHANGES.values()}
SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")
# what may follow the company name in Wikidata's label: "Apple Inc." is Apple, "Apple Music" is not
LEGAL_FORM = re.compile(r"^[\s,.]*(inc|incorporated|corp|corporation|plc|ltd|limited|llc|ag|se|nv|sa|"
                        r"co|company|group|holdings?|spa|ab|asa|oyj|kk|\s|[.,&])*$", re.I)


def _starts_after(snak, day):
    """True when a P580 start-time snak is later than `day` (YYYY-MM-DD), or is not a readable date."""
    t = (snak.get("datavalue", {}).get("value") or {}).get("time", "") if isinstance(snak.get("datavalue", {}).get("value"), dict) else ""
    m = re.match(r"^\+(\d{4}-\d{2}-\d{2})", t.replace("-00", "-01"))
    return not m or m.group(1) > day


DIRECTORIES = {"NASDAQ": "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt",
               "NYSE": "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt"}


def us_directory(fetch=True):
    """{(exchange, symbol): security name} of what NASDAQ and NYSE list today, from Nasdaq Trader's public
    symbol directory (refreshed daily), or None when it cannot be read. Wikidata does not know a company
    went private: on 2026-11-26 it still gave Denny's NASDAQ: DENN, ten months after the delisting."""
    out = {}
    for ex, url in DIRECTORIES.items():
        f = CACHE / f"listing-{ex.lower()}.txt"
        try:
            if not f.exists() or datetime.now().timestamp() - f.stat().st_mtime > 86400:
                if not fetch:
                    return None
                f.write_bytes(_get(url, raw=True))
            lines = f.read_text("utf-8", "ignore").splitlines()[1:]
        except Exception:  # noqa: BLE001  without the directory a US ticker cannot be confirmed
            return None
        for line in lines:
            cols = line.split("|")
            if len(cols) < 3 or line.startswith("File Creation"):
                continue
            if ex == "NYSE" and cols[2] != "N":
                continue  # otherlisted also holds NYSE American, Arca and Cboe names
            for sym in {cols[0], cols[3] if ex == "NYSE" and len(cols) > 3 else cols[0]}:
                out[(ex, sym)] = cols[1]
    return out


def pick_ticker(name, label, claims, directory=None):
    """{"exchange", "symbol"} when the company has exactly one current listing on a major exchange, else None.

    Listings that ended (P582), are deprecated or have not started are ignored. NASDAQ and NYSE listings must
    also be in `directory` (what the exchanges list now); other exchanges need a Wikidata reference. If Wikidata marks one or more listings
    preferred, only those count; the same symbol on Frankfurt and Xetra is one listing. Two listings and
    no preferred one is ambiguity, and a wrong ticker is worse than none."""
    low = (label or "").lower()
    rest = low.replace(name.lower(), "", 1) if name.lower() in low else None
    if rest is None or not LEGAL_FORM.match(rest):
        return None
    rows = {}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for c in claims.get("P414", []):
        q = c.get("qualifiers", {})
        ex = c.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        qid = ex.get("id") if isinstance(ex, dict) else None
        if c.get("rank") == "deprecated" or "P582" in q or qid not in EXCHANGES:
            continue
        if any(_starts_after(x, today) for x in q.get("P580", [])):
            continue
        us = EXCHANGES[qid][0] in DIRECTORIES
        if not us and not c.get("references"):
            continue  # an unsourced Wikidata edit is not enough outside the US, where nothing else confirms it
        syms = {x["datavalue"]["value"] for x in q.get("P249", []) if "datavalue" in x}
        if len(syms) != 1:
            return None  # a listing with no symbol, or two, cannot be shown honestly
        sym = syms.pop()
        if not isinstance(sym, str) or not SYMBOL.match(sym):
            return None
        key = (EXCHANGES[qid][0], sym)
        # a US listing counts only while the exchange itself lists that symbol under this company's name
        if us and (directory is None or name.lower() not in directory.get(key, "").lower()):
            continue
        rows[key] = rows.get(key, False) or c.get("rank") == "preferred"
    if any(rows.values()):
        rows = {k: v for k, v in rows.items() if v}
    if len(rows) != 1:
        return None
    (exchange, symbol), = rows
    return {"exchange": exchange, "symbol": symbol}


def ticker(name, fetch=True):
    """{"exchange": "NASDAQ", "symbol": "NVDA"} for a listed company, else None.

    Uses the entity the logo lookup resolves, label check included. A private company, an ambiguous
    listing or a failed lookup gives None. Answers are cached for a week, not forever like logos: a company
    lists (Anthropic, 2026-11-19) and delists. A cached US ticker is checked against the exchange's own
    directory on every read, so a delisting stops it at once. Only a definite answer is cached, so an outage
    is retried."""
    if not name:
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    hit, miss = CACHE / f"ticker-{_slug(name)}.json", CACHE / f"ticker-{_slug(name)}.none"
    week = datetime.now().timestamp() - 7 * 86400
    if hit.exists() and hit.stat().st_mtime > week:
        found = json.loads(hit.read_text())
        if found["exchange"] not in DIRECTORIES:
            return found
        names = us_directory(fetch)
        return found if names and name.lower() in names.get((found["exchange"], found["symbol"]), "").lower() else None
    if (miss.exists() and miss.stat().st_mtime > week) or not fetch:
        return None
    try:
        label, claims = company_entity(name)
    except LookupError:
        miss.write_text("")
        return None
    except Exception:  # noqa: BLE001  network trouble is not an answer
        return None
    directory = us_directory()
    if directory is None:
        return None
    found = pick_ticker(name, label, claims, directory)
    (miss if found else hit).unlink(missing_ok=True)  # the fresh answer replaces an expired one of the other kind
    if found:
        hit.write_text(json.dumps(found))
    else:
        miss.write_text("")
    return found


def google_finance_url(t):
    """The Google Finance page of a ticker, or '' for an exchange whose Google code is not in the map."""
    suffix = GOOGLE_SUFFIX.get((t or {}).get("exchange", ""))
    if not suffix or not SYMBOL.match((t or {}).get("symbol", "")):
        return ""
    return f"https://www.google.com/finance/quote/{urllib.parse.quote(t['symbol'])}:{suffix}"


def ticker_text(t):
    """"NASDAQ: NVDA", or '' for no ticker."""
    return f"{t['exchange']}: {t['symbol']}" if t else ""


def photo(person, fetch=True):
    """(path, credit) for a person's Commons photo, or (None, "")."""
    if not person:
        return None, ""
    CACHE.mkdir(parents=True, exist_ok=True)
    p, c, miss = (CACHE / f"photo-{_slug(person)}.jpg", CACHE / f"photo-{_slug(person)}.txt",
                  CACHE / f"photo-{_slug(person)}.none")
    if p.exists() and c.exists():
        return p, c.read_text()
    if miss.exists() or not fetch:
        return None, ""
    try:
        _, claims = _entity(person)
        files = [x["mainsnak"]["datavalue"]["value"] for x in claims.get("P18", []) if "datavalue" in x["mainsnak"]]
        # the lead image may be an agency shot; the person's Commons category often holds a free one
        cats = [x["mainsnak"]["datavalue"]["value"] for x in claims.get("P373", []) if "datavalue" in x["mainsnak"]]
        for cat in cats[:1]:
            t = urllib.parse.quote("Category:" + cat)
            members = _get(f"https://commons.wikimedia.org/w/api.php?action=query&format=json&list=categorymembers"
                           f"&cmtitle={t}&cmtype=file&cmlimit=30")["query"]["categorymembers"]
            files += [m["title"][5:] for m in members if m["title"].lower().endswith((".jpg", ".jpeg", ".png"))]
        for f in files[:25]:
            info = _commons_info(f, width=2000)
            ok, credit = photo_ok(info)
            if ok:
                p.write_bytes(_get(info.get("thumburl") or info["url"], raw=True))
                c.write_text(credit)
                return p, credit
        raise LookupError("no reusable photo")
    except Exception:  # noqa: BLE001
        miss.write_text("")
        return None, ""


NOT_PHOTO = re.compile(r"logo|icon|wordmark|map|flag|diagram|chart|screenshot|interface|extension|extention|seal|"
                       r"coat of arms|signature|poster|banner|approved|official ball|match ball|"
                       # a made-up picture is not a news photo: "AI generated image of Loab" reached a Character.AI story
                       r"ai.generated|midjourney|dall.e|stable diffusion|\bflux\b|\bimagen\b|firefly|ai art|render|rendering|concept art|mockup|"
                       # a building site is not the building: the ECB tower under construction ran on a 2026 post
                       r"under construction|construction site|groundbreaking|topping.out", re.I)
# a photo of a topic must not put a person on a story they are not in: a search for "press conference"
# once returned the President of the United States for a story about state attorneys general
PEOPLE = re.compile(r"\b(president|minister|senator|governor|secretary|ceo|chairman|mayor|king|queen|prince|pope|"
                    r"press conference|holds|meets|meeting|speaks|speech|visit|delegation|representatives|portrait|"
                    r"interview|summit|ceremony|rally|protest|selfie|headshot|wedding|funeral|team photo|match|players?|"
                    # scenes a reader takes as part of the news: a fighter jet beside an airliner is not "an airline"
                    r"military|fighter|interception|army|navy|war|weapon|missile|police|crash|accident|fire|"
                    r"explosion|disaster|flood|riot|emergency|defen[cs]e|drone|tank|soldier|troops|air force|airbase)\b", re.I)
# a company search matches words, so "Amazon" found a parrot (Amazona aestiva); animals and plants are never the company
NATURE = re.compile(r"\b(bird|parrot|animal|species|flower|plant|tree|insect|fish|mammal|reptile|wildlife|zoo|"
                    r"forest|river|mountain|amazona|rainforest|fungi|fungus|yeast|bacteria|moss|lichen|mushrooms?)\b|\([A-Z][a-z]+ [a-z]+\)")
# a place the story does not name moves the news somewhere else: Taiwan's air defence on a Kuwait story,
# an Irish copper mine on a Latin America story, another airline's jet on a Heathrow story
PLACES = re.compile(r"\b(afghanistan|albania|algeria|argentina|armenia|australia|austria|azerbaijan|bahrain|bangladesh|"
                    r"belarus|belgium|bolivia|bosnia|brazil|bulgaria|cambodia|cameroon|canada|chile|china|colombia|"
                    r"croatia|cuba|cyprus|czech|denmark|ecuador|egypt|estonia|ethiopia|finland|france|georgia|germany|"
                    r"ghana|greece|hungary|iceland|india|indonesia|iran|iraq|ireland|israel|italy|japan|jordan|"
                    r"kazakhstan|kenya|korea|kuwait|latvia|lebanon|libya|lithuania|luxembourg|malaysia|mexico|morocco|"
                    r"netherlands|holland|zealand|nigeria|norway|oman|pakistan|palestine|gaza|peru|philippines|poland|"
                    r"portugal|qatar|romania|russia|saudi|serbia|singapore|slovakia|slovenia|spain|sweden|switzerland|"
                    r"syria|taiwan|thailand|tunisia|turkey|ukraine|emirates|uae|dubai|abu dhabi|britain|england|"
                    r"scotland|wales|venezuela|vietnam|yemen|zimbabwe|cork|dublin|paris|berlin|munich|frankfurt|"
                    r"madrid|rome|milan|tokyo|beijing|shanghai|hong kong|shenzhen|seoul|taipei|moscow|kyiv|istanbul|"
                    r"tehran|riyadh|doha|cairo|mumbai|delhi|sydney|toronto|vancouver|chicago|texas|california|"
                    r"florida|middle east|africa|asia|europe|latin america|south america)\b", re.I)
# museum objects and artworks are never a company's news photo
ART = re.compile(r"\b(museum|painting|textile|fragment|sculpture|statue|artwork|exhibit|exhibition|mosaic|fresco|"
                 r"manuscript|engraving|century|bce|ce|antique|ancient|relic|tapestry)\b", re.I)
# fans, visitors and passers-by are people the story is not about
CROWD = re.compile(r"\b(fan|fans|crowd|cosplay|cosplayer|visitors?|audience|attendees?|man|woman|men|women|girl|boy|"
                   r"people|person|kids?|child|children|queue|line outside|selfie)\b", re.I)
# a show at a venue is not the venue: "One Direction - Lincoln Financial Field" ran on an Eagles result (2026-11-27)
EVENT = re.compile(r"\b(concerts?|tour|live|festival|gig|performing|performance|show|stage|fireworks|wedding|halftime|"
                   r"rally|ceremony|parade|wrestlemania|exhibition match)\b", re.I)
FACE = re.compile(r"cropped|crop\b|portrait|official|headshot", re.I)
# What a company photo may show: the company's own premises or its own sign. A file that only carries the name
# shows whatever the uploader liked: an Nvidia graphics card from 2008 on a credit-rating story, a FIFA
# merchandise truck on a FIFA data-breach story, a "biggest fan" on a Rockstar union vote.
PREMISES = re.compile(r"\b(headquarters?|hq|head ?office|offices?|campus|building|tower|plant|factory|works|"
                      r"refinery|store|shop|flagship|branch|sign|signage|entrance|exterior|facade|fa\u00e7ade|depot|"
                      r"terminal|warehouse|fulfil+ment cent(?:er|re)|data cent(?:er|re))\b", re.I)
# an airline's or a planemaker's news is about its aircraft, and a photo of its own jet names the company
AIRCRAFT = re.compile(r"\b(boeing|airbus|embraer|bombardier|atr|a3\d\d|7[0-8]7|aircraft|airliner|jet)\b", re.I)
AIR_COMPANY = re.compile(r"\b(air|airlines?|airways|aviation|aerospace|boeing|airbus|embraer)\b", re.I)
PEOPLE_ART = re.compile(r"guilty|convicted|impeach|sign|poster|banner|placard|mural|cartoon|caricature|meme|graffiti|"
                        r"effigy|mask|costume|parody|protest|rally|march|vote|ballot|campaign|sticker|flag", re.I)
GROUP = re.compile(r"\b(with|and|meets|meeting|delegation|visit|group|team|family|ceremony|summit|tweet|notes|"
                   r"endorsed|cartoon|meme|caricature|parody|drawing|illustration|graffiti|mural|protest|sign|"
                   r"trump|biden|putin|xi|modi|obama|harris|vance|zuckerberg|bezos|gates|altman|musk|huang|"
                   r"nadella|pichai|amodei|hassabis)\b|[A-Z][a-z]+-[A-Z][a-z]+", re.I)
WORD_ = re.compile(r"[a-z][a-z0-9]+")

# Company names that are also a river, a fruit, a bird, a planet or a shape. A Commons search for the bare name
# finds the other thing ("Amazon" found a parrot, Amazona aestiva), so a file for one of these must show the
# company's side in its own title.
AMBIGUOUS = frozenset({"amazon", "apple", "shell", "oracle", "jaguar", "puma", "mercury", "corona", "delta", "target",
                       "square", "block", "meta", "alphabet", "visa", "uber", "orange", "gap", "ford", "lotus", "snap",
                       "nest", "mars", "sap"})
CORP_WORDS = re.compile(r"\b(headquarters|hq|offices?|stores?|storefront|buildings?|towers?|campus|warehouses?|"
                        r"fulfil+ments?|distribution|signage|sign|trucks?|vans?|aircraft|airliners?|planes?|jets?|"
                        r"data ?cent(?:er|re)s?|factory|showroom|dealership|inc|corp|corporation|ag|plc|ltd|gmbh|llc)\b", re.I)
# the word after a title-case company name that turns it back into a river, a fruit, a place or an animal
WRONG_SENSE = frozenset({"river", "rainforest", "basin", "forest", "jungle", "parrot", "parrots", "tree", "trees",
                         "orchard", "pie", "fruit", "blossom", "blossoms", "juice", "cider", "seed", "seeds", "beach",
                         "island", "islands", "lake", "bay", "valley", "desert", "bird", "birds", "cat", "cats", "virus",
                         "del", "heights", "rapids", "falls", "delta", "peninsula", "bridge"})


def company_context(name, subject):
    """True when a Commons file name `name` can be a photo of the company `subject`, not of what else the word means.

    Words that are only a company some of the time need proof in the title: a corporate word (headquarters, store,
    warehouse, Inc, aircraft ...), or the name in title case leading the title and not followed by a river, fruit
    or other word that gives the other sense."""
    sub = (subject or "").strip()
    if sub.lower() not in AMBIGUOUS:
        return True
    if CORP_WORDS.search(name):
        return True
    if len(sub) <= 3:  # "SAP" is too short to trust a title that merely starts with it
        return False
    for form in dict.fromkeys((sub, sub.capitalize())):  # "SAP" leads a title as "Sap"
        m = re.match(re.escape(form) + r"(?![A-Za-z0-9])[\W_]*([A-Za-z]*)", name)
        if m:
            return m.group(1).lower() not in WRONG_SENSE
    return False


def _words(text):
    return {w for w in WORD_.findall((text or "").lower()) if len(w) > 2}


# Brands a stock photo can show by name. A generic "computer chip" search once put an AMD chip on an Nvidia
# story; a photo whose title or description names a company the story does not name is somebody else's news.
BRANDS = re.compile(r"\b(amd|radeon|ati|intel|nvidia|geforce|qualcomm|snapdragon|tsmc|samsung|apple|iphone|ipad|macbook|"
                    r"google|pixel|microsoft|xbox|windows|meta|facebook|instagram|whatsapp|amazon|alexa|kindle|tesla|"
                    r"spacex|starlink|openai|chatgpt|anthropic|huawei|xiaomi|sony|playstation|nintendo|lg|dell|hp|"
                    r"lenovo|asus|acer|ibm|oracle|cisco|broadcom|arm|micron|sk hynix|asml|boeing|airbus|ford|gm|"
                    r"toyota|volkswagen|vw|bmw|mercedes|audi|porsche|byd|nissan|honda|hyundai|kia|ferrari|uber|lyft|"
                    r"netflix|disney|spotify|tiktok|bytedance|alibaba|tencent|baidu|walmart|costco|target|nike|adidas|"
                    r"coca-cola|pepsi|mcdonald's|starbucks|shell|bp|exxon|chevron|aramco|jpmorgan|goldman|"
                    r"morgan stanley|citi|hsbc|barclays|ubs|deutsche bank|visa|mastercard|paypal)\b", re.I)


def phrase_in(name, text):
    """The whole name, as a phrase, in a file name or title ("Rockstar Games", not "rockstar" in another word)."""
    name = (name or "").strip()
    return bool(name) and re.search(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", text or "", re.I) is not None


# capitalised words that open or sit inside a headline without naming anything
NOT_NAMES = {
    "the", "this", "that", "with", "from", "after", "global", "new", "says", "report", "reports", "monday", "tuesday",
    "wednesday", "thursday", "friday", "saturday", "sunday", "january", "february", "march", "april", "june", "july",
    "august", "september", "october", "november", "december", "german", "american", "african", "asian", "indian",
    "mexican", "european", "korean", "arab", "south", "north", "east", "west", "first", "second", "latest", "what",
    "why", "how", "who", "will", "here", "more", "most", "over", "under", "into", "amid", "still", "just"}
PROPER = re.compile(r"^(?:[A-Z][A-Za-z0-9'’]*|\d+[A-Za-z][A-Za-z0-9]*)$")


def headline_names(headline, skip=()):
    """Proper names a headline carries, in order: runs of capitalised words ("Hugging Face") and single names
    of four letters or more ("Ibiza", "1Password"). The word that opens the sentence only counts inside a longer
    run or with a digit or inner capital, since "Global stocks rally" names nothing. Names in `skip` (the person
    and company already tried) and nationality adjectives are left out."""
    skipped = {x.lower() for x in skip if x}
    runs, cur = [], []

    def flush():
        if cur:
            runs.append(list(cur))
            cur.clear()
    for i, raw in enumerate(re.findall(r"\S+", headline or "")):
        w = re.sub(r"['’]s$", "", raw.strip("'\"‘’“”.,:;!?()[]"))
        ok = (bool(PROPER.match(w)) and w.lower() not in NOT_NAMES and not re.search(r"(?:ese|ish|ian|ean)$", w.lower())
              and "-" not in w)
        if ok:
            cur.append((i, w))
        else:
            flush()
        if raw[-1:] in ",;:" or raw.endswith(("'s", "’s")):
            flush()
    flush()
    out = []
    for run in runs:
        words = [w for _, w in run]
        name = " ".join(words)
        if len(words) == 1:
            w = words[0]
            sentence_start = run[0][0] == 0
            marked = bool(re.search(r"\d", w)) or bool(re.search(r"[a-z][A-Z]", w))
            if len(w) < 4 or (sentence_start and not marked):
                continue
        if name.lower() in skipped or any(name.lower() in x or x in name.lower() for x in skipped) or name in out:
            continue
        out.append(name)
    return out


def is_human(name):
    """True when Wikidata's top hit for `name` is a person; a lookup that fails counts as one, which skips the name."""
    try:
        _, claims = _entity(name)
        return any(c.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id") == "Q5"
                   for c in claims.get("P31", []))
    except Exception:  # noqa: BLE001
        return True


def foreign_brand(text, allow, own=""):
    """The first brand or place named in `text` that `allow` (headline and subject) does not name, or ''.

    When the file names the story's own company (`own`), brands beside it are context: "Norse Atlantic
    Airways Boeing 787" is Norse's own aircraft, not a Boeing story."""
    allowed = (allow or "").lower()
    if not text:
        return ""
    # a photo of the subject itself (the ECB tower in Frankfurt, Norse's own Boeing) carries its place and
    # maker as context; only a photo of something else must not name another place or brand
    if own and _words(own) and _words(own) <= _words(text):
        return ""
    for m in PLACES.finditer(text):
        word = m.group(1).lower()
        if not re.search(r"\b" + re.escape(word) + r"\b", allowed):
            return m.group(1)
    for m in BRANDS.finditer(text):
        if not re.search(r"\b" + re.escape(m.group(1).lower()) + r"\b", allowed):
            return m.group(1)
    return ""


# Teams whose kit or badge puts an athlete on the wrong side: a Packers jersey on a Steelers article. A photo whose title,
# description or Commons categories name a team that the article does not name is somebody else's team.
TEAMS = re.compile(
    r"\b(cardinals|falcons|ravens|bills|panthers|bears|bengals|browns|cowboys|broncos|lions|packers|texans|colts|jaguars|chiefs|"
    r"raiders|chargers|rams|dolphins|vikings|patriots|saints|giants|jets|eagles|steelers|49ers|seahawks|buccaneers|titans|commanders|"
    r"redskins|celtics|nets|knicks|76ers|sixers|raptors|bulls|cavaliers|pistons|pacers|bucks|hawks|hornets|heat|magic|wizards|"
    r"nuggets|timberwolves|thunder|trail blazers|jazz|warriors|clippers|lakers|suns|kings|mavericks|rockets|grizzlies|pelicans|spurs|"
    r"arsenal|aston villa|bournemouth|brentford|brighton|burnley|chelsea|crystal palace|everton|fulham|leeds|leicester|liverpool|"
    r"manchester city|manchester united|man city|man united|newcastle|nottingham forest|southampton|sunderland|tottenham|spurs|"
    r"west ham|wolves|wolverhampton|bayern|dortmund|leverkusen|leipzig|real madrid|barcelona|atletico|sevilla|valencia|villarreal|"
    r"juventus|inter milan|ac milan|napoli|roma|lazio|atalanta|psg|paris saint-germain|ajax|benfica|porto|celtic|rangers|"
    r"ferrari|mercedes|red bull|mclaren|aston martin|alpine|williams|haas|sauber|audi|cadillac|racing bulls|alphatauri|renault)\b", re.I)


def foreign_team(text, allow):
    """The first team named in `text` that `allow` (the article's own words) does not name, or ''."""
    allowed = (allow or "").lower()
    for m in TEAMS.finditer(text or ""):
        if not re.search(r"\b" + re.escape(m.group(1).lower()) + r"\b", allowed):
            return m.group(1)
    return ""


# Words that make a capitalised run in a file title an organisation or a place: "Virginia Tech", "Fisherman's Wharf",
# "New York Stock Exchange". A photo of one of them on a story that does not name it is somebody else's news.
ORG_CUE = {"university", "college", "institute", "school", "hospital", "stadium", "museum", "cathedral", "church",
           "wharf", "merch", "tech", "unc", "mit", "exchange", "campus", "academy", "airport", "pier"}


def foreign_names(title, allow):
    """The first organisation or place named in a file title that `allow` (headline, company, person) does not name, or ''.

    A run of capitalised words that holds one of the ORG_CUE words is taken as a name; it passes when any other
    word of the run appears in `allow` ("Heathrow Airport" on a Heathrow story), and a run of cue words alone never does."""
    allowed = _words(allow)
    run = []

    def verdict():
        words = [w for w in run if w.lower() not in ORG_CUE]
        if any(w.lower() in ORG_CUE for w in run) and not any(w.lower() in allowed for w in words if len(w) > 2):
            return " ".join(run)
        return ""
    for raw in re.findall(r"[A-Za-z0-9'’]+|[^\sA-Za-z0-9]", re.sub(r"\.(jpe?g|png)$", "", title or "", flags=re.I)):
        w = re.sub(r"['’]s$", "", raw)
        if re.match(r"^[A-Z][A-Za-z0-9]*$", w) or w.lower() in ORG_CUE and w.isupper():
            run.append(w)
            continue
        found = verdict()
        if found:
            return found
        run = []
    return verdict()


def candidates(subject, person=False, company=False, role=None):
    """Commons JPEG names that may show the subject: a person's Wikidata image and category, or a search
    whose hits must name the subject in their own title and must not be photos of people or events.
    With `role`, the person is the Wikidata entity whose description matches it (see person_entity)."""
    files = []
    if person:
        _, claims = _entity(subject) if role is None else person_entity(subject, role)
        if role is not None and not claims:
            return []
        files += [x["mainsnak"]["datavalue"]["value"] for x in claims.get("P18", []) if "datavalue" in x["mainsnak"]]
        cats = [x["mainsnak"]["datavalue"]["value"] for x in claims.get("P373", []) if "datavalue" in x["mainsnak"]]
        for cat in cats[:1]:
            t = urllib.parse.quote("Category:" + cat)
            got = _get(f"https://commons.wikimedia.org/w/api.php?action=query&format=json&list=categorymembers"
                       f"&cmtitle={t}&cmtype=file&cmlimit=50")["query"]["categorymembers"]
            # a photo of the person with someone else puts that someone on the story
            files += [m["title"][5:] for m in got]
        category = set(files)
        # many people have a handful of files in their category and many more elsewhere; a title that
        # carries the full name and nobody else's is a photo of them
        q = urllib.parse.quote(f'"{subject}" filetype:bitmap')
        got = _get(f"https://commons.wikimedia.org/w/api.php?action=query&format=json&list=search"
                   f"&srnamespace=6&srlimit=50&srsearch={q}")["query"]["search"]
        need = _words(subject)
        searched = [m["title"][5:] for m in got]
        files += searched
        # the title must name the person, and nobody else from a list of the people news photos pair them with
        own = re.compile(r"\b(" + "|".join(map(re.escape, need)) + r")\b", re.I)
        lead = files[:len([x for x in claims.get("P18", []) if "datavalue" in x["mainsnak"]])]
        # beyond the Wikidata image, only files whose names say they are a picture of the person: a crop,
        # a portrait, an official photo. A Commons category also holds protest signs, cartoons and posters
        # about a politician, and one of those once landed on a tariff story.
        files = lead + [f for f in files[len(lead):] if need <= _words(f) and FACE.search(f)
                        and not GROUP.search(own.sub("", f)) and not PEOPLE_ART.search(f)]
        SEARCHED.update(f for f in searched if f not in category)
    else:
        q = urllib.parse.quote(f"{subject} filetype:bitmap")
        got = _get(f"https://commons.wikimedia.org/w/api.php?action=query&format=json&list=search"
                   f"&srnamespace=6&srlimit=50&srsearch={q}")["query"]["search"]
        # the whole name as a phrase: word overlap let "Anthropic" match a museum textile with an "anthropic
        # figure" and "Rockstar Games" match a fan in a branded shirt
        phrase = re.compile(r"(?<![a-z0-9])" + re.escape(subject.strip()) + r"(?![a-z0-9])", re.I)
        for m in got:
            name = m["title"][5:]
            # full-text search matches descriptions too; the title is the only part that says what is shown
            shows = (not company or PREMISES.search(phrase.sub(" ", name))
                     or (AIR_COMPANY.search(subject) and AIRCRAFT.search(name)))
            # a short name is many companies: "ABC" found the Australian broadcaster's Darwin office for a story
            # about the US network
            if company and len(re.sub(r"[^A-Za-z0-9]", "", subject)) <= 4:
                shows = False
            # "<act> - <venue>" is an act's photo filed under the venue's name
            billed = re.search(r"\S\s+[-–]\s+(?=" + re.escape(subject.strip()) + r")", name, re.I)
            if (subject.strip() and phrase.search(name) and shows and not PEOPLE.search(name) and not NATURE.search(name)
                    and not ART.search(name) and not CROWD.search(name) and not EVENT.search(name) and not billed
                    and company_context(name, subject)):
                files.append(name)
    seen, out = set(), []
    for f in files:
        if f not in seen and f.lower().endswith((".jpg", ".jpeg")) and not NOT_PHOTO.search(f):
            seen.add(f)
            out.append(f)
    return out


# what a photo of a place or an organisation found by name must not be: people on a street, a march, a talk
STRICT_NOT = re.compile(r"\b(walking|walks?|talk|talking|giving|speaking|speech|standing|sitting|holding|wearing|march(?:ing)?|"
                        r"protest\w*|queue|crowds?|selfie|portrait|interview|octopus|dog|cat|ceiling|interior|inside|detail)\b", re.I)


# a map, chart or logo is filed under a category that says so even when the file name does not ("2026 FIFA World cup.jpg")
GRAPHIC = re.compile(r"\b(maps?|diagrams?|infographics?|charts?|graphs?|logos?|icons?|flags?|svg|illustrations?)\b", re.I)


def fresh_photo(subjects, used, fetch=True, allow="", teams=False, strict=False):
    """(path, credit, file) for the first reusable photo, across the subjects in order, that is not in `used`.

    Each subject is (text, is_person). Rotating through a person's whole Commons category is what keeps
    the tenth story about the same founder from carrying the same face.
    """
    if not fetch:
        return None, "", ""
    CACHE.mkdir(parents=True, exist_ok=True)
    for subject in subjects:
        text, is_person = subject[0], subject[1]
        role = subject[2] if len(subject) > 2 else None
        if not text:
            continue
        try:
            # the premises rule is for a company's photos; a place named in the headline (strict) and a sport ground
            # (teams) have their own checks
            names = candidates(text, is_person, company=not (is_person or strict or teams), role=role)
        except Exception:  # noqa: BLE001  one failed lookup moves on to the next subject
            continue
        for f in names[:30]:
            if f in used:
                continue
            # strict (a place or organisation named in the headline): the title leads with the name, shows no people
            # doing things, and no longer gets the benefit of the doubt for naming other places or brands
            if strict and (not re.match(r"^[\W\d_]*" + re.escape(text.strip()), f, re.I) or STRICT_NOT.search(f)
                           or PEOPLE.search(f) or CROWD.search(f) or PEOPLE_ART.search(f)):
                continue
            try:
                info = _commons_info(f, width=1600)
            except Exception:  # noqa: BLE001
                continue
            ok, credit = photo_ok(info)
            desc = re.sub(r"<[^>]+>", " ", (info.get("extmetadata", {}).get("ImageDescription") or {}).get("value", ""))
            # the title says what is shown; a description is often a caption about something else, so it
            # is checked for brands only, and only when the file is not a photo of the story's own subject
            desc_brands = " ".join(BRANDS.findall(desc))
            # a person's own name does not excuse a place: "Claudia Sheinbaum Argentina v Spain" is a football match
            if foreign_brand(f, allow + " " + text, own="" if (strict or is_person) else text) or (
                    not is_person and foreign_names(f, allow + " " + text)) or (
                    not is_person and foreign_brand(desc_brands, allow + " " + text, own=f)):
                continue
            cats = (info.get("extmetadata", {}).get("Categories") or {}).get("value", "").replace("|", " ")
            if GRAPHIC.search(cats):
                continue
            # a file found by name alone may show a namesake: its description or categories must carry the role
            if is_person and role is not None and f in SEARCHED:
                if not _role_words(role) & _role_words(desc + " " + cats):
                    continue
            if teams:
                if foreign_team(f"{f} {desc} {cats}", allow + " " + text):
                    continue
            # an archive scan from 1920 is free to use and wrong for today's news
            when = (info.get("extmetadata", {}).get("DateTimeOriginal") or {}).get("value", "")
            year = re.search(r"\b(1[89]\d\d|20\d\d)\b", re.sub(r"<[^>]+>", "", when))
            if year and int(year.group(1)) < 2008:
                continue
            # a small or thin image looks broken across a full card
            if not ok or (info.get("width") or 0) < 900 or (info.get("height") or 0) < 600:
                continue
            p = CACHE / f"img-{_slug(f)[:80]}.jpg"
            if not p.exists():
                p.write_bytes(_get(info.get("thumburl") or info["url"], raw=True))
            return p, credit, f
    return None, "", ""
