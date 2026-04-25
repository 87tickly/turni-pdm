# Design System Document: The Precision Conductor

## 1. Overview & Creative North Star
This design system is built for the high-stakes environment of railway management. Our **Creative North Star** is **"The Precision Conductor."** 

In an industry where seconds dictate safety and efficiency, the UI must transcend being a mere "tool." It must feel like a high-end, editorial dashboard—think of a luxury Swiss watch movement or the cockpit of a high-speed train. We avoid the "generic SaaS" look by rejecting heavy shadows and boxy containers. Instead, we use **Tonal Layering** and **Intentional Asymmetry** to guide the dispatcher’s eye through dense data with surgical precision. The aesthetic is pragmatic, inspired by the efficiency of Linear and the clarity of Notion, but elevated with a signature depth that feels custom and premium.

---

## 2. Colors & The Surface Philosophy
The palette is rooted in functional clarity. We use the brand’s signature green as an operational "pulse" rather than just a decoration.

### The "No-Line" Rule
To achieve a high-end editorial feel, **prohibit the use of 1px solid borders for sectioning.** Structural boundaries must be defined solely through background color shifts. 
- A sidebar should not have a right-border; it should be rendered in `surface-container-low` (#eff4ff) against a main content area of `surface` (#f8f9ff).
- Use `surface-container-highest` (#d3e4fe) to highlight active or high-priority workspaces.

### Surface Hierarchy & Nesting
Treat the UI as a series of physical layers—stacked sheets of frosted glass or fine paper.
- **Base Layer:** `surface` (#f8f9ff)
- **Nested Workspaces:** `surface-container` (#e5eeff)
- **Interactive Modals:** `surface-container-lowest` (#ffffff) to create a soft, natural lift.

### The "Glass & Gradient" Rule
Flat colors can feel "dead." For primary CTAs and the signature brand "pulse," use subtle gradients. 
- **Action Gradient:** Transition from `primary` (#0050cb) to `primary_container` (#0066ff) at a 135-degree angle.
- **Glassmorphism:** For floating elements (tooltips, command bars), use `surface_container_lowest` with an 80% opacity and a `20px` backdrop-blur. This allows the movement of the railway data to bleed through, keeping the dispatcher grounded in the live environment.

---

## 3. Typography
We utilize a system-font stack (centered on **Inter**) to ensure zero latency and maximum legibility.

- **Display & Headlines:** Use `headline-lg` (2rem) with tight letter-spacing (-0.02em) for a bold, authoritative "editorial" header.
- **The Data Layer:** `body-sm` (0.75rem) is the workhorse. Ensure a line-height of 1.5 to prevent "data-fatigue" during long shifts.
- **Labels:** `label-sm` (0.6875rem) should be used for metadata. For a premium touch, use `on_surface_variant` (#424656) in ALL CAPS with +0.05em tracking to differentiate from interactive text.

---

## 4. Elevation & Depth
Depth is achieved through **Tonal Layering** rather than traditional drop shadows.

- **The Layering Principle:** Stack `surface-container` tiers. A `surface-container-lowest` card placed on a `surface-container-low` background creates a "lift" that feels integrated into the architecture.
- **Ambient Shadows:** If a floating effect is required (e.g., a critical alert popover), use an extra-diffused shadow: `box-shadow: 0 12px 40px rgba(11, 28, 48, 0.06)`. Note the tint: the shadow is a low-opacity version of `on_surface` (#0b1c30), not pure black.
- **The "Ghost Border" Fallback:** If a border is required for accessibility in high-density tables, use a "Ghost Border": `outline-variant` (#c2c6d8) at **15% opacity**. Never use 100% opaque lines.

---

## 5. Components

### Buttons
- **Primary:** Gradient (`primary` to `primary_container`), `md` (0.375rem) corner radius. No border.
- **Secondary:** `surface_container_high` background with `primary` text. This feels more "integrated" than an outlined button.
- **Operational (Success):** Use `secondary` (#006e25) for the brand's signature "green dot" status actions.

### The Data Grid (Crucial for Dispatchers)
- **Forbid Dividers:** Do not use horizontal lines between rows. Use `surface_container_low` for zebra-striping or a 4px vertical gap between row containers.
- **States:** On hover, change the row background to `surface_container_highest`.

### Input Fields
- Use `surface_container_low` as the fill. 
- On focus, transition the background to `surface_container_lowest` and apply a 2px "Ghost Border" of `primary` at 40% opacity.

### The "Pulse" Chip (Status)
- For the brand "COLAZIONE" identity, use a `secondary` (#006e25) dot next to text. The chip background should be `secondary_container` (#80f98b) at 30% opacity for a soft, premium feel.

---

## 6. Do's and Don'ts

### Do
- **DO** use whitespace as a separator. If you feel the need for a line, try adding 8px of padding instead.
- **DO** use `tertiary` (#725500) for "Attention" states that aren't quite errors (e.g., scheduled maintenance).
- **DO** maintain a "Density with Breathability" approach. Keep data points close, but use large margins for the overall page layout to provide visual relief.

### Don't
- **DON'T** use `error` (#ba1a1a) for anything other than critical system failures or stopped trains.
- **DON'T** use "Hard" corners (0px) or "Bubble" corners (999px) for functional containers. Stick to the `DEFAULT` (0.25rem) or `md` (0.375rem) to maintain a professional, pragmatic tone.
- **DON'T** use pure black (#000000) for text. Always use `on_surface` (#0b1c30) to maintain a sophisticated, low-contrast eye-comfort level.