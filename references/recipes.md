# Recipes

Drop-in code snippets for common creative web patterns. Each recipe is a self-contained component or utility you can copy directly into a React/Next.js project.

## How to Use

1. **Browse by need** — Each recipe has a description of what it does, its strengths, and where to use it
2. **Copy and adapt** — Recipes are starting points, not final code. Adjust timing, colors, physics values to match your aesthetic direction
3. **Combine recipes** — Most real prototypes use 3-5 recipes layered together (e.g. Smooth Scroll + Text Reveal + Grain Overlay + Magnetic Buttons)
4. **Install dependencies first** — Each recipe lists its required packages

---

## Table of Contents

1. [Smooth Scroll + Scroll-Linked Animations](#smooth-scroll)
2. [Text Reveal on Scroll](#text-reveal)
3. [Grain Overlay](#grain-overlay)
4. [Magnetic Button](#magnetic-button)
5. [Floating Particles Background](#particles)
6. [Gradient Mesh Background](#gradient-mesh)
7. [Custom Cursor](#custom-cursor)
8. [Image Parallax on Scroll](#parallax)
9. [Staggered Grid Entrance](#staggered-grid)
10. [Horizontal Scroll Section](#horizontal-scroll)
11. [Native View Transitions](#view-transitions)

---

## 1. Smooth Scroll + Scroll-Linked Animations {#smooth-scroll}

**What it does:** Replaces native browser scroll with buttery-smooth inertia scrolling and enables scroll-position-linked animations (elements that animate as you scroll, not just when they enter the viewport).

**Strengths:**
- Transforms the feel of an entire page instantly — the single biggest UX upgrade you can make
- Enables "scrub" animations where scroll position directly controls animation progress
- Creates a premium, app-like feel that separates you from standard websites
- Foundation layer that all other scroll-based recipes build on

**Use when:**
- Every editorial/storytelling page (this should be your default)
- Product showcases where scroll = exploration
- Any page with pinned sections or scroll-driven reveals
- Landing pages, campaign microsites, brand experiences

**Don't use when:**
- Data-heavy dashboards where users need to scan quickly
- Accessibility-critical pages (some users rely on native scroll behavior)
- Very long pages with primarily text content (blog posts)

**Dependencies:** `npm i gsap @studio-freight/lenis`

```tsx
"use client";
import { useEffect } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import Lenis from "@studio-freight/lenis";

gsap.registerPlugin(ScrollTrigger);

export function SmoothScrollProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    const lenis = new Lenis({ lerp: 0.1, smoothWheel: true });
    lenis.on("scroll", ScrollTrigger.update);
    gsap.ticker.add((time) => lenis.raf(time * 1000));
    gsap.ticker.lagSmoothing(0);
    return () => { lenis.destroy(); gsap.ticker.remove(lenis.raf); };
  }, []);
  return <>{children}</>;
}
```

**Tuning tips:**
- `lerp: 0.1` = very smooth/slow, `0.2` = snappier. Start at 0.1 and increase if it feels laggy.
- Wrap your entire app layout in this component.
- Pair with ScrollTrigger `scrub: 1` on child animations for scroll-linked effects.

---

## 2. Text Reveal on Scroll {#text-reveal}

**What it does:** Splits text into individual characters and animates them in with a staggered upward reveal when the element scrolls into view. Creates a "typewriter meets waterfall" effect.

**Strengths:**
- Makes headlines feel alive and intentional instead of just appearing
- The stagger creates natural reading rhythm — your eye follows the animation
- Extremely versatile — works for hero titles, section headers, pull quotes
- Low performance cost for high visual impact

**Use when:**
- Hero headlines (the first thing users see)
- Section transitions where you want to signal "new topic"
- Pull quotes in editorial layouts
- Any text that deserves a moment of attention

**Don't use when:**
- Body copy (too distracting for long reading)
- Navigation text or UI labels
- When the page already has a lot of competing motion

**Dependencies:** `npm i gsap` (uses ScrollTrigger)

```tsx
"use client";
import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

export function RevealText({ text, className }: { text: string; className?: string }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const chars = containerRef.current?.querySelectorAll(".char");
    if (!chars) return;
    gsap.fromTo(chars,
      { y: "100%", opacity: 0 },
      {
        y: "0%", opacity: 1,
        stagger: 0.03, duration: 0.8, ease: "power4.out",
        scrollTrigger: { trigger: containerRef.current, start: "top 80%" }
      }
    );
  }, []);

  return (
    <div ref={containerRef} className={className} style={{ overflow: "hidden" }}>
      {text.split("").map((char, i) => (
        <span key={i} className="char" style={{ display: "inline-block" }}>
          {char === " " ? "\u00A0" : char}
        </span>
      ))}
    </div>
  );
}
```

**Variations:**
- Split by word instead of character for a chunkier feel (`text.split(" ")`)
- Add `rotationX: -90` to the from-state for a 3D flip reveal
- Use `scrub: true` instead of `toggleActions` to tie the reveal to scroll position
- Animate `clipPath` instead of `y` for a mask-wipe reveal

---

## 3. Grain Overlay {#grain-overlay}

**What it does:** Adds a subtle film grain texture over the entire viewport using a CSS pseudo-element with an SVG noise filter. Zero JavaScript, zero images, zero performance cost.

**Strengths:**
- Instantly breaks the "digital sterility" of clean web design
- Adds warmth and analog texture that makes designs feel crafted
- Works on ANY aesthetic — just adjust opacity (0.02 for subtle, 0.08 for heavy)
- Completely free in terms of performance (GPU-composited, no repaints)

**Use when:**
- Almost always — this is a universal polish layer
- Editorial and magazine layouts (feels like print)
- Dark themes (grain becomes atmospheric, almost cinematic)
- Lo-fi, analog, or vintage aesthetics (crank opacity to 0.06-0.10)
- Photography-heavy pages (grain unifies digital and photographic textures)

**Don't use when:**
- Ultra-clean, clinical aesthetics where sterility is the point
- Data visualization where grain could interfere with readability
- When layered over already-textured backgrounds (double texture = muddy)

**Dependencies:** None (pure CSS)

```css
.grain::after {
  content: "";
  position: fixed;
  inset: 0;
  z-index: 9999;
  pointer-events: none;
  opacity: 0.04;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E");
}
```

**Tuning tips:**
- Apply the `.grain` class to your root layout element (`<body>` or top-level `<div>`)
- `opacity: 0.02-0.03` = barely there (clean designs), `0.04-0.06` = noticeable (editorial), `0.08+` = heavy (lo-fi/vintage)
- Change `baseFrequency` to adjust grain size: `0.5` = coarser, `1.2` = finer
- For animated grain, add a CSS animation that shifts `background-position` randomly

---

## 4. Magnetic Button {#magnetic-button}

**What it does:** Button that magnetically pulls toward the user's cursor when they hover near it, with spring physics that make it feel alive and responsive.

**Strengths:**
- Tiny code footprint for a big "wow" moment — people notice and play with it
- Spring physics feel organic and premium (not robotic linear motion)
- Creates a sense that the interface is responding to you personally
- Pairs perfectly with custom cursors for a cohesive interactive layer

**Use when:**
- Primary CTAs (Buy, Explore, Enter, Play)
- Navigation links on creative/brand pages
- Any button that should feel premium and interactive
- Portfolio and showcase navigation

**Don't use when:**
- Forms with many buttons close together (magnetic pull would conflict)
- Mobile layouts (no hover state)
- Utility buttons (save, cancel, close) where function > delight

**Dependencies:** `npm i framer-motion`

```tsx
"use client";
import { motion, useMotionValue, useSpring } from "framer-motion";
import { useRef } from "react";

export function MagneticButton({ children, className }: { children: React.ReactNode; className?: string }) {
  const ref = useRef<HTMLButtonElement>(null);
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const springX = useSpring(x, { stiffness: 200, damping: 20 });
  const springY = useSpring(y, { stiffness: 200, damping: 20 });

  return (
    <motion.button
      ref={ref}
      className={className}
      style={{ x: springX, y: springY }}
      onMouseMove={(e) => {
        const rect = ref.current!.getBoundingClientRect();
        x.set((e.clientX - rect.left - rect.width / 2) * 0.3);
        y.set((e.clientY - rect.top - rect.height / 2) * 0.3);
      }}
      onMouseLeave={() => { x.set(0); y.set(0); }}
    >
      {children}
    </motion.button>
  );
}
```

**Tuning tips:**
- `0.3` multiplier controls pull strength — `0.2` = subtle, `0.5` = aggressive
- `stiffness: 200, damping: 20` = bouncy. Try `stiffness: 300, damping: 30` for snappier
- Add `scale: 1.05` on hover for an extra "lift" effect
- Combine with a hover background-color slide (see enhancement-recipes.md #4)

---

## 5. Floating Particles Background {#particles}

**What it does:** Renders a full-screen 3D particle field using React Three Fiber that slowly rotates and drifts, creating an ambient living background.

**Strengths:**
- Turns any static page into something that feels alive and dimensional
- 3D particles create natural depth that flat CSS backgrounds can't match
- Hypnotic and calming — great for setting a premium or futuristic tone
- Surprisingly performant for the visual impact (GPU-rendered points)

**Use when:**
- Hero sections that need depth without a specific image
- Loading or transition states (gives users something beautiful to watch)
- Dark-themed pages (particles pop against dark backgrounds)
- Tech/futuristic aesthetics, data visualization contexts
- Abstract brand pages where you want ambiance over content

**Don't use when:**
- Content-heavy pages where the background would compete with text
- Light themes (white particles on white = invisible, dark particles = distracting)
- Mobile-first designs where 3D rendering drains battery
- Pages that need fast initial load (Three.js is ~600KB)

**Dependencies:** `npm i @react-three/fiber @react-three/drei three`

```tsx
"use client";
import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

function Particles({ count = 500 }) {
  const mesh = useRef<THREE.Points>(null);
  const positions = useMemo(() => {
    const pos = new Float32Array(count * 3);
    for (let i = 0; i < count * 3; i++) pos[i] = (Math.random() - 0.5) * 10;
    return pos;
  }, [count]);

  useFrame(({ clock }) => {
    if (!mesh.current) return;
    mesh.current.rotation.y = clock.elapsedTime * 0.05;
    mesh.current.rotation.x = Math.sin(clock.elapsedTime * 0.03) * 0.2;
  });

  return (
    <points ref={mesh}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial size={0.02} color="#ffffff" transparent opacity={0.6} sizeAttenuation />
    </points>
  );
}

export function ParticleBackground() {
  return (
    <div className="fixed inset-0 -z-10">
      <Canvas camera={{ position: [0, 0, 5], fov: 60 }}>
        <Particles />
      </Canvas>
    </div>
  );
}
```

**Tuning tips:**
- `count: 200` for subtle, `500` for medium, `1000+` for dense fields
- Add `<fog attach="fog" args={['#000', 3, 10]} />` inside Canvas for depth fade
- Use `dynamic import` with `ssr: false` to avoid hydration issues and reduce initial bundle
- Add mouse reactivity: pass cursor position to `useFrame` and offset rotation

---

## 6. Gradient Mesh Background {#gradient-mesh}

**What it does:** Creates a living, slowly-moving gradient background using layered radial gradients animated with GSAP. Feels like lava lamp meets northern lights.

**Strengths:**
- Rich, organic color without any images — fully code-driven
- Slow movement creates ambiance without being distracting
- Way more interesting than flat solid backgrounds
- Tiny performance footprint (CSS + transform animations)

**Use when:**
- Any page that currently has a flat color background (instant upgrade)
- Dark themes where you want atmospheric color
- Hero sections as a base layer under text or 3D elements
- Brand pages where the palette should feel alive

**Don't use when:**
- Over photographic backgrounds (competing textures)
- When you need precise color control at specific viewport positions
- Extremely minimal/brutalist aesthetics where even gradients feel excessive

**Dependencies:** `npm i gsap`

```tsx
"use client";
import { useEffect, useRef } from "react";
import gsap from "gsap";

export function GradientMesh({ colors = ["rgba(255,100,50,0.15)", "rgba(50,100,255,0.1)", "rgba(200,50,255,0.1)"] }) {
  const blobRefs = [useRef<HTMLDivElement>(null), useRef<HTMLDivElement>(null), useRef<HTMLDivElement>(null)];

  useEffect(() => {
    blobRefs.forEach((ref, i) => {
      if (!ref.current) return;
      gsap.to(ref.current, {
        x: `+=${60 + i * 40}`, y: `+=${30 + i * 20}`,
        duration: 15 + i * 5, repeat: -1, yoyo: true, ease: "sine.inOut",
      });
    });
  }, []);

  return (
    <div className="fixed inset-0 -z-10 overflow-hidden" style={{ background: "#0a0a0a" }}>
      {colors.map((color, i) => (
        <div key={i} ref={blobRefs[i]} className="absolute rounded-full"
          style={{
            width: "60vw", height: "60vw",
            background: `radial-gradient(circle, ${color} 0%, transparent 70%)`,
            left: `${i * 30}%`, top: `${i * 25}%`,
            filter: "blur(80px)",
          }}
        />
      ))}
    </div>
  );
}
```

**Tuning tips:**
- Change color arrays to match your palette — this is the fastest way to set a page's mood
- Increase blur (`120px`+) for more diffuse, atmospheric color
- Add a 4th blob for richer blending
- Layer grain overlay (Recipe #3) on top for extra texture

---

## 7. Custom Cursor {#custom-cursor}

**What it does:** Replaces the default cursor with a small, spring-animated circle that follows mouse movement with slight lag, creating a fluid, premium feel. Uses `mix-blend-difference` to stay visible on any background.

**Strengths:**
- Transforms the entire browsing experience — everything feels more interactive
- Spring physics create personality (the cursor has "weight")
- `mix-blend-difference` is a clever trick that inverts color automatically
- Sets the tone before the user even interacts with content

**Use when:**
- Portfolio and showcase sites
- Brand campaigns and microsites
- Any page going for Awwwards-level polish
- Dark-themed creative pages

**Don't use when:**
- Mobile (no cursor)
- Accessibility-focused pages (custom cursors can confuse screen readers)
- Content-heavy editorial where cursor personality would distract
- E-commerce pages where users need precise click targets

**Dependencies:** `npm i framer-motion`

```tsx
"use client";
import { motion, useMotionValue, useSpring } from "framer-motion";
import { useEffect } from "react";

export function CustomCursor() {
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const smoothX = useSpring(x, { stiffness: 300, damping: 30 });
  const smoothY = useSpring(y, { stiffness: 300, damping: 30 });

  useEffect(() => {
    const handler = (e: MouseEvent) => { x.set(e.clientX); y.set(e.clientY); };
    window.addEventListener("mousemove", handler);
    document.body.style.cursor = "none";
    return () => { window.removeEventListener("mousemove", handler); document.body.style.cursor = ""; };
  }, []);

  return (
    <motion.div
      className="fixed top-0 left-0 w-5 h-5 rounded-full border-2 border-white pointer-events-none z-[9999] mix-blend-difference"
      style={{ x: smoothX, y: smoothY, translateX: "-50%", translateY: "-50%" }}
    />
  );
}
```

**Tuning tips:**
- Add a second, larger circle with lower stiffness for a "trailing" effect
- Scale up the cursor when hovering over interactive elements (listen for `mouseenter` on buttons/links)
- Change to a dot cursor (`w-2 h-2 bg-white`) for minimal aesthetics
- Add text inside the cursor on hover (e.g. "View" over gallery items)

---

## 8. Image Parallax on Scroll {#parallax}

**What it does:** Makes images move at a different speed than surrounding content as the user scrolls, creating a natural sense of depth like looking through a window.

**Strengths:**
- One of the oldest web tricks and still one of the most effective
- Creates depth with zero 3D libraries — just CSS transforms
- Works beautifully with full-bleed photography
- Low performance cost (single transform per element)

**Use when:**
- Editorial layouts with large photos between text sections
- Hero images that should feel immersive
- Product showcase pages
- Any section where you want visual depth

**Don't use when:**
- Pages with many small images (parallax on everything = chaos)
- Fast-scrolling data pages
- When images have text overlays that need to stay aligned

**Dependencies:** `npm i gsap` (uses ScrollTrigger)

```tsx
"use client";
import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

export function ParallaxImage({ src, alt, speed = -30 }: { src: string; alt: string; speed?: number }) {
  const imgRef = useRef<HTMLImageElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!imgRef.current || !containerRef.current) return;
    gsap.to(imgRef.current, {
      yPercent: speed,
      ease: "none",
      scrollTrigger: {
        trigger: containerRef.current,
        start: "top bottom",
        end: "bottom top",
        scrub: true,
      },
    });
  }, [speed]);

  return (
    <div ref={containerRef} className="overflow-hidden">
      <img ref={imgRef} src={src} alt={alt} className="w-full h-[120%] object-cover" />
    </div>
  );
}
```

**Tuning tips:**
- `speed: -30` = subtle, `-50` = noticeable, `-80` = dramatic
- The image needs to be taller than its container (hence `h-[120%]`) to avoid gaps
- Positive `speed` values make the image scroll faster than content (reverse parallax)
- Layer multiple parallax elements at different speeds for a multi-plane effect

---

## 9. Staggered Grid Entrance {#staggered-grid}

**What it does:** Grid items fade and slide in one by one with a cascading delay when they scroll into view, creating a "dealing cards" reveal effect.

**Strengths:**
- Turns a static grid into a choreographed reveal moment
- The stagger creates visual rhythm and guides the eye across the layout
- Works with any card/grid content (products, articles, team members, portfolio)
- Simple to implement but looks sophisticated

**Use when:**
- Product grids, article grids, portfolio galleries
- Team/about pages
- Feature lists and comparison layouts
- Any grid-based content that appears below the fold

**Don't use when:**
- Above-the-fold content (users shouldn't wait for key content to appear)
- Grids that update dynamically (filters, search results) — animation on every update is annoying
- When there are 50+ items (stagger across that many = too slow)

**Dependencies:** `npm i gsap` (uses ScrollTrigger)

```tsx
"use client";
import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

export function StaggerGrid({ children, className }: { children: React.ReactNode; className?: string }) {
  const gridRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!gridRef.current) return;
    const items = gridRef.current.children;
    gsap.fromTo(items,
      { y: 40, opacity: 0 },
      {
        y: 0, opacity: 1,
        duration: 0.6, stagger: 0.08, ease: "power3.out",
        scrollTrigger: { trigger: gridRef.current, start: "top 85%" },
      }
    );
  }, []);

  return <div ref={gridRef} className={className}>{children}</div>;
}
```

**Tuning tips:**
- `stagger: 0.08` = fast cascade, `0.15` = slower/more dramatic
- Add `scale: 0.95` to the from-state for a subtle zoom-in effect
- For a diagonal cascade, use `stagger: { each: 0.08, grid: [rows, cols], from: "start" }`
- Pair with Framer Motion's `layout` prop if the grid is filterable

---

## 10. Horizontal Scroll Section {#horizontal-scroll}

**What it does:** Pins a section to the viewport and converts vertical scroll into horizontal movement, allowing a gallery or content strip to scroll sideways while the user scrolls down.

**Strengths:**
- Breaks the vertical monotony — users notice and engage with horizontal sections
- Perfect for showcasing a series of related items (portfolio, timeline, product lineup)
- Creates a "scene change" that signals different content structure
- Scroll-hijacking done right (pin + scrub, not broken wheel events)

**Use when:**
- Portfolio/gallery showcases
- Product lineups and collections
- Timelines and chronological content
- Feature tours ("scroll to explore")

**Don't use when:**
- Mobile (horizontal scroll via vertical scroll is confusing on touch)
- More than ~8-10 items (too long = user loses patience)
- When content needs to be scannable (horizontal hides everything after the first panel)

**Dependencies:** `npm i gsap` (uses ScrollTrigger)

```tsx
"use client";
import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

export function HorizontalScroll({ children, className }: { children: React.ReactNode; className?: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || !trackRef.current) return;
    const totalWidth = trackRef.current.scrollWidth - window.innerWidth;

    gsap.to(trackRef.current, {
      x: -totalWidth,
      ease: "none",
      scrollTrigger: {
        trigger: containerRef.current,
        start: "top top",
        end: `+=${totalWidth}`,
        pin: true,
        scrub: 1,
      },
    });
  }, []);

  return (
    <div ref={containerRef}>
      <div ref={trackRef} className={`flex gap-8 ${className || ""}`}>
        {children}
      </div>
    </div>
  );
}
```

**Tuning tips:**
- `scrub: 1` = 1 second lag behind scroll (smooth), `scrub: 0.5` = snappier
- Add velocity-based skew: items lean in the scroll direction for a physics feel
- Include a progress indicator (dots or a bar) so users know where they are
- Consider disabling on mobile and using a native horizontal scroll instead

---

## 11. Native View Transitions {#view-transitions}

**What it does:** Uses the native CSS View Transitions API to create smooth, native-feeling transitions between DOM states. The browser automatically captures "before" and "after" snapshots and morphs between them.

**Strengths:**
- **Zero dependencies** — pure browser API, no animation libraries needed
- **Performance** — runs on the compositor thread, hardware-accelerated
- **Automatic intelligent interpolation** — browser figures out how elements should morph
- **Accessible** — respects `prefers-reduced-motion` automatically
- **Progressively enhanced** — gracefully falls back to instant state changes
- **Shared element transitions** — elements can seamlessly morph between screens

**Use when:**
- Navigation between pages/routes (especially single-page app route changes)
- Modal/dialog open/close with shared elements
- Grid-to-detail page transitions (like photo galleries → lightbox)
- Theme switching, layout mode toggles
- Quiz/form step transitions where UI elements morph between states
- Any state change where you can identify "before" and "after" elements

**Don't use when:**
- Complex continuous animations (stick with GSAP/Framer Motion)
- IE or older browser support is critical (progressive enhancement handles this)
- Animations need precise timing control or complex choreography

**Dependencies:** None (native browser API)

```tsx
"use client";
import { useEffect, useState } from "react";

// Browser support check
const supportsViewTransitions = typeof window !== "undefined" && "startViewTransition" in document;

export function ViewTransitionDemo() {
  const [currentView, setCurrentView] = useState<"grid" | "detail">("grid");
  const [selectedItem, setSelectedItem] = useState<number | null>(null);

  const handleTransition = (newView: "grid" | "detail", itemId?: number) => {
    if (!supportsViewTransitions) {
      // Fallback: instant state change
      setCurrentView(newView);
      if (itemId !== undefined) setSelectedItem(itemId);
      return;
    }

    // Native view transition
    document.startViewTransition(() => {
      setCurrentView(newView);
      if (itemId !== undefined) setSelectedItem(itemId);
    });
  };

  if (currentView === "detail" && selectedItem !== null) {
    return (
      <DetailView 
        item={selectedItem} 
        onBack={() => handleTransition("grid")}
      />
    );
  }

  return (
    <GridView 
      onItemClick={(itemId) => handleTransition("detail", itemId)}
    />
  );
}

function GridView({ onItemClick }: { onItemClick: (id: number) => void }) {
  const items = [1, 2, 3, 4, 5, 6];

  return (
    <div className="grid grid-cols-3 gap-4 p-8">
      {items.map((item) => (
        <div 
          key={item}
          onClick={() => onItemClick(item)}
          // 🔥 This is the magic: view-transition-name creates shared element
          style={{ viewTransitionName: `item-${item}` }}
          className="aspect-square bg-gradient-to-br from-purple-400 to-pink-600 
                     rounded-xl cursor-pointer hover:scale-105 transition-transform
                     flex items-center justify-center text-white font-bold text-xl"
        >
          {item}
        </div>
      ))}
    </div>
  );
}

function DetailView({ item, onBack }: { item: number; onBack: () => void }) {
  return (
    <div className="p-8 min-h-screen flex flex-col">
      <button 
        onClick={onBack}
        className="mb-8 px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300"
      >
        ← Back to Grid
      </button>
      
      <div 
        // Same view-transition-name = shared element transition
        style={{ viewTransitionName: `item-${item}` }}
        className="w-full max-w-md mx-auto aspect-square 
                   bg-gradient-to-br from-purple-400 to-pink-600 rounded-xl
                   flex items-center justify-center text-white font-bold text-6xl"
      >
        {item}
      </div>
      
      <div className="mt-8 text-center">
        <h1 className="text-3xl font-bold mb-4">Item {item}</h1>
        <p className="text-gray-600">
          This element smoothly transitioned from the grid using native View Transitions.
          Notice how the element morphed its size and position automatically.
        </p>
      </div>
    </div>
  );
}
```

**Advanced: Custom transition animations with CSS**

```css
/* Custom timing and easing */
::view-transition-old(item-*),
::view-transition-new(item-*) {
  animation-duration: 0.5s;
  animation-timing-function: cubic-bezier(0.4, 0.0, 0.2, 1);
}

/* Custom animation for specific named transitions */
::view-transition-old(modal) {
  animation: fade-out 0.3s ease-out;
}

::view-transition-new(modal) {
  animation: slide-up 0.3s ease-out;
}

@keyframes fade-out {
  from { opacity: 1; }
  to { opacity: 0; }
}

@keyframes slide-up {
  from { 
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Disable transitions for users who prefer reduced motion */
@media (prefers-reduced-motion: reduce) {
  ::view-transition-group(*),
  ::view-transition-old(*),
  ::view-transition-new(*) {
    animation-duration: 0.01ms !important;
  }
}
```

**Real-world use cases:**
- **Photo gallery**: Grid thumbnail → full-size detail with perfect morphing
- **Product catalog**: List view → product detail with shared product image
- **Navigation**: Button → full-screen menu with morphing shape
- **Quiz steps**: Question morphs into next question, progress bar animates
- **Theme toggle**: Elements smoothly recolor and reposition

**Browser support:** Chrome 111+, Edge 111+, Safari 18+, Firefox (partial). Always include the `supportsViewTransitions` check for progressive enhancement.

**Tuning tips:**
- Use meaningful `view-transition-name` values (`product-123`, `nav-menu`) not generic ones
- Elements with same `view-transition-name` will morph between states — this is the key
- Keep transitions under 500ms for snappy feel
- Test with `prefers-reduced-motion` users
- Combine with React Router or Next.js navigation for seamless page transitions
