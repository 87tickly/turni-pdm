import type { Config } from "tailwindcss";

/**
 * Palette brand ARTURO Business (questo prodotto = COLAZIONE: gestione
 * turni / pianificazione / operations per operatori ferroviari).
 * - `primary` = #0062CC (blu ARTURO, comune a tutto l'ecosistema)
 * - `arturo-business` = #B88B5C (terracotta/caramel di Business sul
 *    sito arturo.travel, distingue il prodotto dai fratelli Live e Travel)
 * Font brand: Exo 2 (Google Fonts), weight 900 per il wordmark.
 */
const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(214.3 31.8% 91.4%)",
        input: "hsl(214.3 31.8% 91.4%)",
        ring: "#0062CC",
        background: "hsl(0 0% 100%)",
        foreground: "hsl(222.2 84% 4.9%)",
        primary: {
          DEFAULT: "#0062CC",
          foreground: "#FFFFFF",
        },
        "arturo-business": "#B88B5C",
        secondary: {
          DEFAULT: "hsl(210 40% 96.1%)",
          foreground: "hsl(222.2 47.4% 11.2%)",
        },
        muted: {
          DEFAULT: "hsl(210 40% 96.1%)",
          foreground: "hsl(215.4 16.3% 46.9%)",
        },
        accent: {
          DEFAULT: "hsl(210 40% 96.1%)",
          foreground: "hsl(222.2 47.4% 11.2%)",
        },
        destructive: {
          DEFAULT: "hsl(0 84.2% 60.2%)",
          foreground: "hsl(210 40% 98%)",
        },
      },
      fontFamily: {
        // `font-sans` (default Tailwind) sovrascritto a Exo 2: tutto il
        // markup eredita Exo 2 senza dover taggare ogni elemento.
        sans: ['"Exo 2"', "system-ui", "sans-serif"],
        brand: ['"Exo 2"', "system-ui", "sans-serif"],
      },
      borderRadius: {
        lg: "0.5rem",
        md: "0.375rem",
        sm: "0.25rem",
      },
      gridTemplateColumns: {
        // Per la mini-Gantt giro: 24 colonne ore (00..23)
        "24": "repeat(24, minmax(0, 1fr))",
      },
      keyframes: {
        "pulse-dot": {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.45", transform: "scale(0.78)" },
        },
      },
      animation: {
        "pulse-dot": "pulse-dot 1.6s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
