import { useMemo, useState } from "react";
import type { ComponentType, SVGProps } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  AlertTriangle,
  Building2,
  ChevronLeft,
  ChevronRight,
  IdCard,
  LayoutDashboard,
  ListOrdered,
  Users,
  Workflow,
  Wrench,
} from "lucide-react";

import { ArturoLogo } from "@/components/brand/ArturoLogo";
import { useSidebar } from "@/components/layout/SidebarContext";
import { useAuth } from "@/lib/auth/AuthContext";
import { cn } from "@/lib/utils";

type LucideIcon = ComponentType<SVGProps<SVGSVGElement>>;

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Badge counter inline opzionale (right side). */
  counter?: number | string;
  /** Chip statico inline opzionale (es. "wip"). */
  chip?: string;
}

interface NavGroup {
  /** Identificatore stabile, usato per active state e expanded toggle. */
  id: string;
  /** Etichetta header del gruppo, visibile in maiuscolo nella sidebar. */
  label: string;
  /** Ruolo richiesto per mostrare il gruppo (admin lo vede sempre). */
  requiredRole: string;
  /** Prefisso path che identifica "siamo dentro questo gruppo". */
  pathPrefix: string;
  items: NavItem[];
  /** Icona del gruppo (visibile in modalità collapsed o per i gruppi preview). */
  icon?: LucideIcon;
  /**
   * Gruppo "preview" (ruolo non ancora implementato): mostra label opacizzata
   * + chip "presto", senza items espansi né interazione di routing.
   * Vedi brief §4.5: prevedi visivamente lo spazio per i 5 gruppi.
   */
  preview?: boolean;
}

const NAV_PIANIFICATORE_GIRO: NavGroup = {
  id: "giro",
  label: "Pianificatore Giro",
  requiredRole: "PIANIFICATORE_GIRO",
  pathPrefix: "/pianificatore-giro",
  icon: Workflow,
  items: [
    { to: "/pianificatore-giro/dashboard", label: "Home", icon: LayoutDashboard },
    { to: "/pianificatore-giro/programmi", label: "Programmi", icon: ListOrdered },
  ],
};

const NAV_PIANIFICATORE_PDC: NavGroup = {
  id: "pdc",
  label: "Pianificatore PdC",
  requiredRole: "PIANIFICATORE_PDC",
  pathPrefix: "/pianificatore-pdc",
  icon: ListOrdered,
  items: [
    { to: "/pianificatore-pdc/dashboard", label: "Home", icon: LayoutDashboard },
    { to: "/pianificatore-pdc/giri", label: "Vista giri", icon: Workflow },
    { to: "/pianificatore-pdc/turni", label: "Turni PdC", icon: ListOrdered },
    // Sprint 7.11: anteprima depositi PdC, sotto path PdC fino a quando
    // il ruolo Gestione Personale non sarà implementato.
    { to: "/pianificatore-pdc/depositi", label: "Depositi PdC", icon: Building2 },
    {
      to: "/pianificatore-pdc/revisioni-cascading",
      label: "Rev. cascading",
      icon: AlertTriangle,
      chip: "wip",
    },
  ],
};

/**
 * Gruppi futuri (non ancora implementati). Il brief §4.5 chiede di
 * "prevedere visivamente lo spazio per tutti e 5" per evitare ridisegni
 * quando i ruoli arriveranno. Ognuno ha `preview: true`: mostrato come
 * label opacizzata + chip "presto", non interattivo.
 *
 * Apparizione: dipende da `hasRole` (admin li vede sempre). Quando un
 * ruolo passerà a implementato, basta togliere `preview` e popolare
 * `items` con le voci reali.
 */
const NAV_MANUTENZIONE: NavGroup = {
  id: "manutenzione",
  label: "Manutenzione",
  requiredRole: "MANUTENZIONE",
  pathPrefix: "/manutenzione",
  preview: true,
  icon: Wrench,
  items: [],
};

const NAV_GESTIONE_PERSONALE: NavGroup = {
  id: "gestione-personale",
  label: "Gestione Personale",
  requiredRole: "GESTIONE_PERSONALE",
  pathPrefix: "/gestione-personale",
  preview: true,
  icon: Users,
  items: [],
};

const NAV_PERSONALE: NavGroup = {
  id: "personale",
  label: "Personale",
  requiredRole: "PERSONALE",
  pathPrefix: "/personale",
  preview: true,
  icon: IdCard,
  items: [],
};

const NAV_GROUPS: NavGroup[] = [
  NAV_PIANIFICATORE_GIRO,
  NAV_PIANIFICATORE_PDC,
  NAV_MANUTENZIONE,
  NAV_GESTIONE_PERSONALE,
  NAV_PERSONALE,
];

const APP_VERSION = "0.1.0";

export function Sidebar() {
  const { hasRole, user } = useAuth();
  const location = useLocation();
  const { collapsed, toggle } = useSidebar();

  const visibleGroups = useMemo(
    () => NAV_GROUPS.filter((group) => hasRole(group.requiredRole)),
    [hasRole],
  );

  // Determina il gruppo attivo dal path corrente (matching pathPrefix).
  const activeGroupId = useMemo(() => {
    const match = visibleGroups.find(
      (group) => !group.preview && location.pathname.startsWith(group.pathPrefix),
    );
    return match?.id ?? null;
  }, [visibleGroups, location.pathname]);

  // Stato espansione per gruppi non-attivi (collassabili). Default: solo
  // il gruppo del path corrente è espanso, gli altri collassati.
  // I gruppi preview restano sempre collassati a label.
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => {
    const initial = new Set<string>();
    if (activeGroupId !== null) initial.add(activeGroupId);
    return initial;
  });

  function toggleExpanded(id: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  if (collapsed) {
    return (
      <CollapsedSidebar
        visibleGroups={visibleGroups}
        activeGroupId={activeGroupId}
        userAziendaId={user?.azienda_id ?? null}
      />
    );
  }

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-white/70 backdrop-blur">
      <div className="flex h-14 items-center justify-between border-b border-border pl-5 pr-2">
        <ArturoLogo size="sm" />
        <button
          type="button"
          onClick={toggle}
          aria-label="Riduci sidebar"
          title="Riduci sidebar (più spazio per il Gantt)"
          className="grid h-7 w-7 place-items-center rounded text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          <ChevronLeft className="h-4 w-4" aria-hidden />
        </button>
      </div>

      <nav className="flex flex-1 flex-col gap-3 overflow-y-auto p-3 text-sm">
        {visibleGroups.map((group) => {
          const isActive = group.id === activeGroupId;
          const isExpanded = isActive || expandedIds.has(group.id);
          if (group.preview) {
            return <PreviewGroup key={group.id} group={group} />;
          }
          return (
            <SidebarGroup
              key={group.id}
              group={group}
              isActive={isActive}
              isExpanded={isExpanded}
              onToggle={() => toggleExpanded(group.id)}
            />
          );
        })}
      </nav>

      {user !== null && (
        <div className="flex items-center justify-between border-t border-border px-4 py-3 text-[10px] text-muted-foreground">
          <span className="font-mono">v{APP_VERSION}</span>
          <span>azienda #{user.azienda_id}</span>
        </div>
      )}
    </aside>
  );
}

interface CollapsedSidebarProps {
  visibleGroups: NavGroup[];
  activeGroupId: string | null;
  userAziendaId: number | null;
}

function CollapsedSidebar({ visibleGroups, activeGroupId, userAziendaId }: CollapsedSidebarProps) {
  const { toggle } = useSidebar();

  // In modalità collapsed mostriamo le icone delle voci del gruppo attivo
  // (le altre sono nascoste; toggle in alto per espandere e cambiare ruolo).
  const activeGroup = visibleGroups.find((g) => g.id === activeGroupId) ?? null;
  const items = activeGroup?.items ?? [];

  return (
    <aside className="flex w-14 shrink-0 flex-col border-r border-border bg-white/70 backdrop-blur">
      <div className="flex h-14 items-center justify-center border-b border-border">
        <button
          type="button"
          onClick={toggle}
          aria-label="Espandi sidebar"
          title="Espandi sidebar"
          className="grid h-9 w-9 place-items-center rounded-md text-primary hover:bg-primary/[0.08]"
        >
          <ChevronRight className="h-5 w-5" aria-hidden />
        </button>
      </div>

      <nav className="flex flex-1 flex-col gap-1 overflow-y-auto p-2">
        {items.map((item) => (
          <CollapsedNavItem key={item.to} item={item} />
        ))}
      </nav>

      {userAziendaId !== null && (
        <div className="border-t border-border px-2 py-2 text-center text-[9px] text-muted-foreground">
          <div className="font-mono">v{APP_VERSION}</div>
          <div>az #{userAziendaId}</div>
        </div>
      )}
    </aside>
  );
}

function CollapsedNavItem({ item }: { item: NavItem }) {
  return (
    <NavLink
      to={item.to}
      end={item.to.endsWith("/dashboard")}
      title={item.label}
      aria-label={item.label}
      className={({ isActive }) =>
        cn(
          "relative grid h-10 place-items-center rounded-md transition-colors",
          isActive
            ? "bg-primary text-primary-foreground"
            : "text-muted-foreground hover:bg-accent hover:text-foreground",
        )
      }
    >
      <item.icon className="h-5 w-5" aria-hidden />
      {item.chip !== undefined && (
        <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-amber-500" />
      )}
    </NavLink>
  );
}

interface SidebarGroupProps {
  group: NavGroup;
  isActive: boolean;
  isExpanded: boolean;
  onToggle: () => void;
}

function SidebarGroup({ group, isActive, isExpanded, onToggle }: SidebarGroupProps) {
  if (isActive) {
    return (
      <div className="-mx-1 rounded-lg bg-primary/[0.04] p-2 ring-1 ring-primary/10">
        <div className="flex items-center gap-2 px-2 pb-2 pt-1">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-primary" aria-hidden />
          <span className="text-[10px] font-semibold uppercase tracking-wider text-primary">
            Ruolo attivo
          </span>
        </div>
        <div className="px-2 pb-2 text-[11px] font-semibold uppercase tracking-wider text-foreground/80">
          {group.label}
        </div>
        <ul className="flex flex-col gap-0.5">
          {group.items.map((item) => (
            <li key={item.to}>
              <SidebarItem item={item} />
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={isExpanded}
        className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground transition-colors hover:text-foreground"
      >
        <span className="flex items-center gap-1.5">
          <ChevronRight
            className={cn(
              "h-3 w-3 transition-transform",
              isExpanded && "rotate-90",
            )}
            aria-hidden
          />
          {group.label}
        </span>
        <span className="font-mono text-[10px] font-normal normal-case tracking-normal text-muted-foreground/60">
          {group.items.length}
        </span>
      </button>
      {isExpanded && (
        <ul className="flex flex-col gap-0.5">
          {group.items.map((item) => (
            <li key={item.to}>
              <SidebarItem item={item} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function PreviewGroup({ group }: { group: NavGroup }) {
  const Icon = group.icon;
  return (
    <div className="border-t border-border/70 pt-3 first:border-t-0 first:pt-0">
      <button
        type="button"
        disabled
        className="flex w-full cursor-not-allowed items-center justify-between rounded-md px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground opacity-55"
        title={`${group.label} — non ancora disponibile`}
      >
        <span className="flex items-center gap-1.5">
          <ChevronRight className="h-3 w-3" aria-hidden />
          {Icon !== undefined && <Icon className="h-3 w-3" aria-hidden />}
          {group.label}
        </span>
        <span className="rounded bg-muted px-1 py-0.5 text-[8px] font-semibold normal-case tracking-wide text-muted-foreground">
          presto
        </span>
      </button>
    </div>
  );
}

function SidebarItem({ item }: { item: NavItem }) {
  return (
    <NavLink
      to={item.to}
      end={item.to.endsWith("/dashboard")}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors",
          isActive
            ? "bg-primary font-medium text-primary-foreground"
            : "text-foreground/80 hover:bg-accent hover:text-foreground",
        )
      }
    >
      <item.icon className="h-4 w-4 shrink-0" aria-hidden />
      <span className="flex-1">{item.label}</span>
      {item.counter !== undefined && (
        <span className="font-mono text-[10px] text-muted-foreground/80">
          {item.counter}
        </span>
      )}
      {item.chip !== undefined && (
        <span className="inline-flex items-center rounded bg-amber-100 px-1 py-0.5 text-[8px] font-semibold uppercase tracking-wide text-amber-800">
          {item.chip}
        </span>
      )}
    </NavLink>
  );
}
