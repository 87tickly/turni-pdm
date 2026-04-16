import { useState, useEffect } from "react"
import { getHealth, getDbInfo, type DbInfo } from "@/lib/api"
import {
  Database,
  Train,
  MapPin,
  Activity,
  CircleCheck,
  CircleX,
  Server,
} from "lucide-react"
import { cn } from "@/lib/utils"

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
}: {
  icon: typeof Database
  label: string
  value: string | number
  sub?: string
}) {
  return (
    <div className="bg-card rounded-lg border border-border p-4">
      <div className="flex items-center gap-2 mb-2">
        <Icon size={14} className="text-muted-foreground" />
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

export function SettingsPage() {
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
      <div className="mb-6">
        <h2 className="text-lg font-semibold tracking-tight">Impostazioni</h2>
        <p className="text-[13px] text-muted-foreground mt-0.5">
          Configurazione e informazioni di sistema
        </p>
      </div>

      {/* System status */}
      <div className="bg-card rounded-xl border border-border p-5 mb-6">
        <div className="flex items-center gap-2 mb-4">
          <Server size={15} className="text-muted-foreground" />
          <h3 className="text-[14px] font-semibold">Stato sistema</h3>
          <div
            className={cn(
              "flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium ml-auto",
              health === "ok"
                ? "bg-success-muted text-success"
                : "bg-destructive/10 text-destructive"
            )}
          >
            {health === "ok" ? (
              <CircleCheck size={11} />
            ) : (
              <CircleX size={11} />
            )}
            {health === "ok" ? "Operativo" : health}
          </div>
        </div>

        {error && (
          <div className="bg-destructive/10 text-destructive text-[13px] p-3 rounded-lg border border-destructive/20 mb-4">
            {error}
          </div>
        )}

        {info ? (
          <>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
              <StatCard
                icon={Database}
                label="Segmenti"
                value={info.total_segments.toLocaleString()}
                sub="Train segments nel DB"
              />
              <StatCard
                icon={Train}
                label="Treni unici"
                value={info.unique_trains_count.toLocaleString()}
                sub="Numeri treno distinti"
              />
              <StatCard
                icon={MapPin}
                label="Turni materiale"
                value={info.material_turns.length}
                sub="Cicli rotazione"
              />
              <StatCard
                icon={Activity}
                label="Varianti giorno"
                value={info.day_indices.length}
                sub="Day indices"
              />
            </div>

            {/* Turni materiale */}
            {info.material_turns.length > 0 && (
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-[13px] font-medium">
                    Turni materiale importati
                  </h4>
                  <span className="text-[11px] text-muted-foreground">
                    {info.material_turns.length} turni
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {info.material_turns.map((t) => (
                    <span
                      key={t.id}
                      className="inline-flex items-center gap-1 px-2 py-0.5 bg-muted hover:bg-border rounded text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors cursor-default"
                    >
                      {t.turn_number}
                      {t.material_type && (
                        <span className="px-1 py-px rounded bg-brand/10 text-brand text-[9px] font-semibold">
                          {t.material_type}
                        </span>
                      )}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : (
          !error && (
            <div className="flex items-center justify-center h-24">
              <div className="w-5 h-5 border-2 border-brand border-t-transparent rounded-full animate-spin" />
            </div>
          )
        )}
      </div>
    </div>
  )
}
