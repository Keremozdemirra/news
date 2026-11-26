"""SEO audit of a built site directory: what Google News, Discover and Search read, checked on the real files.

  python3 -m aidaily seo _site            exit 1 on errors, warnings printed

Errors (things that break eligibility or point Google at the wrong address):
  - a page without a canonical link, a canonical outside site_url, og:url not equal to the canonical
  - the old address keremozdemir.de/news anywhere in a page, feed or sitemap (the domain move must be complete)
  - JSON-LD that does not parse; a NewsArticle without headline, image, datePublished with a timezone, author or
    publisher logo; a headline over 110 characters
  - a sitemap <loc> outside site_url; a news sitemap over 1,000 entries; a noindex page listed in a sitemap
  - an internal link to a file that does not exist
Warnings: images without width and height (layout shift), pages over 200 KB of HTML, news-sitemap entries older
than two days, robots.txt not naming every sitemap.

Sources read 2026-11-26: developers.google.com/search/docs/appearance/structured-data/article,
.../crawling-indexing/sitemaps/news-sitemap, .../appearance/google-discover.
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

OLD = "keremozdemir.de/news"
CANON = re.compile(r'<link rel="canonical" href="([^"]+)"')
OGURL = re.compile(r'<meta property="og:url" content="([^"]+)"')
LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
HREF = re.compile(r'\s(?:href|src)="([^"#?]+)')
IMG = re.compile(r"<img\b[^>]*>")
NOINDEX = re.compile(r'<meta name="robots" content="[^"]*noindex')
LOC = re.compile(r"<loc>([^<]+)</loc>")
NEWS_DATE = re.compile(r"<news:publication_date>([^<]+)</news:publication_date>")
TZ = re.compile(r"(Z|[+-]\d\d:?\d\d)$")
MAX_HTML = 200_000


def organization(site_url, name="Boardread", accounts=()):
    """The publisher as schema.org NewsMediaOrganization: its logo, its own channels (sameAs) and the pages that state
    its standards. Google's Article docs ask for publisher name, url and logo; publishingPrinciples, correctionsPolicy
    and verificationFactCheckingPolicy are schema.org properties of NewsMediaOrganization that point at the pages
    Google's news content policies ask a publisher to show (who runs it, how it corrects, how to reach it)."""
    site = site_url.rstrip("/")
    org = {"@type": "NewsMediaOrganization", "name": name, "url": site + "/",
           "logo": {"@type": "ImageObject", "url": f"{site}/logo.png"},
           "publishingPrinciples": f"{site}/standards/", "correctionsPolicy": f"{site}/standards/",
           "verificationFactCheckingPolicy": f"{site}/how-it-works/", "ethicsPolicy": f"{site}/standards/",
           "contactPoint": {"@type": "ContactPoint", "contactType": "corrections", "url": f"{site}/contact/"}}
    same = [a["url"] for a in accounts if a.get("url")]
    if same:
        org["sameAs"] = same
    return org


def _unescape(s):
    return s.replace("&amp;", "&").replace("&quot;", '"').replace("&#x27;", "'").replace("&#39;", "'")


def check_article(ld, where, out):
    need = {"headline": ld.get("headline"), "image": ld.get("image"), "datePublished": ld.get("datePublished"),
            "author": ld.get("author"), "publisher": ld.get("publisher")}
    for k, v in need.items():
        if not v:
            out.append(("error", where, f"NewsArticle without {k}"))
    if len(ld.get("headline") or "") > 110:
        out.append(("error", where, "NewsArticle headline over 110 characters"))
    for k in ("datePublished", "dateModified"):
        if ld.get(k) and not TZ.search(ld[k]):
            out.append(("error", where, f"{k} without a timezone: {ld[k]}"))
    imgs = ld.get("image") if isinstance(ld.get("image"), list) else [ld.get("image")]
    for i in imgs:
        u = i.get("url") if isinstance(i, dict) else i
        if u and not str(u).startswith("https://"):
            out.append(("error", where, f"image not an absolute https URL: {u}"))
    authors = ld.get("author") if isinstance(ld.get("author"), list) else [ld.get("author") or {}]
    for a in authors:
        if not (a.get("name") and a.get("url")):
            out.append(("error", where, "author needs a name and a url"))
    logo = (ld.get("publisher") or {}).get("logo") or {}
    if not (logo.get("url") if isinstance(logo, dict) else logo):
        out.append(("error", where, "publisher without a logo"))


def _target(root, base, url):
    """The file a site-internal URL path is served from, or None when it is not internal."""
    if not url.startswith("/") or url.startswith("//"):
        return None
    path = url[len(base):] if base and url.startswith(base + "/") else (url if not base else None)
    if path is None:
        return None
    p = root / path.lstrip("/")
    return p / "index.html" if url.endswith("/") else p


def audit(root, site_url, now=None):
    root, site_url = Path(root), site_url.rstrip("/")
    base = "/" + site_url.split("/", 3)[3] if site_url.count("/") >= 3 else ""
    now = now or datetime.now(timezone.utc)
    out, noindexed = [], set()
    pages = sorted(root.rglob("*.html"))
    for f in pages:
        rel = "/" + str(f.relative_to(root)).replace("index.html", "")
        text = f.read_text(errors="replace")
        if OLD in text:
            out.append(("error", rel, f"mentions the old address {OLD}"))
        if f.name == "404.html" or 'http-equiv="refresh"' in text:
            continue
        if NOINDEX.search(text):
            noindexed.add(site_url + rel)
        canon = CANON.search(text)
        if not canon:
            out.append(("error", rel, "no canonical link"))
        else:
            c = _unescape(canon.group(1))
            if not c.startswith(site_url + "/"):
                out.append(("error", rel, f"canonical outside {site_url}: {c}"))
            og = OGURL.search(text)
            if og and _unescape(og.group(1)) != c:
                out.append(("error", rel, "og:url differs from the canonical"))
        for block in LD.findall(text):
            try:
                data = json.loads(block)
            except ValueError as e:
                out.append(("error", rel, f"JSON-LD does not parse: {e}"))
                continue
            for item in data if isinstance(data, list) else [data]:
                if item.get("@type") == "NewsArticle":
                    check_article(item, rel, out)
        missing = sorted({u for u in HREF.findall(text) if (t := _target(root, base, u)) is not None and not t.exists()})
        for u in missing[:5]:
            out.append(("error", rel, f"internal link to a missing file: {u}"))
        for tag in IMG.findall(text):
            if "width=" not in tag or "height=" not in tag:
                out.append(("warn", rel, "img without width and height"))
                break
        if len(text.encode()) > MAX_HTML:
            out.append(("warn", rel, f"{len(text.encode()) // 1000} KB of HTML"))
    for name in ("sitemap.xml", "news-sitemap.xml", "feed.xml"):
        f = root / name
        if not f.exists():
            continue
        text = f.read_text(errors="replace")
        if OLD in text:
            out.append(("error", "/" + name, f"mentions the old address {OLD}"))
        if name == "feed.xml":
            continue
        locs = LOC.findall(text)
        for u in locs:
            if not u.startswith(site_url + "/"):
                out.append(("error", "/" + name, f"<loc> outside {site_url}: {u}"))
                break
        for u in set(locs) & noindexed:
            out.append(("error", "/" + name, f"lists a noindex page: {u}"))
        if name == "news-sitemap.xml":
            if len(locs) > 1000:
                out.append(("error", "/" + name, f"{len(locs)} entries, Google reads at most 1,000"))
            for d in NEWS_DATE.findall(text):
                try:
                    if now - datetime.fromisoformat(d.replace("Z", "+00:00")) > timedelta(days=2, hours=1):
                        out.append(("warn", "/" + name, f"entry older than two days: {d}"))
                        break
                except ValueError:
                    out.append(("error", "/" + name, f"publication_date not ISO 8601: {d}"))
                    break
    robots = root / "robots.txt"
    if robots.exists():
        r = robots.read_text()
        for name in ("sitemap.xml", "news-sitemap.xml"):
            if (root / name).exists() and f"{site_url}/{name}" not in r:
                out.append(("warn", "/robots.txt", f"does not name {site_url}/{name}"))
    return out


def main(root, site_url):
    found = audit(root, site_url)
    errors = [x for x in found if x[0] == "error"]
    seen = set()
    for level, where, msg in found:
        key = (level, msg if level == "warn" else where + msg)
        if key in seen:
            continue
        seen.add(key)
        print(f"{level}: {where}: {msg}")
    n_pages = len(list(Path(root).rglob("*.html")))
    print(f"seo audit: {n_pages} pages, {len(errors)} error(s), {len(found) - len(errors)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
