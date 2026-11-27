"""Where the subject of a photo is, so every crop of it (site thumbnails, article figure, paper, link preview, Instagram card)
keeps the face inside the frame.

A photo is shown in boxes of many shapes (3:2, 4:3, 16:9, 2:1, 2:3). `object-fit: cover` crops the overflow, and a fixed
`object-position` (centre, or "top 25%") cuts through the forehead or the chin as soon as a 3:4 portrait meets a wide box.
So each photo carries a focal point (fx, fy), as fractions of its width and height, and every crop is positioned from it.

No face-detection library: the build runs on GitHub Actions with the standard library and ffmpeg only. The detector below is a
skin-tone blob finder on a 64 px decode. It is a heuristic, so it is only run on photos that are about a person (the post names
one, or the Commons file name says portrait / cropped / official / headshot), it refuses anything that does not look like a
head (too small, too wide), and then falls back to the framing prior of a portrait: the face sits in the upper third.
A post can always pin the point by hand with `focus: [fx, fy]`, which wins over everything here."""
import re
import struct
import subprocess
from pathlib import Path

# the framing prior of a portrait photo: face centre a little above a third of the way down; a scene is centred, a touch high
PRIOR_PORTRAIT = (0.5, 0.38)
PRIOR_SCENE = (0.5, 0.40)
FACE_NAME = re.compile(r"cropped|crop\b|portrait|official|headshot", re.I)
# a box wider than this cannot hold a whole head cut from a portrait photo, so portraits of faces never go wider
FACE_MAX_RATIO = 4 / 3
DECODE_W = 64


def jpeg_size(path):
    """(width, height) from the JPEG header, or None. Stdlib only, reads the first 200 KB."""
    try:
        with open(path, "rb") as f:
            d = f.read(200000)
    except OSError:
        return None
    i = 2
    while d[:2] == b"\xff\xd8" and i + 9 < len(d):
        if d[i] != 0xFF:
            i += 1
            continue
        m = d[i + 1]
        if m == 0xFF:
            i += 1
            continue
        if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
            i += 2
            continue
        seg = struct.unpack(">H", d[i + 2:i + 4])[0]
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack(">HH", d[i + 5:i + 9])
            return (w, h) if w and h else None
        i += 2 + seg
    return None


def _decode(path, w, h):
    """The photo as w x h RGB bytes, via ffmpeg (already needed by the build)."""
    try:
        r = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-vf", f"scale={w}:{h}:flags=area",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, timeout=60, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if len(r.stdout) == w * h * 3 else None


def visual_score(path):
    """How strong a photo reads on a card, from a 48 x 48 decode: contrast (the spread of brightness), a subject that
    stands out from its surroundings (the centre's spread against the whole), and no clutter (busy edges everywhere
    read as noise at phone size). Higher is better; about 0 to 1.5. Used only to choose among photos of the same
    subject that all passed the licence and fit checks (entities.fresh_photo)."""
    n = 48
    raw = _decode(path, n, n)
    if raw is None:
        return 0.0
    y = [0.299 * raw[i] + 0.587 * raw[i + 1] + 0.114 * raw[i + 2] for i in range(0, len(raw), 3)]

    def spread(vals):
        m = sum(vals) / len(vals)
        return (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5
    sd = spread(y)
    centre = [y[r * n + c] for r in range(12, 36) for c in range(12, 36)]
    edges = sum(abs(y[r * n + c] - y[r * n + c + 1]) + abs(y[r * n + c] - y[(r + 1) * n + c])
                for r in range(n - 1) for c in range(n - 1)) / ((n - 1) ** 2)
    return min(sd, 70) / 70 + 0.3 * min(spread(centre) / (sd + 1), 1.5) - max(0.0, edges - 30) / 60


def skin_mask(raw, w, h):
    """1 where the pixel is skin-toned (YCbCr box, plus red-dominant and not dark), as a list of rows."""
    rows = []
    for y in range(h):
        row = []
        for x in range(w):
            r, g, b = raw[(y * w + x) * 3:(y * w + x) * 3 + 3]
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b
            cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b
            row.append(1 if 77 <= cb <= 127 and 133 <= cr <= 173 and lum > 50 and r > 95 and r > g > 0.9 * b else 0)
        rows.append(row)
    return rows


def blobs(mask):
    """4-connected components of the mask, as lists of (x, y)."""
    h, w = len(mask), len(mask[0])
    seen = [[False] * w for _ in range(h)]
    out = []
    for y in range(h):
        for x in range(w):
            if mask[y][x] and not seen[y][x]:
                seen[y][x] = True
                stack, pts = [(x, y)], []
                while stack:
                    cx, cy = stack.pop()
                    pts.append((cx, cy))
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if 0 <= nx < w and 0 <= ny < h and mask[ny][nx] and not seen[ny][nx]:
                            seen[ny][nx] = True
                            stack.append((nx, ny))
                out.append(pts)
    return out


def head_from_mask(mask):
    """(fx, fy, head width) of the most head-like skin blob as fractions, or None.

    Head-like: big enough, solid, and high in the frame (a hand or a neckline scores lower than a face). The face is the
    top of that blob: its width is the widest row in the upper half, its height about 1.15 of that, so the centre sits
    half a face below the blob's top and not at the blob's centroid (which the neck and chest drag down)."""
    h, w = len(mask), len(mask[0])
    best = None
    for pts in blobs(mask):
        if len(pts) < w * h * 0.012:
            continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        fill = len(pts) / ((x1 - x0 + 1) * (y1 - y0 + 1))
        score = len(pts) * (1.2 - (y0 + y1) / 2 / h) * (fill + 0.3)
        if best is None or score > best[0]:
            best = (score, pts, y0, y1)
    if best is None:
        return None
    _, pts, y0, y1 = best
    top = [p for p in pts if p[1] <= y0 + (y1 - y0) * 0.5]
    widths = {}
    for x, y in top:
        widths.setdefault(y, []).append(x)
    head_w = max(max(v) - min(v) + 1 for v in widths.values())
    if head_w / w > 0.6 or head_w / w < 0.1:  # a backdrop or a crowd, not a head
        return None
    face_h = min(1.15 * head_w, y1 - y0 + 1)
    return sum(x for x, _ in top) / len(top) / w, (y0 + 0.5 * face_h) / h - 0.03, head_w / w


def detect_face(path, size=None):
    """(fx, fy, head width as a share of the photo's width) of the head in the photo at `path`, or None."""
    size = size or jpeg_size(path)
    if not size:
        return None
    w = DECODE_W
    h = max(8, round(w * size[1] / size[0]))
    raw = _decode(path, w, h)
    if raw is None:
        return None
    return head_from_mask(skin_mask(raw, w, h))


def about_a_face(post):
    return bool((post.get("person") or "").strip()) or bool(FACE_NAME.search(post.get("photo_file") or ""))


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def for_post(post, path, size=None):
    """(focus, is_face): where the subject is in the photo, and whether that is a face (which sets the crop shapes allowed).
    Order: a hand-set `focus` on the post, then the detector (people only), then the framing prior."""
    pinned = post.get("focus")
    if pinned and len(pinned) == 2:
        return (clamp(float(pinned[0]), 0, 1), clamp(float(pinned[1]), 0, 1)), True
    size = size or jpeg_size(path)
    if not about_a_face(post):
        return PRIOR_SCENE, False
    found = detect_face(path, size) if path else None
    if found:
        # A head filling the frame (head-and-shoulders) is centred on the eyes and nose: light hair reads as skin and drags the
        # blob up, so the point is kept in the band where those sit. A smaller head (action, half-length) is taken as found.
        lo, hi = (0.36, 0.44) if found[2] >= 0.4 else (0.12, 0.5)
        return (clamp(found[0], 0.15, 0.85), clamp(found[1], lo, hi)), True
    portrait = bool(size) and size[1] >= size[0] * 1.05
    return (PRIOR_PORTRAIT if portrait else (0.5, 0.35)), True


def position(focus, size, ratio):
    """(px, py) in 0..1: the `cover` offset that puts `focus` in the middle of a `ratio` (width / height) box filled from an
    image of `size`, as far as the edges allow. The browser maps position p to an offset of p * (scaled image - box)."""
    fx, fy = focus
    iw, ih = size
    ri = iw / ih
    px = py = 0.5
    if ri > ratio * 1.001:
        vis = ratio / ri  # share of the width that shows
        px = (fx - vis / 2) / (1 - vis)
    elif ri < ratio / 1.001:
        vis = ri / ratio
        py = (fy - vis / 2) / (1 - vis)
    return clamp(px, 0, 1), clamp(py, 0, 1)


def object_position(focus, size, ratio):
    px, py = position(focus, size, ratio)
    return f"{px * 100:.0f}% {py * 100:.0f}%"


def box_ratio(wanted, size, is_face):
    """The shape to cut: what the page asks for, except that a face in a portrait photo is never squeezed into a strip wider
    than 4:3 (a 16:9 or 2:1 window of a head-and-shoulders portrait is the forehead and nothing else; 3:2 still cuts a tight portrait through the eyes)."""
    if is_face and size and size[1] > size[0] and ratio_value(wanted) > FACE_MAX_RATIO:
        return "4/3"
    return wanted


def ratio_value(r):
    """"16/9" or 1.78 to a float."""
    if isinstance(r, str):
        a, _, b = r.partition("/")
        return float(a) / float(b or 1)
    return float(r)
