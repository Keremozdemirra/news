// Boardread's Bluesky custom feed as a Cloudflare Worker (free tier). Deploy steps: brand/growth/DISTRIBUTION.md.
// It answers three things and stores nothing:
//   /.well-known/did.json                          the did:web document naming this host as a feed generator
//   /xrpc/app.bsky.feed.describeFeedGenerator      which feed it serves
//   /xrpc/app.bsky.feed.getFeedSkeleton            post URIs read from the site's /bsky-feed.json, paged by cursor
// Protocol: https://atproto.com/guides/feeds and https://github.com/bluesky-social/feed-generator (read 2026-11-26).
// Set two Worker variables: FEED_URI (at://<boardread did>/app.bsky.feed.generator/boardread) and
// SKELETON_URL (https://boardread.news/bsky-feed.json).

const json = (body, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "public, max-age=60" },
  });

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const did = `did:web:${url.hostname}`;

    if (url.pathname === "/.well-known/did.json") {
      return json({
        "@context": ["https://www.w3.org/ns/did/v1"],
        id: did,
        service: [{ id: "#bsky_fg", type: "BskyFeedGenerator", serviceEndpoint: `https://${url.hostname}` }],
      });
    }

    if (url.pathname === "/xrpc/app.bsky.feed.describeFeedGenerator") {
      return json({ did, feeds: [{ uri: env.FEED_URI }] });
    }

    if (url.pathname === "/xrpc/app.bsky.feed.getFeedSkeleton") {
      if (url.searchParams.get("feed") !== env.FEED_URI) {
        return json({ error: "UnknownFeed", message: "This host serves one feed." }, 400);
      }
      const limit = Math.min(Math.max(parseInt(url.searchParams.get("limit") || "30", 10) || 30, 1), 100);
      const start = Math.max(parseInt(url.searchParams.get("cursor") || "0", 10) || 0, 0);
      // the static file is cached at the edge for five minutes; the site rebuilds after every publishing run
      const res = await fetch(env.SKELETON_URL, { cf: { cacheTtl: 300, cacheEverything: true } });
      if (!res.ok) return json({ feed: [] });
      const all = (await res.json()).feed || [];
      const page = all.slice(start, start + limit);
      const body = { feed: page };
      if (start + limit < all.length) body.cursor = String(start + limit);
      return json(body);
    }

    return json({ error: "NotFound" }, 404);
  },
};
