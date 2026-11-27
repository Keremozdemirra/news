// One split-flap cell. Four layers: static top (new letter), static bottom (old letter),
// the falling top flap (old letter) and the rising bottom flap (new letter), plus a cast shadow
// frame from the Blender sheet (assets/art/flap-shadow.webp) under the falling flap.
//
// Motion is authored frame by frame, not tweened: every angle below is a held frame.
//  - cycling flap : fall in 2 frames, rise in 2 frames
//  - landing flap : anticipation (the flap lifts 4 degrees), three falling frames, a rising run that
//                   overshoots past flat, a contact frame held for two beats with a 3% squash and a 1px
//                   body nudge, then one settle frame.
// One split-flap cell. Four layers: static top (new letter), static bottom (old letter),
// the falling top flap (old letter) and the rising bottom flap (new letter).
//
// The fall is drawn, not rotated: each held frame is a hand-picked vertical squash of the flap (its foreshortening at
// that angle) plus one frame of the Blender shading sheet (assets/art/flap-shadow.webp: the lamp's light on the card
// at 0, 16, 30, 50, 72 and 86 degrees). Authored beats:
//  - cycling flap : fall in 3 frames, rise in 3 frames
//  - landing flap : anticipation (the flap lifts 2px), three falling frames, a rising run that overshoots (1.04),
//                   a contact frame with a 3% squash and a 1px body nudge, then a settle frame.
const A = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const F = 15; // ms per frame at the cycling rate
const half = (cls) => {
  const d = document.createElement("div"); d.className = cls; d.dataset.s = "empty"; d.appendChild(document.createElement("span"));
  if (cls.includes("flap")) { const sh = document.createElement("i"); sh.className = "shade"; d.appendChild(sh); }
  return d;
};

// s = vertical scale of the flap, i = shading frame, y = lift in px
const CYCLE_FALL = [{ s: 1, i: 0 }, { s: 0.67, i: 3 }, { s: 0.03, i: 5 }];
const CYCLE_RISE = [{ s: 0.03, i: 5 }, { s: 0.7, i: 3 }, { s: 1, i: 0 }];
const LAND_FALL = [{ s: 1, i: 0, y: -2 }, { s: 0.96, i: 1 }, { s: 0.64, i: 3 }, { s: 0.03, i: 5 }];
const LAND_RISE = [{ s: 0.03, i: 5 }, { s: 0.47, i: 4 }, { s: 0.87, i: 2 }, { s: 0.99, i: 1 }, { s: 1.04, i: 0 }, { s: 0.97, i: 0 }, { s: 1.01, i: 0 }, { s: 1, i: 0 }];

const held = (frames, ms, prop) => {
  const n = frames.length;
  const kf = frames.map((f, i) => ({ ...prop(f), offset: i / n, easing: "steps(1, end)" })).concat([{ ...prop(frames[n - 1]), offset: 1 }]);
  return { kf, dur: n * ms };
};
const squash = (f) => ({ transform: `translateY(${f.y || 0}px) scaleY(${f.s})` });
const shade = (f) => ({ backgroundPositionX: `${(f.i / 5) * 100}%` });

export class Tile {
  constructor(reduced) {
    this.reduced = reduced;
    this.el = document.createElement("div");
    this.el.className = "tile";
    this.el.setAttribute("role", "gridcell");
    this.st = half("half top"); this.sb = half("half bot");
    this.ft = half("flap ft"); this.fb = half("flap fb");
    this.mark = document.createElement("i"); this.mark.className = "mark"; this.mark.setAttribute("aria-hidden", "true");
    this.el.append(this.st, this.sb, this.ft, this.fb, this.mark);
    this.letter = ""; this.state = "empty";
    this.set("", "empty");
  }
  paint(layer, letter, state) { layer.firstChild.textContent = letter; layer.dataset.s = state; }
  set(letter, state) {
    this.letter = letter; this.state = state;
    for (const l of [this.st, this.sb]) this.paint(l, letter, state);
    this.el.dataset.s = state;
    this.el.dataset.has = letter ? "1" : "";
  }
  // The drum runs through the alphabet, so the cycling letters are the ones just before the target.
  seq(letter, steps) {
    if (!letter) return [""];
    const i = A.indexOf(letter), out = [];
    for (let k = steps - 1; k >= 0; k--) out.push(A[(i - k + 26) % 26]);
    return out;
  }
  async flip(letter, state, { steps = 1, onStep, onContact, quick = false } = {}) {
    if (this.reduced) { this.set(letter, state); onContact?.(); return; }
    const seq = this.seq(letter, steps);
    for (let i = 0; i < seq.length; i++) {
      const last = i === seq.length - 1, next = seq[i], ns = last ? state : "spin";
      const landing = last && !quick;
      this.el.dataset.has = letter ? "1" : "";
      this.paint(this.st, next, ns); this.paint(this.ft, this.letter, this.state); this.paint(this.fb, next, ns);
      const kids = [this.ft, this.fb, this.ft.lastChild, this.fb.lastChild, this.el];
      for (const a of kids) a.getAnimations().forEach((x) => x.cancel());
      const fall = held(landing ? LAND_FALL : CYCLE_FALL, landing ? 17 : F, squash), fallS = held(landing ? LAND_FALL : CYCLE_FALL, landing ? 17 : F, shade);
      const rise = held(landing ? LAND_RISE : CYCLE_RISE, landing ? 19 : F, squash), riseS = held(landing ? LAND_RISE : CYCLE_RISE, landing ? 19 : F, shade);
      this.ft.style.visibility = "visible"; this.fb.style.visibility = "hidden";
      onStep?.(i, last);
      this.ft.lastChild.animate(fallS.kf, { duration: fallS.dur, fill: "forwards" });
      try { await this.ft.animate(fall.kf, { duration: fall.dur, fill: "forwards" }).finished; } catch { return; }   // a newer flip took this cell over
      this.ft.style.visibility = "hidden"; this.fb.style.visibility = "visible";
      this.fb.lastChild.animate(riseS.kf, { duration: riseS.dur, fill: "forwards" });
      const risen = this.fb.animate(rise.kf, { duration: rise.dur, fill: "forwards" });
      if (landing) {
        // the contact frame is the sixth of eight: nudge the whole cell for it and fire the clack
        setTimeout(() => {
          onContact?.();
          this.el.animate([{ transform: "translateY(1px)" }, { transform: "translateY(1px)", offset: 0.6 }, { transform: "none" }], { duration: 76, easing: "steps(1, end)" });
        }, 19 * 5);
      }
      try { await risen.finished; } catch { return; }
      this.paint(this.sb, next, ns);
      this.fb.style.visibility = "hidden";
      this.letter = next; this.state = ns;
      this.el.dataset.s = ns;
    }
  }
}
