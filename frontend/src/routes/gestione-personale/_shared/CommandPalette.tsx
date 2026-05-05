import { useEffect, useMemo, useRef, useState } from "react";
import type { ComponentType, SVGProps } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  Building2,
  CalendarRange,
  CheckCircle2,
  Filter,
  LayoutDashboard,
  PlaneTakeoff,
  Plus,
  Route as RouteIcon,
  Upload,
  UsersRound,
} from "lucide-react";

import { useGestionePersonale } from "./GestionePersonaleContext";

/**
 * Sprint 7.10 MR β.1 — Command palette ⌘K (Linear/Stripe-style).
 *
 * Navigazione veloce + azioni cross-modulo. Apertura via ⌘K/Ctrl+K
 * (gestita dal context), chiusura via Esc, click fuori, o Invio su un
 * comando. Filtraggio testuale fuzzy semplice (substring case-insensitive).
 */

type LucideIcon = ComponentType<SVGProps<SVGSVGElement>>;

interface CmdItem {
  id: string;
  label: string;
  icon: LucideIcon;
  kbd?: string;
  /** Esecuzione del comando (navigazione o azione applicativa). */
  run: () => void;
  /** Sezione visibile in palette: "Vai a", "Azioni", "Filtri rapidi". */
  section: string;
}

export function CommandPalette() {
  const { paletteOpen, closePalette } = useGestionePersonale();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Reset query + autofocus all'apertura.
  useEffect(() => {
    if (paletteOpen) {
      setQuery("");
      setActiveIndex(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [paletteOpen]);

  const items: CmdItem[] = useMemo(() => {
    const navAndClose = (path: string) => () => {
      navigate(path);
      closePalette();
    };
    return [
      // Vai a
      {
        id: "go-home",
        section: "Vai a",
        label: "Home Gestione Personale",
        icon: LayoutDashboard,
        kbd: "G H",
        run: navAndClose("/gestione-personale/dashboard"),
      },
      {
        id: "go-anagrafica",
        section: "Vai a",
        label: "Anagrafica PdC",
        icon: UsersRound,
        kbd: "G A",
        run: navAndClose("/gestione-personale/persone"),
      },
      {
        id: "go-depositi",
        section: "Vai a",
        label: "Depositi PdC",
        icon: Building2,
        kbd: "G D",
        run: navAndClose("/gestione-personale/depositi"),
      },
      {
        id: "go-calendario",
        section: "Vai a",
        label: "Calendario assegnazioni",
        icon: CalendarRange,
        kbd: "G C",
        run: navAndClose("/gestione-personale/calendario"),
      },
      {
        id: "go-ferie",
        section: "Vai a",
        label: "Ferie & assenze",
        icon: PlaneTakeoff,
        kbd: "G F",
        run: navAndClose("/gestione-personale/indisponibilita"),
      },
      // Azioni
      {
        id: "act-nuova-indisp",
        section: "Azioni",
        label: "Apri nuova indisponibilità",
        icon: Plus,
        kbd: "N I",
        run: navAndClose("/gestione-personale/indisponibilita"),
      },
      {
        id: "act-export",
        section: "Azioni",
        label: "Esporta stato copertura",
        icon: Upload,
        kbd: "⌘ E",
        run: closePalette,
      },
      {
        id: "act-pdc",
        section: "Azioni",
        label: "Apri Pianificatore PdC",
        icon: RouteIcon,
        kbd: "⌘ ⇧ P",
        run: navAndClose("/pianificatore-pdc/dashboard"),
      },
      // Filtri rapidi
      {
        id: "filter-critici",
        section: "Filtri rapidi",
        label: "Mostra solo depositi critici",
        icon: AlertTriangle,
        kbd: "F C",
        run: navAndClose("/gestione-personale/depositi"),
      },
      {
        id: "filter-in-servizio",
        section: "Filtri rapidi",
        label: "Mostra solo PdC in servizio",
        icon: CheckCircle2,
        kbd: "F S",
        run: navAndClose("/gestione-personale/persone"),
      },
      {
        id: "filter-attive-oggi",
        section: "Filtri rapidi",
        label: "Indisponibilità attive oggi",
        icon: Filter,
        kbd: "F O",
        run: navAndClose("/gestione-personale/indisponibilita"),
      },
    ];
  }, [navigate, closePalette]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q.length === 0) return items;
    return items.filter((i) => i.label.toLowerCase().includes(q));
  }, [items, query]);

  // Group by section preservando l'ordine di apparizione.
  const groups = useMemo(() => {
    const acc: Array<{ section: string; items: CmdItem[] }> = [];
    for (const it of filtered) {
      const last = acc[acc.length - 1];
      if (last !== undefined && last.section === it.section) last.items.push(it);
      else acc.push({ section: it.section, items: [it] });
    }
    return acc;
  }, [filtered]);

  // Keep activeIndex within bounds when filtered list shrinks.
  useEffect(() => {
    if (activeIndex >= filtered.length) setActiveIndex(0);
  }, [activeIndex, filtered.length]);

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const target = filtered[activeIndex];
      if (target !== undefined) target.run();
    }
  }

  if (!paletteOpen) return null;

  let runningIdx = 0;
  return (
    <div className="gp-cmd-overlay" onClick={closePalette}>
      <div
        className="gp-cmd-panel"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          ref={inputRef}
          type="text"
          className="gp-cmd-input"
          placeholder="Cerca o esegui un'azione…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
          autoComplete="off"
          spellCheck={false}
        />
        <div className="gp-cmd-list">
          {groups.length === 0 ? (
            <div className="gp-cmd-section-h" style={{ paddingBottom: 12, color: "var(--gp-ink-3)" }}>
              Nessun risultato per "{query}"
            </div>
          ) : (
            groups.map((g) => (
              <div key={g.section}>
                <div className="gp-cmd-section-h">{g.section}</div>
                {g.items.map((it) => {
                  const Icon = it.icon;
                  const isActive = runningIdx === activeIndex;
                  const myIdx = runningIdx;
                  runningIdx += 1;
                  return (
                    <button
                      key={it.id}
                      type="button"
                      className={`gp-cmd-row ${isActive ? "gp-is-active" : ""}`}
                      onMouseEnter={() => setActiveIndex(myIdx)}
                      onClick={it.run}
                    >
                      <Icon className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden />
                      <span className="flex-1">{it.label}</span>
                      {it.kbd !== undefined && <span className="gp-kbd">{it.kbd}</span>}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
