# Advanced Techniques

Deeper techniques for when you need to push beyond standard animation libraries. These require more investment but produce truly unique results.

## Table of Contents

1. [Custom GLSL Shaders](#shaders)
2. [Composite Rendering & Scene Transitions](#composite-rendering)
3. [Postprocessing Effects](#postprocessing)
4. [Scroll-Controlled Video](#scroll-video)
5. [Generative/Procedural Art](#generative)
6. [Advanced GSAP Techniques](#advanced-gsap)
7. [Performance Optimization](#performance)

---

## Custom GLSL Shaders {#shaders}

Shaders run on the GPU and enable effects impossible with CSS or JavaScript alone.

### Image Distortion on Hover

```glsl
// fragment.glsl
uniform sampler2D uTexture;
uniform float uHover; // 0 → 1
uniform vec2 uMouse;  // normalized mouse position
varying vec2 vUv;

void main() {
  vec2 uv = vUv;
  float dist = distance(uv, uMouse);
  float strength = smoothstep(0.5, 0.0, dist) * uHover * 0.1;
  uv += strength * normalize(uv - uMouse);
  gl_FragColor = texture2D(uTexture, uv);
}
```

Use with R3F's `shaderMaterial` for image galleries that warp on hover.

### Noise-Based Color Flow

```glsl
// Organic, flowing color gradients
uniform float uTime;
varying vec2 vUv;

// simplex noise function (include snoise3D)

void main() {
  float n = snoise(vec3(vUv * 3.0, uTime * 0.2));
  vec3 color1 = vec3(0.1, 0.0, 0.3);
  vec3 color2 = vec3(0.0, 0.3, 0.8);
  vec3 color3 = vec3(0.8, 0.1, 0.3);
  vec3 color = mix(mix(color1, color2, n), color3, sin(n * 3.14));
  gl_FragColor = vec4(color, 1.0);
}
```

### Useful Shader Resources
- **The Book of Shaders** (thebookofshaders.com) — essential learning
- **Shadertoy** (shadertoy.com) — inspiration and adaptable effects
- **GLSL Sandbox** (glslsandbox.com) — live shader editing
- **lygia** (github.com/patriciogonzalezvivo/lygia) — shader function library

## Composite Rendering & Scene Transitions {#composite-rendering}

**The breakthrough technique for seamless WebGL transitions.** Instead of rendering 3D scenes directly to screen, render them to off-screen textures (render targets), then composite them with custom shaders. This enables smooth transitions between entirely different scenes without duplicating geometry.

*Source: [Codrops - Composite Rendering](https://tympanus.net/codrops/2026/02/23/composite-rendering-the-brilliance-behind-inspiring-webgl-transitions/) (Feb 2026)*

### The Core Pattern

```tsx
import * as THREE from 'three';
import { useFrame, useThree } from '@react-three/fiber';
import { useMemo, useRef } from 'react';

export function CompositeRenderer({ children }) {
  const { gl, size } = useThree();
  const sceneA = useRef(new THREE.Scene());
  const sceneB = useRef(new THREE.Scene());
  const compositeScene = useRef(new THREE.Scene());
  
  // Render targets for each scene
  const renderTargetA = useMemo(() => 
    new THREE.WebGLRenderTarget(size.width, size.height, {
      minFilter: THREE.LinearFilter,
      magFilter: THREE.LinearFilter,
      format: THREE.RGBAFormat,
      stencilBuffer: false,
    }), [size]);
    
  const renderTargetB = useMemo(() => 
    new THREE.WebGLRenderTarget(size.width, size.height), [size]);

  // Composite shader for blending scenes
  const compositeMaterial = useMemo(() => new THREE.ShaderMaterial({
    uniforms: {
      uFromTexture: { value: null },
      uToTexture: { value: null },
      uTransition: { value: 0 }, // 0 = from scene, 1 = to scene
      uTime: { value: 0 }
    },
    vertexShader: `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = vec4(position.xy, 1.0, 1.0); // fullscreen quad
      }
    `,
    fragmentShader: `
      uniform sampler2D uFromTexture;
      uniform sampler2D uToTexture;
      uniform float uTransition;
      uniform float uTime;
      varying vec2 vUv;

      void main() {
        vec4 fromColor = texture2D(uFromTexture, vUv);
        vec4 toColor = texture2D(uToTexture, vUv);
        
        // Basic transition - customize this for creative effects
        vec4 color = mix(fromColor, toColor, uTransition);
        
        gl_FragColor = color;
      }
    `
  }), []);

  // Fullscreen quad for compositing
  const quad = useMemo(() => new THREE.Mesh(
    new THREE.PlaneGeometry(2, 2),
    compositeMaterial
  ), [compositeMaterial]);

  useFrame((state, delta) => {
    // Render scene A to texture
    gl.setRenderTarget(renderTargetA);
    gl.render(sceneA.current, state.camera);
    
    // Render scene B to texture
    gl.setRenderTarget(renderTargetB);
    gl.render(sceneB.current, state.camera);
    
    // Composite and render to screen
    compositeMaterial.uniforms.uFromTexture.value = renderTargetA.texture;
    compositeMaterial.uniforms.uToTexture.value = renderTargetB.texture;
    compositeMaterial.uniforms.uTime.value += delta;
    
    compositeScene.current.clear();
    compositeScene.current.add(quad);
    
    gl.setRenderTarget(null);
    gl.render(compositeScene.current, state.camera);
  });

  return null; // Scenes managed programmatically
}
```

### Creative Transition Effects

Replace the basic `mix()` in the fragment shader with these patterns:

```glsl
// Wipe transition (left to right)
float progress = step(uTransition, vUv.x);
vec4 color = mix(fromColor, toColor, progress);

// Diagonal wipe
float diagonal = (vUv.x + vUv.y) / 2.0;
float progress = smoothstep(uTransition - 0.3, uTransition + 0.3, diagonal);
vec4 color = mix(fromColor, toColor, progress);

// Radial reveal from center
vec2 center = vec2(0.5);
float dist = distance(vUv, center);
float progress = smoothstep(uTransition - 0.3, uTransition + 0.3, dist);
vec4 color = mix(toColor, fromColor, progress);

// Pixelate transition
vec2 pixelSize = vec2(20.0 * (1.0 - uTransition) + 1.0);
vec2 pixelUv = floor(vUv * pixelSize) / pixelSize;
vec4 fromPixel = texture2D(uFromTexture, pixelUv);
vec4 toPixel = texture2D(uToTexture, pixelUv);
vec4 color = mix(fromPixel, toPixel, uTransition);
```

### Scene Management Pattern

```tsx
// Route-based scene switching with GSAP
const [currentScene, setCurrentScene] = useState('home');
const transitionProgress = useRef({ value: 0 });

function transitionTo(newScene: string) {
  gsap.to(transitionProgress.current, {
    value: 1,
    duration: 1.2,
    ease: "power3.inOut",
    onComplete: () => {
      // Swap scenes and reset
      setCurrentScene(newScene);
      transitionProgress.current.value = 0;
    }
  });
}

// In render loop
compositeMaterial.uniforms.uTransition.value = transitionProgress.current.value;
```

### Performance Optimizations

1. **Reuse render targets** — don't recreate on every frame
2. **Conditional rendering** — only render scenes when transitioning or when they change
3. **Texture disposal** — clean up render targets on unmount
4. **Smart resizing** — update render target size on window resize

```tsx
// Dispose resources properly
useEffect(() => {
  return () => {
    renderTargetA.dispose();
    renderTargetB.dispose();
    compositeMaterial.dispose();
  };
}, []);
```

### Use Cases

- **Page transitions** — Smooth morphing between different page layouts
- **Product configurators** — Blend between different materials/colors seamlessly  
- **Story-driven experiences** — Narrative-based scene transitions
- **Interactive galleries** — Fluid movement between different image sets
- **Dashboard morphing** — Data visualizations that flow into each other

### Advanced: Multiple Render Layers

For ultra-sophisticated experiences, layer multiple render targets:

```glsl
// Composite shader with multiple layers
uniform sampler2D uBackgroundLayer;
uniform sampler2D uContentLayer;  
uniform sampler2D uUILayer;
uniform float uBackgroundOpacity;
uniform float uContentOpacity;

void main() {
  vec4 bg = texture2D(uBackgroundLayer, vUv) * uBackgroundOpacity;
  vec4 content = texture2D(uContentLayer, vUv) * uContentOpacity;
  vec4 ui = texture2D(uUILayer, vUv);
  
  // Alpha blending
  vec4 color = bg;
  color = mix(color, content, content.a);
  color = mix(color, ui, ui.a);
  
  gl_FragColor = color;
}
```

This pattern powers sites like [Active Theory](https://activetheory.net/), [Aircord](https://aircord.co.jp/), and [Kenta Toshikura](https://kentatoshikura.com/) for seamless multi-scene experiences.

## Postprocessing Effects {#postprocessing}

R3F postprocessing adds cinematic quality to 3D scenes.

```bash
npm i @react-three/postprocessing postprocessing
```

### Common Stack

```tsx
import { EffectComposer, Bloom, ChromaticAberration, Noise, Vignette } from "@react-three/postprocessing";

<EffectComposer>
  <Bloom luminanceThreshold={0.6} luminanceSmoothing={0.9} intensity={0.4} />
  <ChromaticAberration offset={[0.001, 0.001]} />
  <Noise opacity={0.03} />
  <Vignette eskil={false} offset={0.1} darkness={0.5} />
</EffectComposer>
```

### Effect Use Cases

| Effect | Creates | Use For |
|--------|---------|---------|
| Bloom | Glow on bright areas | Premium/luxury feel, neon aesthetics |
| ChromaticAberration | RGB fringing at edges | Glitch, analog camera, lo-fi |
| Noise | Film grain over 3D scene | Warmth, texture |
| Vignette | Darkened corners | Focus attention to center |
| DepthOfField | Bokeh blur by distance | Photorealistic, cinematic |
| GodRays | Light beams from a source | Dramatic lighting, ethereal |
| Glitch | Digital glitch distortion | Edgy, cyberpunk, error states |

## Scroll-Controlled Video {#scroll-video}

Scrubbing through a video with scroll (like Apple AirPods Pro page):

```tsx
"use client";
import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

export function ScrollVideo({ src }: { src: string }) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    // Wait for video metadata
    video.addEventListener("loadedmetadata", () => {
      ScrollTrigger.create({
        trigger: video.parentElement,
        start: "top top",
        end: "+=300%", // 3x viewport = scroll distance
        pin: true,
        scrub: 1,
        onUpdate: (self) => {
          video.currentTime = self.progress * video.duration;
        },
      });
    });
  }, []);

  return (
    <div className="h-screen w-full">
      <video
        ref={videoRef}
        src={src}
        muted
        playsInline
        preload="auto"
        className="h-full w-full object-cover"
      />
    </div>
  );
}
```

**Tips:**
- Encode video in H.264 with keyframes every 1-2 frames for smooth scrubbing
- Keep videos under 20MB, use lower resolution if needed (the scrub hides quality loss)
- Preload the video or show a loading state
- Alternative: use an image sequence (more responsive but larger total size)

### Image Sequence Alternative

```tsx
// For buttery smooth scroll scrubbing, preload an image sequence
const frameCount = 120;
const images = Array.from({ length: frameCount }, (_, i) =>
  `/frames/frame-${String(i).padStart(4, "0")}.webp`
);

// Draw to canvas based on scroll progress
useEffect(() => {
  const canvas = canvasRef.current;
  const ctx = canvas?.getContext("2d");
  if (!ctx || !canvas) return;

  ScrollTrigger.create({
    trigger: canvas.parentElement,
    start: "top top",
    end: "+=300%",
    pin: true,
    scrub: 1,
    onUpdate: (self) => {
      const frame = Math.min(frameCount - 1, Math.floor(self.progress * frameCount));
      const img = preloadedImages[frame]; // preload all images on mount
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    },
  });
}, []);
```

## Generative/Procedural Art {#generative}

For unique, non-repeatable visual elements:

### Perlin Noise Flow Field

```tsx
// Canvas-based flow field — great for backgrounds
function drawFlowField(ctx: CanvasRenderingContext2D, width: number, height: number) {
  const scale = 20;
  const cols = Math.floor(width / scale);
  const rows = Math.floor(height / scale);
  const particles: { x: number; y: number }[] = [];

  for (let i = 0; i < 1000; i++) {
    particles.push({ x: Math.random() * width, y: Math.random() * height });
  }

  function animate() {
    ctx.fillStyle = "rgba(0, 0, 0, 0.02)"; // slow fade trail
    ctx.fillRect(0, 0, width, height);

    particles.forEach((p) => {
      const col = Math.floor(p.x / scale);
      const row = Math.floor(p.y / scale);
      const angle = noise2D(col * 0.1, row * 0.1) * Math.PI * 2;
      p.x += Math.cos(angle) * 1;
      p.y += Math.sin(angle) * 1;

      // Wrap
      if (p.x < 0) p.x = width; if (p.x > width) p.x = 0;
      if (p.y < 0) p.y = height; if (p.y > height) p.y = 0;

      ctx.fillStyle = "rgba(255, 255, 255, 0.3)";
      ctx.fillRect(p.x, p.y, 1, 1);
    });
    requestAnimationFrame(animate);
  }
  animate();
}
```

### Useful Libraries for Generative Work
- **simplex-noise** — fast noise functions
- **p5.js** — creative coding (use in React with react-p5 or instance mode)
- **pts.js** — geometry and creative coding primitives
- **matter.js** — 2D physics (falling objects, cloth simulation)

## Advanced GSAP Techniques {#advanced-gsap}

### SplitText for Character Animation

```tsx
// GSAP SplitText (Club plugin — or DIY with the RevealText pattern)
// For each headline, split into chars/words/lines and stagger
const split = new SplitText(".headline", { type: "chars,words,lines" });
gsap.from(split.chars, {
  y: 100, opacity: 0, rotationX: -90,
  stagger: 0.02, duration: 0.8, ease: "back.out(1.7)",
  scrollTrigger: { trigger: ".headline", start: "top 80%" }
});
```

### FLIP for Layout Magic

```tsx
// Animate between two completely different layouts
const state = Flip.getState(".grid-item");

// Change the DOM layout (reorder, resize, reparent)
container.classList.toggle("alt-layout");

// Animate from old positions to new
Flip.from(state, {
  duration: 0.8,
  ease: "power3.inOut",
  stagger: 0.05,
  absolute: true,
});
```

### DrawSVG for Path Animation

```tsx
// Animate SVG paths drawing on screen
gsap.from(".svg-path", {
  drawSVG: 0,
  duration: 2,
  ease: "power2.inOut",
  stagger: 0.2,
  scrollTrigger: { trigger: ".svg-container", start: "top 70%" }
});
```

## Performance Optimization {#performance}

### Critical Rules

1. **Animate only `transform` and `opacity`** — these are GPU-composited. Animating `width`, `height`, `top`, `left`, `margin` causes layout recalculations.

2. **Use `will-change` sparingly** — only on elements about to animate:
```css
.about-to-animate { will-change: transform, opacity; }
```

3. **Throttle scroll handlers** — GSAP ScrollTrigger handles this internally. If writing custom scroll logic, use `requestAnimationFrame`.

4. **Lazy load heavy elements**:
```tsx
<Canvas style={{ opacity: inView ? 1 : 0 }}>
  {inView && <HeavyScene />}
</Canvas>
```

5. **Optimize Three.js scenes**:
   - Use `instancedMesh` for repeated geometries (particles, objects)
   - Limit draw calls — merge geometries where possible
   - Use `LOD` (Level of Detail) for complex models
   - Dispose of materials/geometries on unmount
   - Target 60fps — use `useFrame` wisely, avoid allocations in render loop

6. **Image optimization**:
   - Use Next/Image with proper sizing and formats (WebP/AVIF)
   - Use `loading="lazy"` for below-fold images
   - Preload hero images/videos

7. **Bundle size awareness**:
   - Three.js is ~600KB — use dynamic imports: `const Canvas = dynamic(() => import("./Canvas"), { ssr: false })`
   - GSAP core is small (~30KB), plugins add incrementally
   - Tree-shake drei — import only what you use

## Emerging Techniques (2026) {#emerging-2026}

Latest techniques trending in the creative dev community. Monitor these for prototype inspiration:

### Scroll-Velocity Reactive Galleries
*Source: [Codrops - Scroll-Reactive 3D Gallery](https://tympanus.net/codrops/2026/03/09/building-a-scroll-reactive-3d-gallery-with-three-js-velocity-and-mood-based-backgrounds/)*

3D galleries that respond to scroll velocity — faster scrolling triggers different visual effects:

```tsx
const velocity = useRef(0);

useFrame(() => {
  // Track scroll velocity
  const currentScroll = window.scrollY;
  const newVelocity = (currentScroll - prevScroll.current) * 0.1;
  velocity.current = THREE.MathUtils.lerp(velocity.current, newVelocity, 0.1);
  
  // Apply velocity-based effects
  material.uniforms.uVelocity.value = Math.abs(velocity.current);
  prevScroll.current = currentScroll;
});
```

### DOM-to-WebGL Upgrade Patterns  
*Source: [Codrops - DOM to WebGL Parallax](https://tympanus.net/codrops/2026/02/19/creating-a-smooth-horizontal-parallax-gallery-from-dom-to-webgl/)*

Start with CSS/DOM for layout, then seamlessly upgrade to WebGL for performance:

1. Build the experience in DOM first (functional, accessible)
2. Use `getBoundingClientRect()` to capture DOM element positions
3. Create WebGL planes that match the DOM positions exactly
4. Fade out DOM, fade in WebGL with identical positioning
5. Now you have GPU-accelerated version with shader effects

### WebGPU Production Ready (2026)
*Source: [Three.js 2026 Update](https://www.utsubo.com/blog/threejs-2026-what-changed)*

WebGPU is now production-ready across all major browsers (including Safari iOS as of Sept 2025). Three.js r171+ provides zero-config WebGPU support with significant performance improvements over WebGL.

**Quick Migration:**
```tsx
// Old: WebGL renderer  
import { WebGLRenderer } from 'three';

// New: WebGPU renderer (with WebGL2 fallback)
import { WebGPURenderer } from 'three/webgpu';

const renderer = new WebGPURenderer();
// Automatic fallback to WebGL2 on older browsers
```

**Key Benefits:**
- **~100x performance improvement** for compute-heavy applications (particles, physics)
- **Compute shaders** — run ML models directly on GPU in browser
- **Better multi-threading** — less main thread blocking
- **Modern GPU optimizations** — especially on mobile devices

**Best Use Cases:**
- Large particle systems (1M+ particles)
- Real-time data visualization with millions of points
- GPU-accelerated physics simulations
- AI/ML model inference (via compute shaders)
- Multi-scene composite rendering

**Browser Support (2026):**
- Chrome/Edge: Full support since 2024
- Firefox: Full support since early 2025  
- Safari: Desktop + iOS support since Sept 2025
- Three.js handles fallback automatically

### Hand Gesture Particle Control
*Source: Reddit - MediaPipe + Particle Simulation*

Combine MediaPipe hand tracking with GPU particle systems:

```tsx
// Use MediaPipe Hands for gesture recognition
import { Hands } from '@mediapipe/hands';

// Drive particle simulations with hand positions
useFrame(() => {
  if (handLandmarks) {
    const indexFinger = handLandmarks[8]; // MediaPipe landmark index
    particleSystem.setAttractor(indexFinger.x, indexFinger.y);
  }
});
```

### Watercolor-Style Shaders
*Source: Reddit - Susurrus watercolor world*

Fluid, organic shader effects using noise-based dissolve patterns:

```glsl
// Watercolor dissolve effect
uniform float uDissolve;
uniform sampler2D uNoiseTexture;

void main() {
  float noise = texture2D(uNoiseTexture, vUv * 3.0).r;
  float dissolve = smoothstep(uDissolve - 0.1, uDissolve + 0.1, noise);
  
  vec3 color = mix(vec3(1.0, 0.8, 0.6), vec3(0.2, 0.4, 0.8), dissolve);
  gl_FragColor = vec4(color, dissolve);
}
```

### Multi-Page WebGL with Barba.js
*Source: [Codrops - Scroll-Revealed WebGL Gallery](https://tympanus.net/codrops/2026/02/02/building-a-scroll-revealed-webgl-gallery-with-gsap-three-js-astro-and-barba-js/)*

Persistent WebGL canvas across page transitions using Barba.js:

- Single Three.js context persists across route changes
- Page-specific scenes load/unload dynamically
- Smooth transitions between different page layouts
- Scroll triggers work seamlessly with page transitions

**Monitor these resources for cutting-edge techniques:**
- [Codrops](https://tympanus.net/codrops/) — monthly advanced tutorials
- [r/creativecoding](https://reddit.com/r/creativecoding) — community experiments
- [r/threejs](https://reddit.com/r/threejs) — Three.js specific techniques
- [Awwwards](https://awwwards.com/websites/three-js/) — award-winning WebGL sites
