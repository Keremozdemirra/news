"""Silence alarms: what went quiet, found from what the queue and state files say was sent, not from run results.

A run can be green and send nothing (a platform skipping every post, a story slot that never fires, a Short that
never gets built). 2026-11-27: stories stopped for hours and Facebook went silent for hours, and nobody knew until
the owner looked. status.problems() calls problems() here; a problem that lasts HOLD_MINUTES reaches the one
"Desk health" issue, with no new channel and no new secret.

All times are UTC. The desk only expects posts inside the DAY window, so the night never alarms.
"""
import re
from datetime import timedelta

from . import desk

DAY = (8, 22)               # hours of the UTC day when every feed platform is expected to send
STORY_FROM = 9              # stories are expected from this hour (the first slot is 06:15, then 08:30, 09:30)
STORY_GAP_HOURS = 3         # the widest planned gap between story slots is 2.5 h
SHORT_BY_HOUR = 14          # a Short is due by now when growth.shorts is on
# longest quiet stretch inside the day window before an alarm; measured on 2026-11-26/27: Instagram's and Threads'
# widest gap was 1.5 h, Telegram's 3 h, Bluesky's 2.2 h; Facebook sends two to four a day from 10:00
SILENCE_HOURS = {"instagram": 3, "threads": 3, "bluesky": 3, "telegram": 3.5, "facebook": 8}
DUP_HOURS = 48
EXPIRY_WARN_DAYS = 14
FEED_KINDS = (None, "", "news", "data")


def _cfg():
    return desk.CONFIG.get("liveness") or {}


def _t(text):
    return desk._stamp(text or "")


def last_sends(rows):
    """{channel: newest send time} from the posts: each platform slot with an id, Instagram feed posts, stories."""
    out = {}

    def see(name, stamp):
        t = _t(stamp)
        if t and (name not in out or t > out[name]):
            out[name] = t
    for p in rows:
        for name, slot in (p.get("platforms") or {}).items():
            if slot.get("id"):
                see(name, slot.get("at"))
        if p.get("kind") == "story":
            if p.get("status") == "published":
                see("stories", p.get("published"))
            fb = p.get("fb_story") or {}
            if fb.get("id"):
                see("stories", fb.get("at"))
        elif p.get("status") == "published" and p.get("media_id", True) and p.get("published"):
            see("instagram", p["published"])
    return out


def _window_start(t):
    return t.replace(hour=DAY[0], minute=0, second=0, microsecond=0)


def _cooling(name):
    if name == "instagram":
        return desk.cooldown_until()
    return desk.platform_cooldown(name)


def silent_platforms(rows, t):
    """[(key, message)] for every enabled channel that has not sent for longer than its limit, inside the day window."""
    if not DAY[0] <= t.hour < DAY[1]:
        return []
    last, out = last_sends(rows), []
    limits = {**SILENCE_HOURS, **(_cfg().get("silence_hours") or {})}
    names = ["instagram"] + [n for n, on in (desk.CONFIG.get("platforms") or {}).items() if on]
    for name in names:
        limit = limits.get(name)
        # a channel with no send for a week is dead or off, not quiet: the credential and error alarms own that case
        if not limit or name not in last or t - last[name] > timedelta(days=7):
            continue
        # a quiet night is not silence: count from the start of today's window at the earliest
        since = max(last.get(name) or _window_start(t), _window_start(t))
        quiet = t - since
        if quiet <= timedelta(hours=limit):
            continue
        cooling = _cooling(name)
        if cooling and quiet <= timedelta(hours=2 * limit):
            continue  # a known cooldown explains it; twice the limit does not
        ago = f"{quiet.total_seconds() / 3600:.0f} hours"
        what = f"last at {last[name]:%d %b %H:%M} UTC"
        out.append((f"silent-{name}", f"{name.capitalize()} has sent nothing for {ago} ({what})"
                    + (f"; cooling down until {cooling:%H:%M} UTC" if cooling else "") + "."))
    return out


def silent_stories(rows, t):
    if not STORY_FROM <= t.hour < DAY[1] + 1:
        return []
    last = last_sends(rows).get("stories")
    if last is None or t - last > timedelta(days=7):
        return []  # a desk that never made a story, or stopped on purpose a week ago, has not just lost one
    start = t.replace(hour=STORY_FROM - 3, minute=0, second=0, microsecond=0)  # the 06:15 slot counts
    since = max(last or start, start)
    gap = t - since
    if gap <= timedelta(hours=_cfg().get("story_gap_hours", STORY_GAP_HOURS)):
        return []
    cooling = desk.cooldown_until()
    fb_only = " Instagram is cooling down." if cooling else ""
    return [("silent-stories", f"No story went out for {gap.total_seconds() / 3600:.0f} hours (last "
             + f"{last:%d %b %H:%M} UTC" + f").{fb_only}")]


def silent_shorts(t, state=None):
    """growth.shorts is on and it is past SHORT_BY_HOUR with no Short attempted today."""
    if not desk.growth("shorts") or t.hour < _cfg().get("short_by_hour", SHORT_BY_HOUR):
        return []
    st = state if state is not None else desk._load(desk.STATE / "shorts.json", {})
    day = f"{t:%Y-%m-%d}"
    at = [v.get("at") or "" for v in (st.get("attempted") or {}).values()]
    if any(a.startswith(day) for a in at):
        return []
    if not any((_t(a) or t - timedelta(days=99)) > t - timedelta(days=7) for a in at):
        return []  # nothing uploaded this week: switched off or never connected, not a day that went quiet
    why = st.get("build_error") if st.get("build_date") == day else ""
    return [("silent-shorts", f"No YouTube Short has been uploaded today (it is {t:%H:%M} UTC)"
             + (f"; last build error: {re.sub(r'[^ -~]', '', str(why))[:120]}" if why else "") + ".")]


def norm(headline):
    return re.sub(r"[^a-z0-9]+", " ", (headline or "").lower()).strip()


def duplicates(rows, t):
    """[(key, message)] for one headline sent twice to one platform inside DUP_HOURS: the duplicate check let it by."""
    cut = t - timedelta(hours=DUP_HOURS)
    seen, out = {}, []
    for p in rows:
        if p.get("kind") not in FEED_KINDS or p.get("kind") == "data" or not p.get("headlines"):
            continue
        head = norm(p["headlines"][0])
        if not head:
            continue
        sent = {n: s.get("at") for n, s in (p.get("platforms") or {}).items() if s.get("id")}
        if p.get("status") == "published" and p.get("media_id", True):
            sent["instagram"] = p.get("published")
        for name, at in sent.items():
            when = _t(at)
            if not when or when < cut:
                continue
            key = (name, head)
            if key in seen and seen[key] != p["id"]:
                out.append((f"dup-{name}", f"{name.capitalize()} got the same headline twice ({seen[key]} and {p['id']}): "
                            f"{p['headlines'][0][:70]!r}."))
            seen[key] = p["id"]
    return list({k: (k, m) for k, m in out}.values())


def token_dates(today=None):
    """[(key, message)] for a recorded token expiry (desk.json token_expiry) inside EXPIRY_WARN_DAYS, expired included."""
    today = today or desk.now().date()
    out = []
    for name, day in (desk.CONFIG.get("token_expiry") or {}).items():
        try:
            left = (desk.datetime.fromisoformat(day).date() - today).days
        except ValueError:
            out.append((f"token-{name}", f"The {name} token expiry date {day!r} in desk.json is not a date."))
            continue
        if left <= EXPIRY_WARN_DAYS:
            out.append((f"token-{name}", f"The {name} token {'expired ' + day if left < 0 else 'expires ' + day + f' ({left} days)'}. "
                        f"Make a new long-lived token, store it with `gh secret set`, and update token_expiry in desk.json."))
    return out


def withdrawn_live(rows, shorts=None):
    """[(key, message)] for a withdrawn article that is still up somewhere. Two kinds: a correction that withdraws it
    (corrections.json: "retracted", every platform) and a social takedown (`aidaily withdraw`: "withdrawn", the site
    article stays, Instagram is archived by the owner in the app). A copy is cleared by "removed" on its slot."""
    out = []
    shorts = (shorts or {}).get("attempted") or {}
    for p in rows:
        if not (p.get("retracted") or p.get("withdrawn")):
            continue
        where = [n for n, s in (p.get("platforms") or {}).items() if s.get("id") and not s.get("removed")]
        if p.get("retracted") and p.get("status_was") == "published" and p.get("media_id") and not p.get("removed"):
            where.append("instagram")
        short = shorts.get(p["id"]) or {}
        if short.get("video_id") and not short.get("removed"):
            where.append("youtube")
        if where:
            out.append((f"withdrawn-{p['id']}", f"Withdrawn article {p['id']} is still up on {', '.join(where)}: take it down there "
                        "(`aidaily withdraw` does the mirrored platforms, YouTube Studio the Short, the app Instagram), "
                        "then set \"removed\" on its slot."))
    return out


def problems(t=None, rows=None):
    """Every silence alarm now: [(key, message)]."""
    t = t or desk.now()
    rows = rows if rows is not None else [p for p, _ in desk.posts()]
    return (silent_platforms(rows, t) + silent_stories(rows, t) + silent_shorts(t) + duplicates(rows, t) + token_dates(t.date())
            + withdrawn_live(rows, desk._load(desk.STATE / "shorts.json", {})))
