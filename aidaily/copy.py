"""Write the day's post copy with Claude, then check it against the sources.

The model gets only the fetched titles and summaries and no tools: it cannot
browse, post or read files. Every number it writes must appear in the source
text, or the story falls back to the source headline. A wrong figure in a
news post is the one mistake this brand cannot afford.
"""
import json
import re
import subprocess

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
- topic: one of AI, Tech, Business, Markets, Economy, Politics, World, Culture
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
  slot, an opinion piece in a breaking slot; true otherwise

Return a JSON array only, no prose.

STORIES:
{stories}"""

NUM = re.compile(r"\d+(?:[.,]\d+)?")
WORD = re.compile(r"[a-z][a-z'’]+")
FILLER = set("that this with from their they have been will would could about into over after than then "
             "also more most such which what when where while there these those its it's the and for are "
             "was were has had not but one two all any each other some said says according reportedly report "
             "source".split())
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


def ask_text(prompt, runner=subprocess.run):
    # no tools, no MCP, no user settings or hooks: the model reads untrusted text and may only answer
    r = runner(["claude", "-p", "--model", MODEL, "--tools", "", "--restricted", "--strict-mcp-config",
                "--no-session-persistence", "--output-format", "json"],
               input=prompt, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"claude exited {r.returncode}: {r.stderr[-400:]}")
    return json.loads(r.stdout)["result"]


def ask_claude(prompt, runner=subprocess.run):
    text = ask_text(prompt, runner)
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        raise RuntimeError("no JSON array in reply")
    return json.loads(m.group(0))


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
    return apply(stories, ask_claude(PROMPT.format(stories=block), runner))


def request(stories):
    """The prompt a Claude session answers when no headless call is available."""
    for i, s in enumerate(stories):
        s["id"] = i
    block = "\n\n".join(f"id: {i}\noutlet: {s['source']}\ntitle: {s['title']}\nsummary: {s.get('summary', '')[:500]}"
                        for i, s in enumerate(stories))
    return PROMPT.format(stories=block)


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
            # a logo for an organisation the source never names would put a company on a story it is not in
            src = (s["title"] + " " + s.get("summary", "")).lower()
            orgs = c.get("orgs") if isinstance(c.get("orgs"), list) else []
            s["orgs"] = [o for o in orgs if isinstance(o, str) and o.strip() and o.lower() in src][:3]
            # the same holds for a face: only a person the source names may be pictured
            if s.get("person") and s["person"].split()[-1].lower() not in src:
                s["person"] = ""
            # a big figure the reader cannot find in the headline or dek reads as the story's number when it is not
            seen = s["headline"] + " " + s["dek"]
            fig = s["figure"]
            if fig and not ((_numbers(fig) & _numbers(seen)) if _numbers(fig) else fig.lower() in seen.lower()):
                s["figure"] = ""
    return rejected
