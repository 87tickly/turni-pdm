/**
 * Calendario agente — pagina "Chi lavora quando · 28 giorni".
 *
 * Implementazione dal design handoff Claude Design
 * (docs/PROMPT-claude-design-navigation.md + bundle HANDOFF-calendario-agente.md).
 *
 * Griglia CSS: 180px (PdC) + repeat(28, 72px) giorni. Sticky corner +
 * sticky header di settimana e giorno. Celle con 7 stati: work, rest,
 * fr, scomp, uncov, leave, locked.
 *
 * Dati: fetch reale da `/api/calendario-agente` (router backend creato
 * in sessione 2026-04-23). Quando il DB non ha ancora turni PdC importati,
 * il componente fa fallback sul dataset MOCK_ROWS per mantenere visibile
 * il design.
 */
import { useEffect, useMemo, useState } from "react"
import {
  ChevronLeft,
  ChevronRight,
  MapPin,
  Users,
  Filter,
  Search,
  Download,
  Bell,
  Info,
  Plus,
  X,
  Loader2,
  AlertTriangle,
} from "lucide-react"
import {
  getCalendarioAgente,
  type AgentCellState,
  type AgentGridCell,
  type AgentGridRow,
} from "@/lib/api"


// I tipi AgentCellState / AgentGridCell / AgentGridRow sono ora in
// lib/api.ts (condivisi col backend response schema). Importati sopra.


// ─────────────────────────────────────────────────────────────
// Mock data (da sostituire con getAgendaGrid quando backend pronto)
// ─────────────────────────────────────────────────────────────

function mockCell(state: AgentCellState, code?: string, hm?: string,
                   span?: number): AgentGridCell {
  const parts = (hm || "0:00").split(":")
  const min = parseInt(parts[0]) * 60 + parseInt(parts[1] || "0")
  return {
    date: "",
    state,
    turno_code: code ?? null,
    prestazione_min: min || null,
    span: span ?? null,
  }
}

function buildMockRow(code: string, name: string, matricola: string,
                       cells: AgentGridCell[]): AgentGridRow {
  const work = cells.filter((c) => c.state === "work" || c.state === "fr").length
  const rest = cells.filter((c) => c.state === "rest").length
  const uncov = cells.filter((c) => c.state === "uncov").length
  const hours = cells.reduce((acc, c) => acc + (c.prestazione_min || 0), 0)
  return {
    pdc_id: Math.floor(Math.random() * 10000),
    pdc_code: code,
    display_name: name,
    matricola,
    deposito: "MILANO",
    totals: { work, rest, uncov, hours_min: hours },
    cells,
  }
}

const MOCK_ROWS: AgentGridRow[] = [
  buildMockRow("AROR_C", "Moretti A.", "7832", [
    mockCell("work", "AROR 01", "8:15"),
    mockCell("work", "AROR 02", "7:42"),
    mockCell("rest"),
    mockCell("work", "AROR 03", "8:00"),
    mockCell("work", "AROR 01", "8:15"),
    mockCell("rest"),
    mockCell("rest"),
    mockCell("work", "AROR 04", "6:50"),
    mockCell("work", "AROR 05", "9:10"),
    mockCell("work", "AROR 02", "7:42"),
    mockCell("fr", "FR 11", "4:20"),
    mockCell("rest"),
    mockCell("work", "AROR 06", "5:55"),
    mockCell("rest"),
    mockCell("work", "AROR 01", "8:15"),
    mockCell("work", "AROR 03", "8:00"),
    mockCell("scomp", "S.COMP", "2:10"),
    mockCell("work", "AROR 04", "6:50"),
    mockCell("work", "AROR 07", "8:45"),
    mockCell("rest"),
    mockCell("rest"),
    mockCell("work", "AROR 02", "7:42"),
    mockCell("work", "AROR 01", "8:15"),
    mockCell("work", "AROR 05", "9:10"),
    mockCell("work", "AROR 03", "8:00"),
    mockCell("work", "AROR 04", "6:50"),
    mockCell("rest"),
    mockCell("leave", "PERM"),
  ]),
  buildMockRow("ALOR_C", "Bianchi L.", "6124", [
    mockCell("work", "ALOR 02", "7:30"),
    mockCell("rest"),
    mockCell("work", "ALOR 01", "8:05"),
    mockCell("work", "ALOR 04", "6:35"),
    mockCell("fr", "FR 07", "4:55"),
    mockCell("rest"),
    mockCell("rest"),
    mockCell("work", "ALOR 03", "8:20"),
    mockCell("work", "ALOR 02", "7:30"),
    mockCell("leave", "FERIE", "8 → 10 apr", 2),
    mockCell("rest"),
    mockCell("work", "ALOR 05", "8:50"),
    mockCell("rest"),
    mockCell("work", "ALOR 01", "8:05"),
    mockCell("work", "ALOR 06", "7:10"),
    mockCell("work", "ALOR 04", "6:35"),
    mockCell("work", "ALOR 02", "7:30"),
    mockCell("scomp", "S.COMP", "1:45"),
    mockCell("rest"),
    mockCell("rest"),
    mockCell("work", "ALOR 03", "8:20"),
    mockCell("work", "ALOR 01", "8:05"),
    mockCell("uncov"),
    mockCell("work", "ALOR 02", "7:30"),
    mockCell("work", "ALOR 05", "8:50"),
    mockCell("rest"),
    mockCell("rest"),
  ]),
  buildMockRow("BSR_C", "Russo D.", "5901", [
    mockCell("work", "BSR 02", "8:10"),
    mockCell("work", "BSR 01", "7:55"),
    mockCell("work", "BSR 03", "9:00"),
    mockCell("rest"),
    mockCell("work", "BSR 02", "8:10"),
    mockCell("work", "BSR 04", "6:40"),
    mockCell("rest"),
    mockCell("rest"),
    mockCell("work", "BSR 01", "7:55"),
    mockCell("work", "BSR 05", "8:30"),
    mockCell("work", "BSR 03", "9:00"),
    mockCell("work", "BSR 02", "8:10"),
    mockCell("rest"),
    mockCell("fr", "FR 03", "5:20"),
    mockCell("work", "BSR 04", "6:40"),
    mockCell("work", "BSR 01", "7:55"),
    mockCell("work", "BSR 02", "8:10"),
    mockCell("rest"),
    mockCell("work", "BSR 05", "8:30"),
    mockCell("uncov"),
    mockCell("rest"),
    mockCell("work", "BSR 03", "9:00"),
    mockCell("work", "BSR 01", "7:55"),
    mockCell("work", "BSR 02", "8:10"),
    mockCell("work", "BSR 04", "6:40"),
    mockCell("work", "BSR 05", "8:30"),
    mockCell("rest"),
    mockCell("rest"),
  ]),
  buildMockRow("MILC_C", "Gallo F.", "4478", [
    mockCell("leave", "FERIE", "30 mar → 5 apr · 7gg", 7),
    mockCell("work", "MILC 01", "8:25"),
    mockCell("work", "MILC 02", "7:40"),
    mockCell("work", "MILC 03", "9:15"),
    mockCell("rest"),
    mockCell("work", "MILC 01", "8:25"),
    mockCell("fr", "FR 12", "4:30"),
    mockCell("rest"),
    mockCell("work", "MILC 04", "6:55"),
    mockCell("work", "MILC 02", "7:40"),
    mockCell("uncov"),
    mockCell("work", "MILC 03", "9:15"),
    mockCell("work", "MILC 01", "8:25"),
    mockCell("rest"),
    mockCell("rest"),
    mockCell("work", "MILC 02", "7:40"),
    mockCell("work", "MILC 05", "8:05"),
    mockCell("work", "MILC 04", "6:55"),
    mockCell("work", "MILC 03", "9:15"),
    mockCell("work", "MILC 01", "8:25"),
    mockCell("rest"),
    mockCell("rest"),
  ]),
  buildMockRow("PVOR_C", "Ferrari M.", "3207", [
    mockCell("work", "PVOR 01", "7:25"),
    mockCell("work", "PVOR 02", "8:00"),
    mockCell("rest"),
    mockCell("work", "PVOR 03", "8:45"),
    mockCell("work", "PVOR 01", "7:25"),
    mockCell("work", "PVOR 04", "6:20"),
    mockCell("rest"),
    mockCell("fr", "FR 09", "5:10"),
    mockCell("rest"),
    mockCell("work", "PVOR 02", "8:00"),
    mockCell("work", "PVOR 01", "7:25"),
    mockCell("work", "PVOR 03", "8:45"),
    mockCell("rest"),
    mockCell("work", "PVOR 05", "9:30"),
    mockCell("work", "PVOR 04", "6:20"),
    mockCell("work", "PVOR 01", "7:25"),
    mockCell("work", "PVOR 02", "8:00"),
    mockCell("scomp", "S.COMP", "2:30"),
    mockCell("work", "PVOR 03", "8:45"),
    mockCell("rest"),
    mockCell("rest"),
    mockCell("work", "PVOR 01", "7:25"),
    mockCell("work", "PVOR 05", "9:30"),
    mockCell("work", "PVOR 04", "6:20"),
    mockCell("work", "PVOR 02", "8:00"),
    mockCell("work", "PVOR 01", "7:25"),
    mockCell("rest"),
    mockCell("rest"),
  ]),
  buildMockRow("VRR_C", "Colombo E.", "2918", [
    mockCell("work", "VRR 01", "8:30"),
    mockCell("work", "VRR 02", "7:50"),
    mockCell("work", "VRR 03", "9:05"),
    mockCell("rest"),
    mockCell("work", "VRR 01", "8:30"),
    mockCell("rest"),
    mockCell("work", "VRR 04", "6:45"),
    mockCell("work", "VRR 02", "7:50"),
    mockCell("work", "VRR 01", "8:30"),
    mockCell("work", "VRR 05", "8:15"),
    mockCell("rest"),
    mockCell("work", "VRR 03", "9:05"),
    mockCell("fr", "FR 05", "4:45"),
    mockCell("rest"),
    mockCell("work", "VRR 01", "8:30"),
    mockCell("uncov"),
    mockCell("work", "VRR 02", "7:50"),
    mockCell("work", "VRR 04", "6:45"),
    mockCell("work", "VRR 01", "8:30"),
    mockCell("rest"),
    mockCell("rest"),
    mockCell("work", "VRR 05", "8:15"),
    mockCell("work", "VRR 03", "9:05"),
    mockCell("work", "VRR 01", "8:30"),
    mockCell("work", "VRR 02", "7:50"),
    mockCell("scomp", "S.COMP", "1:55"),
    mockCell("rest"),
    mockCell("rest"),
  ]),
  buildMockRow("NOV_C", "Greco V.", "7711", [
    mockCell("work", "NOV 01", "8:05"),
    mockCell("work", "NOV 02", "7:35"),
    mockCell("work", "NOV 01", "8:05"),
    mockCell("rest"),
    mockCell("work", "NOV 03", "9:10"),
    mockCell("rest"),
    mockCell("work", "NOV 04", "6:25"),
    mockCell("work", "NOV 02", "7:35"),
    mockCell("work", "NOV 01", "8:05"),
    mockCell("scomp", "S.COMP", "2:15"),
    mockCell("work", "NOV 03", "9:10"),
    mockCell("work", "NOV 02", "7:35"),
    mockCell("rest"),
    mockCell("rest"),
    mockCell("uncov", "SCOPERTO", "2 gg", 2),
    mockCell("work", "NOV 04", "6:25"),
    mockCell("work", "NOV 01", "8:05"),
    mockCell("work", "NOV 03", "9:10"),
    mockCell("rest"),
    mockCell("rest"),
    mockCell("work", "NOV 02", "7:35"),
    mockCell("work", "NOV 01", "8:05"),
    mockCell("fr", "FR 06", "4:50"),
    mockCell("work", "NOV 03", "9:10"),
    mockCell("work", "NOV 04", "6:25"),
    mockCell("rest"),
    mockCell("rest"),
  ]),
]


// ─────────────────────────────────────────────────────────────
// Griglia giorni: 28 giorni (4 settimane ISO)
// ─────────────────────────────────────────────────────────────

// DAY_ROW e WEEK_BANDS sono calcolati dinamicamente dalla startDate
// nel componente principale (buildDayRow / buildWeekBands).


// ─────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────

function FilterPill({ icon: Icon, label, value }: {
  icon: typeof MapPin
  label: string
  value: string
}) {
  return (
    <button
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11.5px] transition-colors"
      style={{
        backgroundColor: "var(--color-surface-container)",
        color: "var(--color-on-surface-muted)",
      }}
    >
      <Icon size={12} strokeWidth={1.8} />
      <span>
        {label} · <strong style={{ color: "var(--color-on-surface-strong)" }}>{value}</strong>
      </span>
      <svg className="opacity-50" width={10} height={10} viewBox="0 0 24 24"
        fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="m6 9 6 6 6-6" />
      </svg>
    </button>
  )
}

function MiniKpi({ label, value, color, unit }: {
  label: string
  value: string | number
  color?: string
  unit?: string
}) {
  return (
    <div
      className="px-3 py-2 rounded-md min-w-[90px]"
      style={{ backgroundColor: "var(--color-surface-container-lowest)" }}
    >
      <div
        className="text-[9.5px] font-bold uppercase tracking-[0.1em]"
        style={{ color: "var(--color-on-surface-quiet)" }}
      >
        {label}
      </div>
      <div
        className="text-[20px] font-bold leading-tight"
        style={{
          color: color || "var(--color-on-surface-strong)",
          fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
        }}
      >
        {value}
        {unit && <span className="text-[12px] font-semibold ml-0.5">{unit}</span>}
      </div>
    </div>
  )
}

function LegendItem({ swatchClass, label, styleOverride }: {
  swatchClass?: string
  label: string
  styleOverride?: React.CSSProperties
}) {
  return (
    <div className="inline-flex items-center gap-1.5 text-[11px]"
      style={{ color: "var(--color-on-surface-muted)" }}>
      <span
        className={swatchClass}
        style={{
          display: "inline-block",
          width: 14,
          height: 10,
          borderRadius: 2,
          ...styleOverride,
        }}
      />
      {label}
    </div>
  )
}

function CellWork({ cell, selected }: { cell: AgentGridCell; selected?: boolean }) {
  const span = cell.span || 1
  const hm = cell.prestazione_min
    ? `${Math.floor(cell.prestazione_min / 60)}:${String(cell.prestazione_min % 60).padStart(2, "0")}`
    : null
  return (
    <div
      className="flex flex-col justify-center items-start gap-0.5 px-1.5 py-1 cursor-pointer transition-colors"
      style={{
        gridColumn: span > 1 ? `span ${span}` : undefined,
        backgroundColor: selected
          ? "var(--color-brand)"
          : "var(--color-surface-container-lowest)",
        color: selected ? "#fff" : undefined,
        minHeight: 52,
        boxShadow:
          "inset 1px 0 0 var(--color-ghost), inset 0 1px 0 var(--color-ghost)",
      }}
    >
      <span
        className="text-[10.5px] font-semibold truncate w-full"
        style={{
          color: selected ? "#fff" : "var(--color-on-surface-strong)",
          fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
        }}
      >
        {cell.turno_code}
      </span>
      {hm && (
        <span
          className="text-[10px]"
          style={{
            color: selected
              ? "rgba(255,255,255,0.80)"
              : "var(--color-on-surface-muted)",
            fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
          }}
        >
          {hm}
        </span>
      )}
    </div>
  )
}

function CellRest() {
  return (
    <div
      className="flex items-center justify-center"
      style={{
        minHeight: 52,
        backgroundColor: "var(--color-surface-container-low)",
        boxShadow:
          "inset 1px 0 0 var(--color-ghost), inset 0 1px 0 var(--color-ghost)",
      }}
    >
      <span
        className="text-[10px] opacity-40"
        style={{ color: "var(--color-on-surface-quiet)" }}
      >
        R
      </span>
    </div>
  )
}

function CellFr({ cell }: { cell: AgentGridCell }) {
  const hm = cell.prestazione_min
    ? `${Math.floor(cell.prestazione_min / 60)}:${String(cell.prestazione_min % 60).padStart(2, "0")}`
    : null
  return (
    <div
      className="bg-fr-gradient flex flex-col justify-center items-start gap-0.5 px-1.5 py-1 cursor-pointer"
      style={{
        minHeight: 52,
        boxShadow:
          "inset 1px 0 0 var(--color-ghost), inset 0 1px 0 var(--color-ghost)",
      }}
    >
      <span
        className="text-[10.5px] font-semibold text-white truncate w-full"
        style={{ fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)" }}
      >
        {cell.turno_code}
      </span>
      {hm && (
        <span
          className="text-[10px] text-white/70"
          style={{ fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)" }}
        >
          {hm}
        </span>
      )}
    </div>
  )
}

function CellScomp({ cell }: { cell: AgentGridCell }) {
  const hm = cell.prestazione_min
    ? `${Math.floor(cell.prestazione_min / 60)}:${String(cell.prestazione_min % 60).padStart(2, "0")}`
    : null
  return (
    <div
      className="flex flex-col justify-center items-start gap-0.5 px-1.5 py-1 cursor-pointer"
      style={{
        minHeight: 52,
        backgroundColor: "rgba(2,132,199,0.10)",
        boxShadow:
          "inset 1px 0 0 var(--color-ghost), inset 0 1px 0 var(--color-ghost)",
      }}
    >
      <span
        className="text-[10.5px] font-semibold"
        style={{
          color: "#075985",
          fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
        }}
      >
        {cell.turno_code || "S.COMP"}
      </span>
      {hm && (
        <span
          className="text-[10px]"
          style={{
            color: "#0369A1",
            fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
          }}
        >
          {hm}
        </span>
      )}
    </div>
  )
}

function CellUncov({ cell }: { cell: AgentGridCell }) {
  const span = cell.span || 1
  return (
    <div
      className="bg-uncov-hatch flex flex-col justify-center items-start gap-0.5 px-1.5 py-1 cursor-pointer"
      style={{
        gridColumn: span > 1 ? `span ${span}` : undefined,
        minHeight: 52,
        boxShadow:
          "inset 1px 0 0 var(--color-ghost), inset 0 1px 0 var(--color-ghost)",
      }}
    >
      <span
        className="text-[10.5px] font-bold"
        style={{
          color: "var(--color-danger, #C33A3A)",
          fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
        }}
      >
        {cell.turno_code || "—"}
      </span>
      {cell.prestazione_min ? null : (
        span > 1 && (
          <span
            className="text-[10px]"
            style={{
              color: "var(--color-danger, #C33A3A)",
              opacity: 0.8,
              fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
            }}
          >
            {span} gg
          </span>
        )
      )}
    </div>
  )
}

function CellLeave({ cell }: { cell: AgentGridCell }) {
  const span = cell.span || 1
  return (
    <div
      className="bg-leave-hatch flex flex-col justify-center items-start gap-0.5 px-1.5 py-1"
      style={{
        gridColumn: span > 1 ? `span ${span}` : undefined,
        minHeight: 52,
        boxShadow:
          "inset 1px 0 0 var(--color-ghost), inset 0 1px 0 var(--color-ghost)",
      }}
    >
      <span
        className="text-[10.5px] font-bold"
        style={{
          color: "var(--color-on-surface-muted)",
          fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
        }}
      >
        {cell.turno_code || "FERIE"}
      </span>
    </div>
  )
}

function Cell({
  cell, selected, onClick,
}: {
  cell: AgentGridCell
  selected?: boolean
  onClick?: () => void
}) {
  const baseProps = { onClick }
  switch (cell.state) {
    case "work":
      return <div {...baseProps}><CellWork cell={cell} selected={selected} /></div>
    case "rest":
      return <div {...baseProps}><CellRest /></div>
    case "fr":
      return <div {...baseProps}><CellFr cell={cell} /></div>
    case "scomp":
      return <div {...baseProps}><CellScomp cell={cell} /></div>
    case "uncov":
      return <div {...baseProps}><CellUncov cell={cell} /></div>
    case "leave":
      return <div {...baseProps}><CellLeave cell={cell} /></div>
    default:
      return <div {...baseProps}><CellRest /></div>
  }
}


// ─────────────────────────────────────────────────────────────
// Page component
// ─────────────────────────────────────────────────────────────

// Calcola il lunedi' della settimana della data data (locale-safe).
function startOfWeekMonday(d: Date): Date {
  const x = new Date(d)
  const day = x.getDay()          // 0=Dom .. 6=Sab
  const diff = (day + 6) % 7      // giorni da lunedi'
  x.setDate(x.getDate() - diff)
  x.setHours(0, 0, 0, 0)
  return x
}

function isoDate(d: Date): string {
  return (
    d.getFullYear() +
    "-" +
    String(d.getMonth() + 1).padStart(2, "0") +
    "-" +
    String(d.getDate()).padStart(2, "0")
  )
}

const MONTH_NAMES_IT = [
  "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
  "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
]
const DOW_LETTERS: ("L" | "M" | "X" | "G" | "V" | "S" | "D")[] =
  ["L", "M", "X", "G", "V", "S", "D"]

interface DayMeta {
  dow: string
  dnum: number
  wknd?: boolean
  today?: boolean
  m?: boolean          // primo del mese
  iso: string          // "YYYY-MM-DD"
  week: number         // ISO week number (semplificato)
}

/** Genera i 28 giorni + le settimane-banner a partire dalla data di inizio. */
function buildDayRow(start: Date, days: number): DayMeta[] {
  const out: DayMeta[] = []
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  for (let i = 0; i < days; i++) {
    const d = new Date(start)
    d.setDate(start.getDate() + i)
    const idx = (d.getDay() + 6) % 7       // 0=L..6=D
    const isToday = d.getTime() === today.getTime()
    out.push({
      dow: DOW_LETTERS[idx],
      dnum: d.getDate(),
      wknd: idx >= 5,
      today: isToday,
      m: d.getDate() === 1,
      iso: isoDate(d),
      week: Math.floor(i / 7),
    })
  }
  return out
}

function buildWeekBands(days: DayMeta[]): string[] {
  const bands: string[] = []
  for (let w = 0; w < Math.ceil(days.length / 7); w++) {
    const slice = days.slice(w * 7, w * 7 + 7)
    if (slice.length === 0) break
    const a = slice[0], b = slice[slice.length - 1]
    const aName = MONTH_NAMES_IT[Number(a.iso.slice(5, 7)) - 1]
      .slice(0, 3).toLowerCase()
    const bName = MONTH_NAMES_IT[Number(b.iso.slice(5, 7)) - 1]
      .slice(0, 3).toLowerCase()
    bands.push(
      `Sett. ${w + 1} · ${a.dnum} ${aName} — ${b.dnum} ${bName}`,
    )
  }
  return bands
}


export function CalendarAgentePage() {
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [query, setQuery] = useState("")
  // Future: rendi depositoFilter settabile via dropdown nella topbar
  const [depositoFilter] = useState<string>("")
  const [fetchedRows, setFetchedRows] = useState<AgentGridRow[] | null>(null)
  const [fetching, setFetching] = useState(false)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [usingMock, setUsingMock] = useState(false)

  // Start = lunedi' della settimana 4 settimane fa, cosi' la "oggi" cade
  // circa a meta' del range.
  const [startDate, setStartDate] = useState<Date>(() => {
    const d = new Date()
    d.setDate(d.getDate() - 21)    // 3 settimane indietro
    return startOfWeekMonday(d)
  })

  const DAY_COUNT = 28

  // Recupera dati dal backend. Fallback su MOCK_ROWS se l'endpoint
  // non restituisce righe (es. DB senza turni PdC importati).
  useEffect(() => {
    let cancelled = false
    setFetching(true)
    setFetchError(null)
    getCalendarioAgente({
      start: isoDate(startDate),
      days: DAY_COUNT,
      deposito: depositoFilter || undefined,
    })
      .then((r) => {
        if (cancelled) return
        if (r.rows && r.rows.length > 0) {
          setFetchedRows(r.rows)
          setUsingMock(false)
        } else {
          // DB vuoto — usiamo il mock per tenere il design visibile
          setFetchedRows(null)
          setUsingMock(true)
        }
      })
      .catch((e) => {
        if (cancelled) return
        setFetchError(e instanceof Error ? e.message : String(e))
        setFetchedRows(null)
        setUsingMock(true)
      })
      .finally(() => {
        if (!cancelled) setFetching(false)
      })
    return () => {
      cancelled = true
    }
  }, [startDate, depositoFilter])

  // Giorni e week-bands calcolati dinamicamente dalla startDate
  const dayRow: DayMeta[] = useMemo(
    () => buildDayRow(startDate, DAY_COUNT),
    [startDate],
  )
  const weekBands = useMemo(() => buildWeekBands(dayRow), [dayRow])

  // Base rows: real fetch, oppure mock se vuoto/errore
  const baseRows: AgentGridRow[] = fetchedRows ?? MOCK_ROWS

  const rows = useMemo(() => {
    if (!query.trim()) return baseRows
    const q = query.toLowerCase()
    return baseRows.filter((r) =>
      r.pdc_code.toLowerCase().includes(q) ||
      r.display_name.toLowerCase().includes(q) ||
      r.matricola.includes(q)
    )
  }, [query, baseRows])

  const totalHoursMin = rows.reduce((a, r) => a + r.totals.hours_min, 0)
  const totalUncov = rows.reduce((a, r) => a + r.totals.uncov, 0)
  const totalFr = rows.reduce(
    (a, r) => a + r.cells.filter((c) => c.state === "fr").length,
    0,
  )

  const monthLabel =
    MONTH_NAMES_IT[startDate.getMonth()] + " " + startDate.getFullYear()

  function shiftMonths(delta: number) {
    setStartDate((prev) => {
      const d = new Date(prev)
      d.setDate(d.getDate() + delta * 28)
      return startOfWeekMonday(d)
    })
  }

  return (
    <div
      className="min-h-screen pl-56"
      style={{ backgroundColor: "var(--color-surface)" }}
    >
      {/* Topbar */}
      <div
        className="flex items-center gap-4 px-6 h-11"
        style={{
          backgroundColor: "var(--color-surface-container-lowest)",
          boxShadow: "inset 0 -1px 0 var(--color-ghost)",
        }}
      >
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-wider"
            style={{ color: "var(--color-on-surface-quiet)" }}>
            Turnazione
          </span>
          <span className="text-[12px] font-bold"
            style={{ color: "var(--color-on-surface-strong)",
              fontFamily: "var(--font-mono, monospace)" }}>
            Calendario agente
          </span>
        </div>
        <div className="flex items-center gap-5 ml-4">
          <div className="flex flex-col">
            <span className="text-[9.5px] uppercase tracking-wider font-semibold"
              style={{ color: "var(--color-on-surface-quiet)" }}>
              Periodo
            </span>
            <span className="text-[11.5px]"
              style={{ color: "var(--color-on-surface-strong)",
                fontFamily: "var(--font-mono, monospace)" }}>
              {monthLabel.toLowerCase().slice(0, 3)} {startDate.getFullYear()} · {DAY_COUNT}gg
            </span>
          </div>
          <div className="flex flex-col">
            <span className="text-[9.5px] uppercase tracking-wider font-semibold"
              style={{ color: "var(--color-on-surface-quiet)" }}>
              Deposito
            </span>
            <span className="text-[11.5px] font-semibold"
              style={{ color: "var(--color-on-surface-strong)" }}>
              Milano C.le
            </span>
          </div>
          <div className="flex flex-col">
            <span className="text-[9.5px] uppercase tracking-wider font-semibold"
              style={{ color: "var(--color-on-surface-quiet)" }}>
              PdC visualizzati
            </span>
            <span className="text-[11.5px]"
              style={{ color: "var(--color-on-surface-strong)",
                fontFamily: "var(--font-mono, monospace)" }}>
              {rows.length} / {baseRows.length}
            </span>
          </div>
        </div>
        <div className="flex-1" />
        <button
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11.5px] font-semibold"
          style={{
            backgroundColor: "var(--color-surface-container)",
            color: "var(--color-on-surface)",
          }}
        >
          <Download size={12} strokeWidth={1.8} />
          Esporta
        </button>
        <button className="p-1.5 rounded-md opacity-70 hover:opacity-100">
          <Bell size={15} strokeWidth={1.8} />
        </button>
      </div>

      {/* Content */}
      <div className="px-6 py-5">
        <div className="flex items-end gap-4">
          <div className="flex-1">
            <h1
              className="text-[22px] font-bold leading-tight"
              style={{
                color: "var(--color-on-surface-strong)",
                fontFamily: "var(--font-display, 'Exo 2', Inter)",
              }}
            >
              Calendario agente
            </h1>
            <p
              className="text-[12px] mt-0.5"
              style={{ color: "var(--color-on-surface-muted)" }}
            >
              Chi lavora quando · 28 giorni · una riga per PdC
            </p>

            {/* Filters */}
            <div className="flex items-center gap-2 mt-3 flex-wrap">
              <div
                className="inline-flex items-center gap-1 rounded-md overflow-hidden"
                style={{ backgroundColor: "var(--color-surface-container)" }}
              >
                <button
                  onClick={() => shiftMonths(-1)}
                  className="px-1.5 py-1 opacity-70 hover:opacity-100"
                >
                  <ChevronLeft size={14} strokeWidth={2} />
                </button>
                <span
                  className="px-2 text-[11.5px] font-semibold"
                  style={{
                    color: "var(--color-on-surface-strong)",
                    fontFamily: "var(--font-mono, monospace)",
                  }}
                >
                  {monthLabel}
                </span>
                <button
                  onClick={() => shiftMonths(1)}
                  className="px-1.5 py-1 opacity-70 hover:opacity-100"
                >
                  <ChevronRight size={14} strokeWidth={2} />
                </button>
              </div>

              <FilterPill
                icon={MapPin}
                label="Deposito"
                value={depositoFilter || "tutti"}
              />
              <FilterPill icon={Users} label="Matricole" value="tutte" />
              <FilterPill icon={Filter} label="Stato" value="tutti" />

              <div className="flex-1" />

              <div
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md"
                style={{
                  backgroundColor: "var(--color-surface-container-lowest)",
                  boxShadow: "inset 0 0 0 2px rgba(0,98,204,0.20)",
                }}
              >
                <Search size={12} strokeWidth={1.8}
                  style={{ color: "var(--color-on-surface-muted)" }} />
                <input
                  placeholder="Cerca PdC o matricola"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="border-0 bg-transparent outline-none text-[11.5px] w-[170px] font-medium"
                  style={{ color: "var(--color-on-surface-strong)" }}
                />
                {query && (
                  <button onClick={() => setQuery("")}
                    className="opacity-60 hover:opacity-100">
                    <X size={11} />
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* KPIs */}
          <div className="flex gap-2">
            <MiniKpi label="Coperture" value="87" unit="%" />
            <MiniKpi label="Scoperti" value={totalUncov}
              color="var(--color-danger, #C33A3A)" />
            <MiniKpi label="FR candidate" value={totalFr} color="#6D28D9" />
          </div>
        </div>

        {/* Data source banner (fetch status) */}
        {(fetching || fetchError || usingMock) && (
          <div
            className="mt-3 flex items-center gap-2 px-3 py-2 rounded-md text-[11.5px]"
            style={{
              backgroundColor: fetchError
                ? "var(--color-destructive-container, rgba(220,38,38,0.08))"
                : usingMock
                ? "var(--color-warning-container, rgba(234,88,12,0.08))"
                : "var(--color-surface-container-low)",
              color: fetchError
                ? "var(--color-destructive, #C33A3A)"
                : usingMock
                ? "var(--color-warning, #C76A12)"
                : "var(--color-on-surface-muted)",
            }}
          >
            {fetching ? (
              <>
                <Loader2 size={13} className="animate-spin" />
                Caricamento calendario…
              </>
            ) : fetchError ? (
              <>
                <AlertTriangle size={13} />
                Errore: {fetchError}. Mostro dati demo.
              </>
            ) : (
              <>
                <Info size={13} />
                Nessun turno PdC attivo nel DB per {depositoFilter || "il range"}: mostro dati demo. Importa un PDF turno PdC per popolare.
              </>
            )}
          </div>
        )}

        {/* Legend */}
        <div className="flex items-center gap-4 mt-4 flex-wrap">
          <LegendItem label="Lavorativo"
            styleOverride={{ backgroundColor: "var(--color-surface-container-lowest)",
              boxShadow: "inset 0 0 0 1px var(--color-ghost)" }} />
          <LegendItem label="Riposo"
            styleOverride={{ backgroundColor: "var(--color-surface-container-low)" }} />
          <LegendItem swatchClass="bg-fr-gradient" label="FR · notturno" />
          <LegendItem label="S.COMP"
            styleOverride={{ backgroundColor: "rgba(2,132,199,0.10)" }} />
          <LegendItem swatchClass="bg-uncov-hatch" label="Scoperto" />
          <LegendItem swatchClass="bg-leave-hatch" label="Ferie / Perm." />
          <div className="flex-1" />
          <div
            className="inline-flex items-center gap-1 text-[11px]"
            style={{ color: "var(--color-on-surface-muted)" }}
          >
            <Info size={12} strokeWidth={1.8} />
            Click cella per dettaglio · doppio click per modificare
          </div>
        </div>

        {/* Calendar card */}
        <div
          className="mt-4 rounded-lg overflow-hidden"
          style={{
            backgroundColor: "var(--color-surface-container-lowest)",
            boxShadow: "var(--shadow-md, 0 4px 12px rgba(11,28,48,0.06))",
          }}
        >
          <div className="overflow-x-auto">
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "180px repeat(28, 72px)",
                minWidth: 180 + 72 * 28,
              }}
            >
              {/* Corner cell */}
              <div
                className="sticky left-0 flex flex-col justify-end px-3 py-2 z-10"
                style={{
                  gridColumn: "1 / 2",
                  gridRow: "1 / 3",
                  backgroundColor: "var(--color-surface-container-lowest)",
                  boxShadow: "inset -1px 0 0 var(--color-ghost), inset 0 -1px 0 var(--color-ghost)",
                }}
              >
                <span className="text-[10px] font-bold uppercase tracking-wider"
                  style={{ color: "var(--color-on-surface-muted)" }}>
                  PdC
                </span>
                <span className="text-[11px] font-medium"
                  style={{
                    color: "var(--color-on-surface-quiet)",
                    fontFamily: "var(--font-mono, monospace)",
                  }}>
                  {rows.length} righe
                </span>
              </div>

              {/* Week bands */}
              <div
                style={{
                  gridColumn: "2 / span 28",
                  gridRow: "1 / 2",
                  display: "grid",
                  gridTemplateColumns: "repeat(4, 1fr)",
                }}
              >
                {weekBands.map((label, i) => (
                  <div
                    key={i}
                    className="px-2 py-1 text-[10px] font-semibold"
                    style={{
                      color: "var(--color-on-surface-muted)",
                      backgroundColor: "var(--color-surface-container-low)",
                      boxShadow:
                        i < 3
                          ? "inset -1px 0 0 var(--color-ghost), inset 0 -1px 0 var(--color-ghost)"
                          : "inset 0 -1px 0 var(--color-ghost)",
                    }}
                  >
                    {label}
                  </div>
                ))}
              </div>

              {/* Day cells header */}
              {dayRow.map((d, i) => (
                <div
                  key={i}
                  className="flex flex-col items-center justify-center py-1"
                  style={{
                    gridRow: "2 / 3",
                    gridColumn: `${i + 2} / ${i + 3}`,
                    backgroundColor: d.wknd
                      ? "var(--color-surface-container-low)"
                      : "var(--color-surface-container-lowest)",
                    boxShadow:
                      "inset 1px 0 0 var(--color-ghost), inset 0 -1px 0 var(--color-ghost)",
                  }}
                >
                  <div
                    className="text-[9px] font-bold uppercase tracking-wider"
                    style={{
                      color: d.wknd || d.today
                        ? "var(--color-brand)"
                        : "var(--color-on-surface-quiet)",
                    }}
                  >
                    {d.dow}
                  </div>
                  <div
                    className={
                      "text-[12px] font-bold mt-0.5 " +
                      (d.today
                        ? "w-6 h-6 rounded-full flex items-center justify-center text-white"
                        : "")
                    }
                    style={{
                      fontFamily: "var(--font-mono, monospace)",
                      color: d.today
                        ? "#fff"
                        : d.m
                        ? "var(--color-brand)"
                        : "var(--color-on-surface-strong)",
                      backgroundColor: d.today
                        ? "var(--color-brand)"
                        : "transparent",
                    }}
                  >
                    {d.dnum}
                  </div>
                </div>
              ))}

              {/* Rows */}
              {rows.map((row, ri) => {
                // Per ogni riga: PdC-cell + N gcells (con eventuali span).
                // Il gridRow = ri + 3 (1 week bands, 2 day header)
                const gridRow = ri + 3
                const cellsJsx: React.ReactNode[] = []
                let col = 2
                row.cells.forEach((cell, ci) => {
                  const span = cell.span || 1
                  const key = `${row.pdc_code}-${ci}`
                  const selected = selectedKey === key
                  cellsJsx.push(
                    <div
                      key={key}
                      onClick={() => setSelectedKey(selected ? null : key)}
                      style={{
                        gridRow: `${gridRow} / ${gridRow + 1}`,
                        gridColumn: `${col} / ${col + span}`,
                      }}
                    >
                      <Cell cell={cell} selected={selected} />
                    </div>,
                  )
                  col += span
                })
                return [
                  // Sticky left PdC cell
                  <div
                    key={`pdc-${row.pdc_code}`}
                    className="sticky left-0 px-3 py-2 z-[1]"
                    style={{
                      gridRow: `${gridRow} / ${gridRow + 1}`,
                      gridColumn: "1 / 2",
                      backgroundColor: "var(--color-surface-container-lowest)",
                      boxShadow:
                        "inset -1px 0 0 var(--color-ghost), inset 0 -1px 0 var(--color-ghost)",
                    }}
                  >
                    <div
                      className="text-[12px] font-bold leading-tight"
                      style={{
                        color: ri === 0 ? "var(--color-brand)"
                          : "var(--color-on-surface-strong)",
                        fontFamily: "var(--font-mono, monospace)",
                      }}
                    >
                      {row.pdc_code}
                    </div>
                    <div
                      className="text-[10px] mt-0.5"
                      style={{ color: "var(--color-on-surface-muted)" }}
                    >
                      {row.display_name} · <span style={{ fontFamily: "var(--font-mono, monospace)" }}>{row.matricola}</span>
                    </div>
                  </div>,
                  ...cellsJsx,
                ]
              })}
            </div>
          </div>

          {/* Footer */}
          <div
            className="flex items-center gap-5 px-4 py-3"
            style={{
              boxShadow: "inset 0 1px 0 var(--color-ghost)",
              backgroundColor: "var(--color-surface-container-low)",
            }}
          >
            <div className="flex items-center gap-5 text-[11.5px]"
              style={{ color: "var(--color-on-surface-muted)" }}>
              <div>
                <strong style={{
                  color: "var(--color-on-surface-strong)",
                  fontFamily: "var(--font-mono, monospace)",
                }}>
                  {rows.length} PdC
                </strong>{" "}
                di {baseRows.length} visualizzati
              </div>
              <div>
                Ore totali settimana ·{" "}
                <strong style={{
                  color: "var(--color-on-surface-strong)",
                  fontFamily: "var(--font-mono, monospace)",
                }}>
                  {Math.floor(totalHoursMin / 60)}h {totalHoursMin % 60}m
                </strong>
              </div>
              <div>
                Scoperti ·{" "}
                <strong style={{
                  color: "var(--color-danger, #C33A3A)",
                  fontFamily: "var(--font-mono, monospace)",
                }}>
                  {totalUncov}
                </strong>
              </div>
              <div>
                FR candidate ·{" "}
                <strong style={{ color: "#6D28D9", fontFamily: "var(--font-mono, monospace)" }}>
                  {totalFr}
                </strong>
              </div>
            </div>
            <div className="flex-1" />
            <button
              className="inline-flex items-center gap-1 px-2 py-1 text-[11.5px] font-semibold rounded-md"
              style={{
                color: "var(--color-on-surface-muted)",
                backgroundColor: "transparent",
              }}
            >
              <Info size={12} strokeWidth={1.8} />
              Mostra solo scoperti
            </button>
            <button
              className="inline-flex items-center gap-1 px-2.5 py-1 text-[11.5px] font-semibold rounded-md text-white"
              style={{ backgroundColor: "var(--color-brand)" }}
            >
              <Plus size={12} strokeWidth={2} />
              Assegna giornata
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
