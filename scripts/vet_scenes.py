"""Propose scene photos for a person to approve: Commons files for a search, filtered for licence, size, people and
graphics, shown on one numbered contact sheet. Runs on the Mac, never on the runner; nothing joins scenes.json until a
person adds it with its alt (and place or needs when the picture shows a place, text or a commodity).

usage: python3 scripts/vet_scenes.py OUT_DIR "query" ["query" ...]
Writes OUT_DIR/<query>.png (the sheet) and OUT_DIR/<query>.json (file, licence, size, categories) per query.
"""
import html
import json
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aidaily import entities as E, render as R  # noqa: E402

# CC0, public domain and CC BY of any version, with the credit and licence link the card prints (Kerem, 2026-11-27);
# never ShareAlike, NonCommercial or NoDerivatives, never a US-only public domain
OK = re.compile(r"^(?:CC0|Public domain|CC BY \d(?:\.\d)?)$", re.I)
NOT_OK = re.compile(r"\b(?:SA|NC|ND|PD-US|URAA|PD-Art|PD-scan|PD-textlogo|OGL)\b", re.I)


def search(query, limit=40):
    q = urllib.parse.quote(f"{query} filetype:bitmap")
    got = E._get("https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search&gsrnamespace=6"
                 f"&gsrlimit={limit}&gsrsearch={q}&prop=imageinfo&iiprop=url|size|extmetadata&iiurlwidth=360"
                 "&iiextmetadatafilter=LicenseShortName|Categories|DateTimeOriginal|Artist")
    out = []
    for p in (got.get("query") or {}).get("pages", {}).values():
        ii = p["imageinfo"][0]
        m = ii.get("extmetadata", {})
        lic = (m.get("LicenseShortName") or {}).get("value", "")
        cats = (m.get("Categories") or {}).get("value", "")
        name = p["title"][5:]
        when = re.search(r"\b(1[89]\d\d|20\d\d)\b", re.sub(r"<[^>]+>", "", (m.get("DateTimeOriginal") or {}).get("value", "")))
        if (not OK.match(lic.strip()) or NOT_OK.search(lic) or ii.get("width", 0) < 1200 or ii.get("height", 0) < 700
                or E.PERSONALITY.search(cats) or E.PERSON_CAT.search(cats) or E.GRAPHIC.search(re.sub(r"(?i)flags? of [^|]*|flags in [^|]*", "", cats))
                or E.NOT_PHOTO.search(re.sub(r"(?i)\bflags?\b", "", name))
                or E.CROWD.search(name) or (when and int(when.group(1)) < 2008) or not name.lower().endswith((".jpg", ".jpeg"))):
            continue
        out.append({"file": name, "licence": lic, "size": [ii["width"], ii["height"]], "thumb": ii.get("thumburl", ""),
                    "categories": cats[:300]})
    return out


def sheet(items, png):
    cells = "".join(f'<div class="c"><img src="{html.escape(i["thumb"])}"><b>{n}</b><span>{html.escape(i["file"][:60])}'
                    f' · {html.escape(i["licence"])}</span></div>' for n, i in enumerate(items, 1))
    page = ("<html><body style='margin:0;background:#fff;font:13px sans-serif'><style>.g{display:grid;grid-template-columns:"
            "repeat(4,1fr);gap:8px;padding:8px}.c{position:relative}.c img{width:100%;height:200px;object-fit:cover}"
            ".c b{position:absolute;top:4px;left:4px;background:#000;color:#fff;padding:2px 6px;font-size:18px}"
            f".c span{{display:block;height:32px;overflow:hidden}}</style><div class='g'>{cells}</div></body></html>")
    R.shoot(page, png, 1400, 250 * ((len(items) + 3) // 4) + 20)


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for query in sys.argv[2:]:
        items = search(query)[:16]
        slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
        (out / f"{slug}.json").write_text(json.dumps(items, indent=1, ensure_ascii=False))
        if items:
            sheet(items, out / f"{slug}.png")
        print(f"{query}: {len(items)} proposals -> {out / slug}.png")
