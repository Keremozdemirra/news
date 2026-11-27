# Post types: what large news accounts post, and what Boardread adds

27 November 2026. Two inputs:

1. **Seen directly.** On 2026-11-27 I opened each public Instagram profile logged out, which shows the 12 newest posts. I also opened three public Threads profiles, which show the 4 newest threads. These observations are dated today and can be checked again at the same addresses.
2. **Published sources.** A sourced literature pass: trade press, analytics vendors and award entries. Most format case studies on these brands are from 2016 to 2020. The 2026 numbers come from third-party tools, and only 4 of the 10 accounts loaded in them. Instagram and Threads block crawlers, so no source gives a current format mix for Reuters, the WSJ, Visual Capitalist or BPT Haber.

## 1. What the accounts post today (seen 2026-11-27)

| Account | What the 12 newest Instagram posts show | Address |
|---|---|---|
| BPT Haber (3.3M followers) | Full-bleed photo, short headline low on the left, "Fotoğrafı kaydır" (swipe for the photo) on two-slide posts. Split portraits of two named people side by side for a meeting or clash. Score cards in a fixed template (shared with its sport account). Navy, white and red brand bar on every card. | instagram.com/bpthaber |
| Bloomberg Business | Full-bleed photo with a 3 to 6 line white headline, "Bloomberg" bottom right, and a red "BREAKING" chip on breaking items. Service and feature headlines ("Leisure sickness is what happens…"). | instagram.com/bloombergbusiness |
| The Economist | Commissioned illustrations and portraits on paper, a small label line ("A few great men", "By Invitation", "The World Ahead"), serif headline. Video with "The Insider" label. | instagram.com/theeconomist |
| Financial Times | Photo cards with a label chip: NEWS BRIEFING, FT EXCLUSIVE, OPINION, BREAKING NEWS. Serif headline, byline "With …". | instagram.com/financialtimes |
| CNBC | Photo cards with a red BREAKING chip and the date. Quote cards: a speaker's photo, a vertical bar and the quote in white. | instagram.com/cnbc |
| Reuters | Photo-first: an agency photo with a short white caption line, or no text at all. Several videos. | instagram.com/reuters |
| The Wall Street Journal | Feature photos with a serif headline on a white box. Video explainers ("How to talk to your boss…"). | instagram.com/wsj |
| Morning Brew | Photo collages with circle cut-outs, a headline and a "MORNING BREW" tag. A "BREW MARKETS" comparison card: two companies side by side, market caps in huge type ($5.2T vs $4.7T). | instagram.com/morningbrew |
| Axios | Almost all video: interview clips with a white caption box, and "The Axios Show". | instagram.com/axios |
| Visual Capitalist | Data posters: ranked bar charts, maps, sankey flows, a year-by-year bar race; some sponsored (DP World, Adobe, Harbor). | instagram.com/visualcap |

Threads, newest four on each public profile (2026-11-27):

| Account | Format | Likes |
|---|---|---|
| Bloomberg Business (1.3M followers) | A post every 5 to 6 minutes: one plain sentence of news plus the article link card. | 0 to 6 |
| The Economist (1.7M followers) | One framing sentence plus the link card. A pinned post. | 3 to 7 (pinned: 119) |
| BPT Haber (314K followers) | Text only. A label prefix ("MAÇ SONUCU \|", match result), short quotes set as `Name: "quote"`, no links. | 22 to 60 |

## 2. What the sources say about performance

- **Reels carry reach.** Reels are 19 of the top 20 posts by views for Bloomberg Business and Morning Brew, 16 of 20 for CNBC, and 13 of 20 for Axios. [Socialpruf](https://socialpruf.com/instagram/cnbc), third-party, 2026-11.
- **Carousels lead on engagement; Reels lead on reach.**
  - [Socialinsider](https://www.socialinsider.io/blog/instagram-carousels/) (2026-06-11): carousels 0.55% engagement, Reels 0.52%, single images 0.37%.
  - [Fanpage Karma](https://www.fanpagekarma.com/insights/instagram-format-reach/) (2026, 3M+ posts): Reels lead reach at every account size.
  - The two sources disagree on carousel reach.
- **Photos still win among top news posts.** NewsWhip's Q3 2025 top 1,000 Instagram posts from 50 publishers were 748 photos and 252 Reels. [NewsWhip](https://www.newswhip.com/?p=54803), 2025-10-20. Sport and entertainment dominate that sample.
- **Charts and data were Bloomberg's core.** About 75% of its Instagram output was charts and stats from the data team; quote cards from business leaders were a recurring format. [Digiday](https://digiday.com/media/longer-videos-powering-bloomberg-instagram-growth/), 2019-03-04.
- **Recap and quiz stories drove traffic.**
  - Bloomberg's weekend roundup story of the week's 10 top articles reported 25% click-through. [Social Media Today](https://www.socialmediatoday.com/news/5-instagram-strategy-tips-from-bloomberg/548175/), 2019-02-12.
  - The Economist's weekly quiz story was "often the most successful traffic driver". [journalism.co.uk](https://www.journalism.co.uk/interactive-data-driven-stories-are-building-community-engagement-at-the-economist/), 2019-06-06.
  - An Insider quiz story reached 347K views. [Shorty Awards](https://shortyawards.com/15th/instagram-overall-presence), undated.
- **Charts grew the FT's following.** It went from 40k to 286k followers in a year on charts. [Digiday](https://digiday.com/media/chart-porn-fts-instagram-following-exploded-year), 2016-10-25. Old.
- **Threads.** Images and link posts "perform strongly" for publishers, but Threads is under 1% of publisher referrals. [Digiday](https://digiday.com/media/traffic-referrals-from-threads-surge-for-some-publishers-this-year/), 2025-03-24.
- **No precedent found** for market-close cards, earnings cards, before/after numbers, timelines or reaction roundups on any news account, in either direction.

## 3. Chosen formats

In genre: business, markets, tech, AI, world. Built only from data the desk already holds and may publish.

| Format | Who does it | Boardread | Status |
|---|---|---|---|
| Breaking label on the card | Bloomberg, CNBC, FT (seen) | "Breaking" chip before the meta line when the score is at `breaking_score` | **Built** (feed cards) |
| Chart card | Visual Capitalist, Bloomberg, FT | Story "Chart · 3 months": the official series that moved most (Brent, WTI, US 2y/10y, EUR/USD, USD/JPY, Henry Hub), one line, first and last print with dates, publisher credit. Skipped when nothing moved | **Built** (story, Thu and Sat 15:00 UTC) |
| Daily data card (rates, oil) | Brew Markets, CNBC markets cards | Story "Rates and oil": EUR/USD, USD/JPY, US 10y/2y, Brent, WTI, each with its own date and move. No index levels or share prices: those are licensed (`aidaily/markets.py`) | **Built** (story, Mon and Wed 16:30 UTC) |
| Quiz with the answer in the next story | Economist, Bloomberg, Insider | Guess the company (sector peers), Fill the number, Which is bigger?, Who is this?; the answer story is the question with one option lit | **Built** (reworked) |
| Daily and weekly recaps | Bloomberg weekend roundup, Economist Weekend Reads | Last 12 hours, Today's top 5, topic board, Week in numbers, Most shared/saved | Existing, redesigned |
| "Who is" profile | BPT split portraits, Bloomberg portrait cards | In the news (named portrait only) | Existing, redesigned |
| Timeline | none found | Company file: the company's last three headlines with dates | Existing, redesigned |
| Comparison card | Morning Brew "Brew Markets" | Two companies' same-kind figures side by side; the data is already used by Which is bigger? | Candidate |
| Quote card | CNBC, Bloomberg | Only a quote that appears verbatim in a source headline, with the speaker and outlet named; our copy step paraphrases, so no quote is taken from our own text | Candidate (needs a verbatim-quote check) |
| Telegram quiz poll | (Telegram Bot API `sendPoll`, quiz mode) | The day's quiz as a Telegram quiz with the correct option and the article link as the explanation | Candidate |
| Threads label prefix | BPT Haber | "MARKETS \|"-style label as the first word of a Threads post | Candidate (test against the reply-rate signal first) |

## 4. Not chosen

- **Reels and video.** They carry reach (section 2) but sit outside the image pipeline; the video session owns them.
- **Earnings cards and market-close cards with index levels.** They need licensed equity data the desk does not hold. The rates and oil card covers the official prints instead.
- **Maps.** Costly to draw honestly per article.
- **Reaction roundups.** They quote people's posts and carry a moderation risk.
- **"Explained" carousels.** They need long-form writing beyond the checked copy step.
- **Off-genre formats** (celebrity, gossip, memes, rage bait, photo contests) are out.
- **Sport.** It reaches social only above `sport_social_min_score`, inside mixed formats.
