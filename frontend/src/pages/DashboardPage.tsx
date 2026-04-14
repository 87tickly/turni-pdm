import { useState, useEffect } from "react"
import { getHealth, getDbInfo, type DbInfo } from "@/lib/api"
import { Database, Train, MapPin, Activity } from "lucide-react"

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
    <div className="bg-card border border-border rounded-lg p-5">
      <div className="flex items-center gap-3 mb-3">
        <div className="p-2 bg-muted rounded-md">
          <Icon size={18} className="text-muted-foreground" />
        </div>
        <span className="text-sm text-muted-foreground">{label}</span>
      </div>
      <p className="text-2xl font-semibold">{value}</p>
      {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
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
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-xl font-semibold">Dashboard</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Stato del sistema e statistiche database
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`inline-block w-2 h-2 rounded-full ${
              health === "ok" ? "bg-success" : "bg-destructive"
            }`}
          />
          <span className="text-sm text-muted-foreground">
            {health === "ok" ? "Sistema operativo" : health}
          </span>
        </div>
      </div>

      {error && (
        <div className="bg-destructive/10 text-destructive text-sm p-3 rounded-md mb-6">
          {error}
        </div>
      )}

      {info ? (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <StatCard
              icon={Database}
              label="Segmenti totali"
              value={info.total_segments.toLocaleString()}
              sub="Train segments nel database"
            />
            <StatCard
              icon={Train}
              label="Treni unici"
              value={info.unique_trains_count}
              sub="Numero treni distinti"
            />
            <StatCard
              icon={MapPin}
              label="Turni materiale"
              value={info.material_turns.length}
              sub="Cicli rotazione importati"
            />
            <StatCard
              icon={Activity}
              label="Day indices"
              value={info.day_indices.length}
              sub="Varianti giornaliere"
            />
          </div>

          {/* Turni materiale */}
          {info.material_turns.length > 0 && (
            <div className="bg-card border border-border rounded-lg p-5">
              <h3 className="text-sm font-medium mb-3">Turni materiale importati</h3>
              <div className="flex flex-wrap gap-2">
                {info.material_turns.map((t) => (
                  <span
                    key={t.id}
                    className="px-2 py-1 bg-muted rounded text-xs font-mono"
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
          <p className="text-sm text-muted-foreground">Caricamento dati...</p>
        )
      )}
    </div>
  )
}
