# boardread desk

An Instagram account for the business, markets, politics, tech and AI news a consultant or manager needs, run by GitHub Actions. Every hour it fetches 138 news feeds from newsrooms on six continents and ranks the stories. It keeps each relevant story above the importance bar that is under a day old and has not been posted yet. It writes the copy, checks it against the sources, and queues one post per story: a photo card, then a slide with the report. Each run opens one issue in this repository listing its posts. Posts go out 20 minutes apart, the first two hours after queuing, unless the owner vetoes them.

## The day

| Time (UTC) | Workflow | What happens |
|---|---|---|
| every 30 min | `daily` | fetch, rank, keep new important stories, copy, check, render, queue in `queue/<id>/`, open the veto issue |
| every 5 min | `publish` | post the oldest due post, one per run, unless vetoed |
| every 5 min | `engage` | DM the sources to anyone who comments SOURCE; answer other new comments, at most 20 a day |
| Monday 06:00 | `weekly` | pull every platform's numbers; set category weights and learned timing; extend the token |
| after each run | `site` | rebuild the news site from the published posts |

GitHub may start a scheduled run up to half an hour late.

## Stopping it

- One post: comment `veto 2` on its run's issue (or `veto 1, 3`, or `veto all`). Only the repository owner's comments count.
- A whole run: close its issue.
- Everything: commit a file named `PAUSED` at the root, or set the repository variable `DESK_PAUSED` to `1`. The repository ships with `PAUSED` in place; deleting it is the go-live step.

## Watching it

- `/status/` on the site (and `/status/status.json`): last run of every workflow, last post and today's count per platform, cooldowns, the queue, and the last day's errors as HTTP status and platform code. The site rebuilds it at least hourly; if the page says it has not been rebuilt for a while, the desk has stopped.
- One issue, "Desk health: needs attention", opened by the `publish` run when something will not fix itself (a platform rejecting its token, posts stuck, a workflow failing again and again, no tick running, the site hours behind). A problem must last 20 minutes first; the issue gets one comment when the list changes and closes itself after 30 clear minutes. Cooldowns and single failed runs never open it.
- Every Monday the `weekly` run opens "Weekly health" with the week's posts per platform, failures and token dates, and closes last week's.
- Duplicates: before any send, Instagram, Threads, Facebook and Bluesky are checked for the post already being live, so a lost status commit is recorded and the post stays single. Telegram cannot be read back by a bot; there the marker written before the send is the only guard.

## What keeps it safe

- The two model calls (copy and comment replies) run `claude -p` with no tools, no MCP and no user settings. They read untrusted text and can only return text.
- Fixed code checks that text before anything is public. Every number must appear in the source. Sentences that read as commentary are rejected. A big figure on a card must also appear in its headline or dek. Stories about deaths, violence or abuse are skipped. A reply with a link, a mention, a number missing from the post, or more than 200 characters is dropped.
- The only secret that can post is `IG_TOKEN`, and it can post to one Instagram account. It travels in a request header and is scrubbed from every error message.
- No daily quota. Every story at or above `site_min_score` (8.0), under 24 hours old and carried by a newsroom or lab, is queued in one of two tiers. The most important take Instagram's remaining room for the day (the cap in `state/pace.json`, at most as many as fit the schedule, 45 minutes apart, none more than 2 hours ahead). Every other story is published to the website at once (status `web`). A web story at or above `social_min_score` (8.8) also goes to Bluesky and Threads, one per `publish` run and at least `social_spacing_minutes` (20) apart. Facebook and Telegram only get what Instagram published. An Instagram post that waits longer than 12 hours, for instance through a block, becomes a web story and never goes to Instagram. A story is not posted again within 3 days, even when a later run clusters it under a different link. 20 replies a day.
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

## Growth loop

Each Monday `python3 -m aidaily insights` reads per-post numbers from every connected platform into `post.json` (`metrics`) and writes `state/insights/<week>.json`. Each number is compared with that platform's 30-day median. The results feed three things, each inside fixed limits: category weights for ranking, the Telegram digest hour, and quiet hours for web-tier social posts. When per-post Instagram sends fall, the volume ramp holds. `python3 -m aidaily seo _site` audits a build for Google; the site workflow prints it on every run. Plans, the legal reasoning and the owner's checklists are in `brand/growth/`.

## Secrets and settings

| Name | Kind | Used by |
|---|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | secret, from `claude setup-token` | daily, engage |
| `IG_TOKEN` | secret, long-lived Instagram User token | publish, engage, weekly |
| `IG_USER_ID` | secret, the account's Instagram user id | publish, engage, weekly |
| `DESK_PAUSED` | variable, optional | all |

Instagram fetches each JPEG from its raw URL on the `media` branch, which is why the repository is public. A reader who comments SOURCE gets one DM with the story's page; that needs the `instagram_business_manage_messages` permission. The repository is named `news` because GitHub serves it under the owner's Pages domain, keremozdemir.de/news, until the site moves to boardread.news (next section).

## Files

| Path | What it does |
|---|---|
| `aidaily/feeds.py`, `rank.py` | fetch 138 feeds, cluster items into stories (weighting the words few titles share), score them by newsrooms, recency and hard-news terms |
| `aidaily/copy.py` | the copy prompt and the checks against the source text |
| `aidaily/templates.py`, `render.py` | 1080x1350 cards and the daily cover, rendered by headless Chrome, saved as JPEG |
| `aidaily/desk.py` | queue, publish, replies, token check |
| `aidaily/insights.py` | the weekly numbers from Instagram, Threads, Facebook, Bluesky and Telegram, and the guarded feedback into weights and timing |
| `aidaily/seo.py`, `distribution.py` | the SEO audit of a built site; the Telegram pinned post and the Bluesky custom feed |
| `aidaily/instagram.py` | the Instagram API calls (graph.facebook.com with a unified-login system-user token, v27.0) |
| `aidaily/github.py` | the veto issues |
| `aidaily/status.py` | the status page, `status.json`, the health and weekly issues |
| `aidaily/redact.py` | removes secrets from every saved file and every printed line |
| `desk.json` | caps, window, hashtags, skipped topics |
| `aidaily/site.py`, `assets-site/` | the news site (front page, stories, topics, week, archive, search, static pages, RSS, sitemaps); one address setting, `site_url` |
| `scripts/media.sh` | the `media` branch: one commit of the JPEGs Instagram fetches and the thumbnails the pages show, pruned by age |
| `queue/`, `state/` | every post, reply and weekly number, committed by the workflows |

## Local run

```bash
python3 -m aidaily daily            # needs a logged-in claude CLI; queues locally, posts nothing
python3 -m aidaily publish --dry    # shows what would go out
./check.sh                          # tests, prose, secrets
```

## Moving the site to boardread.news

Two settings in `desk.json` and nothing else decide where the site lives and what the posts print:

| Setting | Now | At the cut-over | What it drives |
|---|---|---|---|
| `site_url` | `https://keremozdemir.de/news` | `https://boardread.news` | every page's links and canonical URLs, the base path (`/news` or none), feeds, sitemaps, og images, the story link in platform posts, DMs and replies (`desk.story_url`) |
| `brand_domain` | `boardread.news` | unchanged | the domain printed on card footers, detail slides, the reel end frame and the reel caption |

Steps, in this order:

1. Porkbun DNS for boardread.news: four `A` records on the apex (185.199.108.153, 185.199.109.153, 185.199.110.153, 185.199.111.153), optionally the four `AAAA` records (2606:50c0:8000::153, 8001::153, 8002::153, 8003::153), and `CNAME www` to `keremozdemir.github.io`. Check against GitHub's Pages custom-domain docs before entering them.
2. Wait until `dig boardread.news` answers from public resolvers.
3. One commit: `site_url` to `https://boardread.news`, add a file named `CNAME` containing `boardread.news` to `assets-site/` (the build copies it to the site root), push. The `site` workflow rebuilds at the root. Then in the repository's Pages settings set the custom domain and tick Enforce HTTPS once the certificate is issued.
4. Old links: with a custom domain on the project, GitHub redirects the old project address. If keremozdemir.de/news/... does not redirect, run `python3 -m aidaily redirects <dir>` after step 3 and publish the `<dir>/news/...` stubs from the keremozdemir.de repository. Feeds cannot be stubbed; subscribers need the new feed URL.
5. Update by hand: the profile links on every platform (`brand/PROFILE.md` lists them), the Bluesky starter pack and the Telegram channel description.

`DESK_SITE_URL=http://localhost:8000 python3 -m aidaily site` builds the same pages for a local address without touching `desk.json`.
