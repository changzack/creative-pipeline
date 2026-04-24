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
8. [Emerging Techniques (2026)](#emerging-2026) — WebGPU, TSL, fluid X-ray, native scroll animations
9. [TSL Migration Guide: GLSL → TSL](#tsl-migration)

---

## Persistent 3D Scenes with Page Transitions {#persistent-3d}

**Breakthrough pattern for seamless multi-page WebGL experiences.** A single Three.js context survives across page navigation, with smooth camera movements and content transitions instead of reloading the 3D scene.

*Source: [Codrops - Seamless 3D Transitions](https://tympanus.net/codrops/2026/03/18/building-seamless-3d-transitions-with-webflow-gsap-and-three-js/) (Mar 2026)*

### The Core Architecture

Unlike traditional page transitions that reload everything, this pattern maintains:
- **One persistent Canvas** — never destroyed or recreated
- **Single Experience instance** — scene, renderer, resources persist
- **Route-based camera movement** — slides between 3D objects positioned along axes
- **Content swapping** — only HTML content changes, 3D scene stays alive

### Key Technologies

- **Barba.js** — handles page transitions and DOM swapping
- **Three.js** — persistent 3D scene with models positioned spatially  
- **GSAP** — smooth camera movement and text animations
- **Vite + Webflow** — build system for external script deployment

### Implementation Pattern

```tsx
// 1. Experience as singleton - persists across navigation
export default class Experience {
  constructor(canvas) {
    // Only created ONCE on first page load
    this.canvas = canvas;
    this.scene = new THREE.Scene();
    this.camera = new Camera(); // Position: (0, 0, 1)
    this.renderer = new Renderer();
    this.world = new World(); // Models positioned along X-axis
  }
  
  // Never destroyed - this is the key insight
}

// 2. World positions models spatially for camera movement
class World {
  constructor() {
    this.modelsGroup = new THREE.Group();
    
    // Position models along X-axis for camera sliding
    const modelsConfig = [
      { name: 'pen', positionX: 0 },     // /pen → camera.position.x = 0
      { name: 'cup', positionX: 3 },     // /cup → camera.position.x = 3  
      { name: 'suzanne', positionX: 6 }  // /suzanne → camera.position.x = 6
    ];
    
    this.models = modelsConfig.map(({ name, positionX }) =>
      new Model(name, positionX, this.modelsGroup)
    );
  }
}

// 3. Barba handles page swapping, NOT 3D scene
barba.init({
  transitions: [{
    name: 'default-transition',
    
    once({ next }) {
      // Create Experience ONCE - never again
      experience = new Experience(document.querySelector('.webgl'));
      animateCameraToNamespace(next.namespace, experience);
    },
    
    leave(data) {
      // Animate content OUT while camera moves
      return transitionOut(data); // GSAP timeline
    },
    
    enter(data) {
      // Camera + content animate IN together  
      animateCameraToNamespace(data.next.namespace, experience);
      return transitionIn(data); // GSAP timeline
    }
  }]
});

// 4. Camera movement maps routes to 3D positions
const cameraPositionsByNamespace = {
  pen: 0,
  cup: 3,
  suzanne: 6
};

function animateCameraToNamespace(namespace, experience) {
  const targetX = cameraPositionsByNamespace[namespace] ?? 0;
  gsap.to(experience.camera.instance.position, {
    x: targetX,
    duration: 2,
    ease: 'expo.inOut'
  });
}
```

### Critical Markup Structure

```html
<!-- Canvas lives OUTSIDE Barba container - never swapped -->
<body data-barba="wrapper">
  <canvas class="webgl"></canvas>
  
  <!-- Only this gets swapped between pages -->
  <div data-barba="container" data-barba-namespace="pen">
    <h1 data-animation="title">Pen Page</h1>
    <p data-animation="text">Content about pens...</p>
  </div>
</body>
```

### Advanced Techniques from the Pattern

**1. Canvas Blend Modes for Paper Texture:**
```css
/* Canvas multiply blend with background texture */
.webgl {
  mix-blend-mode: multiply;
  /* Paper texture positioned behind canvas */
}

.paper-background {
  position: absolute;
  z-index: -1;
  background-image: url('/paper-texture.jpg');
  /* WebGL renders on top, blends with paper */
}
```

**2. ShadowMaterial for Grounded Scenes:**
```tsx
// Invisible plane that only shows cast shadows
const shadowPlane = new THREE.Mesh(
  new THREE.PlaneGeometry(10, 10),
  new THREE.ShadowMaterial({ opacity: 0.3 })
);
shadowPlane.position.z = -0.25; // Slightly behind models
shadowPlane.receiveShadow = true;

// Result: shadows appear directly on page background,
// not on visible geometry - seamless integration
```

**3. Mouse-Reactive Model Groups:**
```tsx
// Each model has nested structure for mouse interaction
class Model {
  constructor(name, positionX, parent) {
    this.group = new THREE.Group();
    this.group.position.x = positionX;
    
    // mouseGroup provides subtle cursor following
    this.mouseGroup = new THREE.Group();
    this.group.add(this.mouseGroup);
    
    // model goes inside mouseGroup for reactivity
    this.mouseGroup.add(this.model);
    parent.add(this.group);
  }
}

// In render loop - models follow cursor subtly
useFrame(() => {
  const targetRotationX = mouseY * 0.0005;
  const targetRotationY = mouseX * 0.0005;
  
  models.forEach(model => {
    model.mouseGroup.rotation.x = lerp(
      model.mouseGroup.rotation.x,
      targetRotationX,
      0.08
    );
  });
});
```

### When to Use This Pattern

**Perfect for:**
- Portfolio sites with consistent 3D branding across pages
- Product showcases where each page represents a different model
- Narrative sites where 3D scene tells a story across multiple pages
- Brand sites needing premium feel without reload flicker

**Requirements:**
- Static site generation (Gatsby, Next.js, Astro) or headless CMS
- Models can be positioned spatially (not all in same location)
- Consistent 3D aesthetic across all pages
- Performance budget for persistent 3D context

### Performance Considerations

**Benefits:**
- No model reloading between pages
- No Three.js context recreation
- Smooth experience vs page reload flicker
- Progressive loading - models loaded once, cached

**Costs:**
- 3D context always running (battery impact on mobile)
- Memory footprint higher than traditional sites  
- Initial load includes all models for the experience
- Requires careful resource management

### Accessibility Adaptations

```tsx
// Respect prefers-reduced-motion
const mm = gsap.matchMedia();
mm.add('(prefers-reduced-motion: no-preference)', () => {
  // Full camera movement and text animations
});

mm.add('(prefers-reduced-motion: reduce)', () => {
  // Instant page swaps, no camera movement
  gsap.set(camera.position, { x: targetX });
});
```

### Production Examples

This pattern powers sites like:
- **Portfolio/Agency sites** — continuous 3D brand presence
- **Product showcases** — each page = different 3D model  
- **Storytelling sites** — 3D environment that evolves with narrative
- **Premium brand experiences** — seamless luxury feel

The technique represents a fundamental shift from "pages with 3D elements" to "a 3D world with page content" — opening new creative possibilities for cohesive digital experiences.

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

### easeReverse for Better UI Animations
*Source: [Codrops - A Playful Clip Menu with GSAP's easeReverse](https://tympanus.net/codrops/2026/04/22/a-playful-clip-menu-with-gsaps-easereverse/) (Apr 2026)*

**GSAP 3.15+ breakthrough:** When reversing animations, `easeReverse` lets you specify a different easing curve for the reverse direction. This solves the common problem where an `ease-out` animation played backwards becomes sluggish `ease-in`.

**The problem:** 
```tsx
// This feels awkward when reversed
gsap.to(menu, {
  x: 300,
  duration: 0.8,
  ease: "expo.out"  // Smooth entry, but jerky when reversed
});

// Later: menu.reverse(); // Now it's expo.IN — feels sluggish
```

**The solution:**
```tsx
const tl = gsap.timeline();

tl.to(menu, {
  x: 300,
  duration: 0.8,
  ease: "expo.out",
  easeReverse: "elastic.out(0.3)" // Different feel for reverse direction
});

// Usage in menu toggle
const isOpen = useRef(false);

const toggleMenu = () => {
  if (isOpen.current) {
    tl.reverse(); // Uses elastic.out(0.3)
  } else {
    tl.play();    // Uses expo.out
  }
  isOpen.current = !isOpen.current;
};
```

**Advanced pattern for scattering UI:**
```tsx
// Menu items scatter outward on open, smoothly return on close
items.forEach((item, i) => {
  const tl = gsap.timeline({ paused: true });
  
  tl.to(item, {
    x: gsap.utils.random(-200, 200),
    y: gsap.utils.random(-200, 200),
    opacity: 0,
    rotation: gsap.utils.random(-30, 30),
    duration: 0.7,
    ease: "expo.out",
    easeReverse: "elastic.out(0.3)", // Bouncy return feel
  });
  
  menuTimelines.push(tl);
});

// Toggle all items with stagger
const toggleMenu = () => {
  menuTimelines.forEach((tl, i) => {
    const delay = i * 0.05;
    if (isOpen) {
      gsap.delayedCall(delay, () => tl.reverse());
    } else {
      gsap.delayedCall(delay, () => tl.play());
    }
  });
};
```

**Best practices:**
- **Modal/drawer interactions** — Use softer reverse easing to make dismissals feel gentle
- **Scatter/gather patterns** — Forward: expo/power, Reverse: elastic/bounce for satisfying return
- **Toggle buttons** — Forward: quick ease-out, Reverse: bouncy ease for tactile feedback
- **Menu systems** — Different personality on open vs close creates richer interaction language

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

### WebGPU Production Ready (2026) — Universal Browser Support
*Source: [Three.js 2026: What Changed](https://www.utsubo.com/blog/threejs-2026-what-changed)*

**Major milestone:** WebGPU achieved universal browser support in Sept 2025 when Apple shipped Safari 26 with full WebGPU on macOS, iOS, iPadOS, and visionOS. The "waiting game is over" — you can now ship WebGPU applications expecting them to work for every user.

**Three.js r171+ provides zero-config WebGPU:**
```tsx
// Zero-config import — automatic fallback handling
import { WebGPURenderer } from 'three/webgpu';

const renderer = new WebGPURenderer();
// Automatically falls back to WebGL2 if WebGPU unavailable
```

**Real-world performance data:**
- **100x performance improvement** documented for million-particle systems vs WebGL
- NPM downloads hit 2.7M/week (270x more than Babylon.js) — ecosystem dominance
- Powers rich applications processing millions of data points in real-time
- Physical installations use Three.js now (1M+ particle interactive artworks)

**Key WebGPU advantages over WebGL:**
- **Compute shaders** — general-purpose GPU computations (physics, ML inference, data processing)
- **Explicit GPU memory control** — better resource management
- **Modern API design** — built for contemporary GPU architectures
- **Reduced CPU overhead** — less main thread blocking

**Deployment reality check (March 2026):**
- **Chrome/Edge:** Full support since v113 (2023)
- **Firefox:** Windows support since v141, macOS ARM since v145
- **Safari:** Full support (all platforms) since v26 (Sept 2025)
- **Market reality:** Can now deploy WebGPU-first with confidence

**Migration strategy:**
Start projects with WebGPU by default. Three.js handles fallback automatically. The performance ceiling is dramatically higher, and the browser support floor is now solid.

### CSS Scroll-Driven Corner-Shape Animations  
*Source: [CSS-Tricks - Scroll-Driven corner-shape Animations](https://css-tricks.com/experimenting-with-scroll-driven-corner-shape-animations/)*

New CSS `corner-shape` property enables animatable corners beyond `border-radius`, using mathematical `superellipse()` functions. Now supports scroll-driven animation timelines (Chrome 139+, coming to Firefox via Interop 2026):

```css
/* Define the animation */
@keyframes corner-morph {
  from { corner-shape: round; }        /* superellipse(1) */
  to   { corner-shape: squircle; }     /* superellipse(2) */
}

/* Scroll-driven timeline */
.morphing-element {
  animation: corner-morph linear;
  animation-timeline: scroll(root);    /* Ties animation to scroll position */
  animation-range: 0% 100%;
}

/* Or with JS control for broader support */
.morphing-element {
  corner-shape: superellipse(var(--corner-value));
  transition: corner-shape 0.3s ease;
}
```

**Available corner-shape values:**
- `square` = `superellipse(infinity)` — sharp corners
- `squircle` = `superellipse(2)` — Apple-style rounded squares  
- `round` = `superellipse(1)` — perfect circle sectors
- `bevel` = `superellipse(0)` — chamfered edges
- `scoop` = `superellipse(-1)` — concave corners
- `notch` = `superellipse(-infinity)` — inverted corners

**React/GSAP Integration:**
```tsx
// Animate corner-shape with GSAP for better browser support
useLayoutEffect(() => {
  gsap.to(elementRef.current, {
    '--corner-value': 2,  // animates to squircle
    duration: 1,
    scrollTrigger: {
      trigger: elementRef.current,
      start: 'top center',
      end: 'bottom center',
      scrub: 1
    }
  });
}, []);
```

Use for: dynamic button states, morphing containers, scroll-reactive UI elements, progressive brand shape transitions.

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

### Non-Photorealistic Rendering (NPR) — Kuwahara Shader
*Source: [Codrops - Susurrus: Crafting a Cozy Watercolor World](https://tympanus.net/codrops/2026/04/24/susurrus-crafting-a-cozy-watercolor-world-with-three-js-and-shaders/) (Apr 2026)*

**The Kuwahara shader** transforms 3D scenes into watercolor paintings through intelligent pixel clustering and directional blur. Unlike simple blur effects, it preserves edges while creating fluid, painterly regions.

**Core technique:** For each pixel, sample surrounding regions in multiple directions, calculate the variance in each region, then blend toward the region with lowest variance (most uniform color). This creates the characteristic "flow" of watercolor paint.

```glsl
// Simplified Kuwahara implementation
uniform sampler2D uTexture;
uniform float uKernel; // Blur kernel size
uniform vec2 uResolution;

vec4 kuwahara(sampler2D tex, vec2 uv, float kernel) {
  vec2 pixel = 1.0 / uResolution;
  
  // Sample 4 regions around current pixel
  vec4 regions[4];
  float variances[4];
  
  // Top-left region
  vec3 mean = vec3(0.0);
  vec3 variance = vec3(0.0);
  
  for(int x = -int(kernel); x <= 0; x++) {
    for(int y = -int(kernel); y <= 0; y++) {
      vec3 col = texture2D(tex, uv + vec2(x, y) * pixel).rgb;
      mean += col;
      variance += col * col;
    }
  }
  
  float n = pow(kernel + 1.0, 2.0);
  mean /= n;
  variance = variance / n - mean * mean;
  float totalVariance = variance.r + variance.g + variance.b;
  
  regions[0] = vec4(mean, totalVariance);
  
  // Repeat for other 3 regions (top-right, bottom-left, bottom-right)
  // ... 
  
  // Find region with lowest variance
  int bestRegion = 0;
  for(int i = 1; i < 4; i++) {
    if(regions[i].a < regions[bestRegion].a) {
      bestRegion = i;
    }
  }
  
  return vec4(regions[bestRegion].rgb, 1.0);
}

void main() {
  gl_FragColor = kuwahara(uTexture, vUv, 4.0);
}
```

**Performance optimization:** The Kuwahara effect is expensive at full resolution. Always render to a reduced-size render target (half or quarter resolution) then composite back up. The painterly blur naturally hides the lower resolution.

**Integration with Three.js postprocessing:**
```tsx
import { EffectComposer, RenderPass, ShaderPass } from 'three-stdlib';

const kuwaharaPass = new ShaderPass({
  uniforms: {
    tDiffuse: { value: null },
    uKernel: { value: 3.0 },
    uResolution: { value: new Vector2(512, 512) } // Half-res for performance
  },
  vertexShader: /* standard fullscreen vertex */,
  fragmentShader: /* kuwahara fragment above */
});

// Render pipeline: scene → half-res kuwahara → full-res composite
composer.addPass(new RenderPass(scene, camera));
composer.addPass(kuwaharaPass);
```

**Design applications:** Perfect for cozy, meditative, or storytelling experiences. Creates an instant "handmade" aesthetic that softens harsh digital edges while maintaining interactive responsiveness.
```

### Curved 3D Product Grids with Holographic Effects
*Source: [Codrops - From Flat to Spatial](https://tympanus.net/codrops/2026/02/24/from-flat-to-spatial-creating-a-3d-product-grid-with-react-three-fiber/) (Feb 2026)*

Advanced R3F patterns for immersive e-commerce experiences: curved grid layouts, topographic GLSL backgrounds, holographic selection states, and performance-optimized state architecture.

**Key Architectural Pattern:**
```tsx
// CRITICAL: Separate React state from 60fps animation values
// React state = discrete user actions (selection, filters)
// Mutable refs = continuous animation values (position, opacity, uniforms)

const CONFIG = {
  gridCols: 8,
  itemSize: 2.5,
  gap: 0.4,
  curvatureStrength: 0.06, // Amount of Z-axis curve
  dampFactor: 0.2,
  tiltFactor: 0.08,
};

function CurvedGrid({ items, selectedId }) {
  const rigState = useRef({ 
    targetX: 0, 
    targetY: 0, 
    currentX: 0, 
    currentY: 0 
  });

  useFrame(() => {
    // 60fps camera damping - never put this in React state
    rigState.current.currentX = THREE.MathUtils.lerp(
      rigState.current.currentX, 
      rigState.current.targetX, 
      CONFIG.dampFactor
    );
  });

  return items.map((item, idx) => (
    <GridTile 
      key={item.id}
      position={calculateCurvedPosition(idx)}
      selected={item.id === selectedId}
      rigState={rigState}
    />
  ));
}

// Curved grid positioning algorithm
function calculateCurvedPosition(index) {
  const col = index % CONFIG.gridCols;
  const row = Math.floor(index / CONFIG.gridCols);
  
  const x = col * (CONFIG.itemSize + CONFIG.gap) - gridWidth / 2;
  const y = -(row * (CONFIG.itemSize + CONFIG.gap)) + gridHeight / 2;
  
  // Apply curvature - creates bowl/dome effect
  const distFromCenter = Math.sqrt(x * x + y * y);
  const z = -Math.pow(distFromCenter * CONFIG.curvatureStrength, 2);
  
  return [x, y, z];
}
```

**Holographic Selection Shader:**
```glsl
// Iridescent rainbow effect for selected cards
uniform float uSelected; // 0.0 → 1.0
uniform float uTime;
varying vec2 vUv;
varying vec3 vNormal;

void main() {
  // Base gradient
  vec3 color1 = vec3(1.0, 0.1, 0.8); // magenta
  vec3 color2 = vec3(0.1, 0.8, 1.0); // cyan
  vec3 color3 = vec3(0.8, 1.0, 0.1); // lime
  
  // Animated iridescent shift
  float shift = sin(uTime * 2.0 + vUv.x * 10.0) * 0.5 + 0.5;
  vec3 rainbow = mix(mix(color1, color2, shift), color3, vUv.y);
  
  // Apply selection state
  vec3 finalColor = mix(vec3(1.0), rainbow, uSelected);
  
  // Fresnel-based edge glow
  float fresnel = pow(1.0 - dot(vNormal, vec3(0.0, 0.0, 1.0)), 2.0);
  finalColor += fresnel * uSelected * 0.5;
  
  gl_FragColor = vec4(finalColor, 1.0);
}
```

**Performance Rules:**
1. **Never put 60fps values in React state** - kills performance via reconciliation overhead
2. **Use Leva debug controls** for all CONFIG values during development 
3. **Cull distant objects** - hide tiles beyond `cullDistance` from camera
4. **Batch uniform updates** - update shader uniforms once per frame, not per tile

### Modern GLSL Development with glslify
*Source: [Codrops - Curved 3D Grids](https://tympanus.net/codrops/2026/02/24/from-flat-to-spatial-creating-a-3d-product-grid-with-react-three-fiber/)*

Modern shader development workflow using glslify + webpack for modular GLSL:

**next.config.mjs setup:**
```js
/** @type {import('next').NextConfig} */
const nextConfig = {
  webpack: (config) => {
    config.module.rules.push({
      test: /\.(glsl|vs|fs|vert|frag)$/,
      exclude: /node_modules/,
      use: ['raw-loader', 'glslify-loader']
    });
    return config;
  }
};

export default nextConfig;
```

**Modular shader imports:**
```glsl
// shaders/topographic.frag
#pragma glslify: snoise = require('glsl-noise/simplex/2d')
#pragma glslify: fbm = require('./utils/fbm.glsl')

uniform float uTime;
uniform vec2 uResolution;
varying vec2 vUv;

void main() {
  // Layered noise for topographic effect
  float elevation = fbm(vUv * 8.0 + uTime * 0.1);
  
  // Contour lines
  float lines = abs(sin(elevation * 50.0)) < 0.1 ? 1.0 : 0.0;
  
  vec3 color = mix(vec3(0.1, 0.2, 0.4), vec3(0.8, 0.9, 1.0), elevation);
  color += lines * 0.3;
  
  gl_FragColor = vec4(color, 1.0);
}
```

```tsx
// Import as ES module
import topographicFrag from './shaders/topographic.frag';

const material = new THREE.ShaderMaterial({
  fragmentShader: topographicFrag,
  uniforms: {
    uTime: { value: 0 },
    uResolution: { value: [window.innerWidth, window.innerHeight] }
  }
});
```

### Multi-Page WebGL with Barba.js
*Source: [Codrops - Scroll-Revealed WebGL Gallery](https://tympanus.net/codrops/2026/02/02/building-a-scroll-revealed-webgl-gallery-with-gsap-three-js-astro-and-barba-js/)*

Persistent WebGL canvas across page transitions using Barba.js:

- Single Three.js context persists across route changes
- Page-specific scenes load/unload dynamically
- Smooth transitions between different page layouts
- Scroll triggers work seamlessly with page transitions

### Dual-Scene Fluid X-Ray Reveal (WebGPU + TSL)
*Source: [Codrops - Dual-Scene Fluid X-Ray Reveal](https://tympanus.net/codrops/2026/03/23/dual-scene-fluid-x-ray-reveal-effect/) (Mar 23, 2026)*

**This is the new frontier.** TSL (Three.js Shading Language) replaces GLSL for shader authoring in WebGPU mode. This tutorial demonstrates rendering two complete 3D scenes and using a real-time Navier-Stokes fluid simulation as a mask between them — something impossible with standard postprocessing.

**Why this matters:**
- TSL is JavaScript-native shader authoring (no GLSL string templates)
- Fluid sim runs as a WebGPU compute shader (not on CPU)
- Two full scenes rendered simultaneously with fluid-driven masking
- Performance: compute shaders handle physics that would tank a CPU implementation

**TSL Shader Authoring Pattern:**
```tsx
import { tslFn, uniform, texture, uv, vec4, float } from 'three/tsl';

// TSL replaces GLSL strings with composable JS functions
const fluidMaskShader = tslFn(({ sceneA, sceneB, fluidMask }) => {
  const uvCoord = uv();
  const colorA = texture(sceneA, uvCoord);
  const colorB = texture(sceneB, uvCoord);
  const mask = texture(fluidMask, uvCoord).r;
  
  // Fluid simulation drives the reveal
  return vec4(
    colorA.rgb.mul(float(1.0).sub(mask)).add(colorB.rgb.mul(mask)),
    float(1.0)
  );
});

// Use with WebGPURenderer
import { WebGPURenderer } from 'three/webgpu';
const renderer = new WebGPURenderer();
```

**Compute Shader for Fluid Simulation:**
```tsx
import { compute, storageTexture, textureStore } from 'three/tsl';

// Navier-Stokes fluid sim running entirely on GPU
const fluidCompute = compute(({ velocityField, pressureField, mousePos }) => {
  // Advection, diffusion, pressure solve — all in compute shaders
  // Mouse/touch input drives the fluid
  // Output: density texture used as scene mask
});

// Run compute pass before render
renderer.computeAsync(fluidCompute);
```

**Use Cases:**
- X-ray/reveal effects between any two scenes
- Liquid transitions driven by user touch/mouse
- Smoke/fire masking between different visual states
- Any effect where you need physics-based masking

**Key Insight:** This pattern generalizes — any GPU compute simulation (fluid, particles, cloth) can drive visual transitions between scenes. The compute shader is the creative lever.

### Chrome 146: Native Scroll-Triggered Animations (CSS-only)
*Source: CSS-Tricks, Chrome 146 release (Mar 13, 2026)*

Browser-native scroll animations without JavaScript. Uses `animation-timeline: scroll()` and `animation-range`:

```css
/* CSS-only scroll-triggered fade + slide */
.reveal-element {
  animation: revealUp linear both;
  animation-timeline: view();
  animation-range: entry 0% entry 100%;
}

@keyframes revealUp {
  from {
    opacity: 0;
    transform: translateY(60px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Scroll-linked progress bar */
.progress-bar {
  animation: growWidth linear both;
  animation-timeline: scroll(root);
}

@keyframes growWidth {
  from { transform: scaleX(0); }
  to { transform: scaleX(1); }
}
```

**When to use native vs GSAP ScrollTrigger:**
| Feature | CSS Scroll Animations | GSAP ScrollTrigger |
|---|---|---|
| Simple reveal animations | ✅ Best choice | Overkill |
| Complex timelines | ❌ Limited | ✅ Best choice |
| Pinning sections | ❌ Not supported | ✅ Built-in |
| Scrub-linked animations | ⚠️ Basic only | ✅ Full control |
| Performance | ✅ Compositor thread | ⚠️ Main thread |
| Browser support (2026) | Chrome/Edge/Safari | Universal |
| Custom easing + callbacks | ❌ No | ✅ Full |

**Recommendation:** Use native CSS for simple reveal-on-scroll patterns (parallax, fade-in, slide-up). Use GSAP for anything involving pinning, complex timelines, scrubbing, or callbacks. They can coexist.

### SVG Mask Scroll Transitions
*Source: [Codrops - SVG Mask Scroll Transitions](https://tympanus.net/codrops/2026/03/11/) (Mar 11, 2026)*

Complex image reveals using GSAP + ScrollTrigger + animated SVG clip-paths:

```tsx
// SVG mask that morphs on scroll
const maskPath = useRef<SVGPathElement>(null);

useEffect(() => {
  gsap.to(maskPath.current, {
    attr: {
      d: "M0,0 L1440,0 L1440,900 L0,900 Z" // full reveal
    },
    ease: "power3.inOut",
    scrollTrigger: {
      trigger: ".reveal-section",
      start: "top center",
      end: "bottom center",
      scrub: 1,
    }
  });
}, []);

// In JSX
<svg viewBox="0 0 1440 900">
  <defs>
    <clipPath id="reveal-mask">
      <path ref={maskPath} d="M720,450 L720,450 L720,450 L720,450 Z" />
    </clipPath>
  </defs>
</svg>
<div style={{ clipPath: "url(#reveal-mask)" }}>
  {/* Content revealed by the morphing SVG path */}
</div>
```

**Advantage over `clip-path` CSS:** SVG paths can be any shape — circles, blobs, organic forms, text outlines — not just basic rectangles/circles/polygons.

---

## TSL Migration Guide: GLSL → TSL {#tsl-migration}

TSL (Three.js Shading Language) is the future of shader authoring in Three.js. It replaces GLSL strings with composable JavaScript functions that work with both WebGPU and WebGL2.

### Why Migrate

1. **No more GLSL strings** — type-safe, composable, debuggable
2. **Cross-renderer** — same shader code works on WebGPU and WebGL2
3. **Compute shaders** — only available through TSL/WebGPU
4. **Better DX** — IDE autocomplete, imports, tree-shaking

### Quick Translation Guide

| GLSL | TSL |
|---|---|
| `uniform float uTime` | `const uTime = uniform(float(0))` |
| `varying vec2 vUv` | `uv()` (built-in) |
| `texture2D(tex, uv)` | `texture(tex, uv())` |
| `mix(a, b, t)` | `a.mix(b, t)` or `mix(a, b, t)` |
| `smoothstep(e0, e1, x)` | `smoothstep(e0, e1, x)` |
| `gl_FragColor = vec4(...)` | `return vec4(...)` |
| Custom function | `tslFn(({ inputs }) => { ... })` |

### Example: Noise Color Flow (GLSL → TSL)

**Before (GLSL):**
```glsl
uniform float uTime;
varying vec2 vUv;

void main() {
  float n = snoise(vec3(vUv * 3.0, uTime * 0.2));
  vec3 color = mix(vec3(0.1, 0.0, 0.3), vec3(0.0, 0.3, 0.8), n);
  gl_FragColor = vec4(color, 1.0);
}
```

**After (TSL):**
```tsx
import { tslFn, uniform, uv, vec3, float, mx_noise_vec3 } from 'three/tsl';

const uTime = uniform(float(0));

const noiseFlow = tslFn(() => {
  const uvCoord = uv().mul(3.0);
  const n = mx_noise_vec3(vec3(uvCoord, uTime.mul(0.2)));
  const color1 = vec3(0.1, 0.0, 0.3);
  const color2 = vec3(0.0, 0.3, 0.8);
  return vec4(color1.mix(color2, n.x), float(1.0));
});
```

### When to Use TSL vs GLSL

- **New projects targeting modern browsers** → TSL
- **Existing GLSL shaders that work fine** → keep GLSL (Three.js still supports it)
- **Need compute shaders** → TSL (only option)
- **Need Shadertoy-style experimentation** → GLSL (more examples/resources available)
- **Production prototypes for 2026+** → TSL preferred

### Resources
- [Three.js TSL Documentation](https://threejs.org/docs/#api/en/nodes/core/Node)
- [Three.js TSL Examples](https://threejs.org/examples/?q=tsl)
- [Codrops Dual-Scene Fluid Tutorial](https://tympanus.net/codrops/2026/03/23/dual-scene-fluid-x-ray-reveal-effect/) — production TSL example

---

**Monitor these resources for cutting-edge techniques:**
- [Codrops](https://tympanus.net/codrops/) — monthly advanced tutorials
- [r/creativecoding](https://reddit.com/r/creativecoding) — community experiments
- [r/threejs](https://reddit.com/r/threejs) — Three.js specific techniques
- [Awwwards](https://awwwards.com/websites/three-js/) — award-winning WebGL sites
