import { useState, useEffect, useCallback } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import {
  Plus,
  Trash2,
  Save,
  Calendar,
  AlertCircle,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  X,
  Search,
  Home,
  Loader2,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { PdcGantt } from "@/components/PdcGantt"
import {
  createPdcTurn,
  updatePdcTurn,
  getPdcTurn,
  getCalendarPeriodicity,
  lookupTrainInGiroMateriale,
  findReturnTrain,
  type PdcTurnInput,
  type PdcDayInput,
  type PdcBlockInput,
  type PdcBlock,
  type ReturnTrain,
} from "@/lib/api"

// ── Constants ──────────────────────────────────────────────────

const BLOCK_TYPES: {
  value: PdcBlockInput["block_type"]
  label: string
  icon: string
  color: string
}[] = [
  { value: "train", label: "Treno", icon: "🚆", color: "bg-primary/10" },
  { value: "coach_transfer", label: "Vettura", icon: "🚌", color: "bg-violet-50" },
  { value: "cv_partenza", label: "CVp (partenza)", icon: "↳", color: "bg-amber-50" },
  { value: "cv_arrivo", label: "CVa (arrivo)", icon: "↲", color: "bg-amber-50" },
  { value: "meal", label: "Refezione", icon: "🍽️", color: "bg-emerald-50" },
  { value: "scomp", label: "S.COMP", icon: "⏸", color: "bg-slate-100" },
  { value: "available", label: "Disponibile", icon: "💤", color: "bg-slate-50" },
]

const PERIODICITA_OPTIONS = [
  "LMXGVSD",
  "LMXGVS",
  "LMXGV",
  "SD",
  "S",
  "D",
  "V",
  "G",
]

/** Converte un PdcBlockInput (editor) in un PdcBlock (visualizzatore). */
function inputToPdcBlock(b: PdcBlockInput): PdcBlock {
  return {
    id: 0,
    pdc_turn_day_id: 0,
    seq: b.seq ?? 0,
    block_type: b.block_type,
    train_id: b.train_id || "",
    vettura_id: b.vettura_id || "",
    from_station: b.from_station || "",
    to_station: b.to_station || "",
    start_time: b.start_time || "",
    end_time: b.end_time || "",
    accessori_maggiorati: b.accessori_maggiorati ? 1 : 0,
  }
}

// ── Sottocomponente: Editor blocco ─────────────────────────────

function BlockEditor({
  block,
  index,
  onChange,
  onRemove,
}: {
  block: PdcBlockInput
  index: number
  onChange: (b: PdcBlockInput) => void
  onRemove: () => void
}) {
  const showTrain = ["train", "cv_partenza", "cv_arrivo"].includes(block.block_type)
  const showVettura = block.block_type === "coach_transfer"
  const showStations = !["scomp", "available"].includes(block.block_type)
  const [lookupMsg, setLookupMsg] = useState<string>("")

  const handleLookup = async () => {
    if (!block.train_id) return
    setLookupMsg("🔍 ricerca...")
    try {
      const r = await lookupTrainInGiroMateriale(block.train_id)
      if (r.found) {
        onChange({
          ...block,
          from_station: r.from_station || block.from_station,
          to_station: r.to_station || block.to_station,
          start_time: r.dep_time || block.start_time,
          end_time: r.arr_time || block.end_time,
        })
        setLookupMsg(`✓ trovato nel giro materiale (turno ${r.material_turn_id || "?"})`)
      } else {
        setLookupMsg(`⚠ treno ${block.train_id} non trovato nel giro materiale`)
      }
    } catch (e) {
      setLookupMsg(`✗ errore: ${e instanceof Error ? e.message : "sconosciuto"}`)
    }
    setTimeout(() => setLookupMsg(""), 4000)
  }

  return (
    <div className="border border-border-subtle rounded-lg p-2 bg-muted/20 space-y-2">
      <div className="flex items-center gap-2 text-[11px]">
        <span className="font-mono text-muted-foreground min-w-[20px]">{index}</span>
        <select
          className="px-2 py-1 border border-border rounded bg-background text-[11px]"
          value={block.block_type}
          onChange={(e) =>
            onChange({ ...block, block_type: e.target.value as PdcBlockInput["block_type"] })
          }
        >
          {BLOCK_TYPES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.icon} {t.label}
            </option>
          ))}
        </select>

        {showTrain && (
          <>
            <input
              className="px-2 py-1 border border-border rounded font-mono w-20 text-[11px]"
              placeholder="Treno #"
              value={block.train_id || ""}
              onChange={(e) => onChange({ ...block, train_id: e.target.value })}
            />
            {block.block_type === "train" && block.train_id && (
              <button
                onClick={handleLookup}
                className="text-[10px] px-1.5 py-1 bg-primary/10 text-primary rounded hover:bg-primary/20 flex items-center gap-0.5"
                title="Cerca nel giro materiale e popola stazioni/orari"
                type="button"
              >
                <Search size={10} />
              </button>
            )}
          </>
        )}
        {showVettura && (
          <input
            className="px-2 py-1 border border-border rounded font-mono w-20 text-[11px]"
            placeholder="Vettura #"
            value={block.vettura_id || ""}
            onChange={(e) => onChange({ ...block, vettura_id: e.target.value })}
          />
        )}

        <div className="ml-auto flex items-center gap-1">
          <label className="flex items-center gap-1 text-[10px]">
            <input
              type="checkbox"
              checked={block.accessori_maggiorati || false}
              onChange={(e) =>
                onChange({ ...block, accessori_maggiorati: e.target.checked })
              }
            />
            ● acc. magg.
          </label>
          <button
            onClick={onRemove}
            className="text-destructive hover:bg-destructive/10 p-1 rounded"
            title="Rimuovi blocco"
          >
            <X size={12} />
          </button>
        </div>
      </div>

      {showStations && (
        <div className="flex items-center gap-2 text-[11px]">
          <input
            className="px-2 py-1 border border-border rounded flex-1 text-[11px]"
            placeholder="Stazione da"
            value={block.from_station || ""}
            onChange={(e) => onChange({ ...block, from_station: e.target.value })}
          />
          <span className="text-muted-foreground">→</span>
          <input
            className="px-2 py-1 border border-border rounded flex-1 text-[11px]"
            placeholder="Stazione a"
            value={block.to_station || ""}
            onChange={(e) => onChange({ ...block, to_station: e.target.value })}
          />
        </div>
      )}

      {lookupMsg && (
        <div className="text-[10px] text-muted-foreground pl-6">
          {lookupMsg}
        </div>
      )}

      <div className="flex items-center gap-2 text-[11px]">
        <label className="text-muted-foreground">Orari:</label>
        <input
          type="time"
          className="px-2 py-1 border border-border rounded font-mono text-[11px]"
          value={block.start_time || ""}
          onChange={(e) => onChange({ ...block, start_time: e.target.value })}
        />
        <span className="text-muted-foreground">–</span>
        <input
          type="time"
          className="px-2 py-1 border border-border rounded font-mono text-[11px]"
          value={block.end_time || ""}
          onChange={(e) => onChange({ ...block, end_time: e.target.value })}
        />
      </div>
    </div>
  )
}

// ── Sottocomponente: Editor giornata ───────────────────────────

function DayEditor({
  day,
  onChange,
  onRemove,
  impianto,
}: {
  day: PdcDayInput
  onChange: (d: PdcDayInput) => void
  onRemove: () => void
  impianto: string
}) {
  const [open, setOpen] = useState(true)
  const [returnSearching, setReturnSearching] = useState(false)
  const [returnCandidates, setReturnCandidates] = useState<ReturnTrain[] | null>(
    null
  )
  const [returnMsg, setReturnMsg] = useState("")

  const updateBlock = (i: number, b: PdcBlockInput) => {
    const blocks = [...(day.blocks || [])]
    blocks[i] = b
    onChange({ ...day, blocks })
  }
  const addBlock = () => {
    const blocks = [...(day.blocks || [])]
    blocks.push({ block_type: "train", seq: blocks.length })
    onChange({ ...day, blocks })
  }
  const removeBlock = (i: number) => {
    const blocks = (day.blocks || []).filter((_, idx) => idx !== i)
    onChange({ ...day, blocks: blocks.map((b, idx) => ({ ...b, seq: idx })) })
  }

  // Trova rientro in vettura: usa l'ultima stazione dell'ultimo blocco
  // con to_station e cerca treni per il deposito via ARTURO Live.
  const findReturnVettura = async () => {
    if (!impianto.trim()) {
      setReturnMsg("⚠ Impianto non impostato")
      return
    }
    const lastWithStation = [...(day.blocks || [])]
      .reverse()
      .find((b) => b.to_station && b.block_type !== "cv_arrivo")
    if (!lastWithStation) {
      setReturnMsg("⚠ Nessun treno con stazione di arrivo nel turno")
      return
    }
    const fromStation = lastWithStation.to_station || ""
    const afterTime = lastWithStation.end_time || "00:00"
    setReturnSearching(true)
    setReturnMsg("")
    setReturnCandidates(null)
    try {
      const r = await findReturnTrain(fromStation, impianto, afterTime)
      if (r.error) {
        setReturnMsg(`⚠ ${r.error}`)
      } else if (r.return_trains.length === 0) {
        setReturnMsg(
          `Nessun treno ARTURO Live dopo ${afterTime} da ${fromStation} a ${impianto}`
        )
      } else {
        setReturnCandidates(r.return_trains)
        setReturnMsg(
          `${r.return_trains.length} treno/i trovato/i da ${fromStation} → ${impianto}`
        )
      }
    } catch (e) {
      setReturnMsg(`✗ ${e instanceof Error ? e.message : "Errore"}`)
    } finally {
      setReturnSearching(false)
    }
  }

  // Aggiunge un treno di ritorno come coach_transfer (vettura) al turno
  const acceptReturnCandidate = (rt: ReturnTrain) => {
    const blocks = [...(day.blocks || [])]
    blocks.push({
      block_type: "coach_transfer",
      seq: blocks.length,
      vettura_id: rt.numero,
      from_station: rt.via || "",
      to_station: rt.destinazione || impianto,
      start_time: rt.dep_time,
      end_time: rt.arr_time,
    })
    onChange({ ...day, blocks })
    setReturnCandidates(null)
    setReturnMsg(`✓ aggiunto rientro vettura treno ${rt.numero}`)
    setTimeout(() => setReturnMsg(""), 3000)
  }

  return (
    <div className="border border-border-subtle rounded-lg bg-card">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border-subtle">
        <button onClick={() => setOpen(!open)}>
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        <label className="text-[11px] text-muted-foreground">g</label>
        <input
          type="number"
          min={1}
          className="w-12 px-1 py-0.5 border border-border rounded font-mono text-[12px]"
          value={day.day_number}
          onChange={(e) =>
            onChange({ ...day, day_number: parseInt(e.target.value) || 1 })
          }
        />
        <select
          className="px-2 py-0.5 border border-border rounded text-[11px] font-mono"
          value={day.periodicita}
          onChange={(e) => onChange({ ...day, periodicita: e.target.value })}
        >
          {PERIODICITA_OPTIONS.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>

        <label className="flex items-center gap-1 text-[10px] ml-2">
          <input
            type="checkbox"
            checked={day.is_disponibile || false}
            onChange={(e) =>
              onChange({ ...day, is_disponibile: e.target.checked })
            }
          />
          Disponibile
        </label>

        <div className="ml-auto flex items-center gap-1">
          <button
            onClick={onRemove}
            className="text-destructive hover:bg-destructive/10 p-1 rounded"
            title="Rimuovi giornata"
          >
            <Trash2 size={12} />
          </button>
        </div>
      </div>

      {open && (
        <div className="p-3 space-y-2">
          {!day.is_disponibile && (
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <label className="flex items-center gap-2">
                <span className="text-muted-foreground min-w-[70px]">Inizio:</span>
                <input
                  type="time"
                  className="flex-1 px-2 py-1 border border-border rounded font-mono text-[11px]"
                  value={day.start_time || ""}
                  onChange={(e) => onChange({ ...day, start_time: e.target.value })}
                />
              </label>
              <label className="flex items-center gap-2">
                <span className="text-muted-foreground min-w-[70px]">Fine:</span>
                <input
                  type="time"
                  className="flex-1 px-2 py-1 border border-border rounded font-mono text-[11px]"
                  value={day.end_time || ""}
                  onChange={(e) => onChange({ ...day, end_time: e.target.value })}
                />
              </label>

              <label className="flex items-center gap-2">
                <span className="text-muted-foreground min-w-[70px]">Lav min:</span>
                <input
                  type="number"
                  className="flex-1 px-2 py-1 border border-border rounded text-[11px]"
                  value={day.lavoro_min || 0}
                  onChange={(e) => onChange({ ...day, lavoro_min: parseInt(e.target.value) || 0 })}
                />
              </label>
              <label className="flex items-center gap-2">
                <span className="text-muted-foreground min-w-[70px]">Cct min:</span>
                <input
                  type="number"
                  className="flex-1 px-2 py-1 border border-border rounded text-[11px]"
                  value={day.condotta_min || 0}
                  onChange={(e) => onChange({ ...day, condotta_min: parseInt(e.target.value) || 0 })}
                />
              </label>
              <label className="flex items-center gap-2">
                <span className="text-muted-foreground min-w-[70px]">Km:</span>
                <input
                  type="number"
                  className="flex-1 px-2 py-1 border border-border rounded text-[11px]"
                  value={day.km || 0}
                  onChange={(e) => onChange({ ...day, km: parseInt(e.target.value) || 0 })}
                />
              </label>
              <label className="flex items-center gap-2">
                <span className="text-muted-foreground min-w-[70px]">Rip min:</span>
                <input
                  type="number"
                  className="flex-1 px-2 py-1 border border-border rounded text-[11px]"
                  value={day.riposo_min || 0}
                  onChange={(e) => onChange({ ...day, riposo_min: parseInt(e.target.value) || 0 })}
                />
              </label>
            </div>
          )}

          {!day.is_disponibile && (
            <>
              {/* Gantt visuale interattivo */}
              <div className="pt-2 border-t border-border-subtle">
                <p className="text-[10px] text-muted-foreground mb-1">
                  Trascina un blocco per spostarlo, trascina i bordi per ridimensionarlo, clicca sulla timeline vuota per aggiungere un nuovo blocco.
                </p>
                <PdcGantt
                  blocks={(day.blocks || []).map(b => inputToPdcBlock(b))}
                  startTime={day.start_time}
                  endTime={day.end_time}
                  label={`g${day.day_number} ${day.periodicita}`}
                  onBlockClick={(_, idx) => {
                    const el = document.getElementById(`block-editor-${idx}`)
                    if (el) {
                      el.scrollIntoView({ behavior: "smooth", block: "center" })
                      el.classList.add("ring-2", "ring-primary")
                      setTimeout(() => el.classList.remove("ring-2", "ring-primary"), 1500)
                    }
                  }}
                  onBlocksChange={(changes) => {
                    // Modifica uno o più blocchi (train + CVp/CVa agganciati)
                    // preservando tutti gli altri
                    const blocks = [...(day.blocks || [])]
                    for (const [idxStr, patch] of Object.entries(changes)) {
                      const idx = parseInt(idxStr)
                      blocks[idx] = { ...blocks[idx], ...patch }
                    }
                    onChange({ ...day, blocks })
                  }}
                  onTimelineClick={(h, m) => {
                    const blocks = [...(day.blocks || [])]
                    const hhmm = `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}`
                    blocks.push({
                      block_type: "train",
                      seq: blocks.length,
                      start_time: hhmm,
                    })
                    onChange({ ...day, blocks })
                  }}
                />
              </div>

              <div className="flex items-center justify-between pt-2 flex-wrap gap-2">
                <span className="text-[11px] font-semibold">Blocchi ({(day.blocks || []).length})</span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={findReturnVettura}
                    disabled={returnSearching}
                    className="text-[11px] px-2 py-1 bg-amber-50 text-amber-700 rounded hover:bg-amber-100 border border-amber-200 flex items-center gap-1 disabled:opacity-50"
                    title="Cerca un treno ARTURO Live per rientrare al deposito come vettura"
                  >
                    {returnSearching ? (
                      <Loader2 size={11} className="animate-spin" />
                    ) : (
                      <Home size={11} />
                    )}
                    Rientro in vettura
                  </button>
                  <button
                    onClick={addBlock}
                    className="text-[11px] px-2 py-1 bg-primary/10 text-primary rounded hover:bg-primary/20 flex items-center gap-1"
                  >
                    <Plus size={11} /> Aggiungi blocco
                  </button>
                </div>
              </div>

              {returnMsg && (
                <div className="text-[10px] text-muted-foreground px-1">
                  {returnMsg}
                </div>
              )}

              {returnCandidates && returnCandidates.length > 0 && (
                <div className="border border-amber-200 bg-amber-50 rounded-md p-2 space-y-1">
                  <p className="text-[11px] font-semibold text-amber-800 mb-1">
                    Treni per rientro al deposito:
                  </p>
                  {returnCandidates.map((rt, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-2 text-[11px] bg-white rounded px-2 py-1 border border-amber-100"
                    >
                      <span className="font-mono font-semibold">{rt.numero}</span>
                      {rt.categoria && (
                        <span className="text-[9px] text-muted-foreground">
                          {rt.categoria}
                        </span>
                      )}
                      <span className="text-muted-foreground">
                        {rt.via} → {rt.destinazione}
                      </span>
                      <span className="font-mono text-[10px]">
                        {rt.dep_time} – {rt.arr_time}
                      </span>
                      {rt.duration_min && (
                        <span className="text-[9px] text-muted-foreground">
                          ({rt.duration_min}m)
                        </span>
                      )}
                      <button
                        onClick={() => acceptReturnCandidate(rt)}
                        className="ml-auto text-[10px] px-2 py-0.5 bg-amber-600 text-white rounded hover:bg-amber-700"
                      >
                        + Aggiungi
                      </button>
                    </div>
                  ))}
                  <button
                    onClick={() => {
                      setReturnCandidates(null)
                      setReturnMsg("")
                    }}
                    className="text-[10px] text-muted-foreground hover:text-foreground"
                  >
                    Chiudi
                  </button>
                </div>
              )}
              <div className="space-y-2">
                {(day.blocks || []).map((b, i) => (
                  <div id={`block-editor-${i}`} key={i} className="rounded-lg transition-all">
                    <BlockEditor
                      block={b}
                      index={i}
                      onChange={(nb) => updateBlock(i, nb)}
                      onRemove={() => removeBlock(i)}
                    />
                  </div>
                ))}
                {(day.blocks || []).length === 0 && (
                  <p className="text-[11px] text-muted-foreground italic text-center py-3">
                    Nessun blocco. Clicca sulla timeline sopra per aggiungere il primo.
                  </p>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ── Sottocomponente: Preview calendario ────────────────────────

function CalendarPreview() {
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [info, setInfo] = useState<{ letter: string; weekday: string; holiday?: string | null } | null>(null)

  useEffect(() => {
    if (!date) return
    getCalendarPeriodicity(date)
      .then((r) => setInfo({ letter: r.letter, weekday: r.weekday, holiday: r.holiday_name }))
      .catch(() => setInfo(null))
  }, [date])

  return (
    <div className="border border-border-subtle rounded-lg p-3 bg-muted/20">
      <div className="flex items-center gap-2 text-[12px] font-semibold mb-2">
        <Calendar size={14} className="text-primary" />
        Preview calendario
      </div>
      <div className="flex items-center gap-2 text-[11px]">
        <input
          type="date"
          className="px-2 py-1 border border-border rounded text-[11px]"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
        {info && (
          <div className="flex items-center gap-2">
            <span className="font-mono font-bold text-primary text-[14px]">{info.letter}</span>
            <span className="text-muted-foreground">{info.weekday}</span>
            {info.holiday && (
              <span className="bg-amber-100 text-amber-800 px-2 py-0.5 rounded text-[10px]">
                {info.holiday}
              </span>
            )}
          </div>
        )}
      </div>
      <p className="text-[10px] text-muted-foreground mt-1">
        Un turno con periodicita' che contiene la lettera mostrata si applica a questa data.
        Festivi infrasettimanali → D.
      </p>
    </div>
  )
}

// ── Pagina principale ──────────────────────────────────────────

export function PdcBuilderPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const editId = searchParams.get("edit")

  const [codice, setCodice] = useState("")
  const [planning, setPlanning] = useState("")
  const [impianto, setImpianto] = useState("")
  const [profilo, setProfilo] = useState<"Condotta" | "Scorta">("Condotta")
  const [validFrom, setValidFrom] = useState("")
  const [validTo, setValidTo] = useState("")
  const [days, setDays] = useState<PdcDayInput[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const [success, setSuccess] = useState(false)
  const [loaded, setLoaded] = useState(false)

  // Modalità edit: carica turno esistente
  useEffect(() => {
    if (!editId) {
      setLoaded(true)
      return
    }
    getPdcTurn(parseInt(editId))
      .then((detail) => {
        setCodice(detail.turn.codice)
        setPlanning(detail.turn.planning)
        setImpianto(detail.turn.impianto)
        setProfilo(detail.turn.profilo as "Condotta" | "Scorta")
        setValidFrom(detail.turn.valid_from)
        setValidTo(detail.turn.valid_to)
        setDays(
          detail.days.map((d) => ({
            day_number: d.day_number,
            periodicita: d.periodicita,
            start_time: d.start_time,
            end_time: d.end_time,
            lavoro_min: d.lavoro_min,
            condotta_min: d.condotta_min,
            km: d.km,
            notturno: d.notturno === 1,
            riposo_min: d.riposo_min,
            is_disponibile: d.is_disponibile === 1,
            blocks: d.blocks.map((b) => ({
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
          }))
        )
        setLoaded(true)
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : "Errore caricamento turno")
        setLoaded(true)
      })
  }, [editId])

  const addDay = useCallback(() => {
    setDays((prev) => [
      ...prev,
      {
        day_number: (prev[prev.length - 1]?.day_number || 0) + 1,
        periodicita: "LMXGVSD",
        blocks: [],
      },
    ])
  }, [])

  const updateDay = useCallback((i: number, d: PdcDayInput) => {
    setDays((prev) => prev.map((x, idx) => (idx === i ? d : x)))
  }, [])

  const removeDay = useCallback((i: number) => {
    setDays((prev) => prev.filter((_, idx) => idx !== i))
  }, [])

  const save = async () => {
    setError("")
    setSuccess(false)
    if (!codice.trim() || !impianto.trim()) {
      setError("Codice e impianto sono obbligatori")
      return
    }
    setSaving(true)
    try {
      const payload: PdcTurnInput = {
        codice: codice.trim(),
        planning: planning.trim(),
        impianto: impianto.trim(),
        profilo,
        valid_from: validFrom,
        valid_to: validTo,
        days,
      }
      if (editId) {
        await updatePdcTurn(parseInt(editId), payload)
      } else {
        await createPdcTurn(payload)
      }
      setSuccess(true)
      setTimeout(() => navigate("/pdc"), 1000)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Errore salvataggio")
    } finally {
      setSaving(false)
    }
  }

  if (!loaded) {
    return <p className="text-[12px] text-muted-foreground">Caricamento...</p>
  }

  return (
    <div className="max-w-4xl mx-auto pb-20">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">
            {editId ? "Modifica turno PdC" : "Nuovo turno PdC"}
          </h2>
          <p className="text-[13px] text-muted-foreground mt-0.5">
            {editId
              ? "Modifica un turno PdC esistente"
              : "Crea un turno PdC nel formato ufficiale Trenord"}
          </p>
        </div>
        <button
          onClick={() => navigate("/pdc")}
          className="text-[12px] text-muted-foreground hover:text-foreground px-3 py-1"
        >
          Annulla
        </button>
      </div>

      {/* Calendar preview */}
      <div className="mb-4">
        <CalendarPreview />
      </div>

      {/* Header turno */}
      <div className="border border-border-subtle rounded-lg bg-card p-4 mb-4">
        <h3 className="text-[13px] font-semibold mb-3">Dati del turno</h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-[11px] text-muted-foreground">Codice *</span>
            <input
              className="px-2 py-1.5 border border-border rounded font-mono text-[12px]"
              placeholder="es. MIO_C"
              value={codice}
              onChange={(e) => setCodice(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] text-muted-foreground">Planning</span>
            <input
              className="px-2 py-1.5 border border-border rounded font-mono text-[12px]"
              placeholder="es. 99999"
              value={planning}
              onChange={(e) => setPlanning(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] text-muted-foreground">Impianto *</span>
            <input
              className="px-2 py-1.5 border border-border rounded text-[12px]"
              placeholder="es. MILANO"
              value={impianto}
              onChange={(e) => setImpianto(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] text-muted-foreground">Profilo</span>
            <select
              className="px-2 py-1.5 border border-border rounded text-[12px]"
              value={profilo}
              onChange={(e) => setProfilo(e.target.value as "Condotta" | "Scorta")}
            >
              <option value="Condotta">Condotta</option>
              <option value="Scorta">Scorta</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] text-muted-foreground">Valido dal</span>
            <input
              type="date"
              className="px-2 py-1.5 border border-border rounded text-[12px]"
              value={validFrom}
              onChange={(e) => setValidFrom(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] text-muted-foreground">Valido al</span>
            <input
              type="date"
              className="px-2 py-1.5 border border-border rounded text-[12px]"
              value={validTo}
              onChange={(e) => setValidTo(e.target.value)}
            />
          </label>
        </div>
      </div>

      {/* Giornate */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-[13px] font-semibold">Giornate ({days.length})</h3>
          <button
            onClick={addDay}
            className="text-[12px] px-3 py-1 bg-primary text-primary-foreground rounded hover:bg-primary/90 flex items-center gap-1"
          >
            <Plus size={12} /> Aggiungi giornata
          </button>
        </div>
        <div className="space-y-2">
          {days.map((d, i) => (
            <DayEditor
              key={i}
              day={d}
              onChange={(nd) => updateDay(i, nd)}
              onRemove={() => removeDay(i)}
              impianto={impianto}
            />
          ))}
          {days.length === 0 && (
            <p className="text-[12px] text-muted-foreground italic text-center py-6 border border-dashed border-border rounded">
              Nessuna giornata. Aggiungi la prima giornata del turno.
            </p>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="sticky bottom-0 bg-background/90 backdrop-blur border-t border-border-subtle py-3 -mx-4 px-4">
        {error && (
          <div className="text-[12px] text-destructive bg-destructive/10 p-2 rounded mb-2 flex items-center gap-2">
            <AlertCircle size={14} /> {error}
          </div>
        )}
        {success && (
          <div className="text-[12px] text-success bg-success/10 p-2 rounded mb-2 flex items-center gap-2">
            <CheckCircle size={14} /> Salvato! Reindirizzo...
          </div>
        )}
        <div className="flex items-center justify-end gap-2">
          <button
            onClick={() => navigate("/pdc")}
            className="text-[12px] px-4 py-2 border border-border rounded hover:bg-muted"
          >
            Annulla
          </button>
          <button
            onClick={save}
            disabled={saving}
            className={cn(
              "text-[12px] px-4 py-2 rounded flex items-center gap-1 font-semibold",
              saving
                ? "bg-muted text-muted-foreground cursor-wait"
                : "bg-primary text-primary-foreground hover:bg-primary/90"
            )}
          >
            <Save size={12} />
            {saving ? "Salvataggio..." : editId ? "Aggiorna turno" : "Crea turno"}
          </button>
        </div>
      </div>
    </div>
  )
}
