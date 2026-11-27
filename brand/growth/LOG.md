# Growth log

One entry a week: what changed, what the numbers did. Numbers come from public profile pages or APIs on the day
named, and from `state/insights/<week>.json` once the Monday pull runs. Plan: `PLAN-30.md`.

## Week 0, baseline (read 2026-11-26, 23:55 UTC)

| Channel | Followers / subscribers | Read from |
|---|---|---|
| Instagram @boardread | 10 | public profile page |
| Threads @boardread | 0 | public profile page (posting again since the token renewal) |
| Bluesky boardread.bsky.social | 0 (10 posts) | public.api.bsky.app getProfile |
| Telegram t.me/boardread | 2 | t.me page |
| Site | news sitemap and sitemap answer 200, both in robots.txt | curl |

Instagram is in an action-block cooldown until 2026-11-27 16:15 UTC; nothing posts there before then.

### Changed this week

- Video cards (commits 8e104b2, 104a61a). Two posts a day carry a video in place of the still card: the same
  card, its photo moving behind the text. They alternate between two shapes so the weekly insights can compare
  them on similar stories: `video carousel` (4:5 video as the first slide, detail slide after) and `video reel`
  (9:16 Reel with a cover). Inside the 12-a-day cap and the 45-minute spacing; a video replaces its still card.
  Only photos under CC0, CC BY or public domain move. Switch: `desk.json` `video.on`.
- Why both shapes: vendor data says Reels reach more non-followers and carousels earn more saves per reach
  (`brand/GROWTH-RESEARCH.md`); this account has no numbers of its own yet. Decision rule for 2026-12-15: with at
  least 6 posts of each shape, keep the shape with the higher median reach per post unless its sends and saves per
  reach are 30% lower; set `video.format` to it.

### Next

- 2026-11-27 after 16:15 UTC: first video posts live on Instagram; check them on the profile at phone size.
- 2026-12-01: first multi-platform insights pull; first numbered entry here.
