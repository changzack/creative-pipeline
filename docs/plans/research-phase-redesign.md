# Research Phase Redesign — V3d Retro

## Problem Statement
The research phase is performative. The agent screenshots aggregator listing pages (Dribbble search results, Behance grids) instead of actual designs. Screenshots are half-loaded due to lazy loading. No design tokens are extracted. VISUAL-RESEARCH.md isn't even written because the agent runs out of iterations. Designers receive garbage and design from training data instead.

## Evidence (V3d)
- 5 moodboard files, ALL are aggregator listing pages
- ~80-90% of thumbnails in screenshots are unloaded (black/gray rectangles)
- No VISUAL-RESEARCH.md was written (agent hit 40 iteration limit)
- No design tokens extracted (no hex values, no font names, no spacing)
- Agent log confirms: hit max iterations, never completed the research doc

## Root Causes
1. **Task doesn't distinguish "search" from "analyze"** — agent treats finding references and analyzing them as one step
2. **No explicit instruction to click INTO designs** — agent stays on search results pages
3. **No lazy-loading awareness** — screenshots taken before content renders
4. **40 iterations insufficient** — agent wastes most iterations navigating aggregator UIs
5. **No quality gate on screenshots** — half-loaded pages are accepted as "done"
6. **Hermes isn't great at browser tasks** — the design-research skill was built for Mira's browser, not Hermes

## Proposed Solution: Two-Stage Research

### Option A: Move research back to Mira (orchestrator)
Since Mira has direct browser control, she can:
- Navigate to actual design sites
- Wait for full page load
- Screenshot at specific viewports
- Extract CSS values via browser console
- Quality-gate every screenshot

The research node would become an orchestrator task, not a Hermes delegation.

### Option B: Curated reference library + brief-specific lookup
Instead of searching every run, maintain a curated library of high-quality reference screenshots with extracted tokens. The research phase becomes a lookup/selection task rather than a discovery task. New references get added during skill evolution, not during pipeline runs.

### Option C: Hybrid — Mira does discovery, Hermes does analysis
Mira finds and screenshots 8-10 references using her browser.
Hermes receives the screenshots and writes VISUAL-RESEARCH.md with deep analysis.
Plays to each agent's strengths.

## Recommendation: Option C (Hybrid)
- Mira already has browser tools and screenshot capabilities
- Hermes is good at analysis/writing but bad at browser navigation
- This also reduces Hermes iterations (analysis only = ~10 iterations vs 40+ for discovery)
- Cost stays similar since Mira's browser work doesn't consume LLM tokens the same way

## Implementation Changes
1. `research_node` becomes a Python function that uses Playwright directly (no Hermes)
2. Search queries → visit individual design pages → wait for load → screenshot → extract tokens
3. Pass screenshots to Hermes (or LLM vision) for token extraction + VISUAL-RESEARCH.md
4. Quality gate: verify each screenshot has >50% pixel variance (not blank/half-loaded)
5. Output: high-quality VISUAL-RESEARCH.md with real extracted tokens

## Key Rules for Research Phase
- NEVER screenshot search results / listing pages — always click into individual designs
- ALWAYS wait 3+ seconds after page load for lazy content to render
- ALWAYS scroll to trigger below-fold content before screenshotting
- VERIFY each screenshot is fully rendered (check for placeholder/skeleton UI)
- Extract REAL CSS values from browser console, don't guess
- Budget: 8-12 references, not 5 half-loaded ones
