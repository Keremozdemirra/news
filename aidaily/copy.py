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
The page lists its sources, so no sentence opens with a newsroom's name ("Bloomberg reports that ...") for a fact
several newsrooms give, and a report names a newsroom at most once, only for a claim that newsroom alone makes or that
the source hedges ("Reuters reported the revival, citing people familiar with the matter"). A hedged claim ("in talks",
"could", "plans to") is never written as a plain fact. Reports do not all open the same
way: not every one with "The company".
A currency conversion the source gives goes in parentheses right after the figure it converts, once, on its first
mention: "405.8 billion won ($303 million)". Never a sentence of its own, never one you work out yourself.
A percentage names its period as the source states it ("year on year", "on the month", "quarter on quarter",
"in October"). When the headline, dek and report give percentages for different periods, each one names its own.

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
  country when a senate, parliament, court, central bank or election is not American ("Argentina's Senate"), and
  call a chamber by its own name: Japan's Diet (House of Representatives, House of Councillors, never
  "Senate" or "Congress"), India's Rajya Sabha or Lok Sabha, Britain's House of Commons or House of Lords,
  Germany's Bundestag or Bundesrat, Russia's State Duma, South Korea's National Assembly, Israel's Knesset,
  Taiwan's Legislative Yuan, China's National People's Congress; "Senate" only where the chamber is called that
  (the United States, Australia, Canada, France, Italy, Spain, the Philippines, Argentina, Brazil, Mexico) and
  "Congress" only for the United States and Latin America. This holds in the dek and the report too
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
- venue: the institution or ground the story is about that a photo can show, by the name Wikipedia gives it: a central
  bank, court, parliament, stock exchange, ministry, international body, stadium or arena, like "Bank of Japan",
  "International Court of Justice", "Vitality Stadium" ("" if none; never a company, never a city alone)
- figure: the single key figure as written in the source, digits only, like "$36M", "40%" or "77,000" ("" if
  none, if it is a word like "a quarter", or if the source qualifies it with "more than", "up to", "about")
- x_post: max 240 characters, headline plus one fact, no hashtags, no link
- linkedin_post: the report, printed under the headline and the dek. Two sentences when one newsroom reported the
  story (nothing under "also reported"); three to five when two or more newsrooms each add a fact the others lack.
  Every sentence is a fact that is in neither the headline nor the dek (a sentence that says either again is
  deleted). Use every such fact the listed reports hold: who, what, how much, when, where, what was said, what
  happens next as the sources state it; no fact that only one sentence of a source half-states. Say each fact in
  your own words: never copy a run of seven words or more from a source, and quote at most one statement in the
  whole post, under 15 words, with its speaker. The dek and these sentences together stay under 600 characters.
  The first sentence names its subject: never open with "It", "This", "They", "These", "Together" or "also".
  Every sentence is about the story the headline names: nothing from another story ("Separately, ..."), nothing
  about the source article itself ("named in the report's headline"). Each sentence complete and grammatical,
  never a source phrase pasted into another sentence. If the sources hold no fact beyond the headline and dek,
  write only the Source line. End with the line "Source: <outlet>"
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

# Added to the prompt only while desk.json growth.by_source is true. Log-only: the lines are checked and stored on the
# post (post.json "by_source") and no page, card or caption prints them yet.
BY_SOURCE_FIELD = """
- by_source: [] or one object per newsroom that has a fact of its own, {{"outlet": "<name exactly as listed>", "line":
  "<one sentence>"}}. The outlet is the one named after "outlet:" or one named under "also reported". The line says
  what THAT newsroom's own title and summary say, with nothing from any other newsroom, in your own words (never a run
  of seven words copied, no quote), max 25 words, no newsroom named, no "reports that". Leave a newsroom out when its
  text adds nothing. [] for a story only one newsroom reported"""


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


PCT = re.compile(r"(\d+(?:[.,]\d+)?)\s?(?:%|percent\b|per cent\b|percentage points?\b)", re.I)
_MONTHS = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
PERIODS = {
    "year": re.compile(r"\b(?:year[- ](?:on|over)[- ]year|on[- ]year|yoy|y/y|annual\w*|(?:a|the|last|previous|prior|this|full|per) "
                       r"year|years?)\b|\bfull-year\b", re.I),
    "quarter": re.compile(r"\b(?:quarter[- ]on[- ]quarter|q/q|sequential\w*|quarter\w*|Q[1-4])\b|\b(?:first|second|third|fourth)-quarter\b", re.I),
    "month": re.compile(r"\b(?:month[- ]on[- ]month|on the month|m/m|month\w*|" + _MONTHS + r")\b", re.I),
    "week": re.compile(r"\b(?:week[- ]on[- ]week|w/w|week\w*)\b", re.I),
    "day": re.compile(r"\b(?:day|session|today|intraday|overnight)\b", re.I),
}


TWELVE_MONTHS = re.compile(r"\b(?:12|twelve)[- ]months?\b", re.I)


def _period_kinds(sentence):
    """"the past 12 months" is a year, not a month; a weekday or a bare year number names no period."""
    sentence = TWELVE_MONTHS.sub("year", sentence)
    return {k for k, rx in PERIODS.items() if rx.search(sentence)}


FROM_BEFORE = re.compile(r"\bfrom\s+$", re.I)  # "slows to 2.1% from 2.6%": the earlier figure is a reference, not a claim


def _percent_sentences(story, c):
    """(figure, sentence, field) for every percentage the copy prints and every sentence of the source that has one."""
    mine = []
    for field in ("headline", "dek", "linkedin_post"):
        text = "\n".join(l for l in str(c.get(field) or "").splitlines() if not l.startswith("Source:"))
        for sent in ([text] if field == "headline" else sentences(" ".join(text.split("\n")))):
            for m in PCT.finditer(sent):
                if not FROM_BEFORE.search(sent[:m.start()]):
                    mine.append((m.group(1).replace(",", ""), sent, field))
    theirs = []
    for title, summary in [(story.get("title", ""), story.get("summary", ""))] + [(r.get("title", ""), r.get("summary", "")) for r in story.get("reports") or []]:
        for sent in [title] + sentences(summary):
            theirs += [(m.group(1).replace(",", ""), sent) for m in PCT.finditer(sent) if not FROM_BEFORE.search(sent[:m.start()])]
    return mine, theirs


def period_gaps(story, c):
    """{figure: why} for percentages whose period the page leaves out. Only when the page prints two or more
    different percentages: a lone figure cannot be mistaken for another period. The period must be the source's own
    ("year on year" over a figure the source gives for the month is wrong), and a figure whose source sentence names
    no period needs none."""
    mine, theirs = _percent_sentences(story, c)
    figs = {f for f, _, _ in mine}
    if len(figs) < 2:
        return {}
    gaps = {}
    for fig in figs:
        needed = set().union(*[_period_kinds(sent) for f, sent in theirs if f == fig]) if any(f == fig for f, _ in theirs) else set()
        if not needed:
            continue
        got = set().union(*[_period_kinds(sent) for f, sent, _ in mine if f == fig])
        if not got:
            gaps[fig] = f"{fig}% names no period; the source says {sorted(needed)}"
        elif not got & needed:
            gaps[fig] = f"{fig}% names {sorted(got)}, the source {sorted(needed)}"
    return gaps


def trim_periods(story, c):
    """A report or dek sentence whose percentage has no period is cut; the report is optional and so is the dek (the
    report's first sentence moves up in its place). The headline is not: its gap stays and rejects the story."""
    gaps = period_gaps(story, c)
    headline = c.get("headline", "")
    cut = [g for g in gaps if not any(m.group(1).replace(",", "") == g for m in PCT.finditer(headline))]
    if not cut:
        return []
    out = []

    def trim(text):
        lines = []
        for line in str(text or "").split("\n"):
            if line.startswith("Source:") or not line.strip():
                lines.append(line)
                continue
            kept = []
            for sent in sentences(line):
                (out.append(sent) if any(m.group(1).replace(",", "") in cut for m in PCT.finditer(sent)) else kept.append(sent))
            if kept:
                lines.append(" ".join(kept))
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    c["linkedin_post"] = trim(c.get("linkedin_post"))
    if isinstance(c.get("dek"), str):
        c["dek"] = trim(c["dek"])
    return out


AMOUNT = r"\d+(?:[.,]\d+)*(?: ?(?:million|billion|trillion|m|bn|tn|k))?"
MONEY = r"(?:about |roughly |around |nearly |some )?[$\u20ac\u00a3\u00a5][\d]+(?:[.,]\d+)*(?: ?(?:million|billion|trillion|m|bn|tn|k))?"
# an amount in a currency other than the dollar: "405.8 billion won", "40 euros", "\u20ac40 million"
FOREIGN = (r"(?:[\u20ac\u00a3\u00a5\u20b9]\d+(?:[.,]\d+)*(?: ?(?:million|billion|trillion|m|bn|tn|k))?|" + AMOUNT +
           r" (?:won|yen|euros?|pounds?|rupees?|yuan|renminbi|francs?|kroner|krona|rubles?|reais|pesos?|lira|zloty|baht|rand|dirhams?|riyals?))")
# a conversion that is a sentence of its own: "That equals $303 million." It only counts after a sentence that holds a
# foreign amount: "The deal is worth $5 billion." is a fact, not a conversion.
CONVERSION_SENTENCE = re.compile(r"^(?:That|This|It)\s+(?:equals?|is equal to|converts to|translates to|works out to|is equivalent to)\s+" + MONEY, re.I)
# "405.8 billion won, or $303 million": the same conversion, written outside parentheses. Only after a foreign amount:
# "priced at $5 or $6" and "a deal worth $5 billion" are not conversions.
INLINE_CONVERSION = re.compile(r"(" + FOREIGN + r")(,)? (?:or|equal(?:s|ing)?|equivalent to) (" + MONEY + r")(?(2),?)(?=[,.;]|\s|$)", re.I)


def is_conversion(sent, prev=""):
    """A sentence that is only the dollar value of the foreign amount the sentence before it gave."""
    return bool(CONVERSION_SENTENCE.search(sent) and re.search(FOREIGN, prev or "", re.I))


PAREN_CONVERSION = re.compile(r"\((" + MONEY + r")\)", re.I)


def fix_conversions(c):
    """A conversion is a parenthesis after its figure and appears once. A sentence that is only a conversion is cut,
    an inline one ("405.8 billion won, or $303 million") moves into parentheses, a repeat of one already given goes.
    Returns the sentences cut."""
    cut, seen = [], set()
    for field in ("headline", "dek", "linkedin_post", "x_post"):
        text = c.get(field)
        if not isinstance(text, str) or not text:
            continue
        if field == "x_post":
            seen = set()  # its own post: the first mention there is its own
        lines = []
        for line in text.split("\n"):
            if line.startswith("Source:") or not line.strip():
                lines.append(line)
                continue
            kept, prev = [], ""
            for sent in sentences(line):
                before, prev = prev, sent
                if is_conversion(sent, before):
                    cut.append(sent)
                    continue
                sent = INLINE_CONVERSION.sub(lambda m: f"{m.group(1)} ({m.group(3)})", sent)

                def once(m):
                    key = re.sub(r"\W", "", m.group(1).lower())
                    if key in seen:
                        return ""
                    seen.add(key)
                    return m.group(0)
                kept.append(re.sub(r" {2,}", " ", PAREN_CONVERSION.sub(once, sent)).replace(" .", ".").replace(" ,", ",").strip())
            if kept:
                lines.append(" ".join(kept))
        c[field] = "\n".join(lines).strip()
    return cut


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
    problems += [f"period: {why}" for why in period_gaps(story, copy).values()]
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
    return PROMPT.format(stories=block, recent=tail, extra_fields=(SO_WHAT_FIELD if switch("so_what") else "") + (BY_SOURCE_FIELD if switch("by_source") else ""),
                         audience=SPORT_AUDIENCE if sport else AUDIENCE, relevant=SPORT_RELEVANT if sport else RELEVANT,
                         topic_rule=SPORT_TOPIC_RULE if sport else TOPIC_RULE,
                         image_rule=SPORT_IMAGE if sport else IMAGE_RULE,
                         company_rule=SPORT_COMPANY if sport else 'the main company the story is about, as the company names itself ("" if none)')


def source_text(story):
    """Every word the copy may stand on: the lead's title and summary and the other newsrooms' reports."""
    return " ".join([story.get("title", ""), story.get("summary", "")]
                    + [f"{r.get('title', '')} {r.get('summary', '')}" for r in story.get("reports") or []])


SUMMARY_CAP = 600  # what the feeds keep (feeds.clean); the writer used to see only 500 and 400 of it


def block(stories):
    out = []
    for i, s in enumerate(stories):
        s["id"] = i
        also = "".join(f"\n- {r['outlet']}: {r['title']}. {r['summary'][:SUMMARY_CAP]}" for r in s.get("reports") or [])
        out.append(f"id: {i}\noutlet: {s['source']}\ntitle: {s['title']}\nsummary: {s.get('summary', '')[:SUMMARY_CAP]}"
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


# a full stop that ends an abbreviation ends no sentence: "found on Nov. 3." is one sentence, not two
ABBR = re.compile(r"(?:^|\s)(?:Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|Mr|Mrs|Ms|Dr|St|Gov|Sen|Rep|Gen|Lt|"
                  r"Col|Corp|Inc|Ltd|No|vs|[A-Z]\.[A-Z]|U\.S|U\.K|U\.N)\.$")


def sentences(text):
    out = []
    for x in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"“‘'])", text or ""):
        if not x.strip():
            continue
        if out and ABBR.search(out[-1]):
            out[-1] += " " + x
        else:
            out.append(x)
    return out


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
        # a number the headline and dek do not have is a new fact, whatever words carry it: "Muse commands 51 percent
        # of all agentic shopping orders" was cut for sharing its other words with them
        if _numbers(x) - _numbers(both):
            kept.append(x)
            cut = False
        elif any(d and said(x, d) for d in deks) or (deks and repeats(x, both, share=0.6)):
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


# a sentence about the source rather than the news ("with Dwight McNeil named in the report's headline"), or about
# another story ("Separately, the Liberal Democrats say ..."): never report
META = re.compile(r"\b(?:the (?:report|article|story|source)['’]s (?:headline|title)|named in the (?:report|headline|article|"
                  r"story)|the (?:article|report|story|source|piece) (?:says|said|notes|adds|reports|describes)|"
                  r"(?:the|this) (?:report|article|story|piece) (?:cites|cited|quotes|quoted|mentions|mentioned|names|identifies|"
                  r"gives|offers|provides|includes|relies|is based|draws|attributes|did not|didn['’]t|does not|doesn['’]t)|"
                  r"according to the (?:report|article|story|piece))\b", re.I)
OFFTOPIC = re.compile(r"^(?:Separately|In other news|Elsewhere|In a separate (?:development|story|move))\b", re.I)


VERBATIM_WORDS = 8     # a run this long, word for word from a source, is copied, not reported (the prompt asks for under 7)
QUOTE_WORDS = 15       # the longest statement the post may quote, once
QUOTE = re.compile(r"[\"“]([^\"”]{1,500})[\"”]")
MAX_REPORT = 600       # dek and report together: what the detail slide can set without shrinking past 38 px


def _words(text):
    return re.findall(r"[a-z0-9]+(?:['’][a-z]+)?", _fold(text).lower())


def copied_run(sentence, source, n=VERBATIM_WORDS):
    """The first run of `n` words the sentence takes word for word from the source, or "". Quoted statements are
    judged apart (see strip_copied); the rest must be the writer's own words (the EU press publishers' right allows
    very short extracts only)."""
    words, src = _words(QUOTE.sub(" ", sentence)), _words(source)
    grams = {tuple(src[i:i + n]) for i in range(len(src) - n + 1)}
    for i in range(len(words) - n + 1):
        if tuple(words[i:i + n]) in grams:
            return " ".join(words[i:i + n])
    return ""


def strip_copied(story, c):
    """Cuts the sentences that copy a source and the quotes past the first short one; the story keeps its other
    facts. A quote is a quoted statement of four words or more ("underhanded" is a term, not a quote). Returns the
    sentences cut."""
    src = source_text(story)
    cut, quoted = [], False
    for field in ("dek", "linkedin_post", "x_post"):
        text = c.get(field)
        if not isinstance(text, str) or not text:
            continue
        lines = []
        for line in text.split("\n"):
            if line.startswith("Source:") or not line.strip():
                lines.append(line)
                continue
            kept = []
            for sent in sentences(line):
                quotes = [q for q in QUOTE.findall(sent) if len(q.split()) >= 4]
                too_long = any(len(q.split()) > QUOTE_WORDS for q in quotes)
                if too_long or (quotes and quoted and field != "x_post") or copied_run(sent, src):
                    cut.append(sent)
                    continue
                if quotes and field != "x_post":
                    quoted = True
                kept.append(sent)
            if kept:
                lines.append(" ".join(kept))
        c[field] = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    if not c.get("x_post"):
        c["x_post"] = c.get("headline", "")
    return cut


def cap_report(dek, post, limit=MAX_REPORT):
    """The report without its last sentences while dek and report together run past what the detail slide holds; the
    two sentences an article needs always stay."""
    lines = (post or "").split("\n")
    tail = [l for l in lines if l.startswith("Source:")]
    sents = sentences(body_of(post))
    while len(sents) > MIN_SENTENCES and len(dek or "") + len(" ".join(sents)) > limit:
        sents.pop()
    body = " ".join(sents)
    return (body + ("\n\n" + "\n".join(tail) if tail else "")).strip() if body else "\n".join(tail)


ALIAS_NAMES = {"FT": "Financial Times", "WSJ": "The Wall Street Journal", "NYT": "The New York Times"}
FEED_SUFFIX = re.compile(r"\s+(AI|Tech|Technology|Companies|Business|Main|Top Stories|Top News|News|World|US Politics|Politics|"
                         r"Economy|Economics|Markets|Finance|Venture|Asia)$")
SAYS = r"(?:reports?|reported|says?|said|writes?|wrote|states?|stated|adds?|added|notes?|noted|claims?|claimed|reveals?|revealed)"
DESCRIBES = r"(?:describes?|described|cites?|cited|quotes?|quoted|mentions?|mentioned|according to)"


def outlet_names(story):
    """Every way the page's own source list names the newsrooms that reported the story."""
    raw = [story.get("source", "")] + [r.get("outlet", "") for r in story.get("reports") or []] \
        + list(story.get("newsrooms") or story.get("outlets") or [])
    names = set()
    for n in raw:
        n = FEED_SUFFIX.sub("", n or "").strip()
        for x in {n, ALIAS_NAMES.get(n, n)}:
            if len(x) >= 2:
                names |= {x, re.sub(r"^The ", "", x)}
    return {n for n in names if len(n) >= 2}


def _outlet_rx(names):
    return "(?:" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + ")"


# a clause that is hedged or leans on a source stays attributed: "Bloomberg reports that Intel is in talks" is the
# newsroom's claim, not a fact the page may state as its own
HEDGED = re.compile(r"\b(?:in talks|talks|could|may|might|would|plans? to|planning to|set to|poised to|expected to|"
                    r"considering|weighing|exploring|negotiat\w+|citing|people familiar|sources?|unnamed|insiders?|"
                    r"reportedly|is said to|are said to|allegedly|rumou?rs?)\b", re.I)
BARE_PRONOUN = re.compile(r"^(?:it|its|he|she|they|them|his|her|their|this|that|these|those)\b", re.I)


def newsroom_count(story):
    keys = {_outlet_key(n) for n in [story.get("source", "")] + [r.get("outlet", "") for r in story.get("reports") or []]
            + list(story.get("newsrooms") or story.get("outlets") or []) if n}
    return len(keys)


def attributed_clause(sent, story):
    """The clause of "<Outlet> reports that <clause>" or "According to <Outlet>, <clause>" when the opener may go, else
    None. It stays when the story has one newsroom (then it is that newsroom's claim), when the clause is hedged or
    sourced, and when the clause begins with a pronoun that would dangle once the newsroom is gone."""
    names = outlet_names(story)
    if not names or newsroom_count(story) < 2:
        return None
    O = _outlet_rx(names)
    m = re.match(rf"^(?:the )?{O}(?:['\u2019]s [a-z]+(?: [a-z]+)?)? (?:also )?{SAYS} that\s+(?=\S)", sent, re.I) \
        or re.match(rf"^according to (?:the )?{O},\s+(?=\S)", sent, re.I)
    if not m:
        return None
    clause = sent[m.end():]
    if len(clause.split()) < 4 or HEDGED.search(clause) or BARE_PRONOUN.search(clause) or re.search(rf"\b{O}\b", clause, re.I):
        return None
    return clause


def strip_attributions(story, c):
    """The page lists its sources: a sentence never opens with "Bloomberg reports that ..." when two or more newsrooms
    reported the story, and a text names a newsroom at most once. A plain opener is cut and the clause stands
    ("Bloomberg reports that prices fell" becomes "Prices fell"); a hedged or sourced claim ("in talks", "citing
    people familiar"), a claim of the only newsroom, and a clause that opens with a pronoun keep their attribution
    (the claim would read as fact, or dangle). A sentence that only describes the source ("The Guardian describes the
    letter as ...") goes. Returns the sentences cut."""
    names = outlet_names(story)
    if not names:
        return []
    O = _outlet_rx(names)
    about = re.compile(rf"^(?:the )?{O}(?:['\u2019]s [a-z]+(?: [a-z]+)?)? (?:also )?{DESCRIBES}\b", re.I)
    mid = re.compile(rf",?\s*\b(?:according to|as reported by|reported by|per)\s+(?:the )?{O}\b|,?\s*\b(?:the )?{O}\s+(?:reported|reports|said|says|writes|wrote)\b", re.I)
    cut, named = [], False
    for field in ("dek", "linkedin_post"):
        text = c.get(field)
        if not isinstance(text, str) or not text:
            continue
        lines = []
        for line in text.split("\n"):
            if line.startswith("Source:") or not line.strip():
                lines.append(line)
                continue
            kept = []
            for sent in sentences(line):
                if about.search(sent):
                    cut.append(sent)
                    continue
                clause = attributed_clause(sent, story)
                if clause:
                    sent = clause[0].upper() + clause[1:]
                if mid.search(sent):
                    if named:
                        trimmed = mid.sub("", sent).strip()
                        if len(trimmed.split()) < 4 or mid.search(trimmed):
                            cut.append(sent)
                            continue
                        sent = trimmed if trimmed.endswith((".", "!", "?")) else trimmed + "."
                    named = True
                kept.append(sent)
            if kept:
                lines.append(" ".join(kept))
        c[field] = "\n".join(lines).strip()
    return cut


NAME_WORD = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-zA-Z’'-]{2,}")
CALENDAR = set("January February March April May June July August September October November December Jan Feb Mar Apr "
               "Jun Jul Aug Sep Sept Oct Nov Dec Monday Tuesday Wednesday Thursday Friday Saturday Sunday".split())


def _names(text):
    return {re.sub(r"['’]s$", "", w).lower() for w in NAME_WORD.findall(text or "") if w not in CALENDAR}


def drop_offtopic(post, headline, dek="", source=""):
    """The report without sentences about something else. Cut: a sentence about the source article ("named in the
    report's headline"), one that opens another story ("Separately, ..."), and one that shares no word with the
    headline, the dek or a sentence kept before it while bringing in two names none of them nor the lead source
    carries. The Zelenskyy article (2026-11-27) ran a headline about Hitler and Putin over drones in Latvia."""
    lines = (post or "").split("\n")
    tail = [l for l in lines if l.startswith("Source:")]
    known = _names(" ".join([headline, dek, source])) | {w.lower() for w in WORD.findall(_fold(headline + " " + dek))}
    kept = []
    for x in sentences(" ".join(l for l in lines if l.strip() and not l.startswith("Source:"))):
        context = _stems(" ".join([headline, dek] + kept), short=True) | _stems(" ".join([headline, dek] + kept))
        new_names = {n for n in _names(x) if n not in known and _fold(n) not in known}
        unrelated = not (_stems(x, short=True) & context) and not (_numbers(x) & _numbers(headline + " " + dek + " " + " ".join(kept)))
        if META.search(x) or OFFTOPIC.search(x) or (unrelated and len(new_names) >= 2):
            continue
        kept.append(x)
    body = " ".join(kept)
    return (body + ("\n\n" + "\n".join(tail) if tail else "")).strip() if body else "\n".join(tail)


# Legislatures called by another country's name. A country that has no Senate has an upper house under its own name
# ("Japan's Senate" is the House of Councillors, 2026-11-27); one that has no Congress has a parliament, a Diet, a
# Bundestag. UPPER_HOUSE is a short allow-list of countries known to have none: a country that really has a Senate
# (Australia, Canada, France, Italy, Spain, the Philippines, Argentina, Brazil, Mexico, Thailand, Pakistan, Poland,
# Belgium, the Czech Republic, Romania, Kenya, Nigeria, Egypt, Kazakhstan, Jordan, the Netherlands, Ireland, Malaysia)
# is not in it, so its copy is never rewritten. "India's Congress" is the party and stays.
UPPER_HOUSE = {"Japan": "upper house", "India": "upper house", "Germany": "Bundesrat", "Russia": "upper house",
               "Britain": "House of Lords", "UK": "House of Lords", "U.K.": "House of Lords", "Austria": "upper house",
               "Switzerland": "upper house", "South Korea": "National Assembly", "Taiwan": "legislature", "Israel": "Knesset",
               "Turkey": "parliament", "China": "legislature", "Sweden": "parliament", "Denmark": "parliament",
               "Norway": "parliament", "Finland": "parliament", "New Zealand": "parliament", "Indonesia": "upper house",
               "Ukraine": "parliament", "Hungary": "parliament", "Portugal": "parliament", "Greece": "parliament",
               "Vietnam": "National Assembly", "South Africa": "upper house", "Iran": "parliament",
               "Saudi Arabia": "council", "Singapore": "parliament", "Morocco": "upper house"}
CONGRESS = {"Japan": "Diet", "Britain": "Parliament", "UK": "Parliament", "U.K.": "Parliament", "Germany": "Bundestag",
            "Australia": "Parliament", "Canada": "Parliament", "Russia": "State Duma", "South Korea": "National Assembly",
            "Israel": "Knesset", "Turkey": "parliament", "Italy": "parliament", "New Zealand": "Parliament",
            "Ireland": "Dail", "Sweden": "Riksdag", "Norway": "Storting", "Denmark": "Folketing", "Taiwan": "Legislative Yuan",
            "Singapore": "Parliament", "Poland": "Sejm", "Hungary": "parliament", "Ukraine": "Verkhovna Rada"}
# "Japanese Senate", "British Congress": the country's adjective names it the same way
ADJECTIVE = {"Japanese": "Japan", "British": "Britain", "German": "Germany", "Russian": "Russia", "Israeli": "Israel",
             "Turkish": "Turkey", "Korean": "South Korea", "Taiwanese": "Taiwan", "Indian": "India", "Swedish": "Sweden",
             "Norwegian": "Norway", "Danish": "Denmark", "Polish": "Poland", "Ukrainian": "Ukraine", "Irish": "Ireland",
             "Australian": "Australia", "Canadian": "Canada"}
_PLACES = sorted(set(UPPER_HOUSE) | set(CONGRESS) | set(ADJECTIVE), key=len, reverse=True)
SENATE = re.compile(r"\b(" + "|".join(map(re.escape, sorted(UPPER_HOUSE, key=len, reverse=True))) + r")(['’]s)?\s+Senate\b")
# not a chamber: "Irish Congress of Trade Unions", "Nigeria's Senate President", "Senate Majority Leader"
WRONG_CHAMBER = re.compile(r"\b(" + "|".join(map(re.escape, _PLACES)) + r")(['\u2019]s)?\s+(Senate|Congress)\b(?!\s+of\b)"
                           r"(?!\s+(?i:Party|leaders?|spokes\w+|president|chief|MPs?|majority|minority)\b)")


def _right_chamber(country, word):
    country = ADJECTIVE.get(country, country)
    if word == "Senate":
        return UPPER_HOUSE.get(country)
    # "Indian Congress" and "India's Congress" are the party; Australia and Canada have a Senate but no Congress
    return CONGRESS.get(country)


def fix_legislature(text):
    """A country's chamber by its own name: "Japan's Senate" becomes "Japan's upper house", "Britain's Congress"
    "Britain's Parliament". A chamber the country does have is never touched."""
    def swap(m):
        right = _right_chamber(m.group(1), m.group(3))
        return m.group(0) if right is None else f"{m.group(1)}{m.group(2) or ''} {right}"
    return WRONG_CHAMBER.sub(swap, text or "")


def wrong_chamber(text):
    """The first "Japan's Senate" in a text, or "". Used by the audit, which holds a post that still has one."""
    for m in WRONG_CHAMBER.finditer(text or ""):
        if _right_chamber(m.group(1), m.group(3)) is not None:
            return m.group(0)
    return ""


# a headline's own opener is a name only when it is not a plain word: "Spain holds snap election" is about Spain,
# "Why the Fed waits" is not about "Why"
OPENERS = set("a an the why how what when where who will can could would should does did is are was were more most "
              "new first last big top key major latest after before as at in on by for with from to of and or but "
              "shares stocks prices markets investors oil gold bonds".split())


def _prefixes(text):
    return {w[:4] for w in WORD.findall(_fold(text).lower()) if len(w) >= 4}


def _heads(text):
    """Four-letter stem prefixes of a text's content words: "Chinese" and "China", "calling" and "calls" meet."""
    return {w[:4] for w in _stems(text, short=True)}


def _bridged(story, mine, theirs):
    """One source sentence holds a word of the headline and a word of the dek or report that the headline lacks:
    the two were written from the same passage, whatever words each chose ("Spain heads to early election" over
    "the vote may usher in a right-wing coalition")."""
    pieces = [(story.get("title", ""), story.get("summary", ""))] + [(r.get("title", ""), r.get("summary", ""))
                                                                      for r in story.get("reports") or []]
    for title, summary in pieces:
        for sent in [title] + sentences(summary):
            heads = _heads(sent)
            if heads & mine and heads & theirs:
                return True
    return False


def fingerprint(headline, dek, post):
    """Marks the text the writer checked: a post whose text was edited by hand afterwards no longer matches."""
    import hashlib
    return hashlib.sha1("\n".join([headline or "", dek or "", body_of(post)]).encode()).hexdigest()[:12]


def headline_gap(headline, dek, post, story=None):
    """Why the dek and report do not support the headline, or "". The headline is the claim; the dek and report
    are what stands behind it. When they share none of its numbers, none of its names and almost none of its
    words, the page is two stories: the Zelenskyy headline about Putin and Hitler ran over a report on drones in
    Latvia (2026-11-27). The reader sees the headline first, so it is the headline that is withheld. With the
    story at hand, a source sentence that holds a word from each side also counts as support."""
    text = f"{dek or ''} {body_of(post)}".strip()
    if not text or not (headline or "").strip():
        return ""  # thin() reports an empty report; there is nothing to compare
    if _numbers(headline) & _numbers(text):
        return ""
    names = {n for n in _names("- " + headline) if len(n) >= 4 and n not in OPENERS}
    seen = _prefixes(text)
    if any(n[:4] in seen for n in names):
        return ""
    mine = _heads(headline)
    theirs = _heads(text)
    shared = mine & theirs
    if len(shared) >= 2 or (mine and len(shared) / len(mine) >= 0.34):
        return ""
    # a dek and report that only use other words for the same news ("restructuring" under "job cuts") bring in
    # no one new; a page about another story brings in its own people and places
    others = _names(f"- {dek or ''} {body_of(post)}") | _names("- " + (dek or ""))
    strangers = {n[:4] for n in others if len(n) >= 4 and n not in OPENERS and n[:4] not in _prefixes(headline)}
    if len(strangers) < 2:
        return ""
    if story and _bridged(story, mine, theirs - mine):
        return ""
    return "the dek and report do not support the headline"


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


# a name that is also an ordinary word or a surname is not read as a company without the model saying so
AMBIGUOUS_BRANDS = {"target", "shell", "arm", "ford", "windows", "pixel", "ati", "citi", "visa"}
# an institution of government is not a company: no logo, ticker or hashtag (the desk's own rule, "filler")
GOVERNMENT = re.compile(r"\b(?:court|tribunal|federal reserve|the fed|central bank|reserve bank|ecb|bank of (?:england|japan|canada|korea|"
                        r"france|italy|israel|mexico|china|russia|thailand|jamaica)|people['\u2019]s bank|congress|senate|parliament|"
                        r"ministry|department|commission|treasury|government|police|army|navy|white house|kremlin|supreme)\b", re.I)
# the product in a headline, and the company that makes it
MAKER = {"iphone": "Apple", "ipad": "Apple", "macbook": "Apple", "radeon": "AMD", "geforce": "Nvidia", "snapdragon": "Qualcomm",
         "xbox": "Microsoft", "facebook": "Meta", "instagram": "Meta", "whatsapp": "Meta", "alexa": "Amazon", "kindle": "Amazon",
         "chatgpt": "OpenAI", "starlink": "SpaceX", "playstation": "Sony"}


def headline_company(headline, text=""):
    """(company, position) of the first company a headline names, spelled as the headline spells it, or ("", 0).
    Only a well-known company written with its capital, found in the source text too; a product stands for its maker
    ("iPhone" for Apple). The model leaves the field empty on "OpenAI raises ..." often enough that the tag, the
    hashtag and the page's "about" went missing."""
    from .entities import BRANDS
    low = (text or "").lower()
    for m in BRANDS.finditer(headline or ""):
        word = m.group(0)
        key = word.lower()
        if (not word[0].isupper() and key not in ("openai", "nvidia", "iphone", "chatgpt")) or key in AMBIGUOUS_BRANDS:
            continue
        name = MAKER.get(key, word)
        if name.lower() in low or key in low:
            return name, m.start()
    return "", 0


def tag_company(s):
    """The company field follows the headline: set when the headline names a company and the field is empty or names
    one the headline does not. The company is the first one the headline names, a well-known brand or an
    organisation the model listed from the source; it also leads the `orgs` list."""
    head_ = s.get("headline", "")
    low = head_.lower()
    found = [(m.start(), m.group(0)) for o in s.get("orgs") or [] if isinstance(o, str) and len(o) > 2 and not GOVERNMENT.search(o)
             for m in [re.search(rf"(?<![\w])({re.escape(o)})(?![\w])", head_)] if m]
    brand, at = headline_company(head_, source_text(s))
    if brand:
        found.append((at, brand))
    if not found:
        return
    named = min(found)[1]
    have = s.get("company") or ""
    if not have or have.lower() not in low:
        s["company"] = named
    if named.lower() not in [o.lower() for o in s.get("orgs") or []]:
        s["orgs"] = ([named] + list(s.get("orgs") or []))[:3]


BY_SOURCE_MIN = 2   # a by-source list needs two newsrooms that each pass: one line is just the report again
BY_SOURCE_WORDS = 30


def _outlet_key(name):
    n = FEED_SUFFIX.sub("", name or "").strip()
    return re.sub(r"^the ", "", ALIAS_NAMES.get(n, n).lower())


def check_by_source(story, rows):
    """The by-source lines that stand, or []. Each line says what one newsroom's own title and summary say: the
    outlet must be one the story lists, and the line must be one sentence of its own words, with every number from that
    newsroom's own text and most of its words too (ungrounded() against that text alone), no quote, no run copied from
    it, no other newsroom named, no commentary. A list is kept only when two or more newsrooms pass."""
    from . import desk  # the house slop list lives in desk; imported here because desk imports this module
    if not isinstance(rows, list):
        return []
    own = {_outlet_key(story.get("source", "")): (story.get("source", ""), f"{story.get('title', '')} {story.get('summary', '')}")}
    for r in story.get("reports") or []:
        own.setdefault(_outlet_key(r.get("outlet", "")), (r.get("outlet", ""), f"{r.get('title', '')} {r.get('summary', '')}"))
    kept, used = [], set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("outlet"), str) or not isinstance(row.get("line"), str):
            continue
        key = _outlet_key(row["outlet"])
        line = re.sub(r"\s+", " ", row["line"].translate(DASHES)).strip()
        if key not in own or key in used or not line:
            continue
        name, text = own[key]
        others = {n for k, (o, _) in own.items() if k != key for n in outlet_names({"source": o})} - outlet_names({"source": name})
        if (len(sentences(line)) != 1 or len(line.split()) > BY_SOURCE_WORDS or not line.endswith((".", "!", "?"))
                or _numbers(line) - _numbers(text) or ungrounded(line, f"{text} {name}") or copied_run(line, text)
                or [q for q in QUOTE.findall(line) if len(q.split()) >= 4] or META.search(line) or OFFTOPIC.search(line)
                or HYPE.search(line) or NOT_BUT.search(line) or desk.SLOP.search(line) or MALFORMED.search(line)
                or (others and re.search(r"\b" + _outlet_rx(others) + r"\b", line))
                or re.search(rf"^(?:the )?{_outlet_rx(outlet_names({'source': name}))}\s+{SAYS}\b", line, re.I)):
            continue
        used.add(key)
        kept.append({"outlet": name, "line": line})
    return kept if len(kept) >= BY_SOURCE_MIN else []


def fall_back(s):
    """The story as its source worded it: no checked copy, so the desk will not post it."""
    s.update(headline=s["title"][:MAX_HEADLINE], dek="", x_post=s["title"],
             linkedin_post=f"{s['title']}\n\nSource: {s['source']}", copy_status="fallback", by_source=[])


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
            strip_attributions(s, c)
            fix_conversions(c)
            strip_ungrounded(s, c)
            strip_copied(s, c)
            trim_periods(s, c)
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
            fall_back(s)
        else:
            s.update({k: c.get(k, "") for k in ("headline", "dek", "company", "company_domain", "backer", "person",
                                                 "person_role", "figure", "x_post", "linkedin_post", "image_query",
                                                 "topic", "venue")},
                     copy_status="ok")
            for f in ("headline", "dek", "x_post", "linkedin_post"):
                s[f] = fix_legislature(s.get(f, ""))
            if s.get("dek") and (META.search(s["dek"]) or OFFTOPIC.search(s["dek"])):
                s["dek"] = ""
            s["linkedin_post"] = drop_offtopic(s["linkedin_post"], s["headline"], s.get("dek", ""),
                                               s.get("title", "") + " " + s.get("summary", ""))
            s["linkedin_post"] = drop_restated_lead(s["linkedin_post"], s["headline"])
            # a dek about another subject than the headline's ("Separately, the Liberal Democrats ...") is no dek: the
            # story keeps its report, whose first sentence moves up below
            if s.get("dek") and headline_gap(s["headline"], s["dek"], "", s):
                s["dek"] = ""
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
            s["linkedin_post"] = cap_report(s.get("dek", ""), s["linkedin_post"])
            # an unchecked sentence is never shown: any problem leaves the field empty and the story as it was
            s["so_what"] = ""
            if switch("so_what") and s.get("lane") != "sport":
                sw = (c.get("so_what") or "").strip()
                if sw and not check_so_what(s, c, sw):
                    s["so_what"] = sw
            # what is left to show must stand behind the headline; a headline over another story's report is withheld
            gap = headline_gap(s["headline"], s.get("dek", ""), s.get("linkedin_post", ""), s)
            if gap:
                rejected.append((s["title"], [gap]))
                fall_back(s)
                continue
            s["supported"] = fingerprint(s["headline"], s.get("dek", ""), s.get("linkedin_post", ""))
            # log-only: stored for the post.json record, shown nowhere
            s["by_source"] = check_by_source(s, c.get("by_source")) if switch("by_source") else []
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
            if s.get("lane") != "sport":
                tag_company(s)
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
