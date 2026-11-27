// One letter cell. A flat card that turns on its middle: it closes to a line, takes its new letter and state there,
// and opens again. Transform only, 200 ms for a scored letter, so a row of six is read in under a second.
const EASE_IN = "cubic-bezier(0.55, 0, 0.85, 0.3)", EASE_OUT = "cubic-bezier(0.23, 1, 0.32, 1)";
export const TURN = 200, STAGGER = 110;      // ms: one card's turn, and the gap before the next card starts

export class Tile {
  constructor(reduced) {
    this.reduced = reduced;
    this.el = document.createElement("div");
    this.el.className = "tile"; this.el.setAttribute("role", "gridcell");
    this.el.dataset.s = "empty";
    this.ch = document.createElement("span");
    this.mark = document.createElement("i"); this.mark.className = "mark"; this.mark.setAttribute("aria-hidden", "true");
    this.el.append(this.ch, this.mark);
  }
  set(letter, state) {
    this.ch.textContent = letter;
    this.el.dataset.s = state;
    this.el.dataset.has = letter ? "1" : "";
  }
  // quick: a typed or deleted letter, shown at once with a small press. Otherwise a scored letter: the card turns.
  // Resolves when the next card may start, which is before this one has finished opening.
  flip(letter, state, { quick = false, onContact } = {}) {
    if (this.reduced || !this.el.animate) { this.set(letter, state); onContact?.(); return Promise.resolve(); }
    if (quick) {
      this.set(letter, state);
      if (letter) this.el.animate([{ transform: "scale(1.08)" }, { transform: "scale(1)" }], { duration: 120, easing: EASE_OUT });
      return Promise.resolve();
    }
    return new Promise((res) => {
      const close = this.el.animate([{ transform: "scaleY(1)" }, { transform: "scaleY(0.02)" }], { duration: TURN * 0.45, easing: EASE_IN });
      close.onfinish = () => {
        this.set(letter, state); onContact?.();
        this.el.animate([{ transform: "scaleY(0.02)" }, { transform: "scaleY(1)" }], { duration: TURN * 0.55, easing: EASE_OUT });
      };
      setTimeout(res, STAGGER);
    });
  }
}
