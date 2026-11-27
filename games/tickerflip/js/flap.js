// One letter cell, drawn as a split-flap card in flat ink: a seam across the middle, and a turn about that seam.
// A scored letter turns twice, as a departure board does: a passing letter first, then the one that stays.
// Transform only. A row of six is read in about a second.
const EASE_IN = "cubic-bezier(0.55, 0, 0.85, 0.3)", EASE_OUT = "cubic-bezier(0.23, 1, 0.32, 1)";
export const TURN = 300, STAGGER = 100;      // ms: one card's two turns, and the gap before the next card starts
const ABC = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

export class Tile {
  constructor(reduced) {
    this.reduced = reduced;
    this.el = document.createElement("div");
    this.el.className = "tile"; this.el.setAttribute("role", "gridcell");
    this.el.dataset.s = "empty";
    this.card = document.createElement("div"); this.card.className = "leaf";
    this.ch = document.createElement("span");
    this.mark = document.createElement("i"); this.mark.className = "mark"; this.mark.setAttribute("aria-hidden", "true");
    this.card.append(this.ch); this.el.append(this.card, this.mark);
  }
  set(letter, state) {
    this.ch.textContent = letter;
    this.el.dataset.s = state;
    this.el.dataset.has = letter ? "1" : "";
  }
  turn(ms, at) {      // the card closes about its seam, changes at the dead point, and opens
    return new Promise((res) => {
      const close = this.card.animate([{ transform: "perspective(240px) rotateX(0deg)" }, { transform: "perspective(240px) rotateX(-90deg)" }], { duration: ms * 0.45, easing: EASE_IN });
      close.onfinish = () => { at(); this.card.animate([{ transform: "perspective(240px) rotateX(90deg)" }, { transform: "perspective(240px) rotateX(0deg)" }], { duration: ms * 0.55, easing: EASE_OUT }).onfinish = res; };
    });
  }
  // quick: a typed or deleted letter, shown at once with a small press. Otherwise a scored letter: the card turns.
  // Resolves when the next card may start, which is before this one has finished.
  flip(letter, state, { quick = false, onContact } = {}) {
    if (this.reduced || !this.card.animate) { this.set(letter, state); onContact?.(); return Promise.resolve(); }
    if (quick) {
      this.set(letter, state);
      if (letter) this.el.animate([{ transform: "scale(1.08)" }, { transform: "scale(1)" }], { duration: 120, easing: EASE_OUT });
      return Promise.resolve();
    }
    const pass = ABC[(ABC.indexOf(letter) + 7 + Math.floor(Math.random() * 12)) % 26];
    this.turn(TURN * 0.4, () => { this.ch.textContent = pass; }).then(() => this.turn(TURN * 0.6, () => { this.set(letter, state); onContact?.(); }));
    return new Promise((res) => setTimeout(res, STAGGER));
  }
}
