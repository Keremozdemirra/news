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
                 f"&iiprop=url|extmetadata|metadata{extra}&titles={t}")["query"]["pages"]
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
