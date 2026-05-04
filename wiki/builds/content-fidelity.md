# Build Lessons: Content Fidelity

## The Problem
Builders consistently reproduce MOODBOARD content instead of BRIEF content. If the moodboard shows music apps, builders build music apps — even when the brief says "sneaker ranking."

## Root Cause (V3b)
Moodboard images are multimodal input (vision). Brief is text. Vision input dominates text instructions for LLMs — they build what they SEE, not what they READ.

## Solution: Multi-layer enforcement

### 1. Brief includes sample data
The `## Sample Data` section gives exact content to use. Builders must use these items verbatim.

### 2. Designer prompt includes content fidelity rule
> "Your concept must match the PRODUCT described in the brief. The moodboard is for visual style only."

### 3. Builder prompt includes content fidelity rule
> "You must build exactly the product described in the brief using the sample data provided."

### 4. QA station checks content fidelity
`_extract_sample_items()` parses sample data from brief, then checks if each item appears in the built HTML. Threshold: 70% of items must be present.

### 5. QA fix round
If content fidelity fails, the fix round tells the builder exactly which items are missing.

## Results After Enforcement
| Run | Concept 0 (Opus) | Concept 1 (GPT) | Concept 2 (Gemini) |
|-----|-------------------|------------------|---------------------|
| V3h | 2/10 → fixed | 10/10 ✅ | 0/10 → fixed |
| V3i | 10/10 ✅ | 10/10 ✅ | rebuilt |
| V3j-b | 6/10 → fixed | 0/10 → fixed | 4/10 → fixed |

GPT-5.4 has best natural content fidelity. Opus and Gemini need QA fix rounds.
