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


def fits(item, text):
    """The scene may go on this article: a place-named scene (a skyline, a parliament, a ballot box from a named
    country) only when the article names that place, and a scene that shows one kind of thing (a ballot box, a
    courtroom, a harvest) only when the article is about it. A cow once stood for Alberta's oil money, the Melbourne
    skyline for an Indian trust and a Polish ballot box for Guinea-Bissau's election."""
    places = item.get("place") or []
    if places and not any(re.search(r"(?<![A-Za-z])" + re.escape(n) + r"(?![A-Za-z])", text or "",
                                    0 if n.isupper() or len(n) <= 3 else re.I) for n in places):
        return False
    if item.get("needs") and not re.search(item["needs"], text or "", re.I):
        return False
    return True


def sport_of(text, data):
    """The sport an article is about: its sport rule, or a football club it names; '' when neither says."""
    for rule in data["sport"]:
        if re.search(rule["match"], text or "", re.I):
            return rule["id"]
    for kind, rx in LEAGUES:
        if rx.search(text or ""):
            return kind
    return ""


# entities.TEAMS by league: NFL teams, then NBA (from "celtics"), football clubs (from "arsenal"), F1 teams (from
# "ferrari"). A club named without its sport's name still says which sport the article is about.
_T = entities.TEAMS.pattern
_body = _T[_T.index("(") + 1:_T.rindex(")")]
_NFL, _rest = _body.split("|celtics|", 1)
_NBA, _rest = ("celtics|" + _rest).split("|arsenal|", 1)
_FOOT, _F1 = ("arsenal|" + _rest).split("|ferrari|", 1)
LEAGUES = (("nfl", _NFL), ("nba", _NBA), ("football", _FOOT), ("f1", "ferrari|" + _F1))
LEAGUES = tuple((k, re.compile(r"\b(" + v + r")\b", re.I)) for k, v in LEAGUES)


# One-word triggers that also mean something else in a business story: "AI exports drive Asia growth" is no shipping
# story, "Bank of Japan" no high-street bank. Each counts half, so it needs a second signal before its rule applies.
WEAK = re.compile(r"^(?:tariffs?|exports?|imports?|ports?|ships?|chips?|banks?|banking|fed|jobs?|workers|labou?r|"
                  r"gas|homes?|property|construction|developers?|stores?|shops?|consumers?|tokens?|vehicles?|"
                  r"cars?|autos?|trucks?|outage|passwords?|encryption|inflation|cargo|straits?|processors?|lenders?|"
                  r"utilit(?:y|ies)|batter(?:y|ies)|nuclear|electricity|flights?|aircraft|trade war|employment|hiring)$", re.I)


def rule_score(rule, title, text):
    """How strongly an article is about a rule's subject: each distinct term once, a strong term 2 in the headline and
    1 elsewhere, a weak term half that."""
    score, seen = 0.0, set()
    for m in re.finditer(rule["match"], text or "", re.I):
        term = m.group(0).lower()
        if term in seen:
            continue
        seen.add(term)
        # a weak word written as a name mid-sentence is the institution: "the Fed", "Bank of Japan"
        proper = (m.group(0) == "Fed" or m.group(0)[:1].isupper() and m.start() > 0
                  and not re.search(r"[.!?]\s*$", (text or "")[:m.start()]))
        weight = 0.5 if WEAK.match(term) and not proper else 1.0
        score += weight * (2 if re.search(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", title or "", re.I) else 1)
    return score


def best_rule(rules, title, text):
    """The rule an article is most about, or None when none scores 2 or the top two tie (a ship and a bank in one
    story say neither)."""
    scored = sorted(((rule_score(r, title, text), i, r) for i, r in enumerate(rules)
                     if not (r.get("skip") and re.search(r["skip"], text or "", re.I))), key=lambda x: (-x[0], x[1]))
    if not scored or scored[0][0] < 2 or (len(scored) > 1 and scored[1][0] == scored[0][0]):
        return None
    return scored[0][2]


def entries(headline, topic, data=None, sport=False, title=None):
    """The lists to try, best first: the rule the article is most about (see best_rule), the story's topic, then the
    two general ones. Each item is {"file", "alt"}. `headline` is the text read (headline and summary); `title` the
    headline alone, which counts double (it defaults to the text). A sport story reads the sport rules (a ground or a
    court of its own sport) and then the Sport topic; the news rules would read "city" and "united" as place names."""
    data = data or load()
    title = headline if title is None else title
    gone = set(data.get("retired", []))
    out = []
    if sport:
        for rule in data["sport"]:
            if re.search(rule["match"], headline or "", re.I) and not (rule.get("skip") and re.search(rule["skip"], headline or "", re.I)):
                out.append(rule["files"])
                break
        # the Sport topic only lends a file of the article's own sport: an F1 pit lane is no picture of a football match
        kind = sport_of(headline, data)
        rule = next((r for r in data["sport"] if r["id"] == kind), None)
        if rule and rule["files"] not in out:
            out.append(rule["files"])
        same = [i for i in data["topics"].get("Sport", []) if kind and i.get("sport") == kind]
        if same:
            out.append(same)
        return [[i for i in items if fits(i, headline) and i["file"] not in gone] for items in out]
    rule = best_rule(data["rules"], title, headline)
    if rule:
        out.append(rule["files"])
    for t in (topic,) + FALLBACK_TOPICS:
        if t in data["topics"] and data["topics"][t] not in out:
            out.append(data["topics"][t])
    # a retired file is never picked, whichever list still names it (the audit holds one already on a post)
    return [[i for i in items if fits(i, headline) and i["file"] not in gone] for items in out]


def order(items, used, last=None, seed=""):
    """Items not in `used` first (rotated by the story, so two stories in one run differ even before anything is
    used); once all are used, the one used longest ago first. `last` maps a file to the ISO time it last ran."""
    last = last or {}
    key = zlib.crc32(seed.encode())
    spin = key % len(items) if items else 0
    ring = items[spin:] + items[:spin]
    fresh = [i for i in ring if i["file"] not in used]
    return fresh + sorted((i for i in ring if i["file"] in used), key=lambda i: last.get(i["file"], ""))


def photo(headline, topic, used, last=None, fetch=True, data=None, sport=False, title=None, batch=(), _again=False):
    """(path, credit, file, alt) of the scene photo to use, or four empty strings when nothing could be fetched.
    A file already in `batch` (this run's cards) is never used twice: the next list is tried instead. The voting
    machine ran on six posts of one batch and the New Jersey stadium on four."""
    if not fetch:
        return None, "", "", ""
    entities.CACHE.mkdir(parents=True, exist_ok=True)
    seen = set()
    for items in entries(headline, topic, data, sport, title=title):
        # a file that matched the article by its place or subject goes before a generic one (Westminster for Labour MPs)
        ranked = order(items, used, last, seed=headline)
        for item in sorted(ranked, key=lambda i: not (i.get("place") or i.get("needs"))):
            f = item["file"]
            if f in seen or f in batch:
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
    # every post carries a picture (Kerem): when this batch has used every fitting file, the least recently used one
    # runs again rather than none
    if batch and not _again:
        return photo(headline, topic, used, last, fetch, data, sport, title, (), _again=True)
    return None, "", "", ""
