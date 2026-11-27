#!/usr/bin/env python3
"""Links and assets of a built site directory, checked on the files (no network).

  python3 scripts/linkcheck.py [DIR]      DIR defaults to _site; exit 1 with one line per finding

Beyond what `aidaily seo` already checks (href and src that point at a missing file), this reads the places a broken
asset hides: srcset candidates, CSS url() references, og:image and twitter:image, JSON-LD image URLs on this site, the
#fragment of an internal link (the id must exist on the target page), and any referenced file that is empty. An address
that resolves to a folder needs its index.html. External links are not fetched.
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urldefrag, urlsplit

ATTR = re.compile(r'\s(?:href|src|poster|data-src)="([^"]*)"')
SRCSET = re.compile(r'\ssrcset="([^"]*)"')
META_IMG = re.compile(r'<meta[^>]+(?:property|name)="(?:og:image|twitter:image)"[^>]+content="([^"]*)"')
LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
ID = re.compile(r'\sid="([^"]+)"')
CSS_URL = re.compile(r'url\(\s*["\']?([^)"\']+)["\']?\s*\)')
SKIP = ("http:", "https:", "mailto:", "tel:", "data:", "javascript:", "sms:", "webcal:", "//")


def site_host(root):
    try:
        return urlsplit(json.loads((Path(root).parent / "desk.json").read_text())["site_url"]).netloc
    except (OSError, ValueError, KeyError):
        return ""


def resolve(root, page, ref, host=""):
    """The file a reference means, or None when it is external or not a path. page: the referring file."""
    ref = ref.strip()
    if not ref or ref.startswith("#"):
        return None
    if ref.startswith(("http://", "https://")):
        parts = urlsplit(ref)
        if not host or parts.netloc != host:
            return None
        ref = parts.path + (f"?{parts.query}" if parts.query else "")
    elif ref.startswith(SKIP):
        return None
    path = unquote(urlsplit(urldefrag(ref)[0]).path)
    base = Path(root) if path.startswith("/") else Path(page).parent
    target = (base / path.lstrip("/")).resolve() if path else Path(page)
    try:
        target.relative_to(Path(root).resolve())
    except ValueError:
        return target  # points out of the site: reported as missing
    return target / "index.html" if target.is_dir() else target


def _ld_images(text):
    for raw in LD.findall(text):
        try:
            doc = json.loads(raw)
        except ValueError:
            continue
        stack = [doc]
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                for k, v in x.items():
                    if k in ("image", "logo", "thumbnailUrl", "contentUrl"):
                        for item in v if isinstance(v, list) else [v]:
                            if isinstance(item, str):
                                yield item
                            elif isinstance(item, dict) and isinstance(item.get("url"), str):
                                yield item["url"]
                    stack.append(v)
            elif isinstance(x, list):
                stack.extend(x)


def refs_of(page, text):
    out = list(ATTR.findall(text)) + META_IMG.findall(text) + list(_ld_images(text))
    for s in SRCSET.findall(text):
        out += [c.strip().split()[0] for c in s.split(",") if c.strip()]
    return out


def check(root):
    root = Path(root).resolve()
    host = site_host(root)
    ids, out = {}, []

    def ids_of(f):
        if f not in ids:
            ids[f] = set(ID.findall(f.read_text(errors="ignore"))) if f.suffix == ".html" else set()
        return ids[f]
    seen_ok = {}
    for page in sorted(root.rglob("*.html")):
        rel = "/" + str(page.relative_to(root))
        text = page.read_text(errors="ignore")
        for ref in refs_of(page, text):
            f = resolve(root, page, ref, host)
            if f is None:
                continue
            if f not in seen_ok:
                seen_ok[f] = "missing" if not f.is_file() else "empty" if f.stat().st_size == 0 else ""
            if seen_ok[f]:
                out.append(f"{rel}: {seen_ok[f]} file for {ref[:90]}")
            elif "#" in ref and not ref.startswith(("http://", "https://")) and f.suffix == ".html":
                frag = unquote(ref.split("#", 1)[1])
                if frag and frag not in ids_of(f) and not frag.startswith(":~:"):
                    out.append(f"{rel}: no #{frag} on {ref.split('#')[0] or 'this page'}")
        for ref in ATTR.findall(text):  # same-page anchors
            if ref.startswith("#") and len(ref) > 1 and unquote(ref[1:]) not in ids_of(page):
                out.append(f"{rel}: no #{ref[1:]} on this page")
    for css in sorted(root.rglob("*.css")):
        for ref in CSS_URL.findall(css.read_text(errors="ignore")):
            f = resolve(root, css, ref, host)
            if f is not None and not (f.is_file() and f.stat().st_size):
                out.append(f"/{css.relative_to(root)}: missing asset url({ref[:80]})")
    return sorted(set(out))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    root = Path(argv[0] if argv else "_site")
    if not (root / "index.html").exists():
        print(f"{root} is not a built site")
        return 2
    found = check(root)
    for f in found[:60]:
        print("FAIL", f)
    print(f"linkcheck: {'clean' if not found else str(len(found)) + ' finding(s)'}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
