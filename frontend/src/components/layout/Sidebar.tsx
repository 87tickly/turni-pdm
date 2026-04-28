import { NavLink } from "react-router-dom";
import { LayoutDashboard, ListOrdered } from "lucide-react";

import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
}

const NAV_PIANIFICATORE_GIRO: NavItem[] = [
  { to: "/pianificatore-giro/dashboard", label: "Home", icon: LayoutDashboard },
  { to: "/pianificatore-giro/programmi", label: "Programmi", icon: ListOrdered },
];

export function Sidebar() {
  return (
    <aside className="flex w-60 flex-col border-r border-border bg-secondary/40">
      <div className="flex h-14 items-center border-b border-border px-4">
        <span className="text-base font-semibold">Colazione</span>
        <span className="ml-2 rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium uppercase text-primary">
          beta
        </span>
      </div>
      <div className="flex flex-col gap-1 p-3">
        <p className="px-2 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Pianificatore Giro
        </p>
        {NAV_PIANIFICATORE_GIRO.map((item) => (
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
    </aside>
  );
}
