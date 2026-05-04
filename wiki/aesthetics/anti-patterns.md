# Anti-Patterns — What Fails

Accumulated from human verdicts across all pipeline runs. Every entry has evidence.

---

## Banned (automatic rejection)

### Vintage Boxing / Fight Card Poster
- **Evidence:** Run V3c — all 3 designers independently chose this aesthetic. Cream/newsprint background, red accents, bold serif type, "VS" or "FIGHT CARD" framing.
- **Why banned:** LLMs converge on this as a "safe creative" choice for ranking content. It's the aesthetic local optimum for "make a ranked list look interesting." Three independent agents choosing identical concepts proves it's a gravity well.
- **First banned:** 2026-05-02

### Spotify Wrapped / Music Streaming Recap
- **Evidence:** Run V3b — moodboard of Spotify Wrapped screenshots caused all 3 builders to create music recap layouts instead of the brief's sneaker ranking cards.
- **Why banned:** Moodboard visual content overwhelms brief text instructions. Also, the layout (personal stats summary with colorful cards) doesn't fit ranked list content.
- **First banned:** 2026-05-02

### Cream / Newsprint / Sepia Backgrounds
- **Evidence:** Runs V3c — always appears alongside the boxing poster aesthetic.
- **Why banned:** Co-occurs with fight card convergence. Also reads as "AI trying to look vintage."
- **First banned:** 2026-05-02

---

## Bad Patterns (consistently rated bad by CD)

### Centered Card on Dark Background
- **Evidence:** V2 all concepts, Smoke Test 2/3 concepts. Every centered-layout dark card was rated bad.
- **Why it fails:** Default AI aesthetic. Zero editorial intent. Reads as "template" not "artifact."
- **CD feedback:** Clean but generic = AI slop = instant fail.

### Gold Gradient + Dark Background
- **Evidence:** V1 all 3 concepts converged on this exact palette.
- **Why it fails:** LLMs' default "premium" palette. When all 3 concepts use it, proves it's the model's prior, not creative intent.

### Uniform Spacing / Center-itis
- **Evidence:** Across V1, V2, multiple V3 runs. Equal padding everywhere, centered everything.
- **Why it fails:** Real designers create tension through varied spacing — tight here, breathing room there. Uniform spacing = no editorial intent.

### Sequential Fade-In Animation
- **Evidence:** V1, V2 — items appearing one by one with opacity transition.
- **Why it fails:** No narrative arc. No physics. No surprise. Every AI prototype does this.

### Polished But Soulless
- **Evidence:** V2 was rated "worse than V1" despite being technically cleaner.
- **CD feedback:** > "V2 is worse." Quality of execution doesn't compensate for lack of creative ambition. A rough build with personality beats a clean build with none.

---

## Risky (sometimes works, often fails)

### Glassmorphism / Frosted Glass
- **Evidence:** No specific run — preemptively flagged as overused AI aesthetic.
- **Risk:** Instantly reads as "2023 AI design trend." Can work if combined with other techniques but never as the primary visual language.

### Gradient Blobs / Mesh Gradients
- **Evidence:** Multiple runs — appears as background when builders have no stronger visual idea.
- **Risk:** Fine as accent, bad as hero. If the gradient IS the design, it's AI slop.

### Texture on Readable Text
- **Evidence:** V3k-SMPLX Concept 0 — rated "great" overall but CD explicitly flagged: "The texture impacted the contrast of the main elements that's supposed to be readable. The main text should not have texture applied."
- **Risk:** Decorative texture (grain, noise, halftone) on body/title text kills readability. Apply texture to BACKGROUNDS and DECORATIVE elements only. Primary text must have clean contrast.
- **First flagged:** 2026-05-04

### Random/Unintentional Background Graphics
- **Evidence:** V3k-SMPLX Concept 0 — "The background graphic is cool but a little random. Could be done with more intention"
- **Risk:** Generated or decorative backgrounds need conceptual justification. "Cool but random" = half credit at best. Every visual element should connect to the concept.
- **First flagged:** 2026-05-04

### Brief Drift / Wrong Deliverable
- **Evidence:** V3k-SMPLX Concept 1 (GPT-5.4) — "Created a quiz when we wanted a scorecard of rankings." Also V3b (all 3 built Spotify Wrapped instead of sneaker cards).
- **Risk:** Content fidelity failure is an automatic disqualifier regardless of visual quality. No amount of creative ambition compensates for building the wrong thing.
- **First flagged:** 2026-05-04 (but recurring since V3b)
