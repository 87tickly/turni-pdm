import { useState, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import {
  getHealth,
  getDashboardKpi,
  getActivityRecent,
  getLineaAttiva,
  type DashboardKpi,
  type ActivityItem,
  type LineaAttivaRow,
} from "@/lib/api"
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
  const [kpi, setKpi] = useState<DashboardKpi | null>(null)
  const [activity, setActivity] = useState<ActivityItem[]>([])
  const [linea, setLinea] = useState<LineaAttivaRow[]>([])
  const [lineaNote, setLineaNote] = useState<string | null>(null)

  useEffect(() => {
    getHealth()
      .then((h) => setHealth(h.status))
      .catch(() => setHealth("errore"))

    getDashboardKpi()
      .then(setKpi)
      .catch(() => setKpi(null))

    getActivityRecent(4)
      .then((r) => setActivity(r.items))
      .catch(() => setActivity([]))

    getLineaAttiva()
      .then((r) => {
        setLinea(r.items)
        setLineaNote(r.note)
      })
      .catch((e) => setLineaNote(`Errore caricamento: ${e.message ?? e}`))
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
          value={kpi?.totale_turni ?? "—"}
          delta={
            kpi?.delta_30gg_pct != null
              ? `${kpi.delta_30gg_pct > 0 ? "+" : ""}${kpi.delta_30gg_pct}%`
              : undefined
          }
          sublabel={kpi?.delta_30gg_pct != null ? "vs 30gg" : "—"}
          icon={LayoutGrid}
        />
        <KpiCard
          label="Turni settimana"
          value={kpi?.turni_settimana ?? "—"}
          sublabel="In questa settimana"
          live={kpi != null && kpi.turni_settimana > 0}
        />
        <KpiCard
          label="Lavorati settimana"
          value={kpi?.giorni_lavorati ?? "—"}
          unit={kpi ? `/${kpi.giorni_max} gg` : undefined}
          sublabel={
            kpi
              ? `${Math.max(0, kpi.giorni_max - kpi.giorni_lavorati)} rimasti`
              : "—"
          }
          icon={Calendar}
        />
        <KpiCard
          label="Ore settimana"
          value={kpi ? Math.floor(kpi.ore_settimana_min / 60) : "—"}
          unit={kpi ? `h ${kpi.ore_settimana_min % 60}m` : undefined}
          sublabel={kpi ? `Max ${Math.floor(kpi.ore_max_min / 60)}h` : "—"}
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
              {activity.length === 0 ? (
                <ActivityRow
                  icon={FileText}
                  tone="slate"
                  title="Nessuna attività registrata"
                  subtitle="Inizia creando un turno o importa un PDF"
                  time="—"
                />
              ) : (
                activity.map((ev) => {
                  const toneByType: Record<
                    ActivityItem["type"],
                    "blue" | "green" | "amber" | "slate"
                  > = {
                    edit: "blue",
                    validate: "green",
                    conflict: "amber",
                    import: "slate",
                  }
                  const iconByType: Record<
                    ActivityItem["type"],
                    typeof Pencil
                  > = {
                    edit: Pencil,
                    validate: CheckCircle2,
                    conflict: AlertTriangle,
                    import: FileText,
                  }
                  return (
                    <ActivityRow
                      key={ev.id ?? `${ev.type}-${ev.title}`}
                      icon={iconByType[ev.type]}
                      tone={toneByType[ev.type]}
                      title={ev.title}
                      subtitle={ev.subtitle}
                      time={
                        ev.created_at
                          ? new Date(ev.created_at).toLocaleDateString(
                              "it-IT",
                              { day: "numeric", month: "short" },
                            )
                          : "—"
                      }
                      onClick={() => navigate("/turni")}
                    />
                  )
                })
              )}
            </div>
          </div>

          {/* Linea attiva — dati reali da ARTURO Live (cache 60s) */}
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
              <div className="ml-auto flex items-center gap-2">
                {linea.length > 0 && (
                  <>
                    <StatoChip stato="ok" />
                    {linea.some((r) => r.stato === "ritardo") && (
                      <StatoChip stato="ritardo" />
                    )}
                  </>
                )}
              </div>
            </div>
            {linea.length === 0 ? (
              <div
                className="px-5 py-6 text-[12px]"
                style={{ color: "var(--color-on-surface-muted)" }}
              >
                {lineaNote ?? "Nessun treno monitorato al momento. Crea un turno per popolare la lista."}
              </div>
            ) : (
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
                  {linea.map((r) => (
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
                        {r.ritardo_label}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
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
                  {activity[0]?.title ?? "Nessun turno attivo"}
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
                {kpi?.totale_turni ?? "—"} turni archiviati
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
