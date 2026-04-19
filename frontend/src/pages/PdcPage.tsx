import { useState, useEffect, useCallback, useRef } from "react"
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
import {
  TrainDetailDrawer as BlockDetailModal,
  type TrainOccurrenceInTurn,
} from "@/components/TrainDetailDrawer"
// Alias: stesso signature, swap drop-in dal modal centrato al drawer destro
// (refactor handoff Claude Design, vedi docs/HANDOFF-claude-design.md §01).
import {
  getPdcStats,
  listPdcTurns,
  getPdcTurn,
  deletePdcTurn,
  updatePdcTurn,
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

function DayCard({
  day,
  open: externalOpen,
  onToggle,
  ganttId,
  onBlocksChange,
  onCrossDayDragStart,
  onCrossDayDrop,
  allDaysForOccurrences,
  onJumpToDay,
  forceOpenSignal,
}: {
  day: PdcDay
  open?: boolean
  onToggle?: () => void
  ganttId?: string
  onBlocksChange?: (
    changes: Record<number, { start_time?: string; end_time?: string }>,
  ) => void
  onCrossDayDragStart?: (payload: {
    block: PdcBlock
    index: number
  }) => void
  onCrossDayDrop?: (targetGanttId: string) => void
  /**
   * Elenco di tutte le giornate del turno corrente. Usato per calcolare,
   * al momento del click su un blocco treno, le occurrences dello stesso
   * train_id in altre giornate → passate al drawer.
   */
  allDaysForOccurrences?: PdcDay[]
  /**
   * Callback invocato dal drawer quando l'utente clicca "questo treno
   * anche in → g{N}". PdcPage riceve il dayId target e fa scroll+expand.
   */
  onJumpToDay?: (dayId: number) => void
  /**
   * Signal esterno per forzare l'apertura della day card (es. dopo jumpTo).
   * Quando cambia e non e' null e coincide con day.id, la card si apre.
   */
  forceOpenSignal?: number | null
}) {
  // Default: espansa se la giornata NON e' disponibile (ha dati da mostrare)
  const [internalOpen, setInternalOpen] = useState(day.is_disponibile !== 1)
  const open = externalOpen ?? internalOpen
  const toggle = onToggle ?? (() => setInternalOpen((o) => !o))
  const cardRef = useRef<HTMLDivElement>(null)

  // Reagisce al jump: apre la card e la scrolla in vista
  useEffect(() => {
    if (forceOpenSignal != null && forceOpenSignal === day.id) {
      setInternalOpen(true)
      // micro-delay per lasciare che il DOM si espanda prima dello scroll
      const t = setTimeout(() => {
        cardRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })
      }, 60)
      return () => clearTimeout(t)
    }
  }, [forceOpenSignal, day.id])

  // Calcola occurrences dello stesso train_id in altre giornate
  const computeOccurrences = (trainId: string): TrainOccurrenceInTurn[] => {
    if (!allDaysForOccurrences || !trainId) return []
    const occ: TrainOccurrenceInTurn[] = []
    for (const d of allDaysForOccurrences) {
      if (d.id === day.id) continue // escludi la giornata corrente
      for (const b of d.blocks) {
        if (b.block_type === "train" && b.train_id === trainId) {
          occ.push({
            day_id: d.id,
            day_number: d.day_number,
            periodicita: d.periodicita || "",
            block_start: b.start_time || "—",
            block_end: b.end_time || "—",
            from_station: b.from_station || "—",
            to_station: b.to_station || "—",
          })
        }
      }
    }
    return occ
  }
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
      ref={cardRef}
      data-day-id={day.id}
      className="rounded-lg overflow-hidden transition-shadow scroll-mt-24"
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
                  autoFit
                  ganttId={ganttId}
                  onBlocksChange={onBlocksChange}
                  onCrossDayDragStart={
                    onCrossDayDragStart
                      ? (payload) =>
                          onCrossDayDragStart({
                            block: payload.block,
                            index: payload.index,
                          })
                      : undefined
                  }
                  onCrossDayDrop={
                    onCrossDayDrop
                      ? (_payload, targetGanttId) =>
                          onCrossDayDrop(targetGanttId)
                      : undefined
                  }
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
          sameTurnOccurrences={
            detailModal.block.block_type === "train"
              ? computeOccurrences(detailModal.block.train_id || "")
              : undefined
          }
          onJumpToDay={onJumpToDay}
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
  onDetailChange,
  saving,
  dirty,
}: {
  detail: PdcTurnDetail
  onEdit: () => void
  onDelete: () => void
  onDepotView: () => void
  onDetailChange?: (next: PdcTurnDetail) => void
  saving?: boolean
  dirty?: boolean
}) {
  const t = detail.turn
  const totalBlocks = detail.days.reduce((acc, d) => acc + (d.blocks?.length || 0), 0)

  // State per cross-day move (drag da giornata A verso giornata B)
  const [moveState, setMoveState] = useState<{
    sourceDayId: number
    blockIndex: number
    block: PdcBlock
  } | null>(null)

  // In-day drag/resize: aggiorna solo gli orari di blocchi esistenti
  const updateDayBlocks = useCallback(
    (dayId: number, changes: Record<number, { start_time?: string; end_time?: string }>) => {
      if (!onDetailChange) return
      const nextDetail: PdcTurnDetail = {
        ...detail,
        days: detail.days.map((d) => {
          if (d.id !== dayId) return d
          const newBlocks = [...d.blocks]
          for (const [idxStr, patch] of Object.entries(changes)) {
            const idx = parseInt(idxStr)
            newBlocks[idx] = { ...newBlocks[idx], ...patch } as PdcBlock
          }
          return { ...d, blocks: newBlocks }
        }),
      }
      onDetailChange(nextDetail)
    },
    [detail, onDetailChange],
  )

  // Cross-day drop: sposta il blocco (+ CVp/CVa agganciati se treno) dalla
  // giornata sorgente alla giornata target
  const completeMove = useCallback(
    (targetDayId: number) => {
      if (!moveState || !onDetailChange) {
        setMoveState(null)
        return
      }
      if (moveState.sourceDayId === targetDayId) {
        setMoveState(null)
        return
      }

      const src = detail.days.find((d) => d.id === moveState.sourceDayId)
      if (!src) {
        setMoveState(null)
        return
      }

      // Identifica blocchi da spostare (treno + CVp/CVa agganciati)
      const toMoveIdxs = new Set<number>([moveState.blockIndex])
      const b = src.blocks[moveState.blockIndex]
      if (b?.block_type === "train") {
        const p = src.blocks[moveState.blockIndex - 1]
        const n = src.blocks[moveState.blockIndex + 1]
        if (p?.block_type === "cv_partenza") toMoveIdxs.add(moveState.blockIndex - 1)
        if (n?.block_type === "cv_arrivo") toMoveIdxs.add(moveState.blockIndex + 1)
      }
      const movedBlocks = Array.from(toMoveIdxs)
        .sort((a, b) => a - b)
        .map((i) => src.blocks[i])

      const nextDetail: PdcTurnDetail = {
        ...detail,
        days: detail.days.map((d) => {
          if (d.id === moveState.sourceDayId) {
            return {
              ...d,
              blocks: d.blocks
                .filter((_, i) => !toMoveIdxs.has(i))
                .map((bb, i) => ({ ...bb, seq: i })),
            }
          }
          if (d.id === targetDayId) {
            const combined = [...d.blocks, ...movedBlocks]
            combined.sort((a, b) => {
              const sa = (a.start_time || "99:99")
              const sb = (b.start_time || "99:99")
              return sa.localeCompare(sb)
            })
            return {
              ...d,
              blocks: combined.map((bb, i) => ({ ...bb, seq: i })),
            }
          }
          return d
        }),
      }
      onDetailChange(nextDetail)
      setMoveState(null)
    },
    [detail, moveState, onDetailChange],
  )

  const canEdit = !!onDetailChange

  // Jump-to-day signal: quando cambia, la day card target si apre + scrolla
  const [jumpSignal, setJumpSignal] = useState<number | null>(null)
  const handleJumpToDay = useCallback((dayId: number) => {
    // Change signal a un nuovo valore (usa dayId, ma anche lo stesso signal
    // ripetuto deve ri-triggerare → useEffect depende da forceOpenSignal+day.id)
    setJumpSignal(dayId)
  }, [])

  return (
    <div className="flex flex-col h-full">
      {/* ── TOP BAR Editor (stile Stitch header) ─────────────── */}
      <div
        className="sticky top-0 z-10 flex items-center flex-wrap gap-x-6 gap-y-2 px-5 py-3"
        style={{
          backgroundColor: "var(--color-surface-container-lowest)",
          boxShadow: "0 1px 0 var(--color-ghost)",
        }}
      >
        <div className="flex flex-col">
          <span
            className="text-[10px] font-bold uppercase"
            style={{
              color: "var(--color-brand)",
              letterSpacing: "0.12em",
            }}
          >
            Editor Turno
          </span>
          <span
            className="font-extrabold tracking-tight"
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "18px",
              color: "var(--color-on-surface-strong)",
            }}
          >
            {t.codice}
          </span>
        </div>
        <div
          className="h-8 w-px hidden sm:block"
          style={{ backgroundColor: "var(--color-ghost)" }}
        />
        <TopBarField label="Impianto" value={t.impianto} icon={Building2} />
        <TopBarField label="Profilo" value={t.profilo} />
        <TopBarField
          label="Data Validità"
          value={`${t.valid_from} → ${t.valid_to}`}
          icon={Calendar}
          mono
        />
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={onDepotView}
            className="text-[11.5px] font-bold px-3 py-1.5 rounded-md flex items-center gap-1.5 transition-colors"
            style={{
              backgroundColor: "rgba(0, 98, 204, 0.10)",
              color: "var(--color-brand)",
            }}
            onMouseEnter={(e) =>
              (e.currentTarget.style.backgroundColor =
                "rgba(0, 98, 204, 0.18)")
            }
            onMouseLeave={(e) =>
              (e.currentTarget.style.backgroundColor =
                "rgba(0, 98, 204, 0.10)")
            }
            title="Vista completa del deposito (tutti i turni + Gantt editabili)"
          >
            <LayoutGrid size={12} strokeWidth={2} />
            Vista deposito
          </button>
        </div>
      </div>

      {/* ── CANVAS scrollable con Giornate Turno ──────────────── */}
      <div className="flex-1 overflow-y-auto px-5 py-5">
        <div className="flex items-center justify-between mb-5">
          <h2
            className="font-bold tracking-tight"
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "20px",
              letterSpacing: "-0.02em",
              color: "var(--color-on-surface-strong)",
            }}
          >
            Giornate Turno
          </h2>
          <div className="flex items-center gap-2">
            {saving ? (
              <StatusChip tone="brand" label="Salvataggio…" />
            ) : dirty ? (
              <StatusChip tone="brand" label="Modificato" />
            ) : (
              <StatusChip tone="success" label="Sincronizzato" />
            )}
            <StatusChip tone="brand" label={`${totalBlocks} blocchi`} />
          </div>
        </div>

        {/* Hint drag cross-day (visible solo durante un drag attivo) */}
        {moveState && (
          <div
            className="mb-3 px-3 py-2 rounded-md flex items-center gap-3 text-[11.5px]"
            style={{
              backgroundColor: "rgba(0, 98, 204, 0.10)",
              color: "var(--color-brand)",
            }}
          >
            <span className="font-bold uppercase" style={{ letterSpacing: "0.08em" }}>
              Sposta in corso
            </span>
            <span>
              Rilascia il blocco{" "}
              <span style={{ fontFamily: "var(--font-mono)", fontWeight: 700 }}>
                {moveState.block.train_id || moveState.block.vettura_id || "?"}
              </span>{" "}
              su un'altra giornata del turno
            </span>
            <button
              onClick={() => setMoveState(null)}
              className="ml-auto text-[10px] px-2 py-0.5 rounded hover:bg-[rgba(0,98,204,0.18)]"
            >
              Annulla
            </button>
          </div>
        )}

        <div className="space-y-3">
          {detail.days.map((d, i) => (
            <DayCard
              key={`${d.id}-${i}`}
              day={d}
              ganttId={canEdit ? String(d.id) : undefined}
              onBlocksChange={
                canEdit ? (changes) => updateDayBlocks(d.id, changes) : undefined
              }
              onCrossDayDragStart={
                canEdit
                  ? (payload) =>
                      setMoveState({
                        sourceDayId: d.id,
                        blockIndex: payload.index,
                        block: payload.block,
                      })
                  : undefined
              }
              onCrossDayDrop={
                canEdit
                  ? (targetGanttId) => {
                      const targetDayId = parseInt(targetGanttId)
                      if (Number.isFinite(targetDayId)) completeMove(targetDayId)
                    }
                  : undefined
              }
              allDaysForOccurrences={detail.days}
              onJumpToDay={handleJumpToDay}
              forceOpenSignal={jumpSignal}
            />
          ))}
        </div>

        {/* Note periodicita — collassabile */}
        {detail.notes.length > 0 && (
          <div className="mt-6">
            <h4
              className="font-semibold mb-2"
              style={{
                fontFamily: "var(--font-display)",
                fontSize: "13px",
                color: "var(--color-on-surface-strong)",
              }}
            >
              Note periodicità treni
              <span
                className="ml-2 text-[11px] font-normal"
                style={{ color: "var(--color-on-surface-muted)" }}
              >
                ({detail.notes.length})
              </span>
            </h4>
            <div
              className="space-y-0.5 max-h-80 overflow-y-auto rounded-lg p-2"
              style={{ backgroundColor: "var(--color-surface-container-low)" }}
            >
              {detail.notes.map((n) => (
                <details
                  key={n.id}
                  className="text-[11px] rounded p-1.5 transition-colors hover:bg-[var(--color-surface-container-lowest)]"
                >
                  <summary className="cursor-pointer flex items-center gap-2">
                    <span
                      className="font-bold"
                      style={{
                        fontFamily: "var(--font-mono)",
                        color: "var(--color-brand)",
                      }}
                    >
                      Treno {n.train_id}
                    </span>
                    <span
                      className="truncate flex-1"
                      style={{ color: "var(--color-on-surface-muted)" }}
                    >
                      {n.periodicita_text}
                    </span>
                  </summary>
                  <div className="mt-1 pl-4 text-[10px] font-mono">
                    {n.non_circola_dates.length > 0 && (
                      <p>
                        <span style={{ color: "var(--color-destructive)" }}>
                          Non circola:
                        </span>{" "}
                        {n.non_circola_dates.join(", ")}
                      </p>
                    )}
                    {n.circola_extra_dates.length > 0 && (
                      <p>
                        <span style={{ color: "var(--color-success)" }}>
                          Circola extra:
                        </span>{" "}
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

      {/* ── FOOTER sticky (stile Stitch) ───────────────────────── */}
      <div
        className="sticky bottom-0 z-10 flex items-center justify-between gap-4 px-5 py-3"
        style={{
          backgroundColor: "var(--color-surface-container-lowest)",
          boxShadow: "0 -1px 0 var(--color-ghost)",
        }}
      >
        <div className="flex items-center gap-4">
          <button
            onClick={onDelete}
            className="text-[12px] font-semibold px-3 py-1.5 rounded-md flex items-center gap-1.5 transition-colors"
            style={{ color: "var(--color-destructive)" }}
            onMouseEnter={(e) =>
              (e.currentTarget.style.backgroundColor =
                "var(--color-destructive-container)")
            }
            onMouseLeave={(e) =>
              (e.currentTarget.style.backgroundColor = "transparent")
            }
            title="Elimina questo turno"
          >
            <Trash2 size={12} strokeWidth={2} />
            Elimina
          </button>
        </div>
        <div className="flex items-center gap-4">
          {/* Legenda colori */}
          <div
            className="hidden md:flex items-center gap-3 text-[10px] font-semibold"
            style={{ color: "var(--color-on-surface-muted)" }}
          >
            <LegendSwatch color="var(--color-brand)" label="Guida" />
            <LegendSwatch color="#E2E8F0" label="Vuota" />
            <LegendSwatch color="#DCFCE7" label="Refez" />
            <LegendSwatch color="#FFEDD5" label="S.Comp" />
          </div>
          {/* CTA primaria: Modifica turno */}
          <button
            onClick={onEdit}
            className="text-[12px] font-bold px-5 py-2 rounded-md text-white uppercase transition-opacity hover:opacity-90 flex items-center gap-1.5"
            style={{
              background: "var(--gradient-primary)",
              boxShadow: "var(--shadow-sm)",
              letterSpacing: "0.05em",
            }}
            title="Modifica le giornate del turno"
          >
            <Edit size={12} strokeWidth={2} />
            Modifica turno
          </button>
        </div>
      </div>
    </div>
  )
}

function TopBarField({
  label,
  value,
  icon: Icon,
  mono,
}: {
  label: string
  value: string
  icon?: typeof Building2
  mono?: boolean
}) {
  return (
    <div className="flex flex-col">
      <span
        className="text-[10px] font-semibold uppercase flex items-center gap-1"
        style={{
          color: "var(--color-on-surface-muted)",
          letterSpacing: "0.08em",
        }}
      >
        {Icon && <Icon size={10} strokeWidth={2} />}
        {label}
      </span>
      <span
        className="font-semibold"
        style={{
          fontSize: "13px",
          color: "var(--color-on-surface-strong)",
          fontFamily: mono ? "var(--font-mono)" : undefined,
        }}
      >
        {value}
      </span>
    </div>
  )
}

function StatusChip({
  tone,
  label,
}: {
  tone: "brand" | "success"
  label: string
}) {
  const map = {
    brand: {
      bg: "rgba(0, 98, 204, 0.10)",
      fg: "var(--color-brand)",
    },
    success: {
      bg: "var(--color-success-container)",
      fg: "var(--color-success)",
    },
  }[tone]
  return (
    <span
      className="px-2.5 py-1 text-[10px] font-bold uppercase rounded-full"
      style={{
        backgroundColor: map.bg,
        color: map.fg,
        letterSpacing: "0.08em",
      }}
    >
      {label}
    </span>
  )
}

function LegendSwatch({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        aria-hidden="true"
        className="w-2.5 h-2.5 rounded-sm"
        style={{ backgroundColor: color }}
      />
      {label}
    </span>
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
  // Stato salvataggio in-line (auto-save debounced)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const saveTimerRef = useRef<number | null>(null)

  // Persiste il detail corrente sul backend tramite updatePdcTurn
  const persistDetail = useCallback(async (d: PdcTurnDetail) => {
    setSaving(true)
    try {
      await updatePdcTurn(d.turn.id, {
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
      setDirty(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Errore salvataggio")
    } finally {
      setSaving(false)
    }
  }, [])

  // Debounced detail change handler — UI optimistic, backend 1.5s dopo
  const handleDetailChange = useCallback(
    (next: PdcTurnDetail) => {
      setDetail(next)
      setDirty(true)
      if (saveTimerRef.current != null) {
        window.clearTimeout(saveTimerRef.current)
      }
      saveTimerRef.current = window.setTimeout(() => {
        saveTimerRef.current = null
        persistDetail(next)
      }, 1500)
    },
    [persistDetail],
  )

  // Cleanup timer on unmount
  useEffect(
    () => () => {
      if (saveTimerRef.current != null) {
        window.clearTimeout(saveTimerRef.current)
      }
    },
    [],
  )

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
          className="rounded-lg overflow-hidden flex flex-col"
          style={{
            backgroundColor: "var(--color-surface-container-lowest)",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          {loadingDetail ? (
            <div className="flex items-center justify-center flex-1 p-5">
              <p className="text-[12px] text-muted-foreground">Caricamento...</p>
            </div>
          ) : detail ? (
            <TurnDetail
              detail={detail}
              onEdit={handleEdit}
              onDelete={handleDelete}
              onDepotView={() =>
                navigate(`/pdc/depot/${encodeURIComponent(detail.turn.impianto)}`)
              }
              onDetailChange={handleDetailChange}
              saving={saving}
              dirty={dirty}
            />
          ) : (
            <div className="h-full flex items-center justify-center text-center p-5">
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
