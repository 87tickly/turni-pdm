/**
 * Wordmark "ARTURO • Business" — questo prodotto è ARTURO Business
 * (gestione turni / pianificazione / operations sul sito arturo.travel).
 *
 * Tre elementi inline:
 *   1. "ARTURO"    — Exo 2, weight 900, #0062CC (blu ecosistema)
 *   2. punto       — cerchio #B88B5C con animazione `pulse-dot` (1.6s loop)
 *   3. "Business"  — Exo 2, weight 900, #B88B5C (terracotta Business)
 *
 * Pattern direttamente derivato dalla skill `arturo-brand-logo` per
 * il fratello "Live" — qui adattato a Business con il colore proprio
 * del prodotto (cambio approvato dall'utente in chat 2026-04-28).
 */

import { cn } from "@/lib/utils";

type Size = "sm" | "lg";

interface ArturoLogoProps {
  size?: Size;
  className?: string;
}

const TEXT_CLASS: Record<Size, string> = {
  sm: "text-xl",
  lg: "text-3xl",
};

const DOT_CLASS: Record<Size, string> = {
  sm: "h-2 w-2",
  lg: "h-3 w-3",
};

export function ArturoLogo({ size = "sm", className }: ArturoLogoProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 font-brand font-black tracking-tight",
        TEXT_CLASS[size],
        className,
      )}
      aria-label="ARTURO Business"
    >
      <span className="text-primary">ARTURO</span>
      <span
        className={cn(
          "inline-block animate-pulse-dot rounded-full bg-arturo-business",
          DOT_CLASS[size],
        )}
        aria-hidden
      />
      <span className="text-arturo-business">Business</span>
    </span>
  );
}
