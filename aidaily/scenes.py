"""Scene photos: what a story carries when nothing shows its own person, company or named place.

aidaily/scenes.json maps keyword rules and the eight topics to Commons files a person looked at one by one: wide
shots with no identifiable private person as the subject, no other company's brand and no flag of a country the
story does not name. A story takes the least recently used file of its entry, so the front page does not run the
same refinery twice in a day, and a list that runs out starts over with the file used longest ago."""
import json
import re
import zlib
from pathlib import Path

from . import entities

DATA = Path(__file__).with_name("scenes.json")
MIN_WIDTH = 1400  # a card is 1080 wide
FALLBACK_TOPICS = ("Business", "World")


def load():
    return json.loads(DATA.read_text())


def entries(headline, topic, data=None, sport=False):
    """The lists to try, best first: the first keyword rule the headline matches, the story's topic, then the two
    general ones. Each item is {"file", "alt"}. A sport story reads the sport rules (a ground or a court of its own
    sport) and then the Sport topic; the news rules would read "city" and "united" as place names."""
    data = data or load()
    out = []
    for rule in data["sport"] if sport else data["rules"]:
        if re.search(rule["match"], headline or "", re.I):
            out.append(rule["files"])
            break
    for t in (("Sport",) if sport else (topic,) + FALLBACK_TOPICS):
        if t in data["topics"] and data["topics"][t] not in out:
            out.append(data["topics"][t])
    return out


def order(items, used, last=None, seed=""):
    """Items not in `used` first (rotated by the story, so two stories in one run differ even before anything is
    used); once all are used, the one used longest ago first. `last` maps a file to the ISO time it last ran."""
    last = last or {}
    key = zlib.crc32(seed.encode())
    spin = key % len(items) if items else 0
    ring = items[spin:] + items[:spin]
    fresh = [i for i in ring if i["file"] not in used]
    return fresh + sorted((i for i in ring if i["file"] in used), key=lambda i: last.get(i["file"], ""))


def photo(headline, topic, used, last=None, fetch=True, data=None, sport=False):
    """(path, credit, file, alt) of the scene photo to use, or four empty strings when nothing could be fetched."""
    if not fetch:
        return None, "", "", ""
    entities.CACHE.mkdir(parents=True, exist_ok=True)
    seen = set()
    for items in entries(headline, topic, data, sport):
        for item in order(items, used, last, seed=headline):
            f = item["file"]
            if f in seen:
                continue
            seen.add(f)
            try:
                info = entities._commons_info(f, width=MIN_WIDTH)
                ok, credit = entities.photo_ok(info)
                if not ok or (info.get("width") or 0) < MIN_WIDTH:
                    continue
                p = entities.CACHE / f"img-{entities._slug(f)[:80]}.jpg"
                if not p.exists():
                    p.write_bytes(entities._get(info.get("thumburl") or info["url"], raw=True))
            except Exception:  # noqa: BLE001  a file that will not load moves on to the next
                continue
            return p, credit, f, item.get("alt", "")
    return None, "", "", ""
