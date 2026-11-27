// The building, drawn: a stepped tower in line and flat ink, a hundred floors from the street to a helipad.
// Units: one floor is 20 high; the tower's axis is x = 120. Five setbacks at the five tiers, each with its own
// window rhythm. build(false) is the tower with dark windows; build(true) is only its windows, lit, for the layer
// that shows below the car.
export const U = 20, TOP = 220, AXIS = 120, VIEW = [-52, 0, 412];       // floor height, units above floor 100, view box x and width
export const BANDS = [[0, 19, 100, "Lobby"], [20, 44, 84, "Mezzanine"], [45, 71, 68, "Corner Office"], [72, 91, 52, "Penthouse"], [92, 100, 38, "Helipad"]];
export const HEIGHT = TOP + 101 * U + 26;
export const yTop = (f) => TOP + (100 - f) * U;       // top edge of floor f
const hwOf = (f) => BANDS.find(([a, b]) => f >= a && f <= b)[2];
// windows of one floor on one side of the shaft: [x, y, w, h] relative to the axis, mirrored by the caller
function bays(band, f) {
  const hw = BANDS[band][2], y = yTop(f), out = [];
  const row = (n, w, h, dy, inset = 7) => { const span = hw - 13 - inset, gap = (span - n * w) / (n - 1 || 1); for (let i = 0; i < n; i++) out.push([13 + i * (w + gap), y + dy, w, h]); };
  if (band === 0) { if (f >= 3) row(6, 8, 11, 5); }                           // the base: six plain bays over the entrance
  else if (band === 1) row(5, 9, 12, 4);
  else if (band === 2) { if (f % 9 !== 8) row(4, 9, 14, 3); }                 // tall bays, a blind floor every ninth
  else if (band === 3) row(2, 12, 12, 4);
  else row(1, 15, 13, 4, 6);
  return out;
}
export function build(lit) {
  const p = [], rect = (x, y, w, h, extra = "") => p.push(`<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${w.toFixed(1)}" height="${h.toFixed(1)}" ${extra}/>`);
  const line = (x1, y1, x2, y2, w = 1) => p.push(`<path d="M${x1} ${y1}L${x2} ${y2}" stroke-width="${w}"/>`);
  const win = lit ? 'fill="currentColor" stroke="none"' : 'fill="none"';
  BANDS.forEach(([a, b], band) => { for (let f = a; f <= b; f++) for (const [x, y, w, h] of bays(band, f)) { rect(AXIS + x, y, w, h, win); rect(AXIS - x - w, y, w, h, win); } });
  // the entrance: three tall openings either side of the lift, lit with the lobby
  for (const s of [-1, 1]) for (let i = 0; i < 3; i++) rect(AXIS + s * (20 + i * 26) - (s < 0 ? 16 : 0), yTop(2) + 6, 16, 3 * U - 8, win);
  if (lit) return svg(p, "lit");
  // walls with their setbacks; a cornice of two lines where the tower steps in
  BANDS.forEach(([a, b, hw], band) => {
    const y0 = yTop(b), y1 = yTop(a) + U;
    line(AXIS - hw, y0, AXIS - hw, y1, 1.5); line(AXIS + hw, y0, AXIS + hw, y1, 1.5);
    if (band) { const below = BANDS[band - 1][2]; line(AXIS - below - 3, y1, AXIS + below + 3, y1, 1.5); line(AXIS - below, y1 + 3.5, AXIS + below, y1 + 3.5, 0.75); }
    if (band === 2) for (const s of [-1, 1]) for (const x of [24, 37, 50]) line(AXIS + s * x, y0 + 2, AXIS + s * x, y1 - 2, 0.6);     // piers the height of the band
    if (band === 3) for (const s of [-1, 1]) line(AXIS + s * 29, y0 + 2, AXIS + s * 29, y1 - 2, 0.6);
  });
  // the lift shaft, the street, the canopy over the doors
  line(AXIS - 9, yTop(100), AXIS - 9, yTop(0) + U, 0.75); line(AXIS + 9, yTop(100), AXIS + 9, yTop(0) + U, 0.75);
  line(VIEW[0], yTop(0) + U, VIEW[0] + VIEW[2], yTop(0) + U, 2);
  line(AXIS - 86, yTop(2) + 2, AXIS + 86, yTop(2) + 2, 1.5);
  // the crown: two steps, the pad on its struts, the circled H, a mast
  const t = yTop(100);
  line(AXIS - 41, t, AXIS + 41, t, 1.5);
  p.push(`<path d="M${AXIS - 28} ${t}V${t - 18}H${AXIS + 28}V${t}M${AXIS - 18} ${t - 18}V${t - 36}H${AXIS + 18}V${t - 18}" fill="none" stroke-width="1.5"/>`);
  for (const x of [-10, 0, 10]) line(AXIS + x, t - 34, AXIS + x, t - 20, 0.6);
  line(AXIS - 14, t - 36, AXIS - 22, t - 52, 1); line(AXIS + 14, t - 36, AXIS + 22, t - 52, 1);
  line(AXIS - 40, t - 52, AXIS + 40, t - 52, 2.5);
  p.push(`<circle cx="${AXIS}" cy="${t - 72}" r="11" fill="none" stroke-width="1.25"/><path d="M${AXIS - 4} ${t - 78}V${t - 66}M${AXIS + 4} ${t - 78}V${t - 66}M${AXIS - 4} ${t - 72}H${AXIS + 4}" stroke-width="1.5"/>`);
  line(AXIS + 34, t - 52, AXIS + 34, t - 150, 0.9); line(AXIS + 30, t - 120, AXIS + 38, t - 120, 0.9); line(AXIS + 31, t - 135, AXIS + 37, t - 135, 0.9);
  // floor numbers at the wall, every ten; the tier's name where the tower steps in
  // (at a setback the number stands beside the wider wall below it)
  for (let f = 0; f <= 100; f += 10) { const hw = hwOf(Math.max(0, f - 1)), y = yTop(f) + U; line(AXIS - hw - 6, y, AXIS - hw, y, 1); p.push(`<text class="fn" x="${AXIS - hw - 10}" y="${y + 4}" text-anchor="end">${f}</text>`); }
  BANDS.forEach(([a, , hw, name]) => p.push(`<text class="bn" x="${AXIS - hw - 10}" y="${yTop(a) + U - 26}" text-anchor="end">${name}</text>`));
  return svg(p, "dark");
}
const svg = (p, cls) => `<svg class="tw ${cls}" viewBox="${VIEW[0]} 0 ${VIEW[2]} ${HEIGHT}" fill="none" stroke="currentColor" stroke-linecap="square" aria-hidden="true">${p.join("")}</svg>`;
