# Sheepy Tab Bar icon prompts

Mode: built-in `image_gen`, generation with references. Every icon used both
`sheepNormal.png` (character reference) and `AppIcon.png` (product-style reference).
The corrected pet pass also used the user's screenshot as the authoritative visual
reading of Sheepy.

## Shared constraints

```text
Use case: stylized-concept
Asset type: one standalone iOS Tab Bar template-image pixel glyph
Create exactly one centered 8-bit pixel icon on a 16 x 16 square-cell design grid.
Use one visible color only: pure black #000000. The canvas background must be genuine
alpha-0 transparency. Each design cell is either fully opaque black or fully
transparent. Keep at least one empty cell of margin on every side. Use hard square
stair-step edges. No checkerboard, white background, grey, partial alpha,
anti-aliasing, gradients, outlines, strokes, shadows, highlights, text, or watermark.
Output a 1024 x 1024 PNG with alpha. The silhouette must remain clear at 25 pt.
```

## `tabNow`

```text
A front-facing desk lamp: a wide stepped trapezoid lampshade, narrower on top and wider
below; exactly three short evenly spaced vertical light-ray blocks underneath; a
centered two-cell-wide post; and a wider flat base. Left-right symmetrical. No desk,
bulb, cord, or surrounding scene.
```

## `tabPet`

```text
Translate the authoritative Sheepy screenshot into a one-color template glyph while
preserving its stepped wool silhouette, squared face proportions, square eye spacing,
and blocky side ears. Convert the white wool into a solid black fluffy head; convert
the central black face into a large transparent horizontal rectangular cutout; convert
the two white eyes into exactly two solid black square eyes inside that cutout. Keep
one small solid black ear protruding outside each side at face height. Head only: no
body, legs, nose, mouth, horns, inner-ear holes, or line work.
```

## `tabWeekly`

```text
A compact chart of exactly four equal-width vertical bars on a common invisible
baseline, separated by one empty grid cell. Heights from left to right: short, medium,
tallest, medium. Flat tops. No axes, drawn baseline, labels, dots, rounded corners, or
chart frame.
```

## `tabSettings`

```text
Exactly three evenly spaced horizontal sliders. Each row has a one-cell-tall square-end
bar spanning most of the width and a two-cell-wide square knob taller than the bar.
Knob positions: top right of center, middle left of center, bottom near the right end.
No circles, gear, switches, labels, border, or panel.
```
