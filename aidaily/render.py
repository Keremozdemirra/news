"""Render stories to PNG cards (and the weekly carousel to PDF) with headless Chrome.

The daily video was cut on 2026-09-28. Templates live in templates.py.
"""
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from . import templates as T

MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
# the GitHub Actions Ubuntu image ships google-chrome on PATH
CHROME = MAC_CHROME if Path(MAC_CHROME).exists() else (shutil.which("google-chrome") or shutil.which("chromium") or "google-chrome")


def jpeg(png, quality=92):
    """Instagram takes JPEG only. sips on macOS, ffmpeg elsewhere; no Python image package needed."""
    out = Path(png).with_suffix(".jpg")
    if shutil.which("sips"):
        cmd = ["sips", "-s", "format", "jpeg", "-s", "formatOptions", str(quality), str(png), "--out", str(out)]
    else:
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(png), "-q:v", "2", str(out)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    return out


def shoot(html_text, png, w, h):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(html_text)
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={w},{h}",
                    "--virtual-time-budget=6000", f"--screenshot={png}", f"file://{f.name}"],
                   check=True, capture_output=True, timeout=60)
    Path(f.name).unlink()


def pdf(html_text, out_pdf):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(html_text)
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--virtual-time-budget=6000",
                    f"--print-to-pdf={out_pdf}", f"file://{f.name}"], check=True, capture_output=True, timeout=90)
    Path(f.name).unlink()


def pack(slots, out_dir, brand=T.BRAND):
    """One card per story across the day's slots, plus manifest.json for the share page.

    Returns the list of card files, in slot order (breaking first).
    """
    import json
    out = Path(out_dir)
    # a rerun must never leave yesterday's card beside today's
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    files, manifest, seen = [], [], set()
    for slot in ("breaking", "funding", "top", "business"):
        for s in slots.get(slot, []):
            if s["url"] in seen:
                continue
            seen.add(s["url"])
            f = out / f"card-{len(files) + 1:02d}.png"
            shoot(T.card(s, brand), f, 1080, 1350)
            files.append(f)
            manifest.append({"file": f.name, "slot": slot, "url": s["url"], "headline": s.get("headline") or s["title"],
                             "category": s.get("category", ""), "source": s.get("source", ""),
                             "x_post": s.get("x_post", ""), "linkedin_post": s.get("linkedin_post", ""),
                             "score": s.get("score", 0), "photo_file": s.get("_assets", {}).get("file", ""), "outlets": len(s.get("timeline") or s.get("outlets") or [])})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return files
