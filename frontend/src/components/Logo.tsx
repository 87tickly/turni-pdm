import { Link } from "react-router-dom"

export function Logo({ size = "lg" }: { size?: "sm" | "lg" }) {
  const textSize = size === "lg" ? "text-2xl" : "text-lg"
  const dotSize = size === "lg" ? "h-2 w-2" : "h-1.5 w-1.5"

  return (
    <Link
      to="/"
      className="flex items-baseline gap-0.5 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
      aria-label="COLAZIONE PDM — Homepage"
    >
      <span
        className={`${textSize} font-black tracking-tight`}
        style={{ color: "#0062CC" }}
      >
        COLAZIONE
      </span>
      <span
        className={`inline-block ${dotSize} rounded-full animate-pulse-dot`}
        style={{ backgroundColor: "#30D158" }}
      />
    </Link>
  )
}
