---
name: Topfloor
description: A brass floor indicator and a lift car on a Deco tower at dusk. Rendered brass, a painted skyline, flat ink plates.
colors:
  ink: "#0b1218"
  ink-2: "#111b21"
  brass: "#c7a25e"
  brass-hi: "#ecd49c"
  brass-lo: "#7d6330"
  cream: "#f2e9d3"
  muted: "#a9b5b3"
  cinnabar: "#e0644a"
  tier-lobby: "#aab2b6"
  tier-mezzanine: "#72b9a6"
  tier-corner-office: "#e3ac43"
  tier-penthouse: "#e8694d"
  tier-helipad: "#f7ecc8"
typography:
  display: { family: "Limelight", use: "title, questions, numerals on the dial and the odometer, the end floor" }
  text: { family: "Jost", weight: 400-600, use: "everything else; labels are 600 caps with 0.12 to 0.16em tracking" }
rounded: { none: "0", full: "50% (pips and the alarm lamp only)" }
---

# Design System: Topfloor

## The object

A lift in a Deco tower, seen from the street at dusk. Above the car hangs the floor indicator: a brass-bezelled dial with a needle and a three-wheel odometer. A rare answer sends the car up; the needle and the counter show how far. The skyline behind is a painted backdrop in flat poster colours that darkens to night as the car climbs.

## Rules

1. **The three brass things are rendered.** The dial (bezel, enamel face, odometer window), its needle and hub cap, the lift car in thirteen door positions, and the call button in two positions come out of Blender (`art/build_art.py`, packed by `art/pack.py`). CSS draws no brass: no metal gradient, no bevel, no glow, no drop shadow.
2. **Print is flat.** What is printed on the dial face (ticks, numerals, the five tier bands, the word FLOOR) is SVG over the render, because print has no depth.
3. **The backdrop is paint.** Sky, skyline, tower and street are flat vector shapes with one grain layer. The sky is the only gradient in the product.
4. **Chrome is a plate.** The header bar, the card, the answer slot and the buttons are flat ink plates with 2 to 3px brass trim and square corners. Circles are for pips and the alarm lamp.
5. **Colour means a tier.** The five tier colours appear on the dial band, the floor lamps, the pips and the end list, and nowhere as decoration.

## Layout

The dial and the car hang as low as the open card allows, so the street meets the top of the card and the sky takes the spare room. On a phone the card is the bottom of the screen; from 560px it is a framed plate 28px off the bottom. Everything scales with one factor from a 390 x 844 design.

## Motion (authored, not tweened)

| Move | Score |
|---|---|
| Doors | thirteen held frames; quick off the stop, slow into it; shut, the car takes a 1.5px knock sideways |
| Timer | the doors close one frame at a time over the 25 seconds; the alarm lens blinks for the last six |
| Departure | the car sinks 3px on its cable, rises 2px, then the world scrolls past |
| Needle | dips 2 degrees back against the stop, runs, overshoots the mark, swings back twice, rests |
| Arrival | the car rides 4px over the sill, drops 2.5px, settles |
| Stamp | slams once at 1.9x with a twist |

Nothing on the header, the card or the dial loops. Reduced motion: doors, needle and car jump to their final frame.

## The round (measured against Krillion in play, 2026-11-27)

- **Floor lamps.** Five lamps over the result (10, 30, 60, 85, 100) come on one at a time up to the answer's tier and stop there. The player sees where the answer landed and what was still above it.
- **The clock waits.** The doors open and the prompt is read for 1.5 s before the 25 s run.
- **One rule under the answer slot** runs out with the time; the closing doors say the same thing in the world.
- **A kind of thing is not an answer.** "supermarket" or "investment bank" is refused; `extras.json` `drop` keeps the list of them.
- **Examples read as names.** The rare example shown after a miss is drawn by date from the top tier's plain names, with its tier named.

## Keyboard up, reload, practice (2026-11-27)

- **The question card is never clipped.** With the phone keyboard open the card keeps its height and the dial and car shrink to stand in what is left; the header stays 44 px.
- **Each answer is saved as it lands**; a reload resumes on the next question at the floor reached.
- **A valid answer typed when the clock runs out counts.**
- **Practice building.** Seven prompts from the other lists, the same lift, nothing counted or shared.
- **Lists are wider than Wikidata's classes**: restaurant, pizzeria, bakery and cafe chains, beer brands, convenience chains, and `extras.json` `names` for real answers Wikidata has no item for.

## Do not

Brass or glass drawn in CSS, text-shadow, rounded rectangles, a vignette, a second accent colour, a tween on the needle or the doors.
