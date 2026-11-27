---
name: Tickerflip
description: A split-flap departure board in an exchange hall: dark lacquer wall, one brass frame, one lit amber state.
colors:
  wall: "#140d0a"
  cabinet: "#0c0807"
  brass: "#c9a05a"
  brass-hi: "#ecd49c"
  brass-lo: "#7a5f2b"
  amber: "#f6b73c"
  amber-hi: "#ffd58a"
  cream: "#f2e9d3"
  muted: "#b3a58c"
  face-empty: "#2a241f"
  face-typed: "#4a3e33"
  face-absent: "#17120f"
  face-present: "#2d2113"
  face-answer: "#f1e0b4"
typography:
  signage: { family: "Big Shoulders Display", weight: 800, use: "title, plate, buttons, counters, labels" }
  flap: { family: "Barlow Condensed", weight: 700, use: "letters on a flap, nothing else" }
  text: { family: "Libre Franklin", weight: 400-600, use: "instructions, meta, share text" }
  headline: { family: "Newsreader", weight: 600, use: "article headlines in the reveal only" }
rounded: { none: "0", full: "50% (lamps and the brand dot only)" }
---

# Design System: Tickerflip

## The object

A departure board in an old exchange hall, seen straight on. A lacquered wall, a brass picture rail, hanging lamps, and one brass-framed board of split-flap cells. The player is standing in front of it with a keypad. Everything on screen is either that object or a flat printed plate beside it.

## Rules (strict)

1. **Depth comes only from rendered art.** The hall wall and lamps, the brass frame, the flap cell housing and the shadow a falling flap throws are rendered in Blender (art/build_art.py) and shipped as sprites in assets/art/. CSS never draws a gradient fill, glow, bevel or drop shadow. The only CSS gradients are hard-stop hatch stripes, which are a pattern, not a surface.
2. **Flat plates for everything else.** Keys, buttons, the clue stamp, article cards, the share box: zero radius, 2 to 3px brass trim, flat fill. Circles are for lamps only.
3. **One lit colour.** Amber means lit: a correct cell, a correct key, the primary button, the clue lamp. It is never used for anything decorative.
4. **State is colour plus shape plus text.** Correct = solid lit amber flap + square. Present = half-lit flap (top amber, bottom dark, amber keyline) + diamond. Absent = recessed black flap + bar. Keys: used-absent are dashed and struck through. Every cell has an aria-label in words; the share line uses the same three shapes.
5. **The frame holds the board only** (and the intro card). Nothing else gets the brass frame.

## Type roles

Big Shoulders Display 800 is signage: title 60 to 66px, plate numbers, button labels, section labels in capitals with 0.1 to 0.2em tracking. Barlow Condensed 700 is only the letter on a flap, sized to 0.84 of the cell height. Libre Franklin is the voice of instructions and meta at 12.5 to 17px. Newsreader 600 sets the headline of an article in the reveal and nothing else.

## Motion (authored, not tweened)

Every move is held frames, not one eased tween (see art notes from the studio: anticipation, contact, follow-through, squash, secondary beat).

| Move | Frames |
|---|---|
| Cycling flap | squash 1, .67, .03 then .03, .7, 1 on held frames, 15 ms each, with the matching shading frame; the drum steps through the alphabet |
| Landing flap | lifts 2px (anticipation), squash .96, .64, .03, then rises .03, .47, .87, .99, overshoots 1.04, contact .97 with a 1px body nudge, settles 1.01, 1 (follow-through); the clack fires on contact |
| Flap light | one of six Blender-rendered shading frames, stepped with the squash |
| Row | tiles start 150 ms apart, 4 to 6 cycling flaps each, so the row lands as a ripple, not a block |
| Invalid word | four-beat shake on held frames |
| Win | the row hops once, tile by tile, 90 ms apart (secondary beat); the board never loops anything |
| Clue | the plate lamp lights; no motion |

HUD, keys, panels and the clock never loop or tween. Only the cells move. Reduced motion: no flaps, states appear at once, no shake, no hop.

## Do not

Brass gradients in CSS, glow, text-shadow, rounded rectangles, pills, emoji, a second accent colour, a centred hero. Do not put the answer anywhere the page can read before the finish (the data file stores it base64-reversed, which is obscurity, not secrecy).
