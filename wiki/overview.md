# Pipeline Wiki — Overview

## Current State (as of V3k-smplx, May 3, 2026)

### Pipeline Maturity
- **12+ runs** completed (V1, V2, Smoke Test, Ranking Exp, Quiz V3, V3b-V3k)
- **15 builds rated** by creative director: 0 great, 6 acceptable, 9 bad
- **$0.83-$1.70** per run (3 concepts, research through judge)
- **~30-40 min** per run end-to-end

### Biggest Insight
The #1 predictor of a build being rated "acceptable" is **physical metaphor + creative ambition**. 4 of 6 acceptable builds used physical metaphors (tape, stacking, ink bleed, seismograph). 0 of 9 bad builds had strong metaphors — they were all "dark card + text + animation."

### Current Strengths
- Multi-model diversity (Opus + GPT-5.4 + Gemini)
- Asset generation via fal.ai (textures, graphics — product shots blocked by trademark filter)
- QA station catches content fidelity, mobile viewport, console errors
- Design system enforcement (`--design-system` flag)
- Bidirectional pairwise judging
- Experience walker (added 2026-05-13) — judge sees an ordered journey of screenshots per build, plus dead/inert-prototype signals. Brief-agnostic. See [[builds/experience-walker]].

### Current Weaknesses
- **No "great" builds yet** — acceptable is the ceiling (V3k-SMPLX got the first 'great' — still rare)
- **Asset generation limited** — trademark filtering blocks product shots (highest-value asset)
- **Design system compliance** — builders ignore constraints even when told to enforce (V3k: GPT used Space Grotesk)
- **Evaluation loop** — human feedback doesn't compound automatically yet (this wiki is the fix)
- **Walker doesn't drive sliders/keyboard inputs intelligently** — builds with precise-value controls need click-driven fallbacks

### What Would Move the Needle
1. **Fix product shot generation** — rephrase prompts to avoid brand names
2. **Tighter evaluation → wiki feedback loop** — every verdict enriches the wiki, every run reads the wiki
3. **More calibration data** — 15 ratings isn't enough; need 30-50 for reliable taste model
4. **Push creative ambition harder** — the pipeline produces "solid B+" work but not "A" work
