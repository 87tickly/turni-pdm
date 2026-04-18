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
  Home,
  Loader2,
  Moon,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { PdcGanttV2 as PdcGantt, type CrossDayDragPayload } from "@/components/PdcGanttV2"
import { TrainDetailDrawer as BlockDetailModal } from "@/components/TrainDetailDrawer"
// Alias drop-in: drawer destro al posto del modal centrato.
import {
  createPdcTurn,
  updatePdcTurn,
  getPdcTurn,
  getCalendarPeriodicity,
  lookupTrainInGiroMateriale,
  findReturnTrain,
  trainCheck,
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
    minuti_accessori: b.minuti_accessori || "",
  }
}

function pdcBlockToInput(b: PdcBlock): PdcBlockInput {
  return {
    seq: b.seq,
    block_type: b.block_type,
    train_id: b.train_id,
    vettura_id: b.vettura_id,
    from_station: b.from_station,
    to_station: b.to_station,
    start_time: b.start_time,
    end_time: b.end_time,
    accessori_maggiorati: b.accessori_maggiorati === 1,
    minuti_accessori: b.minuti_accessori || "",
  }
}

// ── Calcoli derivati dai blocchi ───────────────────────────────
// Origine 03:00: i turni Trenord vanno da 03:00 a 03:00 del giorno dopo,
// quindi se vediamo 00:25 lo trattiamo come "21h25m dall'origine".
const STATS_ORIGIN_HOUR = 3
function _toRelMin(hhmm: string | undefined): number | null {
  if (!hhmm || !/^\d{1,2}:\d{2}$/.test(hhmm)) return null
  const [h, m] = hhmm.split(":").map(Number)
  const hourAdj = h < STATS_ORIGIN_HOUR ? h + 24 : h
  return (hourAdj - STATS_ORIGIN_HOUR) * 60 + m
}
function _relToHhmm(min: number): string {
  const abs = (STATS_ORIGIN_HOUR * 60 + min) % (24 * 60)
  const h = Math.floor(abs / 60)
  const m = abs % 60
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}`
}

interface DayStats {
  start_time: string      // HH:MM (assoluto)
  end_time: string        // HH:MM (assoluto, puo' essere giorno dopo)
  lavoro_min: number
  condotta_min: number
  km: number
  notturno: boolean
}

function computeDayStats(blocks: PdcBlockInput[] | undefined): DayStats {
  const empty: DayStats = { start_time: "", end_time: "", lavoro_min: 0, condotta_min: 0, km: 0, notturno: false }
  if (!blocks || blocks.length === 0) return empty

  let firstStart: number | null = null
  let lastEnd: number | null = null
  let condotta = 0

  for (const b of blocks) {
    const sm = _toRelMin(b.start_time)
    if (sm === null) continue
    const em = _toRelMin(b.end_time) ?? sm  // blocchi puntuali (CVp/CVa) usano start
    if (firstStart === null || sm < firstStart) firstStart = sm
    if (lastEnd === null || em > lastEnd) lastEnd = em
    if (b.block_type === "train" && em > sm) condotta += em - sm
  }

  if (firstStart === null || lastEnd === null) return empty

  const lavoro = lastEnd - firstStart
  // Notturno: se l'intervallo include qualche minuto tra 00:01 e 05:00 assoluti.
  // In rel: 00:00 = 21*60=1260, 05:00 = 26*60=1560 → range [1261,1560].
  const notturno = !(lastEnd <= 1260 || firstStart >= 1560)

  return {
    start_time: _relToHhmm(firstStart),
    end_time: _relToHhmm(lastEnd),
    lavoro_min: lavoro,
    condotta_min: condotta,
    km: 0,  // futuro: somma km dei segmenti
    notturno,
  }
}

function _fmtHm(min: number): string {
  if (min <= 0) return "—"
  const h = Math.floor(min / 60)
  const m = min % 60
  return `${h}h${m.toString().padStart(2, "0")}`
}

// Mini-componente: chip "Etichetta valore" leggera
function Stat({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <span className="inline-flex items-baseline gap-1">
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</span>
      <span className={`text-[12px] font-semibold ${mono ? "font-mono tabular-nums" : ""}`}>{value}</span>
    </span>
  )
}

// ── Sottocomponente: Editor blocco (chip-row stile Linear/Notion) ──────
//
// Una singola riga compatta per ogni blocco. I valori sono "chip"
// cliccabili che aprono un mini popover di edit inline. Niente piu'
// form rettangolare con 6 input vuoti. Auto-fill al cambio del numero
// treno (debounce 600ms): legge il giro materiale e popola in
// automatico stazioni + orari + flag deadhead. Mostra un badge di
// origine ("◆ giro mat" / "◆ ARTURO Live" / "◇ manuale").

type ChipFieldName = "type" | "id" | "from" | "to" | "start" | "end" | "acc"

const BLOCK_TYPE_META: Record<PdcBlockInput["block_type"], { icon: string; label: string; color: string }> = {
  train:           { icon: "🚆",  label: "Treno",     color: "bg-blue-50 text-blue-800 border-blue-200" },
  coach_transfer:  { icon: "▭",   label: "Vettura",   color: "bg-slate-50 text-slate-700 border-slate-200" },
  cv_partenza:     { icon: "⏵",   label: "CVp",       color: "bg-violet-50 text-violet-800 border-violet-200" },
  cv_arrivo:       { icon: "⏸",   label: "CVa",       color: "bg-violet-50 text-violet-800 border-violet-200" },
  meal:            { icon: "🍴",  label: "Refez",     color: "bg-amber-50 text-amber-800 border-amber-200" },
  scomp:           { icon: "⏱",   label: "S.COMP",    color: "bg-cyan-50 text-cyan-800 border-cyan-200" },
  available:       { icon: "🛏",   label: "Riposo",    color: "bg-emerald-50 text-emerald-800 border-emerald-200" },
}

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
  const meta = BLOCK_TYPE_META[block.block_type] ?? BLOCK_TYPE_META.train
  const isTrain = block.block_type === "train"
  const isCv = block.block_type === "cv_partenza" || block.block_type === "cv_arrivo"
  const isCoach = block.block_type === "coach_transfer"
  const isPunctual = isCv

  const [editing, setEditing] = useState<ChipFieldName | null>(null)
  // Stato auto-fill per badge origine
  const [origin, setOrigin] = useState<"manual" | "giro" | "live" | "loading" | "miss" | null>(null)

  // ── Auto-fill al cambio train_id (debounced 600ms) ────────────
  useEffect(() => {
    if (!isTrain || !block.train_id || !block.train_id.trim()) {
      setOrigin(null)
      return
    }
    const tid = block.train_id.trim()
    setOrigin("loading")
    const handle = setTimeout(async () => {
      try {
        // 1. Tenta giro materiale
        const r = await lookupTrainInGiroMateriale(tid)
        if (r.found) {
          // Popola solo i campi vuoti (non sovrascrive edit utente)
          const patched: PdcBlockInput = { ...block }
          let changed = false
          if (!block.from_station && r.from_station) { patched.from_station = r.from_station; changed = true }
          if (!block.to_station   && r.to_station)   { patched.to_station   = r.to_station;   changed = true }
          if (!block.start_time   && r.dep_time)     { patched.start_time   = r.dep_time;     changed = true }
          if (!block.end_time     && r.arr_time)     { patched.end_time     = r.arr_time;     changed = true }
          if (changed) onChange(patched)
          setOrigin("giro")
          return
        }
        // 2. Fallback ARTURO Live
        const tc = await trainCheck(tid)
        if (tc.arturo_live?.found && tc.arturo_live.data) {
          const patched: PdcBlockInput = { ...block }
          let changed = false
          if (!block.from_station && tc.arturo_live.data.origin)      { patched.from_station = tc.arturo_live.data.origin;      changed = true }
          if (!block.to_station   && tc.arturo_live.data.destination) { patched.to_station   = tc.arturo_live.data.destination; changed = true }
          if (!block.start_time   && tc.arturo_live.data.dep_time)    { patched.start_time   = tc.arturo_live.data.dep_time;    changed = true }
          if (!block.end_time     && tc.arturo_live.data.arr_time)    { patched.end_time     = tc.arturo_live.data.arr_time;    changed = true }
          if (changed) onChange(patched)
          setOrigin("live")
          return
        }
        setOrigin("miss")
      } catch {
        setOrigin("miss")
      }
    }, 600)
    return () => clearTimeout(handle)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [block.train_id, isTrain])

  const updateField = <K extends keyof PdcBlockInput>(k: K, v: PdcBlockInput[K]) => {
    onChange({ ...block, [k]: v })
  }

  const closeEdit = () => setEditing(null)

  return (
    <div
      className="group flex items-center gap-1.5 py-1.5 px-2 rounded-md hover:bg-muted/40 transition-colors text-[11px] relative"
      onClick={(e) => {
        // Click fuori dai chip: chiude eventuale edit
        if (e.target === e.currentTarget) closeEdit()
      }}
    >
      {/* Drag handle (placeholder) + index */}
      <span className="font-mono text-muted-foreground/60 w-5 text-right select-none">{index}</span>

      {/* Chip TIPO */}
      <Chip
        active={editing === "type"}
        className={meta.color}
        onClick={() => setEditing(editing === "type" ? null : "type")}
        title="Cambia tipo blocco"
      >
        <span className="text-[12px]">{meta.icon}</span>
        <span className="font-semibold">{meta.label}</span>
      </Chip>
      {editing === "type" && (
        <Popover onClose={closeEdit}>
          <div className="grid grid-cols-2 gap-1 p-1">
            {BLOCK_TYPES.map((t) => (
              <button key={t.value}
                className="text-[11px] text-left px-2 py-1 rounded hover:bg-muted flex items-center gap-1.5"
                onClick={() => { updateField("block_type", t.value); closeEdit() }}>
                <span>{t.icon}</span> {t.label}
              </button>
            ))}
          </div>
        </Popover>
      )}

      {/* Chip ID (treno o vettura) */}
      {(isTrain || isCv) && (
        <Chip
          active={editing === "id"}
          className="bg-white border-slate-300 font-mono"
          onClick={() => setEditing(editing === "id" ? null : "id")}
          title="Numero treno"
        >
          {block.train_id || <span className="text-muted-foreground italic">treno?</span>}
          {isTrain && origin === "loading" && <Loader2 size={9} className="animate-spin text-muted-foreground" />}
          {isTrain && origin === "giro" && <span title="Trovato nel giro materiale" className="text-emerald-600">◆</span>}
          {isTrain && origin === "live" && <span title="Trovato in ARTURO Live" className="text-blue-600">◆</span>}
          {isTrain && origin === "miss" && <span title="Non trovato — inserito manualmente" className="text-amber-600">◇</span>}
        </Chip>
      )}
      {isCoach && (
        <Chip
          active={editing === "id"}
          className="bg-white border-slate-300 font-mono italic"
          onClick={() => setEditing(editing === "id" ? null : "id")}
          title="Numero vettura"
        >
          ({block.vettura_id || <span className="text-muted-foreground">vett?</span>}
        </Chip>
      )}
      {editing === "id" && (
        <Popover onClose={closeEdit}>
          <input
            autoFocus
            type="text"
            className="px-2 py-1 border border-border rounded font-mono text-[12px] w-32"
            placeholder={isCoach ? "Numero vettura" : "Numero treno"}
            value={isCoach ? (block.vettura_id || "") : (block.train_id || "")}
            onChange={(e) =>
              isCoach
                ? updateField("vettura_id", e.target.value)
                : updateField("train_id", e.target.value)
            }
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === "Escape") closeEdit() }}
          />
        </Popover>
      )}

      {/* Chip TRATTA from→to */}
      {block.block_type !== "scomp" && block.block_type !== "available" && (
        <Chip
          active={editing === "from" || editing === "to"}
          className="bg-white border-slate-300 font-mono"
          onClick={() => setEditing(editing === "from" ? null : "from")}
          title="Stazione partenza → arrivo"
        >
          {block.from_station || <span className="text-muted-foreground italic">da?</span>}
          {!isPunctual && (
            <>
              <span className="text-muted-foreground/60 mx-0.5">→</span>
              {block.to_station || <span className="text-muted-foreground italic">a?</span>}
            </>
          )}
        </Chip>
      )}
      {editing === "from" && (
        <Popover onClose={closeEdit}>
          <div className="flex items-center gap-1 p-1">
            <input autoFocus type="text" className="px-2 py-1 border border-border rounded text-[11px] w-28"
              placeholder="da" value={block.from_station || ""}
              onChange={(e) => updateField("from_station", e.target.value)} />
            {!isPunctual && (
              <>
                <span className="text-muted-foreground">→</span>
                <input type="text" className="px-2 py-1 border border-border rounded text-[11px] w-28"
                  placeholder="a" value={block.to_station || ""}
                  onChange={(e) => updateField("to_station", e.target.value)} />
              </>
            )}
          </div>
        </Popover>
      )}

      {/* Chip ORARI start–end (o solo start per puntuali) */}
      <Chip
        active={editing === "start"}
        className="bg-white border-slate-300 font-mono"
        onClick={() => setEditing(editing === "start" ? null : "start")}
        title="Orari del blocco"
      >
        {block.start_time || <span className="text-muted-foreground italic">--:--</span>}
        {!isPunctual && (
          <>
            <span className="text-muted-foreground/60">–</span>
            {block.end_time || <span className="text-muted-foreground italic">--:--</span>}
          </>
        )}
      </Chip>
      {editing === "start" && (
        <Popover onClose={closeEdit}>
          <div className="flex items-center gap-1 p-1">
            <input autoFocus type="time" className="px-2 py-1 border border-border rounded font-mono text-[11px]"
              value={block.start_time || ""}
              onChange={(e) => updateField("start_time", e.target.value)} />
            {!isPunctual && (
              <>
                <span className="text-muted-foreground">–</span>
                <input type="time" className="px-2 py-1 border border-border rounded font-mono text-[11px]"
                  value={block.end_time || ""}
                  onChange={(e) => updateField("end_time", e.target.value)} />
              </>
            )}
          </div>
        </Popover>
      )}

      {/* Chip ACCESSORI (sempre visibile per i treni, opzionale altri) */}
      {(isTrain || isCv || block.block_type === "meal") && (
        <Chip
          active={editing === "acc"}
          className={(block.minuti_accessori
            ? "bg-amber-50 border-amber-200 text-amber-800"
            : "bg-white border-slate-300 text-muted-foreground")
            + " font-mono"}
          onClick={() => setEditing(editing === "acc" ? null : "acc")}
          title="Minuti accessori (es. 5/5 = 5 prep + 5 consegna)"
        >
          acc {block.minuti_accessori || <span className="italic">5/5</span>}
        </Chip>
      )}
      {editing === "acc" && (
        <Popover onClose={closeEdit}>
          <div className="flex items-center gap-1 p-1">
            <input autoFocus type="text" className="px-2 py-1 border border-border rounded font-mono text-[11px] w-20 text-center"
              placeholder="5/5" value={block.minuti_accessori || ""}
              onChange={(e) => updateField("minuti_accessori", e.target.value)} />
            <button
              type="button"
              className={"text-[10px] px-2 py-1 rounded border " + (block.accessori_maggiorati
                ? "bg-red-50 border-red-200 text-red-700"
                : "bg-white border-slate-300 text-muted-foreground")}
              onClick={() => updateField("accessori_maggiorati", !block.accessori_maggiorati)}
              title="Accessori maggiorati (preriscaldo)"
            >
              ● magg.
            </button>
          </div>
        </Popover>
      )}

      {/* Spacer + azioni a destra */}
      <span className="flex-1" />

      <button
        onClick={(e) => { e.stopPropagation(); onRemove() }}
        className="opacity-0 group-hover:opacity-100 transition-opacity text-destructive hover:bg-destructive/10 p-1 rounded"
        title="Rimuovi blocco"
        type="button"
      >
        <X size={12} />
      </button>
    </div>
  )
}

// Mini-componente: chip generico cliccabile
function Chip({
  children, active, className = "", onClick, title,
}: {
  children: React.ReactNode
  active?: boolean
  className?: string
  onClick?: () => void
  title?: string
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={(e) => { e.stopPropagation(); onClick?.() }}
      className={
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-[11px] " +
        "transition-colors hover:brightness-95 " +
        className + (active ? " ring-2 ring-blue-400 ring-offset-1" : "")
      }
    >
      {children}
    </button>
  )
}

// Popover overlay sotto il chip cliccato
function Popover({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [onClose])
  return (
    <div
      className="absolute top-full left-12 mt-1 z-20 bg-card border border-border rounded-lg shadow-lg"
      onClick={(e) => e.stopPropagation()}
    >
      {children}
    </div>
  )
}

// ── Sottocomponente: Editor giornata ───────────────────────────

function DayEditor({
  day,
  dayIndex,
  onChange,
  onRemove,
  impianto,
  onCrossDayDragStart,
  onCrossDayDrop,
}: {
  day: PdcDayInput
  dayIndex: number
  onChange: (d: PdcDayInput) => void
  onRemove: () => void
  impianto: string
  onCrossDayDragStart?: (payload: CrossDayDragPayload) => void
  onCrossDayDrop?: (payload: CrossDayDragPayload, targetGanttId: string) => void
}) {
  const [open, setOpen] = useState(true)
  const [returnSearching, setReturnSearching] = useState(false)
  const [returnCandidates, setReturnCandidates] = useState<ReturnTrain[] | null>(
    null
  )
  const [returnMsg, setReturnMsg] = useState("")
  const [detailModal, setDetailModal] = useState<{
    block: PdcBlock
    index: number
    mode: "detail" | "warn"
  } | null>(null)
  const [actionToast, setActionToast] = useState("")

  // ── Auto-calcolo stats della giornata dai blocchi ────────────
  // Ogni volta che blocks cambia, ricalcolo start/end/lavoro/condotta/km/notturno
  // e li propago via onChange. Confronto con i valori attuali per evitare loop.
  useEffect(() => {
    if (day.is_disponibile) return
    const calc = computeDayStats(day.blocks)
    const changed =
      calc.start_time !== (day.start_time || "") ||
      calc.end_time !== (day.end_time || "") ||
      calc.lavoro_min !== (day.lavoro_min || 0) ||
      calc.condotta_min !== (day.condotta_min || 0) ||
      (calc.notturno ? 1 : 0) !== (day.notturno ? 1 : 0)
    if (changed) {
      onChange({
        ...day,
        start_time: calc.start_time,
        end_time: calc.end_time,
        lavoro_min: calc.lavoro_min,
        condotta_min: calc.condotta_min,
        // km non ricalcolato (no info nei blocchi); preservo se gia' settato
        notturno: calc.notturno,
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [day.blocks, day.is_disponibile])

  const updateBlock = (i: number, b: PdcBlockInput) => {
    const blocks = [...(day.blocks || [])]
    blocks[i] = b
    onChange({ ...day, blocks })
  }
  const addBlock = () => {
    const blocks = [...(day.blocks || [])]
    // Default: 5 min accessori inizio + 5 min accessori fine sui treni
    blocks.push({ block_type: "train", seq: blocks.length, minuti_accessori: "5/5" })
    onChange({ ...day, blocks })
  }
  const removeBlock = (i: number) => {
    const blocks = (day.blocks || []).filter((_, idx) => idx !== i)
    onChange({ ...day, blocks: blocks.map((b, idx) => ({ ...b, seq: idx })) })
  }

  // Trova rientro in vettura: usa l'ultima stazione dell'ultimo blocco
  // con to_station e cerca treni per il deposito via ARTURO Live.
  // Strategia con retry: se la prima ricerca filtrata sull'after_time
  // non trova nulla, riprova senza filtro temporale per mostrare comunque
  // candidati (utile per turni mattutini molto presto).
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
    // Normalizzo in MAIUSCOLO per evitare problemi di case sensitivity
    // sull'autocomplete stazioni di ARTURO Live (sebbene il backend
    // gia' fa upper, alcune ricerche fuzzy danno risultati diversi).
    const fromStation = (lastWithStation.to_station || "").trim().toUpperCase()
    const toStation = impianto.trim().toUpperCase()
    const afterTime = lastWithStation.end_time || "00:00"
    setReturnSearching(true)
    setReturnMsg("")
    setReturnCandidates(null)
    try {
      console.log("[rientro] cerca", { fromStation, toStation, afterTime })
      const r = await findReturnTrain(fromStation, toStation, afterTime)
      console.log("[rientro] risposta filtrata", r)

      if (r.error) {
        setReturnMsg(`⚠ ${r.error} — verifica i nomi delle stazioni (es. "TORINO PORTA NUOVA" invece di "torino")`)
      } else if (r.return_trains.length === 0) {
        // Retry senza filtro orario: usa "00:00" per mostrare tutti i treni
        // di oggi, anche prima dell'orario richiesto.
        setReturnMsg(`Nessuno dopo ${afterTime}, cerco anche prima...`)
        const r2 = await findReturnTrain(fromStation, toStation, "00:00")
        console.log("[rientro] risposta senza filtro", r2)
        if (r2.return_trains.length === 0) {
          setReturnMsg(
            `Nessun treno ARTURO Live trovato da ${fromStation} → ${toStation} ` +
            `(verifica nomi stazioni: per Torino prova "TORINO PORTA NUOVA", ` +
            `per Milano "MILANO CENTRALE", ecc.)`
          )
        } else {
          setReturnCandidates(r2.return_trains)
          setReturnMsg(
            `Nessun treno DOPO ${afterTime} da ${fromStation} → ${toStation}. ` +
            `Mostro ${r2.return_trains.length} treno/i trovati nel resto della giornata.`
          )
        }
      } else {
        setReturnCandidates(r.return_trains)
        setReturnMsg(
          `${r.return_trains.length} treno/i trovato/i da ${fromStation} → ${toStation}`
        )
      }
    } catch (e) {
      console.error("[rientro] errore", e)
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
      vettura_id: rt.train_number,
      from_station: rt.from_station || "",
      to_station: rt.to_station || impianto,
      start_time: rt.dep_time,
      end_time: rt.arr_time,
    })
    onChange({ ...day, blocks })
    setReturnCandidates(null)
    setReturnMsg(`✓ aggiunto rientro vettura treno ${rt.train_number}`)
    setTimeout(() => setReturnMsg(""), 3000)
  }

  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{
        backgroundColor: "var(--color-surface-container-lowest)",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      <div
        className="flex items-center gap-2 px-3 py-2.5"
        style={{ backgroundColor: "var(--color-surface-container-low)" }}
      >
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
            <div
              className="flex items-center flex-wrap gap-2 text-[11px] rounded-md px-3 py-2"
              style={{ backgroundColor: "var(--color-surface-container-low)" }}
            >
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Calcolato dai blocchi</span>
              <span className="text-muted-foreground">·</span>
              <Stat label="Inizio" value={day.start_time || "—"} mono />
              <span className="text-muted-foreground">→</span>
              <Stat label="Fine" value={day.end_time || "—"} mono />
              <span className="text-muted-foreground">·</span>
              <Stat label="Lav" value={_fmtHm(day.lavoro_min || 0)} mono />
              <Stat label="Cct" value={_fmtHm(day.condotta_min || 0)} mono />
              <Stat label="Km" value={(day.km || 0).toString()} mono />
              {day.notturno && (
                <span className="bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded text-[10px] font-mono flex items-center gap-1">
                  <Moon size={10} /> notturno
                </span>
              )}
              <details className="ml-auto">
                <summary className="text-[10px] text-muted-foreground cursor-pointer hover:text-foreground select-none">
                  override manuale
                </summary>
                <div className="absolute z-10 mt-1 right-0 w-[420px] bg-card border border-border rounded-lg p-2 shadow-lg space-y-2">
                  <p className="text-[10px] text-muted-foreground italic">
                    Sovrascrivi i valori calcolati. Se modifichi qui, le modifiche resteranno
                    fino a quando non cambi un blocco (che ricalcolera' tutto).
                  </p>
                  <div className="grid grid-cols-2 gap-2">
                    <label className="flex items-center gap-1 text-[11px]">
                      <span className="text-muted-foreground min-w-[55px]">Inizio</span>
                      <input type="time" value={day.start_time || ""} className="flex-1 px-1.5 py-0.5 border border-border rounded font-mono text-[11px]"
                        onChange={(e) => onChange({ ...day, start_time: e.target.value })} />
                    </label>
                    <label className="flex items-center gap-1 text-[11px]">
                      <span className="text-muted-foreground min-w-[55px]">Fine</span>
                      <input type="time" value={day.end_time || ""} className="flex-1 px-1.5 py-0.5 border border-border rounded font-mono text-[11px]"
                        onChange={(e) => onChange({ ...day, end_time: e.target.value })} />
                    </label>
                    <label className="flex items-center gap-1 text-[11px]">
                      <span className="text-muted-foreground min-w-[55px]">Lav min</span>
                      <input type="number" value={day.lavoro_min || 0} className="flex-1 px-1.5 py-0.5 border border-border rounded text-[11px]"
                        onChange={(e) => onChange({ ...day, lavoro_min: parseInt(e.target.value) || 0 })} />
                    </label>
                    <label className="flex items-center gap-1 text-[11px]">
                      <span className="text-muted-foreground min-w-[55px]">Cct min</span>
                      <input type="number" value={day.condotta_min || 0} className="flex-1 px-1.5 py-0.5 border border-border rounded text-[11px]"
                        onChange={(e) => onChange({ ...day, condotta_min: parseInt(e.target.value) || 0 })} />
                    </label>
                    <label className="flex items-center gap-1 text-[11px]">
                      <span className="text-muted-foreground min-w-[55px]">Km</span>
                      <input type="number" value={day.km || 0} className="flex-1 px-1.5 py-0.5 border border-border rounded text-[11px]"
                        onChange={(e) => onChange({ ...day, km: parseInt(e.target.value) || 0 })} />
                    </label>
                    <label className="flex items-center gap-1 text-[11px]">
                      <span className="text-muted-foreground min-w-[55px]">Rip min</span>
                      <input type="number" value={day.riposo_min || 0} className="flex-1 px-1.5 py-0.5 border border-border rounded text-[11px]"
                        onChange={(e) => onChange({ ...day, riposo_min: parseInt(e.target.value) || 0 })} />
                    </label>
                  </div>
                </div>
              </details>
            </div>
          )}

          {!day.is_disponibile && (
            <>
              {/* Gantt visuale interattivo */}
              <div
                className="pt-3 -mx-3 -mb-3 px-3 pb-3"
                style={{
                  backgroundColor: "var(--color-surface-container-low)",
                  marginTop: "10px",
                }}
              >
                <p className="text-[10px] text-muted-foreground mb-1">
                  Trascina un blocco per spostarlo, trascina i bordi per ridimensionarlo, clicca sulla timeline vuota per aggiungere un nuovo blocco.
                </p>
                <PdcGantt
                  blocks={(day.blocks || []).map(b => inputToPdcBlock(b))}
                  startTime={day.start_time}
                  endTime={day.end_time}
                  label={`g${day.day_number} ${day.periodicita}`}
                  ganttId={`day-${dayIndex}`}
                  onCrossDayDragStart={onCrossDayDragStart}
                  onCrossDayDrop={onCrossDayDrop}
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
                      minuti_accessori: "5/5",  // default accessori inizio/fine
                    })
                    onChange({ ...day, blocks })
                  }}
                  onAction={(act, _block, idx) => {
                    if (act === "delete") {
                      if (!confirm("Eliminare il blocco? Se e' un treno con CVp/CVa agganciati verranno rimossi anche quelli.")) return
                      const src = [...(day.blocks || [])]
                      // Se e' un treno: rimuovi anche CVp prima e CVa dopo se adiacenti
                      const target = src[idx]
                      const toRemove = new Set<number>([idx])
                      if (target?.block_type === "train") {
                        const prev = src[idx - 1]
                        if (prev && prev.block_type === "cv_partenza") toRemove.add(idx - 1)
                        const next = src[idx + 1]
                        if (next && next.block_type === "cv_arrivo") toRemove.add(idx + 1)
                      }
                      const blocks = src
                        .filter((_, i) => !toRemove.has(i))
                        .map((b, i) => ({ ...b, seq: i }))
                      onChange({ ...day, blocks })
                      return
                    }
                    if (act === "duplicate") {
                      const src = [...(day.blocks || [])]
                      const orig = src[idx]
                      if (!orig) return
                      const copy = { ...orig, seq: idx + 1 }
                      // Inserisce subito dopo l'originale
                      const blocks = [
                        ...src.slice(0, idx + 1),
                        copy,
                        ...src.slice(idx + 1),
                      ].map((b, i) => ({ ...b, seq: i }))
                      onChange({ ...day, blocks })
                      return
                    }
                    if (act === "edit") {
                      // Scroll all'editor come onBlockClick
                      const el = document.getElementById(`block-editor-${idx}`)
                      if (el) {
                        el.scrollIntoView({ behavior: "smooth", block: "center" })
                        el.classList.add("ring-2", "ring-primary")
                        setTimeout(() => el.classList.remove("ring-2", "ring-primary"), 1500)
                      }
                      return
                    }
                    if (act === "detail" || act === "warn") {
                      const src = (day.blocks || [])[idx]
                      if (!src) return
                      setDetailModal({
                        block: inputToPdcBlock(src),
                        index: idx,
                        mode: act,
                      })
                      return
                    }
                    if (act === "history") {
                      // Storico ritardi: usa il modale detail (mostra ARTURO Live
                      // con delay e stato corrente). Grafico 30gg: futuro.
                      const src = (day.blocks || [])[idx]
                      if (!src) return
                      setDetailModal({
                        block: inputToPdcBlock(src),
                        index: idx,
                        mode: "detail",
                      })
                      return
                    }
                    if (act === "link") {
                      // Collega al giro materiale: interroga /train-check e
                      // sostituisce gli orari/stazioni del blocco con quelli
                      // ufficiali. Priorita': giro materiale > ARTURO Live.
                      const src = (day.blocks || [])[idx]
                      if (!src) {
                        setActionToast("Blocco non trovato")
                        setTimeout(() => setActionToast(""), 2500)
                        return
                      }
                      if (src.block_type !== "train") {
                        setActionToast(`Collegamento disponibile solo per i treni (questo e' '${src.block_type}')`)
                        setTimeout(() => setActionToast(""), 3500)
                        return
                      }
                      if (!src.train_id || !String(src.train_id).trim()) {
                        setActionToast("Il treno non ha un numero — aggiungilo nell'editor sotto")
                        setTimeout(() => setActionToast(""), 3500)
                        return
                      }
                      const trainId = String(src.train_id).trim()
                      setActionToast(`Verifica treno ${trainId}...`)
                      trainCheck(trainId).then((check) => {
                        // Log diagnostico (utile in DevTools)
                        console.log("[link]", trainId, check)

                        let newStart = ""
                        let newEnd = ""
                        let newFrom = ""
                        let newTo = ""
                        let srcName = ""
                        if (check.db_internal?.found && check.db_internal.data) {
                          newStart = check.db_internal.data.dep_time || ""
                          newEnd = check.db_internal.data.arr_time || ""
                          newFrom = check.db_internal.data.from_station || ""
                          newTo = check.db_internal.data.to_station || ""
                          srcName = "giro materiale"
                        } else if (check.arturo_live?.found && check.arturo_live.data) {
                          newStart = check.arturo_live.data.dep_time || ""
                          newEnd = check.arturo_live.data.arr_time || ""
                          newFrom = check.arturo_live.data.origin || ""
                          newTo = check.arturo_live.data.destination || ""
                          srcName = "ARTURO Live"
                        }
                        if (!newStart || !newEnd) {
                          // Diagnostica granulare
                          const inGiro = check.db_internal?.found ? "trovato" : "NON trovato"
                          const inLive = check.arturo_live?.found ? "trovato" : "NON trovato"
                          const inPdc = check.pdc?.found
                            ? `trovato in ${check.pdc.results.length} turni PdC`
                            : "non in nessun PdC"
                          setActionToast(
                            `Treno ${trainId} senza orari canonici. Giro materiale: ${inGiro}. ARTURO Live: ${inLive}. ${inPdc}.`,
                          )
                          setTimeout(() => setActionToast(""), 6000)
                          return
                        }
                        const blocks = [...(day.blocks || [])]
                        blocks[idx] = {
                          ...blocks[idx],
                          start_time: newStart,
                          end_time: newEnd,
                          from_station: newFrom || blocks[idx].from_station,
                          to_station: newTo || blocks[idx].to_station,
                        }
                        onChange({ ...day, blocks })
                        setActionToast(`✓ Treno ${trainId} allineato a ${srcName}: ${newStart} → ${newEnd} (${newFrom}→${newTo})`)
                        setTimeout(() => setActionToast(""), 5000)
                      }).catch((err) => {
                        console.error("[link] errore trainCheck", err)
                        setActionToast(`Errore /train-check per ${trainId}: ${err?.message || "rete o backend offline"}`)
                        setTimeout(() => setActionToast(""), 5000)
                      })
                      return
                    }
                    if (act === "move") {
                      setActionToast("Trascina direttamente il blocco sull'asse temporale per spostarlo, oppure trascinalo su un'altra giornata per il cross-day move")
                      setTimeout(() => setActionToast(""), 4500)
                      return
                    }
                    console.log("[PdcBuilder] azione non ancora collegata:", act)
                  }}
                />
                {actionToast && (
                  <div className="mt-2 text-[11px] text-blue-800 bg-blue-50 border border-blue-200 rounded px-3 py-1.5">
                    {actionToast}
                  </div>
                )}
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
                      <span className="font-mono font-semibold">{rt.train_number}</span>
                      {rt.category && (
                        <span className="text-[9px] text-muted-foreground">
                          {rt.category}
                        </span>
                      )}
                      <span className="text-muted-foreground">
                        {rt.from_station} → {rt.to_station}
                      </span>
                      <span className="font-mono text-[10px]">
                        {rt.dep_time} – {rt.arr_time}
                      </span>
                      {rt.destination_finale && rt.destination_finale !== rt.to_station && (
                        <span className="text-[9px] text-muted-foreground italic">
                          (dest. finale: {rt.destination_finale})
                        </span>
                      )}
                      {(rt.delay !== undefined && rt.delay > 0) && (
                        <span className="text-[9px] text-amber-700">+{rt.delay}m</span>
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

      {/* Modale dettaglio blocco (triple-check DB interno + PdC + ARTURO Live) */}
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
    <div
      className="rounded-lg p-3"
      style={{
        backgroundColor: "var(--color-surface-container-lowest)",
        boxShadow: "var(--shadow-sm)",
      }}
    >
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

  // ── Drag cross-day tra giornate dello stesso turno ────────────
  const [crossDragSourceDay, setCrossDragSourceDay] = useState<number | null>(null)
  const [crossInfoMsg, setCrossInfoMsg] = useState("")

  const handleCrossDayDragStart = useCallback((sourceDayIdx: number) => {
    setCrossDragSourceDay(sourceDayIdx)
  }, [])

  const handleCrossDayDrop = useCallback(
    (payload: CrossDayDragPayload, targetGanttId: string) => {
      // targetGanttId = `day-${idx}`
      const targetDayIdx = parseInt(targetGanttId.replace("day-", ""), 10)
      const sourceDayIdx = parseInt(payload.ganttId.replace("day-", ""), 10)
      if (!Number.isFinite(targetDayIdx) || !Number.isFinite(sourceDayIdx)) return
      if (targetDayIdx === sourceDayIdx) {
        setCrossDragSourceDay(null)
        return
      }

      // STEP 1: SINCRONO — applica subito il move con orari originali
      // (UI fluida, nessuna attesa per la rete)
      const originalBlockInput = pdcBlockToInput(payload.block)
      setDays((prev) => {
        const next = [...prev]
        // Rimuovi dal giorno source il blocco + CVp/CVa agganciati
        const source = { ...next[sourceDayIdx] }
        const sBlocks = [...(source.blocks || [])]
        const toRemove = new Set<number>([payload.index])
        if (payload.block.block_type === "train") {
          if (sBlocks[payload.index - 1]?.block_type === "cv_partenza")
            toRemove.add(payload.index - 1)
          if (sBlocks[payload.index + 1]?.block_type === "cv_arrivo")
            toRemove.add(payload.index + 1)
        }
        source.blocks = sBlocks
          .filter((_, idx) => !toRemove.has(idx))
          .map((b, idx) => ({ ...b, seq: idx }))
        next[sourceDayIdx] = source

        // Aggiungi al giorno target
        const target = { ...next[targetDayIdx] }
        const tBlocks = [...(target.blocks || [])]
        const added: PdcBlockInput[] = []
        if (payload.linkedCvp) added.push(pdcBlockToInput(payload.linkedCvp))
        added.push(originalBlockInput)
        if (payload.linkedCva) added.push(pdcBlockToInput(payload.linkedCva))
        target.blocks = [...tBlocks, ...added].map((b, idx) => ({ ...b, seq: idx }))
        next[targetDayIdx] = target
        return next
      })

      setCrossDragSourceDay(null)

      // STEP 2: ASYNC — auto-correzione orari in background
      if (payload.block.block_type === "train" && payload.block.train_id) {
        const trainId = payload.block.train_id
        trainCheck(trainId)
          .then((check) => {
            let newStart = ""
            let newEnd = ""
            let newFrom = ""
            let newTo = ""
            let srcName = ""
            if (check.db_internal?.found && check.db_internal.data) {
              newStart = check.db_internal.data.dep_time || ""
              newEnd = check.db_internal.data.arr_time || ""
              newFrom = check.db_internal.data.from_station || ""
              newTo = check.db_internal.data.to_station || ""
              srcName = "giro materiale"
            } else if (check.arturo_live?.found && check.arturo_live.data) {
              newStart = check.arturo_live.data.dep_time || ""
              newEnd = check.arturo_live.data.arr_time || ""
              newFrom = check.arturo_live.data.origin || ""
              newTo = check.arturo_live.data.destination || ""
              srcName = "ARTURO Live"
            }
            if (!newStart || !newEnd) return
            if (newStart === payload.block.start_time && newEnd === payload.block.end_time) return

            // Patch del blocco appena spostato nel target
            setDays((prev) => {
              const next = [...prev]
              const target = { ...next[targetDayIdx] }
              target.blocks = (target.blocks || []).map((b) =>
                b.train_id === trainId &&
                b.block_type === "train" &&
                b.start_time === payload.block.start_time
                  ? {
                      ...b,
                      start_time: newStart,
                      end_time: newEnd,
                      from_station: newFrom || b.from_station,
                      to_station: newTo || b.to_station,
                    }
                  : b,
              )
              next[targetDayIdx] = target
              return next
            })
            setCrossInfoMsg(`Orari del treno ${trainId} allineati a ${srcName}: ${newStart} → ${newEnd}`)
            setTimeout(() => setCrossInfoMsg(""), 4000)
          })
          .catch(() => { /* silenzioso */ })
      }
      return // chiude la callback
      // (i due rami legacy sotto non vengono mai eseguiti — held over)
    },
    [],
  )

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
      <div className="mb-5 flex items-start justify-between">
        <div>
          <div
            className="text-[10px] font-bold uppercase mb-1"
            style={{
              color: "var(--color-on-surface-quiet)",
              letterSpacing: "0.12em",
            }}
          >
            {editId ? "Modifica turno PdC" : "Nuovo turno PdC"}
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
            {editId ? "Editor turno PdC" : "Nuovo turno PdC"}
          </h2>
          <p
            className="text-[13px] mt-0.5"
            style={{ color: "var(--color-on-surface-muted)" }}
          >
            {editId
              ? "Modifica un turno PdC esistente"
              : "Crea un turno PdC nel formato ufficiale Trenord"}
          </p>
        </div>
        <button
          onClick={() => navigate("/pdc")}
          className="text-[12px] px-3 py-1.5 rounded-md transition-colors"
          style={{ color: "var(--color-on-surface-muted)" }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor =
              "var(--color-surface-container-low)"
            e.currentTarget.style.color = "var(--color-on-surface-strong)"
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = "transparent"
            e.currentTarget.style.color = "var(--color-on-surface-muted)"
          }}
        >
          Annulla
        </button>
      </div>

      {/* Calendar preview */}
      <div className="mb-4">
        <CalendarPreview />
      </div>

      {/* Header turno */}
      <div
        className="rounded-lg p-4 mb-4"
        style={{
          backgroundColor: "var(--color-surface-container-lowest)",
          boxShadow: "var(--shadow-sm)",
        }}
      >
        <h3
          className="font-semibold mb-3"
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "13px",
            color: "var(--color-on-surface-strong)",
          }}
        >
          Dati del turno
        </h3>
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
              dayIndex={i}
              onChange={(nd) => updateDay(i, nd)}
              onRemove={() => removeDay(i)}
              impianto={impianto}
              onCrossDayDragStart={() => handleCrossDayDragStart(i)}
              onCrossDayDrop={handleCrossDayDrop}
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
        {crossInfoMsg && (
          <div className="text-[12px] text-emerald-800 bg-emerald-50 border border-emerald-200 p-2 rounded mb-2 flex items-center gap-2">
            ✓ {crossInfoMsg}
          </div>
        )}
        {crossDragSourceDay !== null && (
          <div className="text-[11px] text-blue-800 bg-blue-50 border border-blue-200 p-2 rounded mb-2">
            Trascina su un'altra giornata per spostare il treno
            (gli orari verranno allineati a giro materiale / ARTURO Live se disponibili)
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
