"""Write the day's post copy with Claude, then check it against the sources.

The model gets only the fetched titles and summaries and no tools: it cannot
browse, post or read files. Every number it writes must appear in the source
text, or the story falls back to the source headline. A wrong figure in a
news post is the one mistake this brand cannot afford.
"""
import json
import os
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
MODEL = "sonnet"
MAX_HEADLINE = 80
DASHES = str.maketrans({"—": ",", "–": "-"})

PROMPT = """You write copy for a news brand that posts every story a consultant, manager or business student
needs to know: business, markets, the economy, politics and elections, world events, technology and AI, and
the culture moments everyone at work talks about (a record-breaking launch, a viral phenomenon).
For each story below, return one JSON object. Use ONLY facts present in that story's title and summary.
Never add a number, name or claim that is not in them. Report; do not interpret. No sentence about what the
news means, why it matters, what to watch, or what it signals: the reader decides that. No closing line
that sounds quotable. American English. No em or en dashes. No hype words. No "not X but Y" constructions.

Fields:
- id: copy the id
- relevant: false if a consultant or manager would not need it: crime and court cases about private
  people, sports results, celebrity gossip, local news, weather, lifestyle, recipes, obituaries, opinion
  and advice pieces, product deals and reviews; true otherwise
- topic: one of AI, Tech, Business, Markets, Economy, Politics, World, Culture. Business: companies, deals,
  people moves, a company's marketing or products. Markets: stocks, bonds, ratings, funds. Economy: data, central
  banks, trade. Politics: governments, elections, regulation, courts. World: international events. Tech and AI:
  what the technology does. Culture: entertainment, games, media, sport, art. A company story is never Culture
- headline: max 80 characters, present tense, names the actor and the action, the key figure if any
- dek: one sentence, max 140 characters, the most useful extra fact
- company: the main company the story is about, as the company names itself ("" if none)
- company_domain: that company's website domain if you are certain of it, like "redqueen.bio" ("" if unsure;
  it is checked against the site's own title before use)
- backer: a named investor or parent company in the story, like "OpenAI" ("" if none)
- person: the one person the story is centrally about, full name ("" if none; never a person only quoted)
- orgs: up to 3 companies or institutions the story names, main one first, each spelled as in the source
  ([] if none)
- image_query: 2 to 4 words to search Wikimedia Commons for a photo of a physical thing the story is
  about: a named product, a named building, or a plain object or place such as "data center",
  "semiconductor wafer", "courthouse", "satellite". Never a person, a crowd, an event, a meeting or a
  press conference (the story's own person goes in "person"), never a logo, never an abstract idea
- figure: the single key figure as written in the source, like "$36M" or "40%" ("" if none)
- x_post: max 240 characters, headline plus one fact, no hashtags, no link
- linkedin_post: 2 to 3 short sentences: what happened, then the most useful further facts from the source;
  end with the line "Source: <outlet>"
- fits_category: false if the story does not match its slot, e.g. a profile or retrospective in a funding
  slot, an opinion piece in a breaking slot; true otherwise{extra_fields}

Return a JSON array only, no prose.

STORIES:
{stories}"""

# Added to the prompt only while desk.json growth.so_what is true. It overrides the "do not interpret" rule above
# for this one field, which is why the field text repeats the limits instead of leaning on them.
SO_WHAT_FIELD = """
- so_what: the one field where you do say what the story means, overriding the rule above. ONE plain sentence,
  max 22 words, for a manager, investor or business student: the practical consequence that follows from facts
  in the source, stated as fact. Do not restate the headline or dek. Use only words and facts from the source plus
  plain connecting words. No advice ("should", "must"), no prediction ("could", "might", "likely", "will"), no
  question, no new number or name. Example for "Bank X cuts 3,000 jobs after profit falls": "The bank is lowering
  its costs after weaker profit." Return "" only when the source gives nothing to build on"""


def switch(name):
    """A growth switch from desk.json; read on each call so a test or a config edit takes effect at once."""
    try:
        return bool(json.loads((HERE / "desk.json").read_text()).get("growth", {}).get(name))
    except (OSError, ValueError):
        return False


NUM = re.compile(r"\d+(?:[.,]\d+)?")
WORD = re.compile(r"[a-z][a-z'’]+")
FILLER = set("that this with from their they have been will would could about into over after than then "
             "also more most such which what when where while there these those its it's the and for are "
             "was were has had not but one two all any each other some said says according reportedly report "
             "source".split())
CULTURE = re.compile(r"\b(film|films|movie|movies|box office|game|games|gaming|console|music|album|song|singer|"
                     r"concert|tour|sport|sports|football|soccer|nba|nfl|olympic\w*|series|streaming|netflix|"
                     r"festival|art|artist|museum|celebrity|actor|actress|oscar\w*|grammy|book|novel|tv|show)\b", re.I)
SO_WHAT_MAX_WORDS = 24  # the prompt asks for 22; two words of slack for a hyphenated or possessive count
SO_WHAT_OVERLAP = 0.6   # share of the sentence's content words already in the headline or dek
SO_WHAT_ANCHOR = 0.3    # share that must come from the source, so a consequence still hangs on the report
ADVICE = re.compile(r"\b(should|must|ought|need to|needs to|could|might|may|likely|unlikely|probably|perhaps|"
                    r"expected to|bullish|bearish|buy|sell|recommend\w*|advis\w*)\b", re.I)
NOT_BUT = re.compile(r"\bnot\b[^.;]{0,50}\bbut\b|\bnot just\b|\bisn['’]t\b[^.;]{0,50}\bit['’]s\b", re.I)
HYPE = re.compile(r"\b(huge|massive|incredible|stunning|shocking|explosive|game[- ]changing|groundbreaking|"
                  r"seismic|earth-shattering|unprecedented)\b", re.I)
GROUNDED = 0.6  # share of a sentence's content words that must come from the source


def _stems(text):
    return {w[:5] for w in WORD.findall((text or "").lower()) if len(w) > 3 and w not in FILLER}


def ungrounded(sentence, source_text):
    """True when most of a sentence's content words are absent from the source: commentary, not report."""
    words = _stems(sentence)
    if len(words) < 3:
        return False
    return len(words & _stems(source_text)) / len(words) < GROUNDED


def _numbers(text):
    return {n.replace(",", "") for n in NUM.findall(text or "")}


def verify(story, copy):
    """Numbers in the copy must exist in the source text. Returns a list of problems."""
    src = _numbers(story["title"] + " " + story.get("summary", ""))
    problems = []
    for field in ("headline", "dek", "figure", "x_post", "linkedin_post"):
        extra = _numbers(copy.get(field, "")) - src
        if extra:
            problems.append(f"{field}: numbers not in source {sorted(extra)}")
    if len(copy.get("headline", "")) > MAX_HEADLINE:
        problems.append("headline too long")
    text = story["title"] + " " + story.get("summary", "")
    for field in ("dek", "x_post", "linkedin_post"):
        for sent in re.split(r"(?<=[.!?])\s+|\n+", copy.get(field, "")):
            if sent and not sent.startswith("Source:") and ungrounded(sent, text):
                problems.append(f"{field}: sentence not grounded in source: {sent[:80]}")
    if copy.get("fits_category") is False:
        problems.append("does not fit its slot")
    if copy.get("relevant") is False:
        problems.append("not relevant to the audience")
    return problems


def check_so_what(story, copy, text):
    """Problems with the "what it means" sentence; empty means it may be shown. A bad sentence costs only
    itself: the story keeps its checked copy and the line is simply absent."""
    from . import desk  # the house slop list lives in desk; imported here because desk imports this module
    if not isinstance(text, str) or not text.strip():
        return ["empty"]
    problems = []
    if len(text.split()) > SO_WHAT_MAX_WORDS:
        problems.append("too long")
    if "?" in text or "\n" in text or len(re.findall(r"[.!]\s+\S", text)) > 0:
        problems.append("not one plain sentence")
    src_text = story["title"] + " " + story.get("summary", "")
    extra = _numbers(text) - _numbers(src_text)
    if extra:
        problems.append(f"numbers not in source {sorted(extra)}")
    low_src = src_text.lower()
    # a capitalised word that is not the first word is a name; every name must come from the source
    for w in re.findall(r"(?<![.!?]\s)(?<!^)\b[A-Z][A-Za-z0-9&'’-]+", text):
        if re.sub(r"['’]s$", "", w.lower()) not in low_src:
            problems.append(f"name not in source: {w}")
            break
    seen = _stems(copy.get("headline", "") + " " + copy.get("dek", ""))
    mine = _stems(text)
    if mine and len(mine & seen) / len(mine) >= SO_WHAT_OVERLAP:
        problems.append("repeats the headline or dek")
    if mine and len(mine & _stems(src_text)) / len(mine) < SO_WHAT_ANCHOR:
        problems.append("not tied to the source text")
    for rx, why in ((desk.SLOP, "stock phrase"), (ADVICE, "advice or speculation"), (NOT_BUT, "not X but Y"), (HYPE, "hype")):
        m = rx.search(text)
        if m:
            problems.append(f"{why}: {m.group(0)!r}")
    return problems


# The model reads untrusted text, so the CLI gets only what it needs to run: never the Instagram or GitHub tokens
# that sit in the same job's environment.
CLI_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TERM", "CLAUDE_CODE_OAUTH_TOKEN",
           "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "SSL_CERT_FILE", "NODE_EXTRA_CA_CERTS")


def cli_env(environ=None):
    environ = os.environ if environ is None else environ
    return {k: v for k, v in environ.items() if k in CLI_ENV}


def ask_text(prompt, runner=subprocess.run):
    # no tools, no MCP, no user settings or hooks: the model reads untrusted text and may only answer
    r = runner(["claude", "-p", "--model", MODEL, "--tools", "", "--restricted", "--strict-mcp-config",
                "--no-session-persistence", "--output-format", "json"],
               input=prompt, capture_output=True, text=True, timeout=600, env=cli_env())
    if r.returncode != 0:
        raise RuntimeError(f"claude exited {r.returncode}: {r.stderr[-400:]}")
    return json.loads(r.stdout)["result"]


def ask_claude(prompt, runner=subprocess.run):
    text = ask_text(prompt, runner)
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        raise RuntimeError("no JSON array in reply")
    return json.loads(m.group(0))


def prompt(block):
    return PROMPT.format(stories=block, extra_fields=SO_WHAT_FIELD if switch("so_what") else "")


def write(stories, runner=subprocess.run):
    """Adds headline, dek, company, figure, x_post, linkedin_post to each story in place.

    Returns a list of (title, problems) for stories whose copy was rejected.
    """
    if not stories:
        return []
    for i, s in enumerate(stories):
        s["id"] = i
    block = "\n\n".join(f"id: {i}\noutlet: {s['source']}\ntitle: {s['title']}\nsummary: {s.get('summary', '')[:500]}"
                        for i, s in enumerate(stories))
    return apply(stories, ask_claude(prompt(block), runner))


def request(stories):
    """The prompt a Claude session answers when no headless call is available."""
    for i, s in enumerate(stories):
        s["id"] = i
    block = "\n\n".join(f"id: {i}\noutlet: {s['source']}\ntitle: {s['title']}\nsummary: {s.get('summary', '')[:500]}"
                        for i, s in enumerate(stories))
    return prompt(block)


def apply(stories, reply_rows):
    """Merge the model's rows into the stories; numbers not in the source send a story back to its headline."""
    # the model sometimes quotes the id ("0"); a string id must still match its story
    rows = {int(r["id"]) if str(r.get("id", "")).isdigit() else r.get("id"): r for r in reply_rows}
    rejected = []
    for i, s in enumerate(stories):
        c = {k: (v.translate(DASHES) if isinstance(v, str) else v) for k, v in rows.get(i, {}).items()}
        problems = verify(s, c) if c else ["no copy returned"]
        if problems:
            rejected.append((s["title"], problems))
            s.update(headline=s["title"][:MAX_HEADLINE], dek="", x_post=s["title"],
                     linkedin_post=f"{s['title']}\n\nSource: {s['source']}", copy_status="fallback")
        else:
            s.update({k: c.get(k, "") for k in ("headline", "dek", "company", "company_domain", "backer", "person",
                                                 "figure", "x_post", "linkedin_post", "image_query", "topic")},
                     copy_status="ok")
            # an unchecked sentence is never shown: any problem leaves the field empty and the story as it was
            s["so_what"] = ""
            if switch("so_what"):
                sw = (c.get("so_what") or "").strip()
                if sw and not check_so_what(s, c, sw):
                    s["so_what"] = sw
            # "Culture" only when the story is about culture: a company's viral marketing is a business story
            if s.get("topic") == "Culture" and not CULTURE.search(s["title"] + " " + s.get("summary", "")):
                s["topic"] = "Business"
            # a logo for an organisation the source never names would put a company on a story it is not in
            src = (s["title"] + " " + s.get("summary", "")).lower()
            orgs = c.get("orgs") if isinstance(c.get("orgs"), list) else []
            s["orgs"] = [o for o in orgs if isinstance(o, str) and o.strip() and o.lower() in src][:3]
            # the same holds for a face: only a person the source names may be pictured
            if s.get("person") and s["person"].split()[-1].lower() not in src:
                s["person"] = ""
            # and for every logo: a company or backer the source does not name gets no logo on the card. An
            # unchecked "backer" once put the BCG logo on an FCC story.
            for field in ("company", "backer"):
                if s.get(field) and s[field].lower() not in src:
                    s[field] = ""
            # a big figure the reader cannot find in the headline or dek reads as the story's number when it is not
            seen = s["headline"] + " " + s["dek"]
            fig = s["figure"]
            if fig and not ((_numbers(fig) & _numbers(seen)) if _numbers(fig) else fig.lower() in seen.lower()):
                s["figure"] = ""
    return rejected
