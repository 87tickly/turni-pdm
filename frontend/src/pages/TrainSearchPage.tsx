import { useState, useCallback, useEffect, useRef } from "react"
import {
  Search,
  Train,
  MapPin,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  Loader2,
  Database,
  Radio,
} from "lucide-react"
import { cn } from "@/lib/utils"
import {
  queryTrain,
  vtAutocompleteStation,
  vtDepartures,
  vtArrivals,
  vtTrainInfo,
  getGiroChain,
  type TrainSegment,
  type VtDeparture,
  type VtStation,
  type VtTrainInfo,
  type VtStop,
  type GiroChainContext,
} from "@/lib/api"

// ── Tab component ────────────────────────────────────────────────

function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { id: string; label: string; icon: typeof Train }[]
  active: string
  onChange: (id: string) => void
}) {
  return (
    <div className="flex gap-1 bg-muted p-1 rounded-lg">
      {tabs.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          onClick={() => onChange(id)}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] font-medium transition-colors",
            active === id
              ? "bg-card text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          <Icon size={13} />
          {label}
        </button>
      ))}
    </div>
  )
}

// ── Delay badge ──────────────────────────────────────────────────

function DelayBadge({ delay }: { delay: number }) {
  if (delay === 0) return <span className="text-[11px] text-success font-medium">In orario</span>
  if (delay > 0)
    return (
      <span className="text-[11px] text-destructive font-medium">+{delay}&apos;</span>
    )
  return <span className="text-[11px] text-success font-medium">{delay}&apos;</span>
}

// ── Train detail panel ───────────────────────────────────────────

function TrainDetail({ trainNumber }: { trainNumber: number }) {
  const [info, setInfo] = useState<VtTrainInfo | null>(null)
  const [giro, setGiro] = useState<GiroChainContext | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    setLoading(true)
    setError("")
    Promise.all([
      vtTrainInfo(trainNumber).catch(() => null),
      getGiroChain(String(trainNumber)).catch(() => null),
    ]).then(([vtData, giroData]) => {
      setInfo(vtData)
      setGiro(giroData)
      if (!vtData) setError("Treno non trovato su ARTURO Live")
      setLoading(false)
    })
  }, [trainNumber])

  if (loading)
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 size={16} className="animate-spin text-muted-foreground" />
      </div>
    )

  if (error && !info)
    return <p className="text-[12px] text-muted-foreground py-4">{error}</p>

  if (!info) return null

  const statusColors: Record<string, string> = {
    regolare: "text-success",
    ritardo: "text-destructive",
    soppresso: "text-destructive",
    non_partito: "text-warning",
  }

  return (
    <div className="space-y-4 pt-2">
      {/* Header treno */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className={cn("text-[12px] font-medium", statusColors[info.status] || "text-foreground")}>
          {info.status.toUpperCase().replace("_", " ")}
        </span>
        <span className="text-[11px] text-muted-foreground">
          {info.operator}
        </span>
        {info.delay !== 0 && <DelayBadge delay={info.delay} />}
      </div>

      {/* Giro materiale */}
      {giro && giro.chain && giro.chain.length > 1 && (
        <div className="bg-muted rounded-lg p-3">
          <p className="text-[11px] text-muted-foreground mb-2 flex flex-wrap items-center gap-1.5">
            <span>
              Giro materiale {giro.turn_number && `— turno ${giro.turn_number}`} ({giro.position + 1}/{giro.total})
            </span>
            {giro.material_type && (
              <span className="px-1.5 py-0.5 rounded bg-brand/10 text-brand text-[10px] font-semibold font-mono">
                {giro.material_type}
              </span>
            )}
          </p>
          <div className="flex flex-wrap gap-1">
            {giro.chain.map((c, i) => (
              <span
                key={i}
                className={cn(
                  "px-1.5 py-0.5 rounded text-[10px] font-mono",
                  i === giro.position
                    ? "bg-primary/20 text-primary font-medium"
                    : "bg-card text-muted-foreground"
                )}
              >
                {c.train_id}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Fermate */}
      {info.stops.length > 0 && (
        <div>
          {/* Header colonne */}
          <div className="grid grid-cols-[16px_1fr_48px_48px_48px_56px] items-center gap-1 py-1 px-2 text-[10px] text-muted-foreground uppercase tracking-wider border-b border-border-subtle mb-1">
            <span />
            <span>{info.stops.length} fermate</span>
            <span className="text-right">Arr</span>
            <span className="text-right">Dep</span>
            <span className="text-center">Bin</span>
            <span className="text-right">Rit.</span>
          </div>
          <div className="space-y-0">
            {info.stops.map((stop, i) => (
              <StopRow key={i} stop={stop} isFirst={i === 0} isLast={i === info.stops.length - 1} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function StopRow({
  stop,
  isFirst,
  isLast,
}: {
  stop: VtStop
  isFirst: boolean
  isLast: boolean
}) {
  const arrTime = stop.scheduled_arr || ""
  const depTime = stop.scheduled_dep || ""
  const delay = isFirst ? stop.delay_dep : stop.delay_arr

  return (
    <div
      className={cn(
        "grid grid-cols-[16px_1fr_48px_48px_48px_56px] items-center gap-1 py-1.5 px-2 text-[12px]",
        stop.cancelled && "opacity-40 line-through"
      )}
    >
      {/* Timeline dot */}
      <div className="flex justify-center">
        <div
          className={cn(
            "w-2 h-2 rounded-full",
            isFirst || isLast ? "bg-primary" : "bg-border"
          )}
        />
      </div>

      {/* Station */}
      <span className="truncate">{stop.station}</span>

      {/* Arr */}
      <span className="font-mono text-muted-foreground text-right text-[11px]">
        {arrTime || ""}
      </span>

      {/* Dep */}
      <span className="font-mono text-right text-[11px]">
        {depTime || ""}
      </span>

      {/* Platform */}
      <span className="text-[10px] text-muted-foreground text-center">
        {stop.platform_actual || stop.platform_scheduled || ""}
      </span>

      {/* Delay */}
      <span className="text-right">
        {delay !== 0 ? (
          <span className={cn("text-[11px] font-medium", delay > 0 ? "text-destructive" : "text-success")}>
            {delay > 0 ? "+" : ""}{delay}&apos;
          </span>
        ) : (
          <span className="text-[10px] text-success">ok</span>
        )}
      </span>
    </div>
  )
}

// ── DB Segment row ───────────────────────────────────────────────

function SegmentRow({ seg }: { seg: TrainSegment }) {
  return (
    <div className="flex items-center gap-3 py-1.5 px-2 text-[12px] hover:bg-muted/50 rounded">
      <span className="font-mono text-primary w-14">{seg.train_id}</span>
      <span className="truncate flex-1">{seg.from_station}</span>
      <ArrowRight size={12} className="text-muted-foreground shrink-0" />
      <span className="truncate flex-1">{seg.to_station}</span>
      <span className="font-mono w-12 text-right">{seg.dep_time}</span>
      <span className="text-muted-foreground">→</span>
      <span className="font-mono w-12 text-right">{seg.arr_time}</span>
    </div>
  )
}

// ── Main page ────────────────────────────────────────────────────

export function TrainSearchPage() {
  const [tab, setTab] = useState("treno")
  const [query, setQuery] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  // Train search results
  const [dbSegments, setDbSegments] = useState<TrainSegment[]>([])
  const [expandedTrain, setExpandedTrain] = useState<number | null>(null)

  // Station search
  const [stationSuggestions, setStationSuggestions] = useState<VtStation[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [departures, setDepartures] = useState<VtDeparture[]>([])
  const [arrivals, setArrivals] = useState<VtDeparture[]>([])
  const [stationTab, setStationTab] = useState<"partenze" | "arrivi">("partenze")
  const [selectedStation, setSelectedStation] = useState("")
  const suggestionsRef = useRef<HTMLDivElement>(null)

  // Autocomplete stazione
  const handleStationInput = useCallback(async (value: string) => {
    setQuery(value)
    if (value.length >= 2) {
      try {
        const data = await vtAutocompleteStation(value)
        setStationSuggestions(data.stations)
        setShowSuggestions(true)
      } catch {
        setStationSuggestions([])
      }
    } else {
      setStationSuggestions([])
      setShowSuggestions(false)
    }
  }, [])

  // Cerca treno nel DB locale
  const searchTrain = useCallback(async () => {
    if (!query.trim()) return
    setLoading(true)
    setError("")
    setDbSegments([])
    setExpandedTrain(null)

    try {
      const data = await queryTrain(query.trim())
      setDbSegments(data.segments)
      if (data.segments.length === 0) {
        setError(`Treno ${query} non trovato nel database locale`)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Errore ricerca")
    } finally {
      setLoading(false)
    }
  }, [query])

  // Seleziona stazione da autocomplete
  const selectStation = useCallback(async (station: VtStation) => {
    setShowSuggestions(false)
    setSelectedStation(station.name)
    setQuery(station.name)
    setLoading(true)
    setError("")
    setDepartures([])
    setArrivals([])

    try {
      const [depData, arrData] = await Promise.all([
        vtDepartures(station.code, false),
        vtArrivals(station.code, false),
      ])
      setDepartures(depData.departures)
      setArrivals(arrData.arrivals)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Errore caricamento stazione")
    } finally {
      setLoading(false)
    }
  }, [])

  // Close suggestions on click outside
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (suggestionsRef.current && !suggestionsRef.current.contains(e.target as Node)) {
        setShowSuggestions(false)
      }
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [])

  const trainNum = parseInt(query)
  const canExpandRealtime = tab === "treno" && dbSegments.length > 0 && !isNaN(trainNum)

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h2 className="text-lg font-semibold tracking-tight">Cerca treni</h2>
        <p className="text-[13px] text-muted-foreground mt-0.5">
          Cerca per numero treno o per stazione
        </p>
      </div>

      {/* Tabs */}
      <div className="mb-4">
        <Tabs
          tabs={[
            { id: "treno", label: "Numero treno", icon: Train },
            { id: "stazione", label: "Stazione", icon: MapPin },
          ]}
          active={tab}
          onChange={(id) => {
            setTab(id)
            setQuery("")
            setError("")
            setDbSegments([])
            setDepartures([])
            setArrivals([])
            setExpandedTrain(null)
            setSelectedStation("")
          }}
        />
      </div>

      {/* Search input */}
      <div className="relative mb-6" ref={suggestionsRef}>
        <div className="relative">
          <Search
            size={15}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <input
            type="text"
            value={query}
            onChange={(e) => {
              if (tab === "stazione") {
                handleStationInput(e.target.value)
              } else {
                setQuery(e.target.value)
              }
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && tab === "treno") searchTrain()
            }}
            placeholder={
              tab === "treno"
                ? "Numero treno (es. 10603)"
                : "Nome stazione (es. Milano Centrale)"
            }
            className="w-full pl-9 pr-4 py-2.5 bg-card border border-border rounded-lg text-[13px] placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary transition-colors"
            autoFocus
          />
          {tab === "treno" && (
            <button
              onClick={searchTrain}
              disabled={loading || !query.trim()}
              className="absolute right-2 top-1/2 -translate-y-1/2 px-3 py-1 bg-primary text-primary-foreground rounded-md text-[12px] font-medium hover:bg-primary-hover disabled:opacity-30 transition-colors"
            >
              {loading ? <Loader2 size={13} className="animate-spin" /> : "Cerca"}
            </button>
          )}
        </div>

        {/* Station suggestions dropdown */}
        {showSuggestions && stationSuggestions.length > 0 && (
          <div className="absolute z-50 w-full mt-1 bg-card border border-border rounded-lg shadow-lg overflow-hidden">
            {stationSuggestions.map((s) => (
              <button
                key={s.code}
                onClick={() => selectStation(s)}
                className="w-full text-left px-3 py-2 text-[13px] hover:bg-muted transition-colors flex items-center gap-2"
              >
                <MapPin size={13} className="text-muted-foreground shrink-0" />
                <span className="truncate">{s.name}</span>
                <span className="text-[10px] text-muted-foreground font-mono ml-auto">
                  {s.code}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 bg-warning-muted text-warning text-[12px] p-3 rounded-lg mb-4">
          <AlertTriangle size={14} />
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 size={20} className="animate-spin text-muted-foreground" />
        </div>
      )}

      {/* ── TRENO RESULTS ── */}
      {tab === "treno" && !loading && dbSegments.length > 0 && (
        <div className="space-y-3">
          {/* DB locale results */}
          <div className="bg-card rounded-lg border border-border-subtle">
            <div className="flex items-center gap-2 px-4 py-3 border-b border-border-subtle">
              <Database size={14} className="text-muted-foreground" />
              <span className="text-[12px] font-medium">Database locale</span>
              <span className="text-[11px] text-muted-foreground ml-auto">
                {dbSegments.length} segmento/i
              </span>
            </div>
            <div className="p-1">
              {dbSegments.map((seg, i) => (
                <SegmentRow key={i} seg={seg} />
              ))}
            </div>
          </div>

          {/* Real-time expand */}
          {canExpandRealtime && (
            <div className="bg-card rounded-lg border border-border-subtle">
              <button
                onClick={() =>
                  setExpandedTrain(expandedTrain === trainNum ? null : trainNum)
                }
                className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-muted/30 transition-colors"
              >
                <Radio size={14} className="text-primary" />
                <span className="text-[12px] font-medium">
                  Dati real-time (ARTURO Live)
                </span>
                {expandedTrain === trainNum ? (
                  <ChevronUp size={14} className="ml-auto text-muted-foreground" />
                ) : (
                  <ChevronDown size={14} className="ml-auto text-muted-foreground" />
                )}
              </button>
              {expandedTrain === trainNum && (
                <div className="px-4 pb-4 border-t border-border-subtle">
                  <TrainDetail trainNumber={trainNum} />
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── STAZIONE RESULTS ── */}
      {tab === "stazione" && !loading && selectedStation && (departures.length > 0 || arrivals.length > 0) && (
        <div className="bg-card rounded-lg border border-border-subtle">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-border-subtle">
            <MapPin size={14} className="text-muted-foreground" />
            <span className="text-[12px] font-medium">{selectedStation}</span>
            <div className="ml-auto flex gap-1">
              <button
                onClick={() => setStationTab("partenze")}
                className={cn(
                  "px-2 py-0.5 rounded text-[11px] font-medium transition-colors",
                  stationTab === "partenze"
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                Partenze ({departures.length})
              </button>
              <button
                onClick={() => setStationTab("arrivi")}
                className={cn(
                  "px-2 py-0.5 rounded text-[11px] font-medium transition-colors",
                  stationTab === "arrivi"
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                Arrivi ({arrivals.length})
              </button>
            </div>
          </div>

          <div className="p-1">
            {(stationTab === "partenze" ? departures : arrivals).map((t, i) => (
              <DepartureRow key={i} train={t} />
            ))}
            {(stationTab === "partenze" ? departures : arrivals).length === 0 && (
              <p className="text-[12px] text-muted-foreground py-4 text-center">
                Nessun {stationTab === "partenze" ? "treno in partenza" : "arrivo"}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Departure/Arrival row ────────────────────────────────────────

function DepartureRow({
  train,
}: {
  train: VtDeparture
}) {
  return (
    <div className="flex items-center gap-3 py-2 px-3 hover:bg-muted/30 rounded transition-colors">
      {/* Train number */}
      <div className="w-16">
        <span className="text-[12px] font-mono font-medium text-primary">
          {train.train_number}
        </span>
      </div>

      {/* Category */}
      <span className="text-[10px] text-muted-foreground font-medium uppercase w-8">
        {train.category}
      </span>

      {/* Destination/Origin */}
      <span className="flex-1 text-[12px] truncate">{train.destination}</span>

      {/* Operator */}
      <span className="text-[10px] text-muted-foreground w-16 text-center truncate">
        {train.operator}
      </span>

      {/* Platform */}
      {(train.platform_actual || train.platform_scheduled) && (
        <span className="text-[11px] text-muted-foreground w-8 text-center font-mono">
          {train.platform_actual || train.platform_scheduled}
        </span>
      )}

      {/* Time */}
      <span className="text-[12px] font-mono w-12 text-right">
        {train.dep_time}
      </span>

      {/* Delay */}
      <span className="w-12 text-right">
        <DelayBadge delay={train.delay} />
      </span>
    </div>
  )
}
