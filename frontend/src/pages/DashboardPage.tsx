import { useState, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { getHealth, getSavedShifts, type SavedShift } from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import {
  PlusCircle,
  Search,
  Upload,
  ClipboardList,
  ArrowRight,
  CircleCheck,
  CircleX,
  LayoutGrid,
  Calendar,
  Clock,
  Pencil,
  CheckCircle2,
  AlertTriangle,
  FileText,
  Train,
} from "lucide-react"
import { cn } from "@/lib/utils"

// ─────────────────────────────────────────────────────────────────
// MOCK DATA — placeholder finche` non esistono i 3 endpoint backend
// (/dashboard/kpi, /activity/recent, /linea/attiva). Da rimuovere
// quando saranno implementati gli endpoint (vedi HANDOFF §04).
// ─────────────────────────────────────────────────────────────────
const MOCK_KPI = {
  turni_attivi: 42,
  giorni_lavorati: 5,
  giorni_max: 7,
  ore_settimana_h: 38,
  ore_settimana_m: 45,
  ore_max: 42,
  delta_30gg: "+12%",
}

const MOCK_LINEA: Array<{
  treno: string
  tratta: string
  stato: "ok" | "ritardo" | "soppresso"
  ritardo: string
}> = [
  { treno: "RV 2831", tratta: "Milano C.le → Bergamo", stato: "ok", ritardo: "—" },
  { treno: "R 10581", tratta: "Lecco → Milano P.G.", stato: "ritardo", ritardo: "+8′" },
  { treno: "RE 2615", tratta: "Brescia → Verona PN", stato: "ok", ritardo: "—" },
]

// ─────────────────────────────────────────────────────────────────

function KpiCard({
  label,
  value,
  unit,
  sublabel,
  delta,
  live,
  icon: Icon,
}: {
  label: string
  value: string | number
  unit?: string
  sublabel?: string
  delta?: string
  live?: boolean
  icon?: typeof LayoutGrid
}) {
  return (
    <div
      className="relative rounded-xl px-5 py-4 shadow-sm overflow-hidden"
      style={{ backgroundColor: "var(--color-surface-container-lowest)" }}
    >
      <div
        className="flex items-center justify-between text-[10px] font-bold uppercase"
        style={{
          color: "var(--color-on-surface-muted)",
          letterSpacing: "0.1em",
        }}
      >
        <span>{label}</span>
        {Icon && (
          <Icon size={14} style={{ color: "var(--color-on-surface-quiet)" }} />
        )}
      </div>
      {live && (
        <span
          className="absolute top-3 right-3 inline-flex items-center gap-1.5 text-[9.5px] font-bold uppercase"
          style={{ color: "var(--color-success)", letterSpacing: "0.1em" }}
        >
          <span
            className="w-1.5 h-1.5 rounded-full animate-pulse-dot"
            style={{ backgroundColor: "var(--color-success)" }}
          />
          LIVE
        </span>
      )}
      <div
        className="mt-1.5 leading-none"
        style={{
          fontFamily: "var(--font-display)",
          fontWeight: 700,
          fontSize: "32px",
          color: "var(--color-on-surface-strong)",
          letterSpacing: "-0.025em",
        }}
      >
        {value}
        {unit && (
          <span
            className="ml-0.5 font-semibold"
            style={{ fontSize: "16px", color: "var(--color-on-surface-muted)" }}
          >
            {unit}
          </span>
        )}
      </div>
      <div
        className="mt-1 text-[11px] flex items-center gap-1.5"
        style={{ color: "var(--color-on-surface-muted)" }}
      >
        {delta && (
          <span style={{ color: "var(--color-success)", fontWeight: 600 }}>
            {delta}
          </span>
        )}
        {sublabel}
      </div>
    </div>
  )
}

function ActivityRow({
  icon: Icon,
  tone,
  title,
  subtitle,
  time,
  onClick,
}: {
  icon: typeof Pencil
  tone: "blue" | "green" | "amber" | "slate"
  title: string
  subtitle: string
  time: string
  onClick?: () => void
}) {
  const toneStyle = {
    blue: { bg: "rgba(0, 98, 204, 0.10)", fg: "var(--color-brand)" },
    green: { bg: "rgba(34, 197, 94, 0.14)", fg: "var(--color-success)" },
    amber: { bg: "rgba(234, 88, 12, 0.12)", fg: "var(--color-warning)" },
    slate: {
      bg: "var(--color-surface-container)",
      fg: "var(--color-on-surface-muted)",
    },
  }[tone]
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full grid grid-cols-[32px_1fr_auto] gap-3 items-center px-2.5 py-2 rounded-md text-left transition-colors hover:bg-[var(--color-surface-container-low)]"
    >
      <div
        className="w-8 h-8 rounded-md grid place-items-center"
        style={{ backgroundColor: toneStyle.bg, color: toneStyle.fg }}
      >
        <Icon size={14} />
      </div>
      <div className="min-w-0">
        <div
          className="text-[13px] font-semibold truncate"
          style={{ color: "var(--color-on-surface-strong)" }}
        >
          {title}
        </div>
        <div
          className="text-[11px] truncate"
          style={{ color: "var(--color-on-surface-muted)" }}
        >
          {subtitle}
        </div>
      </div>
      <span
        className="text-[10.5px]"
        style={{
          fontFamily: "var(--font-mono)",
          color: "var(--color-on-surface-quiet)",
          letterSpacing: "0.03em",
        }}
      >
        {time}
      </span>
    </button>
  )
}

function StatoChip({ stato }: { stato: "ok" | "ritardo" | "soppresso" }) {
  const map = {
    ok: {
      bg: "var(--color-success-container)",
      fg: "var(--color-success)",
      label: "In orario",
    },
    ritardo: {
      bg: "var(--color-warning-container)",
      fg: "var(--color-warning)",
      label: "Ritardato",
    },
    soppresso: {
      bg: "var(--color-surface-container)",
      fg: "var(--color-on-surface-muted)",
      label: "Soppresso",
    },
  }[stato]
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10.5px] font-semibold"
      style={{ backgroundColor: map.bg, color: map.fg }}
    >
      <span
        className="w-1.5 h-1.5 rounded-full"
        style={{ backgroundColor: map.fg }}
      />
      {map.label}
    </span>
  )
}

export function DashboardPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [health, setHealth] = useState<string>("...")
  const [recentShifts, setRecentShifts] = useState<SavedShift[]>([])
  const [totalShifts, setTotalShifts] = useState<number>(0)

  useEffect(() => {
    getHealth()
      .then((h) => setHealth(h.status))
      .catch(() => setHealth("errore"))

    getSavedShifts()
      .then((data) => {
        setTotalShifts(data.count ?? data.shifts.length)
        setRecentShifts(data.shifts.slice(0, 4))
      })
      .catch(() => {})
  }, [])

  const hour = new Date().getHours()
  const greeting =
    hour < 12 ? "Buongiorno" : hour < 18 ? "Buon pomeriggio" : "Buonasera"

  const today = new Date()
  const todayLabel = today.toLocaleDateString("it-IT", {
    day: "numeric",
    month: "short",
  })
  const dayCodes = ["D", "L", "M", "X", "G", "V", "S"]
  const todayDow = today.getDay()

  return (
    <div>
      {/* Hero */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <div
            className="text-[10px] font-bold uppercase mb-1"
            style={{
              color: "var(--color-on-surface-quiet)",
              letterSpacing: "0.12em",
            }}
          >
            Pannello di controllo
          </div>
          <h2
            className="font-bold tracking-tight"
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "26px",
              letterSpacing: "-0.02em",
              color: "var(--color-on-surface-strong)",
            }}
          >
            {greeting}, {user?.username}
          </h2>
          <p
            className="text-[13px] mt-1"
            style={{ color: "var(--color-on-surface-muted)" }}
          >
            Gestionale turni personale di macchina
          </p>
        </div>
        <div
          className={cn(
            "flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium"
          )}
          style={
            health === "ok"
              ? {
                  backgroundColor: "var(--color-success-container)",
                  color: "var(--color-success)",
                }
              : {
                  backgroundColor: "var(--color-destructive-container)",
                  color: "var(--color-destructive)",
                }
          }
        >
          {health === "ok" ? <CircleCheck size={12} /> : <CircleX size={12} />}
          {health === "ok" ? "Operativo" : health}
        </div>
      </div>

      {/* KPI grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <KpiCard
          label="Totale turni"
          value={totalShifts}
          delta={MOCK_KPI.delta_30gg}
          sublabel="vs 30gg"
          icon={LayoutGrid}
        />
        <KpiCard
          label="Turni attivi"
          value={MOCK_KPI.turni_attivi}
          sublabel="In corso ora"
          live
        />
        <KpiCard
          label="Lavorati settimana"
          value={MOCK_KPI.giorni_lavorati}
          unit={`/${MOCK_KPI.giorni_max} gg`}
          sublabel="2 riposi programmati"
          icon={Calendar}
        />
        <KpiCard
          label="Ore settimana"
          value={MOCK_KPI.ore_settimana_h}
          unit={`h ${MOCK_KPI.ore_settimana_m}m`}
          sublabel={`Max ${MOCK_KPI.ore_max}h`}
          icon={Clock}
        />
      </div>

      {/* Two-column main */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-4">
        {/* Left col: Activity + Linea attiva */}
        <div className="flex flex-col gap-4">
          {/* Activity feed */}
          <div
            className="rounded-xl shadow-sm overflow-hidden"
            style={{ backgroundColor: "var(--color-surface-container-lowest)" }}
          >
            <div className="px-5 py-4 flex items-center">
              <span
                className="font-semibold"
                style={{
                  fontFamily: "var(--font-display)",
                  fontSize: "15px",
                  color: "var(--color-on-surface-strong)",
                }}
              >
                Attività recente
              </span>
              <button
                onClick={() => navigate("/turni")}
                className="ml-auto text-[11.5px] font-semibold flex items-center gap-1"
                style={{ color: "var(--color-brand)" }}
              >
                Vedi tutto <ArrowRight size={12} />
              </button>
            </div>
            <div className="px-2.5 pb-2.5 space-y-0.5">
              {recentShifts.length === 0 ? (
                <ActivityRow
                  icon={FileText}
                  tone="slate"
                  title="Nessuna attività registrata"
                  subtitle="Inizia creando un turno o importa un PDF"
                  time="—"
                />
              ) : (
                recentShifts.map((s, i) => (
                  <ActivityRow
                    key={s.id}
                    icon={i === 0 ? Pencil : i === 1 ? CheckCircle2 : i === 2 ? FileText : AlertTriangle}
                    tone={i === 0 ? "blue" : i === 1 ? "green" : i === 2 ? "slate" : "amber"}
                    title={s.name}
                    subtitle={`${s.deposito} · ${s.day_type} · ${
                      typeof s.train_ids === "string"
                        ? s.train_ids.split(",").length
                        : s.train_ids.length
                    } treni`}
                    time={new Date(s.created_at).toLocaleDateString("it-IT", {
                      day: "numeric",
                      month: "short",
                    })}
                    onClick={() => navigate("/turni")}
                  />
                ))
              )}
            </div>
          </div>

          {/* Linea attiva (mock) */}
          <div
            className="rounded-xl shadow-sm overflow-hidden"
            style={{ backgroundColor: "var(--color-surface-container-lowest)" }}
          >
            <div className="px-5 py-3.5 flex items-center">
              <span
                className="font-semibold"
                style={{
                  fontFamily: "var(--font-display)",
                  fontSize: "14px",
                  color: "var(--color-on-surface-strong)",
                }}
              >
                Monitoraggio linea attiva
              </span>
              <span
                className="ml-2 text-[9.5px] uppercase font-bold px-1.5 py-0.5 rounded"
                style={{
                  color: "var(--color-on-surface-quiet)",
                  backgroundColor: "var(--color-surface-container)",
                  letterSpacing: "0.1em",
                }}
              >
                Mock
              </span>
              <div className="ml-auto flex gap-2">
                <StatoChip stato="ok" />
                <StatoChip stato="ritardo" />
              </div>
            </div>
            <table className="w-full text-[12px] border-collapse">
              <thead>
                <tr
                  style={{
                    backgroundColor: "var(--color-surface-container-low)",
                  }}
                >
                  {["Treno", "Tratta", "Stato", "Ritardo"].map((h) => (
                    <th
                      key={h}
                      className="text-[9.5px] font-bold uppercase text-left px-5 py-2"
                      style={{
                        color: "var(--color-on-surface-quiet)",
                        letterSpacing: "0.1em",
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {MOCK_LINEA.map((r) => (
                  <tr
                    key={r.treno}
                    className="transition-colors hover:bg-[var(--color-surface-container-low)]"
                  >
                    <td className="px-5 py-2.5">
                      <span
                        className="font-bold"
                        style={{
                          fontFamily: "var(--font-mono)",
                          color: "var(--color-brand)",
                          fontSize: "12.5px",
                        }}
                      >
                        {r.treno}
                      </span>
                    </td>
                    <td
                      className="px-5 py-2.5"
                      style={{
                        fontFamily: "var(--font-mono)",
                        color: "var(--color-on-surface-muted)",
                        fontSize: "11.5px",
                      }}
                    >
                      {r.tratta}
                    </td>
                    <td className="px-5 py-2.5">
                      <StatoChip stato={r.stato} />
                    </td>
                    <td
                      className="px-5 py-2.5"
                      style={{
                        fontFamily: "var(--font-mono)",
                        color:
                          r.stato === "ritardo"
                            ? "var(--color-warning)"
                            : "var(--color-on-surface-muted)",
                        fontWeight: r.stato === "ritardo" ? 700 : 400,
                      }}
                    >
                      {r.ritardo}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right col: Today card (gradient) + Quick actions */}
        <div className="flex flex-col gap-4">
          <div
            className="rounded-xl px-5 py-4 shadow-md text-white"
            style={{ background: "var(--gradient-primary)" }}
          >
            <div
              className="flex items-center justify-between text-[10px] font-bold uppercase opacity-85"
              style={{ letterSpacing: "0.12em" }}
            >
              <span>Oggi in servizio</span>
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  letterSpacing: "0.04em",
                }}
              >
                {todayLabel}
              </span>
            </div>
            <div className="mt-3.5 flex flex-col gap-2.5">
              <div className="grid grid-cols-[auto_1fr_auto] items-center gap-2.5 text-[13px]">
                <span
                  className="w-2 h-2 rounded-full"
                  style={{
                    backgroundColor: "var(--color-dot)",
                    boxShadow: "0 0 0 3px rgba(34, 197, 94, 0.20)",
                  }}
                />
                <div className="font-semibold">
                  {recentShifts[0]?.name ?? "Nessun turno attivo"}
                </div>
                <div
                  className="inline-flex gap-0.5"
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "9.5px",
                    fontWeight: 700,
                  }}
                >
                  {dayCodes.map((d, i) => (
                    <span
                      key={i}
                      className="w-3.5 h-3.5 grid place-items-center rounded-[2px]"
                      style={{
                        backgroundColor:
                          i === todayDow
                            ? "#fff"
                            : "rgba(255,255,255,0.18)",
                        color:
                          i === todayDow
                            ? "var(--color-brand)"
                            : "rgba(255,255,255,0.55)",
                      }}
                    >
                      {d}
                    </span>
                  ))}
                </div>
              </div>
            </div>
            <div
              className="mt-3.5 p-3 rounded-md text-[11px]"
              style={{ backgroundColor: "rgba(255,255,255,0.12)" }}
            >
              <div
                className="font-bold uppercase opacity-80"
                style={{ fontSize: "9.5px", letterSpacing: "0.1em" }}
              >
                Stato sistema
              </div>
              <div
                className="mt-1"
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "12.5px",
                }}
              >
                {totalShifts} turni archiviati
              </div>
              <div
                className="mt-0.5 opacity-80"
                style={{ fontFamily: "var(--font-mono)", fontSize: "11px" }}
              >
                {health === "ok" ? "Backend operativo" : health}
              </div>
            </div>
          </div>

          {/* Azioni rapide compatte (preserva funzionalita esistente) */}
          <div
            className="rounded-xl shadow-sm p-3"
            style={{ backgroundColor: "var(--color-surface-container-lowest)" }}
          >
            <div
              className="px-2 pb-2 text-[10px] font-bold uppercase"
              style={{
                color: "var(--color-on-surface-muted)",
                letterSpacing: "0.1em",
              }}
            >
              Azioni rapide
            </div>
            {[
              { icon: PlusCircle, label: "Nuovo turno", to: "/builder" },
              { icon: Search, label: "Cerca treni", to: "/treni" },
              { icon: ClipboardList, label: "Turni salvati", to: "/turni" },
              { icon: Train, label: "Turni PdC", to: "/pdc" },
              { icon: Upload, label: "Importa PDF", to: "/import" },
            ].map(({ icon: Icon, label, to }) => (
              <button
                key={to}
                onClick={() => navigate(to)}
                className="w-full flex items-center gap-2.5 px-2 py-1.5 rounded-md text-[12.5px] font-medium text-left transition-colors hover:bg-[var(--color-surface-container-low)]"
                style={{ color: "var(--color-on-surface)" }}
              >
                <Icon
                  size={14}
                  strokeWidth={1.8}
                  style={{ color: "var(--color-brand)" }}
                />
                {label}
                <ArrowRight
                  size={12}
                  className="ml-auto"
                  style={{ color: "var(--color-on-surface-quiet)" }}
                />
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
