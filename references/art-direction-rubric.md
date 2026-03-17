# Art Direction Rubric

Composition, hierarchy, and visual judgment — the layer between "does it work?" (code) and "does it have cool effects?" (enhancement tactics). This is the craft that separates a strong layout from a decorated one.

Use this during Stitch prompt refinement, design contract writing, and the art direction gate. These principles apply before any animation, 3D, or interaction code exists — they're about the still frame.

---

## 1. Focal Point

Every screen needs exactly ONE place the eye goes first. If everything is emphasized, nothing is.

**Diagnosing weak focal point:**
- Squint at the screen. What's brightest/largest/most contrasted? That's your focal point. If you can't tell → problem.
- If two elements compete at equal visual weight → one needs to yield.

**Controls:**
| Lever | How It Creates Focus |
|-------|---------------------|
| Scale | The largest element wins first glance. A 120px headline dominates a 16px body. |
| Contrast | High contrast (light on dark, saturated on muted) pulls the eye before low contrast. |
| Isolation | An element surrounded by whitespace commands more attention than one crowded by neighbors. |
| Color | A single saturated accent in a muted composition is a magnet. |
| Position | Top-left (in LTR cultures) and center have natural gravity. Breaking this needs compensating weight. |
| Detail | A complex or textured element in a simple field attracts the eye. |

**Stitch prompt pattern:**
> "The headline should be the clear focal point — 3x the size of anything else on screen, high contrast against the background. Everything else is secondary."

**Anti-pattern:** Hero section where the headline, image, CTA button, and navigation all compete at similar visual weight. The eye bounces; nothing lands.

---

## 2. Visual Hierarchy

After the focal point, there's a reading order: what does the eye see 1st, 2nd, 3rd? Hierarchy is the choreography of attention without animation.

**The squint test:** Blur the screen (or squint). You should be able to read the hierarchy in 3 levels:
1. **Primary** — the one thing (headline, hero image, key stat)
2. **Secondary** — supporting elements (subhead, description, key UI)
3. **Tertiary** — everything else (nav, metadata, fine print)

**Creating separation between levels:**
- Size ratio: primary should be 3-5x secondary, secondary 2x tertiary
- Weight contrast: primary bold/black, secondary medium, tertiary regular/light
- Color: primary in full-strength brand color, secondary in muted, tertiary in grey
- Spacing: more space around primary elements, tighter grouping for tertiary

**Anti-pattern:** "Everything is medium." Headlines that are 24px when they should be 80px. Body text that's 18px when it should be 14px. No level dominates, so the page reads as a wall of equally-important content.

---

## 3. Silhouette and Shape Language

The overall shape of the composition — its outline and mass distribution — communicates before any content is read.

**What to look for:**
- **Mass balance** — is visual weight distributed intentionally? Asymmetric compositions need a counterweight (a heavy image left balanced by a strong headline right).
- **Edge tension** — elements near the edge of the frame create tension (energy, unease). Elements centered create stability (calm, authority). Choose based on intent.
- **Negative space shape** — the empty space between elements is a shape too. If it's random/awkward, the composition feels unresolved. If it's intentional, it feels designed.
- **Silhouette recognition** — if you filled the entire layout with a single color, would the resulting shape be interesting or just a rectangle? Strong compositions have distinctive silhouettes.

**Stitch prompt pattern:**
> "Asymmetric layout — heavy image mass in the upper-left (60% of viewport), balanced by a bold headline in the lower-right. Generous negative space between them creates breathing room."

**Anti-pattern:** Perfectly centered, perfectly symmetrical layout where everything sits in safe zones. It's balanced but has zero tension. Tension is interest.

---

## 4. Crop and Frame

How images are cropped and framed changes their energy entirely. Same image, different crop = different feeling.

**Crop energy spectrum:**
| Crop | Energy | Feeling |
|------|--------|---------|
| Full frame, lots of context | Low | Documentary, editorial, story |
| Medium crop, subject fills 60% | Medium | Balanced, commercial, clean |
| Tight crop, subject bleeds edge | High | Intimate, intense, fashion |
| Extreme crop, subject cut off | Very high | Abstract, provocative, art |

**Framing decisions:**
- **Full-bleed** (image touches all edges) → immersive, cinematic, no separation from content
- **Contained** (image has visible margins/borders) → editorial, controlled, gallery-like
- **Overlapping** (image breaks its container, overlaps text or other elements) → dynamic, layered, energetic
- **Masked** (image visible through a shape — circle, text, irregular) → designed, intentional, branded

**Stitch prompt pattern:**
> "Hero image: tight crop on the subject, bleeding off the right edge of the viewport. The crop should feel fashion-editorial, not documentary."

**Anti-pattern:** Every image at default aspect ratio, centered in its container, with equal padding on all sides. Safe, predictable, no tension.

---

## 5. Pacing and Rhythm

A page is a sequence of moments. Pacing is the tempo — when to be loud, when to be quiet, when to breathe.

**The music analogy:**
- **Verse** — content-dense sections (text, details, features). Medium energy.
- **Chorus** — hero moments (full-bleed images, massive type, key statements). High energy.
- **Bridge** — transitions, breathing room, spacers. Low energy.

A good page alternates: chorus → verse → bridge → chorus → verse. A bad page is all chorus (exhausting) or all verse (flat).

**Pacing tools:**
| Tool | Effect |
|------|--------|
| Whitespace between sections | Controls breathing room. More space = longer pause. |
| Section height | Tall sections (100vh) slow the reader. Short sections quicken the pace. |
| Content density | Dense content = slower reading. Sparse content = faster scanning. |
| Visual weight shifts | Moving from dark/heavy to light/airy (or vice versa) creates a "gear change." |
| Full-bleed moments | Act as punctuation — a visual exclamation mark between content sections. |

**Diagnosing bad pacing:**
- The page feels like "one long thing" with no memorable moments → needs more contrast between sections
- The page feels exhausting → too many high-energy sections in a row, needs breathing room
- The page feels monotonous → every section is the same height/density/weight, needs variation

**Stitch prompt pattern:**
> "Alternate between full-bleed hero sections (100vh, dramatic) and compact content sections (60vh, text-focused). Include at least one spacer section with just a single pull quote and generous whitespace."

---

## 6. Image Treatment and Consistency

How images are processed, filtered, and presented creates (or destroys) visual cohesion.

**Treatment dimensions:**
| Dimension | Range | Effect |
|-----------|-------|--------|
| Color grading | Natural ↔ Heavily graded | Graded = mood, editorial. Natural = documentary, honest. |
| Contrast | Flat ↔ High contrast | Flat = dreamy, soft. High = dramatic, punchy. |
| Saturation | Desaturated ↔ Vivid | Desat = sophisticated, moody. Vivid = energetic, pop. |
| Temperature | Cool ↔ Warm | Cool = tech, night, future. Warm = human, nostalgia, comfort. |
| Grain/texture | Clean ↔ Textured | Clean = digital, modern. Textured = analog, editorial. |

**The consistency rule:** Pick ONE treatment and apply it across ALL images in a concept. Mixed treatments (one warm, one cool, one grainy, one clean) make the page feel like a mood board, not a finished design.

**Stitch prompt pattern:**
> "All photography should have a consistent treatment: high contrast, slightly desaturated, cool temperature, with subtle film grain. No clean/vivid/warm images."

**Anti-pattern:** Stock photos with wildly different color grading, lighting, and style dropped into the same layout. Instantly reads as "placeholder."

---

## 7. When Restraint Beats Embellishment

The enhancement tactics and recipes in this skill are powerful. The danger is using all of them.

**The restraint principle:** For every effect you add, ask: "Does this serve the focal point and hierarchy, or does it compete with them?"

**Signs you've over-designed:**
- The background animation is more interesting than the content
- Hover effects distract from the primary CTA
- Grain + gradient mesh + particles + custom cursor + magnetic buttons all at once = sensory overload
- The page takes 3 seconds to load before anything appears
- You can't describe the hierarchy in 3 levels because there are too many competing elements

**The "remove until it breaks" test:** Take away effects one at a time. When removing something makes the design noticeably worse → that effect was earning its place. When removing something and nobody notices → it was decoration, not design.

**Effect budget by aesthetic direction:**

| Direction | Max Concurrent Effects | Focus |
|-----------|----------------------|-------|
| Brutalist/Raw | 1-2 | Typography and structure do all the work. Almost no enhancement. |
| Luxury/Refined | 2-3 | One exquisite transition, perfect spacing, subtle texture. Restraint IS the design. |
| Editorial/Magazine | 2-3 | Image treatment + typography expression + one scroll moment. |
| Cinematic/Immersive | 3-4 | Full-bleed media + atmospheric depth + one interactive layer. |
| Maximalist Chaos | 4-6 | The exception. Density IS the aesthetic. But focal point still matters. |
| Street/Culture | 3-4 | Texture + collage + bold type. Don't over-polish — roughness is the point. |

---

## Using This Rubric

### During Stitch Prompt Writing
Before prompting Stitch, define:
- Where is the focal point?
- What's the 3-level hierarchy?
- What crop/frame energy do we want for images?
- What's the pacing plan (chorus/verse/bridge)?
- What's the image treatment?

Include these in the Stitch prompt explicitly.

### During Art Direction Gate
When reviewing Stitch output, check each concept against:
- [ ] Clear focal point (squint test passes)
- [ ] 3-level hierarchy readable without content
- [ ] Intentional negative space (not random gaps)
- [ ] Image treatment is consistent across screens
- [ ] Pacing varies between screens (not all the same density)
- [ ] Crop/frame choices match the intended energy

### During Design Contract
The non-negotiables section should reference:
- Focal point per screen
- Hierarchy levels with specific size/weight/color values
- Image treatment specification
- Effect budget (how many concurrent effects allowed)

### During Debrief
When probing visual feedback, use this rubric's vocabulary:
- "Is the focal point landing where you want it?"
- "Does the pacing feel right — or is it all one speed?"
- "Are the images feeling cohesive, or do they clash?"
- "Is there enough restraint, or does it feel overworked?"
