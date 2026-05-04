# Technique: SVG feTurbulence Grain

**Status:** proven

## Description
Inline SVG `<filter>` with `<feTurbulence>` creates organic film grain/noise texture overlaid on the design. Adds perceived craft quality — the difference between "digital" and "printed."

## Evidence
- Run: V1, Concept "Monument", rated **bad** — had grain but everything else was generic (grain alone doesn't save a bad concept)
- Run: Quiz V3, Concept "Bleed Through", rated **acceptable** — grain was part of an ink/print metaphor that worked holistically
- Run: V3j-b, Concept 0 (Opus) — film grain overlay generated as asset (117KB)

## Why It Works
- Breaks the "clean digital surface" that signals AI
- References physical media (film, print, paper)
- Subtle at 3-5% opacity but perceivable on close inspection
- Zero performance cost (SVG filter is GPU-accelerated)

## Implementation
```html
<svg style="position:fixed;width:0;height:0">
  <filter id="grain">
    <feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="4" />
    <feColorMatrix type="saturate" values="0" />
  </filter>
</svg>
<div class="grain-overlay" style="
  position: fixed; inset: 0; z-index: 9999;
  filter: url(#grain);
  opacity: 0.04;
  mix-blend-mode: overlay;
  pointer-events: none;
"></div>
```

## Gotchas
- `baseFrequency` controls grain size: 0.4-0.6 = visible dots, 0.8-1.0 = fine film grain
- Too high opacity (>8%) looks like a broken filter, not intentional grain
- Must use `pointer-events: none` or grain overlay blocks all clicks
- Gemini builders sometimes specify grain in approach but don't implement it (see [[gemini-3.1-pro]])

## Best Model
All models can implement this. The SVG is simple enough. The issue is whether they REMEMBER to include it.
