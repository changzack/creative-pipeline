# Pipeline Feature: Unified Builder (with playability mode)

Status: active (introduced 2026-05-13)
Scope: refactor — `builder_node` is now dual-mode; the separate `playability_loop_node` was removed
Supersedes: [[builds/playability-loop]]
File: `pipeline.py` — `builder_node`, `_builder_playability_run`, `fan_out_playability_mode`, `route_after_qa`, `route_after_builder`

## What it does
One `builder_node` handles both phases of HTML generation:

- **mode="initial"** — write a fresh prototype from the approach doc (original behavior).
- **mode="playability"** — continue an existing build by appending `<script>` patches until the experience is end-to-end playable, in the SAME model voice that did the initial build.

A new fan-out helper (`fan_out_playability_mode`) emits one parallel `Send("builder", …)` per build with `builder_mode="playability"` and `builder_model` pulled from `build["model"]`. Each concept's playability patches are made by ITS original builder model (Opus → Opus patch, GPT-5 → GPT-5 patch, Gemini → Gemini patch), with the original approach doc included in the prompt as creative anchor.

Graph layout:
```
research → designer (×3 fan-out)
  ↓
approach_gate → asset_gen
  ↓ (fan-out via fan_out_builders, mode="initial")
builder (×3 parallel)
  ↓ (conditional via route_after_builder: builder_mode == "initial" → qa)
qa
  ↓ (conditional via route_after_qa: returns Sends to builder in playability mode, or "judge" if disabled)
builder (×3 parallel, mode="playability")
  ↓ (conditional via route_after_builder: builder_mode == "playability" → judge)
judge → human_gate → [approve|iterate|reject]
```

## Why
The original `playability_loop_node` used a single shared patch model (Claude Opus) for all 3 concepts and allowed it to "hide pre-existing UI elements and replace them." The first production run produced 3 identical generic UIs — the patcher converged each concept onto the same safe local optimum. Root cause: no model-voice anchor and no creative anchor.

Fix:
1. **Continuity** — Each concept's patch is made by its original builder model. Opus continues in Opus's voice; GPT-5 continues in GPT-5's voice; Gemini in Gemini's.
2. **Creative anchor** — The original approach doc is included in the patch prompt. Mechanics, palette, tone all come from the same source the initial build drew from.
3. **No "DO NOT replace" rules** — The legacy prompt's negative rules backfired when the patcher legitimately needed to refactor. The new prompt uses positive framing: "Continue building this experience in the same voice."
4. **No duplicate code** — Builder routing logic (Anthropic streaming / OpenAI sync / Google GenAI sync) is shared between modes via `_call_playability_patch_model`.
5. **Smaller diff for future modes** — When we add `mode="human_feedback"` for the iterate path, it's just another branch in the same node.

## State additions / changes
Kept from the legacy loop (still used by both modes):
- `playability_signals: Dict[int, dict]` — per-build final telemetry.
- `playability_iterations: Dict[int, int]` — per-build iteration count.
- `playability_status: Dict[int, str]` — `complete | partial | failed | skipped`.
- `playability_patches: Dict[int, list]` — per-build patch metadata.
- `playability_max_iter: Optional[int]` — per-run override.

Added:
- `builder_mode: Optional[str]` — `"initial" | "playability"`. Defaults to `"initial"` if absent. Set per-`Send` by fan-out functions; written back by `builder_node` as a routing signal for `route_after_builder`.

`iterate_node` now also resets `builder_mode` to `None` so the next pipeline pass starts fresh in initial mode.

## Routing
Two new conditional-edge routers replace the old direct edges:

- `route_after_qa(state)` — returns either a list of `Send("builder", …)` (one per build, all in playability mode) or the literal `"judge"` when playability is disabled (`playability_max_iter == 0`) or no builds exist.
- `route_after_builder(state)` — returns `"qa"` if `state["builder_mode"] != "playability"`, else `"judge"`. Reads the merged-state `builder_mode` written by all parallel `builder` invocations in the current pass (all parallel sends in a single pass write the same value, so the merged read is well-defined).

## Skip / short-circuit conditions (per-build, in `_builder_playability_run`)
- QA verdict is `BROKEN` (no point patching what's flagged for human review).
- Build file is missing or under 500 bytes.
- Brief isn't multi-step (no rounds/screens/steps language detected via `_playability_infer_requirements`).
- Build dict not found in state.

Whole-fan-out short-circuit (in `route_after_qa` / `fan_out_playability_mode`):
- `playability_max_iter == 0`
- `len(state["builds"]) == 0`

## Per-concept model selection
`fan_out_playability_mode` passes `builder_model = build["model"]` for each build. `build["model"]` is set during the initial builder pass to one of `claude-opus | gpt-5 | gemini-3.1-pro` (the same canonical aliases used by `fan_out_builders`). `_call_playability_patch_model` dispatches on the resolved model family:
- `claude-*` → Anthropic streaming (`messages.stream`) — preserves the legacy loop's streaming UX for long outputs.
- `gpt-*` → OpenAI `chat.completions.create` (sync).
- `gemini-*` → Google GenAI `generate_content` (sync).

All three paths call `track_cost(..., phase="playability")` for clean cost rollups.

## Tuning knobs (module constants, unchanged from legacy loop)
- `MAX_PLAYABILITY_ITERATIONS` — default per-build iteration cap (default 3).
- `PLAYABILITY_MIN_ROUNDS` — fallback rounds requirement when brief doesn't specify (default 5).
- `PLAYABILITY_CODE_MAX_CHARS` — max code context shipped to the patch model (default 90 000).
- `PLAYABILITY_PATCH_MIN_BYTES` — reject patches shorter than this (default 500).
- CLI: `--playability-iter N` on `run` (sets `state["playability_max_iter"]`). `0` disables the playability fan-out entirely.

## Patch discipline (unchanged from legacy)
- Append-only — never rewrites the original file. Patch wrapped in `<!-- AUTO-PATCH: iter HH:MM:SS -->` markers so subsequent iterations can detect and supersede prior patches.
- Pre-iteration backup saved as `concept-N.pre-playability-iter{it}-{ts}.html` next to the build.
- Base64 asset blobs stripped from the code-context payload.
- Frontier models only via `resolve_model()` / `max_output_for()`.

## What changed vs the deprecated loop
| Concern | Old (`playability_loop_node`) | New (`builder_node` + playability mode) |
|---|---|---|
| Patch model | Single shared `claude-opus` for all concepts | Each concept's original builder model |
| Approach doc in prompt | No | Yes — primary creative anchor |
| Concurrency | Sequential per build inside one node | Parallel fan-out via `Send` (mirrors initial fan-out) |
| Prompt style | Negative rules ("DO NOT replace…") | Positive framing ("continue your work…") |
| Graph nodes | One extra node (`playability_loop`) | None — same `builder` node, branched on `builder_mode` |
| Routing | Direct edges `qa → playability_loop → judge` | Conditional edges `qa → [builder|judge]` + `builder → [qa|judge]` |
| Cost phase | `playability` | `playability` (unchanged) |

## Verification (2026-05-13)
- `py_compile` clean.
- Imports OK: `builder_node`, `build_graph`, `fan_out_playability_mode`, `route_after_qa`, `route_after_builder`, `_builder_playability_run`, `PipelineState`.
- Graph builds and compiles with `SqliteSaver`.
- Edges wired: `playability_loop` node is GONE; `qa → [builder, judge]` and `builder → [qa, judge]` confirmed.
- Existing `iterate-playability.py` imports (`RUNS_DIR, walk_experience, max_output_for, resolve_model`) still resolve cleanly (script is otherwise obsolete and slated for deletion).

## Future work
- Add `mode="human_feedback"` so the iterate path also routes back through `builder_node` with the human's feedback as another anchor.
- Wiki-ingest playability iteration counts per run.
- Add per-mode metadata to all Langfuse spans (already in span input dicts; just needs to be surfaced in eval app).
- Delete `iterate-playability.py` once we confirm no scripts/crons reference it.
