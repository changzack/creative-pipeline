# Three Pipeline Bugs — 2026-05-13

**Status:** shipped
**Date:** 2026-05-13
**Author:** Mira (subagent: three-pipeline-bugs-fix)
**Backup of pre-fix file:** `pipeline.py.before-three-bugs-fix`
**Plan:** `~/.openclaw/workspace/memory/plans/three-pipeline-bugs.md`

Three independent bugs uncovered during the sneaker-game-v1 retro. All three
landed in a single edit pass against `pipeline.py`, validated after each.

---

## Bug A — Hardcoded share-card-shaped designer eras

**Symptom:** `fan_out_designers()` shipped 3 hardcoded `era` strings that
literally said "the CARD should feel ALIVE" — which makes no sense for a
sneaker-game brief, an onboarding flow, a poster, etc. Designers were forced
to apply share-card framing to non-card artifacts → noisy diversification.

**Fix:** Added `generate_diversification_axes(state)` that calls Claude Opus
(`max_output_for(model, kind="verdict")`, ~16K tokens) right at the END of
`research_node`. The prompt is generic across artifact types — explicitly tells
the model to avoid card/list language and read the brief to pick fitting axes.

- Output: JSON list of 3 axes (`axis_name`, `era`, `anti_patterns`)
- State: new `diversification_axes: Optional[list]` in `PipelineState`
- Fan-out: `fan_out_designers()` now reads from `state["diversification_axes"]`,
  with `_LEGACY_DESIGNER_CONFIGS` as a fallback if the LLM call fails or
  returns malformed output
- Persist: `{run_dir}/diversification-axes.json` written for QA + human review
- Cost: tracked under `phase="diversification"`

**Files modified:** `pipeline.py` (research_node, fan_out_designers,
PipelineState, main initial_state)

---

## Bug B — Wiki context dumps cross-brief noise into every prompt

**Symptom:** `get_wiki_context(brief, max_chars=8000)` ignored `brief` and
loaded the same 8K chars of share-card-era lessons into every prompt —
"don't use cream/newsprint backgrounds" injected into a sneaker game prompt.
Cross-brief contamination + context bloat.

**Fix:** Two-tier context model.

- **Tier 1 (always):** `wiki/global-taste-rules.md` — ~1.6K chars of universal
  taste rules I wrote (no AI slop, real craft, hierarchy, texture & depth,
  push novel techniques, visible metaphor). This file replaces ~8K of
  share-card-era guidance.
- **Tier 2 (per-brief):** `<brief>.LEARNINGS.md` sibling file, written by
  `append_per_brief_learnings(state, verdict_data)` from
  `wiki_ingest_structured`. Accumulates run-by-run feedback specific to THIS
  brief. Capped at 5K chars; oldest blocks rotate off when over budget.

- `get_wiki_context()` now takes a `Path` (or None) instead of a brief string
- All 3 callers (`research_node`, `designer_node`, `builder_node`) use the new
  helper `_brief_path_from_state(state)` to extract the Path safely
- `PipelineState` gains `brief_path: Optional[str]`, populated in `main()`
  from `args.brief`
- The old `aesthetics/what-scores-well.md` + `anti-patterns.md` files stay
  on disk as human-browseable reference but are no longer auto-injected

**Files added:** `wiki/global-taste-rules.md`
**Files modified:** `pipeline.py` (get_wiki_context, PipelineState, main,
wiki_ingest_structured, all 3 callers)

---

## Bug C — Builder hallucinates `asset://` references silently

**Symptom:** Builder writes `<img src="asset://noise-texture-overlay">` for
assets the designer never commissioned. Post-process can't substitute them.
The HTML ships with broken `asset://` URLs → `ERR_UNKNOWN_URL_SCHEME` console
errors. Concrete proof: sneaker-game-v1 concept-1.html had 3 such refs:
`asset://noise-texture-overlay`, `asset://pixel-art-shop-name-sign`,
`asset://shoe-photo-—-air-jordan-4-retro-"bred"`.

**Fix:** Two parts.

1. **Strict contract in the builder prompt** — explicit list of available
   asset slugs and a hard rule: "DO NOT write `asset://made-up-name`. If you
   need something not commissioned, draw it inline with CSS/SVG or add it to
   `NEEDED_ASSETS.md`."

2. **Post-build validation step** in `builder_node`, AFTER the existing
   base64 replacement:
   - `validate_asset_references(html_path, manifest_path)` scans the HTML
     with a regex, percent-decodes slugs, strips image extensions, and
     compares against the manifest names.
   - Returns `{"matched": [...], "missing": [...], "extra_in_manifest": [...]}`
   - Missing refs trigger `apply_missing_asset_fallbacks()` which substitutes
     each unresolved `asset://X` with an inline striped-SVG data URI labelled
     "MISSING ASSET: X" so the user SEES what was missing instead of getting
     a broken image.
   - Mismatches surface in `{run_dir}/builds/concept-N-NEEDED_ASSETS.md` for
     the human gate.
   - Validation result is propagated into `build_out["builds"][0]["asset_validation"]`
     for QA reports.

**Files modified:** `pipeline.py` (new helpers
`_decode_asset_slug`, `validate_asset_references`,
`apply_missing_asset_fallbacks`; builder_node prompt + post-process)

---

## Validation

```bash
.venv/bin/python -c "import py_compile; py_compile.compile('pipeline.py', doraise=True); print('OK')"
# → OK

OPENAI_API_KEY=sk-fake PYTHONPATH=. .venv/bin/python -c \
  "from pipeline import build_graph, get_wiki_context, validate_asset_references, generate_diversification_axes, append_per_brief_learnings; print('imports OK')"
# → imports OK

OPENAI_API_KEY=sk-fake PYTHONPATH=. .venv/bin/python -c \
  "from pipeline import build_graph; g = build_graph(); print('graph OK', type(g).__name__)"
# → graph OK StateGraph
```

- **Bug C test:** `validate_asset_references` against the real
  `sneaker-game-v1/builds/concept-1.html` flagged all 3 known-missing refs
  AND identified the 8 commissioned assets the builder never used.
- **Bug B test:** `get_wiki_context(None)` returns 1,647 chars (down from
  8,000), contains zero share-card anti-patterns, and `get_wiki_context(brief)`
  correctly loads a sibling `LEARNINGS.md` when one exists.

---

## Deviations from plan

- `get_wiki_context()` accepts `None` (no brief_path) in addition to a `Path`.
  The original plan implied always-Path; staying permissive avoids breaking
  any future callers that don't have a brief on disk (e.g., ad-hoc resumes).
- For missing assets in Bug C, I went with the "Option A" default
  (SVG placeholder + NEEDED_ASSETS.md) rather than wiring an opt-in flag for
  auto-regen. Auto-regen mid-build is a much bigger architectural change and
  the plan listed it as opt-in only.
- Designer model rotation in Bug A is now a constant
  (`_DESIGNER_MODEL_ROTATION = ["claude-opus", "gpt-5", "gemini"]`) so the
  per-brief axes inherit the same 3-model spread the legacy configs used.
  The LLM call only chooses the axis content, not the model assignment.
