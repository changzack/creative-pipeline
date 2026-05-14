# QA Loop + Judge Polish Loop — Architecture (2026-05-13)

**Status:** Implemented, not yet smoke-tested in a real run.
**Plan source:** `memory/plans/qa-judge-loop-refactor.md`
**Backup:** `pipeline.py.before-qa-judge-loops`

## What changed

Replaced the previous `qa_station → playability_loop → pairwise_judge_node → human_gate` flow with two clean, per-concept, threshold-gated loops plus a final ranking pass:

```
       builder (initial × 3)
            │
            ▼
       qa_loop  ◀──┐
            │     │ qa_fix patches (per concept, original model)
            ▼     │
      need fix? ──┘
            │
            │ all pass / failed_max / cost_circuit
            ▼
      judge_loop  ◀──┐
            │       │ judge_polish patches (per concept, original model)
            ▼       │
      above bar? ───┘
            │
            │ all above_bar / failed_max / cost_circuit
            ▼
      pairwise_rank   (only among survivors, purely for ordering)
            │
            ▼
       human_gate
```

## Loops

### QA Loop (`qa_loop_node`)

Folds together the legacy `qa_station_node`'s structural checks **and** the legacy `playability_loop`'s walker-driven completion check.

- Per-concept, parallel. Each concept iterates independently.
- Each iteration runs: source checks (content fidelity, dimensions, spec compliance, asset references, design system compliance) + experience checks (Playwright render, console errors, mobile viewport, image loading) + **walker journey** (interactive elements found, clicks attempted, state changes, multi-step completeness for round-based briefs).
- If verdict is FIXABLE or BROKEN AND we're under `MAX_QA_ITERATIONS` (default 20) → mark `qa_status="pending"` and route back to `builder` in `builder_mode="qa_fix"`.
- The `qa_fix` patch reuses `_builder_playability_run` as the patch driver with `playability_max_iter=1` (one patch per outer-loop visit), so the surgical-patch model and per-concept-model rule from the unified-builder refactor still apply.
- Iteration counter (`qa_iterations`) is bumped by the builder wrapper, not the loop, so the count reflects patches actually attempted.

### Judge Polish Loop (`judge_loop_node`)

The first place where **per-build scoring** happens. Replaces the win-counting role of the old pairwise judge.

- Uses the REVIEWER persona (live file: `~/.openclaw/workspace/skills/creative-technologist/personas/REVIEWER.md`) compiled into a new prompt: `prompts/judge_score.txt`.
- Per-concept, parallel. Each build is scored independently with structured JSON output (per-dimension scores + Priority Fixes + weighted total).
- Hybrid pass threshold (configurable via CLI):
  - `weighted_total >= 7.0`
  - every dimension >= `5.0`
  - `ai_slop_flagged != true` (hard-cap)
  - `renders_and_runs == true` (binary tech gate)
- If a concept fails AND we're under `MAX_JUDGE_ITERATIONS` (default 20) → mark `judge_status="pending_polish"` and route back to `builder` in `builder_mode="judge_polish"`.
- The `judge_polish` patch uses a new prompt (`_judge_polish_build_patch_prompt`) that anchors to the original approach doc and embeds the REVIEWER's Priority Fixes verbatim, so feedback is fed straight back into the same builder voice.

### Pairwise Rank (`pairwise_rank_node`)

Runs the legacy bidirectional pairwise tournament — but **only on `above_bar` survivors**, purely for ordering. Non-survivors are appended at the bottom of the final ranking with their (failing) weighted scores so the eval app can still display them.

If <= 1 survivor exists, this node skips the tournament and emits a trivial ranking.

## Per-concept-model routing

Same rule as the unified builder refactor: **concept N is only ever patched by concept N's original builder model.**

- `fan_out_qa_fix` and `fan_out_judge_polish` both pull `build["model"]` to set `builder_model` on each `Send`.
- This preserves the model-as-creative-voice continuity across all patch iterations.

## Cost circuit breaker

`MAX_COST_USD` (default 20.0, override via `--max-cost`) is now a *soft* breaker:

- `track_cost()` no longer raises when the budget is exceeded — it logs once and leaves the breaker bit in `_run_costs`.
- `_cost_circuit_broken(state)` is called at the top of each loop iteration. If true:
  - The current loop marks every still-pending concept as `cost_circuit`.
  - Routes short-circuit to the next stage (qa_loop → judge_loop → pairwise_rank → human_gate).
- `cost_circuit_broken` is also tracked in `PipelineState` so it survives across loop iterations and graph nodes.

## State additions

New fields on `PipelineState`:

```python
# QA Loop
qa_iterations: Dict[int, int]           # per-concept iteration count
qa_status: Dict[int, str]               # "pass" | "failed_max" | "cost_circuit" | "pending"
qa_reports_by_concept: Dict[int, dict]  # latest report per concept
qa_max_iter: Optional[int]

# Judge Polish Loop
judge_scores: Dict[int, dict]
judge_polish_iterations: Dict[int, int]
judge_status: Dict[int, str]            # "above_bar" | "pending_polish" | "failed_max" | "cost_circuit"
judge_max_iter: Optional[int]
judge_threshold: Optional[dict]

# Cost breaker
cost_circuit_broken: Optional[bool]
```

All Dict fields use the `_merge_dict` reducer (shallow merge, right wins, `{}` resets).

The legacy `qa_reports` list and `playability_*` fields are retained for back-compat with eval-app readers and the old wiki-ingest path.

## CLI flags (new)

```
--qa-iter N                 # default 20, set 0 to skip QA loop
--judge-iter N              # default 20, set 0 to skip judge polish loop
--max-cost USD              # default 20.0
--judge-threshold-total X   # default 7.0
--judge-threshold-min-dim X # default 5.0
```

`--playability-iter N` is kept as a deprecated alias (the QA loop now owns this scope).

## Builder modes

`builder_node` dispatches on `state["builder_mode"]`:

- `"initial"` — write a fresh prototype from the approach doc.
- `"qa_fix"` — surgical patch driven by QA report issues + walker signals. Reuses `_builder_playability_run` internals.
- `"judge_polish"` — surgical patch driven by REVIEWER's Priority Fixes. New `_builder_judge_polish_run`.
- `"playability"` — legacy alias for `qa_fix` (kept for back-compat with checkpointed runs).

## Prompts

New: `prompts/judge_score.txt` — per-build scoring prompt. Includes `{{persona}}` placeholder for REVIEWER injection. Asks for structured JSON output with `scores`, `weighted_total`, `priority_fixes`, `verdict`, `ai_slop_flagged`, `renders_and_runs`.

Existing `prompts/judge_system.txt` is **kept** — used by `pairwise_rank_node` for the final tie-breaker ordering pass after thresholds.

## REVIEWER.md — proposed change staged for human review

A draft update to `REVIEWER.md` is staged at `REVIEWER.md.proposed`:

- Adds **Brief Fit** (20%) and **Distinctiveness** (10%) as new weighted dimensions
- Rebalances: Creative Ambition 40 → 30, Visual Depth 15 → 10, Typography 10 → 5, Hierarchy & Readability 10 → 5
- AI Slop stays at 20% with hard-cap
- Technical Execution removed from weighted total → binary "renders and runs" gate

The new `judge_score.txt` works with either the current OR proposed REVIEWER weights — the persona is loaded verbatim via `{{persona}}`. If Zack approves the proposed weights, replace `REVIEWER.md` with `REVIEWER.md.proposed` and the new dimensions land automatically on the next run.

## Rollback path

1. `cp pipeline.py.before-qa-judge-loops pipeline.py`
2. `rm pipeline.py.pyc`
3. The legacy `pairwise_judge_node_legacy` + `qa_station_node` + `fan_out_playability_mode` are still present and functional in the current pipeline.py — you could also re-wire `build_graph()` to use them without restoring from backup.
4. `prompts/judge_score.txt` and `REVIEWER.md.proposed` are additive — leaving them in place causes no harm to a rolled-back run.
