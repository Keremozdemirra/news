"""Pack the Blender renders for the page: python3 pack.py <render_dir> <assets/art dir>

A render_dir with layers.json (build_scale.py ... layers) is packed as six sprites, which is what the page uses.
The stepped frames below are the older form, kept in art/frames/.

Balance frames become WebP with alpha. The shadow a frame carries is faded out over its outer 48 px so it never
ends on the frame edge (the balance itself never reaches the edge). The room plate becomes one opaque WebP.
"""
import json, sys
from pathlib import Path
from PIL import Image, ImageChops

src, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)

if (src / "layers.json").exists():
    # the six sprites of build_scale.py "layers": each cut to what it draws, with its box in the frame written to scale.json
    meta = json.loads((src / "layers.json").read_text())
    W, H, FADE = meta["w"], meta["h"], 48
    boxes = {}
    for name in meta["layers"]:
        im = Image.open(src / f"{name}.png").convert("RGBA")
        if name == "stand":                 # it carries the shadow: fade it out before the frame edge
            ramp = Image.new("L", (W, H), 255); px = ramp.load()
            for x in range(W):
                e = min(x, W - 1 - x)
                if e < FADE:
                    v = int(255 * (e / FADE) ** 1.5)
                    for y in range(H): px[x, y] = v
            im.putalpha(ImageChops.multiply(im.getchannel("A"), ramp))
        x0, y0, x1, y1 = im.getchannel("A").point(lambda v: 255 if v > 2 else 0).getbbox()
        x0, y0, x1, y1 = max(0, x0 - 2), max(0, y0 - 2), min(W, x1 + 2), min(H, y1 + 2)
        im.crop((x0, y0, x1, y1)).save(out / f"{name}.webp", "WEBP", quality=86, method=6)
        boxes[name] = {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}
    meta["layers"] = boxes
    (out / "scale.json").write_text(json.dumps(meta, separators=(",", ":")))
    print("packed", {n: (out / f"{n}.webp").stat().st_size // 1024 for n in boxes}, "KB")
    sys.exit(0)
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
