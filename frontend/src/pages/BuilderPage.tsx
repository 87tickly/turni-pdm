import { useState, useEffect, useCallback } from "react"
import {
  Plus,
  X,
  Search,
  Save,
  Loader2,
  AlertTriangle,
  CheckCircle,
  Train,
  MapPin,
  Clock,
  ArrowRight,
  Moon,
  ChevronDown,
} from "lucide-react"
import { cn, fmtMin } from "@/lib/utils"
import {
  getConstants,
  queryTrain,
  getConnections,
  validateDayWithTimeline,
  saveShift,
  type AppConstants,
  type TrainSegment,
  type ValidateDayResult,
  type TimelineBlock,
  type Violation,
} from "@/lib/api"

// ── Timeline bar (reused from ShiftsPage pattern) ────────────────

const BLOCK_COLORS: Record<string, string> = {
  extra: "bg-zinc-700",
  accessori: "bg-zinc-600",
  train: "bg-primary",
  deadhead: "bg-amber-600",
  attesa: "bg-zinc-800",
  meal: "bg-emerald-600",
  spostamento: "bg-cyan-600",
  giro_return: "bg-violet-600",
}

function MiniTimeline({ blocks }: { blocks: TimelineBlock[] }) {
  if (!blocks.length) return null
  const minStart = Math.min(...blocks.map((b) => b.start))
  const maxEnd = Math.max(...blocks.map((b) => b.end))
  const span = maxEnd - minStart
  if (span <= 0) return null

  return (
    <div className="space-y-1.5">
      <div className="relative h-6 bg-muted rounded overflow-hidden">
        {blocks.map((b, i) => {
          const left = ((b.start - minStart) / span) * 100
          const w = ((b.end - b.start) / span) * 100
          if (w < 0.3) return null
          return (
            <div
              key={i}
              className={cn("absolute top-0 h-full", BLOCK_COLORS[b.type] || "bg-zinc-500")}
              style={{ left: `${left}%`, width: `${Math.max(w, 0.5)}%` }}
              title={`${b.label} ${b.start_time}–${b.end_time}`}
            />
          )
        })}
      </div>
      <div className="flex justify-between text-[10px] text-muted-foreground font-mono">
        <span>{blocks[0]?.start_time}</span>
        <span>{blocks[blocks.length - 1]?.end_time}</span>
      </div>
    </div>
  )
}

// ── Stat pill ────────────────────────────────────────────────────

function StatPill({
  label,
  value,
  limit,
  warning,
}: {
  label: string
  value: number
  limit?: number
  warning?: boolean
}) {
  const over = limit !== undefined && value > limit
  return (
    <div
      className={cn(
        "px-3 py-2 rounded-lg border",
        over
          ? "border-destructive/30 bg-destructive/5"
          : warning
            ? "border-warning/30 bg-warning/5"
            : "border-border-subtle bg-card"
      )}
    >
      <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-0.5">
        {label}
      </p>
      <p
        className={cn(
          "text-[14px] font-mono font-medium",
          over ? "text-destructive" : ""
        )}
      >
        {fmtMin(value)}
      </p>
      {limit !== undefined && (
        <p className="text-[9px] text-muted-foreground">max {fmtMin(limit)}</p>
      )}
    </div>
  )
}

// ── Main page ────────────────────────────────────────────────────

export function BuilderPage() {
  // Config
  const [constants, setConstants] = useState<AppConstants | null>(null)
  const [deposito, setDeposito] = useState("")
  const [dayType, setDayType] = useState("LV")
  const [accessoryType, setAccessoryType] = useState("standard")

  // Trains added to shift
  const [trainIds, setTrainIds] = useState<string[]>([])
  const [deadheadIds, setDeadheadIds] = useState<string[]>([])
  const [isFr, setIsFr] = useState(false)

  // Search
  const [searchQuery, setSearchQuery] = useState("")
  const [searchResults, setSearchResults] = useState<TrainSegment[]>([])
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchMode, setSearchMode] = useState<"numero" | "connessioni">("numero")

  // Validation
  const [validation, setValidation] = useState<ValidateDayResult | null>(null)
  const [validating, setValidating] = useState(false)

  // Save
  const [saveName, setSaveName] = useState("")
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState("")

  // Load constants on mount
  useEffect(() => {
    getConstants().then(setConstants).catch(() => {})
  }, [])

  // Validate whenever trains change
  useEffect(() => {
    if (trainIds.length === 0) {
      setValidation(null)
      return
    }
    const timer = setTimeout(async () => {
      setValidating(true)
      try {
        const result = await validateDayWithTimeline({
          train_ids: trainIds,
          deposito,
          accessory_type: accessoryType,
          deadhead_ids: deadheadIds,
          is_fr: isFr,
        })
        setValidation(result)
      } catch {
        // silent — validation is optional feedback
      } finally {
        setValidating(false)
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [trainIds, deposito, accessoryType, deadheadIds, isFr])

  // Search train by number
  const searchByNumber = useCallback(async () => {
    if (!searchQuery.trim()) return
    setSearchLoading(true)
    setSearchResults([])
    try {
      const data = await queryTrain(searchQuery.trim())
      setSearchResults(data.segments)
    } catch {
      setSearchResults([])
    } finally {
      setSearchLoading(false)
    }
  }, [searchQuery])

  // Search connections from last station
  const searchConnections = useCallback(async () => {
    if (!validation?.last_station) return
    setSearchLoading(true)
    setSearchResults([])
    try {
      const lastSeg = validation.segments[validation.segments.length - 1]
      const data = await getConnections({
        from_station: lastSeg?.to_station || validation.last_station,
        after_time: lastSeg?.arr_time || "00:00",
        day_type: dayType,
        exclude: trainIds.join(","),
      })
      // Convert connections to segment-like format for display
      setSearchResults(
        data.connections.map((c) => ({
          train_id: c.train_id,
          from_station: c.from_station,
          to_station: c.to_station,
          dep_time: c.dep_time,
          arr_time: c.arr_time,
        }))
      )
    } catch {
      setSearchResults([])
    } finally {
      setSearchLoading(false)
    }
  }, [validation, dayType, trainIds])

  // Add train
  const addTrain = useCallback(
    (trainId: string) => {
      if (!trainIds.includes(trainId)) {
        setTrainIds((prev) => [...prev, trainId])
        setSearchResults([])
        setSearchQuery("")
        setSaved(false)
      }
    },
    [trainIds]
  )

  // Remove train
  const removeTrain = useCallback((trainId: string) => {
    setTrainIds((prev) => prev.filter((t) => t !== trainId))
    setDeadheadIds((prev) => prev.filter((t) => t !== trainId))
    setSaved(false)
  }, [])

  // Toggle deadhead
  const toggleDeadhead = useCallback((trainId: string) => {
    setDeadheadIds((prev) =>
      prev.includes(trainId) ? prev.filter((t) => t !== trainId) : [...prev, trainId]
    )
  }, [])

  // Save
  const handleSave = useCallback(async () => {
    if (!saveName.trim() || !validation) return
    setSaving(true)
    setError("")
    try {
      await saveShift({
        name: saveName.trim(),
        deposito,
        day_type: dayType,
        train_ids: trainIds,
        deadhead_ids: deadheadIds,
        prestazione_min: validation.prestazione_min,
        condotta_min: validation.condotta_min,
        meal_min: validation.meal_min,
        accessori_min: validation.accessori_min,
        extra_min: validation.extra_min,
        is_fr: isFr,
        last_station: validation.last_station,
        violations: validation.violations,
        accessory_type: accessoryType,
        presentation_time: validation.presentation_time,
        end_time: validation.end_time,
      })
      setSaved(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Errore salvataggio")
    } finally {
      setSaving(false)
    }
  }, [saveName, validation, deposito, dayType, trainIds, deadheadIds, isFr, accessoryType])

  if (!constants) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={20} className="animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-6">
      {/* ── LEFT: Builder ── */}
      <div className="space-y-4">
        {/* Header */}
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Costruzione turno</h2>
          <p className="text-[13px] text-muted-foreground mt-0.5">
            Aggiungi treni per costruire la giornata
          </p>
        </div>

        {/* Config row */}
        <div className="flex flex-wrap gap-3">
          {/* Deposito */}
          <div className="relative">
            <select
              value={deposito}
              onChange={(e) => setDeposito(e.target.value)}
              className="appearance-none bg-card border border-border rounded-lg px-3 py-2 pr-8 text-[12px] focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="">Deposito...</option>
              {constants.DEPOSITI.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
            <ChevronDown
              size={12}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none"
            />
          </div>

          {/* Day type */}
          <div className="flex gap-1 bg-muted p-0.5 rounded-md">
            {["LV", "SAB", "DOM"].map((dt) => (
              <button
                key={dt}
                onClick={() => setDayType(dt)}
                className={cn(
                  "px-2.5 py-1 rounded text-[11px] font-medium transition-colors",
                  dayType === dt
                    ? "bg-card text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                {dt}
              </button>
            ))}
          </div>

          {/* Accessory type */}
          <div className="relative">
            <select
              value={accessoryType}
              onChange={(e) => setAccessoryType(e.target.value)}
              className="appearance-none bg-card border border-border rounded-lg px-3 py-2 pr-8 text-[12px] focus:outline-none focus:ring-1 focus:ring-primary"
            >
              {Object.entries(constants.ACCESSORY_OPTIONS).map(([key, opt]) => (
                <option key={key} value={key}>
                  {opt.label}
                </option>
              ))}
            </select>
            <ChevronDown
              size={12}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none"
            />
          </div>

          {/* FR toggle */}
          <button
            onClick={() => setIsFr(!isFr)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium border transition-colors",
              isFr
                ? "bg-violet-500/10 border-violet-500/30 text-violet-400"
                : "bg-card border-border text-muted-foreground hover:text-foreground"
            )}
          >
            <Moon size={12} />
            FR
          </button>
        </div>

        {/* Search */}
        <div className="bg-card rounded-lg border border-border-subtle p-3 space-y-3">
          <div className="flex gap-2">
            {/* Search mode tabs */}
            <button
              onClick={() => setSearchMode("numero")}
              className={cn(
                "text-[11px] font-medium px-2 py-1 rounded transition-colors",
                searchMode === "numero"
                  ? "bg-muted text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              Per numero
            </button>
            {trainIds.length > 0 && (
              <button
                onClick={() => {
                  setSearchMode("connessioni")
                  searchConnections()
                }}
                className={cn(
                  "text-[11px] font-medium px-2 py-1 rounded transition-colors",
                  searchMode === "connessioni"
                    ? "bg-muted text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                Connessioni da {validation?.last_station?.slice(0, 15) || "..."}
              </button>
            )}
          </div>

          {searchMode === "numero" && (
            <div className="relative">
              <Search
                size={14}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
              />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && searchByNumber()}
                placeholder="Numero treno (es. 10603)"
                className="w-full pl-8 pr-16 py-2 bg-muted border border-border rounded-md text-[12px] placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary"
              />
              <button
                onClick={searchByNumber}
                disabled={searchLoading || !searchQuery.trim()}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 px-2 py-1 bg-primary text-primary-foreground rounded text-[11px] font-medium hover:bg-primary-hover disabled:opacity-30"
              >
                {searchLoading ? <Loader2 size={12} className="animate-spin" /> : "Cerca"}
              </button>
            </div>
          )}

          {/* Results */}
          {searchResults.length > 0 && (
            <div className="space-y-0.5 max-h-48 overflow-y-auto">
              {searchResults.map((seg, i) => (
                <button
                  key={`${seg.train_id}-${i}`}
                  onClick={() => addTrain(seg.train_id)}
                  disabled={trainIds.includes(seg.train_id)}
                  className={cn(
                    "w-full flex items-center gap-2 px-2 py-1.5 rounded text-[12px] text-left transition-colors",
                    trainIds.includes(seg.train_id)
                      ? "opacity-30 cursor-not-allowed"
                      : "hover:bg-muted/50"
                  )}
                >
                  <Plus size={12} className="text-primary shrink-0" />
                  <span className="font-mono text-primary w-14">{seg.train_id}</span>
                  <span className="truncate">{seg.from_station}</span>
                  <ArrowRight size={10} className="text-muted-foreground shrink-0" />
                  <span className="truncate">{seg.to_station}</span>
                  <span className="font-mono text-muted-foreground ml-auto text-[11px]">
                    {seg.dep_time}–{seg.arr_time}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Added trains */}
        {trainIds.length > 0 && (
          <div className="bg-card rounded-lg border border-border-subtle">
            <div className="px-3 py-2 border-b border-border-subtle flex items-center gap-2">
              <Train size={14} className="text-muted-foreground" />
              <span className="text-[12px] font-medium">
                Treni nel turno ({trainIds.length})
              </span>
            </div>
            <div className="p-1">
              {trainIds.map((tid) => {
                const isDh = deadheadIds.includes(tid)
                const seg = validation?.segments.find((s) => s.train_id === tid)
                return (
                  <div
                    key={tid}
                    className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-muted/30 group"
                  >
                    <span
                      className={cn(
                        "font-mono text-[12px] w-14",
                        isDh ? "text-amber-500" : "text-primary"
                      )}
                    >
                      {tid}
                    </span>
                    {seg && (
                      <>
                        <span className="text-[11px] text-muted-foreground truncate">
                          {seg.from_station}
                        </span>
                        <ArrowRight size={10} className="text-muted-foreground shrink-0" />
                        <span className="text-[11px] text-muted-foreground truncate">
                          {seg.to_station}
                        </span>
                        <span className="text-[10px] font-mono text-muted-foreground ml-auto">
                          {seg.dep_time}–{seg.arr_time}
                        </span>
                      </>
                    )}
                    <div className="flex items-center gap-1 ml-auto opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={() => toggleDeadhead(tid)}
                        className={cn(
                          "text-[9px] px-1.5 py-0.5 rounded font-medium transition-colors",
                          isDh
                            ? "bg-amber-500/20 text-amber-400"
                            : "bg-muted text-muted-foreground hover:text-foreground"
                        )}
                        title={isDh ? "Treno in condotta" : "Marca come vettura"}
                      >
                        {isDh ? "VET" : "VET"}
                      </button>
                      <button
                        onClick={() => removeTrain(tid)}
                        className="p-0.5 text-muted-foreground hover:text-destructive transition-colors"
                      >
                        <X size={12} />
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Timeline */}
        {validation && validation.timeline.length > 0 && (
          <div className="bg-card rounded-lg border border-border-subtle p-3 space-y-3">
            <p className="text-[11px] text-muted-foreground font-medium uppercase tracking-wider">
              Timeline giornata
            </p>
            <MiniTimeline blocks={validation.timeline} />

            {/* Block list */}
            <div className="space-y-0.5">
              {validation.timeline.map((b, i) => (
                <div
                  key={i}
                  className="grid grid-cols-[8px_1fr_48px_48px_40px] items-center gap-2 py-1 px-1 text-[11px]"
                >
                  <div className={cn("w-2 h-2 rounded-full", BLOCK_COLORS[b.type] || "bg-zinc-500")} />
                  <span className="truncate">
                    {b.label}
                    {b.detail && <span className="text-muted-foreground ml-1">{b.detail}</span>}
                  </span>
                  <span className="font-mono text-muted-foreground text-right text-[10px]">
                    {b.start_time}
                  </span>
                  <span className="font-mono text-right text-[10px]">{b.end_time}</span>
                  <span className="text-right text-[10px] text-muted-foreground">
                    {b.duration}m
                  </span>
                </div>
              ))}
            </div>

            {/* Legend */}
            <div className="flex flex-wrap gap-2.5 pt-1 border-t border-border-subtle text-[9px] text-muted-foreground">
              {[
                { c: "bg-primary", l: "Treno" },
                { c: "bg-amber-600", l: "Vettura" },
                { c: "bg-emerald-600", l: "Refez." },
                { c: "bg-zinc-600", l: "Acc." },
                { c: "bg-cyan-600", l: "Spost." },
              ].map(({ c, l }) => (
                <span key={l} className="flex items-center gap-1">
                  <span className={cn("w-2 h-2 rounded-sm", c)} />
                  {l}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── RIGHT: Validation panel ── */}
      <div className="space-y-4">
        {/* Validation stats */}
        <div className="bg-card rounded-lg border border-border-subtle p-4 space-y-3 sticky top-6">
          <div className="flex items-center justify-between">
            <p className="text-[12px] font-medium">Validazione</p>
            {validating && <Loader2 size={12} className="animate-spin text-muted-foreground" />}
            {validation && !validating && (
              <span
                className={cn(
                  "flex items-center gap-1 text-[11px] font-medium",
                  validation.valid ? "text-success" : "text-destructive"
                )}
              >
                {validation.valid ? (
                  <>
                    <CheckCircle size={12} /> Valido
                  </>
                ) : (
                  <>
                    <AlertTriangle size={12} /> {validation.violations.length} violazioni
                  </>
                )}
              </span>
            )}
          </div>

          {validation ? (
            <>
              {/* Stats */}
              <div className="grid grid-cols-2 gap-2">
                <StatPill
                  label="Prestazione"
                  value={validation.prestazione_min}
                  limit={constants.MAX_PRESTAZIONE_MIN}
                />
                <StatPill
                  label="Condotta"
                  value={validation.condotta_min}
                  limit={constants.MAX_CONDOTTA_MIN}
                />
                <StatPill label="Refezione" value={validation.meal_min} />
                <StatPill label="Accessori" value={validation.accessori_min} />
              </div>

              {/* Times */}
              <div className="flex gap-4 text-[11px]">
                <div>
                  <span className="text-muted-foreground">Inizio </span>
                  <span className="font-mono font-medium">{validation.presentation_time}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Fine </span>
                  <span className="font-mono font-medium">{validation.end_time}</span>
                </div>
                {validation.is_fr && (
                  <span className="flex items-center gap-1 text-violet-400">
                    <Moon size={10} /> FR
                  </span>
                )}
              </div>

              {/* Last station */}
              {validation.last_station && (
                <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                  <MapPin size={10} />
                  Ultima stazione: {validation.last_station}
                </div>
              )}

              {/* Violations */}
              {validation.violations.length > 0 && (
                <div className="space-y-1 pt-2 border-t border-border-subtle">
                  {validation.violations.map((v, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-1.5 text-[11px] text-destructive/80 bg-destructive/5 px-2 py-1.5 rounded"
                    >
                      <AlertTriangle size={11} className="shrink-0 mt-0.5" />
                      <span>{v.message}</span>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p className="text-[12px] text-muted-foreground py-4 text-center">
              Aggiungi treni per vedere la validazione
            </p>
          )}

          {/* Save */}
          {trainIds.length > 0 && (
            <div className="pt-3 border-t border-border-subtle space-y-2">
              <input
                type="text"
                value={saveName}
                onChange={(e) => setSaveName(e.target.value)}
                placeholder="Nome turno (es. G1-Cremona)"
                className="w-full px-3 py-2 bg-muted border border-border rounded-md text-[12px] placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary"
              />
              {error && (
                <p className="text-[11px] text-destructive">{error}</p>
              )}
              <button
                onClick={handleSave}
                disabled={saving || !saveName.trim() || saved}
                className={cn(
                  "w-full flex items-center justify-center gap-2 py-2 rounded-lg text-[12px] font-medium transition-colors",
                  saved
                    ? "bg-success/10 text-success border border-success/20"
                    : "bg-primary text-primary-foreground hover:bg-primary-hover disabled:opacity-30"
                )}
              >
                {saving ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : saved ? (
                  <>
                    <CheckCircle size={14} /> Salvato
                  </>
                ) : (
                  <>
                    <Save size={14} /> Salva turno
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
