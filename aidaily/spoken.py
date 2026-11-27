"""The narration script for a Short: how a person would tell a friend the news, written from the published copy and
checked by a gate before any audio is made.

Kerem, 2026-11-27, on the first samples: the script read as AI. So the narration no longer reads the screen text.
A model writes a short spoken script from the published headline, dek and body only, and gate() refuses it unless:
  - it is 55 to 85 words (about 30 seconds), every sentence 20 words or fewer;
  - no phrase from the banned lists below (the humanizer skill's overused words, inflated significance and sales
    language; Kerem's slopcheck list; the stock openers and closers he named), no dash, no question, no "not X but Y";
  - numbers are said as words ("about two billion dollars"): no $, %, "bn" or decimals left in the text;
  - every name in it appears in the published copy, and every fact it rests on is quoted verbatim from that copy.
A script that fails is never voiced; the Short stays silent.
"""
import json
import re

MIN_WORDS, MAX_WORDS, MAX_SENTENCE = 45, 62, 20
REPEAT = 0.6  # a sentence whose content words mostly appear in one earlier sentence restates it

PROMPT = """You've just read this story and you're telling a friend about it, out loud, in about 20 seconds.
Use ONLY the facts in PUBLISHED; add nothing, guess nothing.

How it should sound:
- Open on the thing that happened, in your own words, with one concrete detail (a number, a name, a place).
- Mix sentence lengths: a short one, then a longer one. Start one sentence with "And" or "But" if it fits.
- Fold the source in once, lightly ("France's stats office says", "according to Bloomberg" is fine once).
- Each sentence tells the listener something new. Never repeat or sum up a point already made, not even at the end.
- End on the most interesting concrete fact, or on why it matters to someone if PUBLISHED says why.
- 45 to 60 words, four or five sentences.

Words: plain, specific verbs ("shrank", "jumped", "cut"), not "made more profit" or "saw growth".
Numbers: as people say them, rounded where natural: "zero point two percent", "about twenty-one and a half
trillion won", "nearly three percent". A sum in another currency gets its dollar amount when PUBLISHED gives one or
CONVERSIONS below has it. No symbols, no digits except a year. Each number once.
Contractions are good. Never: questions, lists of three, "not just X but Y", dashes, "earlier on", "this time",
"in money terms", "the numbers come from", "the data shows", "this comes as", "here's what you need to know",
"it remains to be seen", "only time will tell", "so the new figure", "which means".

Return JSON only: {{"script": "...", "facts": ["exact quote from PUBLISHED that each fact rests on", ...]}}

PUBLISHED:
Headline: {headline}
Summary: {dek}
More: {body}
Reported by: {sources}

CONVERSIONS (today's ECB reference rates; use only if the script names one of these sums):
{conversions}
"""

# the humanizer skill, sections 12 (overused AI words), 13 (inflated significance), 16 (sales language)
HUMANIZER = ["additionally", "align with", "bolstered", "crucial", "deep dive", "delve", "emphasiz", "enduring", "enhance",
             "foster", "garner", "highlight", "interplay", "intricate", "key ", "landscape", "meticulous", "pivotal",
             "quietly", "robust", "showcas", "tapestry", "testament", "underscor", "valuable", "vibrant",
             "plays a key role", "marking a", "shaping the", "reflects a broader", "legacy", "setting the stage",
             "evolving", "indelible", "continues to thrive", "the future looks", "exciting times", "step in the right direction",
             "boasts", "profound", "exemplif", "commitment to", "nestled", "in the heart of", "groundbreaking", "renowned",
             "diverse array", "breathtaking", "stunning", "associated with", "in connection with"]
# Kerem's slopcheck list (~/agents/rota/tools/slopcheck.py, 2026-11-27), as plain phrases
SLOPCHECK = ["here's the thing", "heres the thing", "it turns out", "the truth is", "let me be clear", "this matters because",
             "let that sink in", "make no mistake", "at the end of the day", "in today's", "it's worth noting", "game changer",
             "game-changer", "lean into", "moving forward", "circle back", "unpack", "seamlessly", "effortlessly",
             "supercharge", "revolutioni", "unlock", "the implications are", "the stakes are high", "plot twist",
             "really", "actually", "genuinely", "truly", "fundamentally", "crucially", "honestly", "literally",
             "importantly", "interestingly", "inevitably"]
# the stock openers and closers Kerem named, and their cousins
STOCK = ["in a significant development", "in a major development", "this comes as", "this comes after", "here's what you need to know",
         "what you need to know", "let's dive in", "let's take a look", "buckle up", "breaking news", "in a move that",
         "it remains to be seen", "only time will tell", "what does this mean", "the bottom line", "all eyes", "stay tuned",
         "this is a reminder", "a reminder that", "this shows", "in other words", "make sure to", "don't forget",
         # stiff spoken links Kerem's review named (2026-11-27)
         "earlier on", "this time", "in money terms", "the numbers come from", "the figures come from", "the data comes from",
         "reported the figure", "the figure was reported", "according to the report", "the data shows", "the figure shows",
         "the numbers show", "the data show", "made more profit", "saw growth", "so the new figure", "which means"]
BANNED = HUMANIZER + SLOPCHECK + STOCK
CONTRAST = re.compile(r"\bnot (?:just|only|merely)\b[^.]{1,60}\bbut\b|\bit'?s not [^.]{1,40}\. it'?s\b", re.I)
WRITTEN_NUMBER = re.compile(r"[$€£¥₩%]|\b\d+[.,]\d+\b|\b\d+\s?(?:bn|m|k)\b|\b(?!(?:19|20)\d\d\b)\d{2,}\b", re.I)


NUMBER_WORDS = {"zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
                "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty",
                "forty", "fifty", "sixty", "seventy", "eighty", "ninety"}
STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "for", "from", "with", "by", "that", "this", "it",
        "its", "it's", "is", "are", "was", "were", "be", "been", "has", "have", "had", "says", "said", "say", "about",
        "than", "as", "so", "but", "up", "down", "over", "after", "before", "their", "they", "them", "which", "who",
        "now", "also", "just", "into", "out", "more", "less", "year", "per", "cent", "percent", "that's", "there"}


def content_words(sentence):
    return {w for w in re.findall(r"[a-z][a-z'-]+", sentence.lower()) if w not in STOP and len(w) > 2}


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!])\s+", text.strip()) if s.strip()]


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[’‘]", "'", re.sub(r"[“”]", '"', s or ""))).strip().lower()


# a capitalised first word that is just the start of a sentence, not a name
STARTERS = {"the", "a", "an", "it", "its", "it's", "that", "that's", "this", "these", "those", "so", "and", "but", "he",
            "she", "they", "their", "there", "we", "you", "in", "on", "at", "for", "from", "with", "after", "before",
            "earlier", "later", "now", "still", "more", "most", "some", "many", "one", "two", "three", "about", "nearly",
            "over", "under", "last", "next", "today", "yesterday", "meanwhile", "officials", "investors", "voters",
            "prices", "shares", "profit", "net", "twenty", "thirty", "forty", "fifty", "if", "as", "while", "when"}


def names(text):
    """Capitalised words, the first word of a sentence too unless it is an ordinary starter: the names the script uses."""
    out = set()
    for s in sentences(text):
        words = re.findall(r"[A-Za-z][\w'’.-]*", s)
        for i, w in enumerate(words):
            w = w.strip(".'’")
            if w and w[0].isupper() and w.lower() != "i" and not (i == 0 and w.lower() in STARTERS):
                out.add(w)
    return out


UNITS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
                                    "fifteen sixteen seventeen eighteen nineteen".split())}
TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}
BIG = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}
DIGIT_SCALE = {"thousand": 1e3, "k": 1e3, "million": 1e6, "m": 1e6, "mn": 1e6, "billion": 1e9, "bn": 1e9, "b": 1e9,
               "trillion": 1e12, "tn": 1e12, "t": 1e12}
DIGITS = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s?(thousand|million|billion|trillion|bn|mn|tn|k|m|b|t)?\b", re.I)
TOLERANCE = 0.15  # "nearly three percent" for 2.7: a rounded number is fine, a different one is not


def spoken_numbers(text):
    """[(value, phrase)] for the numbers a script says in words that a listener takes as a claim: a percent, a decimal, or
    anything with hundred, thousand, million, billion or trillion. A bare "three" or a year is a count or a date, not a claim."""
    toks = re.findall(r"[a-z]+|\d+", (text or "").lower().replace("-", " "))
    out, i, n = [], 0, len(toks)
    numeric = lambda k: k < n and (toks[k] in UNITS or toks[k] in TENS or toks[k] == "hundred" or toks[k] in BIG)  # noqa: E731
    while i < n:
        a_big = toks[i] == "a" and i + 1 < n and (toks[i + 1] == "hundred" or toks[i + 1] in BIG)
        if not (toks[i] in UNITS or toks[i] in TENS or a_big):
            i += 1
            continue
        start, j, cur, total, claim = i, i + (1 if a_big else 0), 1 if a_big else 0, 0.0, False
        while j < n:
            w = toks[j]
            if w in UNITS:
                cur += UNITS[w]
            elif w in TENS:
                cur += TENS[w]
            elif w == "hundred":
                cur, claim = (cur or 1) * 100, True
            elif w in BIG:
                total, cur, claim = total + (cur or 1) * BIG[w], 0, True
            elif w == "and" and toks[j + 1:j + 3] == ["a", "half"]:
                cur += 0.5
                j += 2
            elif w == "and" and numeric(j + 1) and toks[j + 1] not in BIG and total + cur:
                pass
            else:
                break
            j += 1
        value = total + cur
        if toks[j:j + 1] == ["point"] and toks[j + 1:j + 2] and toks[j + 1] in UNITS:
            k, frac = j + 1, ""
            while k < n and toks[k] in UNITS and UNITS[toks[k]] < 10:
                frac += str(UNITS[toks[k]])
                k += 1
            value += float("0." + frac)
            claim, j = True, k
            if toks[j:j + 1] and toks[j] in BIG:  # "two point five billion"
                value *= BIG[toks[j]]
                j += 1
        if toks[j:j + 1] in (["percent"], ["percentage"]):
            claim, j = True, j + 1
        elif toks[j:j + 2] == ["per", "cent"]:
            claim, j = True, j + 2
        if claim:
            out.append((value, " ".join(toks[start:j])))
        i = max(j, i + 1)
    return out


def published_values(text):
    """Every number the published copy states, as a value: digits with their scale word, and numbers written as words."""
    vals = set()
    for m in DIGITS.finditer(text or ""):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        vals.add(v)
        if m.group(2):
            vals.add(v * DIGIT_SCALE[m.group(2).lower()])
    vals |= {v for v, _ in spoken_numbers(text)}
    return vals


def number_gaps(script, published, extra=""):
    """The numbers the script says that the published copy (or today's conversions of its sums) does not state, allowing
    the rounding of speech. Empty when every claim-sized number is stated."""
    known = published_values(published) | published_values(extra)
    gaps = []
    for value, phrase in spoken_numbers(script):
        if not any(abs(value - k) <= max(TOLERANCE * abs(k), 0.05) for k in known):
            gaps.append(phrase)
    return gaps


def gate(script, facts, published, extra=""):
    """The problems with a script, empty when it may be voiced. published: every word the script may stand on.
    extra: text whose numbers the script may use too (the conversions of the published sums)."""
    problems = []
    low = " " + _norm(script) + " "
    words = script.split()
    if not MIN_WORDS <= len(words) <= MAX_WORDS:
        problems.append(f"{len(words)} words, not {MIN_WORDS}-{MAX_WORDS}")
    for s in sentences(script):
        if len(s.split()) > MAX_SENTENCE:
            problems.append(f"long sentence ({len(s.split())} words): {s[:60]}")
    hits = sorted({b for b in BANNED if b in low})
    if hits:
        problems.append("banned: " + ", ".join(hits))
    if "?" in script:
        problems.append("a question")
    if re.search(r"[—–]|\s-\s", script):
        problems.append("a dash")
    if CONTRAST.search(script):
        problems.append("not X but Y")
    sents = sentences(script)
    for i, sent in enumerate(sents[1:], start=1):
        w = content_words(sent)
        for prev in sents[:i]:
            if w and len(w & content_words(prev)) / len(w) >= REPEAT:
                problems.append(f"restates an earlier sentence: {sent[:60]}")
                break
    for sent in sents:
        if re.match(r"(?i)(?:it'?s |this is )?(?:according to|reported by|the figures? (?:came|come)|that'?s (?:from|according))\b", sent) \
                or re.fullmatch(r"(?i)[A-Z][\w' ]{0,40} (?:says|said|reported|reports)(?: (?:it|this|so|that))?\.", sent):
            problems.append(f"a source credited in a sentence of its own: {sent[:60]}")
    for m in re.finditer(r"(?i)(?:^|(?<=[\s,]))(\w+ )?point (?:one|two|three|four|five|six|seven|eight|nine)\b", script):
        if not m.group(1) or m.group(1).strip().lower() not in NUMBER_WORDS:
            problems.append(f"say 'zero point': {m.group(0).strip()!r}")
    m = WRITTEN_NUMBER.search(script)
    if m:
        problems.append(f"number not said as words: {m.group(0)!r}")
    pub = _norm(published)
    for name in sorted(names(script)):
        if name.lower() not in pub:
            problems.append(f"name not in the published copy: {name}")
    for phrase in number_gaps(script, published, extra):
        problems.append(f"number not in the published copy: {phrase!r}")
    if not facts:
        problems.append("no facts quoted")
    for f in facts:
        if _norm(f) not in pub:
            problems.append(f"fact not quoted from the published copy: {f[:60]}")
    return problems


def published_text(post):
    return " ".join([post["headlines"][0], post.get("dek", ""), post.get("body", "") or "", " ".join(post.get("sources") or [])])


CURRENCY = {"yen": "JPY", "¥": "JPY", "pound": "GBP", "£": "GBP", "yuan": "CNY", "renminbi": "CNY", "euro": "EUR", "€": "EUR"}
SCALE = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12, "bn": 1e9, "m": 1e6}


def conversions(text, m=None):
    """Lines "<sum as written> = about <N> billion dollars" for sums in a currency today's ECB reference rates cover
    (yen, pounds, yuan, euros), so the script can give the dollar amount without a guess. Other currencies (won,
    rupees...) get none: the ECB file the desk keeps does not carry them."""
    if m is None:
        from . import markets as M
        m = M.load(live=False) or {}
    rates = (m.get("fx") or {}).get("rates") or {}
    usd = rates.get("USD")
    if not usd:
        return ""
    out = []
    pat = r"(?:([€£¥])\s?([\d.,]+)\s?(thousand|million|billion|trillion|bn|m)?)|(?:([\d.,]+)\s?(thousand|million|billion|trillion)?\s?(yen|pounds?|yuan|renminbi|euros?))"
    for g in re.finditer(pat, text, re.I):
        sym, n1, sc1, n2, sc2, word = g.groups()
        try:
            n = float((n1 or n2).replace(",", ""))
        except ValueError:
            continue
        code = CURRENCY.get(sym or (word or "").lower().rstrip("s"))
        if not code:
            continue
        eur = n * SCALE.get((sc1 or sc2 or "").lower(), 1) / (rates.get(code, 1.0) if code != "EUR" else 1.0)
        dollars = eur * usd
        unit, div = ("billion", 1e9) if dollars >= 1e9 else ("million", 1e6) if dollars >= 1e6 else ("", 1)
        out.append(f"{g.group(0).strip()} = about {dollars / div:,.1f} {unit} dollars".replace("  ", " "))
    return "\n".join(dict.fromkeys(out))


def write(post, ask=None, tries=3):
    """(script, problems). The model writes, the gate checks; up to two retries with the gate's findings. problems empty: voice it."""
    if ask is None:
        from .copy import ask_text as ask
    prompt = PROMPT.format(headline=post["headlines"][0], dek=post.get("dek", ""), body=post.get("body", "") or "",
                           sources=", ".join(post.get("sources") or []), conversions=conversions(published_text(post)) or "none")
    script, problems = "", ["not written"]
    for _ in range(tries):
        raw = ask(prompt)
        m = re.search(r"\{.*\}", raw or "", re.S)
        try:
            got = json.loads(m.group(0)) if m else {}
        except ValueError:
            got = {}
        script, facts = (got.get("script") or "").strip(), got.get("facts") or []
        problems = gate(script, facts, published_text(post), extra=conversions(published_text(post)))
        if not problems:
            return script, []
        prompt += "\nYour last draft failed these checks; write it again:\n- " + "\n- ".join(problems) + "\n"
    return script, problems
