"""The desk's health, in public: /status/ on the site, status.json beside it, and one GitHub issue when
something needs the owner.

Everything here is built from what the repository already shows (queue/, state/, the Actions run list) and is
safe to publish: an error is never quoted, only classified ("HTTP 400, Meta code 190: credential expired"),
and no secret, token fingerprint or personal detail is written out.

  python3 -m aidaily status DIR     status.json and index.html into DIR (the site build calls it for _site/status)
  python3 -m aidaily health         the problems now; opens, updates or closes the one "Desk health" issue
  python3 -m aidaily health --weekly   the Monday report issue

The issue is the owner's only alarm, so it is quiet by design: a problem has to last HOLD_MINUTES before the issue
opens, the issue gets one comment when the set of problems changes (an edit alone sends no e-mail), and it closes
itself once everything has been clear for CLEAR_MINUTES. A GitHub outage or one failed run never reaches it.
"""
import json
import os
import re
import subprocess
import urllib.request
from datetime import datetime, timedelta, timezone
from html import escape as E
from pathlib import Path

from . import desk, github

WORKFLOWS = ("tick", "daily", "publish", "engage", "weekly", "site", "crosspost", "ci")
DESK_WORKFLOWS = ("daily", "publish", "engage", "weekly", "site", "crosspost")
HOLD_MINUTES = 20
CLEAR_MINUTES = 30
ISSUE_TITLE = "Desk health: needs attention"
WEEKLY_TITLE = "Weekly health"
BOT = "github-actions[bot]"
STALE_SITE_HOURS = 3
STUCK_HOURS = 2

# what an error is, without its text: Meta codes from developers.facebook.com/docs/graph-api/guides/error-handling
# and the Instagram publishing error codes (developers.facebook.com/docs/instagram-platform/instagram-graph-api/
# reference/error-codes), read 2026-11-26
LABELS = {"190": "credential expired or revoked", "4": "app request limit", "17": "account request limit",
          "32": "page request limit", "613": "rate limit", "10": "permission missing", "200": "permission missing",
          "100": "invalid parameter", "2207051": "action blocked", "2207052": "image could not be fetched",
          "2207003": "image download timed out", "368": "temporarily blocked", "9007": "media not ready"}


def now():
    return desk.now()


def iso(t):
    return t.isoformat(timespec="seconds") if t else None


def classify(error):
    """A public-safe description of an error string: HTTP status, platform code, a known label. Never the text."""
    text = str(error or "")
    if text.startswith("manual:"):
        return text[:120]
    parts = []
    m = re.search(r"HTTP (\d{3})", text)
    if m:
        parts.append(f"HTTP {m.group(1)}")
    sub = re.search(r'"error_subcode":\s*(\d+)', text)
    code = re.search(r'"(?:code|error_code)":\s*(\d+)', text)
    label = ""
    for c in (sub and sub.group(1), code and code.group(1)):
        if c and c in LABELS and not label:
            label = LABELS[c]
    if code:
        parts.append(f"code {code.group(1)}" + (f"/{sub.group(1)}" if sub and sub.group(1) != "0" else ""))
    if not label:
        for rx, name in ((r"timed? ?out", "timed out"), (r"Temporary failure|Name or service|resolve", "network"),
                         (r"RateLimit|\bHTTP 429\b|Too Many Requests", "rate limit"),
                         (r"ExpiredToken|InvalidToken|AuthenticationRequired|\bUnauthorized\b|\bHTTP 401\b", "credential rejected"),
                         (r"not ready after", "media not ready"), (r"HTTP 5\d\d", "platform error"),
                         (r"already attempted|result is unknown", "earlier send unconfirmed")):
            if re.search(rx, text, re.I):
                label = name
                break
    return " · ".join(parts + [label or "other error"])


# reading the repository

def _platform_names():
    from . import platforms
    return platforms.NAMES


def _today_count(rows, day):
    return sum(1 for r in rows if (r or "")[:10] == day)


def _quarantined():
    """Articles the site build held back (empty body, empty dek, template leak); empty unless this process just built the site."""
    from . import site
    return site.QUARANTINE


def snapshot(runs=None):
    """Everything the page and the health check read, from queue/ and state/ (and the run list when given)."""
    t, day = now(), now().strftime("%Y-%m-%d")
    cut = t - timedelta(hours=24)
    allp = [p for p, _ in desk.posts()]
    by_status = {}
    for p in allp:
        by_status[p.get("status", "?")] = by_status.get(p.get("status", "?"), 0) + 1
    feed = [p for p in allp if p.get("kind") != "story"]
    ig = [p for p in feed if p.get("status") == "published" and p.get("published")]
    last = max(ig, key=lambda p: p["published"], default=None)
    errors = []
    for p in allp:
        stamp = desk._stamp(p.get("attempted") or p.get("published") or p.get("created") or "")
        if p.get("error") and p.get("status") in ("failed", "queued") and stamp and stamp > cut:
            errors.append({"at": iso(stamp), "post": p["id"], "where": "instagram", "summary": classify(p["error"])})
        for name, slot in (p.get("platforms") or {}).items():
            st = desk._stamp(slot.get("attempted") or slot.get("at") or "")
            if slot.get("error") and st and st > cut:
                errors.append({"at": iso(st), "post": p["id"], "where": name, "summary": classify(slot["error"])})
            ck = desk._stamp(slot.get("checked") or "")
            if slot.get("check_error") and ck and ck > cut:
                errors.append({"at": iso(ck), "post": p["id"], "where": name, "check": True,
                               "summary": "duplicate check failed, not sent · " + classify(slot["check_error"])})
    errors.sort(key=lambda e: e["at"], reverse=True)
    plats = {}
    for name in _platform_names():
        sent = [((p.get("platforms") or {}).get(name) or {}) for p in allp]
        done = [s for s in sent if s.get("id")]
        latest = max(done, key=lambda s: s.get("at", ""), default=None)
        cd = desk._load(desk.STATE / f"cooldown-{name}.json", {})
        until = desk.platform_cooldown(name)
        plats[name] = {
            "enabled": bool(desk.CONFIG.get("platforms", {}).get(name)),
            "last_post": {"at": latest.get("at"), "url": latest.get("url", "")} if latest else None,
            "today": _today_count([s.get("at") for s in done], day),
            "sent_24h": sum(1 for s in done if (desk._stamp(s.get("at", "")) or cut) > cut),
            "errors_24h": sum(1 for e in errors if e["where"] == name),
            "cooldown_until": iso(until),
            "cooldown_kind": ("credential rejected" if cd.get("auth") else "rate limit") if until else None,
            "cooldown_reason": classify(cd.get("error")) if until else None,
        }
    cd = desk._load(desk.STATE / "cooldown.json", {})
    until = desk.cooldown_until()
    due = [p for p in allp if p.get("status") == "queued" and desk._stamp(p.get("publish_after", "")) and desk._stamp(p["publish_after"]) <= t]
    replies = desk._load(desk.STATE / "replies.json", {})
    snap = {
        "generated": iso(t),
        "state_as_of": _head_time(),
        "paused": desk.paused() or os.environ.get("DESK_PAUSED") == "1",
        "instagram": {
            "last_post": {"at": last["published"], "url": last.get("permalink", "")} if last else None,
            "today": _today_count([p["published"] for p in ig], day),
            "published_24h": desk.published_last_24h(),
            "daily_cap": desk.daily_cap(),
            "cooldown_until": iso(until),
            "cooldown_reason": classify(cd.get("error")) if until else None,
        },
        "platforms": plats,
        "queue": {"queued": by_status.get("queued", 0), "due": len(due), "held": by_status.get("held", 0),
                  "failed": by_status.get("failed", 0), "web": by_status.get("web", 0), "by_status": by_status,
                  "oldest_due": min((p["publish_after"] for p in due), default=None)},
        "today": {"date": day, "replies": (replies.get("days") or {}).get(day, 0), "web": _today_count(
            [p.get("published") for p in feed if p.get("status") == "web"], day)},
        "errors": errors[:20],
        "tokens": dict(desk.CONFIG.get("token_expiry") or {}),
        "workflows": workflows(runs) if runs is not None else {},
        "quarantined": list(_quarantined()),
    }
    return snap


def _head_time():
    try:
        return subprocess.run(["git", "log", "-1", "--format=%cI"], cwd=desk.HERE, capture_output=True, text=True,
                              timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def fetch_runs(per=30):
    """{workflow name: [runs newest first]} from the Actions API with the job's own token, or None without one."""
    if not github.enabled():
        return None
    out = {}
    for name in WORKFLOWS:
        try:
            got = github._call("GET", f"actions/workflows/{name}.yml/runs?per_page={per}")
        except Exception as e:  # noqa: BLE001  a workflow that cannot be read is shown as unknown
            print(f"runs of {name}: {str(e)[:120]}")
            continue
        out[name] = [{"status": r.get("status"), "conclusion": r.get("conclusion"), "created": r.get("created_at"),
                      "url": r.get("html_url", "")} for r in got.get("workflow_runs", [])]
    return out


def workflows(runs):
    t = now()
    rows = {}
    for name, rs in (runs or {}).items():
        done = [r for r in rs if r["status"] == "completed"]
        ok = next((r for r in done if r["conclusion"] == "success"), None)
        streak = 0
        for r in done:
            if r["conclusion"] != "failure":
                break
            streak += 1
        rows[name] = {
            "last_run": rs[0]["created"] if rs else None,
            "last_status": (rs[0]["conclusion"] or rs[0]["status"]) if rs else None,
            "last_url": rs[0]["url"] if rs else "",
            "last_success": ok["created"] if ok else None,
            "failures_6h": sum(1 for r in done if r["conclusion"] == "failure"
                               and (desk._stamp(r["created"] or "") or t) > t - timedelta(hours=6)),
            "failure_streak": streak,
            "active": any(r["status"] in ("queued", "in_progress", "waiting", "pending") for r in rs),
        }
    return rows


# what needs the owner

def problems(snap, live_site=None):
    """[(key, message)]: each a thing that will not fix itself. Cooldowns, one failed run or a paused desk are not."""
    out, t = [], now()
    if snap["paused"]:
        return out
    for name, p in snap["platforms"].items():
        if not p["enabled"]:
            continue
        # a rejection older than the platform's last good send is history: a renewed token clears the alarm at once
        good = desk._stamp((p["last_post"] or {}).get("at") or "")
        rejected = [e for e in snap["errors"] if e["where"] == name and "credential" in e["summary"]
                    and not (good and desk._stamp(e["at"]) <= good)]
        if p["cooldown_kind"] == "credential rejected" or rejected:
            if not p["cooldown_reason"] and rejected:
                p = {**p, "cooldown_reason": rejected[0]["summary"]}
            secret = {"threads": "THREADS_TOKEN", "facebook": "FB_PAGE_TOKEN", "bluesky": "BSKY_APP_PASSWORD",
                      "telegram": "TG_BOT_TOKEN"}.get(name, "its secret")
            out.append((f"auth-{name}", f"{name.capitalize()} rejects its credential ({p['cooldown_reason']}). Store a new "
                        f"{secret} with `gh secret set`; posting there resumes on the next run."))
        elif p["errors_24h"] >= 3 and not p["cooldown_until"]:
            out.append((f"errors-{name}", f"{name.capitalize()}: {p['errors_24h']} failed sends in 24 hours "
                        f"(latest: {next(e['summary'] for e in snap['errors'] if e['where'] == name)})."))
    q, ig = snap["queue"], snap["instagram"]
    if q["oldest_due"] and not ig["cooldown_until"]:
        waited = t - desk._stamp(q["oldest_due"])
        if waited > timedelta(hours=STUCK_HOURS):
            out.append(("stuck", f"{q['due']} post(s) due for {int(waited.total_seconds() // 3600)}h but not published, "
                        "and Instagram is not cooling down."))
    failed = [e for e in snap["errors"] if e["where"] == "instagram"]
    if failed:
        out.append(("ig-failed", f"{len(failed)} Instagram post(s) failed in 24 hours: "
                    + ", ".join(f"{e['post']} ({e['summary']})" for e in failed[:5]) + "."))
    for name, w in snap["workflows"].items():
        if name in DESK_WORKFLOWS and (w["failure_streak"] >= 3 or w["failures_6h"] >= 4):
            out.append((f"wf-{name}", f"The {name} workflow failed {max(w['failure_streak'], w['failures_6h'])} times "
                        f"recently ([latest run]({w['last_url']}))."))
    tick = snap["workflows"].get("tick")
    if tick is not None and not tick["active"]:
        out.append(("clock", "No tick run is queued or running, so nothing is scheduled. Start one: "
                    "`gh workflow run tick.yml --ref main`."))
    if live_site is not None:
        made = desk._stamp(live_site.get("generated", "")) if isinstance(live_site, dict) else None
        if made and t - made > timedelta(hours=STALE_SITE_HOURS):
            out.append(("site", f"The site has not been rebuilt since {made:%Y-%m-%d %H:%M} UTC."))
    # token dates are not repeated here: the Monday run already opens one reminder issue per token (desk.py)
    return out


def live_status():
    """The status.json the site serves now, or None when it cannot be read (a network blip is not a problem)."""
    url = desk.CONFIG["site_url"].rstrip("/") + f"/status/status.json?t={int(now().timestamp())}"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001
        return None


def _bot_issues(prefix, gh=github):
    rows = gh._call("GET", "issues?state=open&per_page=100")
    return [i for i in rows if (i.get("user") or {}).get("login") == BOT and i.get("title", "").startswith(prefix)
            and "pull_request" not in i]


def _issue_body(found, snap):
    lines = ["The desk found something that will not fix itself. This issue updates itself and closes when it is clear.", ""]
    lines += [f"- {msg}" for _, msg in found]
    lines += ["", f"Status page: {desk.CONFIG['site_url'].rstrip('/')}/status/", f"Checked {snap['generated']} UTC."]
    return "\n".join(lines)


def health(snap=None, live_site=None, gh=github):
    """Compares the problems now with state/health.json and acts on the one issue. Returns the active problems."""
    snap = snap or snapshot(fetch_runs())
    found = problems(snap, live_site)
    t = now()
    state = desk._load(desk.STATE / "health.json", {"since": {}, "issue": None, "reported": [], "clear_since": None})
    since = {k: state["since"].get(k, iso(t)) for k, _ in found}
    held = [(k, m) for k, m in found if t - desk._stamp(since[k]) >= timedelta(minutes=HOLD_MINUTES)]
    state["since"] = since
    keys = sorted(k for k, _ in held)
    if not gh.enabled():
        for _, m in found:
            print(f"health: {m}")
        desk._save(desk.STATE / "health.json", state)
        return found
    try:
        open_ = _bot_issues(ISSUE_TITLE, gh)
        if held:
            state["clear_since"] = None
            if not open_:
                state["issue"] = gh.open_issue(ISSUE_TITLE, _issue_body(held, snap))
                print(f"health: opened issue #{state['issue']}")
            else:
                num = open_[0]["number"]
                state["issue"] = num
                if keys != state.get("reported"):
                    gh._call("PATCH", f"issues/{num}", {"body": _issue_body(held, snap)})
                    new = [m for k, m in held if k not in state.get("reported", [])]
                    gone = [k for k in state.get("reported", []) if k not in keys]
                    note = "\n".join([f"New: {m}" for m in new] + ([f"Cleared: {', '.join(gone)}"] if gone else []))
                    if note:
                        gh._call("POST", f"issues/{num}/comments", {"body": note})
            state["reported"] = keys
        elif open_:
            state["clear_since"] = state.get("clear_since") or iso(t)
            if t - desk._stamp(state["clear_since"]) >= timedelta(minutes=CLEAR_MINUTES):
                for i in open_:
                    gh.comment(i["number"], f"All clear since {state['clear_since']} UTC.", close=True)
                state.update(issue=None, reported=[], clear_since=None)
                print("health: all clear, issue closed")
        else:
            state.update(reported=[], clear_since=None)
    except RuntimeError as e:  # GitHub itself unreachable: say so in the log, never fail the run over it
        print(f"health: issue not updated: {str(e)[:160]}")
    desk._save(desk.STATE / "health.json", state)
    for _, m in found:
        print(f"health: {m}")
    if not found:
        print("health: nothing needs attention")
    return found


def weekly(gh=github, runs=None, meta_expiry=None):
    """The Monday report: a week of posts and failures in one issue; last week's report is closed."""
    t = now()
    cut = t - timedelta(days=7)
    if runs is None:
        runs = fetch_runs(per=100) or {}
    snap = snapshot(runs)
    allp = [p for p, _ in desk.posts()]
    ig = sum(1 for p in allp if p.get("status") == "published" and p.get("kind") != "story"
             and (desk._stamp(p.get("published", "")) or cut) > cut)
    web = sum(1 for p in allp if p.get("status") == "web" and (desk._stamp(p.get("published", "")) or cut) > cut)
    per = {n: sum(1 for p in allp if ((p.get("platforms") or {}).get(n) or {}).get("id")
                  and (desk._stamp(p["platforms"][n].get("at", "")) or cut) > cut) for n in _platform_names()}
    lines = [f"Week to {t:%Y-%m-%d}.", "", "| | posts, 7 days |", "|---|---|", f"| Instagram | {ig} |"]
    lines += [f"| {n.capitalize()} | {c} |" for n, c in per.items()] + [f"| site only (web tier) | {web} |", ""]
    if snap["workflows"]:
        lines += ["| workflow | last run | last success | failures in the last runs read |", "|---|---|---|---|"]
        for n, w in snap["workflows"].items():
            fails = sum(1 for r in (runs or {}).get(n, []) if r.get("conclusion") == "failure")
            lines.append(f"| {n} | {w['last_status'] or '-'} {w['last_run'] or ''} | {w['last_success'] or '-'} | {fails} |")
        lines.append("")
    found = problems(snap)
    lines += ["Open problems:" if found else "Open problems: none."] + [f"- {m}" for _, m in found]
    tokens = dict(snap["tokens"])
    for name, d in (meta_expiry or {}).items():
        end, data = (d or {}).get("expires"), (d or {}).get("data_access")
        tokens[f"{name} (Meta's debug_token)"] = (f"expires {end:%Y-%m-%d}" if end else "never expires") + (
            f", data access until {data:%Y-%m-%d}" if data else "")
        if end and (end - t) <= timedelta(days=10):
            lines.append(f"- The {name} token expires {end:%Y-%m-%d} by Meta's own record.")
    if tokens:
        lines += ["", "Token dates: " + ", ".join(f"{k} {v}" for k, v in tokens.items()) + "."]
    lines += ["", f"Status page: {desk.CONFIG['site_url'].rstrip('/')}/status/"]
    body = "\n".join(lines)
    if not gh.enabled():
        print(body)
        return body
    try:
        for i in _bot_issues(WEEKLY_TITLE, gh):
            gh.close(i["number"])
        gh.open_issue(f"{WEEKLY_TITLE} {t:%G-W%V}", body)
    except RuntimeError as e:
        print(f"weekly health: issue not opened: {str(e)[:160]}")
    print(body)
    return body


# the page

def _ago(stamp):
    """The time as text, with data-t so status.js can keep "x min ago" current between builds."""
    if not stamp:
        return '<span class="faint">never</span>'
    d = desk._stamp(stamp)
    return f'<time datetime="{E(iso(d))}" data-t="{E(iso(d))}">{d:%d %b %H:%M} UTC</time>' if d else E(str(stamp))


def _link(url, text):
    return f'<a href="{E(url)}" rel="noopener">{text}</a>' if url and url.startswith("https://") else text


def _md(text):
    """The issue's markdown (`code`, [text](https://...)) as HTML, everything else escaped."""
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", E(text))
    return re.sub(r"\[([^\]]+)\]\((https://[^)\s]+)\)", r'<a href="\2" rel="noopener">\1</a>', out)


def render(snap, found):
    ig, q = snap["instagram"], snap["queue"]
    rows = []
    for n, w in snap["workflows"].items():
        state = "running" if w["active"] and n == "tick" else (w["last_status"] or "-")
        rows.append(f'<tr><td>{E(n)}</td><td>{_ago(w["last_run"])}</td><td class="st-{E(state)}">{_link(w["last_url"], E(state))}</td>'
                    f'<td>{_ago(w["last_success"])}</td><td>{w["failures_6h"]}</td></tr>')
    wf = (f'<table><thead><tr><th>Workflow</th><th>Last run</th><th>Result</th><th>Last success</th><th>Failures, 6 h</th></tr></thead>'
          f'<tbody>{"".join(rows)}</tbody></table>') if rows else '<p class="meta">Run list not available in this build.</p>'
    prow = [f'<tr><td>Instagram</td><td>on</td><td>{_ago((ig["last_post"] or {}).get("at"))}</td><td>{ig["today"]}</td>'
            f'<td>{ig["published_24h"]} of {ig["daily_cap"]}</td>'
            f'<td>{(_ago(ig["cooldown_until"]) + " · " + E(ig["cooldown_reason"] or "")) if ig["cooldown_until"] else "-"}</td></tr>']
    for n, p in snap["platforms"].items():
        cd = (f'{E(p["cooldown_kind"])}, {_ago(p["cooldown_until"])}' if p["cooldown_until"] else "-")
        prow.append(f'<tr><td>{E(n.capitalize())}</td><td>{"on" if p["enabled"] else "off"}</td>'
                    f'<td>{_link((p["last_post"] or {}).get("url"), _ago((p["last_post"] or {}).get("at")))}</td>'
                    f'<td>{p["today"]}</td><td>{p["sent_24h"]}</td><td>{cd}</td></tr>')
    plat = (f'<table><thead><tr><th>Platform</th><th>Switch</th><th>Last post</th><th>Today</th><th>24 h</th><th>Cooldown</th></tr></thead>'
            f'<tbody>{"".join(prow)}</tbody></table>')
    prob = ("<ul>" + "".join(f"<li>{_md(m)}</li>" for _, m in found) + "</ul>") if found else "<p>Nothing needs attention.</p>"
    errs = ("<table><thead><tr><th>When</th><th>Post</th><th>Where</th><th>What</th></tr></thead><tbody>"
            + "".join(f'<tr><td>{_ago(e["at"])}</td><td>{E(e["post"])}</td><td>{E(e["where"])}</td><td>{E(e["summary"])}</td></tr>'
                      for e in snap["errors"]) + "</tbody></table>") if snap["errors"] else "<p>None in the last 24 hours.</p>"
    held = ("<h2>Held back from the site</h2><ul>" + "".join(f'<li>{E(h["id"])}: {E(", ".join(h["reasons"]))}</li>' for h in snap["quarantined"]) + "</ul>") if snap.get("quarantined") else ""
    state = "Stopped" if any(k == "clock" for k, _ in found) else "Running"
    head = ("Paused by the owner." if snap["paused"] else
            (f"{state}, {len(found)} {'thing needs' if len(found) == 1 else 'things need'} the owner." if found else f"{state}, nothing needs the owner."))
    return f"""<style>
.status{{max-width:56rem}}.status table{{width:100%;border-collapse:collapse;font:400 14px/1.45 var(--f);margin:0 0 24px}}
.status th,.status td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--rule,#ddd);vertical-align:top}}
.status th{{font-weight:600}}.status .st-failure{{color:#b3261e;font-weight:600}}.status .stale{{color:#b3261e;font-weight:600}}
.status .wrap{{overflow-x:auto}}.status h2{{margin-top:32px}}
@media (max-width:480px){{.status table{{font-size:13px}}.status th,.status td{{padding:6px 4px}}}}
</style>
<div class="status prose">
<p class="lede" id="overall">{E(head)}</p>
<p class="meta">Built {_ago(snap["generated"])} from the repository as of {_ago(snap["state_as_of"])}.
<span id="stale" class="stale" hidden>This page has not been rebuilt for a while, so the desk may have stopped.</span></p>
<h2>Open problems</h2>{prob}
<h2>Platforms</h2><div class="wrap">{plat}</div>
<h2>Queue</h2><p>{q["queued"]} queued, {q["due"]} due now, {q["held"]} held for review, {q["failed"]} failed, {q["web"]} site-only.
Replies today: {snap["today"]["replies"]}.</p>
<h2>Workflows</h2><div class="wrap">{wf}</div>
<h2>Errors, last 24 hours</h2><div class="wrap">{errs}</div>{held}
<p class="meta">Every figure comes from the public repository and its Actions runs. Errors are classified, never quoted.
Machine-readable: <a href="status.json">status.json</a>.</p>
</div>"""


SCRIPT = """// keeps the ages on /status/ current and flags a page the desk has stopped rebuilding
(function () {
  var made = document.querySelector('[data-t]');
  function span(m) {
    if (m < 90) return m + ' min';
    var h = Math.round(m / 60);
    return h < 48 ? h + ' h' : Math.round(h / 24) + ' days';
  }
  function ago(s) {
    var m = Math.round((Date.now() - Date.parse(s)) / 60000);
    if (isNaN(m)) return '';
    if (m < -1) return 'ends in ' + span(-m);  // a cooldown's end
    if (m < 1) return 'just now';
    return span(m) + ' ago';
  }
  document.querySelectorAll('[data-t]').forEach(function (el) {
    var a = ago(el.getAttribute('data-t'));
    if (a) el.title = el.textContent, el.textContent = a;
  });
  if (made && Date.now() - Date.parse(made.getAttribute('data-t')) > 3 * 3600 * 1000) {
    var s = document.getElementById('stale');
    if (s) s.hidden = false;
  }
})();
"""


def write(out_dir, snap=None, runs=None):
    """status.json and index.html into out_dir, the page in the site's own frame when the site was just built."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    snap = snap or snapshot(runs if runs is not None else fetch_runs())
    found = problems(snap)
    snap["problems"] = [m for _, m in found]
    (out / "status.json").write_text(json.dumps(snap, indent=1) + "\n")
    body = render(snap, found)
    try:
        from . import site
        assets = out.parent / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        (assets / "status.js").write_text(SCRIPT)
        html_ = site.page("Desk status · boardread.", site.pagehead("Desk status", "Is the desk running, and what did it post today.")
                          + body, "Whether the Boardread desk is running.", "/status/", noindex=True, scripts=("status",))
    except Exception as e:  # noqa: BLE001  the page must exist even if the site frame cannot be built
        print(f"status: plain page ({str(e)[:120]})")
        html_ = f'<!doctype html><meta charset="utf-8"><meta name="robots" content="noindex"><title>Desk status</title>{body}'
    (out / "index.html").write_text(html_)
    print(f"status: {len(found)} problem(s) -> {out}")
    return snap
