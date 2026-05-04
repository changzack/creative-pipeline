# Model: Claude Opus (claude-opus-4-6)

## Role in Pipeline
- Primary designer (via Hermes agent)
- Builder (via Hermes agent)
- Used for research (via Hermes agent)

## Strengths
- **Richest approach docs** — consistently produces 30-38KB approach documents with deep creative rationale
- **Best concept commitment** — follows through on metaphors more completely than other models
- **Strongest typography choices** — picks distinctive fonts with rationale, not just Inter/Helvetica
- **Largest builds** — produces 20-30KB HTML (more code = more implemented techniques)
- **Best asset integration** — when given `asset://` refs, embeds them thoughtfully

## Weaknesses
- **Slow execution** — takes 10-15 min of "thinking" before writing, can look stalled
- **Approach doc verbosity** — 35KB approach docs are rich but can overwhelm context for other nodes
- **Sometimes ignores forbidden fonts** — compliance check needed
- **Expensive** — ~$0.15-0.20 per build call

## Quirks
- Hermes execution: uses detached process via signal files. Set timeout to 30 min minimum.
- The "still working" period is real thinking, not stalling — confirmed via controlled test.

## Performance History
| Run | Role | Rank | Verdict | Notes |
|-----|------|------|---------|-------|
| V3f | Builder 0 | #1 (1 win) | iterate | Best of 3, but "flat" |
| V3h | Builder 0 | #2 | iterate | 2/10 content fidelity initially, fixed |
| V3i | Builder 0 | tied #1 | iterate | 10/10 content fidelity — first time |
| V3j | Builder 0 | #1 (2 wins) | — | Won all matchups |
| V3j-b | Builder 0 | #1 (1 win) | — | 3.7MB with assets, largest build |
| V3k-smplx | Builder 0 | #1 (🔥 Great) | iterate | **First "great" rating from CD.** Hierarchy 5/5, Type 4/5, AI Slop 4/5. Texture on text hurt readability. Background graphic "cool but random." |

## Context Budget
- Window: 200K tokens (~644KB text)
- Typical builder prompt: 97-100KB (15% utilization)
- Safe zone: well within limits
