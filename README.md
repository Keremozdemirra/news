# boardread desk

An Instagram account for the business, markets, politics, tech and AI news a consultant or manager needs, run by GitHub Actions. Every hour it fetches 82 news feeds and ranks the stories. It keeps each relevant story above the importance bar that is under a day old and has not been posted yet. It writes the copy, checks it against the sources, and queues one post per story: a photo card, then a slide with the report. Each run opens one issue in this repository listing its posts. Posts go out 20 minutes apart, the first two hours after queuing, unless the owner vetoes them.

## The day

| Time (UTC) | Workflow | What happens |
|---|---|---|
| every 30 min | `daily` | fetch, rank, keep new important stories, copy, check, render, queue in `queue/<id>/`, open the veto issue |
| every 5 min | `publish` | post the oldest due post, one per run, unless vetoed |
| every 5 min | `engage` | DM the sources to anyone who comments SOURCE; answer other new comments, at most 20 a day |
| Monday 06:00 | `weekly` | pull reach, shares and saves; set category weights; extend the token |
| after each run | `site` | rebuild keremozdemir.de/news from the published posts |

GitHub may start a scheduled run up to half an hour late.

## Stopping it

- One post: comment `veto 2` on its run's issue (or `veto 1, 3`, or `veto all`). Only the repository owner's comments count.
- A whole run: close its issue.
- Everything: commit a file named `PAUSED` at the root, or set the repository variable `DESK_PAUSED` to `1`. The repository ships with `PAUSED` in place; deleting it is the go-live step.

## What keeps it safe

- The two model calls (copy and comment replies) run `claude -p` with no tools, no MCP and no user settings. They read untrusted text and can only return text.
- Fixed code checks that text before anything is public. Every number must appear in the source. Sentences that read as commentary are rejected. A big figure on a card must also appear in its headline or dek. Stories about deaths, violence or abuse are skipped. A reply with a link, a mention, a number missing from the post, or more than 200 characters is dropped.
- The only secret that can post is `IG_TOKEN`, and it can post to one Instagram account. It travels in a request header and is scrubbed from every error message.
- No daily quota: every story with a score of 7 or more, under 24 hours old and carried by a newsroom or lab, goes out. The ceiling is Meta's publishing limit (kept at 45 a day). Posts are 20 minutes apart and none is scheduled more than 6 hours past its veto window. A story is not posted again within 3 days, even when a later run clusters it under a different link. 20 replies a day.
- It never follows, likes, comments elsewhere or sends DMs: Instagram's terms forbid automated interaction.

## Growth switches

`desk.json` holds five switches under `growth`, all off. Each can be turned on alone; with all off the posts are what they were.

| Switch | Effect |
|---|---|
| `so_what` | the copy call returns one more field, a one-sentence consequence; fixed checks drop it if it adds a number or name, repeats the headline, gives advice or guesses. Shown on the detail slide under "What it means" and as one caption line |
| `send_prompt` | the closing caption line comes from the six approved `send_prompts`, picked by topic |
| `alt_text` | alt text on each carousel image: the headline on the card, headline and dek on the detail slide |
| `keyword_caption` | the company and person go into the first 125 characters when the headline lacks them; hashtags drop to the topic tag and `#news` |
| `daily_reel` | once a day, from `reel_hour` UTC, a 1080x1920 recap video of the day's top five posts, published as a Reel by the `publish` workflow (`aidaily reel due`, `build`, `send`); state in `state/reel.json`; never cross-posted |

`python3 scripts/growth_preview.py` writes `brand/preview/growth.html` with all five on, from real posts, without calling Instagram.

## Secrets and settings

| Name | Kind | Used by |
|---|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | secret, from `claude setup-token` | daily, engage |
| `IG_TOKEN` | secret, long-lived Instagram User token | publish, engage, weekly |
| `IG_USER_ID` | secret, the account's Instagram user id | publish, engage, weekly |
| `DESK_PAUSED` | variable, optional | all |

Instagram fetches each JPEG from its raw URL on the `media` branch, which is why the repository is public. A reader who comments SOURCE gets one DM with the story's page; that needs the `instagram_business_manage_messages` permission. The repository is named `news` because GitHub serves it under the owner's Pages domain, keremozdemir.de/news.

## Files

| Path | What it does |
|---|---|
| `aidaily/feeds.py`, `rank.py` | fetch 82 feeds, cluster items into stories, score them |
| `aidaily/copy.py` | the copy prompt and the checks against the source text |
| `aidaily/templates.py`, `render.py` | 1080x1350 cards and the daily cover, rendered by headless Chrome, saved as JPEG |
| `aidaily/desk.py` | queue, publish, replies, weekly weights, token check |
| `aidaily/instagram.py` | the Instagram API calls (graph.facebook.com with a unified-login system-user token, v27.0) |
| `aidaily/github.py` | the veto issues |
| `desk.json` | caps, window, hashtags, skipped topics |
| `aidaily/site.py` | the pages at keremozdemir.de/news: latest stories, one page per story, weekly issues, RSS |
| `scripts/media.sh` | the `media` branch: one commit of the JPEGs Instagram fetches and the thumbnails the pages show, pruned by age |
| `queue/`, `state/` | every post, reply and weekly number, committed by the workflows |

## Local run

```bash
python3 -m aidaily daily            # needs a logged-in claude CLI; queues locally, posts nothing
python3 -m aidaily publish --dry    # shows what would go out
./check.sh                          # tests, prose, secrets
```
