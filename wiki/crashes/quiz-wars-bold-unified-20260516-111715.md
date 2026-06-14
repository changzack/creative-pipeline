# Crash: quiz-wars-bold-unified-20260516-111715
- **Date:** 2026-05-16T12:15:58-0700
- **Verdict:** degraded
- **Phase at terminal:** unknown
- **Cost at crash:** $0.50
- **Last successful node:** __interrupt__
- **Iterations completed:** qa=2, judge=0, playability=0

## Symptom (auto-classified)
failed_max-on-all

## Last exception (if any)
```
N/A
```

## Retry-loop detection
QA-LOOP-STUCK detected: 6 cycles in log, max iter=2 (iter likely not advancing); PLAYABILITY-LOOP-STUCK detected: 6 cycles in log, no polish_iterations recorded for this loop

## Cost trajectory
- start: $25.00 (💰 Cost circuit breaker set to $25.00)
- start: $3.20 (💰 Total cost: $3.20)
- start: $0.84 (approach_gate: $0.8480)
- start: $0.70 (asset_gen: $0.7080)
- start: $0.73 (builder: $0.7336)
- start: $0.17 (diversification: $0.1734)
- start: $0.74 (playability: $0.7406)

## Last 50 log lines (raw)
```
     iter 1/1 [gpt-5]: rounds=5/5, perf=True, share=True, states=9, errors=0
     ✅ end-to-end complete on iteration 1
  ✅ concept-1: complete after 1 iter(s) [gpt-5]
     iter 1/1 [gemini]: rounds=5/5, perf=True, share=True, states=39, errors=1
     ✅ end-to-end complete on iteration 1
  ✅ concept-2: complete after 1 iter(s) [gemini]
[QA-LOOP] (unified) Running qa on 3 concepts
  ❌ concept-0: qa FAIL — verdict=BROKEN — max iter (2) reached
  ❌ concept-1: qa FAIL — verdict=FIXABLE — max iter (2) reached
  ❌ concept-2: qa FAIL — verdict=FIXABLE — max iter (2) reached
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
  #1 — concept 0 (claude-opus) — status=unknown wins=0 weighted=?
  #2 — concept 1 (gpt-5) — status=unknown wins=0 weighted=?
  #3 — concept 2 (gemini) — status=unknown wins=0 weighted=?
  → pairwise_rank: pairwise_rank_complete

============================================================
HUMAN GATE — Iteration 0
============================================================
  #1 — Concept 0 (claude-opus) — 0 wins
  #2 — Concept 1 (gpt-5) — 0 wins
  #3 — Concept 2 (gemini) — 0 wins

💰 Total cost: $3.20
   approach_gate: $0.8480
   asset_gen: $0.7080
   builder: $0.7336
   diversification: $0.1734
   playability: $0.7406
  📁 Eval app generated locally: /Users/zackchang/.openclaw/workspace/overnight-runs/quiz-wars-bold-unified-20260516-111715/eval/index.html

Builds at: /Users/zackchang/.openclaw/workspace/overnight-runs/quiz-wars-bold-unified-20260516-111715/builds
Eval app: /Users/zackchang/.openclaw/workspace/overnight-runs/quiz-wars-bold-unified-20260516-111715/eval/index.html
============================================================

  → __interrupt__: (Interrupt(value={'action': 'taste_gate', 'ranking': [{'rank': 1, 'build_index': 0, 'wins': 0, 'judge_status': 'unknown', 'weighted_total': None, 'index': 0, 'designer_id': 0, 'model': 'claude-opus', 'path': '/Users/zackchang/.openclaw/workspace/overnight-runs/quiz-wars-bold-unified-20260516-111715/builds/concept-0.html', 'exists': True, 'size': 45396214, 'status': 'done', 'compliance': {'pass': True, 'failures': [], 'warnings': [], 'checks': 0}, 'asset_validation': {'matched': ['result-card-sparkle-asset'], 'missing': [], 'extra_in_manifest': ['ghost-opponent-sprite-pack-(3-silhouettes)', 'complex-wordmark-lockup-(cabinet-edition)', 'cabinet-plastic-texture-(used-as-svg-filter,-but-a-real-asset-version-improves-quality)', 'pixel-art-badge-tier-icons-(3-tiers)', 'leaderboard-avatar-set-(20-fictional-players)', 'paper-marquee-texture-(smplx-side-body)']}, 'qa_fix_attempts': 2}, {'rank': 2, 'build_index': 1, 'wins': 0, 'judge_status': 'unknown', 'weighted_total': None, 'index': 1, 'designer_id': 1, 'model': 'gpt-5', 'path': '/Users/zackchang/.openclaw/workspace/overnight-runs/quiz-wars-bold-unified-20260516-111715/builds/concept-1.html', 'exists': True, 'size': 45862845, 'status': 'done', 'compliance': {'pass': True, 'failures': [], 'warnings': [], 'checks': 0}, 'asset_validation': {'matched': [], 'missing': [], 'extra_in_manifest': ['daily-plate-backdrop-(q4-reveal-background)', 'complex-quiz-wars-mark-(logo-lockup-for-share-card-top-left)', 'avatar-default-(monogram-fallback)', 'share-card-edge-bleed-mark-(bottom-right-corner-of-q5)', 'badge-glyph-set-(3-monochrome-diamond-marks)']}, 'qa_fix_attempts': 2}, {'rank': 3, 'build_index': 2, 'wins': 0, 'judge_status': 'unknown', 'weighted_total': None, 'index': 2, 'designer_id': 2, 'model': 'gemini', 'path': '/Users/zackchang/.openclaw/workspace/overnight-runs/quiz-wars-bold-unified-20260516-111715/builds/concept-2.html', 'exists': True, 'size': 8012370, 'status': 'done', 'compliance': {'pass': True, 'failures': [], 'warnings': [], 'checks': 0}, 'asset_validation': {'matched': ['avatar-pile-—-diverse-user-headshots', 'ghost-opponent-sprite-—-tamagotchi-style', 'leaderboard-row-avatar-set', 'smplx-share-card-edge-bleed', 'pixel-art-badge-sprites-—-legendary-tier'], 'missing': [], 'extra_in_manifest': ['chromatic-glow-sheet-—-bonus-stamp-halos', 'background-texture-—-dark-canvas-static-noise']}, 'qa_fix_attempts': 2}], 'pairwise_results': [], 'builds_dir': '/Users/zackchang/.openclaw/workspace/overnight-runs/quiz-wars-bold-unified-20260516-111715/builds', 'eval_url': '/Users/zackchang/.openclaw/workspace/overnight-runs/quiz-wars-bold-unified-20260516-111715/eval/index.html', 'iteration': 0, 'message': 'Review builds at eval app: /Users/zackchang/.openclaw/workspace/overnight-runs/quiz-wars-bold-unified-20260516-111715/eval/index.html. Submit verdict.json to run dir, then resume.'}, id='8e80b07b04292ce8d732ecfa1669aba0'),)
  📚 Wiki ingested: runs/quiz-wars-bold-unified-20260516-111715.md + log + model pages
  📚 Terminal wiki ingest complete (verdict=completed)
```

## State snapshot at crash
- polish_iterations: {'qa': {0: 2, 1: 2, 2: 2}, 'judge': {0: 0, 1: 0, 2: 0}}
- polish_status: {'qa': {0: 'failed_max', 1: 'failed_max', 2: 'failed_max'}, 'judge': {0: 'failed_max', 1: 'failed_max', 2: 'failed_max'}}
- build count: 3
- builder_mode: qa_fix

## Linked lessons
(Mira will populate this via a separate cross-link pass.)

## See also
- [[runs/quiz-wars-bold-unified-20260516-111715]] (full run page)
