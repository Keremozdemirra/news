"""The local share desk: python3 -m aidaily serve, then open http://127.0.0.1:8742

Reads what the daily run writes to out/<date>/pack/ (cards and manifest.json),
so each scheduled run feeds it without a step in between. Per card: copy the
image, copy the text, open X or LinkedIn with the text filled in, mark it
posted. Text edits and posted marks are saved to out/<date>/share.json.

Listens on 127.0.0.1 only. Nothing here talks to a platform: the browser
opens the platform's own compose page and the owner presses Post.
"""
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "out"
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FILE = re.compile(r"^card-\d{2}\.png$")


def days():
    return sorted((p.name for p in OUT.iterdir() if DAY.match(p.name) and (p / "pack" / "manifest.json").exists()),
                  reverse=True) if OUT.exists() else []


def load(day):
    cards = json.loads((OUT / day / "pack" / "manifest.json").read_text())
    state_file = OUT / day / "share.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    for c in cards:
        c.update(state.get(c["url"], {}))
    return cards


def save(day, url, patch):
    f = OUT / day / "share.json"
    state = json.loads(f.read_text()) if f.exists() else {}
    allowed = {k: v for k, v in patch.items() if k in ("x_post", "linkedin_post", "posted_x", "posted_linkedin")}
    state.setdefault(url, {}).update(allowed)
    f.write_text(json.dumps(state, indent=1))


class Desk(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass

    def do_GET(self):
        parts = self.path.split("?")[0].strip("/").split("/")
        if parts == [""]:
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if parts == ["api", "days"]:
            return self._send(200, json.dumps(days()), "application/json")
        if len(parts) == 3 and parts[:2] == ["api", "day"] and DAY.match(parts[2]) and parts[2] in days():
            return self._send(200, json.dumps(load(parts[2])), "application/json")
        if len(parts) == 3 and parts[0] == "card" and DAY.match(parts[1]) and FILE.match(parts[2]):
            f = OUT / parts[1] / "pack" / parts[2]
            if f.exists():
                return self._send(200, f.read_bytes(), "image/png")
        self._send(404, "not found", "text/plain")

    def do_POST(self):
        parts = self.path.strip("/").split("/")
        if len(parts) == 3 and parts[:2] == ["api", "day"] and DAY.match(parts[2]) and parts[2] in days():
            n = int(self.headers.get("Content-Length", 0))
            if n > 100_000:
                return self._send(413, "too large", "text/plain")
            body = json.loads(self.rfile.read(n) or b"{}")
            save(parts[2], str(body.get("url", "")), body.get("patch", {}))
            return self._send(200, "{}", "application/json")
        self._send(404, "not found", "text/plain")


def serve(port=8742):
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Desk)
    print(f"share desk: http://127.0.0.1:{port}")
    httpd.serve_forever()


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Boardread desk</title>
<link href="https://fonts.googleapis.com/css2?family=Libre+Franklin:wght@400;500;700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#fcfcfb;--ink:#111;--mute:#6f6f6f;--line:#e4e4e2;--done:#1d6b45}
@media (prefers-color-scheme:dark){:root{--bg:#111;--ink:#f2f2f0;--mute:#a3a3a3;--line:#2c2c2c;--done:#5fc28d}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 'Libre Franklin',system-ui,sans-serif}
main{max-width:1180px;margin:0 auto;padding:28px 16px 80px}
header{display:flex;align-items:baseline;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:28px}
h1{margin:0;font-size:34px;font-weight:800;letter-spacing:-.5px}
select,button,textarea{font:inherit;color:inherit}
select{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px 12px;min-height:44px}
.card{display:grid;grid-template-columns:minmax(0,340px) minmax(0,1fr);gap:28px;padding:28px 0;border-top:1px solid var(--line)}
.card img{width:100%;border-radius:10px;border:1px solid var(--line);display:block}
.meta{color:var(--mute);font-size:14px;margin-bottom:6px}
h2{margin:0 0 18px;font-size:24px;font-weight:800;line-height:1.15;letter-spacing:-.3px}
.post{margin-top:16px}
.row{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;font-size:14px;color:var(--mute)}
.row b{color:var(--ink);font-weight:700}
.over{color:#c0392b}
textarea{width:100%;min-height:92px;padding:12px;border:1px solid var(--line);border-radius:8px;background:transparent;resize:vertical;line-height:1.45}
.btns{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}
button{min-height:44px;padding:0 16px;border-radius:8px;border:1px solid var(--line);background:transparent;cursor:pointer;font-weight:500}
button.go{background:var(--ink);color:var(--bg);border-color:var(--ink)}
button:focus-visible,select:focus-visible,textarea:focus-visible{outline:2px solid var(--ink);outline-offset:2px}
.posted{color:var(--done);font-weight:700}
.toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:var(--ink);color:var(--bg);padding:10px 16px;border-radius:8px;opacity:0;transition:opacity .15s}
.toast.on{opacity:1}
.empty{color:var(--mute);padding:40px 0}
@media (max-width:760px){.card{grid-template-columns:1fr}}
@media (prefers-reduced-motion:reduce){.toast{transition:none}}
</style></head><body><main>
<header><h1>Boardread desk</h1><label><span class="meta">Day </span><select id="day" aria-label="Day"></select></label></header>
<div id="list"></div>
</main><div class="toast" id="toast" role="status" aria-live="polite"></div>
<script>
const $ = s => document.querySelector(s);
let day = null, cards = [];
function toast(t){const e=$('#toast');e.textContent=t;e.classList.add('on');clearTimeout(e._t);e._t=setTimeout(()=>e.classList.remove('on'),1400)}
async function save(url, patch){await fetch('/api/day/'+day,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url,patch})})}
async function copyImage(src){
  const blob = await (await fetch(src)).blob();
  await navigator.clipboard.write([new ClipboardItem({'image/png': blob})]);
  toast('Image copied: paste it into the post');
}
async function copyText(t){await navigator.clipboard.writeText(t);toast('Text copied')}
function openX(t){window.open('https://x.com/intent/post?text='+encodeURIComponent(t),'_blank','noopener')}
function openLinkedIn(t){window.open('https://www.linkedin.com/feed/?shareActive=true&text='+encodeURIComponent(t),'_blank','noopener')}
function post(c, key, label, limit){
  const posted = c['posted_'+(key==='x_post'?'x':'linkedin')];
  const wrap = document.createElement('div'); wrap.className='post';
  wrap.innerHTML = `<div class="row"><b>${label}</b><span class="count"></span></div>
    <textarea aria-label="${label} text"></textarea>
    <div class="btns">
      <button class="go" data-a="open">Copy image, open ${label}</button>
      <button data-a="img">Copy image</button>
      <button data-a="txt">Copy text</button>
      <button data-a="done">${posted?'Posted':'Mark posted'}</button>
    </div>`;
  const ta = wrap.querySelector('textarea'), cnt = wrap.querySelector('.count'), done = wrap.querySelector('[data-a=done]');
  ta.value = c[key] || '';
  const upd = () => {cnt.textContent = ta.value.length + ' / ' + limit; cnt.classList.toggle('over', ta.value.length > limit)};
  upd();
  let t; ta.addEventListener('input', () => {upd(); clearTimeout(t); t=setTimeout(()=>save(c.url,{[key]:ta.value}),400)});
  if (posted) done.classList.add('posted');
  const src = '/card/'+day+'/'+c.file;
  wrap.addEventListener('click', async e => {
    const a = e.target.dataset.a; if (!a) return;
    try {
      if (a==='img') await copyImage(src);
      if (a==='txt') await copyText(ta.value);
      if (a==='open') {
        // the compose page opens even when the clipboard refuses, so one failure never blocks posting
        try {await copyImage(src)} catch(err) {toast('Image not copied: drag it from the card instead')}
        key==='x_post'?openX(ta.value):openLinkedIn(ta.value)
      }
      if (a==='done') {const v = !done.classList.contains('posted'); done.classList.toggle('posted', v); done.textContent = v?'Posted':'Mark posted';
        await save(c.url, {['posted_'+(key==='x_post'?'x':'linkedin')]: v})}
    } catch(err) {toast('Could not copy: '+err.message)}
  });
  return wrap;
}
function render(){
  const list = $('#list'); list.innerHTML='';
  if (!cards.length){list.innerHTML='<p class="empty">No cards for this day yet.</p>';return}
  for (const c of cards){
    const el = document.createElement('article'); el.className='card';
    el.innerHTML = `<img alt=""><div><div class="meta"></div><h2></h2></div>`;
    el.querySelector('img').src = '/card/'+day+'/'+c.file;
    el.querySelector('img').alt = c.headline;
    el.querySelector('.meta').textContent = [c.slot, c.category, c.source, c.outlets>1?c.outlets+' newsrooms':''].filter(Boolean).join(' · ');
    el.querySelector('h2').textContent = c.headline;
    const col = el.children[1];
    col.appendChild(post(c,'x_post','X',280));
    col.appendChild(post(c,'linkedin_post','LinkedIn',3000));
    list.appendChild(el);
  }
}
async function loadDay(d){day=d; cards = await (await fetch('/api/day/'+d)).json(); render()}
(async()=>{
  const ds = await (await fetch('/api/days')).json(); const sel = $('#day');
  sel.innerHTML = ds.map(d=>`<option>${d}</option>`).join('');
  sel.onchange = () => loadDay(sel.value);
  if (ds.length) loadDay(ds[0]); else $('#list').innerHTML='<p class="empty">No packs yet. Run python3 -m aidaily prepare, write copy.json, then finish.</p>';
})();
</script></body></html>"""
