# Asset Generation Phase — Pipeline Integration Plan

**Date:** May 3, 2026  
**Status:** Draft — approved by Zack to plan  
**Core Insight:** 100% programmatic output = AI slop. Mixing generated imagery with programmatic UI = design-grade output.

---

## The Problem

Every build we've produced has:
- **Grey placeholder boxes** where product images should be
- **CSS gradients** where designed textures should be
- **Procedural patterns** where crafted visual elements should be
- **No soul** — everything looks computationally generated because it IS

A human designer would never ship a layout without real imagery, custom textures, or designed graphical elements. Our pipeline skips this entirely.

## The Solution: Asset Generation Node

Add `asset_gen_node` between **approach_gate** and **builder** in the pipeline graph.

```
research → designer → approach_gate → ASSET_GEN → builder → qa → judge → human_gate
```

The designer's approach doc includes an **Asset Manifest** — a structured list of visual assets needed. We generate them via fal.ai, then the builder receives actual images to embed.

---

## Asset Manifest Format

Added to the designer's BUILD CONTRACT:

```markdown
## ASSET MANIFEST

### Background
- type: texture
- description: "Dark concrete surface with subtle grain, almost black (#0a0a0a) with micro-noise"
- dimensions: 1080x1920
- model_hint: flux-schnell (abstract texture, speed > quality)

### Hero Product Shot
- type: product
- description: "Air Jordan 1 Chicago, side profile, floating on dark background, dramatic studio lighting, slight shadow beneath"  
- dimensions: 540x540
- model_hint: flux-2-pro (photorealistic)

### Rank Badge
- type: graphic
- description: "Gold metallic '#1' badge with embossed text, circular, premium feel, transparent background"
- dimensions: 200x200
- model_hint: recraft-v3 (text + design asset)

### Decorative Element
- type: decoration
- description: "Subtle diagonal scratch marks / distress overlay, white on transparent, 10% opacity when applied"
- dimensions: 1080x1920
- model_hint: flux-schnell (abstract, fast)

### Section Divider  
- type: graphic
- description: "Thin horizontal line with small diamond shape in center, gold (#C4A265) on transparent"
- dimensions: 1080x40
- model_hint: recraft-v3 (precise graphic)
```

## Asset Categories & Model Routing

| Category | What | Model | Cost/asset | Why |
|---|---|---|---|---|
| **Textures** | Backgrounds, overlays, noise, grain, paper, concrete | FLUX.1 schnell | ~$0.003 | Abstract, fast, cheap. Texture doesn't need reasoning. |
| **Product shots** | Sneaker hero images, styled product photography | FLUX.2 Pro | ~$0.03 | Best photorealistic prompt adherence |
| **Design graphics** | Badges, icons, dividers, stamps, logos with text | Recraft V3 | ~$0.04-$0.08 | Only model with clean text rendering + vector quality |
| **Atmospheric elements** | Smoke, light leaks, bokeh, lens flares, dramatic lighting | FLUX.2 Pro | ~$0.03 | Photorealistic effects |
| **Editorial illustrations** | Custom artwork, stylized interpretations | Nano Banana 2 | ~$0.08 | Understands creative intent, consistent style |
| **Rapid exploration** | Draft any of the above before committing | FLUX.1 schnell | ~$0.003 | 1-2 sec, near-free |

## Pipeline Node: `asset_gen_node`

```python
def asset_gen_node(state: dict) -> dict:
    """Phase 3.5: Generate visual assets from designer's asset manifest."""
    import fal_client
    
    run_dir = RUNS_DIR / state["name"]
    assets_dir = run_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    
    for i, approach in enumerate(state["approaches"]):
        if approach.get("status") != "approved":
            continue
        
        manifest = extract_asset_manifest(approach["content"])
        if not manifest:
            print(f"  [assets] Designer {i}: no asset manifest found")
            continue
        
        concept_assets = assets_dir / f"concept-{i}"
        concept_assets.mkdir(exist_ok=True)
        
        generated = []
        for asset in manifest:
            model = route_model(asset)
            prompt = build_asset_prompt(asset, approach["content"])
            
            print(f"  [assets] Generating: {asset['name']} via {model}")
            
            result = fal_client.subscribe(
                model,
                arguments={
                    "prompt": prompt,
                    "image_size": {
                        "width": asset.get("width", 1080),
                        "height": asset.get("height", 1080),
                    },
                    "num_images": 1,
                },
            )
            
            # Download and save
            img_url = result["images"][0]["url"]
            img_path = concept_assets / f"{asset['name']}.png"
            download_image(img_url, img_path)
            
            # Also save as base64 for builder injection
            with open(img_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            
            generated.append({
                "name": asset["name"],
                "path": str(img_path),
                "b64_size_kb": len(b64) // 1024,
                "prompt": prompt[:200],
                "model": model,
            })
            
            track_cost(model, 0, 0, "asset_gen", 
                       override_cost=ASSET_GEN_COSTS.get(model, 0.05))
        
        # Save manifest with paths for builder
        manifest_path = concept_assets / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(generated, f, indent=2)
        
        state["approaches"][i]["assets"] = generated
        print(f"  [assets] Designer {i}: generated {len(generated)} assets")
    
    return state
```

## Model Routing Logic

```python
ASSET_MODEL_MAP = {
    "texture": "fal-ai/flux/schnell",        # Fast, cheap, abstract
    "product": "fal-ai/flux-2-pro",           # Photorealistic
    "graphic": "fal-ai/recraft-v3",           # Text + design
    "decoration": "fal-ai/flux/schnell",      # Abstract overlays
    "atmosphere": "fal-ai/flux-2-pro",        # Realistic effects
    "illustration": "fal-ai/nano-banana-2",   # Creative intent
}

ASSET_GEN_COSTS = {
    "fal-ai/flux/schnell": 0.003,
    "fal-ai/flux-2-pro": 0.03,
    "fal-ai/recraft-v3": 0.06,
    "fal-ai/nano-banana-2": 0.08,
}

def route_model(asset: dict) -> str:
    """Route to best model based on asset type and optional hint."""
    if asset.get("model_hint"):
        # Map shorthand to full endpoint
        hints = {
            "flux-schnell": "fal-ai/flux/schnell",
            "flux-2-pro": "fal-ai/flux-2-pro",
            "recraft-v3": "fal-ai/recraft-v3",
            "nano-banana-2": "fal-ai/nano-banana-2",
            "ideogram-v3": "fal-ai/ideogram-v3",
        }
        return hints.get(asset["model_hint"], ASSET_MODEL_MAP.get(asset["type"], "fal-ai/flux/schnell"))
    return ASSET_MODEL_MAP.get(asset["type"], "fal-ai/flux/schnell")
```

## Builder Integration

The builder receives assets as:

1. **Asset manifest JSON** — what was generated, file paths, dimensions
2. **Base64 data URIs** — embedded directly in the HTML as `<img src="data:image/png;base64,...">` or CSS `background-image: url(data:...)`
3. **Vision input** — top 3 assets sent as multimodal images so the builder can SEE what it's working with

### Builder Prompt Addition

```
## GENERATED ASSETS
You have {N} pre-generated visual assets. Use them instead of CSS gradients or placeholder boxes.

Assets available:
{for each asset}
- **{name}** ({dimensions}): {description}
  Usage: `<img src="data:image/png;base64,{ASSET_{name}_B64}" />`
  Or CSS: `background-image: url(data:image/png;base64,{ASSET_{name}_B64});`
{/for}

CRITICAL: These are REAL images, not placeholders. Embed them. Your build should look like
a designed artifact, not a code prototype. The assets ARE the design — your HTML is the frame.
```

### Context Budget Impact

Asset base64 is large. A 540×540 PNG ≈ 300-500KB base64. For 5 assets that's ~2MB.

**Mitigation strategies:**
1. **Compress aggressively** — resize to exact needed dimensions, use JPEG for photos (80% quality), PNG only for transparency
2. **Host externally** — upload to a temp URL instead of base64 (preferred for large assets)
3. **Limit count** — max 5-6 assets per concept (most impactful ones)
4. **Prioritize** — hero background + top product shot are highest value; decorative elements can stay CSS

**Recommended approach:** 
- Upload generated assets to here.now as a temp directory
- Builder references them as `https://{slug}.here.now/assets/{name}.jpg`
- Final build downloads and embeds them
- This avoids the context window tax entirely

## Designer Prompt Updates

Add to `DESIGNER.md`:

```markdown
## Asset Manifest (REQUIRED)

Your approach doc MUST include an `## ASSET MANIFEST` section listing visual assets that 
should be GENERATED (not coded) for the build. Think like an art director commissioning work:

For each asset specify:
- **name**: slug identifier (e.g., hero-texture, rank-badge, product-hero)
- **type**: texture | product | graphic | decoration | atmosphere | illustration
- **description**: Detailed visual description — be specific about colors, style, lighting, composition
- **dimensions**: WxH in pixels
- **model_hint** (optional): flux-schnell, flux-2-pro, recraft-v3, nano-banana-2

### What to generate (DO):
- Background textures (concrete, paper, fabric, abstract)
- Product photography (styled hero shots of the items being ranked)
- Graphic elements (badges, stamps, dividers, rank indicators)
- Atmospheric effects (smoke, light leaks, bokeh, grain overlays)
- Custom typography treatments (via Recraft V3)

### What NOT to generate (the builder handles these):
- UI elements (buttons, inputs)
- Animations (GSAP/CSS handles this)
- Layout structure (HTML/CSS)
- Interactive elements
```

## Sharecard-Specific Assets

For the Rerank Sharecard (Top 10 Sneakers), a typical asset manifest would include:

| Asset | Type | Model | Purpose |
|---|---|---|---|
| `bg-texture` | texture | schnell | Full-card background (concrete, paper, dark surface) |
| `sneaker-hero` | product | flux-2-pro | #1 ranked sneaker, dramatic angle, studio lit |
| `sneaker-02` through `sneaker-05` | product | flux-2-pro | Top 5 product shots (smaller) |
| `rank-badge-1` | graphic | recraft-v3 | "#1" badge/stamp with metallic/embossed feel |
| `distress-overlay` | decoration | schnell | Scratch/grain overlay for texture depth |
| `brand-lockup` | graphic | recraft-v3 | "RERANK × COMPLEX" styled typography |

**Estimated cost per concept:** ~$0.30 (8 assets: 2 schnell + 5 flux-pro + 1 recraft)  
**Total for 3 concepts:** ~$0.90  
**Added to current $0.80 pipeline cost:** ~$1.70 total (still well under $20 budget)

## Implementation Phases

### Phase 1: Minimal Viable (2-3 hours)
1. Add `extract_asset_manifest()` parser
2. Add `asset_gen_node()` with fal.ai integration
3. Wire into graph between approach_gate and builder
4. Update designer prompt with asset manifest requirement
5. Update builder prompt with asset embedding instructions
6. Host assets on here.now temp URL (avoid base64 context bloat)

### Phase 2: Quality Loop (1-2 hours)  
1. Add asset QA — verify generated images match prompt (vision check)
2. Retry bad generations (wrong subject, wrong style)
3. Add to cost tracking (per-model rates)

### Phase 3: Sophistication (future)
1. Style LoRA training for consistent visual language across assets
2. Product-specific LoRA (train on real sneaker photos for higher fidelity)
3. Recraft V3 vector assets for resolution-independent graphics
4. Asset caching — reuse textures across runs

## Graph Update

```
Current:  research → designer → approach_gate → builder → qa → judge → human_gate
Proposed: research → designer → approach_gate → ASSET_GEN → builder → qa → judge → human_gate
```

Fan-out pattern: asset_gen runs per-concept (like builder), generating assets from each approved approach doc's manifest.

## Decision Points

1. **Asset hosting:** Base64 embed vs here.now URL vs local file path?  
   → Recommend here.now URL (avoids context bloat, builder just references URLs)

2. **Product images:** Generate stylized sneaker shots or use placeholder silhouettes?  
   → Generate. FLUX.2 Pro does excellent product photography from text prompts.

3. **How many assets per concept?** 
   → Start with 5-8. Hero bg + top 3-5 product shots + 1-2 decorative elements.

4. **When to skip?** 
   → If designer's approach is purely kinetic typography / data viz with no imagery needs, skip asset gen.

---

*Plan generated May 3, 2026. Ready for implementation.*
