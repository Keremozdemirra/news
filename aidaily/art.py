"""Abstract plates: the printed picture of an article that has no usable photo, and the day's mark.

Each plate is deterministic (same article, same picture) and built from real values: the number of newsrooms sets the
number of strokes, the publish hour sets the rotation, the topic picks the pattern family (Markets parallel lines, Economy a
grid, Business stacked bars, Politics concentric arcs, World circles, Tech a dot matrix, AI contour lines, Culture waves).
Ink on paper, flat and crisp: strokes and fills are currentColor, so the same SVG is ink on white in the light theme and
paper on ink in the dark one. No gradients, no filters, no text, no colour.
"""
import hashlib
import math
import random


def rng(*parts):
    """A generator seeded from text: the same on every machine and Python version (Mersenne Twister random())."""
    return random.Random(int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest(), 16))


def f(x):
    return f"{x:.1f}".rstrip("0").rstrip(".")


def svg(body, w, h, cls="plate"):
    return (f'<svg class="{cls}" viewBox="0 0 {w} {h}" width="{w}" height="{h}" fill="currentColor" stroke="none" '
            f'preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">{body}</svg>')


def lines(r, n, w, h):
    """Markets: parallel lines, one stroke per newsroom group, in varying weight."""
    k = 5 + n * 3
    gap = h * 2.2 / k
    return "".join(f'<rect x="{f(-w)}" y="{f(-h * .6 + i * gap)}" width="{f(w * 3)}" height="{f(r.choice((2, 2, 4, 7, 11)))}"/>' for i in range(k))


def grid(r, n, w, h):
    """Economy: a grid whose size grows with the newsrooms, some cells filled."""
    c = 3 + n
    rows = max(3, round(c * h / w))
    cw, ch = w / c, h / rows
    out = "".join(f'<rect x="{f(i * cw)}" y="0" width="2" height="{h}"/>' for i in range(c + 1))
    out += "".join(f'<rect x="0" y="{f(j * ch)}" width="{w}" height="2"/>' for j in range(rows + 1))
    cells = [(i, j) for i in range(c) for j in range(rows)]
    r.shuffle(cells)
    out += "".join(f'<rect x="{f(i * cw + 2)}" y="{f(j * ch + 2)}" width="{f(cw - 2)}" height="{f(ch - 2)}"/>' for i, j in cells[:max(2, len(cells) // 4)])
    return out


def stacked(r, n, w, h):
    """Business: horizontal bars stacked on one another, of unequal length."""
    k = 3 + n * 2
    bh = h / k
    return "".join(f'<rect x="0" y="{f(i * bh + 3)}" width="{f(w * r.uniform(.25, 1))}" height="{f(bh - 6)}"/>' for i in range(k))


def arcs(r, n, w, h):
    """Politics: concentric arcs around a point on the edge, as many as the strokes allow."""
    k = 2 + n * 2
    cx, cy = w * r.choice((.15, .5, .85)), h * 1.05
    return "".join(f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(h * .2 + i * h * .95 / k)}" fill="none" stroke="currentColor" stroke-width="{f(r.choice((3, 5, 8)))}"/>' for i in range(k))


def circles(r, n, w, h):
    """World: overlapping circles."""
    k = 2 + n * 2
    return "".join(f'<circle cx="{f(r.uniform(w * .1, w * .9))}" cy="{f(r.uniform(h * .1, h * .9))}" r="{f(r.uniform(h * .12, h * .45))}" '
                   f'fill="none" stroke="currentColor" stroke-width="{f(r.choice((3, 6, 10)))}"/>' for _ in range(k))


def matrix(r, n, w, h):
    """Tech: a dot matrix with a wave switching dots on and off; denser with more newsrooms."""
    cols, rows = 26, round(26 * h / w)
    ph = r.uniform(0, 6.28)
    out = ""
    for c in range(cols):
        for j in range(rows):
            v = (math.sin(c * .45 + ph) + math.cos(j * .55 - ph)) / 2 + n * .06
            if v > -.15:
                out += f'<circle cx="{f((c + .5) * w / cols)}" cy="{f((j + .5) * h / rows)}" r="{f(1.5 + 4.5 * min(1, v + .3))}"/>'
    return out


def contours(r, n, w, h):
    """AI: nested wavy contour lines."""
    k = 3 + n * 2
    cx, cy = w * r.uniform(.3, .7), h * r.uniform(.3, .7)
    a, b = r.uniform(2, 5), r.uniform(0, 6.28)
    out = ""
    for i in range(k):
        rad = (i + 1) * min(w, h) * .62 / k
        pts = [(cx + (rad + rad * .12 * math.sin(a * t + b + i)) * math.cos(t) * 1.4, cy + (rad + rad * .12 * math.sin(a * t + b + i)) * math.sin(t)) for t in (j * math.pi / 30 for j in range(61))]
        out += '<path d="' + "".join(("M" if j == 0 else "L") + f"{f(x)} {f(y)}" for j, (x, y) in enumerate(pts)) + 'Z" fill="none" stroke="currentColor" stroke-width="3"/>'
    return out


def waves(r, n, w, h):
    """Culture: sine waves, one per stroke."""
    k = 3 + n * 2
    amp, freq, ph = h * r.uniform(.05, .12), r.uniform(1.5, 4), r.uniform(0, 6.28)
    out = ""
    for i in range(k):
        y0 = h * (i + 1) / (k + 1)
        pts = [(w * x / 60, y0 + amp * math.sin(freq * x / 60 * 6.28 + ph + i * .5)) for x in range(61)]
        out += '<path d="' + "".join(("M" if j == 0 else "L") + f"{f(x)} {f(y)}" for j, (x, y) in enumerate(pts)) + '" fill="none" stroke="currentColor" stroke-width="4"/>'
    return out


FAMILY = {"Markets": lines, "Economy": grid, "Business": stacked, "Politics": arcs, "World": circles, "Tech": matrix, "AI": contours, "Culture": waves}


def plate(topic, key, newsrooms, hour=0, w=600, h=400):
    """The plate for one article: topic picks the family, the id the drawing, newsrooms the strokes, the hour the rotation."""
    r = rng(topic, key)
    n = max(1, min(6, newsrooms))
    angle = (hour % 12) * 15 - 40
    body = FAMILY.get(topic, stacked)(r, n, w, h)
    return svg(f'<g transform="rotate({angle} {w // 2} {h // 2})">{body}</g>', w, h)


def barcode(counts, w=1240, h=72, cls="barcode"):
    """The day's mark: one thin bar per article, oldest to newest, as tall as the number of newsrooms that reported it."""
    counts = list(counts)
    if not counts:
        return ""
    step = w / len(counts)
    top = max(max(counts), 1)
    bw = max(1.5, step * .26)
    out = "".join(f'<rect x="{f(i * step + (step - bw) / 2)}" y="{f(h - 2 - (h - 4) * c / top)}" width="{f(bw)}" height="{f((h - 4) * c / top)}"/>' for i, c in enumerate(counts))
    return svg(out, w, h, cls)
