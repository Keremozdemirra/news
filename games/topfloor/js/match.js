// Which entry does a typed answer mean? The player's side of names.py: the same folding, the same order
// (exact key, then the distinctive core, then one typo), so a build-time test of a name holds on the device.
const MAP = { "ø": "o", "đ": "d", "ł": "l", "æ": "ae", "œ": "oe", "ı": "i", "þ": "th", "ð": "d", "ß": "ss" };
const UML = { "ä": "ae", "ö": "oe", "ü": "ue" };

export function norm(s, umlaut = false) {
  s = s.toLowerCase();
  if (umlaut) s = s.replace(/[äöü]/g, (c) => UML[c]);
  s = s.replace(/[øđłæœıþðß]/g, (c) => MAP[c]).normalize("NFKD").replace(/\p{M}/gu, "");
  s = s.replace(/[&+]/g, " and ").replace(/['’`´]/g, "").replace(/[^\p{L}\p{N}]+/gu, " ").replace(/\s+/g, " ").trim();
  return s.replace(/^the /, "");
}

// one typo apart: a letter wrong, missing, extra, or two neighbours swapped
export function dl1(a, b) {
  const la = a.length, lb = b.length;
  if (a === b || Math.abs(la - lb) > 1) return a === b;
  let i = 0;
  while (i < Math.min(la, lb) && a[i] === b[i]) i++;
  if (la === lb) return a.slice(i + 1) === b.slice(i + 1) || (i + 1 < la && a[i] === b[i + 1] && a[i + 1] === b[i] && a.slice(i + 2) === b.slice(i + 2));
  return la > lb ? a.slice(i + 1) === b.slice(i) : a.slice(i) === b.slice(i + 1);
}

// rules: { legal: [...], stop: [...], fuzz: 7 } from today.json; generic: the prompt's own filler words
export function matcher(entries, generic, rules) {
  const legal = new Set(rules.legal), stop = new Set(rules.stop), gen = new Set(generic), fuzz = rules.fuzz || 7;
  const gens = [...gen].filter((g) => g.length >= 4).sort((a, b) => b.length - a.length);
  const keys = new Map(), cores = new Map();
  entries.forEach((e, i) => { for (const k of e[3]) if (!keys.has(k)) keys.set(k, i); for (const c of e[4] || []) if (!cores.has(c)) cores.set(c, i); });

  const stripLegal = (k) => { for (;;) { const j = k.lastIndexOf(" "); if (j < 0 || !legal.has(k.slice(j + 1)) || j < 2) return k; k = k.slice(0, j); } };
  const solid = (k) => k.split(" ").filter((t) => t !== "and").join("");
  const spaced = (name) => { const out = []; for (const u of [false, true]) { const k = norm(name, u); for (const v of [k, stripLegal(k)]) if (v.length >= 2 && !out.includes(v)) out.push(v); } return out; };
  const core = (key) => {
    const toks = [];
    for (let t of stripLegal(key).split(" ")) {
      if (stop.has(t) || gen.has(t) || legal.has(t)) continue;
      for (const g of gens) if (t.endsWith(g) && t.length - g.length >= 4) { t = t.slice(0, -g.length); if (t.endsWith("s") && t.length > 4) t = t.slice(0, -1); break; }
      toks.push(t);
    }
    const c = toks.join("");
    return c.length >= 4 && !/^\d+$/.test(c) ? c : "";
  };

  // returns the entry index, or null when the answer is not on file
  return function find(guess) {
    const sp = spaced(guess), vs = [...new Set(sp.map(solid))].filter((v) => v.length >= 2);
    for (const v of vs) if (keys.has(v)) return keys.get(v);
    for (const v of sp) { const c = core(v); if (c && keys.has(c)) return keys.get(c); if (c && cores.has(c)) return cores.get(c); }
    let best = null;
    for (const v of vs) {
      if (v.length < fuzz) continue;
      for (const [k, i] of keys) if (k.length >= fuzz && Math.abs(k.length - v.length) <= 1 && (best === null || i < best) && dl1(v, k)) best = i;
    }
    return best;
  };
}
