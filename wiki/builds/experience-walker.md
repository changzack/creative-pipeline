# Pipeline Feature: Experience Walker

Status: active (introduced 2026-05-13)
Scope: judge node (QA station unchanged)
File: `pipeline.py` — `walk_experience`, `walk_builds`, `_select_journey_screenshots`

## What it does
Before pairwise judging, every build is walked by a Playwright-driven function that:
1. Loads the HTML at 1080×1920.
2. Discovers visible interactive elements (buttons, links, role=button, [onclick], cursor:pointer, etc.).
3. Clicks them BFS-style, capturing a screenshot after each click.
4. Detects whether each click produced a state change via a DOM-hash snapshot (visible text + visible element count + url/hash + title).
5. Flags `inert_prototype` (no clickable elements at all) or `dead_prototype` (clickable elements present but no state changes after several clicks).
6. Selects a representative ordered set of ≤8 journey screenshots, preferring screenshots that followed state changes.

The judge receives the ordered journey per artifact plus a one-line signal summary ("3 click(s) attempted, 2 produced state changes, 3 unique states visited"). The judge prompt instructs evaluation on both visual quality across the journey AND experience cohesion.

## Why
Before this change, the judge saw only a single landing-state screenshot per build. For static artifacts (e.g., share cards) this is fine; for multi-screen experiences (quizzes, games, flows) the judge was effectively grading splash screens. The walker generalizes the judge to any artifact type without baking artifact-specific logic into the pipeline.

## What the walker does NOT do
- Does not click drag/slider/keyboard inputs with target values. Sliders register as clickable but the walker only triggers a basic click — the build should still expose a click-driven fallback if a precise value matters.
- Does not assert specific routes, screen counts, or button labels — fully generic.
- Does not perform visual diffing across builds. Pairwise judging still owns comparison.

## Cost impact
- Walker run time: ~5-15s per build (vs ~2s for the prior single screenshot).
- Judge image count per pair: rose from 4-6 (moodboard + 2 builds) to ~10-18 (moodboard + 2 journeys × up to 8 screenshots each). Per-run judge cost on a 3-build run rises from ~$0.20 to ~$0.50-$1.00. Still cheap relative to builders.

## Operational signals
Each build emits a `walks/concept-N-walk.json` summary in the run directory plus per-step screenshots `walks/concept-N-step-NN.png`. Useful for debugging when the judge flags a build as non-functional.

## Tuning knobs (module constants)
- `WALKER_MAX_STEPS` — hard ceiling on clicks per build (default 25).
- `WALKER_MAX_SCREENSHOTS` — cap on screenshots passed to judge per build (default 8).
- `WALKER_STABILIZE_MS` — settle time after each click (default 600ms).
- `WALKER_INITIAL_SETTLE_MS` — settle time after page load (default 1500ms).

## Verification
Smoke-tested 2026-05-13 against V4c builds (share cards). Walker correctly found their Reset/Play/Replay controls, captured 2-3 screenshot journeys per build, zero console errors, zero walker errors.

## Future work
- Hoist walker into a shared cache so QA + judge reuse the same walk (currently runs once inside the judge node).
- Treat slider/drag/keyboard inputs more intelligently (target middle values, send Tab/Enter, etc.).
- Surface walker results in the eval app so humans see the same journey the judge saw.
