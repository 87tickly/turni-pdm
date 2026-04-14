import { NavLink } from "react-router-dom"
import {
  LayoutDashboard,
  Train,
  Calendar,
  ClipboardList,
  Upload,
  Settings,
  LogOut,
} from "lucide-react"
import { cn } from "@/lib/utils"

interface SidebarProps {
  username: string
  isAdmin: boolean
  onLogout: () => void
}

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/treni", icon: Train, label: "Treni" },
  { to: "/turni", icon: ClipboardList, label: "Turni" },
  { to: "/calendario", icon: Calendar, label: "Calendario" },
  { to: "/import", icon: Upload, label: "Import" },
  { to: "/impostazioni", icon: Settings, label: "Impostazioni" },
]

export function Sidebar({ username, isAdmin, onLogout }: SidebarProps) {
  return (
    <aside className="flex flex-col w-60 bg-sidebar text-sidebar-foreground h-screen fixed left-0 top-0">
      {/* Brand */}
      <div className="px-5 py-6 border-b border-sidebar-accent">
        <h1 className="text-lg font-semibold tracking-tight">COLAZIONE</h1>
        <p className="text-xs text-sidebar-muted mt-0.5">Gestionale Turni PDM</p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors",
                isActive
                  ? "bg-sidebar-accent text-sidebar-foreground font-medium"
                  : "text-sidebar-muted hover:text-sidebar-foreground hover:bg-sidebar-accent/50"
              )
            }
          >
            <Icon size={18} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* User */}
      <div className="px-4 py-4 border-t border-sidebar-accent">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">{username}</p>
            {isAdmin && (
              <span className="text-[10px] uppercase tracking-wider text-sidebar-muted">
                admin
              </span>
            )}
          </div>
          <button
            onClick={onLogout}
            className="p-1.5 rounded hover:bg-sidebar-accent text-sidebar-muted hover:text-sidebar-foreground transition-colors"
            title="Esci"
          >
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </aside>
  )
}
