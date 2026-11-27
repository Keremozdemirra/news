// What brings a player back, on every end screen: the streak, the last seven days, and the article that leads the
// site today. Everything here is read from this device; nothing is sent anywhere.
const iso = (d) => d.toISOString().slice(0, 10);

// streak: the number; label: "Day streak" or "Win streak"; played: a Set of ISO dates with a finished game; today: ISO date
export function comeBack({ streak, label, played, today }) {
  document.getElementById("e-streak-l").textContent = label;
  document.getElementById("e-streak").textContent = streak;
  const ol = document.getElementById("e-week"); ol.textContent = "";
  const t = Date.parse(today + "T12:00:00Z");
  for (let k = 6; k >= 0; k--) {
    const d = new Date(t - k * 864e5), li = document.createElement("li");
    li.textContent = d.toLocaleDateString("en-GB", { weekday: "narrow", timeZone: "UTC" });
    li.className = (played.has(iso(d)) ? "on" : "") + (k === 0 ? " today" : "");
    li.setAttribute("aria-label", `${d.toLocaleDateString("en-GB", { weekday: "long", timeZone: "UTC" })}: ${played.has(iso(d)) ? "played" : "not played"}`);
    ol.appendChild(li);
  }
  document.getElementById("again").hidden = false;
}
export async function topArticle() {
  const p = document.getElementById("e-top");
  try {
    const a = await (await fetch("/play/top.json", { cache: "no-cache" })).json();
    if (!a.h || !a.url) return;
    const link = document.createElement("a"); link.href = a.url; link.textContent = a.h;
    p.textContent = "Today on Boardread: "; p.appendChild(link); p.hidden = false;
  } catch { /* offline or no file: the line stays out */ }
}
// the share button says what it did, in place, and goes back
export function said(labelId, text, ms = 1600) {
  const el = document.getElementById(labelId), was = el.dataset.was || el.textContent;
  el.dataset.was = was; el.textContent = text;
  clearTimeout(el._t); el._t = setTimeout(() => { el.textContent = was; }, ms);
}
