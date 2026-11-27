// The answer lists live here, off the page's thread: fetching, parsing and indexing 30,000 names takes seconds on a
// phone and used to freeze the opening animation. The page asks by message and gets back only what it draws.
import { matcher } from "./match.js";

let sets = [];      // per prompt: { entries, find }

async function load(prompts, rules, base) {
  sets = await Promise.all(prompts.map(async (p) => {
    const entries = p.entries || (await (await fetch(new URL(p.list, base))).json()).entries;
    return { entries, find: matcher(entries, p.generic || [], rules) };
  }));
  return sets.map((s, i) => { const r = s.entries.find((x) => x[0] === prompts[i].rare?.[0]); return { n: s.entries.length, rareTier: r ? r[2] : null }; });
}

self.onmessage = async ({ data: m }) => {
  try {
    if (m.t === "load") self.postMessage({ id: m.id, info: await load(m.prompts, m.rules, m.base) });
    else if (m.t === "find") {
      const s = sets[m.i], hit = m.raw.trim() ? s.find(m.raw) : null, e = hit === null ? null : s.entries[hit];
      self.postMessage({ id: m.id, hit: e && { rank: hit, label: e[0], tier: e[2], extra: e[5] || "" } });
    }
  } catch (err) { self.postMessage({ id: m.id, error: String(err) }); }
};
