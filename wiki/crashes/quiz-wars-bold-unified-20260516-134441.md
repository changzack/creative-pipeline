# Crash: quiz-wars-bold-unified-20260516-134441
- **Date:** 2026-05-16T13:45:35-0700
- **Verdict:** killed
- **Phase at terminal:** unknown
- **Cost at crash:** $0.00
- **Last successful node:** unknown
- **Iterations completed:** qa=0, judge=0, playability=0

## Symptom (auto-classified)
SIGTERM

## Last exception (if any)
```
RuntimeError: SIGTERM received (signum=15)
```

## Retry-loop detection
none detected

## Cost trajectory
- start: $25.00 (💰 Cost circuit breaker set to $25.00)

## Last 50 log lines (raw)
```
/Users/zackchang/.openclaw/workspace/pipeline/.venv/lib/python3.9/site-packages/urllib3/__init__.py:35: NotOpenSSLWarning: urllib3 v2 only supports OpenSSL 1.1.1+, currently the 'ssl' module is compiled with 'LibreSSL 2.8.3'. See: https://github.com/urllib3/urllib3/issues/3020
  warnings.warn(
📐 Design system loaded: smplx-design-system.md (36KB)
💰 Cost circuit breaker set to $25.00
  ✅ Langfuse tracing initialized
  📊 Langfuse trace started: 9aab629c43b6099d1051f96f2fdd7c53 (session=quiz-wars-bold-unified-20260516-134441)

🚀 Starting pipeline: quiz-wars-bold-unified-20260516-134441
Brief: /Users/zackchang/.openclaw/workspace/overnight-runs/quiz-wars/CREATIVE-BRIEF.bold.md
State stored in: /Users/zackchang/.openclaw/workspace/pipeline/pipeline.db

[SCOPE CONTRACT] Extracting deliverables checklist for: quiz-wars-bold-unified-20260516-134441
  📚 Wiki ingested: runs/quiz-wars-bold-unified-20260516-134441.md + log + model pages
  📚 Terminal wiki ingest complete (verdict=killed)
```

## State snapshot at crash
- polish_iterations: {}
- polish_status: {}
- build count: 0
- builder_mode: ?

## Linked lessons
(Mira will populate this via a separate cross-link pass.)

## See also
- [[runs/quiz-wars-bold-unified-20260516-134441]] (full run page)
