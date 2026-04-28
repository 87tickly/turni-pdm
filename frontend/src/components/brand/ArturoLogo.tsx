/**
 * Wordmark "ARTURO • Live" — variante testuale (skill `arturo-brand-logo`).
 *
 * Tre elementi inline:
 *   1. "ARTURO"  — Exo 2, weight 900, #0062CC
 *   2. punto    — cerchio #30D158 con animazione `pulse-dot` (1.6s loop)
 *   3. "Live"    — Exo 2, weight 900, #0070B5
 *
 * Non modificare colori, pesi o animazione senza approvazione del
 * brand owner (regola assoluta della skill).
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
      aria-label="ARTURO Live"
    >
      <span className="text-primary">ARTURO</span>
      <span
        className={cn("inline-block animate-pulse-dot rounded-full bg-arturo-dot", DOT_CLASS[size])}
        aria-hidden
      />
      <span className="text-arturo-live">Live</span>
    </span>
  );
}
