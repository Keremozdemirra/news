# 30-day organic growth plan: 2026-11-27 to 2026-12-26

Rules from the owner: no ad spend, no bought engagement, no follow/like/comment automation, nothing that needs a cookie banner.

Baseline measured 2026-11-26: Bluesky 0 followers, 9 posts (public API); Telegram 2 subscribers (t.me/boardread); Instagram paused by an action block until 2026-11-27 16:15 UTC, follower count to be read from the first weekly file; site live on boardread.news with 301s from the old address.

Targets below are my estimates for a new automated news brand with no paid push. No benchmark for this exact case exists (`brand/research/platforms.md` found none for Telegram or Threads), so read them as tripwires for a review, and judge success by the decision metrics.

## The numbers that decide

All come from `state/insights/<week>.json` (Mondays 06:01 UTC) and Search Console.

| Metric | Where | Why it decides |
|---|---|---|
| Instagram sends + saves per reach, per post (median) | insights `instagram` | the research's top ranking signal; it gates the volume ramp |
| Instagram profile visits and follows per post | insights `instagram` | whether reach turns into followers |
| Threads replies + reposts + quotes + shares per view | insights `threads` | Threads ranks conversation |
| Bluesky likes and reposts per post; followers | insights `bluesky` | no views exist; followers are the outcome |
| Telegram views per post; subscribers | insights `telegram` | views over subscribers is the open rate |
| Search clicks and impressions on `/s/` pages | Search Console | the only site traffic number until a counter is approved |
| Lift by topic, format, visual, hour | insights `signals` | what to change next |

## Week 1 (Nov 27 to Dec 3): instrument and restart

- Owner: verify Search Console and Bing (`SEO.md`); set the Bluesky bot label; give the Telegram bot the pin right, then `python3 -m aidaily telegram-pin --send`; submit to TGStat.
- Desk: Instagram resumes at the current cap (12 a day); everything else unchanged.
- Merge this branch so Monday Dec 1 runs the first multi-platform insights pull.
- Targets: Search Console verified, both sitemaps accepted; first weekly file lists numbers from at least four platforms; zero new Instagram blocks.
- Decision on Dec 1: if Instagram shows a block again, hold the cap at 12 by hand and stop here until it clears.

## Week 2 (Dec 4 to 10): discovery surfaces

- Owner: deploy the Bluesky feed Worker and write the record (`DISTRIBUTION.md`); add the feed to the starter pack; decide on the Cloudflare DNS move (`MEASUREMENT.md` step 2); ask the lawyer question on the pixel.
- Desk: insights loop applies its first guarded changes (most categories will still sit under the 5-post minimum).
- Targets: Bluesky 25 followers; Telegram 15 subscribers; Instagram median sends per reach measured on at least 30 posts.
- Decision on Dec 8: a topic with a signal (≥5 posts, ±15%) gets one manual test: for example, if text cards beat photos, ask br-editorial to try more text cards for that topic. One change at a time, so its effect can be read the week after.

## Week 3 (Dec 11 to 17): formats

- Desk: switch on `growth.so_what` if the editorial session's checks pass; it is the strongest defence against the originality and scaled-content rules and it gives Threads a reason to reply.
- Try one Threads community tag for one topic (`threads_topic_tags`), only if the insights file shows Threads views.
- Targets: Bluesky 60, Telegram 35, first Search Console impressions on article pages; Instagram follows per post above the week-2 median.
- Decision on Dec 15: if Instagram sends per reach held for two weeks (no `ramp_hold`), let the ramp raise the cap one step (automatic). If it fell, the hold is automatic; the owner decides on any cut.

## Week 4 (Dec 18 to 24): the owned channel

- Owner: pick a newsletter provider (`DISTRIBUTION.md`), get the legal texts checked, put the sign-up page live with double opt-in. Sending stays manual.
- Desk: daily reel (`growth.daily_reel`) only if Instagram reach per post is flat or falling and per-post sends hold; reels are the non-follower format.
- Targets: Bluesky 100, Telegram 60, newsletter sign-up page live, first 10 confirmed subscribers.

## Day 29 to 30 (Dec 25 to 26): review

- Read four weekly files side by side. Keep what lifted, revert what did not (each switch is one line in `desk.json`).
- Decide the paid test from the growth research (EUR 100 to 150, economy or tech carousel with the best sends per reach, no political topics). It is the owner's call and outside these 30 days.
- Write the review into `brand/growth/REVIEW-2026-12.md`.

## What the desk does on its own, and what it never does

- On its own, within the guard rails in `MEASUREMENT.md` §5: category weights, Telegram digest hour, quiet hours for web-tier social posts, holding the Instagram ramp.
- Never: cut volume, switch a growth flag, post anywhere new, change a bio, sign up for a service, or spend money. Those stay with the owner.
