import { useState, useEffect, useCallback } from "react"
import {
  CalendarDays,
  MapPin,
  Clock,
  Train,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Trash2,
  Loader2,
  Moon,
  Zap,
  FileText,
} from "lucide-react"
import { cn, fmtMin } from "@/lib/utils"
import {
  getWeeklyShifts,
  deleteWeeklyShift,
  type WeeklyShift,
  type WeeklyDay,
  type DayVariant,
} from "@/lib/api"

// ── Variant card ────────────────────────────────────────────────

function VariantBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    LMXGV: "bg-primary/10 text-primary",
    S: "bg-warning/10 text-warning",
    D: "bg-success/10 text-success",
  }
  return (
    <span
      className={cn(
        "px-1.5 py-0.5 rounded text-[10px] font-semibold",
        colors[type] || "bg-muted text-muted-foreground"
      )}
    >
      {type}
    </span>
  )
}

function VariantRow({ variant }: { variant: DayVariant }) {
  const totalViolations = variant.violations?.length || 0

  return (
    <div className="flex items-center gap-3 px-3 py-2 rounded-lg bg-muted/50 text-[12px]">
      <VariantBadge type={variant.variant_type} />

      <div className="flex items-center gap-1 text-muted-foreground">
        <Train size={11} />
        <span className="font-mono">{variant.train_ids.length}</span>
      </div>

      <div className="flex items-center gap-1 text-muted-foreground">
        <Clock size={11} />
        <span className="font-mono">{fmtMin(variant.prestazione_min)}</span>
      </div>

      <div className="flex items-center gap-1 text-primary">
        <span className="font-mono text-[11px]">{fmtMin(variant.condotta_min)}</span>
        <span className="text-[10px] text-muted-foreground">cct</span>
      </div>

      {variant.is_fr && (
        <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-500 text-[10px] font-medium">
          <Moon size={9} />
          FR
        </span>
      )}

      {variant.is_scomp && (
        <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-info/10 text-info text-[10px] font-medium">
          <Zap size={9} />
          S.COMP {variant.scomp_duration_min > 0 && `${fmtMin(variant.scomp_duration_min)}`}
        </span>
      )}

      {totalViolations > 0 && (
        <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-destructive/10 text-destructive text-[10px] font-medium">
          <AlertTriangle size={9} />
          {totalViolations}
        </span>
      )}

      {/* Train IDs on the right */}
      <div className="ml-auto flex flex-wrap gap-1 max-w-[300px] justify-end">
        {variant.train_ids.slice(0, 6).map((tid) => (
          <span
            key={tid}
            className="px-1 py-0.5 rounded bg-card text-[10px] font-mono text-muted-foreground border border-border-subtle"
          >
            {tid}
          </span>
        ))}
        {variant.train_ids.length > 6 && (
          <span className="text-[10px] text-muted-foreground">
            +{variant.train_ids.length - 6}
          </span>
        )}
      </div>
    </div>
  )
}

// ── Day card ────────────────────────────────────────────────────

function DayCard({ day }: { day: WeeklyDay }) {
  return (
    <div className="space-y-1.5">
      <p className="text-[11px] font-semibold text-muted-foreground">
        Giorno {day.day_number}
      </p>
      {day.variants.map((v) => (
        <VariantRow key={v.id} variant={v} />
      ))}
    </div>
  )
}

// ── Weekly shift card ───────────────────────────────────────────

function WeeklyShiftCard({
  shift,
  onDelete,
}: {
  shift: WeeklyShift
  onDelete: (id: number) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const days = (shift.days || []) as WeeklyDay[]
  const totalVariants = days.reduce((sum, d) => sum + d.variants.length, 0)
  const totalViolations = days.reduce(
    (sum, d) =>
      sum + d.variants.reduce((vs, v) => vs + (v.violations?.length || 0), 0),
    0
  )

  return (
    <div
      className="rounded-lg transition-shadow hover:shadow-md"
      style={{
        backgroundColor: "var(--color-surface-container-lowest)",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      {/* Header */}
      <button
        onClick={() => setExpanded((p) => !p)}
        className="w-full text-left px-4 py-3 flex items-center gap-3"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[13px] font-medium truncate">{shift.name}</span>
            {totalViolations > 0 && (
              <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-destructive/10 text-destructive text-[10px] font-medium">
                <AlertTriangle size={10} />
                {totalViolations}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
            <span className="flex items-center gap-1">
              <MapPin size={10} />
              {shift.deposito || "—"}
            </span>
            <span className="flex items-center gap-1">
              <CalendarDays size={10} />
              {shift.num_days} giorni
            </span>
            <span className="flex items-center gap-1">
              <FileText size={10} />
              {totalVariants} varianti
            </span>
            {shift.notes && (
              <span className="truncate max-w-[200px] italic">{shift.notes}</span>
            )}
          </div>
        </div>

        {/* Right stats */}
        <div className="flex items-center gap-4 shrink-0">
          <div className="text-right">
            <p className="text-[12px] font-mono font-medium">
              {fmtMin(shift.weekly_prestazione_min)}
            </p>
            <p className="text-[10px] text-muted-foreground">Sett.</p>
          </div>
          <div className="text-right">
            <p className="text-[12px] font-mono font-medium text-primary">
              {fmtMin(shift.weekly_condotta_min)}
            </p>
            <p className="text-[10px] text-muted-foreground">Cct sett.</p>
          </div>
          <div className="text-right hidden lg:block">
            <p className="text-[12px] font-mono">
              {shift.weighted_hours_per_day
                ? `${shift.weighted_hours_per_day.toFixed(1)}h`
                : "—"}
            </p>
            <p className="text-[10px] text-muted-foreground">Media/g</p>
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
          {days.length === 0 ? (
            <p className="text-[12px] text-muted-foreground py-2">
              Nessuna variante giornaliera
            </p>
          ) : (
            <div className="space-y-3">
              {days.map((day) => (
                <DayCard key={day.day_number} day={day} />
              ))}
            </div>
          )}

          {/* Violations summary */}
          {totalViolations > 0 && (
            <div className="space-y-1">
              <p className="text-[11px] text-destructive font-medium">
                Violazioni ({totalViolations})
              </p>
              {days.flatMap((d) =>
                d.variants.flatMap((v) =>
                  (v.violations || []).map((viol, i) => (
                    <div
                      key={`${v.id}-${i}`}
                      className="flex items-start gap-2 text-[11px] text-destructive/80 bg-destructive/5 px-2 py-1.5 rounded"
                    >
                      <AlertTriangle size={12} className="shrink-0 mt-0.5" />
                      <span>
                        G{v.day_number} {v.variant_type}: {viol.message}
                      </span>
                    </div>
                  ))
                )
              )}
            </div>
          )}

          {/* Delete */}
          <div className="flex justify-end pt-2 border-t border-border-subtle">
            {confirmDelete ? (
              <div className="flex items-center gap-2 text-[12px]">
                <span className="text-muted-foreground">Eliminare questo turno settimanale?</span>
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

// ── Main page ───────────────────────────────────────────────────

export function CalendarPage() {
  const [shifts, setShifts] = useState<WeeklyShift[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  const fetchShifts = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const data = await getWeeklyShifts()
      setShifts(data.shifts)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Errore caricamento turni settimanali")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchShifts()
  }, [fetchShifts])

  const handleDelete = useCallback(async (id: number) => {
    try {
      await deleteWeeklyShift(id)
      setShifts((prev) => prev.filter((s) => s.id !== id))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Errore eliminazione")
    }
  }, [])

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Calendario turni</h2>
          <p className="text-[13px] text-muted-foreground mt-0.5">
            {shifts.length} turni settimanali
          </p>
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
            <CalendarDays size={20} className="text-muted-foreground" />
          </div>
          <p className="text-[13px] text-muted-foreground">
            Nessun turno settimanale salvato
          </p>
          <p className="text-[11px] text-muted-foreground mt-1">
            Usa il builder automatico per generare turni settimanali
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {shifts.map((shift) => (
            <WeeklyShiftCard key={shift.id} shift={shift} onDelete={handleDelete} />
          ))}
        </div>
      )}
    </div>
  )
}
