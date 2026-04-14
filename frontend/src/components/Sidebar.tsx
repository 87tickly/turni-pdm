import { NavLink } from "react-router-dom"
import {
  LayoutDashboard,
  Search,
  ClipboardList,
  PlusCircle,
  Calendar,
  Upload,
  Settings,
  LogOut,
  Train,
} from "lucide-react"
import { cn } from "@/lib/utils"

interface SidebarProps {
  username: string
  isAdmin: boolean
  onLogout: () => void
}

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard", shortcut: "D" },
  { to: "/treni", icon: Search, label: "Cerca treni", shortcut: "S" },
  { to: "/turni", icon: ClipboardList, label: "Turni", shortcut: "T" },
  { to: "/builder", icon: PlusCircle, label: "Nuovo turno", shortcut: "N" },
  { to: "/calendario", icon: Calendar, label: "Calendario", shortcut: "C" },
  { to: "/import", icon: Upload, label: "Import", shortcut: "I" },
]

export function Sidebar({ username, isAdmin, onLogout }: SidebarProps) {
  return (
    <aside className="flex flex-col w-56 bg-sidebar h-screen fixed left-0 top-0 border-r border-sidebar-border">
      {/* Brand */}
      <div className="px-4 py-5">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-primary flex items-center justify-center">
            <Train size={14} className="text-primary-foreground" />
          </div>
          <div>
            <h1 className="text-[13px] font-semibold text-sidebar-foreground tracking-tight leading-none">
              COLAZIONE
            </h1>
            <p className="text-[10px] text-sidebar-muted mt-0.5 leading-none">
              Turni PDM
            </p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 space-y-0.5">
        <p className="px-2 pt-2 pb-1.5 text-[10px] font-medium uppercase tracking-widest text-sidebar-muted">
          Menu
        </p>
        {navItems.map(({ to, icon: Icon, label, shortcut }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2.5 px-2 py-1.5 rounded-md text-[13px] transition-all duration-150 group",
                isActive
                  ? "bg-sidebar-accent text-sidebar-foreground"
                  : "text-sidebar-muted hover:text-sidebar-foreground hover:bg-sidebar-accent/60"
              )
            }
          >
            <Icon size={15} strokeWidth={1.8} />
            <span className="flex-1">{label}</span>
            <kbd className="hidden group-hover:inline text-[10px] text-sidebar-muted bg-sidebar-accent/80 px-1 py-0.5 rounded font-mono">
              {shortcut}
            </kbd>
          </NavLink>
        ))}

        <div className="pt-4">
          <p className="px-2 pb-1.5 text-[10px] font-medium uppercase tracking-widest text-sidebar-muted">
            Sistema
          </p>
          <NavLink
            to="/impostazioni"
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2.5 px-2 py-1.5 rounded-md text-[13px] transition-all duration-150",
                isActive
                  ? "bg-sidebar-accent text-sidebar-foreground"
                  : "text-sidebar-muted hover:text-sidebar-foreground hover:bg-sidebar-accent/60"
              )
            }
          >
            <Settings size={15} strokeWidth={1.8} />
            Impostazioni
          </NavLink>
        </div>
      </nav>

      {/* User */}
      <div className="px-3 py-3 border-t border-sidebar-border">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-full bg-sidebar-accent flex items-center justify-center text-[10px] font-medium text-sidebar-foreground uppercase">
            {username[0]}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[12px] font-medium text-sidebar-foreground truncate">
              {username}
            </p>
            {isAdmin && (
              <p className="text-[9px] uppercase tracking-wider text-primary font-medium">
                admin
              </p>
            )}
          </div>
          <button
            onClick={onLogout}
            className="p-1 rounded hover:bg-sidebar-accent text-sidebar-muted hover:text-sidebar-foreground transition-colors"
            title="Esci"
          >
            <LogOut size={14} strokeWidth={1.8} />
          </button>
        </div>
      </div>
    </aside>
  )
}
