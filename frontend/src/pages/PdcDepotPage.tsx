/**
 * PdcDepotPage — Vista completa di tutti i turni di un deposito.
 *
 * Ogni turno mostra tutte le sue giornate una sotto l'altra come Gantt
 * editabili: l'utente puo' modificare blocchi in qualsiasi turno/giornata,
 * spostare treni (con CVp/CVa agganciati) mantenendo il resto intatto.
 *
 * Salva le modifiche automaticamente via debounce (1.5s dopo l'ultima
 * modifica) chiamando PUT /pdc-turn/{id} per il turno modificato.
 */

import { useState, useEffect, useCallback, useRef } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { ChevronLeft, Save, Loader2, ChevronDown, ChevronRight } from "lucide-react"
import { PdcGantt } from "@/components/PdcGantt"
import {
  listPdcTurns,
  getPdcTurn,
  updatePdcTurn,
  type PdcTurn,
  type PdcTurnDetail,
  type PdcBlock,
} from "@/lib/api"

// Stato per-turno: dati caricati + dirty flag per salvataggio automatico
type TurnState = {
  detail: PdcTurnDetail
  dirty: boolean
  saving: boolean
}

export function PdcDepotPage() {
  const { impianto } = useParams<{ impianto: string }>()
  const navigate = useNavigate()

  const [turnsList, setTurnsList] = useState<PdcTurn[]>([])
  const [turns, setTurns] = useState<Record<number, TurnState>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [expandedTurns, setExpandedTurns] = useState<Set<number>>(new Set())

  // Timer debounce salvataggio (per turno_id)
  const saveTimers = useRef<Record<number, ReturnType<typeof setTimeout>>>({})

  // Caricamento iniziale
  useEffect(() => {
    if (!impianto) return
    setLoading(true)
    listPdcTurns({ impianto })
      .then((res) => {
        setTurnsList(res.turns)
        if (res.turns.length > 0) {
          setExpandedTurns(new Set([res.turns[0].id]))
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Errore caricamento"))
      .finally(() => setLoading(false))
  }, [impianto])

  // Carica dettaglio di un turno (lazy quando espanso)
  const loadTurnDetail = useCallback(async (turnId: number) => {
    if (turns[turnId]) return
    try {
      const detail = await getPdcTurn(turnId)
      setTurns((prev) => ({
        ...prev,
        [turnId]: { detail, dirty: false, saving: false },
      }))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Errore caricamento dettaglio")
    }
  }, [turns])

  // Salvataggio di un turno
  const saveTurn = useCallback(async (turnId: number) => {
    const t = turns[turnId]
    if (!t || !t.dirty) return
    setTurns((prev) => ({ ...prev, [turnId]: { ...prev[turnId], saving: true } }))
    try {
      const d = t.detail
      await updatePdcTurn(turnId, {
        codice: d.turn.codice,
        planning: d.turn.planning,
        impianto: d.turn.impianto,
        profilo: d.turn.profilo as "Condotta" | "Scorta",
        valid_from: d.turn.valid_from,
        valid_to: d.turn.valid_to,
        days: d.days.map((day) => ({
          day_number: day.day_number,
          periodicita: day.periodicita,
          start_time: day.start_time,
          end_time: day.end_time,
          lavoro_min: day.lavoro_min,
          condotta_min: day.condotta_min,
          km: day.km,
          notturno: day.notturno === 1,
          riposo_min: day.riposo_min,
          is_disponibile: day.is_disponibile === 1,
          blocks: day.blocks.map((b) => ({
            seq: b.seq,
            block_type: b.block_type,
            train_id: b.train_id,
            vettura_id: b.vettura_id,
            from_station: b.from_station,
            to_station: b.to_station,
            start_time: b.start_time,
            end_time: b.end_time,
            accessori_maggiorati: b.accessori_maggiorati === 1,
          })),
        })),
        notes: d.notes.map((n) => ({
          train_id: n.train_id,
          periodicita_text: n.periodicita_text,
          non_circola_dates: n.non_circola_dates,
          circola_extra_dates: n.circola_extra_dates,
        })),
      })
      setTurns((prev) => ({
        ...prev,
        [turnId]: { ...prev[turnId], dirty: false, saving: false },
      }))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Errore salvataggio")
      setTurns((prev) => ({ ...prev, [turnId]: { ...prev[turnId], saving: false } }))
    }
  }, [turns])

  // Modifica blocchi di una giornata (chiamato dal Gantt)
  const updateDayBlocks = useCallback(
    (turnId: number, dayId: number, changes: Record<number, { start_time?: string; end_time?: string }>) => {
      setTurns((prev) => {
        const st = prev[turnId]
        if (!st) return prev
        const newDetail = {
          ...st.detail,
          days: st.detail.days.map((d) => {
            if (d.id !== dayId) return d
            const newBlocks = [...d.blocks]
            for (const [idxStr, patch] of Object.entries(changes)) {
              const idx = parseInt(idxStr)
              newBlocks[idx] = { ...newBlocks[idx], ...patch } as PdcBlock
            }
            return { ...d, blocks: newBlocks }
          }),
        }
        return {
          ...prev,
          [turnId]: { ...st, detail: newDetail, dirty: true },
        }
      })
      // Debounce salvataggio
      if (saveTimers.current[turnId]) clearTimeout(saveTimers.current[turnId])
      saveTimers.current[turnId] = setTimeout(() => saveTurn(turnId), 1500)
    },
    [saveTurn]
  )

  const toggleExpanded = (turnId: number) => {
    setExpandedTurns((prev) => {
      const next = new Set(prev)
      if (next.has(turnId)) next.delete(turnId)
      else {
        next.add(turnId)
        loadTurnDetail(turnId)
      }
      return next
    })
  }

  // Carica i dettagli dei turni inizialmente espansi
  useEffect(() => {
    for (const id of expandedTurns) {
      loadTurnDetail(id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expandedTurns])

  // Cleanup timers
  useEffect(() => () => {
    for (const t of Object.values(saveTimers.current)) clearTimeout(t)
  }, [])

  return (
    <div className="pb-8">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate("/pdc")}
            className="text-muted-foreground hover:text-foreground"
            title="Torna"
          >
            <ChevronLeft size={18} />
          </button>
          <div>
            <h2 className="text-lg font-semibold tracking-tight">
              Deposito {impianto}
            </h2>
            <p className="text-[13px] text-muted-foreground mt-0.5">
              Tutti i turni del deposito con giornate editabili. Le modifiche
              si salvano automaticamente 1.5s dopo l'ultima azione.
            </p>
          </div>
        </div>
      </div>

      {error && (
        <div className="mb-3 p-2 text-[12px] bg-destructive/10 text-destructive rounded">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-[12px] text-muted-foreground">Caricamento turni...</p>
      ) : turnsList.length === 0 ? (
        <p className="text-[12px] text-muted-foreground italic">
          Nessun turno per questo deposito.
        </p>
      ) : (
        <div className="space-y-3">
          {turnsList.map((t) => {
            const open = expandedTurns.has(t.id)
            const st = turns[t.id]
            return (
              <div
                key={t.id}
                className="border border-border-subtle rounded-lg bg-card"
              >
                <button
                  className="w-full flex items-center gap-3 px-3 py-2 hover:bg-muted/40 transition-colors"
                  onClick={() => toggleExpanded(t.id)}
                >
                  {open ? (
                    <ChevronDown size={14} className="text-muted-foreground" />
                  ) : (
                    <ChevronRight size={14} className="text-muted-foreground" />
                  )}
                  <span className="font-mono font-bold text-[13px]">
                    {t.codice}
                  </span>
                  <span className="text-[11px] text-muted-foreground">
                    [{t.planning}] {t.profilo}
                  </span>
                  {st?.dirty && !st.saving && (
                    <span className="text-[10px] px-2 py-0.5 rounded bg-amber-100 text-amber-700">
                      Modificato
                    </span>
                  )}
                  {st?.saving && (
                    <span className="text-[10px] px-2 py-0.5 rounded bg-primary/10 text-primary flex items-center gap-1">
                      <Loader2 size={10} className="animate-spin" /> Salvataggio...
                    </span>
                  )}
                  {st && !st.dirty && !st.saving && (
                    <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 flex items-center gap-1">
                      <Save size={10} /> Sincronizzato
                    </span>
                  )}
                  <span className="ml-auto text-[11px] text-muted-foreground font-mono">
                    {t.valid_from} → {t.valid_to}
                  </span>
                </button>

                {open && (
                  <div className="px-3 pb-3 border-t border-border-subtle pt-3 space-y-3">
                    {!st ? (
                      <p className="text-[11px] text-muted-foreground">Caricamento...</p>
                    ) : (
                      st.detail.days.map((day) => (
                        <div
                          key={day.id}
                          className="border border-border-subtle rounded-md p-2 bg-white"
                        >
                          <div className="flex items-center gap-3 mb-1 text-[11px]">
                            <span className="font-mono font-bold">
                              g{day.day_number}
                            </span>
                            <span className="font-mono px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                              {day.periodicita}
                            </span>
                            <span className="font-mono text-muted-foreground">
                              {day.start_time || "—"} – {day.end_time || "—"}
                            </span>
                            <span className="text-muted-foreground">
                              Lav {day.lavoro_min}m · Cct {day.condotta_min}m · Km {day.km}
                            </span>
                          </div>
                          {day.is_disponibile === 1 ? (
                            <p className="text-[11px] text-muted-foreground italic py-2 text-center">
                              Giornata disponibile / riposo
                            </p>
                          ) : (
                            <PdcGantt
                              blocks={day.blocks}
                              startTime={day.start_time}
                              endTime={day.end_time}
                              label={`${t.codice} · g${day.day_number} ${day.periodicita}`}
                              onBlocksChange={(changes) =>
                                updateDayBlocks(t.id, day.id, changes)
                              }
                              height={200}
                            />
                          )}
                        </div>
                      ))
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
