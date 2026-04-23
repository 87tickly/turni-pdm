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
 * I dati sono mock in questa versione (endpoint /api/calendario-agente
 * non ancora implementato backend-side — residuo tracciato in
 * LIVE-COLAZIONE.md). La struttura dei tipi e delle chiamate e' gia'
 * pronta per il cablaggio.
 */
import { useMemo, useState } from "react"
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
} from "lucide-react"


// ─────────────────────────────────────────────────────────────
// Tipi (da HANDOFF-calendario-agente.md §3)
// ─────────────────────────────────────────────────────────────

type AgentCellState =
  | "work"
  | "rest"
  | "fr"
  | "scomp"
  | "uncov"
  | "leave"
  | "locked"

interface AgentGridCell {
  date: string
  state: AgentCellState
  span?: number
  turno_code?: string
  prestazione_min?: number
  lock_reason?: string
}

interface AgentGridRow {
  pdc_id: number
  pdc_code: string
  display_name: string
  matricola: string
  totals: { work: number; rest: number; uncov: number; hours_min: number }
  cells: AgentGridCell[]
}


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
    turno_code: code,
    prestazione_min: min || undefined,
    span,
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

const WEEK_BANDS = [
  "Sett. 14 · 30 mar — 5 apr",
  "Sett. 15 · 6 — 12 apr",
  "Sett. 16 · 13 — 19 apr",
  "Sett. 17 · 20 — 26 apr",
]

const DAY_ROW: {
  dow: string
  dnum: number
  wknd?: boolean
  today?: boolean
  m?: boolean
}[] = [
  // Week 14
  { dow: "L", dnum: 30 }, { dow: "M", dnum: 31 },
  { dow: "X", dnum: 1, m: true }, { dow: "G", dnum: 2 },
  { dow: "V", dnum: 3 }, { dow: "S", dnum: 4, wknd: true },
  { dow: "D", dnum: 5, wknd: true },
  // Week 15
  { dow: "L", dnum: 6 }, { dow: "M", dnum: 7 }, { dow: "X", dnum: 8 },
  { dow: "G", dnum: 9 }, { dow: "V", dnum: 10 },
  { dow: "S", dnum: 11, wknd: true }, { dow: "D", dnum: 12, wknd: true },
  // Week 16
  { dow: "L", dnum: 13 }, { dow: "M", dnum: 14 }, { dow: "X", dnum: 15 },
  { dow: "G", dnum: 16 }, { dow: "V", dnum: 17 },
  { dow: "S", dnum: 18, wknd: true }, { dow: "D", dnum: 19, wknd: true },
  // Week 17
  { dow: "L", dnum: 20 }, { dow: "M", dnum: 21 }, { dow: "X", dnum: 22 },
  { dow: "G", dnum: 23, today: true }, { dow: "V", dnum: 24 },
  { dow: "S", dnum: 25, wknd: true }, { dow: "D", dnum: 26, wknd: true },
]


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

export function CalendarAgentePage() {
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [query, setQuery] = useState("")

  const rows = useMemo(() => {
    if (!query.trim()) return MOCK_ROWS
    const q = query.toLowerCase()
    return MOCK_ROWS.filter((r) =>
      r.pdc_code.toLowerCase().includes(q) ||
      r.display_name.toLowerCase().includes(q) ||
      r.matricola.includes(q)
    )
  }, [query])

  const totalHoursMin = rows.reduce((a, r) => a + r.totals.hours_min, 0)
  const totalUncov = rows.reduce((a, r) => a + r.totals.uncov, 0)
  const totalFr = rows.reduce(
    (a, r) => a + r.cells.filter((c) => c.state === "fr").length,
    0,
  )

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
              apr 2026 · 28gg
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
              {rows.length} / {MOCK_ROWS.length}
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
                <button className="px-1.5 py-1 opacity-70 hover:opacity-100">
                  <ChevronLeft size={14} strokeWidth={2} />
                </button>
                <span
                  className="px-2 text-[11.5px] font-semibold"
                  style={{
                    color: "var(--color-on-surface-strong)",
                    fontFamily: "var(--font-mono, monospace)",
                  }}
                >
                  Aprile 2026
                </span>
                <button className="px-1.5 py-1 opacity-70 hover:opacity-100">
                  <ChevronRight size={14} strokeWidth={2} />
                </button>
              </div>

              <FilterPill icon={MapPin} label="Deposito" value="Milano C.le" />
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
                {WEEK_BANDS.map((label, i) => (
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
              {DAY_ROW.map((d, i) => (
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
                di {MOCK_ROWS.length} visualizzati
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
