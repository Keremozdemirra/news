"""IndexNow: tells Bing, Yandex, Seznam, Naver and the other participating engines which pages are new, right after a
deploy. Google does not take part (Search Console covers it). Protocol read 2026-11-27 at indexnow.org/documentation:
POST JSON {host, key, keyLocation, urlList} to https://api.indexnow.org/indexnow; the key is public by design and is
proven by a text file holding it at keyLocation; up to 10,000 URLs per call; 200 or 202 means received."""
import json
import re
import urllib.request
from pathlib import Path

KEY = "9d3fc154baaa5ce444f3553488f3c208"  # gitleaks:allow (public by protocol)
ENDPOINT = "https://api.indexnow.org/indexnow"
LOC = re.compile(r"<loc>([^<]+)</loc>")
MAX = 10000


def locs(text):
    return LOC.findall(text or "")


def new_urls(built_sitemap, live_sitemap):
    """Pages in the sitemap just built that the live site did not list before this deploy. Only new pages: the front
    page and listings change on every build, and resubmitting them each time is what the protocol asks you not to do."""
    old = set(locs(live_sitemap))
    return [u for u in locs(built_sitemap) if u not in old][:MAX]


def ping(site, urls, opener=urllib.request.urlopen):
    """Sends the list; returns the HTTP status, or 0 when there was nothing to send."""
    if not urls:
        return 0
    host = site.split("://", 1)[-1].strip("/")
    body = json.dumps({"host": host, "key": KEY, "keyLocation": f"{site}/{KEY}.txt", "urlList": urls}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "boardread.news build"})
    with opener(req, timeout=30) as r:
        return getattr(r, "status", 200)


def main(site_dir, live_sitemap_file, site):
    built = (Path(site_dir) / "sitemap.xml").read_text()
    live = Path(live_sitemap_file).read_text() if Path(live_sitemap_file).exists() else ""
    urls = new_urls(built, live)
    try:
        status = ping(site, urls)
    except Exception as e:  # noqa: BLE001
        print(f"indexnow: not sent ({type(e).__name__}: {str(e)[:120]})")
        return 0  # a missed ping never fails the deploy; the next new page is sent with the next build
    print(f"indexnow: {len(urls)} new page(s)" + (f", HTTP {status}" if urls else ", nothing to send"))
    return 0
