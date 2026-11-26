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
from pathlib import Path

from .feeds import CTX, UA as UA_STRING

CACHE = Path(__file__).resolve().parent.parent / "assets" / "cache"
UA = {"User-Agent": UA_STRING}
OK_LICENCES = re.compile(r"^(CC BY(-SA)? [\d.]+|CC0|Public domain|OGL|Open Government Licence)", re.I)
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


def photo_ok(info):
    """(ok, credit). Reuse needs a free licence and no agency in author, credit or EXIF copyright."""
    meta = info.get("extmetadata", {})
    lic = meta.get("LicenseShortName", {}).get("value", "")
    artist = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip()
    exif = " ".join(str(m.get("value", "")) for m in (info.get("metadata") or []) if m.get("name") in ("Copyright", "Artist"))
    credit_line = re.sub(r"<[^>]+>", "", meta.get("Credit", {}).get("value", ""))
    if not OK_LICENCES.match(lic) or AGENCIES.search(" ".join((artist, exif, credit_line))):
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
        label, claims = _entity(name)
        # the top search hit can be a neighbour of the company: "S&P" finds the S&P 500 index
        extra = (label or "").lower().replace(name.lower(), "", 1) if label and name.lower() in label.lower() else None
        if extra is None or re.search(r"\d", extra):
            raise LookupError(f"Wikidata's {label!r} is not {name!r}")
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
                       r"coat of arms|signature|poster|banner", re.I)
# a photo of a topic must not put a person on a story they are not in: a search for "press conference"
# once returned the President of the United States for a story about state attorneys general
PEOPLE = re.compile(r"\b(president|minister|senator|governor|secretary|ceo|chairman|mayor|king|queen|prince|pope|"
                    r"press conference|holds|meets|meeting|speaks|speech|visit|delegation|representatives|portrait|"
                    r"interview|summit|ceremony|rally|protest|selfie|headshot|wedding|funeral|team photo|"
                    # scenes a reader takes as part of the news: a fighter jet beside an airliner is not "an airline"
                    r"military|fighter|interception|army|navy|war|weapon|missile|police|crash|accident|fire|"
                    r"explosion|disaster|flood|riot|emergency)\b", re.I)
FACE = re.compile(r"cropped|crop\b|portrait|official|headshot", re.I)
PEOPLE_ART = re.compile(r"guilty|convicted|impeach|sign|poster|banner|placard|mural|cartoon|caricature|meme|graffiti|"
                        r"effigy|mask|costume|parody|protest|rally|march|vote|ballot|campaign|sticker|flag", re.I)
GROUP = re.compile(r"\b(with|and|meets|meeting|delegation|visit|group|team|family|ceremony|summit|tweet|notes|"
                   r"endorsed|cartoon|meme|caricature|parody|drawing|illustration|graffiti|mural|protest|sign|"
                   r"trump|biden|putin|xi|modi|obama|harris|vance|zuckerberg|bezos|gates|altman|musk|huang|"
                   r"nadella|pichai|amodei|hassabis)\b|[A-Z][a-z]+-[A-Z][a-z]+", re.I)
WORD_ = re.compile(r"[a-z][a-z0-9]+")


def _words(text):
    return {w for w in WORD_.findall((text or "").lower()) if len(w) > 2}


def candidates(subject, person=False):
    """Commons JPEG names that may show the subject: a person's Wikidata image and category, or a search
    whose hits must name the subject in their own title and must not be photos of people or events."""
    files = []
    if person:
        _, claims = _entity(subject)
        files += [x["mainsnak"]["datavalue"]["value"] for x in claims.get("P18", []) if "datavalue" in x["mainsnak"]]
        cats = [x["mainsnak"]["datavalue"]["value"] for x in claims.get("P373", []) if "datavalue" in x["mainsnak"]]
        for cat in cats[:1]:
            t = urllib.parse.quote("Category:" + cat)
            got = _get(f"https://commons.wikimedia.org/w/api.php?action=query&format=json&list=categorymembers"
                       f"&cmtitle={t}&cmtype=file&cmlimit=50")["query"]["categorymembers"]
            # a photo of the person with someone else puts that someone on the story
            files += [m["title"][5:] for m in got]
        # many people have a handful of files in their category and many more elsewhere; a title that
        # carries the full name and nobody else's is a photo of them
        q = urllib.parse.quote(f'"{subject}" filetype:bitmap')
        got = _get(f"https://commons.wikimedia.org/w/api.php?action=query&format=json&list=search"
                   f"&srnamespace=6&srlimit=50&srsearch={q}")["query"]["search"]
        need = _words(subject)
        files += [m["title"][5:] for m in got]
        # the title must name the person, and nobody else from a list of the people news photos pair them with
        own = re.compile(r"\b(" + "|".join(map(re.escape, need)) + r")\b", re.I)
        lead = files[:len([x for x in claims.get("P18", []) if "datavalue" in x["mainsnak"]])]
        # beyond the Wikidata image, only files whose names say they are a picture of the person: a crop,
        # a portrait, an official photo. A Commons category also holds protest signs, cartoons and posters
        # about a politician, and one of those once landed on a tariff story.
        files = lead + [f for f in files[len(lead):] if need <= _words(f) and FACE.search(f)
                        and not GROUP.search(own.sub("", f)) and not PEOPLE_ART.search(f)]
    else:
        q = urllib.parse.quote(f"{subject} filetype:bitmap")
        got = _get(f"https://commons.wikimedia.org/w/api.php?action=query&format=json&list=search"
                   f"&srnamespace=6&srlimit=50&srsearch={q}")["query"]["search"]
        want = _words(subject) - {"photo", "image", "picture", "building", "the"}
        for m in got:
            name = m["title"][5:]
            have = _words(name)
            # full-text search matches descriptions too; the title is the only part that says what is shown
            if want and len(want & have) * 2 >= len(want) and not PEOPLE.search(name):
                files.append(name)
    seen, out = set(), []
    for f in files:
        if f not in seen and f.lower().endswith((".jpg", ".jpeg")) and not NOT_PHOTO.search(f):
            seen.add(f)
            out.append(f)
    return out


def fresh_photo(subjects, used, fetch=True):
    """(path, credit, file) for the first reusable photo, across the subjects in order, that is not in `used`.

    Each subject is (text, is_person). Rotating through a person's whole Commons category is what keeps
    the tenth story about the same founder from carrying the same face.
    """
    if not fetch:
        return None, "", ""
    CACHE.mkdir(parents=True, exist_ok=True)
    for text, is_person in subjects:
        if not text:
            continue
        try:
            names = candidates(text, is_person)
        except Exception:  # noqa: BLE001  one failed lookup moves on to the next subject
            continue
        for f in names[:30]:
            if f in used:
                continue
            try:
                info = _commons_info(f, width=1600)
            except Exception:  # noqa: BLE001
                continue
            ok, credit = photo_ok(info)
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
