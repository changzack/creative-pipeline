# Build Lessons: Asset Integration

## fal.ai Asset Generation

### Model Routing
| Asset Type | Model | Cost | Quality |
|-----------|-------|------|---------|
| Textures (concrete, paper, grain) | `fal-ai/flux/schnell` | $0.003 | Good — fast, cheap, reliable |
| Product shots | `fal-ai/flux-2-pro` | $0.03 | Good BUT trademark issues |
| Graphics with text | `fal-ai/recraft-v3` | $0.06 | Good for badges, stamps |
| Illustrations | `fal-ai/nano-banana-2` | $0.08 | Not tested yet |

### Trademark Content Policy (CRITICAL)
fal.ai's FLUX models reject prompts containing brand names:
- ❌ "Air Jordan 1 Chicago" → content_policy_violation
- ❌ "Nike Dunk Low Panda" → content_policy_violation  
- ❌ "New Balance 550" → content_policy_violation

**Workaround needed:** Rephrase as generic descriptions:
- ✅ "High-top basketball sneaker, red and white leather, side profile, floating on dark background"
- ✅ "Low-top skate shoe, black and white colorway, dramatic studio lighting"

This was discovered in V3j-b and V3k-smplx. Both runs lost their hero product shot assets.

### Asset Protocol: `asset://`
- Designers specify assets in `## ASSET MANIFEST` section
- `asset_gen_node` generates via fal.ai, saves to `{run_dir}/assets/concept-{id}/`
- Builders reference as `<img src="asset://hero-texture" />`
- Post-processor replaces `asset://name` with `data:image/jpeg;base64,...`
- Result: self-contained HTML with real imagery

### Size Impact
| Run | Without Assets | With Assets |
|-----|---------------|-------------|
| V3j (no FAL_KEY) | 22-27KB | N/A |
| V3j-b | 31KB (GPT, no manifest) | 3.7MB (Opus), 1.5MB (Gemini) |
| V3k-smplx | 17KB (GPT) | 576KB (Opus), 1MB (Gemini) |

### Max 8 assets per concept
Keeps cost controlled (~$0.03-$0.09 per concept for textures, more for product shots).
