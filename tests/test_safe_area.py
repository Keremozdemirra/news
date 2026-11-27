"""Every text layer of a 9:16 video stays inside the area Reels and Shorts leave clear of their own buttons and
captions. Measured on the rendered pixels (the alpha bounding box of each transparent layer), not on the CSS."""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from aidaily import cardvideo as CV
from aidaily import render
from aidaily import shorts as SH
from aidaily import templates as T

HAVE = shutil.which("ffmpeg") and (Path(render.CHROME).exists() if render.CHROME.startswith("/") else shutil.which(render.CHROME))
LONG = "Taiwan votes Saturday in local elections as officials warn of China interference over the island's referendum"
FACT = ("More than 11,000 officials are on the ballot in a vote seen as a midterm test of President Lai Ching-te's support "
        "across the island's cities and counties.")


def bbox(png):
    """(x1, y1, x2, y2) of the pixels with any opacity."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(png), "-vf", "alphaextract,bbox=min_val=8", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.findall(r"x1:(\d+) x2:(\d+) y1:(\d+) y2:(\d+)", r.stderr)
    x1, x2, y1, y2 = map(int, m[-1])
    return x1, y1, x2, y2


@unittest.skipUnless(HAVE, "needs ffmpeg and Chrome")
class SafeArea(unittest.TestCase):
    def test_no_text_layer_crosses_the_safe_area(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = Path(tmp) / "p.jpg"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=1600x1200", "-frames:v", "1",
                            str(photo)], check=True)
            post = {"id": "a", "headlines": [LONG], "dek": FACT, "sources": ["The Straits Times", "Bloomberg", "Nikkei Asia"],
                    "topic": "Politics", "photo_file": "P.jpg", "credit": "Photo: Kenneth C. Zirkel, CC0, via Wikimedia Commons"}
            story = SH.story_from(post, photo, post["credit"])
            pages = {name: CV.layer_html(story, "reel", name) for name in ("meta", "head", "foot")}
            pages["fact"] = SH.text_layer(story, FACT)
            pages["sources"] = SH.text_layer(story, "Reported by The Straits Times, Bloomberg and Nikkei Asia", weight=700, size=72)
            for name, html_ in pages.items():
                png = Path(tmp) / f"{name}.png"
                CV.shoot_layer(html_, png, CV.W, CV.HEIGHT["reel"])
                x1, y1, x2, y2 = bbox(png)
                self.assertGreaterEqual(x1, 48, name)
                # the floor holds even if the constants are loosened: 140 px right, 380 px bottom at least
                self.assertLessEqual(x2, CV.W - max(T.REEL_SAFE_RIGHT, 140), f"{name} reaches x={x2}")
                self.assertLessEqual(y2, CV.HEIGHT["reel"] - max(T.REEL_SAFE_BOTTOM, 380), f"{name} reaches y={y2}")
                self.assertGreaterEqual(y1, 200, name)


if __name__ == "__main__":
    unittest.main()
