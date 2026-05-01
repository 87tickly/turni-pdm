import { NavLink } from "react-router-dom";
import { LayoutDashboard, ListOrdered, Workflow, AlertTriangle } from "lucide-react";

import { ArturoLogo } from "@/components/brand/ArturoLogo";
import { useAuth } from "@/lib/auth/AuthContext";
import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
}

interface NavGroup {
  /** Etichetta header del gruppo, visibile in maiuscolo nella sidebar. */
  label: string;
  /** Ruolo richiesto per mostrare il gruppo (admin lo vede sempre). */
  requiredRole: string;
  items: NavItem[];
}

const NAV_PIANIFICATORE_GIRO: NavGroup = {
  label: "Pianificatore Giro",
  requiredRole: "PIANIFICATORE_GIRO",
  items: [
    { to: "/pianificatore-giro/dashboard", label: "Home", icon: LayoutDashboard },
    { to: "/pianificatore-giro/programmi", label: "Programmi", icon: ListOrdered },
  ],
};

const NAV_PIANIFICATORE_PDC: NavGroup = {
  label: "Pianificatore PdC",
  requiredRole: "PIANIFICATORE_PDC",
  items: [
    { to: "/pianificatore-pdc/dashboard", label: "Home", icon: LayoutDashboard },
    { to: "/pianificatore-pdc/giri", label: "Vista giri", icon: Workflow },
    { to: "/pianificatore-pdc/turni", label: "Turni PdC", icon: ListOrdered },
    { to: "/pianificatore-pdc/revisioni-cascading", label: "Rev. cascading", icon: AlertTriangle },
  ],
};

const NAV_GROUPS: NavGroup[] = [NAV_PIANIFICATORE_GIRO, NAV_PIANIFICATORE_PDC];

export function Sidebar() {
  const { hasRole } = useAuth();
  const visibleGroups = NAV_GROUPS.filter((group) => hasRole(group.requiredRole));

  return (
    <aside className="flex w-60 flex-col border-r border-border bg-white/70 backdrop-blur">
      <div className="flex h-14 items-center border-b border-border px-4">
        <ArturoLogo size="sm" />
      </div>
      <div className="flex flex-col gap-3 p-3">
        {visibleGroups.map((group) => (
          <SidebarGroup key={group.label} group={group} />
        ))}
      </div>
    </aside>
  );
}

function SidebarGroup({ group }: { group: NavGroup }) {
  return (
    <div className="flex flex-col gap-1">
      <p className="px-2 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {group.label}
      </p>
      {group.items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
              isActive
                ? "bg-primary text-primary-foreground"
                : "text-foreground hover:bg-accent hover:text-accent-foreground",
            )
          }
        >
          <item.icon className="h-4 w-4" aria-hidden />
          <span>{item.label}</span>
        </NavLink>
      ))}
    </div>
  );
}
