"""Pack the Blender renders for the page: python3 pack.py <render_dir> <assets/art dir>

dial-base / dial-needle / dial-cap  -> WebP with alpha, 720 px
car-00..12                          -> car.webp, one strip of thirteen door positions (336 x 468 each); an open
                                       leaf slides behind the corner post, so everything outside the posts below
                                       the roof is cut away
call-up / call-down                 -> call.webp, two frames
"""
import sys
from pathlib import Path
from PIL import Image

src, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
for n in ("dial-base", "dial-needle", "dial-cap"):
    Image.open(src / f"{n}.png").convert("RGBA").save(out / f"{n}.webp", "WEBP", quality=88, method=6)
N, FW, FH = 13, 336, 468
strip = Image.new("RGBA", (N * FW, FH), (0, 0, 0, 0))
for i in range(N):
    im = Image.open(src / f"car-{i:02d}.png").convert("RGBA")
    w, h = im.size
    # 1 unit = 400 px at 448 wide; the posts end at x = +-0.52, the roof starts at z = 1.235 (image bottom is z = 0)
    left, right, roof = int(w / 2 - 0.521 * 400), int(w / 2 + 0.521 * 400), int(h - 1.235 * 400)
    a = im.getchannel("A"); px = a.load()
    for y in range(roof, int(h - 0.13 * 400)):
        for x in list(range(0, left)) + list(range(right, w)): px[x, y] = 0
    im.putalpha(a)
    strip.paste(im.resize((FW, FH), Image.LANCZOS), (i * FW, 0))
strip.save(out / "car.webp", "WEBP", quality=88, method=6)
call = Image.new("RGBA", (480, 240), (0, 0, 0, 0))
for i, n in enumerate(("call-up", "call-down")): call.paste(Image.open(src / f"{n}.png").convert("RGBA"), (i * 240, 0))
call.save(out / "call.webp", "WEBP", quality=90, method=6)
print("packed", sum(f.stat().st_size for f in out.iterdir()) // 1024, "KB")
