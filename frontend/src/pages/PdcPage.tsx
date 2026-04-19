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
  ChevronDown,
  Info,
  Plus,
  Edit,
  Trash2,
  LayoutGrid,
  BarChart3,
  List as ListIcon,
  MoreVertical,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { PdcGanttV2 } from "@/components/PdcGanttV2"
import { TrainDetailDrawer as BlockDetailModal } from "@/components/TrainDetailDrawer"
// Alias: stesso signature, swap drop-in dal modal centrato al drawer destro
// (refactor handoff Claude Design, vedi docs/HANDOFF-claude-design.md §01).
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
      <div
        className="px-3 py-2.5"
        style={{ backgroundColor: "var(--color-surface-container-low)" }}
      >
        <select
          className="w-full text-[12px] px-2 py-1.5 rounded-md outline-none"
          value={filter}
          onChange={(e) => onFilter(e.target.value)}
          style={{
            backgroundColor: "var(--color-surface-container-lowest)",
            color: "var(--color-on-surface)",
            boxShadow: "inset 0 0 0 1px var(--color-ghost)",
          }}
        >
          <option value="">Tutti gli impianti ({turns.length})</option>
          {impianti.map((i) => (
            <option key={i} value={i}>{i}</option>
          ))}
        </select>
      </div>
      <div className="overflow-y-auto flex-1 p-1.5 space-y-0.5">
        {turns.length === 0 ? (
          <p
            className="p-4 text-[12px] text-center"
            style={{ color: "var(--color-on-surface-muted)" }}
          >
            Nessun turno caricato. Carica un PDF da <b>Import</b>.
          </p>
        ) : (
          turns.map((t) => {
            const isSel = selectedId === t.id
            return (
              <button
                key={t.id}
                onClick={() => onSelect(t.id)}
                className="relative w-full text-left px-2.5 py-2 rounded-md transition-colors text-[12px]"
                style={{
                  backgroundColor: isSel
                    ? "var(--color-surface-container-high)"
                    : "transparent",
                  color: isSel
                    ? "var(--color-on-surface-strong)"
                    : "var(--color-on-surface)",
                }}
                onMouseEnter={(e) => {
                  if (!isSel)
                    e.currentTarget.style.backgroundColor =
                      "var(--color-surface-container-low)"
                }}
                onMouseLeave={(e) => {
                  if (!isSel) e.currentTarget.style.backgroundColor = "transparent"
                }}
              >
                {isSel && (
                  <span
                    aria-hidden="true"
                    className="absolute left-0.5 top-1/2 -translate-y-1/2 h-5 w-0.5 rounded-full"
                    style={{ backgroundColor: "var(--color-dot)" }}
                  />
                )}
                <div
                  className="font-bold"
                  style={{
                    fontFamily: "var(--font-mono)",
                    color: isSel
                      ? "var(--color-brand)"
                      : "var(--color-on-surface-strong)",
                  }}
                >
                  {t.codice}
                </div>
                <div
                  className="text-[11px] truncate mt-0.5"
                  style={{ color: "var(--color-on-surface-muted)" }}
                >
                  {t.impianto}
                </div>
              </button>
            )
          })
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

// ── Sottocomponente: giornata espandibile (stile Stitch editor) ──

function dayTitleSubtitle(day: PdcDay): { title: string; subtitle: string } {
  const periodBadge = day.periodicita ? ` · ${day.periodicita}` : ""
  const title = `Giornata ${day.day_number}${periodBadge}`

  if (day.is_disponibile === 1) {
    return { title, subtitle: "Giornata di disponibilità · riposo" }
  }
  if (day.notturno === 1) {
    return {
      title,
      subtitle: `Turno notturno · ${day.start_time || "—"} – ${day.end_time || "—"}`,
    }
  }
  const p = day.periodicita || ""
  let kind = "Servizio ordinario"
  if (p === "S" || p === "SD") kind = "Servizio festivo ridotto"
  else if (p === "D") kind = "Servizio domenica / festività"
  else if (p.includes("L") || p.includes("M") || p.includes("V")) kind = "Servizio feriale"
  return {
    title,
    subtitle: `${kind} · ${day.start_time || "—"} – ${day.end_time || "—"}`,
  }
}

function DayCard({ day, open: externalOpen, onToggle }: {
  day: PdcDay
  open?: boolean
  onToggle?: () => void
}) {
  const [internalOpen, setInternalOpen] = useState(false)
  const open = externalOpen ?? internalOpen
  const toggle = onToggle ?? (() => setInternalOpen((o) => !o))
  const [viewMode, setViewMode] = useState<"gantt-v2" | "list">("gantt-v2")
  const [detailModal, setDetailModal] = useState<{
    block: PdcBlock
    index: number
    mode: "detail" | "warn"
  } | null>(null)

  const { title, subtitle } = dayTitleSubtitle(day)
  const durata = day.is_disponibile === 1 ? "—" : fmtHm(day.lavoro_min)

  return (
    <div
      className="rounded-lg overflow-hidden transition-shadow"
      style={{
        backgroundColor: "var(--color-surface-container-lowest)",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      <button
        type="button"
        className="w-full flex items-center gap-4 px-4 py-3 transition-colors hover:bg-[var(--color-surface-container-low)] text-left"
        onClick={toggle}
      >
        {/* Chevron expand */}
        <span
          className="shrink-0 transition-transform"
          style={{
            color: "var(--color-on-surface-muted)",
            transform: open ? "rotate(0deg)" : "rotate(-90deg)",
          }}
        >
          <ChevronDown size={16} strokeWidth={2} />
        </span>

        {/* Title + subtitle (stile Stitch) */}
        <div className="min-w-0 flex-1">
          <div
            className="font-bold truncate"
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "14px",
              color: "var(--color-on-surface-strong)",
              letterSpacing: "-0.01em",
            }}
          >
            {title}
            {day.notturno === 1 && (
              <Moon
                size={12}
                className="inline-block ml-2 -mt-0.5"
                style={{ color: "var(--color-brand)" }}
              />
            )}
          </div>
          <div
            className="text-[11px] truncate mt-0.5"
            style={{ color: "var(--color-on-surface-muted)" }}
          >
            {subtitle}
          </div>
        </div>

        {/* Metrics strip (dispatcher data) */}
        {day.is_disponibile !== 1 && (
          <div className="shrink-0 hidden md:flex items-center gap-4 text-[11px]">
            <MetricInline label="Cct" value={fmtHm(day.condotta_min)} />
            <MetricInline label="Km" value={day.km ? String(day.km) : "—"} />
            <MetricInline label="Rip" value={fmtHm(day.riposo_min)} />
          </div>
        )}

        {/* Durata totale (Stitch style) */}
        <div className="shrink-0 text-right">
          <div
            className="text-[9.5px] font-bold uppercase"
            style={{
              color: "var(--color-on-surface-quiet)",
              letterSpacing: "0.12em",
            }}
          >
            Durata totale
          </div>
          <div
            className="font-bold"
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "15px",
              color: "var(--color-on-surface-strong)",
            }}
          >
            {durata}
          </div>
        </div>

        {/* Menu ⋮ (rimpiazza l'action bar 8-icone del Gantt) */}
        <span
          className="p-1 rounded hover:bg-[var(--color-surface-container)]"
          style={{ color: "var(--color-on-surface-quiet)" }}
          onClick={(e) => e.stopPropagation()}
          title="Opzioni giornata"
        >
          <MoreVertical size={15} />
        </span>
      </button>

      {open && (
        <div
          className="px-4 pb-4 pt-3"
          style={{ backgroundColor: "var(--color-surface-container-low)" }}
        >
          {day.is_disponibile === 1 ? (
            <div
              className="text-[12px] italic text-center py-4"
              style={{ color: "var(--color-on-surface-muted)" }}
            >
              Giornata di disponibilità — nessun servizio programmato
            </div>
          ) : (
            <>
              {/* Toggle vista (icone lucide al posto degli emoji) */}
              <div className="flex items-center justify-end gap-1 mb-3">
                <ViewToggle
                  active={viewMode === "gantt-v2"}
                  onClick={() => setViewMode("gantt-v2")}
                  icon={BarChart3}
                  label="Gantt"
                />
                <ViewToggle
                  active={viewMode === "list"}
                  onClick={() => setViewMode("list")}
                  icon={ListIcon}
                  label="Lista"
                />
              </div>
              {viewMode === "gantt-v2" ? (
                <PdcGanttV2
                  blocks={day.blocks}
                  startTime={day.start_time}
                  endTime={day.end_time}
                  label={`g${day.day_number} ${day.periodicita}`}
                  hideActionBar
                  onBlockClick={(block, idx) => {
                    setDetailModal({ block, index: idx, mode: "detail" })
                  }}
                  onAction={(act, block, idx) => {
                    if (act === "detail" || act === "warn") {
                      setDetailModal({ block, index: idx, mode: act })
                    } else if (act === "history") {
                      setDetailModal({ block, index: idx, mode: "detail" })
                    }
                  }}
                />
              ) : (
                <BlocksList blocks={day.blocks} />
              )}
            </>
          )}
        </div>
      )}

      {detailModal && (
        <BlockDetailModal
          block={detailModal.block}
          index={detailModal.index}
          mode={detailModal.mode}
          onClose={() => setDetailModal(null)}
        />
      )}
    </div>
  )
}

function MetricInline({ label, value }: { label: string; value: string }) {
  return (
    <span
      className="inline-flex items-center gap-1"
      style={{ fontFamily: "var(--font-mono)" }}
    >
      <span
        className="text-[9.5px] font-bold uppercase"
        style={{
          color: "var(--color-on-surface-quiet)",
          letterSpacing: "0.08em",
        }}
      >
        {label}
      </span>
      <span style={{ color: "var(--color-on-surface-strong)", fontWeight: 600 }}>
        {value}
      </span>
    </span>
  )
}

function ViewToggle({
  active,
  onClick,
  icon: Icon,
  label,
}: {
  active: boolean
  onClick: () => void
  icon: typeof BarChart3
  label: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded transition-colors"
      style={{
        backgroundColor: active
          ? "var(--color-brand)"
          : "var(--color-surface-container)",
        color: active ? "#ffffff" : "var(--color-on-surface-muted)",
      }}
    >
      <Icon size={11} strokeWidth={2} />
      {label}
    </button>
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
      <div
        className="mb-4 pb-3"
        style={{ boxShadow: "inset 0 -1px 0 var(--color-ghost)" }}
      >
        <div
          className="text-[10px] font-bold uppercase mb-1"
          style={{
            color: "var(--color-on-surface-quiet)",
            letterSpacing: "0.12em",
          }}
        >
          Turno PdC
        </div>
        <div className="flex items-center gap-2 mb-1 flex-wrap">
          <h3
            className="text-lg font-bold"
            style={{
              fontFamily: "var(--font-mono)",
              color: "var(--color-on-surface-strong)",
            }}
          >
            {t.codice}
          </h3>
          <span
            className="text-[11px]"
            style={{
              fontFamily: "var(--font-mono)",
              color: "var(--color-on-surface-muted)",
            }}
          >
            [{t.planning}]
          </span>
          <span
            className="text-[11px] px-2 py-0.5 rounded font-semibold"
            style={{
              backgroundColor: "rgba(0, 98, 204, 0.10)",
              color: "var(--color-brand)",
            }}
          >
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
          <div
            className="space-y-0.5 max-h-96 overflow-y-auto rounded-lg p-2"
            style={{ backgroundColor: "var(--color-surface-container-low)" }}
          >
            {detail.notes.map((n) => (
              <details
                key={n.id}
                className="text-[11px] rounded p-1.5 transition-colors hover:bg-[var(--color-surface-container-lowest)]"
              >
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
      <div className="mb-5 flex items-start justify-between">
        <div>
          <div
            className="text-[10px] font-bold uppercase mb-1"
            style={{
              color: "var(--color-on-surface-quiet)",
              letterSpacing: "0.12em",
            }}
          >
            Turni PdC
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
            Personale di Condotta
          </h2>
          <p
            className="text-[13px] mt-0.5"
            style={{ color: "var(--color-on-surface-muted)" }}
          >
            Turni Posto di Condotta (Trenord / rete RFI)
          </p>
        </div>
        <button
          onClick={() => navigate("/pdc/new")}
          className="text-[12.5px] px-3.5 py-2 rounded-md text-white flex items-center gap-1.5 font-semibold transition-opacity hover:opacity-90"
          style={{
            background: "var(--gradient-primary)",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          <Plus size={14} /> Nuovo turno
        </button>
      </div>

      {/* Stats — KPI style */}
      {stats && stats.loaded && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-4">
          {[
            { label: "Turni", value: stats.turni },
            { label: "Giornate", value: stats.days },
            { label: "Blocchi", value: stats.blocks },
            { label: "Treni", value: stats.trains },
            { label: "Impianti", value: stats.impianti.length },
          ].map((k) => (
            <div
              key={k.label}
              className="rounded-lg px-3.5 py-2.5"
              style={{
                backgroundColor: "var(--color-surface-container-lowest)",
                boxShadow: "var(--shadow-sm)",
              }}
            >
              <div
                className="text-[9.5px] font-bold uppercase"
                style={{
                  color: "var(--color-on-surface-muted)",
                  letterSpacing: "0.1em",
                }}
              >
                {k.label}
              </div>
              <div
                className="mt-1 leading-none"
                style={{
                  fontFamily: "var(--font-display)",
                  fontSize: "22px",
                  fontWeight: 700,
                  color: "var(--color-on-surface-strong)",
                  letterSpacing: "-0.02em",
                }}
              >
                {k.value}
              </div>
            </div>
          ))}
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
        <div
          className="rounded-lg overflow-hidden"
          style={{
            backgroundColor: "var(--color-surface-container-lowest)",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          <TurnsList
            turns={turns}
            selectedId={selectedId}
            onSelect={setSelectedId}
            filter={filter}
            onFilter={setFilter}
            impianti={impianti}
          />
        </div>
        <div
          className="rounded-lg p-5 overflow-y-auto"
          style={{
            backgroundColor: "var(--color-surface-container-lowest)",
            boxShadow: "var(--shadow-sm)",
          }}
        >
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
