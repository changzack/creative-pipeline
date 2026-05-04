# Model: Gemini 3.1 Pro (gemini-3.1-pro-preview)

## Role in Pipeline
- Builder (direct API via google.genai SDK)
- Designer (direct API, parallel with Opus/GPT)

## Strengths
- **Massive context window** — 1M tokens (~3.7MB), only uses 2% for typical builds
- **Good approach docs** — produces 30-36KB approach documents as designer
- **Asset integration** — V3j-b built with 4 assets injected (1.5MB final)
- **Cheap** — $2/$12 per 1M input/output tokens

## Weaknesses
- **Model ID instability** — has changed multiple times:
  - `gemini-2.5-pro-preview-05-06` → 404'd
  - `gemini-2.5-pro` → worked briefly
  - `gemini-3-pro-preview` → shut down March 9
  - `gemini-3.1-pro-preview` → current, but QA fix round returns 404
- **QA fix rounds fail** — the fix round API call returns model_not_found, likely a routing issue with the genai SDK
- **Mobile viewport issues** — V3i concept-2 hardcoded 1080×1920 with transform:scale(), invisible on phones
- **Missing techniques** — V3k-smplx missed 4 specified techniques (noise grain, scan lines, red glow, clip-path)

## Quirks
- `google.genai` SDK requires keyword args: `Part.from_text(text="...")` not `Part.from_text("...")`
- Responses sometimes include `thought_signature` non-text parts — need to handle gracefully
- The `enable_safety_checker` and `safety_tolerance` params don't apply to Gemini's own safety filters

## Performance History
| Run | Role | Rank | Verdict | Notes |
|-----|------|------|---------|-------|
| V3h | Builder 2 | #3 | iterate | 0/10 content fidelity initially |
| V3i | Builder 2 | missing | iterate | SDK bug killed build, manually rebuilt |
| V3j | Builder 2 | #2 (1 win) | — | Mobile viewport fix needed |
| V3j-b | Builder 2 | #2 (1 win) | — | 1.5MB with assets, 4 injected |
| V3k-smplx | Builder 2 | Strong iterate | iterate | **CD highlight: "Really great transition and motion design."** Ambition 4/5, Hierarchy 5/5. Brand alignment concern but not dealbreaker. Conceptually consistent. |

## Context Budget
- Window: 1M tokens (~3,769KB text)
- Typical builder prompt: 96-98KB (2% utilization)
- Practically unlimited — could receive entire wiki as context
