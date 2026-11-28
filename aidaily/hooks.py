"""Cover hooks for Reels and Shorts: a huge 2-4 word line taken from the headline ("HACKED", "29 SEATS"), and one
plain sentence under it. Samples only until Kerem approves (2026-11-28); nothing in the publish path calls this.

The model proposes; gate() decides. A hook passes only when:
  - it is 2 to 4 words, letters, digits and an apostrophe only (no "!" or "?");
  - every word, or its stem, is in the published headline or dek, and every number in it is there as written,
    so the hook can only restate the story, never add to it;
  - no hype word (SHOCKING, INSANE, EXPOSED, SECRET, YOU...);
  - a second read by the model finds it faithful: read alone, it suggests nothing the headline does not say.
The line under it is at most 14 words and passes the spoken script's checks (spoken.BANNED, no question, every
name in the published copy).
"""
import json
import re

from . import spoken

HYPE = {"shocking", "insane", "exposed", "secret", "secrets", "unbelievable", "you", "your", "must", "huge", "massive",
        "chaos", "destroyed", "slams", "epic", "crazy", "breaking", "omg", "wow", "nobody", "everyone", "truth"}

PROMPT = """You write the cover of a short news video. Use ONLY the words and facts in PUBLISHED.

1. HOOK: 2 to 4 words, the core of what happened, taken from the headline: a verb, a number with its noun, or a
   name with its verb ("HACKED", "29 SEATS", "OUTAGE HITS ALLSTATE"). Every word must appear in the headline or
   the summary. True and plain: no hype, no question, no exclamation mark.
2. LINE: one plain sentence of at most 14 words that adds the key fact or who it hits, from PUBLISHED. No question.

Return JSON only: {{"hook": "...", "line": "..."}}

PUBLISHED:
Headline: {headline}
Summary: {dek}
"""


def _stem(w):
    return re.sub(r"(ing|ed|es|s)$", "", w.lower())


def gate(hook, line, published):
    problems = []
    words = hook.split()
    if not 2 <= len(words) <= 4:
        problems.append(f"hook has {len(words)} words, not 2-4")
    if re.search(r"[^A-Za-z0-9' %.,$€£-]", hook) or re.search(r"[!?]", hook + line):
        problems.append("hook or line has a symbol, a question or an exclamation")
    pub = published.lower()
    pub_stems = {_stem(w) for w in re.findall(r"[a-z0-9'%$.,-]+", pub)}
    for w in words:
        lw = w.lower().strip(".,")
        if lw in HYPE:
            problems.append(f"hype word: {w}")
        elif re.search(r"\d", lw):
            if lw not in pub:
                problems.append(f"number not in the published copy: {w}")
        elif _stem(lw) not in pub_stems and lw not in pub:
            problems.append(f"word not in the published copy: {w}")
    if len(line.split()) > 14:
        problems.append(f"line has {len(line.split())} words")
    low = " " + spoken._norm(line) + " "
    hits = [b for b in spoken.BANNED if b in low]
    if hits:
        problems.append("banned in line: " + ", ".join(hits))
    for name in spoken.names(line):
        if name.lower() not in pub:
            problems.append(f"name not in the published copy: {name}")
    return problems


FAITHFUL = """A news cover shows only this HOOK in huge letters. Read it alone, as a scroller would.
HEADLINE: {headline}
HOOK: {hook}
Does the HOOK, read without the headline, suggest anything the headline does not say (a different claim, a
stronger one, a comparison or an accusation the headline does not make)? Answer with one word: FAITHFUL or MISLEADING."""


def faithful(hook, headline, ask):
    """A second read by the model: a hook can use only the headline's words and still mislead ("ZELENSKYY COMPARES
    TRUMP" for a headline about comparing Trump calling Putin a friend to befriending Hitler)."""
    verdict = (ask(FAITHFUL.format(headline=headline, hook=hook)) or "").strip().upper()
    return verdict.startswith("FAITHFUL")


def write(post, ask, tries=3):
    """(hook, line, problems): the model writes, the gate checks, up to two retries with its findings."""
    published = f"{post['headlines'][0]} {post.get('dek', '')}"
    prompt = PROMPT.format(headline=post["headlines"][0], dek=post.get("dek", ""))
    hook, line, problems = "", "", ["not written"]
    for _ in range(tries):
        m = re.search(r"\{.*\}", ask(prompt) or "", re.S)
        try:
            got = json.loads(m.group(0)) if m else {}
        except ValueError:
            got = {}
        hook, line = (got.get("hook") or "").strip().upper(), (got.get("line") or "").strip()
        problems = gate(hook, line, published)
        if not problems and not faithful(hook, post["headlines"][0], ask):
            problems = ["the hook, read alone, suggests something the headline does not say: take another angle, "
                        "the full act in two to four words (who did what), or the event itself, never a verb cut from its "
                        "object"]
        if not problems:
            return hook, line, []
        prompt += "\nYour last answer failed these checks; write it again:\n- " + "\n- ".join(problems) + "\n"
    return hook, line, problems
