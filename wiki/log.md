# Pipeline Wiki Log

## [2026-05-13] pipeline | QA Loop + Judge Polish Loop refactor
Replaced `qa_station → playability_loop → pairwise_judge → human_gate` with two clean per-concept threshold-gated loops: `qa_loop` (folds in playability completion checks; up to 20 iter/concept; routes back to `builder` in mode=qa_fix) and `judge_loop` (per-build scoring against REVIEWER persona via new `prompts/judge_score.txt`; hybrid threshold weighted≥7.0 AND min-dim≥5.0 AND no AI slop; up to 20 iter/concept; routes back to `builder` in mode=judge_polish). After both loops complete, `pairwise_rank` does the bidirectional tournament only among above-bar survivors purely for ordering. Per-concept-model rule preserved across both loops (concept N is only ever patched by concept N's original builder model). Cost circuit breaker (MAX_COST_USD, default $20, soft-breaker via `_cost_circuit_broken()`) gracefully halts both loops without unwinding the graph. New CLI flags: `--qa-iter`, `--judge-iter`, `--max-cost`, `--judge-threshold-total`, `--judge-threshold-min-dim`. REVIEWER.md weight-rebalance (Brief Fit + Distinctiveness as new dimensions) **staged** at `REVIEWER.md.proposed` for human review — not applied. Legacy `pairwise_judge_node_legacy` + `qa_station_node` + `_builder_playability_run` kept in place for fast rollback. Backup: `pipeline.py.before-qa-judge-loops`. Details: [[builds/qa-judge-loops-2026-05-13]].

## [2026-05-03] bootstrap | Wiki initialized
Seeded from: techniques.json (11 techniques, 8 verdicts, 5 learnings), calibration-set.json (15 ratings), retro notes, run logs from V1 through V3k.

## [2026-05-03] ingest | Sharecard V1 (3 concepts)
Monument (bad), Countdown Tape (acceptable), Vault Card (bad). Gold gradient convergence. All 3 used same dark+gold palette.

## [2026-05-03] ingest | Sharecard V2 (3 concepts)
Pressure Print (bad), The Mint (bad), Timing Tower (bad). Zack: "V2 is worse." Quality didn't improve from V1.

## [2026-05-03] ingest | Smoke Test (3 concepts)
Fight Card (acceptable), Press Run (bad), Weigh-In (bad). Builder 1 received empty approach doc (race condition), improvised output matching Builder 0.

## [2026-05-03] ingest | Ranking Experiment (3 concepts)
Chain Reaction (acceptable), Swipe Duels (bad), Spectrum (bad).

## [2026-05-03] ingest | Quiz V3 (3 concepts)
Pile Up (acceptable), Bleed Through (acceptable), Seismic (acceptable). Best run — all 3 acceptable. Most iterated AND most creatively ambitious.

## [2026-05-03] ingest | V3b-V3k pipeline runs
V3b: reject (brief drift — Spotify Wrapped clones). V3c: reject (convergence — all boxing posters). V3d: iterate (performative research). V3e: reject (designers burned turns on browser research). V3f: iterate (flat output despite rich approach docs). V3g: first QA station run. V3h: model upgrades (GPT-5.4, Gemini 3.1 Pro). V3i: full context caps removed. V3j: asset gen skipped (missing FAL_KEY). V3j-b: first successful asset generation run. V3k: first SMPLX design system constrained run.

## [2026-05-13] pipeline | Playability Loop added between QA and judge
New `playability_loop` graph node folds the previously standalone `iterate-playability.py` into the LangGraph state machine. Sits between `qa_station` and `judge`. For each non-BROKEN build, scans completion signals (walker + DOM-text regex for round counter / performance reveal / share card), and if the experience isn't end-to-end playable, generates a targeted `<script>` patch via Claude Opus 4.7 and appends it to the build HTML (never rewrites). Repeats up to `--playability-iter N` (default 3) times per build. Skips non-multi-step briefs entirely. State additions: `playability_signals/iterations/status/patches` (`_merge_dict` reducer), `playability_max_iter`. CLI: `--playability-iter` on `run`. Eval app builds are re-synced after the loop. Iterations appear in Langfuse under a `playability_loop` span; costs tracked under phase `playability`. The `iterate` path resets playability state so each pass starts fresh. Backup: `pipeline.py.before-playability-loop`. Details: [[builds/playability-loop]].

## [2026-05-13] pipeline | Experience Walker added to judge node
Generic Playwright walker now clicks through every build before pairwise judging, captures journey screenshots, and surfaces dead/inert-prototype signals to the judge. Judge prompt updated to evaluate both visual quality across the journey AND experience cohesion — brief-agnostic language. QA station unchanged. Smoke-tested against V4c share cards: all three produced 2-3 screenshot journeys (Reset/Play/Replay controls), no errors. Motivation: judging multi-screen experiences (games, quizzes, flows) on a single landing screenshot is broken. Backups: `pipeline.py.backup-before-walker`, `prompts/judge_system.txt.backup`. Details: [[builds/experience-walker]].

## [2026-05-04] ingest | V3k-SMPLX — FIRST STRUCTURED EVAL + FIRST "GREAT" RATING
**Verdict: iterate | Best: Concept 0 (Claude Opus)**
- Concept 0 (Opus): 🔥 GREAT — hierarchy 5/5, type 4/5, slop 4/5. Texture on text hurt readability. Background graphic "cool but random."
- Concept 1 (GPT-5.4): Unrated — built wrong deliverable (quiz vs ranking). Ambition 4/5 but hierarchy 2/5.
- Concept 2 (Gemini): Unrated (positive) — "Really great transition and motion design." Ambition 4/5, hierarchy 5/5. Brand concern.
**Key learnings routed:** Texture-on-text → anti-patterns. Motion design → what-scores-well. Brief drift → anti-patterns. Hierarchy > ambition → what-scores-well.

## [2026-05-13] pipeline | Unified builder with playability mode (replaces playability_loop_node)
Refactor: `builder_node` is now dual-mode (`builder_mode == "initial" | "playability"`). The standalone `playability_loop_node` was removed; its per-build logic was lifted into `_builder_playability_run`, called from `builder_node` when `builder_mode == "playability"`. A new `fan_out_playability_mode` helper emits one parallel `Send("builder", …)` per build, mirroring the initial `fan_out_builders` pattern. Each concept's playability patches are now made by ITS ORIGINAL builder model (Opus → Opus patch, GPT-5 → GPT-5, Gemini → Gemini) via `_call_playability_patch_model`, with the original approach doc included in the prompt as creative anchor. Graph routing changed: `qa → playability_loop → judge` direct edges became conditional edges `qa → [builder | judge]` (via `route_after_qa`) and `builder → [qa | judge]` (via `route_after_builder`, branching on `builder_mode`). State schema added `builder_mode: Optional[str]`. Prompt rewritten with positive framing ("continue your work in your original voice") replacing the legacy "DO NOT replace existing UI" rules. Motivation: the first production run of the legacy playability loop converged all 3 concepts onto identical generic UIs because a single shared patch model was given permission to hide/replace existing UI. The fix is architectural: same model voice + approach-doc anchor preserves per-concept distinctness. Backup: `pipeline.py.before-unified-builder`. The walker / signal-scan / prompt-build / patch-apply `_playability_*` helpers were preserved. `iterate-playability.py` is now obsolete (will be deleted manually). Details: [[builds/unified-builder]]. Deprecates: [[builds/playability-loop]].

## [2026-05-13] build | three-bugs-fix
Fixed three pipeline bugs from sneaker-game-v1 retro: (A) per-brief diversification axes via Claude Opus call at end of research_node, replacing hardcoded share-card-shaped eras; (B) two-tier wiki context (global-taste-rules.md + per-brief LEARNINGS.md sibling) cuts injected context from 8K → 1.6K chars and ends cross-brief contamination; (C) post-build asset:// validation with SVG fallback + NEEDED_ASSETS.md surfacing. Backup: pipeline.py.before-three-bugs-fix. See builds/three-bugs-2026-05-13.md.
