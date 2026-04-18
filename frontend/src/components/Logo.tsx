import { Link } from "react-router-dom"

export function Logo({ size = "lg" }: { size?: "sm" | "lg" }) {
  const textSize = size === "lg" ? "text-2xl" : "text-lg"
  const dotSize = size === "lg" ? "h-2 w-2" : "h-1.5 w-1.5"

  return (
    <Link
      to="/"
      className="flex items-baseline gap-1 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
      aria-label="ARTURO PDM — Homepage"
    >
      <span
        className={`${textSize} font-extrabold tracking-tight`}
        style={{
          color: "var(--color-brand)",
          fontFamily: "var(--font-display)",
          letterSpacing: "-0.02em",
        }}
      >
        ARTURO
      </span>
      <span
        className={`inline-block ${dotSize} rounded-full animate-pulse-dot`}
        style={{
          backgroundColor: "var(--color-dot)",
          boxShadow: "0 0 0 3px rgb(34 197 94 / 0.18)",
        }}
        aria-hidden="true"
      />
    </Link>
  )
}
