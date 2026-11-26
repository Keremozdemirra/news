# loopbrief desk

An Instagram account for AI news that runs itself on GitHub Actions. Every two hours it fetches 48 news sources, ranks the stories, writes the copy and checks it against the sources. It then queues up to three posts, one story each: the story's card, then a slide with the report. Each run opens one issue in this repository listing its posts. A post goes out two hours after it is queued, an hour apart from the next, unless the owner vetoes it.

## The day

| Time (UTC) | Workflow | What happens |
|---|---|---|
| 04:00 to 20:00, every 2 h | `daily` | fetch, rank, copy, check, render, queue up to 3 posts in `queue/<id>/`, open the veto issue |
| every 20 min | `publish` | post the oldest due post, one per run, unless vetoed |
| hourly | `engage` | answer new comments on the last 7 days of posts, at most 20 a day |
| Monday 06:00 | `weekly` | pull reach, shares and saves; set category weights; extend the token |

GitHub may start a scheduled run up to half an hour late.

## Stopping it

- One post: comment `veto 2` on its run's issue (or `veto 1, 3`, or `veto all`). Only the repository owner's comments count.
- A whole run: close its issue.
- Everything: commit a file named `PAUSED` at the root, or set the repository variable `DESK_PAUSED` to `1`. The repository ships with `PAUSED` in place; deleting it is the go-live step.

## What keeps it safe

- The two model calls (copy and comment replies) run `claude -p` with no tools, no MCP and no user settings. They read untrusted text and can only return text.
- Fixed code checks that text before anything is public. Every number must appear in the source. Sentences that read as commentary are rejected. A big figure on a card must also appear in its headline or dek. Stories about deaths, violence or abuse are skipped. A reply with a link, a mention, a number missing from the post, or more than 200 characters is dropped.
- The only secret that can post is `IG_TOKEN`, and it can post to one Instagram account. It travels in a request header and is scrubbed from every error message.
- Caps: 12 posts a day, an hour apart, none scheduled more than 4 hours past its veto window; 20 replies a day. A story is not posted again within 3 days, even when a later run clusters it under a different link.
- It never follows, likes, comments elsewhere or sends DMs: Instagram's terms forbid automated interaction.

## Secrets and settings

| Name | Kind | Used by |
|---|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | secret, from `claude setup-token` | daily, engage |
| `IG_TOKEN` | secret, long-lived Instagram User token | publish, engage, weekly |
| `IG_USER_ID` | secret, the account's Instagram user id | publish, engage, weekly |
| `DESK_PAUSED` | variable, optional | all |

Instagram fetches each JPEG from its raw URL in this repository, which is why the repository is public.

## Files

| Path | What it does |
|---|---|
| `aidaily/feeds.py`, `rank.py` | fetch 48 sources, cluster items into stories, score them |
| `aidaily/copy.py` | the copy prompt and the checks against the source text |
| `aidaily/templates.py`, `render.py` | 1080x1350 cards and the daily cover, rendered by headless Chrome, saved as JPEG |
| `aidaily/desk.py` | queue, publish, replies, weekly weights, token check |
| `aidaily/instagram.py` | the Instagram API calls (graph.instagram.com, v27.0) |
| `aidaily/github.py` | the veto issues |
| `desk.json` | caps, window, hashtags, skipped topics |
| `queue/`, `state/` | every post, reply and weekly number, committed by the workflows |

## Local run

```bash
python3 -m aidaily daily            # needs a logged-in claude CLI; queues locally, posts nothing
python3 -m aidaily publish --dry    # shows what would go out
./check.sh                          # tests, prose, secrets
```
