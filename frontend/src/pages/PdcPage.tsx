import { useState, useEffect, useCallback } from "react"
import { useNavigate } from "react-router-dom"
import {
  Train,
  Building2,
  Calendar,
  Clock,
  Route,
  Coffee,
  Pause,
  Moon,
  ChevronRight,
  ChevronDown,
  Info,
  Plus,
  Edit,
  Trash2,
  LayoutGrid,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { PdcGanttV2 } from "@/components/PdcGanttV2"
import {
  getPdcStats,
  listPdcTurns,
  getPdcTurn,
  deletePdcTurn,
  type PdcStats,
  type PdcTurn,
  type PdcTurnDetail,
  type PdcBlock,
  type PdcDay,
} from "@/lib/api"

// ── Utility ─────────────────────────────────────────────────────

function fmtHm(min: number): string {
  if (!min) return "—"
  const h = Math.floor(min / 60)
  const m = min % 60
  return `${h}:${m.toString().padStart(2, "0")}`
}

const BLOCK_META: Record<
  PdcBlock["block_type"],
  { label: string; color: string; icon: typeof Train }
> = {
  train: { label: "Treno", color: "bg-primary/10 text-primary border-primary/30", icon: Train },
  coach_transfer: { label: "Vettura", color: "bg-violet-50 text-violet-700 border-violet-200", icon: Route },
  cv_partenza: { label: "CVp", color: "bg-amber-50 text-amber-700 border-amber-200", icon: Clock },
  cv_arrivo: { label: "CVa", color: "bg-amber-50 text-amber-700 border-amber-200", icon: Clock },
  meal: { label: "Refez.", color: "bg-emerald-50 text-emerald-700 border-emerald-200", icon: Coffee },
  scomp: { label: "S.COMP", color: "bg-slate-100 text-slate-600 border-slate-300", icon: Pause },
  available: { label: "Disp.", color: "bg-slate-50 text-slate-400 border-slate-200", icon: Pause },
}

// ── Sottocomponente: elenco turni sidebar ───────────────────────

function TurnsList({
  turns,
  selectedId,
  onSelect,
  filter,
  onFilter,
  impianti,
}: {
  turns: PdcTurn[]
  selectedId: number | null
  onSelect: (id: number) => void
  filter: string
  onFilter: (v: string) => void
  impianti: string[]
}) {
  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-border-subtle">
        <select
          className="w-full text-[12px] px-2 py-1.5 rounded-md border border-border bg-background"
          value={filter}
          onChange={(e) => onFilter(e.target.value)}
        >
          <option value="">Tutti gli impianti ({turns.length})</option>
          {impianti.map((i) => (
            <option key={i} value={i}>{i}</option>
          ))}
        </select>
      </div>
      <div className="overflow-y-auto flex-1">
        {turns.length === 0 ? (
          <p className="p-4 text-[12px] text-muted-foreground text-center">
            Nessun turno caricato. Carica un PDF da <b>Import</b>.
          </p>
        ) : (
          turns.map((t) => (
            <button
              key={t.id}
              onClick={() => onSelect(t.id)}
              className={cn(
                "w-full text-left px-3 py-2 border-b border-border-subtle transition-colors text-[12px]",
                selectedId === t.id
                  ? "bg-primary/8 border-l-2 border-l-primary"
                  : "hover:bg-muted/40"
              )}
            >
              <div className="font-mono font-semibold">{t.codice}</div>
              <div className="text-muted-foreground text-[11px] truncate">{t.impianto}</div>
            </button>
          ))
        )}
      </div>
    </div>
  )
}

// ── Sottocomponente: blocchi di una giornata ────────────────────

function BlocksList({ blocks }: { blocks: PdcBlock[] }) {
  if (!blocks.length) {
    return (
      <p className="text-[11px] text-muted-foreground italic px-2 py-1">
        Nessun blocco
      </p>
    )
  }
  return (
    <div className="space-y-1">
      {blocks.map((b) => {
        const meta = BLOCK_META[b.block_type] ?? BLOCK_META.available
        const Icon = meta.icon
        const identifier = b.train_id || b.vettura_id || ""
        return (
          <div
            key={b.id}
            className={cn(
              "flex items-center gap-2 text-[11px] px-2 py-1 rounded border",
              meta.color
            )}
          >
            <Icon size={12} className="shrink-0" />
            <span className="font-semibold min-w-[48px]">{meta.label}</span>
            {identifier && (
              <span className="font-mono font-semibold">{identifier}</span>
            )}
            {b.from_station && (
              <span className="text-muted-foreground">{b.from_station}</span>
            )}
            {b.to_station && (
              <>
                <span className="text-muted-foreground">→</span>
                <span>{b.to_station}</span>
              </>
            )}
            <div className="ml-auto flex items-center gap-2 font-mono">
              {b.start_time && <span>{b.start_time}</span>}
              {b.start_time && b.end_time && (
                <span className="text-muted-foreground">–</span>
              )}
              {b.end_time && <span>{b.end_time}</span>}
              {b.accessori_maggiorati === 1 && (
                <span title="Accessori maggiorati (preriscaldo)" className="text-amber-600">
                  ●
                </span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Sottocomponente: giornata espandibile ───────────────────────

function DayCard({ day }: { day: PdcDay }) {
  const [open, setOpen] = useState(false)
  const [viewMode, setViewMode] = useState<"gantt-v2" | "list">("gantt-v2")
  return (
    <div className="border border-border-subtle rounded-lg bg-card">
      <button
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-muted/30 transition-colors"
        onClick={() => setOpen(!open)}
      >
        {open ? (
          <ChevronDown size={14} className="text-muted-foreground" />
        ) : (
          <ChevronRight size={14} className="text-muted-foreground" />
        )}
        <span className="font-mono font-bold text-[13px] w-8">g{day.day_number}</span>
        <span className="text-[11px] font-mono px-1.5 py-0.5 rounded bg-muted/60 text-muted-foreground">
          {day.periodicita}
        </span>
        {day.is_disponibile === 1 ? (
          <span className="text-[11px] text-slate-500 italic">Disponibile</span>
        ) : (
          <span className="text-[11px] font-mono">
            {day.start_time || "—"} – {day.end_time || "—"}
          </span>
        )}
        <div className="ml-auto flex items-center gap-3 text-[11px] font-mono">
          <span title="Lavoro">
            <span className="text-muted-foreground">Lav</span> {fmtHm(day.lavoro_min)}
          </span>
          <span title="Condotta">
            <span className="text-muted-foreground">Cct</span> {fmtHm(day.condotta_min)}
          </span>
          <span title="Km">
            <span className="text-muted-foreground">Km</span> {day.km}
          </span>
          {day.notturno === 1 && (
            <span title="Notturno" className="text-indigo-600">
              <Moon size={11} className="inline" />
            </span>
          )}
          <span title="Riposo successivo">
            <span className="text-muted-foreground">Rip</span> {fmtHm(day.riposo_min)}
          </span>
        </div>
      </button>
      {open && (
        <div className="px-3 pb-3 border-t border-border-subtle pt-2">
          {day.is_disponibile === 1 ? (
            <p className="text-[11px] text-muted-foreground italic text-center py-2">
              Giornata disponibile (riposo / disponibilità)
            </p>
          ) : (
            <>
              {/* Toggle vista */}
              <div className="flex items-center justify-end gap-1 mb-2">
                <button
                  className={cn(
                    "text-[10px] px-2 py-0.5 rounded",
                    viewMode === "gantt-v2"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground"
                  )}
                  onClick={() => setViewMode("gantt-v2")}
                  title="Gantt (MDL-PdC v1.0)"
                >
                  📊 Gantt
                </button>
                <button
                  className={cn(
                    "text-[10px] px-2 py-0.5 rounded",
                    viewMode === "list"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground"
                  )}
                  onClick={() => setViewMode("list")}
                >
                  📋 Lista
                </button>
              </div>
              {viewMode === "gantt-v2" ? (
                <PdcGanttV2
                  blocks={day.blocks}
                  startTime={day.start_time}
                  endTime={day.end_time}
                  label={`g${day.day_number} ${day.periodicita}`}
                />
              ) : (
                <BlocksList blocks={day.blocks} />
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ── Sottocomponente: dettaglio turno ────────────────────────────

function TurnDetail({
  detail,
  onEdit,
  onDelete,
  onDepotView,
}: {
  detail: PdcTurnDetail
  onEdit: () => void
  onDelete: () => void
  onDepotView: () => void
}) {
  const t = detail.turn
  return (
    <div>
      {/* Header */}
      <div className="mb-4 pb-3 border-b border-border-subtle">
        <div className="flex items-center gap-2 mb-1 flex-wrap">
          <h3 className="text-lg font-bold font-mono">{t.codice}</h3>
          <span className="text-[11px] font-mono text-muted-foreground">
            [{t.planning}]
          </span>
          <span className="text-[11px] px-2 py-0.5 rounded bg-primary/10 text-primary">
            {t.profilo}
          </span>
          <div className="ml-auto flex items-center gap-1">
            <button
              onClick={onDepotView}
              className="text-[11px] px-2 py-1 rounded border border-primary/30 text-primary hover:bg-primary/10 flex items-center gap-1"
              title="Vista completa del deposito (tutti i turni + Gantt editabili)"
            >
              <LayoutGrid size={11} /> Vista deposito
            </button>
            <button
              onClick={onEdit}
              className="text-[11px] px-2 py-1 rounded border border-border hover:bg-muted flex items-center gap-1"
              title="Modifica turno"
            >
              <Edit size={11} /> Modifica
            </button>
            <button
              onClick={onDelete}
              className="text-[11px] px-2 py-1 rounded border border-destructive/30 text-destructive hover:bg-destructive/10 flex items-center gap-1"
              title="Elimina turno"
            >
              <Trash2 size={11} /> Elimina
            </button>
          </div>
        </div>
        <div className="flex items-center gap-4 text-[12px] text-muted-foreground">
          <span className="flex items-center gap-1">
            <Building2 size={12} />
            {t.impianto}
          </span>
          <span className="flex items-center gap-1">
            <Calendar size={12} />
            {t.valid_from} → {t.valid_to}
          </span>
        </div>
      </div>

      {/* Giornate */}
      <div className="mb-6">
        <h4 className="text-[13px] font-semibold mb-2">
          Giornate ({detail.days.length})
        </h4>
        <div className="space-y-2">
          {detail.days.map((d, i) => (
            <DayCard key={`${d.id}-${i}`} day={d} />
          ))}
        </div>
      </div>

      {/* Note periodicità */}
      {detail.notes.length > 0 && (
        <div>
          <h4 className="text-[13px] font-semibold mb-2">
            Note periodicità treni ({detail.notes.length})
          </h4>
          <div className="space-y-1 max-h-96 overflow-y-auto border border-border-subtle rounded-lg p-2">
            {detail.notes.map((n) => (
              <details key={n.id} className="text-[11px] border-b border-border-subtle last:border-0 py-1">
                <summary className="cursor-pointer flex items-center gap-2">
                  <span className="font-mono font-semibold">Treno {n.train_id}</span>
                  <span className="text-muted-foreground truncate flex-1">
                    {n.periodicita_text}
                  </span>
                </summary>
                <div className="mt-1 pl-4 text-[10px] font-mono">
                  {n.non_circola_dates.length > 0 && (
                    <p>
                      <span className="text-red-600">Non circola:</span>{" "}
                      {n.non_circola_dates.join(", ")}
                    </p>
                  )}
                  {n.circola_extra_dates.length > 0 && (
                    <p>
                      <span className="text-emerald-600">Circola extra:</span>{" "}
                      {n.circola_extra_dates.join(", ")}
                    </p>
                  )}
                </div>
              </details>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Pagina principale ────────────────────────────────────────────

export function PdcPage() {
  const navigate = useNavigate()
  const [stats, setStats] = useState<PdcStats | null>(null)
  const [turns, setTurns] = useState<PdcTurn[]>([])
  const [impianti, setImpianti] = useState<string[]>([])
  const [filter, setFilter] = useState("")
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<PdcTurnDetail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [error, setError] = useState("")

  const loadTurns = useCallback(async (impianto: string) => {
    try {
      const res = await listPdcTurns(impianto ? { impianto } : {})
      setTurns(res.turns)
      if (res.turns.length > 0 && !selectedId) {
        setSelectedId(res.turns[0].id)
      } else if (res.turns.length === 0) {
        setSelectedId(null)
        setDetail(null)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Errore caricamento turni")
    }
  }, [selectedId])

  // Primo caricamento
  useEffect(() => {
    getPdcStats()
      .then((s) => {
        setStats(s)
        setImpianti(s.impianti || [])
      })
      .catch(() => {})
    loadTurns("")
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Filtro cambia
  useEffect(() => {
    setSelectedId(null)
    loadTurns(filter)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter])

  // Selezione cambia → carica dettaglio
  useEffect(() => {
    if (!selectedId) {
      setDetail(null)
      return
    }
    setLoadingDetail(true)
    getPdcTurn(selectedId)
      .then(setDetail)
      .catch((e) => setError(e instanceof Error ? e.message : "Errore dettaglio"))
      .finally(() => setLoadingDetail(false))
  }, [selectedId])

  const handleEdit = useCallback(() => {
    if (!selectedId) return
    navigate(`/pdc/edit?edit=${selectedId}`)
  }, [selectedId, navigate])

  const handleDelete = useCallback(async () => {
    if (!selectedId || !detail) return
    if (!confirm(`Eliminare il turno ${detail.turn.codice}? L'operazione e' irreversibile.`)) {
      return
    }
    try {
      await deletePdcTurn(selectedId)
      setSelectedId(null)
      setDetail(null)
      loadTurns(filter)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Errore eliminazione")
    }
  }, [selectedId, detail, filter, loadTurns])

  return (
    <div className="h-[calc(100vh-6rem)] flex flex-col">
      {/* Header */}
      <div className="mb-4 flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Turni PdC</h2>
          <p className="text-[13px] text-muted-foreground mt-0.5">
            Turni Posto di Condotta (Trenord / rete RFI)
          </p>
        </div>
        <button
          onClick={() => navigate("/pdc/new")}
          className="text-[12px] px-3 py-2 bg-primary text-primary-foreground rounded hover:bg-primary/90 flex items-center gap-1 font-semibold"
        >
          <Plus size={14} /> Nuovo turno
        </button>
      </div>

      {/* Stats */}
      {stats && stats.loaded && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 mb-4 text-[11px]">
          <div className="bg-muted/40 rounded-md px-3 py-2">
            <p className="text-muted-foreground">Turni</p>
            <p className="font-mono text-[14px] font-semibold">{stats.turni}</p>
          </div>
          <div className="bg-muted/40 rounded-md px-3 py-2">
            <p className="text-muted-foreground">Giornate</p>
            <p className="font-mono text-[14px] font-semibold">{stats.days}</p>
          </div>
          <div className="bg-muted/40 rounded-md px-3 py-2">
            <p className="text-muted-foreground">Blocchi</p>
            <p className="font-mono text-[14px] font-semibold">{stats.blocks}</p>
          </div>
          <div className="bg-muted/40 rounded-md px-3 py-2">
            <p className="text-muted-foreground">Treni</p>
            <p className="font-mono text-[14px] font-semibold">{stats.trains}</p>
          </div>
          <div className="bg-muted/40 rounded-md px-3 py-2">
            <p className="text-muted-foreground">Impianti</p>
            <p className="font-mono text-[14px] font-semibold">{stats.impianti.length}</p>
          </div>
        </div>
      )}

      {error && (
        <div className="text-[12px] text-destructive bg-destructive/10 p-2 rounded mb-3 flex items-center gap-2">
          <Info size={14} />
          {error}
        </div>
      )}

      {/* Split layout */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4 overflow-hidden">
        <div className="border border-border-subtle rounded-lg bg-card overflow-hidden">
          <TurnsList
            turns={turns}
            selectedId={selectedId}
            onSelect={setSelectedId}
            filter={filter}
            onFilter={setFilter}
            impianti={impianti}
          />
        </div>
        <div className="border border-border-subtle rounded-lg bg-card p-4 overflow-y-auto">
          {loadingDetail ? (
            <p className="text-[12px] text-muted-foreground">Caricamento...</p>
          ) : detail ? (
            <TurnDetail
              detail={detail}
              onEdit={handleEdit}
              onDelete={handleDelete}
              onDepotView={() =>
                navigate(`/pdc/depot/${encodeURIComponent(detail.turn.impianto)}`)
              }
            />
          ) : (
            <div className="h-full flex items-center justify-center text-center">
              <div>
                <Train size={40} className="mx-auto text-muted-foreground/40 mb-2" />
                <p className="text-[13px] text-muted-foreground">
                  {turns.length === 0
                    ? "Nessun turno caricato. Vai alla pagina Import per caricare un PDF."
                    : "Seleziona un turno dalla lista a sinistra"}
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
