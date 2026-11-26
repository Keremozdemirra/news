# Measurement without cookies (2026-11-26)

Goal: count readers on boardread.news without cookies, without personal data and without a consent banner, and learn per post what works on each platform.

Tags: [P] primary source read, [S] secondary, [U] unconfirmed, [inference] my reasoning. Not legal advice; the open legal point is marked "lawyer question".

## 1. The legal frame, in two layers

1. **Access to the device: § 25 TDDDG (Germany), Art. 5(3) ePrivacy Directive.** Storing or reading information on the reader's device needs consent unless strictly necessary. This applies whether or not the information is personal data.
   - DSK, OH Digitale Dienste v1.2 (November 2024), paras 18, 23-24: reading device properties with JavaScript (screen size, OS version, fonts) and sending them to a server counts as access. [P] https://datenschutzkonferenz-online.de/media/oh/OH_Digitale_Dienste.pdf
   - EDPB Guidelines 2/2023 v2.0 (7 October 2024), paras 32-34 and 47-51: a website that makes the browser send information by embedding a tracking pixel or JavaScript gains access within Art. 5(3). The same guidelines (paras 49-51) treat tracking identifiers added to URLs the same way. Paras 54-55: even IP-only tracking can fall in scope. The guidelines leave the consent exemptions to national law. [P] https://www.edpb.europa.eu/system/files/2024-10/edpb_guidelines_202302_technical_scope_art_53_eprivacydirective_v2_en_0.pdf
   - Consequence: under the EDPB reading, no client-side counter is clearly outside consent. A JavaScript beacon is the weakest position: Cloudflare Web Analytics, Plausible's script and GoatCounter's count.js all run one. A scriptless pixel sits in the middle. A count taken from the server's own request log adds no instruction to the device, which makes it the strongest position. [inference]
2. **Personal data: GDPR.** IP addresses are personal data. A tool that keeps only aggregates and drops the IP after counting can rest on legitimate interest (Art. 6(1)(f)), with a processor agreement (Art. 28) when a vendor processes the IP. GoatCounter's own rationale makes this argument and says its author is no lawyer. [P] https://www.goatcounter.com/help/gdpr

## 2. Options compared

| Option | Cost | Device access | Personal data | Fits static GitHub Pages | Verdict |
|---|---|---|---|---|---|
| Cloudflare proxy in front of Pages, zone analytics (server-side, no script) | free plan | none added: counts the page request itself | Cloudflare sees IPs as processor (DPA, EU-US Data Privacy Framework [S] https://cloudflare.com/gdpr) | yes, after moving DNS to Cloudflare | **recommended** |
| GoatCounter hosted, scriptless pixel (prototyped, removed) | free for non-commercial "reasonable public usage" [S] https://goatcounter.com/ | pixel, contested per EDPB 2/2023 para 51 | aggregates only, IP dropped [S] https://goatcounter.com/privacy ; hosting country not found [U] | yes, one `<img>` per page | no, for now: removed so no config edit can start it |
| GoatCounter count.js | free | JS reads screen size and referrer: access per DSK para 24 | as above | yes | no |
| Cloudflare Web Analytics beacon (JS) | free | JS beacon (Performance API) [S] https://developers.cloudflare.com/web-analytics/about/ | Cloudflare | yes | no |
| Plausible self-hosted | a server to run and patch | JS script | own server | needs a server | no: cost and ops for no legal gain |
| Platform-side numbers (Search Console, platform insights) | free | nothing on our site | Google and Meta hold it | yes | **always on**, the baseline |

Server-free counters (a static page that counts itself) do not exist on GitHub Pages: Pages serves files and keeps no logs for the owner. [inference from how Pages works]

## 3. What shipped

- **Platform insights loop** (`aidaily/insights.py`, Monday 06:01 UTC in `weekly`). It reads per-post numbers from Instagram, Threads, Facebook, Bluesky (public AppView, no login) and Telegram (views and subscribers from the public page t.me/s/boardread, no bot token), stores them in each `post.json` under `metrics`, and writes `state/insights/<week>.json`. No site visitor is involved. Tested live on 2026-11-26: 9 Bluesky posts and 10 Telegram posts read correctly.
- **No page counter.** A scriptless GoatCounter pixel was prototyped and taken out again in review: the owner allows no consent banner, and a one-line config edit must not be able to start third-party tracking. The pages load nothing from another host and the CSP keeps `img-src 'self' data:`; a test holds that. Bringing a counter back means a code change and a review.
- **UTM tags switch.** `desk.json` → `growth.utm` (off). When on, links posted to a channel end in `?utm_source=<channel>&utm_medium=social`, one label per channel and the same for every reader. Keep it off while nothing on the site reads the landing URL. A scriptless pixel would not see it either, and Cloudflare's free analytics does not split by query string [U]. The canonical tag stays clean either way.
- **Search Console** needs one DNS record and no page code: see `SEO.md`.

## 4. Recommendation and owner steps

1. Now, no risk: verify Search Console and Bing Webmaster Tools (DNS TXT record). This gives search clicks and impressions per page.
2. For page counts: move boardread.news DNS from Porkbun to Cloudflare (free plan), proxy the apex and `www` to GitHub Pages, SSL mode "Full (strict)", and leave Web Analytics' automatic beacon injection off. Do it in this order: GitHub must issue the Pages certificate while DNS points straight at GitHub, so turn the orange cloud on only after "Enforce HTTPS" is ticked. [U] Check against Cloudflare's and GitHub's docs on the day. Zone analytics then show requests, visits and countries without any page code.
3. Lawyer question, only if a client-side counter is ever wanted: "Does a scriptless counting pixel (path only, no-referrer, no storage, aggregate counts at GoatCounter) need consent under § 25 TDDDG, given EDPB Guidelines 2/2023 para 51?" A clear "no" would justify a code change and a review; nothing in the config can switch one on.
4. Privacy notice: use `privacy-draft.md` for keremozdemir.de/privacy. The site's footer already links that page as Boardread's privacy notice (same operator).

## 5. What the loop computes, and its guard rails

- One number per post and platform: Instagram (shares + saves) / reach, the research's top signal; Threads (replies + reposts + quotes + shares) / views; Facebook interactions / reach when Meta still returns reach, else the count; Bluesky likes + 2 × (reposts + quotes) + replies; Telegram views. Each is divided by that platform's 30-day median, so 1.0 is a typical post.
- Groups: topic, rank category, format (carousel, single image, web only, reel), visual (photo or text card), tier (Instagram or web), UTC hour (3-hour buckets).
- Reading rules: Instagram gets one call per post with all metrics joined (per-metric calls only when Instagram refuses that call), the desk's Instagram cooldown is checked before every call, and a block answer goes to the same `note_block` the publishing flow uses and stops Instagram reads for the run. Posts older than 7 days keep the numbers already stored; only never-measured ones are read. Counts without an audience size (Bluesky, Telegram, Facebook without reach) are compared only once a post is 48 hours old. Telegram pages go back to the oldest post in the window (at most 40 pages); if the cap is hit, the weekly file says the window was shorter. Learned values older than 14 days are ignored.
- Feedback, each with a guard rail (constants at the top of `insights.py`):

| Lever | Rule | Guard rail |
|---|---|---|
| Rank weight per category (`state/weights.json`, read by `desk.pick`) | follows the shrunk lift | ≥5 posts; lift × n/(n+10); 0.8 to 1.25; at most ±0.1 a week; `pick` lets a weight move a story a few places at most |
| Telegram digest hour (`state/learned.json`) | one hour toward the best evening hour | 17 to 21 UTC; one hour a week; ≥5 posts in both hours; ≥0.15 better |
| Quiet hours for web-tier Threads and Bluesky posts | hours with shrunk lift under 0.7 wait | ≥5 posts per hour, breaking posts left out of the scoring; at most 6 hours; a quiet hour stays 14 days; breaking stories always go |
| Instagram daily cap ramp (`desk.ramp`) | held when the last 7 days' median send rate is under 80% of days 8 to 30 | ≥10 posts on each side; the code only holds; any cut is the owner's call |

- Everything before and after is in the weekly file, so any change can be traced and reverted by hand (delete `state/learned.json` and the desk falls back to the shipped constants).
