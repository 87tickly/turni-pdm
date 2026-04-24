import { NavLink } from "react-router-dom"
import {
  LayoutDashboard,
  ClipboardList,
  PlusCircle,
  Train,
  Upload,
  Settings,
  LogOut,
  Sparkles,
  Search,
  CalendarRange,
  Bed,
  BarChart3,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Logo } from "./Logo"

interface SidebarProps {
  username: string
  isAdmin: boolean
  onLogout: () => void
  onOpenPalette?: () => void
}

// Dati — lettura dello stato esistente
const dataItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/turni", icon: ClipboardList, label: "Turni Materiale" },
  { to: "/pdc", icon: Train, label: "Turni PdC" },
]

// Operazioni — motore automatico, controllo, interventi manuali
const opsItems = [
  { to: "/auto-genera", icon: Sparkles, label: "Genera da materiale" },
  { to: "/builder-v2", icon: Sparkles, label: "Builder V2 (normativa)" },
  { to: "/calendario-agente", icon: CalendarRange, label: "Calendario agente" },
  { to: "/gantt-preview", icon: BarChart3, label: "Gantt v3 · preview" },
  { to: "/builder", icon: PlusCircle, label: "Nuovo turno" },
  { to: "/fr-approvati", icon: Bed, label: "Dormite FR" },
  { to: "/import", icon: Upload, label: "Import" },
]

function SectionDivider({ label }: { label: string }) {
  return (
    <div
      className="px-3 pt-3 pb-1 text-[9.5px] font-bold uppercase tracking-[0.12em]"
      style={{ color: "var(--color-on-surface-quiet)" }}
    >
      {label}
    </div>
  )
}

function NavItem({
  to,
  icon: Icon,
  label,
}: {
  to: string
  icon: typeof LayoutDashboard
  label: string
}) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) =>
        cn(
          "relative flex items-center gap-2.5 px-2.5 py-1.5 rounded-md text-[13px] font-medium transition-all duration-150",
          isActive
            ? "text-brand"
            : "text-muted-foreground hover:text-foreground"
        )
      }
      style={({ isActive }) =>
        isActive
          ? { backgroundColor: "var(--color-surface-container-high)" }
          : undefined
      }
    >
      {({ isActive }) => (
        <>
          {isActive && (
            <span
              aria-hidden="true"
              className="absolute left-0.5 top-1/2 -translate-y-1/2 h-3.5 w-0.5 rounded-full"
              style={{ backgroundColor: "var(--color-dot)" }}
            />
          )}
          <Icon size={15} strokeWidth={1.8} />
          {label}
        </>
      )}
    </NavLink>
  )
}

export function Sidebar({ username, isAdmin, onLogout, onOpenPalette }: SidebarProps) {
  const isMac = typeof navigator !== "undefined" && /Mac/i.test(navigator.platform)
  return (
    <aside
      className="flex flex-col w-56 h-screen fixed left-0 top-0"
      style={{ backgroundColor: "var(--color-surface-container-low)" }}
    >
      {/* Brand */}
      <div className="px-4 py-4">
        <Logo size="sm" />
      </div>

      {/* Quick search (apre CommandPalette) — rimpiazza Cerca treni */}
      {onOpenPalette && (
        <div className="px-2 mb-2">
          <button
            type="button"
            onClick={onOpenPalette}
            className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[12px] transition-colors"
            style={{
              backgroundColor: "var(--color-surface-container-lowest)",
              color: "var(--color-on-surface-muted)",
              boxShadow: "inset 0 0 0 1px var(--color-ghost)",
            }}
          >
            <Search size={13} strokeWidth={1.8} />
            <span className="flex-1 text-left">Cerca…</span>
            <kbd
              className="text-[9.5px] font-bold px-1 rounded"
              style={{
                fontFamily: "var(--font-mono)",
                color: "var(--color-on-surface-quiet)",
                backgroundColor: "var(--color-surface-container)",
              }}
            >
              {isMac ? "⌘K" : "Ctrl+K"}
            </kbd>
          </button>
        </div>
      )}

      {/* Navigation con divisori tonal (No-Line rule) */}
      <nav className="flex-1 overflow-y-auto">
        <SectionDivider label="Dati" />
        <div className="px-2 space-y-0.5">
          {dataItems.map(({ to, icon, label }) => (
            <NavItem key={to} to={to} icon={icon} label={label} />
          ))}
        </div>

        <SectionDivider label="Operazioni" />
        <div className="px-2 space-y-0.5">
          {opsItems.map(({ to, icon, label }) => (
            <NavItem key={to} to={to} icon={icon} label={label} />
          ))}
        </div>

        <div className="px-2 pt-4">
          <NavItem to="/impostazioni" icon={Settings} label="Impostazioni" />
        </div>
      </nav>

      {/* User — separazione tonal (no border-top) */}
      <div
        className="px-3 py-3"
        style={{ backgroundColor: "var(--color-surface-container)" }}
      >
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-full bg-brand/10 flex items-center justify-center text-[10px] font-bold text-brand uppercase">
            {username[0]}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[12px] font-semibold text-foreground truncate">
              {username}
            </p>
            {isAdmin && (
              <p className="text-[9px] uppercase tracking-wider text-brand font-bold">
                admin
              </p>
            )}
          </div>
          <button
            onClick={onLogout}
            className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            title="Esci"
          >
            <LogOut size={14} strokeWidth={1.8} />
          </button>
        </div>
      </div>
    </aside>
  )
}
