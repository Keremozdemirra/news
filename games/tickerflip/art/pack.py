#!/usr/bin/env python3
"""Pack the rendered PNGs in art/png/ into the WebP files the page loads (assets/art/).

    python3 art/pack.py

The renders stay lossless in art/png/; only the WebP copies are served. The two halls are opaque backdrops behind
the board and take a low quality; the pieces that sit on the type (frame, flap shadow, tile shade, lamp) keep more.
"""
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "assets" / "art"
QUALITY = {"hall-portrait": 62, "hall-wide": 62, "frame": 88, "flap-shadow": 86, "tile-shade": 86, "lamp": 84}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for src in sorted((HERE / "png").glob("*.png")):
        im = Image.open(src)
        if im.mode == "RGBA" and im.getextrema()[3][0] == 255:
            im = im.convert("RGB")          # no transparency in it: the alpha plane is dead weight
        out = OUT / (src.stem + ".webp")
        im.save(out, "WEBP", quality=QUALITY.get(src.stem, 84), method=6)
        print(f"{src.name}: {src.stat().st_size // 1024} KB -> {out.stat().st_size // 1024} KB ({im.mode})")
