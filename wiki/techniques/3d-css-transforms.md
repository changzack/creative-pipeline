# Technique: 3D CSS Transforms / Perspective

**Status:** proven

## Description
Using CSS `perspective`, `transform: rotateX/Y/Z`, `translateZ()`, and `transform-style: preserve-3d` to create real depth — items at different z-levels, parallax layering, isometric views.

## Evidence
- Run: Quiz V3, Concept "Pile Up" (various), rated **acceptable** — 3D stacking was the core mechanic
- Run: Quiz V3, Concept "Seismic" (various), rated **acceptable** — depth layering for visual hierarchy
- Run: V3j, Concept 0 (Opus), rated **#1** — 3D elements, layered shadows
- Run: V3j-b, Concept 0 (Opus), rated **#1** — judge praised "sense of depth through layering and light effects"

## Why It Works
- Physically impossible in flat design → signals real craft
- Creates visual hierarchy through z-axis, not just size/color
- Makes viewers curious ("how did they do that?")
- References physical objects (stacks, layers, cards)

## Implementation
```css
.container {
  perspective: 1200px;
  transform-style: preserve-3d;
}
.item {
  transform: rotateY(-5deg) translateZ(20px);
  transition: transform 0.4s ease;
}
.item:nth-child(1) { translateZ(60px); }  /* hero item closest */
.item:nth-child(10) { translateZ(-40px); } /* last item furthest */
```

## Gotchas
- `translateZ()` values need to be tested — too much causes items to clip
- `backface-visibility: hidden` prevents flicker on rotation
- Mobile performance: keep perspective simple, avoid deep nesting
- See [[mobile-viewport]] for scaling issues with 3D + `transform: scale()`

## Best Model
Claude Opus — most likely to commit fully to 3D rather than using it as decoration.
