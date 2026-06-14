# Crash: unified-polish-smoke-20260516-072651
- **Date:** 2026-05-16T08:39:40-0700
- **Verdict:** killed
- **Phase at terminal:** unknown
- **Cost at crash:** $0.50
- **Last successful node:** qa_loop
- **Iterations completed:** qa=0, judge=0, playability=0

## Symptom (auto-classified)
SIGTERM

## Last exception (if any)
```
N/A — terminated by signal
```

## Retry-loop detection
PLAYABILITY-LOOP-STUCK detected: 24 cycles in log, no polish_iterations recorded for this loop

## Cost trajectory
- start: $5.00 (💰 Cost circuit breaker set to $5.00)

## Last 50 log lines (raw)
```
  🔧 concept-0: qa FAIL — verdict=BROKEN — will retry (iter 1/20)
  🔧 concept-1: qa FAIL — verdict=BROKEN — will retry (iter 1/20)
  🔧 concept-2: qa FAIL — verdict=BROKEN — will retry (iter 1/20)
[QA-LOOP] (unified) Status: 0 pass | 3 pending | 0 failed_max | 0 cost_circuit
  → qa_loop: polish_loop_qa
[PLAYABILITY 0] QA verdict BROKEN — skipping playability[PLAYABILITY 1] QA verdict BROKEN — skipping playability[PLAYABILITY 2] QA verdict BROKEN — skipping playability


[QA-LOOP] (unified) Running qa on 3 concepts
  🔧 concept-0: qa FAIL — verdict=BROKEN — will retry (iter 1/20)
  🔧 concept-1: qa FAIL — verdict=BROKEN — will retry (iter 1/20)
  🔧 concept-2: qa FAIL — verdict=BROKEN — will retry (iter 1/20)
[QA-LOOP] (unified) Status: 0 pass | 3 pending | 0 failed_max | 0 cost_circuit
  → qa_loop: polish_loop_qa
[PLAYABILITY 1] QA verdict BROKEN — skipping playability[PLAYABILITY 2] QA verdict BROKEN — skipping playability

[PLAYABILITY 0] QA verdict BROKEN — skipping playability
[QA-LOOP] (unified) Running qa on 3 concepts
  🔧 concept-0: qa FAIL — verdict=BROKEN — will retry (iter 1/20)
  🔧 concept-1: qa FAIL — verdict=BROKEN — will retry (iter 1/20)
  🔧 concept-2: qa FAIL — verdict=BROKEN — will retry (iter 1/20)
[QA-LOOP] (unified) Status: 0 pass | 3 pending | 0 failed_max | 0 cost_circuit
  → qa_loop: polish_loop_qa
[PLAYABILITY 0] QA verdict BROKEN — skipping playability
[PLAYABILITY 1] QA verdict BROKEN — skipping playability[PLAYABILITY 2] QA verdict BROKEN — skipping playability

[QA-LOOP] (unified) Running qa on 3 concepts
  🔧 concept-0: qa FAIL — verdict=BROKEN — will retry (iter 1/20)
  🔧 concept-1: qa FAIL — verdict=BROKEN — will retry (iter 1/20)
  🔧 concept-2: qa FAIL — verdict=BROKEN — will retry (iter 1/20)
[QA-LOOP] (unified) Status: 0 pass | 3 pending | 0 failed_max | 0 cost_circuit
  → qa_loop: polish_loop_qa
[PLAYABILITY 0] QA verdict BROKEN — skipping playability
[PLAYABILITY 1] QA verdict BROKEN — skipping playability[PLAYABILITY 2] QA verdict BROKEN — skipping playability

[QA-LOOP] (unified) Running qa on 3 concepts
  🔧 concept-0: qa FAIL — verdict=BROKEN — will retry (iter 1/20)
  🔧 concept-1: qa FAIL — verdict=BROKEN — will retry (iter 1/20)
  🔧 concept-2: qa FAIL — verdict=BROKEN — will retry (iter 1/20)
[QA-LOOP] (unified) Status: 0 pass | 3 pending | 0 failed_max | 0 cost_circuit
  → qa_loop: polish_loop_qa
[PLAYABILITY 0] QA verdict BROKEN — skipping playability
[PLAYABILITY 2] QA verdict BROKEN — skipping playability[PLAYABILITY 1] QA verdict BROKEN — skipping playability

[QA-LOOP] (unified) Running qa on 3 concepts
  📚 Wiki ingested: runs/unified-polish-smoke-20260516-072651.md + log + model pages
  📚 Terminal wiki ingest complete (verdict=killed)
Future exception was never retrieved
future: <Future finished exception=TargetClosedError('Target page, context or browser has been closed')>
playwright._impl._errors.TargetClosedError: Target page, context or browser has been closed
```

## State snapshot at crash
- polish_iterations: {'qa': {0: 0, 1: 0, 2: 0}}
- polish_status: {'qa': {0: 'pending', 1: 'pending', 2: 'pending'}}
- build count: 3
- builder_mode: qa_fix

## Linked lessons
(Mira will populate this via a separate cross-link pass.)

## See also
- [[runs/unified-polish-smoke-20260516-072651]] (full run page)
