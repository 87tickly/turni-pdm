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
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Logo } from "./Logo"

interface SidebarProps {
  username: string
  isAdmin: boolean
  onLogout: () => void
}

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/treni", icon: Search, label: "Cerca treni" },
  { to: "/turni", icon: ClipboardList, label: "Turni" },
  { to: "/builder", icon: PlusCircle, label: "Nuovo turno" },
  { to: "/calendario", icon: Calendar, label: "Calendario" },
  { to: "/import", icon: Upload, label: "Import" },
]

export function Sidebar({ username, isAdmin, onLogout }: SidebarProps) {
  return (
    <aside className="flex flex-col w-56 bg-sidebar h-screen fixed left-0 top-0 border-r border-sidebar-border">
      {/* Brand */}
      <div className="px-4 py-4">
        <Logo size="sm" />
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 space-y-0.5">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2.5 px-2.5 py-1.5 rounded-md text-[13px] font-medium transition-all duration-150",
                isActive
                  ? "bg-brand/8 text-brand"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
              )
            }
          >
            <Icon size={15} strokeWidth={1.8} />
            {label}
          </NavLink>
        ))}

        <div className="pt-4">
          <NavLink
            to="/impostazioni"
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2.5 px-2.5 py-1.5 rounded-md text-[13px] font-medium transition-all duration-150",
                isActive
                  ? "bg-brand/8 text-brand"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
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
