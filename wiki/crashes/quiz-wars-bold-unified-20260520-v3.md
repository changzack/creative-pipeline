# Crash: quiz-wars-bold-unified-20260520-v3
- **Date:** 2026-05-20T16:01:12-0700
- **Verdict:** degraded
- **Phase at terminal:** unknown
- **Cost at crash:** $4.26
- **Last successful node:** __interrupt__
- **Iterations completed:** qa=20, judge=0, playability=0

## Symptom (auto-classified)
failed_max-on-all

## Last exception (if any)
```
N/A
```

## Retry-loop detection
QA-LOOP-STUCK detected: 42 cycles in log, max iter=20 (iter likely not advancing); PLAYABILITY-LOOP-STUCK detected: 60 cycles in log, no polish_iterations recorded for this loop

## Cost trajectory
- start: $20.00 (💰 Cost circuit breaker set to $20.00)
- start: $4.26 (💰 Total cost: $4.26)
- start: $0.88 (approach_gate: $0.8880)
- start: $1.02 (asset_gen: $1.0260)
- start: $0.74 (builder: $0.7487)
- start: $0.16 (diversification: $0.1675)
- start: $1.42 (playability: $1.4293)
- start: $0.16 (⚠️  cost telemetry drift at wiki_ingest: state.cost_usd=$0.1675 vs _run_costs.total_usd=$4.2595 (epsilon=$0.01). Using c)

## Last 50 log lines (raw)
```
     ✅ end-to-end complete on iteration 1
  ✅ concept-1: complete after 1 iter(s) [gpt-5]
     iter 1/1 [gemini]: rounds=5/5, perf=True, share=True, states=8, errors=0
     ✅ end-to-end complete on iteration 1
  ✅ concept-2: complete after 1 iter(s) [gemini]
[QA-LOOP] (unified) Running qa on 3 concepts
  ❌ concept-0: qa FAIL — verdict=BROKEN — max iter (20) reached
  ❌ concept-1: qa FAIL — verdict=FIXABLE — max iter (20) reached
  ❌ concept-2: qa FAIL — verdict=FIXABLE — max iter (20) reached
[QA-LOOP] (unified) Status: 0 pass | 0 pending | 3 failed_max | 0 cost_circuit
  → qa_loop: polish_loop_qa
[JUDGE-LOOP] (unified) Running judge on 3 concepts
Error while fetching prompt 'judge_score-label:production': status_code: 404, body: {'message': "Prompt not found: 'judge_score' with label 'production'", 'error': 'LangfuseNotFoundError'}
  ⚠️  Langfuse prompt fetch failed for 'judge_score' — falling back to file (status_code: 404, body: {'message': "Prompt not found: 'judge_score' with label 'production'", 'error': 'LangfuseNotFoundError'})
  📜 prompt 'judge_score' loaded from local file
  ⏭ concept-0: skipped (qa_status=failed_max)
  ⏭ concept-1: skipped (qa_status=failed_max)
  ⏭ concept-2: skipped (qa_status=failed_max)
[JUDGE-LOOP] (unified) Status: 0 above_bar | 0 pending_polish | 3 failed_max | 0 cost_circuit
  → judge_loop: polish_loop_judge
[PAIRWISE-RANK] 0 survivors, 3 non-survivors
[PAIRWISE-RANK] Final ranking:
  #1 — concept 0 (claude-opus) — status=failed_max wins=0 weighted=?
  #2 — concept 1 (gpt-5) — status=failed_max wins=0 weighted=?
  #3 — concept 2 (gemini) — status=failed_max wins=0 weighted=?
  → pairwise_rank: pairwise_rank_complete

============================================================
HUMAN GATE — Iteration 0
============================================================
  #1 — Concept 0 (claude-opus) — 0 wins
  #2 — Concept 1 (gpt-5) — 0 wins
  #3 — Concept 2 (gemini) — 0 wins

💰 Total cost: $4.26
   approach_gate: $0.8880
   asset_gen: $1.0260
   builder: $0.7487
   diversification: $0.1675
   playability: $1.4293
  📁 Eval app generated locally: /Users/zackchang/.openclaw/workspace/overnight-runs/quiz-wars-bold-unified-20260520-v3/eval/index.html

Builds at: /Users/zackchang/.openclaw/workspace/overnight-runs/quiz-wars-bold-unified-20260520-v3/builds
Eval app: /Users/zackchang/.openclaw/workspace/overnight-runs/quiz-wars-bold-unified-20260520-v3/eval/index.html
============================================================

  → __interrupt__: (Interrupt(value={'action': 'taste_gate', 'ranking': [{'rank': 1, 'build_index': 0, 'wins': 0, 'judge_status': 'failed_max', 'weighted_total': None, 'index': 0, 'designer_id': 0, 'model': 'claude-opus', 'path': '/Users/zackchang/.openclaw/workspace/overnight-runs/quiz-wars-bold-unified-20260520-v3/builds/concept-0.html', 'exists': True, 'size': 31646873, 'status': 'done', 'compliance': {'pass': True, 'failures': [], 'warnings': [], 'checks': 0}, 'asset_validation': {'matched': ['dither-field-(cyan-magenta-base)', 'dither-field-(magenta-saturated-for-reveal)', 'dither-field-(orange-hazard,-timer-low)', 'ghost-opponent-runner-sprite', 'pixel-checkmark-sprite-(correct)', 'pixel-x-sprite-(wrong)', 'badge:-legendary-(chromatic)', 'badge:-streak-flame-(dark-variant)'], 'missing': [], 'extra_in_manifest': []}, 'qa_fix_attempts': 20}, {'rank': 2, 'build_index': 1, 'wins': 0, 'judge_status': 'failed_max', 'weighted_total': None, 'index': 1, 'designer_id': 1, 'model': 'gpt-5', 'path': '/Users/zackchang/.openclaw/workspace/overnight-runs/quiz-wars-bold-unified-20260520-v3/builds/concept-1.html', 'exists': True, 'size': 39564024, 'status': 'done', 'compliance': {'pass': True, 'failures': [], 'warnings': [], 'checks': 0}, 'asset_validation': {'matched': ['cabinet-canvas-bg', 'dither-wipe-mask', 'badge-perfect-sparkle', 'badge-streak-flame', 'ghost-opponent-sprite', 'pixel-check-glyph', 'pixel-cross-glyph', 'badge-legend-crown'], 'missing': [], 'extra_in_manifest': []}, 'qa_fix_attempts': 20}, {'rank': 3, 'build_index': 2, 'wins': 0, 'judge_status': 'failed_max', 'weighted_total': None, 'index': 2, 'designer_id': 2, 'model': 'gemini', 'path': '/Users/zackchang/.openclaw/workspace/overnight-runs/quiz-wars-bold-unified-20260520-v3/builds/concept-2.html', 'exists': True, 'size': 5827330, 'status': 'done', 'compliance': {'pass': True, 'failures': [], 'warnings': [], 'checks': 0}, 'asset_validation': {'matched': ['player-avatars-(15-variants-—-broadcast-portrait)', 'badge-icons-(5-variants-—-monochrome,-flat-broadcast)', 'daily-reset-countdown-frame', 'broadcast-pattern-(very-subtle,-optional-accent)'], 'missing': [], 'extra_in_manifest': ['player-flair-tiles-(5-variants)']}, 'qa_fix_attempts': 20}], 'pairwise_results': [], 'builds_dir': '/Users/zackchang/.openclaw/workspace/overnight-runs/quiz-wars-bold-unified-20260520-v3/builds', 'eval_url': '/Users/zackchang/.openclaw/workspace/overnight-runs/quiz-wars-bold-unified-20260520-v3/eval/index.html', 'iteration': 0, 'message': 'Review builds at eval app: /Users/zackchang/.openclaw/workspace/overnight-runs/quiz-wars-bold-unified-20260520-v3/eval/index.html. Submit verdict.json to run dir, then resume.'}, id='d77d94fefc84f1ec1a11aaada0cd01a0'),)
  ⚠️  cost telemetry drift at wiki_ingest: state.cost_usd=$0.1675 vs _run_costs.total_usd=$4.2595 (epsilon=$0.01). Using canonical.
  📚 Wiki ingested: runs/quiz-wars-bold-unified-20260520-v3.md + log + model pages
  📚 Terminal wiki ingest complete (verdict=completed)
```

## State snapshot at crash
- polish_iterations: {'qa': {0: 20, 1: 20, 2: 20}, 'judge': {0: 0, 1: 0, 2: 0}}
- polish_status: {'qa': {0: 'failed_max', 1: 'failed_max', 2: 'failed_max'}, 'judge': {0: 'failed_max', 1: 'failed_max', 2: 'failed_max'}}
- build count: 3
- builder_mode: qa_fix

## Linked lessons
(Mira will populate this via a separate cross-link pass.)

## See also
- [[runs/quiz-wars-bold-unified-20260520-v3]] (full run page)
