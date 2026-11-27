// Which entry does a typed answer mean? The player's side of names.py: the same folding, the same order
// (exact key, then the distinctive core, then one typo), so a build-time test of a name holds on the device.
const MAP = { "ø": "o", "đ": "d", "ł": "l", "æ": "ae", "œ": "oe", "ı": "i", "þ": "th", "ð": "d", "ß": "ss" };
const UML = { "ä": "ae", "ö": "oe", "ü": "ue" };

// category nouns of any prompt, and everyday words: a guess made only of these names nothing (names.py holds the same lists)
export const KIND = new Set("air airline airlines airways ale authority auto automobile automobiles automotive autos aviation bakery bank banking banks bar beer bier bike bikes brewer breweries brewers brewery brewing burger burgers bus cafe car cars cash chicken coffee coin coins commercial composite crypto cryptocurrency currency donut donuts drink drinks entertainment exchange fast federal finance financial flight flights fly food foods fries game games gaming grill groceries grocery hamburger hamburgers hypermarket index interactive kitchen lager lines manufacturer manufacturing market markets mart monetary money motor motors network pils pizza pizzeria plane planes play protocol pub publisher publishing reserve restaurant restaurants sandwich sandwiches savings securities share shares shop shops software stock stocks store stores studio studios supermarket supermarkets taco tacos token tokens truck trucks trust vehicle vehicles video wine works".split(" "));
export const COMMON = new Set("african all american another any anything apple are asian at bad banana be best better big black blue bright british brown by central city classic cold come country county crown dark day digital direct dunno earth east eastern easy eight english european every express family fast fire first five four free french fresh friends from future general german get global go gold golden good grand gray great green grey happy he high home hot house how idk imperial inner international island it italian its jet king lake land last life light little live long look love low lower lucky made make many max maxi me mega middle mini modern moon more most mountain much my name national net new next night nine no none north northern not nothing now ocean off old on one online only open orange original other our out outer over own people peoples pink plus premium prime prince pro pure queen quick real red river royal same sea second see service services seven she short silver simple six sky small smart some something south southern spanish special standard star state states stuff sun super tech ten test that them these they thing things third this those three time to today top town true turkish two under union united universal up upper us use was water we web week west western what which white who why with world worldwide year yellow yes you young your".split(" "));

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

  const filler = (t) => stop.has(t) || legal.has(t) || gen.has(t) || KIND.has(t);
  const sig = (name) => norm(name).split(" ").filter((t) => t && !filler(t)).join("");
  // false when the guess is only category nouns and everyday words: it then counts as an entry's whole name of
  // several words ("Lucky Stores"), a well-known entry's one-word name ("King"), or a best-known name without its category words ("United")
  const namesIt = (e, guess) => {
    const toks = norm(guess).split(" ").filter(Boolean);
    const plain = (t) => stop.has(t) || legal.has(t) || KIND.has(t) || COMMON.has(t);      // not the prompt's filler: "Sparkasse" is an answer alone
    if (toks.some((t) => !plain(t))) return true;
    const s = sig(guess), g = solid(norm(guess)), whole = g === solid(norm(e[0])) || g === solid(norm(e[0], true));
    if (!s) return false;                // "car", "the bank", "stock exchange", whoever is called that
    if (toks.length > 1) return whole || (e[2] <= 1 && s === sig(e[0]));
    return (whole && e[2] <= 1) || (e[2] === 0 && s === sig(e[0]));
  };

  // returns the entry index, or null when the answer is not on file
  return function find(guess) { const i = lookup(guess); return i !== null && namesIt(entries[i], guess) ? i : null; };
  function lookup(guess) {
    const sp = spaced(guess), vs = [...new Set(sp.map(solid))].filter((v) => v.length >= 2);
    for (const v of vs) if (keys.has(v)) return keys.get(v);
    for (const v of sp) { const c = core(v); if (c && keys.has(c)) return keys.get(c); if (c && cores.has(c)) return cores.get(c); }
    let best = null;
    for (const v of vs) {
      if (v.length < fuzz) continue;
      for (const [k, i] of keys) if (k.length >= fuzz && Math.abs(k.length - v.length) <= 1 && (best === null || i < best) && dl1(v, k)) best = i;
    }
    return best;
  }
}
