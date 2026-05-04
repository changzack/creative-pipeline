# Model: GPT-5.4 (gpt-5.4)

## Role in Pipeline
- Builder (direct API)
- Designer (direct API, parallel with Opus/Gemini)

## Strengths
- **Best content fidelity** — V3h scored 10/10 content fidelity with no fix needed (first model to do this)
- **Fast execution** — typically completes in 2-3 min
- **Clean compliance** — V3j-b passed all spec compliance checks with 0 warnings
- **Good at structured output** — follows Build Contract specs reliably

## Weaknesses
- **Lower creative ambition** — tends to produce functional-but-safe designs
- **Smaller builds** — 17-31KB (less code = fewer implemented techniques)
- **Ignores design system constraints** — V3k-smplx used Space Grotesk despite Inter-only constraint
- **Missing techniques** — V3j skipped 5 specified techniques (grid background, SVG contour rings, blend modes, noise texture)
- **No asset manifest from its designer** — V3j-b Designer 1 produced no asset manifest, so builder had no generated imagery

## Quirks
- Uses `max_completion_tokens` not `max_tokens` (API parameter name difference)
- Upgraded from gpt-4.1 → gpt-5.4 on May 3. gpt-4o produced only 4KB skeletons.
- Cost: $2.50/$10 per 1M input/output tokens

## Performance History
| Run | Role | Rank | Verdict | Notes |
|-----|------|------|---------|-------|
| V3h | Builder 1 | #1 (judge winner) | iterate | 10/10 content fidelity, no fix needed |
| V3i | Builder 1 | tied | iterate | Compliance failure (forbidden font Inter) |
| V3j | Builder 1 | #3 (0 wins) | — | Missing several techniques |
| V3j-b | Builder 1 | #3 (0 wins) | — | 31KB, no assets |
| V3k-smplx | Builder 1 | Unrated | iterate | **Built wrong deliverable — quiz instead of ranking scorecard.** CD: "Created a quiz when we wanted a scorecard of rankings." Ambition 4/5 but hierarchy only 2/5. |

## Context Budget
- Window: 128K tokens (~363KB text)
- Typical builder prompt: 62-94KB (17-26% utilization)
- Safe zone: adequate for current prompt sizes
