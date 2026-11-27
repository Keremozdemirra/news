"""Pack the Blender frames for the page: python3 pack.py <render_dir> <assets/art dir>

Balance frames become WebP with alpha. The shadow a frame carries is faded out over its outer 48 px so it never
ends on the frame edge (the balance itself never reaches the edge). The room plate becomes one opaque WebP.
"""
import json, sys
from pathlib import Path
from PIL import Image, ImageChops

src, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
meta = json.loads((src / "scale.json").read_text())
W, H, FADE = meta["w"], meta["h"], 48
ramp = Image.new("L", (W, H), 255)
px = ramp.load()
for x in range(W):
    e = min(x, W - 1 - x)
    if e < FADE:
        v = int(255 * (e / FADE) ** 1.5)
        for y in range(H): px[x, y] = v
for old in out.glob("back_*.webp"): old.unlink()
for old in out.glob("front_*.webp"): old.unlink()
for n in range(len(meta["frames"])):
    for layer, q in (("back", 82), ("front", 84)):
        im = Image.open(src / f"{layer}_{n:02d}.png").convert("RGBA")
        if layer == "back": im.putalpha(ImageChops.multiply(im.getchannel("A"), ramp))
        im.save(out / f"{layer}_{n:02d}.webp", "WEBP", quality=q, method=4)
Image.open(src / "plate.png").convert("RGB").save(out / "plate.webp", "WEBP", quality=80, method=4)
meta["ext"] = "webp"
(out / "scale.json").write_text(json.dumps(meta, separators=(",", ":")))
print("packed", len(meta["frames"]), "frames", sum(f.stat().st_size for f in out.iterdir()) // 1024, "KB")
