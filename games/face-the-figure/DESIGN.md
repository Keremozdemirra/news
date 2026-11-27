---
name: Assay
description: A brass beam balance on a stone counter in a cobalt-tiled assay office, weighing paper tickets. Porcelain plates, 3px black trim, one needle-lacquer red.
colors:
  bench: "#e9e7df"
  room: "#0d1a3d"
  surface: "#f6f5f0"
  paper: "#fbfbf9"
  ink: "#15171a"
  ink-soft: "#575b5f"
  trim: "#15171a"
  rule: "#cfcfc6"
  lacquer: "#b5330f"
  lacquer-ink: "#ffffff"
  right: "#2f7a3f"
  wrong: "#8a1c1c"
  stamp-ink: "#15171a"
  stamp-soft: "#6b6864"
typography:
  signage:
    fontFamily: "\"Big Shoulders Display\", \"Arial Narrow\", Impact, sans-serif"
    fontSize: "2.75rem"
    fontWeight: 900
    lineHeight: 0.95
    letterSpacing: "0.005em"
  counter:
    fontFamily: "\"Big Shoulders Display\", \"Arial Narrow\", Impact, sans-serif"
    fontSize: "3.25rem"
    fontWeight: 900
    lineHeight: 1
    letterSpacing: "0.01em"
  headline:
    fontFamily: "\"Big Shoulders Display\", \"Arial Narrow\", Impact, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 700
    lineHeight: 1
  body:
    fontFamily: "\"Barlow\", \"Helvetica Neue\", Arial, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "\"Barlow Semi Condensed\", \"Arial Narrow\", Arial, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "0.16em"
  stamp:
    fontFamily: "\"Courier Prime\", \"Courier New\", Courier, monospace"
    fontSize: "0.75rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "0.06em"
rounded:
  none: "0"
  full: "50%"
components:
  key:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.signage}"
    rounded: "{rounded.none}"
    height: "76px"
  button-primary:
    backgroundColor: "{colors.lacquer}"
    textColor: "{colors.lacquer-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    height: "52px"
    width: "100%"
  ticket:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    width: "128px"
  plate:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
---

# Design System: Assay

## Overview

**Creative North Star: "The Assay Balance"**

Face the Figure is a beam balance on the counter of an assay office. Two paper tickets stand in the two pans; the left one is printed, the right one is sealed. The player says which pan will sink, the seal is cut, the number counts up on the ticket, and the beam swings to the truth. The room and the balance are the only picture in the product: a real model, built and rendered in Blender (a wall of hand-set cobalt tiles, a stone counter, one window of light), with no CSS-drawn shapes standing in for any of it. Everything around the picture is a porcelain plate: enamel-white ground, 3px black trim, square corners, and one accent, the lacquer red of the needle.

The system is flat and hard-edged, the same family as Favent (the Fotoautomat) and kept apart from it by object, palette and type roles. Brass and gunmetal live only inside the rendered balance; the UI imitates no metal with gradient.

**Key Characteristics:**
- One real scene (the balance in its room) rendered; everything else flat.
- The room is the colour: cobalt tile, brass, black enamel, white stone. The plates stay porcelain so the picture carries it.
- Porcelain ground, 3px black trim, zero border-radius, circles only for round things (needle boss, coins).
- One accent, the needle lacquer: the needle in the art, and the single lit primary button of a screen.
- Paper tickets are paper: they alone carry a shadow, and they stay white.
- Four self-hosted OFL faces with one job each.

## Colors

- **Bench** (`#e9e7df`): the page and the plates above the picture.
- **Room** (`#0d1a3d`): the flat navy behind the room plate, seen only where a very wide screen runs past it.
- **Plate Surface** (`#f6f5f0`): keys, plates, the end-of-game rows.
- **Ticket Paper** (`#fbfbf9`): a ticket. Fixed; paper is paper.
- **Ink** (`#15171a`): text and `--trim`, the 3px structure.
- **Soft Ink** (`#575b5f`): labels, meta, captions. 6.4:1 on Bench.
- **Hairline Rule** (`#cfcfc6`): dividers inside a plate.
- **Needle Lacquer** (`#b5330f`): the one accent. 5.3:1 on Bench; white text on it 5.6:1.
- **Right** (`#2f7a3f`) and **Wrong** (`#8a1c1c`): the ink of the verdict stamp and its pip, and nothing else.

**The One Needle Rule.** Lacquer red is the needle in the render and exactly one lit button per screen (Open the ledger, Next figure, Share). Higher and Lower are plain keys; red is not a side.
**The Paper Is Paper Rule.** `paper`, `stamp-ink` and `stamp-soft` stay fixed. There is one scheme (light) and no dark variant to keep in step.
**The No-Gloss Rule.** No gradient, no glow, no inner highlight, no bevel in CSS. Gloss exists where a real brass part reflects a studio, and that is in the render.

## Typography

- **Signage** Big Shoulders Display 900, uppercase: wordmark, ticket figures, key words, the end score.
- **Plate / Body** Barlow 400/600 for running copy and verdict lines; **Barlow Semi Condensed 600** tracked caps for labels and buttons.
- **Stamp** Courier Prime 700, only for what is printed on a ticket: the source line, the RIGHT / WRONG stamp. Every other number (score, streak, countdown) is Barlow or signage with tabular figures.

## Layout

One centred column designed at 390 wide and scaled by the viewport (0.7 to 1.3), the same on a phone and at 1440. Top to bottom: trim bar with wordmark and sound key, a status line (streak, ten pips, score), the question, the room with the balance, a plate with the keys. The room is one plate four balance-frames wide: it runs off both sides of the column as a band of wall and counter, so a desktop gets the whole room and a phone gets its middle. Tickets are placed from the per-frame pan coordinates exported with the art. Structure is drawn with 3px trim rules above the plate and under the bar.

## Elevation & Depth

Flat except paper. A ticket carries the strip shadow (`0 1px 2px rgba(21,23,26,.12), 0 12px 22px -12px rgba(21,23,26,.45)`); the balance throws a real shadow on the counter, rendered per frame. **The Paper-Only Shadow Rule**: a shadow means paper, or the object is in the render.

## Shapes

Zero radius on every rectangle. Borders: 3px trim (structure), 2px (keys, plates, tickets), 1px hairline (rows). Circles: needle boss and coins, in the render and the end-screen tally only.

## The Balance (signature, rendered)

Black enamel foot and column, brass collars, brass beam with rivets, an ivory reading plate with ten ticks, a lacquer-red needle, two brass pans on three wires each. Orthographic camera 7 degrees above level, 900 x 880 px, Cycles, transparent. 49 beam angles from -12 to +12 degrees in half-degree steps; for each, a `back` layer (with the shadow it throws on the counter) and a `front` layer (the front half of each pan only) so a ticket stands inside the pan.

The room is a second pass through the same camera, without the balance: 13 rows of glazed cobalt tiles, each set a hair off flush with its own tint, grey grout, a speckled stone counter, and one window high on the left whose frame shades the ends of the wall. `art/build_scale.py` renders both passes (`plate` as the last argument renders the room), `art/pack.py` turns them into WebP, and `assets/art/scale.json` carries the projected pan rim and base per frame.

## Motion

Authored, not eased. A reveal is a short score, played once:

| t (ms) | Beat | What moves |
|---|---|---|
| 0 | Anticipation | beam dips 1.6 degrees toward A as the seal on B tears off |
| 120 to 1500 | Count | B counts up with a ratchet; the beam follows the running value, so it crosses level at the instant the count passes A |
| 1500 | Contact | the beam reaches its stop; the B ticket squashes (scaleY .94, then 1.03, then 1) in 160 ms |
| 1500 to 2100 | Follow-through | the beam overshoots 22 percent, comes back 9 percent, settles; tickets sway a degree behind it |
| 1700 | Secondary | the verdict stamp slams (scale 1.7 to 1 with a 9 degree twist, 140 ms, held); on a right call, coins leave the pan |
| after | Rest | nothing moves until the next round |

The HUD has no loop: no pulse, no shimmer, no idle bob. The only motion at rest is the beam finding its stop. `prefers-reduced-motion` and `?rm=1` skip the score: the final frame and the stamp appear at once.

## Do's and Don'ts

**Do** build every depth object in Blender and ship it as frames; keep the accent to the needle and one button; set measurements in Barlow and signage, printed things in Courier Prime; place tickets from the exported pan coordinates.
**Don't** round a rectangle; draw brass, glass, tile or enamel in CSS; set type on the tiles; add a glow, gradient or bevel; loop anything on the HUD; spend lacquer on a second emphasis.
