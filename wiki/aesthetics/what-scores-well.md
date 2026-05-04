# What Scores Well — Patterns from Acceptable/Great Builds

From calibration session (15 builds rated) + subsequent runs. **0 great, 6 acceptable, 9 bad.**

---

## The Acceptable Builds

### Countdown Tape (Sharecard V1)
- **What made it work:** Tape/reel metaphor with physical material quality. Items revealed as if being printed on tape. Novel framing device.
- **Key technique:** Physical metaphor → material surface (tape texture, perforations)

### Fight Card (Smoke Test)
- **What made it work:** Strong typographic hierarchy, bold concept commitment. Despite "fight card" now being banned as a convergence trap, this specific execution had enough craft to pass.
- **Key technique:** Typographic dominance + editorial asymmetry

### Chain Reaction (Ranking Experiment)
- **What made it work:** Items visually connected — each rank triggers the next in a chain. Spatial relationship between items encodes the ranking.
- **Key technique:** Spatial encoding of data relationships

### Pile Up (Quiz V3)
- **What made it work:** 3D stacking — items literally pile on top of each other. Physical depth, layering, z-axis used to show hierarchy.
- **Key technique:** 3D CSS transforms / perspective for depth encoding

### Bleed Through (Quiz V3)
- **What made it work:** Ink/print metaphor — items bleed through layers like overprinted pages. Texture-heavy, material quality.
- **Key technique:** Mix-blend-mode layering + print/ink metaphor

### Seismic (Quiz V3)
- **What made it work:** Data visualization approach — ranking visualized as seismic waves/amplitude. Novel visual encoding of importance.
- **Key technique:** Data viz (amplitude/wave) + generative SVG patterns

---

## Common Threads Across Acceptable Builds

1. **Physical metaphor** — 4/6 reference a real-world object or process (tape, print, pile, seismic)
2. **Novel visual encoding** — rank isn't just a number, it's encoded in size/depth/position/amplitude
3. **Texture and material** — perceivable surface quality (grain, paper, ink, metal)
4. **Creative ambition over polish** — Pile Up and Seismic are rough but interesting. That's the bar.
5. **Distinct identity** — each build is recognizable as a specific concept, not a generic card

## CD Taste Hierarchy (from calibration)

| Priority | Weight | Criterion |
|----------|--------|-----------|
| 1 | 40% | Creative ambition — novel techniques, visual metaphors, interesting concept |
| 2 | 20% | Anti-AI-slop — does NOT look like an AI made it |
| 3 | 15% | Visual depth — 3D, texture, layering, material quality |
| 4 | 10% | Typography — intentional hierarchy, not default sizing |
| 5 | 10% | Hierarchy/readability — clear primary/secondary/tertiary |
| 6 | 5% | Technical execution — renders, no errors (table stakes) |

---

### V3k-SMPLX Concept 0 — Claude Opus (FIRST "GREAT" RATING)
- **Run:** sharecard-v3k-smplx (May 4, 2026)
- **Rating:** 🔥 Great
- **Dimensions:** Ambition 3, AI Slop 4, Depth 3, Type 4, Hierarchy 5
- **CD Note:** "The texture impacted the contrast of the main elements that's supposed to be readable. The main text should not have texture applied. The background graphic is cool but a little random. Could be done with more intention"
- **What made it work:** Strong hierarchy (5/5), clean typography (4/5), low AI slop (4/5)
- **What to improve:** Texture on readable text hurts contrast — decorative effects must not touch primary text. Background graphic needs conceptual intentionality, not randomness.
- **Key learning:** Hierarchy and readability trump raw visual ambition. A 5/5 hierarchy with 3/5 ambition > 4/5 ambition with 2/5 hierarchy.

### V3k-SMPLX Concept 2 — Gemini 3.1 Pro (strong iterate)
- **Run:** sharecard-v3k-smplx (May 4, 2026)
- **Rating:** Unrated (but positive note)
- **Dimensions:** Ambition 4, AI Slop 3, Depth 3, Type 3, Hierarchy 5
- **CD Note:** "Overall solid. Really great transition and motion design. Feels conceptually consistent though doesn't match our brand strongly"
- **What made it work:** Excellent motion design (explicitly called out), conceptual consistency, strong hierarchy
- **Key learning:** Motion design is a powerful differentiator. Conceptual consistency matters. Brand alignment is a concern but not a dealbreaker.

---

## Learned: Motion Design as Differentiator (V3k)
From CD feedback on Concept 2 (Gemini): "Really great transition and motion design" — explicitly called out as the standout quality. This aligns with Seismic (acceptable) which also used dynamic visual encoding. **Motion that feels intentional and narrative > static beauty.**

## Learned: Hierarchy > Ambition (V3k)
The "great" rated build scored 5/5 hierarchy but only 3/5 ambition. The builds with 4/5 ambition but 2-3/5 hierarchy were not rated "great". **Readability and clear information hierarchy is table stakes — creative ambition only counts if the hierarchy is already solid.**

## What "Great" Looks Like (first achieved V3k)

Based on the first "great" rating + acceptable pattern analysis:
- Everything acceptable has, PLUS:
- Real generated imagery (assets) integrated into the design, not just CSS
- Animation with narrative arc (not just reveals)
- Could appear on Awwwards/FWA
- Makes you want to screenshot it and send to a designer friend
- "How did they do that?" reaction
