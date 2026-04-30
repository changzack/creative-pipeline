# Retro: Sharecard Exploration — Build Convergence

**Date:** 2026-04-30
**Project:** Rerank Share Card Reimagination
**Failure:** Three independent creative concepts produced visually similar builds despite divergent approach docs

---

## What Happened

- 3 approach docs with genuinely different creative directions (Magazine Cover, Ticker, Trading Card)
- 3 parallel Hermes builders, each with a unique approach doc
- Outputs converged: all three look like "numbered list on dark background with GSAP animations"
- Zack couldn't tell them apart in the viewer

## Root Causes

### 1. Same model = same aesthetic defaults
All 3 builders were Opus. Same model = same code patterns, same CSS habits, same "safe" visual choices. Convergence is structural, not accidental.

### 2. Placeholder images removed the primary differentiator
The approach docs specified different color systems, but all relied on product imagery to carry the color. Gray placeholder squares made all three look identical in tone.

### 3. Skipped Phase 0.5 (Visual Research)
No moodboard, no reference screenshots. Builders interpreted metaphors ("PSA graded card", "Solari departure board") from text only. Without visual targets, they defaulted to their own (shared) aesthetic.

### 4. Builder briefs were too abstract
"Follow the approach doc" isn't prescriptive enough for code generation. The approach docs describe FEELINGS ("mechanical", "premium", "collectible") but not specific CSS techniques, gradient values, or texture implementations.

### 5. No model diversity
Three Opus instances = three copies of the same taste. Different models (Gemini, GPT-4) would bring different aesthetic priors.

## What We Should Have Done

1. **Phase 0.5 (Visual Research)** — Screenshot 3-5 real references per concept. The Vault Card builder should have SEEN a PSA graded slab, not just read about one.

2. **Real product images** — Use actual sneaker photos from Unsplash or the Complex CDN. Product imagery was supposed to be the color/life of each card.

3. **Prescriptive CSS in builder briefs** — Instead of "follow the approach doc," include explicit visual constraints:
   - "Vault Card MUST use: 4px sharp corners, metallic linear-gradient on borders, visible animated holographic shimmer via CSS hue-rotate, zero rounded corners"
   - "Countdown Tape MUST use: monospaced type, visible grid lines, amber glow via box-shadow, letter-by-letter DOM animation"
   - "Monument MUST use: full-bleed image with object-fit cover, vignette via radial-gradient overlay, 280px ghost text behind hero"

4. **Builder persona injection** — Give each builder a different technical personality:
   - Builder 1: "You love CSS gradients, SVG filters, and blend modes"
   - Builder 2: "You love clean geometry, sharp edges, and monospace type"
   - Builder 3: "You love texture, noise, grain, and layered depth"

5. **Different models per builder** (if available) — Structural diversity beats prompt diversity for visual output.

## Changes to Make

### CREATIVE-PIPELINE.md
- Phase 0.5 (Visual Research) should be MANDATORY, not skippable
- Builder briefs must include: specific CSS techniques, texture requirements, and at least 3 screenshot references
- Add "Builder Differentiation Checklist" — before spawning builders, verify each has unique visual constraints

### AGENTS.md
- Add lesson: "Approach doc divergence ≠ build divergence. The approach gate catches creative convergence. We also need a BUILD DIFFERENTIATION gate that checks builder inputs include unique visual constraints, not just unique concepts."

### hermes-bridge/SKILL.md
- Add pattern: "For creative builds, always include reference images and prescriptive CSS constraints in the task file. Text-only briefs converge."

---

## Metrics

- Approach doc divergence: HIGH (3 genuinely different metaphors, palettes, animations)
- Build divergence: LOW (visually similar dark-bg layouts)
- Gap: Creative direction worked. Execution converged.
- Cost of the failure: ~$15 in API calls + 30 min of Hermes build time on builds that didn't differentiate

## Key Lesson

**Divergent ideas don't guarantee divergent implementations.** The approach gate catches idea convergence. We need a parallel gate for implementation divergence — checking that builder inputs contain enough prescriptive visual detail (CSS techniques, reference images, texture specs) to produce genuinely different outputs.
