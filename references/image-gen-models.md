# Image Generation Model Intelligence

> Which model to reach for based on the creative task.
> Updated: 2026-03-25
> Platform: fal.ai (single API, pay-per-use)

## Quick Decision Matrix

| Creative Task | Best Model | Why | Cost/image |
|---|---|---|---|
| **Character illustration (hand-drawn style)** | Nano Banana 2 | Reasoning-guided composition, character consistency for up to 5 characters without fine-tuning | $0.08 (1K) |
| **Photorealistic hero shots** | FLUX.2 [pro] | Zero-config, studio-grade, best prompt adherence | $0.03/MP |
| **Text in images (logos, posters)** | Recraft V3 or Ideogram V3 | Purpose-built for accurate text rendering | $0.04-$0.09 |
| **Vector art / icons** | Recraft V3 | Only model with native vector output | $0.08 (vector) |
| **Fast drafts / exploration** | FLUX.1 [schnell] | 1-2 sec generation, cheapest | $0.003/MP |
| **Style-locked batch generation** | FLUX.1 [dev] + LoRA | Train custom LoRA on 15-20 refs, then batch with locked style | $0.025/MP + training |
| **Complex multi-element scenes** | Nano Banana Pro | Full Gemini 3 Pro reasoning, deepest compositional understanding | $0.15 |
| **High-res final output (2K+)** | FLUX 1.1 [pro] Ultra | Native 2K without upscaling | $0.06 |
| **Semantic accuracy + editing** | GPT Image 1.5 | Strong prompt following, versatile | $0.009+ |
| **Campaign consistency (same character, many scenes)** | Nano Banana 2 | Built-in multi-reference (up to 14 images), character lock for 5 people | $0.08 (1K) |

## Model Profiles

### Tier 1: Primary Creative Models

#### Nano Banana 2 (Google DeepMind)
- **Endpoint**: `fal-ai/nano-banana-2`
- **Architecture**: Gemini 3.1 Flash Image (reasoning-guided, not pure diffusion)
- **Superpower**: Understands creative *intent*, not just keywords. Reasons about composition before rendering.
- **Character consistency**: Up to 5 characters across generations without fine-tuning
- **Reference images**: Up to 14 for editing workflows
- **Resolutions**: 512×512, 1K, 2K, 4K (aspect ratios: 21:9, 16:9, 3:2, 4:3, 5:4, 1:1, 4:5, 3:4, 2:3, 9:16)
- **Pricing**: $0.06 (512), $0.08 (1K), $0.12 (2K), $0.16 (4K)
- **Best for**: Companion quiz archetype illustrations, character design sheets, storyboard-style consistency
- **Weakness**: More expensive than FLUX for simple generations; Nano Banana Pro better for very complex compositions

#### FLUX.2 [pro] (Black Forest Labs)
- **Endpoint**: `fal-ai/flux-2-pro`
- **Architecture**: Latest FLUX flagship, zero-configuration pipeline
- **Superpower**: Most consistent prompt adherence in testing. No inference steps or guidance scales to tune.
- **Pricing**: $0.03/megapixel
- **Best for**: Photorealistic hero images, product shots, brand photography
- **Weakness**: Less stylized/artistic than Nano Banana; no built-in character consistency system

#### FLUX.1 [dev] + LoRA
- **Endpoint**: `fal-ai/flux-lora` (inference), `fal-ai/flux-lora-fast-training` (training)
- **Superpower**: Train custom style/character LoRA in minutes, then batch-generate with perfect style lock
- **Pricing**: $0.025/MP (inference) + training cost
- **Best for**: Batch-generating 10+ images in identical style (e.g., all 10 companion quiz archetypes)
- **Workflow**: Generate 15-20 reference images with Nano Banana 2 → Train LoRA → Batch generate all variants
- **Weakness**: Requires training step; quality depends on reference image quality

### Tier 2: Specialized Models

#### Recraft V3
- **Endpoint**: `fal-ai/recraft-v3`
- **Superpower**: Best text rendering + only model with native SVG vector output
- **Pricing**: $0.04 (raster), $0.08 (vector)
- **Best for**: Typography-heavy assets, logos, icon sets, marketing materials

#### Ideogram V3
- **Endpoint**: `fal-ai/ideogram-v3`
- **Superpower**: Strongest text-in-image accuracy, great for posters/marketing
- **Pricing**: $0.03-$0.09
- **Best for**: Social share cards with archetype names, promotional graphics

#### Nano Banana Pro (Google DeepMind)
- **Endpoint**: `fal-ai/nano-banana-pro`
- **Architecture**: Full Gemini 3 Pro backbone (deeper reasoning than Nano Banana 2)
- **Superpower**: Most complex compositional understanding of any model
- **Pricing**: $0.15/image
- **Best for**: Complex hero illustrations, scenes with many interacting elements
- **Weakness**: Slowest and most expensive; overkill for simpler tasks

### Tier 3: Utility Models

#### FLUX.1 [schnell]
- **Endpoint**: `fal-ai/flux/schnell`
- **Superpower**: 1-2 second generation, dirt cheap
- **Pricing**: $0.003/MP
- **Best for**: Rapid exploration, thumbnail drafts, prompt testing before committing to expensive models

#### GPT Image 1.5
- **Endpoint**: `fal-ai/gpt-image-1-5`
- **Superpower**: Versatile, strong prompt following
- **Pricing**: From $0.009/image
- **Best for**: General-purpose when you don't need a specialist

#### FLUX 1.1 [pro] Ultra
- **Endpoint**: `fal-ai/flux-pro/v1.1-ultra`
- **Superpower**: Native 2K output without upscaling
- **Pricing**: $0.06/image
- **Best for**: Final production assets that need to be high-res

## Pipeline Integration

### Phase 0 (Mood Exploration)
Use: **FLUX.1 [schnell]** ($0.003/MP) for rapid visual brainstorming

### Phase 1 (Approach Docs)
Use: **Nano Banana 2** to generate concept art / reference images for approach docs

### Phase 3 (Build) — Static Asset Generation
For prototypes that need illustration assets (like companion quiz archetypes):
1. Generate hero reference with **Nano Banana 2** (best character consistency)
2. If 10+ variants needed in same style: Train **FLUX LoRA** on references, then batch generate
3. For text-heavy assets (share cards, results): Use **Recraft V3** or **Ideogram V3**

### Phase 3 (Build) — Interactive Code
LLM sub-agents still own: Canvas 2D animations, WebGL shaders, Web Audio, particle systems, interaction logic.
Image gen models handle: static illustrations, background textures, character art, share card graphics.

## Recommended Workflow: Companion Quiz Archetypes

1. **Prompt engineer** one archetype with Nano Banana 2 (nail the hand-drawn/kawaii creature style)
2. **Generate 3-5 variations** to find the best direction
3. **Use character consistency** feature to generate all 10 archetypes maintaining the same art style
4. Export as PNG/WebP, embed in HTML prototypes
5. LLM builders focus purely on: quiz interactions, companion animations, transformation sequences, email capture

## Cost Estimates

| Project | Estimated Generations | Model | Est. Cost |
|---|---|---|---|
| Companion Quiz (10 archetypes × 5 variations) | 50 images | Nano Banana 2 (1K) | ~$4.00 |
| Quiz V3 (background textures, share cards) | 20 images | FLUX.2 [pro] | ~$0.60 |
| LoRA training (if needed) | 1 training run | FLUX LoRA fast | ~$2-5 |
| Exploration / drafts | 100 images | FLUX.1 [schnell] | ~$0.30 |

## Testing Log

> Document results here as we test models against specific creative tasks.
> Format: Date | Model | Prompt summary | Result quality (1-10) | Notes

_(No entries yet — testing begins when fal.ai API key is configured)_

## API Setup

```bash
# Set fal.ai API key
export FAL_KEY="your-key-here"

# Test generation (Node.js)
npm install @fal-ai/client

# Or curl:
curl -X POST "https://queue.fal.run/fal-ai/flux/schnell" \
  -H "Authorization: Key $FAL_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "test image"}'
```
