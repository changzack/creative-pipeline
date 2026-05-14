# Pipeline Feature: Playability Loop

Status: **deprecated** (2026-05-13) — superseded by [[builds/unified-builder]]
Scope: was a separate graph node between `qa_station` and `judge`
File: `pipeline.py` — `playability_loop_node` was removed; helpers (`_playability_*`) preserved and reused by the unified builder.

> **Why deprecated:** The original playability loop used a single shared patch model (Claude Opus) across ALL concepts and gave the prompt explicit permission to "hide pre-existing UI elements and replace them." First production run collapsed all 3 distinct concepts onto identical generic UIs. The fix is architectural: route playability fixes back through the original builder per concept (Opus → Opus patch, GPT-5 → GPT-5 patch, Gemini → Gemini patch), in the same model voice, anchored to the original approach doc. See [[builds/unified-builder]] for the new pattern.


## What it does
After QA finishes and before the judge runs, every build (except QA-BROKEN ones) goes through a surgical-patch loop:

1. Walk the build (reusing `walk_experience`) and run a fresh DOM-text scan for completion markers (round counter, performance reveal, share card).
2. Merge walker + DOM signals into a per-build completion telemetry dict.
3. If the build is end-to-end complete → stop, mark `complete`.
4. Otherwise, extract the relevant code chunks (script blocks + button markup, with base64 assets stripped to `data:image/png;base64,[ASSET]` placeholders) and ask Claude Opus 4.7 for a single `<script>` patch that closes the gap.
5. Append the patch as a `<script>` block right before `</body>` (never rewrites the file). Back up the pre-patch file as `concept-N.pre-playability-iter{it}-{ts}.html`.
6. Repeat up to `MAX_PLAYABILITY_ITERATIONS` (default 3, overridable via `--playability-iter`) per build. Final scan after exhausting budget.

After all builds are processed, `eval/builds/` is re-synced with `builds/` so the eval app shows the patched files.

## Why
The walker (introduced earlier today) showed the judge journey screenshots, but for multi-screen game-style briefs many builds still failed end-to-end gameplay on the first try (stuck at round 1, missing performance reveal, missing share card). Sending the judge a half-broken experience meant they were grading splash screens vs splash screens. The standalone `iterate-playability.py` script proved the concept; this node folds it into the LangGraph state machine so:

- Iterations appear in Langfuse traces under a `playability_loop` span (with per-build + per-iteration sub-spans + per-patch generation entries).
- Costs are tracked in the run's cost rollup under phase `playability`.
- State is checkpointed in SQLite (resumable on crash).
- The `iterate` decision at the human gate re-enters the loop for newly-built concepts.
- Per-build status (`complete`/`partial`/`failed`/`skipped`) is visible in run state and `playability-summary.json`.

## State additions (`PipelineState`)
- `playability_signals: Dict[int, dict]` — per-build final telemetry (rounds, perf, share, console errors).
- `playability_iterations: Dict[int, int]` — per-build iteration count used.
- `playability_status: Dict[int, str]` — `complete` | `partial` | `failed` | `skipped`.
- `playability_patches: Dict[int, list]` — per-build patch metadata (bytes, backup filename, timestamp per iteration).
- `playability_max_iter: Optional[int]` — per-run override for `MAX_PLAYABILITY_ITERATIONS`.

All four `Dict` fields use a custom `_merge_dict` reducer (passing `{}` resets, otherwise shallow-merge by key — matches the existing list-reset convention used for `approaches`/`builds`).

## Brief inference
The node short-circuits to `skipped` for non-multi-step briefs (no `round`/`step`/`question`/`game` language). For multi-step briefs it parses:
- `min_rounds` — first `\d+ (rounds|customers|steps|levels|screens|questions)` match, clamped to 2–20, default 5.
- `needs_performance` — any of `performance reveal`, `results screen`, `total profit`, `final score`, `game over`, `p&l`, `end-of-game`, etc.
- `needs_share` — any of `share card`, `share button`, `copy link`, `shareable`, `social card`, etc.

This keeps the loop generic — brief-driven, not concept-specific.

## Skip conditions
- QA verdict is `BROKEN` (no point patching what's already flagged for human review).
- Build file is missing or under 500 bytes.
- Brief isn't multi-step (no rounds/screens/steps language detected).

## Tuning knobs (module constants)
- `MAX_PLAYABILITY_ITERATIONS` — default per-build iteration cap (default 3).
- `PLAYABILITY_MIN_ROUNDS` — fallback rounds requirement when brief doesn't specify (default 5).
- `PLAYABILITY_CODE_MAX_CHARS` — max code context shipped to the patch model (default 90 000).
- `PLAYABILITY_PATCH_MIN_BYTES` — reject patches shorter than this (default 500, likely garbage if smaller).
- CLI: `--playability-iter N` on `run` (sets `state["playability_max_iter"]`). `0` disables the loop entirely.

## Cost impact
- Per non-broken build: 0–`max_iter` Opus 4.7 calls (~$0.50–$2.50 each at 128K output cap).
- Per pipeline run with 3 builds: typically $1–$6 extra on top of existing builder/judge cost.
- Wall time: ~30 s walker+scan + ~30 s Opus generation per iteration → up to ~3 min per concept at max iter.

## Patch discipline
- Append-only — never rewrites the original file. Patch is wrapped in `<!-- AUTO-PATCH: iter HH:MM:SS -->` markers so subsequent iterations can detect and supersede prior patches.
- Pre-iteration backup saved as `concept-N.pre-playability-iter{it}-{ts}.html` next to the build.
- Base64 asset blobs stripped from the code-context payload (otherwise a 15 MB HTML file would blow the patch model's input budget).
- Frontier model only: `resolve_model("claude-opus")` → `claude-opus-4-7` with `max_output_for(model)` budget.

## Verification
- Smoke imports: `from pipeline import playability_loop_node, build_graph, PipelineState` → OK.
- Graph wiring: `qa → playability_loop → judge` (old `qa → judge` edge removed).
- Compile w/ SqliteSaver: OK.
- Existing `iterate-playability.py` imports (`RUNS_DIR, walk_experience, max_output_for, resolve_model`) still resolve cleanly.

## Operational signals
- `playability-summary.json` in the run dir summarizes status, iterations, signals, and patch metadata per build.
- `iter-logs/concept-N-iterlog.json` per build has the per-iteration signal dumps + patch byte counts + backup filenames.
- Langfuse: `playability_loop` span with `playability_build_N` sub-spans, each containing `playability_iter_N_M` and `playability_patch_N_iterM` (generation) entries.

## Future work
- Make completion thresholds fully brief-driven via a `## Outcome Requirements` frontmatter section (currently inferred via regex on the brief body).
- Allow per-iteration patch model fallback (e.g., GPT-5.5) if Anthropic is unhealthy.
- Surface playability iteration count + final signals per build in the eval app.
- Wiki ingest hook to log "playability iterations required" as a per-run build-quality metric.
