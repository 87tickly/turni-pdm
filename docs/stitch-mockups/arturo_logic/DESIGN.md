# Design System Strategy: ARTURO·

## 1. Overview & Creative North Star
**Creative North Star: "The Kinetic Conductor"**

Railway management is an exercise in extreme precision, fluid motion, and absolute clarity. The design system for ARTURO· moves away from the "generic SaaS" look of heavy borders and boxy containers. Instead, it adopts an **Editorial Precision** aesthetic. Think of the UI as a digital timetable or a high-end architectural blueprint: high data density that breathes through intentional white space, sophisticated tonal layering, and a signature typographic rhythm.

We achieve a "premium" feel by prioritizing **Atmospheric Depth** over structural lines. By utilizing the "Kinetic Dot" (#22C55E) as a singular, vibrant anchor against a sophisticated palette of Arturo Blue and cool neutrals, we create a tool that feels less like a spreadsheet and more like a professional cockpit.

---

## 2. Color & Surface Philosophy
The palette is built on the interaction between `primary` (#0062CC) and a sophisticated hierarchy of grayscale neutrals.

### The "No-Line" Rule
To achieve a high-end editorial feel, **1px solid borders are strictly prohibited for sectioning.** 
Layout boundaries must be defined through:
1.  **Background Shifts:** Transitioning from `surface` (#FAF8FF) to `surface-container-low` (#F2F3FF).
2.  **Tonal Transitions:** A `surface-container-highest` panel sitting on a `surface-container-low` background.

### Surface Hierarchy & Nesting
Treat the UI as a series of nested physical layers. 
- **Base Layer:** `surface` (#FAF8FF) for the main application background.
- **Mid Layer:** `surface-container-low` (#F2F3FF) for secondary navigation or content wells.
- **Top Layer:** `surface-container-lowest` (#FFFFFF) for primary cards and data tables. 
This "negative nesting" (placing a white card on a slightly darker base) creates a soft, natural lift without the clutter of shadows.

### The "Glass & Gradient" Rule
For floating elements (modals, tooltips, or flyouts), use **Glassmorphism**:
- **Background:** `surface` at 80% opacity.
- **Effect:** `backdrop-blur: 12px`.
- **Signature Polish:** Primary CTAs should use a subtle linear gradient from `primary` (#004B9F) to `primary-container` (#0062CC) at a 135° angle to add "soul" and depth.

---

## 3. Typography: The Metric of Motion
The typography system balances the technical nature of 'Exo 2' with the functional clarity of 'Inter'.

- **Display & Headlines:** Use `Exo 2` (Weight 600-700). The slight technical slant of Exo 2 evokes the speed and geometry of railway tracks.
- **The Monospace Mandate:** All times (HH:MM), train numbers (e.g., *Treno 9632*), and numeric identifiers must use a Monospace font-variant-numeric (or a dedicated mono font). This ensures columns of numbers align perfectly for rapid scanning.
- **Body & Labels:** Use `Inter` for maximum legibility at small sizes. 
    - **Standard Text:** 13px / 1.5 leading.
    - **Utility Labels:** 11px / 1.2 leading, Uppercase with 0.05em letter spacing for a "technical" feel.

---

## 4. Elevation & Depth
Elevation is communicated through **Tonal Layering** rather than traditional drop shadows.

- **The Layering Principle:** Depth is "stacked." Place `surface-container-lowest` cards on `surface-container-low` sections to create a soft, natural lift.
- **Ambient Shadows:** Only use shadows for "Floating" elements (Modals, Context Menus).
    - **Token:** `rgba(15, 23, 42, 0.04)` with a 12px blur and 4px Y-offset.
    - **Coloring:** Shadows must be tinted with the `on-surface` color to avoid a "dirty" gray appearance.
- **The "Ghost Border" Fallback:** If a divider is mandatory for accessibility, use the `outline-variant` token at **15% opacity**. Never use 100% opaque lines.

---

## 5. Components

### Navigation Sidebar
- **Width:** 224px. 
- **Styling:** `surface` background with a `ghost border` (outline-variant 15%) on the right. 
- **Active State:** `primary` at 8% opacity background with a 3px vertical "Kinetic Dot" (#22C55E) indicator on the left edge.

### Buttons & Inputs
- **Height:** Standard 32px; Large 36px.
- **Radius:** `md` (6px) for a professional, sharp look.
- **Primary Button:** Gradient fill (Primary to Primary-Container), white text.
- **Inputs:** `surface-container-lowest` background with a `ghost border`. On focus, the border transitions to Arturo Blue 40% opacity with a 2px outer glow.

### Data Chips (Railway Specific)
- **Status Chips:** (e.g., *Turno PdC*, *Giro Materiale*)
- **Style:** Pill-shaped, low-saturation backgrounds (e.g., `success-container` at 20% opacity) with high-contrast text.
- **Periodicity Indicators:** (LMXGV, SD, etc.) Use `label-sm` (11px) with `monospace` numbers. Use a `surface-variant` background for inactive days and `primary` for active days.

### Cards & Lists
- **Prohibition:** No divider lines.
- **Separation:** Use `8px` or `16px` vertical white space or a background shift to `surface-container-low` on hover (`Card Hover: #F8FAFC`).
- **Icons:** Lucide-style, 14px, 1.8px stroke. Icons should use `text-muted` (#64748B) unless active.

---

## 6. Do's and Don'ts

### Do
- **DO** use the Monospace font for all time-based data (*Turno PdC* timing).
- **DO** use the Arturo Dot (#22C55E) as a status indicator for "Active" or "On-Time" states.
- **DO** maintain high data density. Railway operators need information at a glance; don't hide data behind unnecessary padding.

### Don't
- **DON'T** use 1px solid #E2E8F0 borders to separate list items. Use white space.
- **DON'T** use standard "Web Blue" colors. Stick strictly to Arturo Blue (#0062CC).
- **DON'T** use large border-radii. Keep it between 6px and 12px to maintain a professional, tool-like feel.
- **DON'T** translate technical terms like *CVp/CVa* or *ACCp/ACCa*. These are industry standards; the design must respect the nomenclature of the rail professional.

---

## 7. Language & Localization Context
All UI strings must respect Italian railway terminology:
- **Turno PdC:** Personale di Condotta (Engine Crew)
- **Giro Materiale:** Rolling Stock Rotation
- **Periodicità:** L(Lunedì), M(Martedì), X(Mercoledì), G(Giovedì), V(Venerdì), S(Sabato), D(Domenica).

The design must accommodate the varying lengths of these strings without breaking the "Kinetic Conductor" grid.