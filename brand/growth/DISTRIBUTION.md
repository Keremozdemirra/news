# Distribution tactics (2026-11-26)

What shipped in code, what the owner does by hand, and what was ruled out. Tags as in `MEASUREMENT.md`.

## Bluesky custom feed

**Static hosting cannot serve it.** Bluesky's AppView calls `app.bsky.feed.getFeedSkeleton` on the feed's host and rejects any reply whose content type is not `application/json` (atproto xrpc client: `readPayload` parses JSON only for that type, `matchesEncoding` then fails with `InvalidFeedResponse`). [P, read through DeepWiki on bluesky-social/atproto] GitHub Pages sets the type from the file extension and the XRPC path has none, so boardread.news alone cannot answer.

**What shipped instead** (no firehose, no database, nothing that runs on our side):

- Every site build writes `/bsky-feed.json`: our own Bluesky post URIs, newest first, at most 100 (`python3 -m aidaily bsky-feed`). Local build: 9 posts.
- `scripts/bsky-feed-worker.js`: a Cloudflare Worker (free tier) that serves `/.well-known/did.json`, `describeFeedGenerator` and `getFeedSkeleton` from that file, with cursor paging.
- `python3 -m aidaily bsky-feed-record <host>` prints the `app.bsky.feed.generator` record; `--send` writes it with `putRecord` and a fixed key, so a second run replaces the record and never mints a second feed.

**Owner steps** (about 20 minutes, needs a free Cloudflare account):

1. Cloudflare → Workers → Create → paste `scripts/bsky-feed-worker.js` → Deploy.
2. Add a custom domain `feed.boardread.news` to the Worker (needs the DNS on Cloudflare, see `MEASUREMENT.md` step 2), or use the `*.workers.dev` hostname it gives.
3. Worker variables: `SKELETON_URL` = `https://boardread.news/bsky-feed.json`; `FEED_URI` = `at://<boardread DID>/app.bsky.feed.generator/boardread` (the DID is `did:plc:rs25xii6lopjeyelvd2otrqq`, read from a live post URI on 2026-11-26).
4. Check `https://<host>/.well-known/did.json` answers JSON.
5. Locally, with `BSKY_HANDLE` and `BSKY_APP_PASSWORD` set, run `python3 -m aidaily bsky-feed-record <host>` to see the record, then the same with `--send`.
6. Add the feed to the "Business & Markets News" starter pack (one of its three feed slots) and pin it on the profile.

Expected value: a durable discovery surface and a reason for other pack makers to include Boardread. Uptake of new feeds depends on likes; no number exists. [U]

**Also by hand on Bluesky:** set the `bot` self-label (Settings → Account → Automation label) as the platform research recommends; set the domain handle `@boardread.news` with a DNS TXT record (`_atproto.boardread.news`).

## Telegram

- **Pinned post.** `python3 -m aidaily telegram-pin` prints it; `--send` posts it silently and pins it (channels never notify on a pin). The bot needs the "Pin messages" right in the channel's admin settings first. Text: what Boardread is, that routine posts are silent and breaking ones notify, the AI disclosure with the source-check rule, the corrections page, the other channels, and the topic hashtags.
- **Hashtags.** Every channel post now ends with its topic hashtag (`#markets`, `#economy`, ...), so Telegram's post search and in-channel tag taps find it. One tag only: more turns a news post into a tag list.
- **Digest cross-links.** The evening digest now closes with the site link and the other channels.
- **Catalogs (owner, free).** TGStat has an "Add a channel" page (tgstat.com, Catalog menu) [S]. telega.io lists criteria including 1,000 subscribers and no political material, so it does not fit yet [S]. tgdr.io (Telegram Directory) takes open submissions [S]. Effect on subscribers: no data found [U]. Do TGStat once, revisit telega.io at 1,000 subscribers.
- **Ruled out:** posting the channel link into other people's groups (spam reports), bought subscribers (ToS, and it poisons "similar channels").

## Threads

- One topic tag per post already ships, taken from the topic. `desk.json` can now name a Threads community tag per topic in `threads_topic_tags` (spaces allowed, 50 characters, no periods or ampersands), e.g. `{"Markets": "Stock Market"}`. Shipped empty: which community tags carry reach on Threads is unmeasured [U]. Try one topic at a time and read the insights file before changing the next.
- The sources link stays in a reply, where Threads shows links less poorly.

## Cross-links and UTM

- Profiles: every bio should name the site and the other channels (`brand/PROFILE.md`). By hand.
- Site: the masthead and footer already link all channels.
- UTM: built, off (`growth.utm`). Turn on together with a counter that reads landing URLs; see `MEASUREMENT.md` §3.

## Email newsletter plan (nothing signed up)

**Why:** the only channel no platform can throttle. Content: the evening top five that Telegram already gets, plus one "what it means" line each, sent weekdays or weekly.

**Shortlist** (free tiers checked 2026-11-26 through search summaries, confirm on the vendor page before choosing):

| Provider | Free tier | EU | API / automation | Fit |
|---|---|---|---|---|
| CleverReach (Germany) | 250 recipients, 1,000 emails a month; an ad button on free plans [S] | German vendor, EU servers [S] | yes | best legal fit, small free tier |
| Brevo (France) | 300 emails a day, "Sent with Brevo" footer [S, help.brevo.com] | EU vendor; data location not confirmed [U] | yes, transactional and campaign API | best free volume |
| Buttondown | first 100 subscribers free; RSS-to-email a paid add-on [S, research] | not confirmed [U] | API exists | simplest Markdown workflow |
| beehiiv | up to 2,500 subscribers free; send API and RSS-to-send on Pro only [S, research] | US | API on all plans, send on Pro | growth features (recommendations), US transfer |

Recommendation: CleverReach or Brevo. Start manual: the desk drafts the issue as a file, the owner presses send. Automate sending only after 200 subscribers.

**Double opt-in flow** (standard in Germany; courts treat it as the proof of consent, the statutory status is debated [S]):

1. Form on boardread.news/newsletter/ posts to the provider's hosted endpoint (no data touches our site; CSP `form-action` must allow that one host).
2. The provider sends the confirmation email; the address is stored as unconfirmed.
3. A click on the link confirms; the provider logs time and IP of sign-up and confirmation.
4. Every issue carries an unsubscribe link and the Impressum.
5. Unconfirmed addresses are deleted after 30 days.

**Draft texts:**

> Sign-up box: "Get the day's five stories that move business, with their sources. One email each weekday evening. Unsubscribe any time. We store your email address and the time and IP of your sign-up to prove your consent; details in the privacy notice."

> Confirmation email subject: "Confirm your Boardread subscription". Body: "Click to confirm and start receiving Boardread: [link]. If you did not ask for this, ignore this email and nothing will be sent."

Privacy section: `privacy-draft.md`, "Newsletter". Lawyer questions: the imprint duty in the email, the data-processing agreement with the provider, and whether an English-only notice suffices.

## Ruled out

- Reddit and Hacker News automation (bans; see `brand/research/platforms.md` §9-10).
- LinkedIn automation (User Agreement 8.2.13). A manual post by the owner a few times a week is allowed and has the best audience fit.
- Paid spend: none for 30 days by the owner's rule.
