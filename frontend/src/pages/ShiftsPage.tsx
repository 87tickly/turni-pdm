import { useState, useEffect, useCallback } from "react"
import {
  ClipboardList,
  Clock,
  MapPin,
  Train,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Trash2,
  Loader2,
  Moon,
  Calendar,
} from "lucide-react"
import { cn, fmtMin } from "@/lib/utils"
import {
  getSavedShifts,
  deleteSavedShift,
  getShiftTimeline,
  type SavedShift,
  type ShiftTimeline,
  type TimelineBlock,
} from "@/lib/api"

// ── Timeline bar component ───────────────────────────────────────

const BLOCK_COLORS: Record<string, string> = {
  extra: "bg-zinc-700",
  accessori: "bg-zinc-600",
  train: "bg-primary",
  deadhead: "bg-amber-600",
  attesa: "bg-zinc-800 border border-border-subtle",
  meal: "bg-emerald-600",
  spostamento: "bg-cyan-600",
  giro_return: "bg-violet-600",
}

function TimelineBar({ blocks }: { blocks: TimelineBlock[] }) {
  if (!blocks.length) return null

  const minStart = Math.min(...blocks.map((b) => b.start))
  const maxEnd = Math.max(...blocks.map((b) => b.end))
  const totalSpan = maxEnd - minStart
  if (totalSpan <= 0) return null

  return (
    <div className="space-y-2">
      {/* Visual bar */}
      <div className="relative h-8 bg-muted rounded-md overflow-hidden">
        {blocks.map((block, i) => {
          const left = ((block.start - minStart) / totalSpan) * 100
          const width = ((block.end - block.start) / totalSpan) * 100
          if (width < 0.3) return null
          return (
            <div
              key={i}
              className={cn(
                "absolute top-0 h-full transition-opacity hover:opacity-80",
                BLOCK_COLORS[block.type] || "bg-zinc-500"
              )}
              style={{ left: `${left}%`, width: `${Math.max(width, 0.5)}%` }}
              title={`${block.label} ${block.start_time}–${block.end_time} (${block.duration}min)`}
            />
          )
        })}
      </div>

      {/* Time markers */}
      <div className="flex justify-between text-[10px] text-muted-foreground font-mono px-0.5">
        <span>{blocks[0]?.start_time}</span>
        <span>{blocks[blocks.length - 1]?.end_time}</span>
      </div>
    </div>
  )
}

// ── Timeline detail list ─────────────────────────────────────────

function TimelineDetail({ blocks }: { blocks: TimelineBlock[] }) {
  return (
    <div className="space-y-0.5">
      {blocks.map((block, i) => (
        <div
          key={i}
          className="grid grid-cols-[8px_1fr_60px_60px_50px] items-center gap-2 py-1 px-2 text-[12px] hover:bg-muted/30 rounded"
        >
          {/* Color dot */}
          <div
            className={cn(
              "w-2 h-2 rounded-full",
              BLOCK_COLORS[block.type]?.replace("bg-", "bg-") || "bg-zinc-500"
            )}
          />

          {/* Label */}
          <div className="truncate">
            <span className="font-medium">{block.label}</span>
            {block.detail && (
              <span className="text-muted-foreground ml-1.5">{block.detail}</span>
            )}
          </div>

          {/* Times */}
          <span className="font-mono text-right text-muted-foreground text-[11px]">
            {block.start_time}
          </span>
          <span className="font-mono text-right text-[11px]">
            {block.end_time}
          </span>

          {/* Duration */}
          <span className="text-right text-[11px] text-muted-foreground">
            {block.duration}m
          </span>
        </div>
      ))}
    </div>
  )
}

// ── Legend ────────────────────────────────────────────────────────

function TimelineLegend() {
  const items = [
    { color: "bg-primary", label: "Treno" },
    { color: "bg-amber-600", label: "Vettura" },
    { color: "bg-emerald-600", label: "Refezione" },
    { color: "bg-zinc-600", label: "Accessori" },
    { color: "bg-zinc-700", label: "Extra" },
    { color: "bg-cyan-600", label: "Spostamento" },
    { color: "bg-violet-600", label: "Giro mat." },
  ]
  return (
    <div className="flex flex-wrap gap-3 text-[10px] text-muted-foreground">
      {items.map(({ color, label }) => (
        <div key={label} className="flex items-center gap-1">
          <div className={cn("w-2.5 h-2.5 rounded-sm", color)} />
          {label}
        </div>
      ))}
    </div>
  )
}

// ── Shift card ───────────────────────────────────────────────────

function ShiftCard({
  shift,
  onDelete,
}: {
  shift: SavedShift
  onDelete: (id: number) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [timeline, setTimeline] = useState<ShiftTimeline | null>(null)
  const [loadingTl, setLoadingTl] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const trainIds = typeof shift.train_ids === "string" ? JSON.parse(shift.train_ids) : shift.train_ids
  const violations = typeof shift.violations === "string" ? JSON.parse(shift.violations) : shift.violations
  const isFr = shift.is_fr === 1 || shift.is_fr === true

  const handleExpand = useCallback(async () => {
    if (expanded) {
      setExpanded(false)
      return
    }
    setExpanded(true)
    if (!timeline) {
      setLoadingTl(true)
      try {
        const tl = await getShiftTimeline(shift.id)
        setTimeline(tl)
      } catch {
        // silently fail — show card without timeline
      } finally {
        setLoadingTl(false)
      }
    }
  }, [expanded, timeline, shift.id])

  return (
    <div className="bg-card rounded-lg border border-border-subtle hover:border-border transition-colors">
      {/* Header */}
      <button
        onClick={handleExpand}
        className="w-full text-left px-4 py-3 flex items-center gap-3"
      >
        {/* Left info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[13px] font-medium truncate">{shift.name}</span>
            {isFr && (
              <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-400 text-[10px] font-medium">
                <Moon size={10} />
                FR
              </span>
            )}
            {violations.length > 0 && (
              <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-destructive/10 text-destructive text-[10px] font-medium">
                <AlertTriangle size={10} />
                {violations.length}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
            <span className="flex items-center gap-1">
              <MapPin size={10} />
              {shift.deposito || "—"}
            </span>
            <span className="flex items-center gap-1">
              <Calendar size={10} />
              {shift.day_type}
            </span>
            <span className="flex items-center gap-1">
              <Train size={10} />
              {trainIds.length} treni
            </span>
          </div>
        </div>

        {/* Right stats */}
        <div className="flex items-center gap-4 shrink-0">
          <div className="text-right">
            <p className="text-[12px] font-mono font-medium">
              {fmtMin(shift.prestazione_min)}
            </p>
            <p className="text-[10px] text-muted-foreground">Prestazione</p>
          </div>
          <div className="text-right">
            <p className="text-[12px] font-mono font-medium text-primary">
              {fmtMin(shift.condotta_min)}
            </p>
            <p className="text-[10px] text-muted-foreground">Condotta</p>
          </div>
          <div className="text-right hidden lg:block">
            <p className="text-[12px] font-mono">
              {shift.presentation_time || "—"}
            </p>
            <p className="text-[10px] text-muted-foreground">Inizio</p>
          </div>
          <div className="text-right hidden lg:block">
            <p className="text-[12px] font-mono">
              {shift.end_time || "—"}
            </p>
            <p className="text-[10px] text-muted-foreground">Fine</p>
          </div>
          {expanded ? (
            <ChevronUp size={16} className="text-muted-foreground" />
          ) : (
            <ChevronDown size={16} className="text-muted-foreground" />
          )}
        </div>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-border-subtle space-y-4 pt-3">
          {/* Train IDs */}
          <div className="flex flex-wrap gap-1">
            {trainIds.map((tid: string) => (
              <span
                key={tid}
                className="px-1.5 py-0.5 rounded bg-muted text-[11px] font-mono text-muted-foreground"
              >
                {tid}
              </span>
            ))}
          </div>

          {/* Timeline */}
          {loadingTl ? (
            <div className="flex items-center justify-center py-4">
              <Loader2 size={16} className="animate-spin text-muted-foreground" />
            </div>
          ) : timeline ? (
            <>
              <TimelineBar blocks={timeline.timeline} />
              <TimelineDetail blocks={timeline.timeline} />
              <TimelineLegend />

              {/* Violations */}
              {timeline.violations.length > 0 && (
                <div className="space-y-1">
                  <p className="text-[11px] text-destructive font-medium">
                    Violazioni ({timeline.violations.length})
                  </p>
                  {timeline.violations.map((v, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-2 text-[11px] text-destructive/80 bg-destructive/5 px-2 py-1.5 rounded"
                    >
                      <AlertTriangle size={12} className="shrink-0 mt-0.5" />
                      <span>{v.message}</span>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : null}

          {/* Actions */}
          <div className="flex justify-end pt-2 border-t border-border-subtle">
            {confirmDelete ? (
              <div className="flex items-center gap-2 text-[12px]">
                <span className="text-muted-foreground">Eliminare questo turno?</span>
                <button
                  onClick={() => onDelete(shift.id)}
                  className="px-2 py-1 bg-destructive text-destructive-foreground rounded text-[11px] font-medium hover:opacity-90"
                >
                  Elimina
                </button>
                <button
                  onClick={() => setConfirmDelete(false)}
                  className="px-2 py-1 bg-muted text-muted-foreground rounded text-[11px] hover:text-foreground"
                >
                  Annulla
                </button>
              </div>
            ) : (
              <button
                onClick={() => setConfirmDelete(true)}
                className="flex items-center gap-1 px-2 py-1 text-[11px] text-muted-foreground hover:text-destructive transition-colors"
              >
                <Trash2 size={12} />
                Elimina
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main page ────────────────────────────────────────────────────

export function ShiftsPage() {
  const [shifts, setShifts] = useState<SavedShift[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [filterDayType, setFilterDayType] = useState<string>("")

  const fetchShifts = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const data = await getSavedShifts(filterDayType || undefined)
      setShifts(data.shifts)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Errore caricamento turni")
    } finally {
      setLoading(false)
    }
  }, [filterDayType])

  useEffect(() => {
    fetchShifts()
  }, [fetchShifts])

  const handleDelete = useCallback(
    async (id: number) => {
      try {
        await deleteSavedShift(id)
        setShifts((prev) => prev.filter((s) => s.id !== id))
      } catch (e) {
        setError(e instanceof Error ? e.message : "Errore eliminazione")
      }
    },
    []
  )

  const dayTypes = ["", "LV", "SAB", "DOM"]

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Turni salvati</h2>
          <p className="text-[13px] text-muted-foreground mt-0.5">
            {shifts.length} turni giornalieri
          </p>
        </div>

        {/* Day type filter */}
        <div className="flex gap-1 bg-muted p-1 rounded-lg">
          {dayTypes.map((dt) => (
            <button
              key={dt}
              onClick={() => setFilterDayType(dt)}
              className={cn(
                "px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors",
                filterDayType === dt
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {dt || "Tutti"}
            </button>
          ))}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 bg-destructive/10 text-destructive text-[12px] p-3 rounded-lg border border-destructive/20 mb-4">
          <AlertTriangle size={14} />
          {error}
        </div>
      )}

      {/* Loading */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 size={20} className="animate-spin text-muted-foreground" />
        </div>
      ) : shifts.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16">
          <div className="w-12 h-12 rounded-xl bg-muted flex items-center justify-center mb-4">
            <ClipboardList size={20} className="text-muted-foreground" />
          </div>
          <p className="text-[13px] text-muted-foreground">
            Nessun turno salvato
          </p>
          <p className="text-[11px] text-muted-foreground mt-1">
            I turni creati dal builder appariranno qui
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {shifts.map((shift) => (
            <ShiftCard key={shift.id} shift={shift} onDelete={handleDelete} />
          ))}
        </div>
      )}
    </div>
  )
}
