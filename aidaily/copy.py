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
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
MODEL = "sonnet"
MAX_HEADLINE = 80
DASHES = str.maketrans({"—": ",", "–": "-"})

AUDIENCE = """You write copy for a news brand that posts every story a consultant, manager or business student
needs to know: business, markets, the economy, politics and elections, world events, technology and AI, and
the culture moments everyone at work talks about (a record-breaking launch, a viral phenomenon)."""
SPORT_AUDIENCE = """You write copy for the sport section of a news site. It covers football (Premier League,
Champions League, Bundesliga, La Liga, Serie A, World Cup qualifiers, transfers) and the main global events:
Formula 1, the NBA, the NFL, the tennis majors, the Olympics, cricket, the golf majors and boxing title fights.
Readers want the result, the decision or the move, stated plainly."""
RELEVANT = """false if a consultant or manager would not need it: crime and court cases about private
  people, sports results, celebrity gossip, local news, weather, lifestyle, recipes, obituaries, opinion
  and advice pieces, personal-finance columns, explainers, product deals and reviews, a brand's marketing
  stunt or social-media post; true otherwise"""
SPORT_RELEVANT = """false for betting tips and odds, gossip, fantasy-league advice, opinion and
  predictions, match previews with no news in them, podcasts and quizzes, and reports on minor or local
  competitions; true for results, signings and transfers, injuries, managerial changes, rulings, records and
  the build-up facts of a major event"""
TOPIC_RULE = """one of AI, Tech, Business, Markets, Economy, Politics, World, Culture. Business: companies, deals,
  people moves, a company's marketing or products. Markets: stocks, bonds, ratings, funds. Economy: data, central
  banks, trade. Politics: governments, elections, regulation, courts. World: international events. Tech and AI:
  what the technology does. Culture: entertainment, games, media, sport, art. A company story is never Culture"""
SPORT_TOPIC_RULE = 'always "Sport"'
IMAGE_RULE = """2 to 4 words to search Wikimedia Commons for a photo of a physical thing the story is
  about: a named product, a named building, or a plain object or place such as "data center",
  "semiconductor wafer", "courthouse", "satellite". Never a person, a crowd, an event, a meeting or a
  press conference (the story's own person goes in "person"), never a logo, never an abstract idea"""
SPORT_IMAGE = """the stadium, arena, circuit or course the story is set at, or the home ground of the club it is about,
  by its own name as Wikimedia Commons titles it, like "Stadium of Light" or "Silverstone Circuit" ("" when
  unsure). Never a person, a crowd, a match, a trophy or a logo"""
SPORT_COMPANY = """the club, team, federation or event the story is about, as it names itself, like
  "Arsenal" or "Wimbledon" ("" if none). It is used to find a photo; no logo is shown"""

PROMPT = """{audience}
For each story below, return one JSON object. Use ONLY facts present in that story's title and summary and in
the reports from other newsrooms listed under it ("also reported").
Never add a number, name or claim that is not in them. Report; do not interpret. No sentence about what the
news means, why it matters, what to watch, or what it signals: the reader decides that. No closing line
that sounds quotable. American English. No em or en dashes. No hype words. No "not X but Y" constructions.

Fields:
- id: copy the id
- relevant: {relevant}
- same_event: the id of an EARLIER story in this list that reports the same event, or the R number of a
  RECENT headline below that reports it with no new development ("R4"); "" when it is a new event. The same
  pledge, deal, ruling, match, market session or announcement told again with more detail, a new figure from
  the same announcement or another angle (the fans, the reaction, a profile) is the same event; only a later
  decision, result or official step is new
- topic: {topic_rule}
- headline: max 80 characters, present tense, names the actor and the action, the key figure if any. Plain
  words: "more than £400m", never "£400m+"; no question; no quote marks around a single word. Name the
  country when a senate, parliament, court, central bank or election is not American ("Argentina's Senate")
- dek: one sentence, max 140 characters, the most useful extra fact (not a restatement of the headline); it
  sums up the story the headline names, so it never leads with a company or person the headline leaves out
- company: {company_rule}
- company_domain: that company's website domain if you are certain of it, like "redqueen.bio" ("" if unsure;
  it is checked against the site's own title before use)
- backer: a named investor or parent company in the story, like "OpenAI" ("" if none)
- person: the one person the story is centrally about, full name ("" if none; never a person only quoted)
- person_role: who that person is, 3 to 8 words: nationality, job, organisation, like "British economist,
  Bank of England governor" ("" if no person). Only used to find the right photo among people who share
  the name; never printed, so it may use what you know beyond the source
- orgs: up to 3 companies or institutions the story names, main one first, each spelled as in the source
  ([] if none)
- image_query: {image_rule}
- figure: the single key figure as written in the source, digits only, like "$36M", "40%" or "77,000" ("" if
  none, if it is a word like "a quarter", or if the source qualifies it with "more than", "up to", "about")
- x_post: max 240 characters, headline plus one fact, no hashtags, no link
- linkedin_post: the report, printed under the headline and the dek: 2 to 4 short sentences, each a fact that
  is in neither of them (a sentence that says the headline or the dek again is deleted). Draw on every report
  listed: who, what, how much, when, where, what was said, what happens next as the source states it. The first
  sentence names its subject: never open with "It", "This", "They", "These", "Together" or "also". Each sentence
  complete and grammatical, never a source phrase pasted into another sentence. If the sources hold no fact beyond
  the headline and dek, write only the Source line. End with the line "Source: <outlet>"
- fits_category: false if the story does not match its slot, e.g. a profile or retrospective in a funding
  slot, an opinion piece in a breaking slot; true otherwise{extra_fields}

Return a JSON array only, no prose.

STORIES:
{stories}{recent}"""

# Added to the prompt only while desk.json growth.so_what is true. It overrides the "do not interpret" rule above
# for this one field, which is why the field text repeats the limits instead of leaning on them.
SO_WHAT_FIELD = """
- so_what: the one field where you do say what the story means, overriding the rule above. Most stories
  support one. ONE plain sentence, max 22 words, naming what the story changes for a specific group: customers,
  passengers, creditors, lenders, competitors, suppliers, investors, shareholders, employees, a market, a
  regulator, a country. The consequence must follow directly from a fact stated in the source, and you state it
  as fact: no advice ("should", "must"), no prediction ("could", "might", "likely", "will"), no question, no
  new number or name. It must say something the headline, dek and body do not already say. Return "" only when
  the source gives no consequence beyond what those already say.
  Good, for "Bank X cuts 3,000 jobs after profit falls": "Employees at the bank lose positions while it
  lowers costs."
  Good, for "Takeover bid would delist Company Z, the source says it leaves the exchange with fewer large
  companies": "The exchange loses one of its large listed companies."
  Bad: "The airline has stopped flying and faces bankruptcy." (restates the story, names no group)
  Bad: "Investors should avoid airline stocks." (advice, not in the source)"""


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
             "source them him his her she who whom being still just very among including made make "
             "while whose them also only even much many".split())
CULTURE = re.compile(r"\b(film|films|movie|movies|box office|game|games|gaming|console|music|album|song|singer|"
                     r"concert|tour|sport|sports|football|soccer|nba|nfl|olympic\w*|series|streaming|netflix|"
                     r"festival|art|artist|museum|celebrity|actor|actress|oscar\w*|grammy|book|novel|tv|show)\b", re.I)
SO_WHAT_MAX_WORDS = 24  # the prompt asks for 22; two words of slack for a hyphenated or possessive count
SO_WHAT_OVERLAP = 0.5   # share of the sentence's content words already in any single headline, dek, body or source sentence
SO_WHAT_UNION = 0.7     # the same, against all of them together
GROUP = re.compile(r"\b(customers?|passengers?|travell?ers?|consumers?|users?|buyers?|clients?|creditors?|lenders?|"
                   r"banks?|competitors?|rivals?|suppliers?|vendors?|investors?|shareholders?|savers?|borrowers?|"
                   r"employees?|workers?|staff|jobs?|managers?|regulators?|governments?|countries|markets?|"
                   r"companies|firms|businesses|airlines|carriers|households?|taxpayers?|voters?|drivers?|patients?|"
                   r"students?|farmers?|importers?|exporters?|retailers?|developers?|creators?|advertisers?)\b", re.I)
SO_WHAT_ANCHOR = 0.3    # share that must come from the source, so a consequence still hangs on the report
ADVICE = re.compile(r"\b(should|must|ought|need to|needs to|could|might|may|likely|unlikely|probably|perhaps|"
                    r"expected to|bullish|bearish|recommend\w*|advis\w*)\b", re.I)
NOT_BUT = re.compile(r"\bnot\b[^.;]{0,50}\bbut\b|\bnot just\b|\bisn['’]t\b[^.;]{0,50}\bit['’]s\b", re.I)
HYPE = re.compile(r"\b(huge|massive|incredible|stunning|shocking|explosive|game[- ]changing|groundbreaking|"
                  r"seismic|earth-shattering|unprecedented)\b", re.I)
GROUNDED = 0.6  # share of a sentence's content words that must come from the source


INFLECTION = re.compile(r"(ing|ed|es|s)$")


def _stem(w):
    """"cutting", "cuts" and "cut", "jobs" and "job" are one word to the grounding check."""
    st = INFLECTION.sub("", w) if len(w) > 4 else w
    st = re.sub(r"([b-df-hj-np-tv-z])\1$", r"\1", st)
    return st[:5]


def _fold(text):
    """"Hernández" and "Hernandez" are one name: accents go before words are compared."""
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()


def _stems(text, short=False):
    """Content-word stems. Words of four letters or more, as ever, so "wins cup tie" never makes two matches one
    event; `short` adds three-letter words, for the source side of the grounding check ("jobs" finds "job")."""
    out = set()
    for w in WORD.findall(_fold(text).lower()):
        if w in FILLER or len(w) < (3 if short else 4):
            continue
        st = _stem(w)
        if len(st) >= 3 and st not in FILLER:
            out.add(st)
    return out


def ungrounded(sentence, source_text):
    """True when most of a sentence's content words are absent from the source: commentary, not report."""
    words = _stems(sentence)
    if len(words) < 3:
        return False
    return len(words & _stems(source_text, short=True)) / len(words) < GROUNDED


def repeats(text, other, share=0.7):
    """Most of `text`'s content words are already in `other`: a dek that only restates its headline."""
    a = _stems(text)
    return len(a) >= 3 and len(a & _stems(other)) / len(a) >= share


def _numbers(text):
    return {n.replace(",", "") for n in NUM.findall(text or "")}


def verify(story, copy):
    """Numbers in the copy must exist in the source text. Returns a list of problems."""
    src = _numbers(source_text(story))
    problems = []
    for field in ("headline", "dek", "figure", "x_post", "linkedin_post"):
        # the "Source: France 24" line names the outlet; its digits are not a claim
        text = "\n".join(l for l in str(copy.get(field, "")).splitlines() if not l.startswith("Source:"))
        extra = _numbers(text) - src
        if extra:
            problems.append(f"{field}: numbers not in source {sorted(extra)}")
    if len(copy.get("headline", "")) > MAX_HEADLINE:
        problems.append("headline too long")
    if re.search(r"\d[\d,.]*\s?(?:[%kKmMbBtn]|bn|tn)?\+", copy.get("headline", "") + " " + copy.get("dek", "")):
        problems.append("a '+' after a number: write 'more than'")
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
    src_text = source_text(story)
    extra = _numbers(text) - _numbers(src_text)
    if extra:
        problems.append(f"numbers not in source {sorted(extra)}")
    low_src = src_text.lower()
    # a capitalised word that is not the first word is a name; every name must come from the source
    for w in re.findall(r"(?<![.!?]\s)(?<!^)\b[A-Z][A-Za-z0-9&'’-]+", text):
        if re.sub(r"['’]s$", "", w.lower()) not in low_src:
            problems.append(f"name not in source: {w}")
            break
    mine = _stems(text)
    # a restatement of any single sentence the reader has already had, or of all of them together
    units = [copy.get("headline", ""), copy.get("dek", "")]
    for field in (copy.get("linkedin_post", ""), story.get("summary", "")):
        units += [x for x in re.split(r"(?<=[.!?])\s+|\n+", field) if x.strip() and not x.startswith("Source:")]
    if mine:
        if any(len(mine & _stems(u)) / len(mine) >= SO_WHAT_OVERLAP for u in units if _stems(u)):
            problems.append("repeats the headline, dek or a sentence of the story")
        elif len(mine & _stems(" ".join(units))) / len(mine) >= SO_WHAT_UNION:
            problems.append("repeats the story")
    if not GROUP.search(text):
        problems.append("names no affected group")
    if mine and len(mine & _stems(src_text)) / len(mine) < SO_WHAT_ANCHOR:
        problems.append("not tied to the source text")
    for rx, why in ((desk.SLOP, "stock phrase"), (ADVICE, "advice or speculation"), (NOT_BUT, "not X but Y"), (HYPE, "hype")):
        m = rx.search(text)
        if m:
            problems.append(f"{why}: {m.group(0)!r}")
    return problems


# The model reads untrusted text, so the CLI gets only what it needs to run: never the Instagram or GitHub tokens
# that sit in the same job's environment.
CLI_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TERM", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN",
           "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "SSL_CERT_FILE", "NODE_EXTRA_CA_CERTS")


def cli_env(environ=None):
    environ = os.environ if environ is None else environ
    env = {k: v for k, v in environ.items() if k in CLI_ENV}
    # An automated service runs on an API key under the Commercial Terms; the subscription sign-in is for
    # ordinary individual use (code.claude.com/docs/en/legal-and-compliance). Once the key exists, the
    # subscription token is withheld so the CLI cannot fall back to it.
    if env.get("ANTHROPIC_API_KEY"):
        env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    return env


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


def prompt(block, lane="news", recent=()):
    sport = lane == "sport"
    tail = ("\n\nRECENT (already posted, for same_event only):\n" + "\n".join(f"R{i}: {h}" for i, h in enumerate(recent, 1))
            if recent else "")
    return PROMPT.format(stories=block, recent=tail, extra_fields=SO_WHAT_FIELD if switch("so_what") else "",
                         audience=SPORT_AUDIENCE if sport else AUDIENCE, relevant=SPORT_RELEVANT if sport else RELEVANT,
                         topic_rule=SPORT_TOPIC_RULE if sport else TOPIC_RULE,
                         image_rule=SPORT_IMAGE if sport else IMAGE_RULE,
                         company_rule=SPORT_COMPANY if sport else 'the main company the story is about, as the company names itself ("" if none)')


def source_text(story):
    """Every word the copy may stand on: the lead's title and summary and the other newsrooms' reports."""
    return " ".join([story.get("title", ""), story.get("summary", "")]
                    + [f"{r.get('title', '')} {r.get('summary', '')}" for r in story.get("reports") or []])


def block(stories):
    out = []
    for i, s in enumerate(stories):
        s["id"] = i
        also = "".join(f"\n- {r['outlet']}: {r['title']}. {r['summary'][:400]}" for r in s.get("reports") or [])
        out.append(f"id: {i}\noutlet: {s['source']}\ntitle: {s['title']}\nsummary: {s.get('summary', '')[:500]}"
                   + (f"\nalso reported:{also}" if also else ""))
    return "\n\n".join(out)


def write(stories, runner=subprocess.run):
    """Adds headline, dek, company, figure, x_post, linkedin_post to each story in place.

    Returns a list of (title, problems) for stories whose copy was rejected.
    """
    if not stories:
        return []
    return apply(stories, ask_claude(prompt(block(stories)), runner))


def request(stories, recent=(), lane="news"):
    """The prompt for the copy call. `recent` are headlines already posted, so the model can say a story repeats one."""
    return prompt(block(stories), lane, recent)


QUALIFIED = re.compile(r"\b(more than|over|up to|at least|about|around|nearly|almost|under|less than|roughly|"
                       r"as many as|as much as|some|close to)\s+$", re.I)


# a source phrase pasted into another sentence: "called an “underhanded” the push", "Justice described as a
# landmark ruling convicted". Such a sentence is cut like commentary.
MALFORMED = re.compile(r"\b(a|an|the)\s+[\"“‘'][^\"”’']{1,40}[\"”’']\s+(the|a|an)\b|"
                       r"\b[A-Z][a-z]+ described as an? [a-z]+ [a-z]+ [a-z]+ed\b", re.I)


def strip_ungrounded(story, copy):
    """Removes every dek, x_post and report sentence whose words are mostly not the source's: commentary is never
    shown, and the story keeps its checked facts. It used to cost the whole story, so one padded sentence
    ("The figure is a minimum") dropped SAP's 10,000 job cuts from the day. Returns the sentences removed."""
    # the outlet's own name is grounded: "the Buenos Aires Times reports" is attribution, not commentary
    text = " ".join([source_text(story), story.get("source", "")] + [r.get("outlet", "") for r in story.get("reports") or []])
    cut = []
    for field in ("dek", "x_post", "linkedin_post"):
        lines = str(copy.get(field) or "").split("\n")
        keep_lines = []
        for line in lines:
            if line.startswith("Source:") or not line.strip():
                keep_lines.append(line)
                continue
            kept = []
            for sent in sentences(line):
                (cut.append(sent) if ungrounded(sent, text) or MALFORMED.search(sent) else kept.append(sent))
            if kept:
                keep_lines.append(" ".join(kept))
        copy[field] = re.sub(r"\n{3,}", "\n\n", "\n".join(keep_lines)).strip()
    if not copy.get("x_post"):
        copy["x_post"] = copy.get("headline", "")
    return cut


def figure_ok(fig, seen):
    """A big figure must be a number (a word like "a quarter" set at 300 px says nothing), and the number the
    reader finds in the headline or dek must not carry a qualifier the card would drop ("more than £400m")."""
    if not fig or not re.search(r"\d", fig):
        return False
    m = re.search(re.escape(fig), seen, re.I)
    if not m:
        return True
    return not QUALIFIED.search(seen[:m.start()]) and not seen[m.end():m.end() + 1] == "+"


def sentences(text):
    return [x for x in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"“‘'])", text or "") if x.strip()]


def drop_restated_lead(post, headline):
    """The report under a headline starts with news: a first sentence that only restates the headline is cut
    when more follows ("SAP explores at least 10,000 job cuts." under "SAP explores at least 10,000 job cuts")."""
    lines = (post or "").split("\n")
    body = [l for l in lines if l.strip() and not l.startswith("Source:")]
    tail = [l for l in lines if l.startswith("Source:")]
    if not body:
        return post
    sents = sentences(" ".join(body))
    # never when what follows leans on the cut sentence: "One share would come from SpaceX and one from him
    # personally." lost its "Musk" that way
    while (len(sents) > 1 and repeats(sents[0], headline, share=0.6)
           and not re.search(r"\b(he|she|him|his|her|hers|they|them|their|it|its|this|that|these|those)\b", sents[1], re.I)):
        sents = sents[1:]
    return " ".join(sents) + ("\n\n" + "\n".join(tail) if tail else "")


LEANS = re.compile(r"^(?:It|Its|This|That|These|Those|They|Their|Them|He|She|His|Her|Together|Both|Such|The (?:two|three|"
                   r"move|deal|flaw|plan|decision|ruling|change|figure|step|measure|news))\b|\b(?:also|too|those|these|"
                   r"either|as well)\b")


def drop_repeats(post, deks, headline):
    """The report without sentences that restate the dek, and without a lone sentence that restates the headline."""
    lines = (post or "").split("\n")
    tail = [l for l in lines if l.startswith("Source:")]
    sents = sentences(" ".join(l for l in lines if l.strip() and not l.startswith("Source:")))
    def said(x, d):
        # a short sentence ("It equals $6 billion.") repeats the dek when its words and numbers are all there
        short = len(_stems(x)) < 3 and _stems(x) <= _stems(d, short=True) and _numbers(x) <= _numbers(d)
        return short or repeats(x, d) or repeats(d, x, share=0.8)
    # and a sentence whose words the headline and dek already hold between them ("The information comes from people
    # familiar with the situation." under a dek that says so)
    both = " ".join([headline] + [d for d in deks if d])
    kept, cut = [], False
    for x in sents:
        if any(d and said(x, d) for d in deks) or (deks and repeats(x, both, share=0.6)):
            cut = True
        # a sentence that leans on the one just cut, or that opens the report leaning on nothing, goes with it: "It
        # concerns the removal and blocking of political content." and "Markets are also tracking U.S. inventories."
        # stood alone on the site on 2026-11-27
        elif (cut or not kept) and LEANS.search(x):
            cut = True
        else:
            kept.append(x)
            cut = False
    if len(kept) == 1 and repeats(kept[0], headline, share=0.6):
        kept = []
    body = " ".join(kept)
    return (body + ("\n\n" + "\n".join(tail) if tail else "")).strip() if body else "\n".join(tail)


MIN_SENTENCES, MIN_WORDS = 2, 15


def body_of(post):
    return " ".join(l for l in (post or "").split("\n") if l.strip() and not l.startswith("Source:"))


def thin(s):
    """Why a checked story is too thin to post, or "": it needs a dek and a report of two sentences beyond it."""
    report = body_of(s.get("linkedin_post"))
    if not (s.get("dek") or "").strip():
        return "no dek"
    n, words = len(sentences(report)), len(report.split())
    if n < MIN_SENTENCES or words < MIN_WORDS:
        return f"report too thin ({n} sentences, {words} words beyond the dek)"
    return ""


def apply(stories, reply_rows):
    """Merge the model's rows into the stories; numbers not in the source send a story back to its headline."""
    # the model sometimes quotes the id ("0"); a string id must still match its story
    rows = {int(r["id"]) if str(r.get("id", "")).isdigit() else r.get("id"): r for r in reply_rows}
    rejected = []
    for i, s in enumerate(stories):
        c = {k: (v.translate(DASHES) if isinstance(v, str) else v) for k, v in rows.get(i, {}).items()}
        # the same event reported twice in one run, or again with nothing new after a post: one post only, and
        # the earlier story inherits the other newsrooms so its count stays true
        same = str(c.get("same_event") or "").strip()
        if same.isdigit() and int(same) < i and stories[int(same)].get("copy_status") == "ok":
            first = stories[int(same)]
            for key in ("newsrooms", "outlets", "links"):
                first[key] = list(dict.fromkeys(list(first.get(key) or []) + list(s.get(key) or [])))
            s["copy_status"] = "duplicate"
            rejected.append((s["title"], [f"same event as story {same}"]))
            continue
        if re.fullmatch(r"R\d+", same):
            s["copy_status"] = "repeat"
            rejected.append((s["title"], [f"repeats recent headline {same}"]))
            continue
        if c:
            strip_ungrounded(s, c)
            # hype the source used ("massive revision") is still hype in our voice: the intensifier goes, the fact stays
            for f in ("headline", "dek", "x_post", "linkedin_post"):
                if isinstance(c.get(f), str):
                    # spaces only: the report's blank line before "Source:" must survive
                    c[f] = re.sub(r"[ \t]{2,}", " ", HYPE.sub("", c[f])).replace(" ,", ",").strip()
        problems = verify(s, c) if c else ["no copy returned"]
        # a headline over the limit is the model's slip, not a wrong fact: the source's own headline stands in when
        # it fits and everything else checked out (a Meloni post was lost to five extra characters)
        if problems == ["headline too long"] and len(s["title"]) <= MAX_HEADLINE:
            c["headline"] = s["title"]
            problems = verify(s, c)
        if problems:
            rejected.append((s["title"], problems))
            s.update(headline=s["title"][:MAX_HEADLINE], dek="", x_post=s["title"],
                     linkedin_post=f"{s['title']}\n\nSource: {s['source']}", copy_status="fallback")
        else:
            s.update({k: c.get(k, "") for k in ("headline", "dek", "company", "company_domain", "backer", "person",
                                                 "person_role", "figure", "x_post", "linkedin_post", "image_query",
                                                 "topic")},
                     copy_status="ok")
            s["linkedin_post"] = drop_restated_lead(s["linkedin_post"], s["headline"])
            # a dek that only says the headline again is no dek ("Congress passed the overhaul ... in its final vote")
            if s.get("dek") and repeats(s["dek"], s["headline"]):
                s["dek"] = ""
            # the report adds facts; it never says the dek again, and never only the headline. The site prints dek
            # and report one under the other, so a repeat reads twice (SAP's job cuts, 2026-11-27). Sentences that
            # repeat either are cut; when nothing is left the report is empty and the dek carries the post alone.
            s["linkedin_post"] = drop_repeats(s["linkedin_post"], [s["dek"]] if s.get("dek") else [], s["headline"])
            # no dek: the report's first sentence moves up, so the page and the card never print an empty summary
            # line (Argentina's primaries and Tokyo inflation, 2026-11-27)
            if not s.get("dek"):
                first = sentences(body_of(s["linkedin_post"]))[:1]
                if first and len(first[0]) <= 160 and not repeats(first[0], s["headline"], share=0.6) and not LEANS.search(first[0]):
                    s["dek"] = first[0]
                    s["linkedin_post"] = drop_repeats(s["linkedin_post"], [s["dek"]], s["headline"])
            # an unchecked sentence is never shown: any problem leaves the field empty and the story as it was
            s["so_what"] = ""
            if switch("so_what") and s.get("lane") != "sport":
                sw = (c.get("so_what") or "").strip()
                if sw and not check_so_what(s, c, sw):
                    s["so_what"] = sw
            # "Culture" only when the story is about culture: a company's viral marketing is a business story
            if s.get("lane") == "sport":
                # the section is fixed by where the story came from, not by what the model says; no logo on a sport card
                s["topic"], s["backer"], c["orgs"] = "Sport", "", []
            elif s.get("topic") == "Culture" and not CULTURE.search(s["title"] + " " + s.get("summary", "")):
                s["topic"] = "Business"
            # a logo for an organisation the source never names would put a company on a story it is not in
            src = source_text(s).lower()
            orgs = c.get("orgs") if isinstance(c.get("orgs"), list) else []
            s["orgs"] = [o for o in orgs if isinstance(o, str) and o.strip() and o.lower() in src][:3]
            # a surname that is also a company reads as the company: "Ford and Unifor leader urge Ottawa to scrap
            # automaker emissions rules" is Ontario's premier, not Ford Motor. The headline gets the full name.
            from .entities import BRANDS
            if s.get("person") and len(s["person"].split()) > 1:
                first, last = s["person"].split()[0], s["person"].split()[-1]
                if (BRANDS.fullmatch(last.lower()) and re.search(rf"(?<!{re.escape(first)} )\b{re.escape(last)}\b", s["headline"])
                        and len(s["headline"]) + len(first) + 1 <= MAX_HEADLINE):
                    s["headline"] = re.sub(rf"(?<!{re.escape(first)} )\b{re.escape(last)}\b", f"{first} {last}", s["headline"], count=1)
            # the same holds for a face: only a person the source names may be pictured, and only when our own text
            # names them too, or the reader sees a face nobody on the card is
            # the card shows the headline, the detail slide the report: the dek alone is not on either
            shown = (s["headline"] + " " + s.get("linkedin_post", "")).lower()
            if s.get("person") and (s["person"].split()[-1].lower() not in src or s["person"].split()[-1].lower() not in shown):
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
            if s["figure"] and not figure_ok(s["figure"], seen):
                s["figure"] = ""
            # a bare count ("14") set huge says nothing unless the headline right under it says 14 of what
            if s["figure"] and not re.search(r"[$€£¥%]|\d\s?[A-Za-z]", s["figure"]) and not (_numbers(s["figure"]) & _numbers(s["headline"])):
                s["figure"] = ""
    return rejected
