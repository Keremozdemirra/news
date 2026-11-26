# SEO: Google News, Discover and Search readiness (2026-11-26)

Measured on a local build of this branch (48 pages) and on the live site. Source rules: Google's Article structured data, news sitemap and Discover pages, and the Google News content policies, as summarised in `brand/research/platforms.md` §5.

## Where the site stands

| Check | State | How it was measured |
|---|---|---|
| Domain move | done. `keremozdemir.de/news/`, `www.boardread.news` and `http://` all answer 301 to `https://boardread.news/` | `curl -w '%{http_code} %{redirect_url}'`, 2026-11-26 |
| Canonical consistency | every page's canonical and og:url are on `https://boardread.news/`; no page, feed or sitemap mentions `keremozdemir.de/news` | `python3 -m aidaily seo` (0 errors) |
| NewsArticle JSON-LD | parses on every article; headline ≤110, image absolute https, datePublished with timezone, author and publisher with logo | same audit |
| Publisher entity (E-E-A-T) | publisher is now a `NewsMediaOrganization` with logo, `sameAs` (the five channels), `publishingPrinciples` and `correctionsPolicy` (/standards/), `verificationFactCheckingPolicy` (/how-it-works/), contact point (/contact/); author points at /about/ | this branch |
| Trust pages | /about/, /standards/ (corrections), /contact/, /how-it-works/ exist and are linked from every footer; Impressum and Privacy link to keremozdemir.de (same operator) | site build |
| AI disclosure | "Written by AI from the sources listed" on every article and footer | site build |
| Sitemaps | /sitemap.xml and /news-sitemap.xml exist; robots.txt now names both (it named only the first) | this branch |
| News sitemap window | two days, as Google asks; the live file held 1 entry on 2026-11-26 because few stories were published yet | `curl` count of `<url>` |
| Discover image | per-article og image 1200x630 and `max-image-preview:large` on every indexable page | site build |
| Internal links | 2,805 internal links checked, all resolve | audit |
| Page speed | front page 19.6 KB HTML; CSS 24 KB + 24 KB, JS 12 KB, four self-hosted fonts at 16 KB each; one origin, no third-party request; live time to first byte 0.07 s from here | `ls`, `du`, `curl -w`; no Lighthouse run in this pass |
| Layout shift | every `<img>` carries width and height | audit |

The site workflow now runs the audit after each build and prints the result in the run summary. It reports and never blocks a deploy, so the design work in `aidaily/site.py` cannot be held up by it. Make it blocking once a few clean weeks have passed: remove `continue-on-error` from the "SEO audit" step in `.github/workflows/site.yml`.

## Known limits

- **Scaled content risk.** Google's spam policy names large amounts of unoriginal content, including AI-generated, as abuse. Each article has to add something: the multi-source synthesis, the source list, the "what it means" line (switch `growth.so_what`, off today). This is the largest SEO risk and no markup fixes it. [P] developers.google.com/search/docs/essentials/spam-policies
- **New domain.** Expect weeks to months before Top stories or Discover. No markup is required for either; eligibility comes from indexing and policy compliance.
- **Discover core update of February 2026** reportedly favoured local, expert, original content and cut non-US sites in US Discover. Treat Discover as upside. [S]

## Search Console checklist (owner)

Do these in order; each takes minutes.

1. search.google.com/search-console → Add property → **Domain** → `boardread.news`. Copy the TXT record.
2. Porkbun (or Cloudflare, if DNS moved there) → DNS → add the TXT record on the apex. Wait, then press Verify.
3. Sitemaps → submit `https://boardread.news/sitemap.xml` and `https://boardread.news/news-sitemap.xml`.
4. URL inspection → paste the front page and two recent articles → Request indexing.
5. Settings → Change of address: open the old property for keremozdemir.de if you have one verified, and pick boardread.news. The 301s are in place, which this tool requires. Skip if keremozdemir.de/news was never verified.
6. Enhancements → after a few days, check "Articles" (structured data) for errors, and Page experience → Core Web Vitals once data appears.
7. Manual actions and Security issues: check weekly for the first month (the 30-day plan has the slot).
8. Bing Webmaster Tools → import from Search Console (one click) → also gives IndexNow later.
9. Google News: there is no application. Publication pages are made automatically since March 2025. Publisher Center is only for Showcase and Reader Revenue. [P] support.google.com/news/publisher-center/answer/15898024
10. Preferred sources: once Search Console shows the site indexed, add a "Add Boardread as a preferred source on Google" link on /about/. The exact link format is unconfirmed. [U]

## What to read each week

Search Console → Performance → filter by page `/s/`: clicks, impressions and average position per article; compare topics with the insights file `state/insights/<week>.json`.
