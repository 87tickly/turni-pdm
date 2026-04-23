/**
 * FR Approvals Panel — Step 10 (23/04/2026).
 *
 * Pannello per gestire le stazioni FR (dormita) approvate per un PdC.
 * Usato dalla UI post-generazione turni per approvare le candidate
 * proposte dall'algoritmo v4 (richiesta utente).
 *
 * Props:
 *   pdcId: identificativo del PdC (stringa non vuota)
 *   candidateStations: lista stazioni proposte dal builder (fr_candidate=True)
 *   nonClosableDays: lista giornate non chiudibili (senza rientro ne' FR)
 *
 * Endpoint backend:
 *   GET    /api/pdc/{pdc_id}/fr-approved
 *   POST   /api/pdc/{pdc_id}/fr-approved
 *   POST   /api/pdc/{pdc_id}/fr-approved/batch
 *   DELETE /api/pdc/{pdc_id}/fr-approved/{station}
 */
import { useEffect, useState } from "react"

interface FRApprovalsPanelProps {
  pdcId: string
  candidateStations?: string[]
  nonClosableDays?: { day: number; reason: string; fromStation?: string }[]
}

export function FRApprovalsPanel({
  pdcId,
  candidateStations = [],
  nonClosableDays = [],
}: FRApprovalsPanelProps) {
  const [approved, setApproved] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [newStation, setNewStation] = useState("")

  const load = async () => {
    if (!pdcId) return
    setLoading(true)
    setError(null)
    try {
      const r = await fetch(
        `/api/pdc/${encodeURIComponent(pdcId)}/fr-approved`,
      )
      if (!r.ok) throw new Error(`${r.status}`)
      const body = await r.json()
      setApproved(body.stations || [])
    } catch (e: any) {
      setError(`Errore caricamento: ${e.message || e}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [pdcId])

  const approve = async (station: string) => {
    if (!station || !station.trim()) return
    setLoading(true)
    try {
      const r = await fetch(
        `/api/pdc/${encodeURIComponent(pdcId)}/fr-approved`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ station, notes: "approvata da UI" }),
        },
      )
      if (!r.ok) throw new Error(`${r.status}`)
      const body = await r.json()
      setApproved(body.stations || [])
      setNewStation("")
    } catch (e: any) {
      setError(`Errore approvazione: ${e.message || e}`)
    } finally {
      setLoading(false)
    }
  }

  const revoke = async (station: string) => {
    setLoading(true)
    try {
      const r = await fetch(
        `/api/pdc/${encodeURIComponent(pdcId)}/fr-approved/${encodeURIComponent(station)}`,
        { method: "DELETE" },
      )
      if (!r.ok) throw new Error(`${r.status}`)
      const body = await r.json()
      setApproved(body.stations || [])
    } catch (e: any) {
      setError(`Errore revoca: ${e.message || e}`)
    } finally {
      setLoading(false)
    }
  }

  // Stazioni candidate non ancora approvate
  const pendingCandidates = candidateStations.filter(
    (s) => !approved.includes(s.toUpperCase()),
  )

  return (
    <div
      className="rounded-lg border p-4 space-y-4"
      style={{
        borderColor: "var(--color-outline-variant)",
        backgroundColor: "var(--color-surface)",
      }}
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">
          Dormite e stazioni FR approvate — PdC {pdcId || "(nessuno)"}
        </h3>
        {loading && (
          <span
            className="text-[11px]"
            style={{ color: "var(--color-on-surface-muted)" }}
          >
            caricamento…
          </span>
        )}
      </div>

      {error && (
        <div
          className="text-[12px] p-2 rounded"
          style={{
            backgroundColor: "var(--color-destructive-container, #fee)",
            color: "var(--color-destructive, #c00)",
          }}
        >
          {error}
        </div>
      )}

      {/* Candidate proposte dal builder */}
      {pendingCandidates.length > 0 && (
        <div className="space-y-2">
          <div
            className="text-[12px] font-medium"
            style={{ color: "var(--color-on-surface-muted)" }}
          >
            Dormite proposte dal builder (approva una volta per stazione)
          </div>
          <div className="flex flex-wrap gap-2">
            {pendingCandidates.map((s) => (
              <div
                key={s}
                className="flex items-center gap-2 px-3 py-1.5 rounded border text-[13px]"
                style={{ borderColor: "var(--color-outline-variant)" }}
              >
                <span className="font-medium">{s}</span>
                <button
                  onClick={() => approve(s)}
                  disabled={loading || !pdcId}
                  className="text-[11px] px-2 py-0.5 rounded font-semibold"
                  style={{
                    backgroundColor: "rgba(16, 185, 129, 0.12)",
                    color: "#059669",
                  }}
                >
                  ✓ Approva
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Lista approvate */}
      <div className="space-y-2">
        <div
          className="text-[12px] font-medium"
          style={{ color: "var(--color-on-surface-muted)" }}
        >
          FR approvate ({approved.length})
        </div>
        {approved.length === 0 ? (
          <div
            className="text-[12px] italic"
            style={{ color: "var(--color-on-surface-muted)" }}
          >
            Nessuna stazione FR approvata per questo PdC.
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {approved.map((s) => (
              <div
                key={s}
                className="flex items-center gap-2 px-3 py-1.5 rounded text-[13px]"
                style={{ backgroundColor: "rgba(124, 58, 237, 0.12)", color: "#6D28D9" }}
              >
                <span className="font-medium">{s}</span>
                <button
                  onClick={() => revoke(s)}
                  disabled={loading || !pdcId}
                  className="text-[11px] opacity-70 hover:opacity-100"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Add manuale */}
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={newStation}
          onChange={(e) => setNewStation(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") approve(newStation)
          }}
          placeholder="Aggiungi stazione FR manualmente…"
          disabled={loading || !pdcId}
          className="flex-1 text-[13px] px-3 py-1.5 rounded border"
          style={{
            borderColor: "var(--color-outline-variant)",
            backgroundColor: "var(--color-surface-variant)",
          }}
        />
        <button
          onClick={() => approve(newStation)}
          disabled={loading || !pdcId || !newStation.trim()}
          className="text-[12px] px-3 py-1.5 rounded font-semibold"
          style={{
            backgroundColor: "var(--color-primary, #1f6feb)",
            color: "var(--color-on-primary, white)",
          }}
        >
          + Aggiungi
        </button>
      </div>

      {/* Non chiudibili (fallback taxi) */}
      {nonClosableDays.length > 0 && (
        <div className="space-y-2 border-t pt-3"
             style={{ borderColor: "var(--color-outline-variant)" }}>
          <div
            className="text-[12px] font-medium"
            style={{ color: "var(--color-destructive, #c00)" }}
          >
            Giornate non chiudibili ({nonClosableDays.length}) — considera
            taxi di rientro
          </div>
          {nonClosableDays.map((d, i) => (
            <div
              key={i}
              className="text-[12px] flex items-center justify-between gap-2 p-2 rounded"
              style={{
                backgroundColor: "rgba(220, 38, 38, 0.06)",
              }}
            >
              <div>
                <span className="font-medium">Giorno {d.day}</span>
                {d.fromStation && (
                  <span className="ml-2">da {d.fromStation}</span>
                )}
                <span
                  className="ml-2"
                  style={{ color: "var(--color-on-surface-muted)" }}
                >
                  {d.reason}
                </span>
              </div>
              <button
                className="text-[11px] px-2 py-0.5 rounded font-semibold"
                style={{
                  backgroundColor: "rgba(245, 158, 11, 0.12)",
                  color: "#D97706",
                }}
                onClick={() =>
                  alert(
                    `Taxi di rientro per giorno ${d.day} — feature proponibile, non ancora implementata`,
                  )
                }
              >
                🚕 Taxi
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
