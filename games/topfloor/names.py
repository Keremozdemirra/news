"""Names to keys: the one place that decides which spellings of an answer Topfloor accepts.

build_lists.py and build_data.py both use it, the tests exercise it, and js/match.js mirrors norm(), variants()
and find() for the player's guess. A key is a folded spelling; a core is a name with its legal form and the
category's generic words taken out ("Bayerische Landesbank" -> "bayerische"), tried only after every key failed.
"""
import re, unicodedata

_MAP = str.maketrans({"ø": "o", "đ": "d", "ł": "l", "æ": "ae", "œ": "oe", "ı": "i", "þ": "th", "ð": "d", "ß": "ss"})
_UML = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue"})
# legal forms and company words that people leave off, in any position at the end of a name
LEGAL = ("inc incorporated ltd limited plc llc lp llp corp corporation co company cos ag sa se nv bv spa srl sas sarl gmbh kg kgaa "
         "ab oyj asa as a/s aps oy pty pte pjsc ojsc jsc psc tbk bhd sdn kk group groupe gruppe grupo holdings holding hldgs "
         "international intl worldwide global and").split()
SUFFIX = re.compile(r"\s(?:" + "|".join(re.escape(w) for w in LEGAL) + r")$")
STOP = set("of the and de la le du des del della di da do dos das der die das den von van for in a an el y e und et & i".split())
# words that say what kind of thing it is, per prompt; a guess that only differs by them still counts
GENERIC = {
    "bank": "bank banks banking banco banca banque banka bankasi bankas bancorp bancorporation bancshares landesbank sparkasse savings trust financial finance national commercial",
    "central-bank": "central bank banks banco banque banca national reserve monetary authority nationalbank zentralbank bankasi merkez state federal",
    "carmaker": "motor motors motorcars automobile automobiles automotive automobili auto autos car cars vehicles vehicle works manufacturing manufacturer",
    "airline": "air airline airlines airways airway aviation aero aerolineas lineas aereas linhas aereas lines flug fluggesellschaft express",
    "exchange": "stock stocks exchange exchanges bourse borsa bolsa borse securities valores market markets",
    "currency": "currency",
    "crypto": "coin token cryptocurrency crypto protocol network",
    "supermarket": "supermarket supermarkets supermarche supermercado supermercados markets market stores store foods food hypermarket",
    "index": "index indices indexes stock market share composite",
    "fast-food": "restaurant restaurants restaurante foods food",
    "publisher": "games game entertainment interactive studios studio software digital publishing",
    "brewery": "brewery breweries brewing brewers brewer brauerei brasserie cerveceria cervejaria birra birrificio bryggeri beer bier",
    "boardread": "",
}


# Category nouns of any prompt, and everyday words. A guess made only of these, the little words and the legal forms
# names nothing: "car", "airline", "new", "group", "pizza". js/match.js carries the same two lists; a test compares them.
KIND = set("""pizza pizzeria burger burgers hamburger hamburgers chicken coffee cafe grill kitchen sandwich sandwiches taco tacos fries
    bakery donut donuts beer bier ale lager pils wine drink drinks pub bar car cars truck trucks bus bike bikes auto autos motor motors
    bank banks banking money cash coin coins token tokens crypto currency stock stocks share shares index exchange market markets
    store stores shop shops mart food foods grocery groceries supermarket game games gaming play video studio studios publisher
    air airline airlines airways aviation flight flights fly plane planes brewery breweries brewing brewer brewers restaurant
    restaurants fast automobile automobiles automotive vehicle vehicles works manufacturing manufacturer lines savings trust financial
    finance commercial reserve monetary authority federal securities composite entertainment interactive software publishing network
    protocol cryptocurrency supermarkets hypermarket""".split())
COMMON = set("""new old big small little great grand best good better super top max mini maxi mega plus pro one two three four five six seven
    eight nine ten first second third last next all any every some more most much many only own same other another this that these those
    it its are was be to on at by with from up out off over under no not yes we us our you your my me he she they them
    red blue green black white gold golden silver yellow orange pink brown grey gray dark light bright north south east west northern
    southern eastern western central middle upper lower inner outer national international global world worldwide universal general
    royal imperial united union american european asian african british english french german italian spanish turkish people peoples
    city town state states country county land island home house family friends free open fresh fast quick easy simple real true pure
    jet star sun moon sky sea ocean river lake mountain earth fire water king queen prince crown time day night week year today now
    happy lucky love life live go get make made use see look come good bad high low long short hot cold young happy
    express direct premium prime classic original standard special modern future smart digital online net web tech service services
    banana apple test name thing things stuff nothing something anything none idk dunno what which who how why""".split())


def norm(s: str, umlaut=False) -> str:
    """Case, accents and punctuation folded. umlaut=True writes ä ö ü as ae oe ue instead of a o u."""
    s = s.lower()
    if umlaut:
        s = s.translate(_UML)
    s = unicodedata.normalize("NFKD", s.translate(_MAP))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("&", " and ").replace("+", " and ")
    s = re.sub(r"['’`´]", "", s)                 # McDonald's and McDonalds are one spelling
    s = re.sub(r"[^\w]+|_", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"^the ", "", s)


def strip_legal(k: str) -> str:
    while True:
        v = SUFFIX.sub("", k)
        if v == k or len(v) < 2:
            return k
        k = v


def solid(k: str) -> str:
    """A key as it is stored and compared: no spaces and no "and", so "Bayern LB", "BayernLB" and "Marks & Spencer",
    "Marks Spencer" are each one spelling."""
    return "".join(t for t in k.split() if t != "and")


def spaced(name: str) -> list:
    """The folded spellings of one written name, words still apart: plain, umlauts spelled out, legal form dropped."""
    out = []
    for u in (False, True):
        k = norm(name, u)
        for v in (k, strip_legal(k)):
            if len(v) >= 2 and v not in out:
                out.append(v)
    return out


def variants(name: str) -> list:
    """Every key one written name stands for."""
    out = []
    for v in spaced(name):
        w = solid(v)
        if len(w) >= 2 and w not in out:
            out.append(w)
    return out


def core(key: str, pid: str) -> str:
    """The distinctive part of a key: generic words of the prompt, legal forms and little words removed."""
    gen = set(GENERIC.get(pid, "").split())
    toks = []
    for t in strip_legal(key).split():
        if t in STOP or t in gen or t in LEGAL:
            continue
        for g in sorted(gen, key=len, reverse=True):      # German writes it solid: landesbank, vereinsbank, bundesbank
            if len(g) >= 4 and t.endswith(g) and len(t) - len(g) >= 4:
                t = t[: -len(g)]
                t = t[:-1] if t.endswith("s") and len(t) > 4 else t
                break
        toks.append(t)
    c = "".join(toks)
    return c if len(c) >= 4 and not c.isdigit() else ""


def latin(s: str) -> bool:
    """A name a player on a Latin keyboard could type."""
    letters = [c for c in s if c.isalpha()]
    return bool(letters) and sum(unicodedata.name(c, "").startswith("LATIN") for c in letters) / len(letters) > 0.9


def dl1(a: str, b: str) -> bool:
    """True when a and b are one typo apart: one letter wrong, missing, extra, or two neighbours swapped."""
    la, lb = len(a), len(b)
    if a == b or abs(la - lb) > 1:
        return a == b
    i = 0
    while i < min(la, lb) and a[i] == b[i]:
        i += 1
    if la == lb:
        return a[i + 1:] == b[i + 1:] or (i + 1 < la and a[i] == b[i + 1] and a[i + 1] == b[i] and a[i + 2:] == b[i + 2:])
    return a[i + 1:] == b[i:] if la > lb else a[i:] == b[i + 1:]


FUZZ_MIN = 7   # a typo is forgiven only on a name at least this long


def sig(name: str, pid: str) -> str:
    """What is left of a name once the little words, legal forms and category nouns are out."""
    gen = set(GENERIC.get(pid, "").split())
    return "".join(t for t in norm(name).split() if t not in STOP and t not in LEGAL and t not in gen and t not in KIND)


def names_it(entry, pid: str, guess: str) -> bool:
    """False when the guess is only category nouns and everyday words and so cannot be told from a random one.
    Such a guess counts as an entry's whole name of several words ("Lucky Stores", "Burger King"), as a well-known
    entry's one-word name ("King"), or as a best-known name without its category words ("United" for United Airlines)."""
    toks = norm(guess).split()
    # the prompt's own filler words are not on this side: "Sparkasse" and "Merkez Bankası" are filler in a name and answers alone
    if any(t not in STOP and t not in LEGAL and t not in KIND and t not in COMMON for t in toks):
        return True
    s, whole = sig(guess, pid), solid(norm(guess)) in (solid(norm(entry[0])), solid(norm(entry[0], True)))
    if not s:
        return False                    # "car", "the bank", "stock exchange", whoever is called that
    if len(toks) > 1:                   # several words: the entry's whole name, or a well-known one without its category words
        return whole or (entry[2] <= 1 and s == sig(entry[0], pid))
    return (whole and entry[2] <= 1) or (entry[2] == 0 and s == sig(entry[0], pid))


def find(entries, pid, guess):
    """Index of the entry a guess means, or None. Order: exact key, core, one typo. Entries are most familiar first,
    so the first hit is the best known one. js/match.js does the same on the player's device."""
    i = lookup(entries, pid, guess)
    return i if i is not None and names_it(entries[i], pid, guess) else None


def lookup(entries, pid, guess):
    if not hasattr(lookup, "_idx") or lookup._idx[0] is not entries:
        keys, cores = {}, {}
        for i, e in enumerate(entries):
            for k in e[3]:
                keys.setdefault(k, i)
            for c in (e[4] if len(e) > 4 and isinstance(e[4], list) else []):
                cores.setdefault(c, i)
        lookup._idx = (entries, keys, cores)
    _, keys, cores = lookup._idx
    vs = variants(guess)
    for v in vs:
        if v in keys:
            return keys[v]
    for v in spaced(guess):
        c = core(v, pid)
        if c and c in keys:              # "Deutsche Bank AG Group" still means the key "deutsche"
            return keys[c]
        if c and c in cores:
            return cores[c]
    best = None
    for v in vs:
        if len(v) < FUZZ_MIN:
            continue
        for k, i in keys.items():
            if abs(len(k) - len(v)) <= 1 and len(k) >= FUZZ_MIN and (best is None or i < best) and dl1(v, k):
                best = i
    return best


def stray(entry, pid: str, words) -> list:
    """Keys of a little-known entry that are dictionary words and no word of its name: airline codes and odd aliases
    ("banana" for Ronimo Games, "ten" for Tennessee Airways). Nobody means the entry by them; a random word hits them."""
    if entry[2] < 2:
        return []
    own = set(norm(entry[0]).split()) | set(norm(entry[0], True).split()) | {solid(norm(entry[0])), sig(entry[0], pid)}
    return [k for k in entry[3] + (entry[4] if len(entry) > 4 else []) if len(k) >= 3 and k in words and k not in own]
