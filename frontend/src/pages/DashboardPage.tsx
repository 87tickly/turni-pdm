import { useState, useEffect } from "react"
import { getHealth, getDbInfo, type DbInfo } from "@/lib/api"
import {
  Database,
  Train,
  MapPin,
  Activity,
  CircleCheck,
  CircleX,
} from "lucide-react"
import { cn } from "@/lib/utils"

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  accent,
}: {
  icon: typeof Database
  label: string
  value: string | number
  sub?: string
  accent?: string
}) {
  return (
    <div className="bg-card rounded-lg border border-border-subtle p-4 hover:border-border transition-colors">
      <div className="flex items-center gap-2 mb-3">
        <div
          className={cn(
            "w-7 h-7 rounded-md flex items-center justify-center",
            accent || "bg-muted"
          )}
        >
          <Icon size={14} className="text-muted-foreground" />
        </div>
        <span className="text-[12px] text-muted-foreground font-medium">
          {label}
        </span>
      </div>
      <p className="text-2xl font-semibold tracking-tight">{value}</p>
      {sub && (
        <p className="text-[11px] text-muted-foreground mt-1">{sub}</p>
      )}
    </div>
  )
}

export function DashboardPage() {
  const [health, setHealth] = useState<string>("...")
  const [info, setInfo] = useState<DbInfo | null>(null)
  const [error, setError] = useState("")

  useEffect(() => {
    getHealth()
      .then((h) => setHealth(h.status))
      .catch(() => setHealth("errore"))

    getDbInfo()
      .then(setInfo)
      .catch((e) => setError(e.message))
  }, [])

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Dashboard</h2>
          <p className="text-[13px] text-muted-foreground mt-0.5">
            Panoramica sistema e database
          </p>
        </div>
        <div
          className={cn(
            "flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium",
            health === "ok"
              ? "bg-success-muted text-success"
              : "bg-destructive/10 text-destructive"
          )}
        >
          {health === "ok" ? (
            <CircleCheck size={12} />
          ) : (
            <CircleX size={12} />
          )}
          {health === "ok" ? "Operativo" : health}
        </div>
      </div>

      {error && (
        <div className="bg-destructive/10 text-destructive text-[13px] p-3 rounded-lg border border-destructive/20 mb-6">
          {error}
        </div>
      )}

      {info ? (
        <>
          {/* Stats grid */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
            <StatCard
              icon={Database}
              label="Segmenti"
              value={info.total_segments.toLocaleString()}
              sub="Train segments nel DB"
              accent="bg-info-muted"
            />
            <StatCard
              icon={Train}
              label="Treni unici"
              value={info.unique_trains_count.toLocaleString()}
              sub="Numeri treno distinti"
              accent="bg-success-muted"
            />
            <StatCard
              icon={MapPin}
              label="Turni materiale"
              value={info.material_turns.length}
              sub="Cicli rotazione"
              accent="bg-warning-muted"
            />
            <StatCard
              icon={Activity}
              label="Varianti giorno"
              value={info.day_indices.length}
              sub="Day indices"
              accent="bg-primary/10"
            />
          </div>

          {/* Turni materiale */}
          {info.material_turns.length > 0 && (
            <div className="bg-card rounded-lg border border-border-subtle p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-[13px] font-medium">
                  Turni materiale importati
                </h3>
                <span className="text-[11px] text-muted-foreground">
                  {info.material_turns.length} turni
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {info.material_turns.map((t) => (
                  <span
                    key={t.id}
                    className="px-2 py-0.5 bg-muted hover:bg-sidebar-accent rounded text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors cursor-default"
                  >
                    {t.turn_number}
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
      ) : (
        !error && (
          <div className="flex items-center justify-center h-40">
            <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          </div>
        )
      )}
    </div>
  )
}
