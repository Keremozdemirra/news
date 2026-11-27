// One letter cell. A scored letter turns over on its horizontal axis: it closes to an edge, takes its colour there,
// and opens again, 250 ms in all; the cards of a row go one after another, left to right. Transform only.
const IN = "cubic-bezier(0.55, 0, 0.85, 0.4)", OUT = "cubic-bezier(0.23, 1, 0.32, 1)";
export const TURN = 250, STAGGER = 170;      // ms: one card's turn, and the gap before the next card starts

export class Tile {
  constructor(reduced) {
    this.reduced = reduced;
    this.el = document.createElement("div");
    this.el.className = "tile"; this.el.setAttribute("role", "gridcell");
    this.el.dataset.s = "empty";
    this.ch = document.createElement("span");
    this.el.append(this.ch);
  }
  set(letter, state) {
    this.ch.textContent = letter;
    this.el.dataset.s = state;
    this.el.dataset.has = letter ? "1" : "";
  }
  // quick: a typed or deleted letter, shown at once with a small pop. Otherwise a scored letter: the card turns and
  // changes colour edge-on. Resolves when the next card may start, which is before this one has finished.
  flip(letter, state, { quick = false, onContact } = {}) {
    if (this.reduced || !this.el.animate) { this.set(letter, state); onContact?.(); return Promise.resolve(); }
    if (quick) {
      this.set(letter, state);
      if (letter) this.el.animate([{ transform: "scale(1.1)" }, { transform: "scale(1)" }], { duration: 110, easing: OUT });
      return Promise.resolve();
    }
    this.el.animate([{ transform: "rotateX(0deg)" }, { transform: "rotateX(-90deg)" }], { duration: TURN / 2, easing: IN }).onfinish = () => {
      this.set(letter, state); onContact?.();
      this.el.animate([{ transform: "rotateX(-90deg)" }, { transform: "rotateX(0deg)" }], { duration: TURN / 2, easing: OUT });
    };
    return new Promise((res) => setTimeout(res, STAGGER));
  }
}
