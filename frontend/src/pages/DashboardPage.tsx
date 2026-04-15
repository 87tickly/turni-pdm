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
  Train,
} from "lucide-react"
import { cn } from "@/lib/utils"

function QuickAction({
  icon: Icon,
  label,
  description,
  to,
  gradient,
}: {
  icon: typeof PlusCircle
  label: string
  description: string
  to: string
  gradient: string
}) {
  const navigate = useNavigate()
  return (
    <button
      onClick={() => navigate(to)}
      className="group flex flex-col items-start p-5 bg-card rounded-xl border border-border hover:border-brand/25 hover:shadow-md transition-all duration-200 text-left"
    >
      <div
        className={cn(
          "w-10 h-10 rounded-lg flex items-center justify-center mb-3",
          gradient
        )}
      >
        <Icon size={20} className="text-white" />
      </div>
      <h3 className="text-[14px] font-semibold mb-1 group-hover:text-brand transition-colors">
        {label}
      </h3>
      <p className="text-[12px] text-muted-foreground leading-relaxed">
        {description}
      </p>
    </button>
  )
}

export function DashboardPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [health, setHealth] = useState<string>("...")
  const [recentShifts, setRecentShifts] = useState<SavedShift[]>([])

  useEffect(() => {
    getHealth()
      .then((h) => setHealth(h.status))
      .catch(() => setHealth("errore"))

    getSavedShifts()
      .then((data) => setRecentShifts(data.shifts.slice(0, 5)))
      .catch(() => {})
  }, [])

  const hour = new Date().getHours()
  const greeting =
    hour < 12 ? "Buongiorno" : hour < 18 ? "Buon pomeriggio" : "Buonasera"

  return (
    <div>
      {/* Hero */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <h2 className="text-xl font-bold tracking-tight">
            {greeting}, {user?.username}
          </h2>
          <p className="text-[13px] text-muted-foreground mt-1">
            Gestionale turni personale di macchina
          </p>
        </div>
        <div
          className={cn(
            "flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium",
            health === "ok"
              ? "bg-success-muted text-success"
              : "bg-destructive/10 text-destructive"
          )}
        >
          {health === "ok" ? (
            <CircleCheck size={12} />
          ) : (
            <CircleX size={12} />
          )}
          {health === "ok" ? "Operativo" : health}
        </div>
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <QuickAction
          icon={PlusCircle}
          label="Nuovo turno"
          description="Costruisci un turno da zero con validazione in tempo reale"
          to="/builder"
          gradient="bg-gradient-to-br from-blue-500 to-blue-600"
        />
        <QuickAction
          icon={Search}
          label="Cerca treni"
          description="Cerca per numero treno o per stazione"
          to="/treni"
          gradient="bg-gradient-to-br from-emerald-500 to-emerald-600"
        />
        <QuickAction
          icon={ClipboardList}
          label="Turni salvati"
          description="Visualizza e gestisci i turni creati"
          to="/turni"
          gradient="bg-gradient-to-br from-amber-500 to-amber-600"
        />
        <QuickAction
          icon={Upload}
          label="Importa dati"
          description="Carica PDF turni materiale"
          to="/import"
          gradient="bg-gradient-to-br from-violet-500 to-violet-600"
        />
      </div>

      {/* Recent shifts */}
      {recentShifts.length > 0 && (
        <div className="bg-card rounded-xl border border-border p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-[14px] font-semibold">Turni recenti</h3>
            <button
              onClick={() => navigate("/turni")}
              className="text-[12px] text-brand hover:text-primary-hover font-medium flex items-center gap-1 transition-colors"
            >
              Vedi tutti <ArrowRight size={12} />
            </button>
          </div>
          <div className="space-y-1">
            {recentShifts.map((shift) => (
              <div
                key={shift.id}
                className="flex items-center gap-3 p-3 rounded-lg hover:bg-muted/60 transition-colors"
              >
                <div className="w-8 h-8 rounded-lg bg-brand/8 flex items-center justify-center">
                  <Train size={14} className="text-brand" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[13px] font-medium truncate">
                    {shift.name}
                  </p>
                  <p className="text-[11px] text-muted-foreground">
                    {shift.deposito} · {shift.day_type}
                  </p>
                </div>
                <span className="text-[11px] text-muted-foreground font-mono">
                  {typeof shift.train_ids === "string"
                    ? shift.train_ids.split(",").length
                    : shift.train_ids.length}{" "}
                  treni
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty state */}
      {recentShifts.length === 0 && health === "ok" && (
        <div className="bg-card rounded-xl border border-border p-8 text-center">
          <div className="w-12 h-12 rounded-xl bg-brand/8 flex items-center justify-center mx-auto mb-3">
            <Train size={22} className="text-brand" />
          </div>
          <h3 className="text-[14px] font-semibold mb-1">
            Nessun turno salvato
          </h3>
          <p className="text-[12px] text-muted-foreground mb-4">
            Inizia creando il tuo primo turno
          </p>
          <button
            onClick={() => navigate("/builder")}
            className="px-4 py-2 bg-brand text-white rounded-lg text-[13px] font-medium hover:bg-primary-hover transition-colors"
          >
            Crea turno
          </button>
        </div>
      )}
    </div>
  )
}
