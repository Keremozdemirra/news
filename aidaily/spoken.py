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

MIN_WORDS, MAX_WORDS, MAX_SENTENCE = 55, 85, 20

PROMPT = """You write the voice-over for a 30-second news video. Tell the story the way a calm person tells a friend
what just happened, out loud. Use ONLY the facts in PUBLISHED below; add nothing, guess nothing.

Rules:
- Start with what happened, in the first sentence. No lead-in, no scene-setting.
- Short sentences. One idea each. Plain words. Contractions are good (it's, they've, didn't).
- Say numbers the way people say them: "about two billion dollars", "nearly three percent", "point two percent". No symbols, no digits except a year. Say each number once.
- One or two facts, then what it means for someone in plain terms, only if PUBLISHED says it. Otherwise end on the most concrete fact.
- Each sentence adds something new; never restate an earlier sentence.
- 60 to 80 words in total.
- Never: questions, lists of three, "not just X but Y", dashes, a closing moral or lesson, "in a significant development",
  "this comes as", "here's what you need to know", "let's dive in", "it remains to be seen", "only time will tell".
- Name the newsroom once if it helps ("Reuters says..."), never as a sign-off.

Return JSON only: {{"script": "...", "facts": ["exact quote from PUBLISHED that each fact rests on", ...]}}

PUBLISHED:
Headline: {headline}
Summary: {dek}
More: {body}
Reported by: {sources}
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
         "this is a reminder", "a reminder that", "this shows", "in other words", "make sure to", "don't forget"]
BANNED = HUMANIZER + SLOPCHECK + STOCK
CONTRAST = re.compile(r"\bnot (?:just|only|merely)\b[^.]{1,60}\bbut\b|\bit'?s not [^.]{1,40}\. it'?s\b", re.I)
WRITTEN_NUMBER = re.compile(r"[$€£¥₩%]|\b\d+[.,]\d+\b|\b\d+\s?(?:bn|m|k)\b|\b(?!(?:19|20)\d\d\b)\d{2,}\b", re.I)


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


def gate(script, facts, published):
    """The problems with a script, empty when it may be voiced. published: every word the script may stand on."""
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
    m = WRITTEN_NUMBER.search(script)
    if m:
        problems.append(f"number not said as words: {m.group(0)!r}")
    pub = _norm(published)
    for name in sorted(names(script)):
        if name.lower() not in pub:
            problems.append(f"name not in the published copy: {name}")
    if not facts:
        problems.append("no facts quoted")
    for f in facts:
        if _norm(f) not in pub:
            problems.append(f"fact not quoted from the published copy: {f[:60]}")
    return problems


def published_text(post):
    return " ".join([post["headlines"][0], post.get("dek", ""), post.get("body", "") or "", " ".join(post.get("sources") or [])])


def write(post, ask=None, tries=2):
    """(script, problems). The model writes, the gate checks; one retry with the gate's findings. problems empty: voice it."""
    if ask is None:
        from .copy import ask_text as ask
    prompt = PROMPT.format(headline=post["headlines"][0], dek=post.get("dek", ""), body=post.get("body", "") or "",
                           sources=", ".join(post.get("sources") or []))
    script, problems = "", ["not written"]
    for _ in range(tries):
        raw = ask(prompt)
        m = re.search(r"\{.*\}", raw or "", re.S)
        try:
            got = json.loads(m.group(0)) if m else {}
        except ValueError:
            got = {}
        script, facts = (got.get("script") or "").strip(), got.get("facts") or []
        problems = gate(script, facts, published_text(post))
        if not problems:
            return script, []
        prompt += "\nYour last draft failed these checks; write it again:\n- " + "\n- ".join(problems) + "\n"
    return script, problems
