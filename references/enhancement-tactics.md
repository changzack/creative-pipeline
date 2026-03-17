# Enhancement Tactics

Diagnose what's flat about a prototype and fix it. Each tactic starts with a **symptom** (what feels wrong) and walks through the transformation steps. Apply one or combine several.

For drop-in code components, see `recipes.md`. This file focuses on *strategy and process* — when to apply what and in what order.

---

## Table of Contents

1. [Add Scroll-Driven Life](#scroll-life)
2. [Elevate Typography](#typography)
3. [Add Depth and Atmosphere](#atmosphere)
4. [Make Interactions Delightful](#interactions)
5. [Add a 3D Hero Element](#3d-hero)
6. [Cinematic Page Transitions](#page-transitions)
7. [Dynamic Color and Theming](#dynamic-color)
8. [Custom Cursor Experience](#custom-cursor)
9. [Loading Experience](#loading)
10. [Sound Design Layer](#sound)

---

## 1. Add Scroll-Driven Life {#scroll-life}

**Symptom**: Content just... sits there. Scrolling is just "more stuff."

**Steps:**

1. **Foundation**: Wrap app in Smooth Scroll provider → `recipes.md#smooth-scroll`
2. **Entrance animations**: Add scroll-triggered reveals to every content section using this reusable hook:

```tsx
function useScrollReveal(ref: React.RefObject<HTMLElement>, options = {}) {
  useEffect(() => {
    if (!ref.current) return;
    gsap.fromTo(ref.current,
      { y: 60, opacity: 0 },
      {
        y: 0, opacity: 1, duration: 1, ease: "power3.out",
        scrollTrigger: {
          trigger: ref.current, start: "top 85%",
          toggleActions: "play none none none", ...options,
        }
      }
    );
  }, []);
}
```

3. **Pin at least one section**: Create a scroll-pinned feature reveal where content swaps while the viewport stays locked:

```tsx
useEffect(() => {
  gsap.timeline({
    scrollTrigger: {
      trigger: sectionRef.current,
      start: "top top", end: "+=200%",
      pin: true, scrub: 1,
    }
  })
  .to(".feature-1", { opacity: 1, y: 0 })
  .to(".feature-1", { opacity: 0, y: -20 })
  .to(".feature-2", { opacity: 1, y: 0 })
  .to(".feature-2", { opacity: 0, y: -20 })
  .to(".feature-3", { opacity: 1, y: 0 });
}, []);
```

4. **Add parallax**: Apply to at least one background image → `recipes.md#parallax`

**Result**: Page now has rhythm — sections reveal, pin, parallax, and flow instead of just stacking.

---

## 2. Elevate Typography {#typography}

**Symptom**: Text is readable but forgettable. No typographic personality.

**Steps:**

1. **Scale contrast**: Headlines should be 3-5x body size minimum:

```css
.hero-title {
  font-size: clamp(3rem, 10vw, 12rem);
  font-weight: 900;
  line-height: 0.9;
  letter-spacing: -0.04em;
}
```

2. **Animate text reveals**: Use the Text Reveal recipe → `recipes.md#text-reveal`

3. **Text masking** for hero moments (image/video visible through text):

```css
.text-mask {
  background: url('/hero-video-or-image.jpg') center/cover;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
```

4. **Variable font animation** — weight shifts on hover for interactive feel:

```css
@font-face {
  font-family: 'Display';
  src: url('/fonts/variable.woff2') format('woff2-variations');
  font-weight: 100 900;
}
.animate-weight {
  transition: font-variation-settings 0.4s ease;
  font-variation-settings: 'wght' 400;
}
.animate-weight:hover {
  font-variation-settings: 'wght' 900;
}
```

5. **Mix typefaces**: Display/serif for headlines, mono for labels/data, sans-serif for body. Contrast creates hierarchy. Refer to Anti-Slop rules in SKILL.md for what NOT to pick.

**Result**: Typography becomes the design itself, not just content delivery.

---

## 3. Add Depth and Atmosphere {#atmosphere}

**Symptom**: Everything feels flat and clinical. Digital sterility.

**Steps:**

1. **Grain overlay**: → `recipes.md#grain-overlay` — instant warmth, apply first
2. **Gradient mesh**: → `recipes.md#gradient-mesh` — replace flat color backgrounds
3. **Blur depth layers**: Large blurred color circles at different positions create atmospheric depth:

```css
.bg-blur-layer {
  position: absolute;
  width: 400px; height: 400px;
  border-radius: 50%;
  background: rgba(100, 50, 255, 0.3);
  filter: blur(120px);
  animation: float 20s ease-in-out infinite alternate;
}
```

4. **Blend modes**: Layer elements with `mix-blend-mode` for rich color interaction:

```css
.blend-overlay { mix-blend-mode: overlay; }
.blend-multiply { mix-blend-mode: multiply; }
.blend-screen { mix-blend-mode: screen; }
```

**Result**: The page has air, warmth, and dimensionality. Feels crafted, not generated.

---

## 4. Make Interactions Delightful {#interactions}

**Symptom**: Hover = color change. Click = instant state change. Everything is binary.

**Steps:**

1. **Magnetic buttons**: → `recipes.md#magnetic-button`
2. **Multi-layered hover states** — background slides in, text inverts, arrow enters:

```tsx
<motion.div whileHover="hover" className="relative overflow-hidden">
  <motion.div className="absolute inset-0 bg-white"
    variants={{ hover: { y: "0%" } }}
    initial={{ y: "100%" }}
    transition={{ duration: 0.4, ease: [0.33, 1, 0.68, 1] }} />
  <motion.span className="relative z-10"
    variants={{ hover: { color: "#000" } }}
    transition={{ duration: 0.3 }}>
    Explore
  </motion.span>
  <motion.span
    variants={{ hover: { x: 0, opacity: 1 } }}
    initial={{ x: -20, opacity: 0 }}
    transition={{ duration: 0.3, delay: 0.1 }}>
    →
  </motion.span>
</motion.div>
```

3. **Spring physics on draggable elements**:

```tsx
<motion.div drag dragElastic={0.2}
  dragConstraints={{ left: 0, right: 0, top: 0, bottom: 0 }}
  whileDrag={{ scale: 1.05, cursor: "grabbing" }} />
```

4. **Image hover enhancement** (CSS-only, no library needed):

```css
.image-hover { transition: filter 0.5s ease; }
.image-hover:hover { filter: saturate(1.2) contrast(1.1) brightness(1.05); }
```

**Result**: Every interaction feels responsive and layered. Users play with the interface.

---

## 5. Add a 3D Hero Element {#3d-hero}

**Symptom**: Hero section is a flat image or gradient with text on it.

**Steps:**

1. **Choose your 3D approach** (easiest to hardest):
   - Floating particles → `recipes.md#particles` (easiest, always works)
   - Abstract shapes — rotating icosahedrons, toruses with wireframe + glass material
   - Noise-deformed sphere — organic, living feel (below)

2. **Noise-deformed sphere** for an organic hero:

```tsx
function NoiseSphere() {
  const mesh = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (!mesh.current) return;
    const positions = mesh.current.geometry.attributes.position;
    const time = clock.elapsedTime;
    for (let i = 0; i < positions.count; i++) {
      const p = new THREE.Vector3().fromBufferAttribute(positions, i).normalize();
      const noise = Math.sin(p.x * 3 + time) * Math.sin(p.y * 3 + time) * 0.15;
      positions.setXYZ(i, p.x * (1 + noise), p.y * (1 + noise), p.z * (1 + noise));
    }
    positions.needsUpdate = true;
  });
  return (
    <mesh ref={mesh}>
      <icosahedronGeometry args={[1.5, 64]} />
      <meshStandardMaterial color="#4444ff" wireframe metalness={0.8} roughness={0.2} />
    </mesh>
  );
}
```

3. **Connect to scroll** so the 3D scene isn't just ambient — it responds to the user:

```tsx
useFrame(() => {
  if (!mesh.current) return;
  mesh.current.rotation.y = scrollProgress.current * Math.PI * 2;
});
```

**Result**: Hero goes from flat poster to dimensional, living scene. First impression transforms.

---

## 6. Cinematic Page Transitions {#page-transitions}

**Symptom**: Page changes are instant. No continuity between views.

**Fix** (Next.js App Router — use `template.tsx`):

```tsx
"use client";
import { AnimatePresence, motion } from "framer-motion";
import { usePathname } from "next/navigation";

export default function Template({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <AnimatePresence mode="wait">
      <motion.div key={pathname}
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -20 }}
        transition={{ duration: 0.5, ease: [0.33, 1, 0.68, 1] }}>
        {children}
      </motion.div>
    </AnimatePresence>
  );
}
```

**For more dramatic transitions**: `clip-path` wipe reveals, color wash overlays, or shared element transitions using GSAP Flip (see `advanced-techniques.md#advanced-gsap`).

**Result**: Navigation feels like scene changes in a film, not tab switches.

---

## 7. Dynamic Color and Theming {#dynamic-color}

**Symptom**: One color palette, no variation or energy.

**Fix**: CSS custom properties that shift per-section as user scrolls:

```tsx
const sections = [
  { bg: "#0a0a0a", accent: "#ff4444", text: "#ffffff" },
  { bg: "#f5f0eb", accent: "#2244ff", text: "#111111" },
  { bg: "#1a0a2e", accent: "#ff44ff", text: "#ffffff" },
];

sections.forEach((s, i) => {
  ScrollTrigger.create({
    trigger: `.section-${i}`,
    start: "top center",
    onEnter: () => {
      gsap.to("html", {
        "--bg": s.bg, "--accent": s.accent, "--text": s.text,
        duration: 0.8, ease: "power2.inOut",
      });
    },
    onEnterBack: () => { /* same values */ }
  });
});
```

**Result**: The page evolves as you scroll — each section has its own mood.

---

## 8. Custom Cursor Experience {#custom-cursor}

**Symptom**: Default cursor. Missed opportunity for personality.

**Fix**: → `recipes.md#custom-cursor` for the base component, then extend:
- Scale up when hovering interactive elements
- Add text inside cursor ("View", "Drag", "Play") contextually
- Add a trailing second circle with lower stiffness

**Result**: The cursor itself becomes part of the design language.

---

## 9. Loading Experience {#loading}

**Symptom**: Content pops in. No entry moment.

**Fix**: Branded loading screen with exit animation:

```tsx
export function Loader({ onComplete }: { onComplete: () => void }) {
  useEffect(() => {
    const tl = gsap.timeline({ onComplete });
    tl.to(".loader-progress", { scaleX: 1, duration: 1.5, ease: "power2.inOut" })
      .to(".loader-text", { y: -40, opacity: 0, duration: 0.4 })
      .to(".loader", { yPercent: -100, duration: 0.8, ease: "power4.inOut" });
  }, []);

  return (
    <div className="loader fixed inset-0 z-50 bg-black flex items-center justify-center">
      <div className="loader-text text-4xl font-bold text-white">COMPLEX</div>
      <div className="absolute bottom-0 left-0 right-0 h-1 bg-white/20">
        <div className="loader-progress h-full bg-white origin-left scale-x-0" />
      </div>
    </div>
  );
}
```

**Result**: The experience has a beginning — an opening act that sets the tone.

---

## 10. Sound Design Layer {#sound}

**Symptom**: Completely silent experience. Missed sensory dimension.

**Fix** (always user-initiated, never autoplay):

```tsx
import { Howl } from "howler";

const sounds = {
  hover: new Howl({ src: ["/sounds/hover.mp3"], volume: 0.1 }),
  click: new Howl({ src: ["/sounds/click.mp3"], volume: 0.15 }),
  transition: new Howl({ src: ["/sounds/whoosh.mp3"], volume: 0.2 }),
  ambient: new Howl({ src: ["/sounds/ambient.mp3"], volume: 0.05, loop: true }),
};
```

**Resources**: freesound.org, mixkit.co, sonniss.com GDC packs. For AI-generated sounds, see SKILL.md → Beyond the Browser (ElevenLabs, Bark).

**Result**: The experience has a sensory dimension most web pages completely ignore.
