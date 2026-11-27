// One letter cell, a split-flap card in flat ink: two halves hinged on a seam. To change, the top half of the old
// letter falls forward to the seam while the new letter's top shows behind it, then the new bottom half swings down
// over the old one. A scored letter does this twice, as a departure board does: a passing letter, then the one that
// stays. Transform only; a row of six is read in about a second.
const FALL = "cubic-bezier(0.5, 0, 0.9, 0.4)", LAND = "cubic-bezier(0.2, 1.3, 0.4, 1)";      // gravity in, a small knock on landing
export const TURN = 300, STAGGER = 90;      // ms: one card's two changes, and the gap before the next card starts
const ABC = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

export class Tile {
  constructor(reduced) {
    this.reduced = reduced;
    this.el = document.createElement("div");
    this.el.className = "tile"; this.el.setAttribute("role", "gridcell");
    this.el.dataset.s = "empty";
    this.face = this.leaf("face", "", "empty");
    this.el.append(this.face);
    this.letter = ""; this.state = "empty";
  }
  leaf(cls, letter, state) {
    const d = document.createElement("div"); d.className = "leaf " + cls; d.dataset.s = state;
    const s = document.createElement("span"); s.textContent = letter; d.appendChild(s);
    return d;
  }
  set(letter, state) {
    this.letter = letter; this.state = state;
    this.face.firstChild.textContent = letter; this.face.dataset.s = state;
    this.el.dataset.s = state;
    this.el.dataset.has = letter ? "1" : "";
  }
  // one change of the card, ms long; at() runs when the new letter is fully down
  change(letter, state, ms, at) {
    return new Promise((res) => {
      const oldTop = this.leaf("top", this.letter, this.state), oldBot = this.leaf("bot", this.letter, this.state), newBot = this.leaf("bot", letter, state);
      newBot.style.transform = "perspective(300px) rotateX(90deg)";
      this.set(letter, state);                            // behind the flaps the card already shows the new letter
      this.el.append(oldBot, oldTop, newBot);
      oldTop.animate([{ transform: "perspective(300px) rotateX(0deg)" }, { transform: "perspective(300px) rotateX(-90deg)" }], { duration: ms * 0.45, easing: FALL, fill: "forwards" }).onfinish = () => {
        oldTop.remove();
        newBot.animate([{ transform: "perspective(300px) rotateX(90deg)" }, { transform: "perspective(300px) rotateX(0deg)" }], { duration: ms * 0.55, easing: LAND, fill: "forwards" }).onfinish = () => { oldBot.remove(); newBot.remove(); at?.(); res(); };
      };
    });
  }
  // quick: a typed or deleted letter, shown at once with a small press. Otherwise a scored letter: the card turns.
  // Resolves when the next card may start, which is before this one has finished.
  flip(letter, state, { quick = false, onContact } = {}) {
    if (this.reduced || !this.el.animate) { this.set(letter, state); onContact?.(); return Promise.resolve(); }
    if (quick) {
      this.set(letter, state);
      if (letter) this.el.animate([{ transform: "scale(1.08)" }, { transform: "scale(1)" }], { duration: 120, easing: "cubic-bezier(0.23, 1, 0.32, 1)" });
      return Promise.resolve();
    }
    const pass = ABC[(ABC.indexOf(letter) + 7 + Math.floor(Math.random() * 12)) % 26];
    this.change(pass, "typed", TURN * 0.42).then(() => this.change(letter, state, TURN * 0.58, onContact));
    return new Promise((res) => setTimeout(res, STAGGER));
  }
}
