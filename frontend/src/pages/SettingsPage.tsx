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
    <div
      className="rounded-lg px-4 py-3"
      style={{
        backgroundColor: "var(--color-surface-container-lowest)",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      <div className="flex items-center gap-2 mb-1">
        <Icon
          size={13}
          style={{ color: "var(--color-on-surface-quiet)" }}
        />
        <span
          className="text-[10px] font-bold uppercase"
          style={{
            color: "var(--color-on-surface-muted)",
            letterSpacing: "0.1em",
          }}
        >
          {label}
        </span>
      </div>
      <div
        className="leading-none"
        style={{
          fontFamily: "var(--font-display)",
          fontSize: "24px",
          fontWeight: 700,
          color: "var(--color-on-surface-strong)",
          letterSpacing: "-0.02em",
        }}
      >
        {value}
      </div>
      {sub && (
        <p
          className="text-[11px] mt-1"
          style={{ color: "var(--color-on-surface-muted)" }}
        >
          {sub}
        </p>
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
        <div
          className="text-[10px] font-bold uppercase mb-1"
          style={{
            color: "var(--color-on-surface-quiet)",
            letterSpacing: "0.12em",
          }}
        >
          Impostazioni
        </div>
        <h2
          className="font-bold tracking-tight"
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "22px",
            letterSpacing: "-0.02em",
            color: "var(--color-on-surface-strong)",
          }}
        >
          Configurazione e informazioni
        </h2>
        <p
          className="text-[13px] mt-0.5"
          style={{ color: "var(--color-on-surface-muted)" }}
        >
          Diagnostica sistema, statistiche database, elenco turni materiale
        </p>
      </div>

      {/* System status */}
      <div
        className="rounded-xl p-5 mb-6"
        style={{
          backgroundColor: "var(--color-surface-container-lowest)",
          boxShadow: "var(--shadow-sm)",
        }}
      >
        <div className="flex items-center gap-2 mb-4">
          <Server
            size={15}
            style={{ color: "var(--color-on-surface-quiet)" }}
          />
          <h3
            className="font-semibold"
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "14px",
              color: "var(--color-on-surface-strong)",
            }}
          >
            Stato sistema
          </h3>
          <div
            className="flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium ml-auto"
            style={
              health === "ok"
                ? {
                    backgroundColor: "var(--color-success-container)",
                    color: "var(--color-success)",
                  }
                : {
                    backgroundColor: "var(--color-destructive-container)",
                    color: "var(--color-destructive)",
                  }
            }
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
          <div
            className="text-[13px] p-3 rounded-lg mb-4"
            style={{
              backgroundColor: "var(--color-destructive-container)",
              color: "var(--color-destructive)",
            }}
          >
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
                  <h4
                    className="font-semibold"
                    style={{
                      fontFamily: "var(--font-display)",
                      fontSize: "13px",
                      color: "var(--color-on-surface-strong)",
                    }}
                  >
                    Turni materiale importati
                  </h4>
                  <span
                    className="text-[11px]"
                    style={{ color: "var(--color-on-surface-muted)" }}
                  >
                    {info.material_turns.length} turni
                  </span>
                </div>
                <div
                  className="flex flex-wrap gap-1.5 p-3 rounded-lg"
                  style={{
                    backgroundColor: "var(--color-surface-container-low)",
                  }}
                >
                  {info.material_turns.map((t) => (
                    <span
                      key={t.id}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono transition-colors"
                      style={{
                        backgroundColor: "var(--color-surface-container-lowest)",
                        color: "var(--color-on-surface-muted)",
                      }}
                    >
                      {t.turn_number}
                      {t.material_type && (
                        <span
                          className="px-1 py-px rounded text-[9px] font-semibold"
                          style={{
                            backgroundColor: "rgba(0, 98, 204, 0.10)",
                            color: "var(--color-brand)",
                          }}
                        >
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
              <div
                className="w-5 h-5 border-2 border-t-transparent rounded-full animate-spin"
                style={{ borderColor: "var(--color-brand)", borderTopColor: "transparent" }}
              />
            </div>
          )
        )}
      </div>
    </div>
  )
}
