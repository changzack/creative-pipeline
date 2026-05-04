# Pipeline Wiki Schema

## Purpose
This wiki is the pipeline's compiled knowledge base. It compounds with every run. Raw artifacts are immutable; the wiki synthesizes them into actionable knowledge that every agent reads.

## Page Types

### Technique Page (`techniques/*.md`)
```yaml
# Technique: [Name]
Status: proven | promising | neutral | risky | banned
Evidence:
  - Run: [name], Concept: [N], Model: [model], Verdict: [rating]
Implementation: [CSS/JS snippet]
Gotchas: [known failure modes]
Best model: [which builder implements it best]
Related: [[other-technique]]
```

### Anti-Pattern Page (`aesthetics/anti-patterns.md`)
Each entry has: description, evidence (which run, what happened), why it fails.
Entries are NEVER removed — only marked deprecated if new evidence contradicts.

### What Scores Well (`aesthetics/what-scores-well.md`)
Patterns from builds rated acceptable or great. Each entry cites the specific build.

### Model Page (`models/*.md`)
Per-model: strengths, weaknesses, prompt tips, context budget, cost, quirks.
Updated after every run with new observations.

### Run Summary (`runs/*.md`)
Created automatically after each human verdict. Contains:
- Brief, design system (if any), date, cost
- Per-concept: model, approach summary, QA result, judge rank
- Human verdict + verbatim feedback
- Learnings extracted → links to updated wiki pages

### Research Page (`research/*.md`)
Refero queries that worked, moodboard composition lessons, banned reference types.

### Build Lessons (`builds/*.md`)
Technical gotchas: font loading, mobile viewport, asset integration, content fidelity.

## Ingest Workflow

After human verdict at taste gate:

1. **Write** `runs/{name}.md` — structured run summary
2. **Update** technique pages — add evidence from this run's approaches + builds
3. **Update** `aesthetics/anti-patterns.md` — if verdict is reject/bad, add pattern
4. **Update** `aesthetics/what-scores-well.md` — if verdict is approve/acceptable, add pattern
5. **Update** `models/*.md` — per-model performance data from this run
6. **Update** `research/refero-playbook.md` — if new queries were effective
7. **Update** `index.md` — add any new pages
8. **Append** `log.md` — chronological record

## Conventions

- Evidence always cites: `Run: {name}, Concept {N} ({model}), rated {verdict}`
- Human feedback is quoted verbatim in blockquotes: `> "feedback text"`
- Contradictions flagged: `⚠️ CONTRADICTS [[page]]: explanation`
- Pages never deleted, only marked `Status: deprecated` with reason
- Technique status progression: promising → proven (2+ acceptable ratings) → or risky → banned
- All file links use relative markdown: `[page](../category/page.md)`
