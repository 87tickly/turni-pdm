import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

/**
 * Sprint 7.10 MR β.1 — Editorial redesign Gestione Personale.
 *
 * Stato cross-route per il ruolo Gestione Personale:
 *
 * - **Coverage tweak**: simulatore stato copertura (current/green/yellow/red).
 *   I componenti che usano il colore di copertura (stripe KPI, callout,
 *   coverage band) leggono `--gp-cov`/`--gp-cov-bg`/`--gp-cov-pct` da
 *   CSS variables, qui aggiornati. Il valore `current` lascia leggere il
 *   dato reale dai KPI (no override).
 * - **Drilldown deposito**: aperto da click su una riga deposito; mostra
 *   Gantt 7gg dei PdC del deposito.
 * - **Drilldown turno**: aperto da click su una pillola turno dentro il
 *   drilldown deposito; mostra Gantt orario "treno-style" del turno.
 * - **Command palette ⌘K**: navigazione veloce + azioni cross-modulo.
 *
 * Esposto via `useGestionePersonale()` ai figli di `GestionePersonaleLayout`.
 */

export type CoverageTweak = "current" | "green" | "yellow" | "red";

export interface DepositoDrilldownPayload {
  codice: string;
  display_name: string;
  copertura_pct: number;
  persone_attive: number;
}

export interface TurnoDrilldownPayload {
  codice: string;          // es. "T1"
  pdc_label: string;       // es. "ALFIERI Vittorio"
  matricola: string;       // es. "100102"
  deposito: string;        // es. "Alessandria"
  durata_label: string;    // es. "8h 00m"
}

interface GestionePersonaleContextValue {
  // Coverage tweak
  coverageTweak: CoverageTweak;
  setCoverageTweak: (v: CoverageTweak) => void;
  /** Override del % copertura coerente con `coverageTweak`, o null per usare il dato reale. */
  coverageOverridePct: number | null;
  /** Override colore copertura (CSS variable string), o null. */
  coverageOverrideTone: "ok" | "warn" | "bad" | null;

  // Drilldown deposito
  drilldownDeposito: DepositoDrilldownPayload | null;
  openDepositoDrilldown: (p: DepositoDrilldownPayload) => void;
  closeDepositoDrilldown: () => void;

  // Drilldown turno
  drilldownTurno: TurnoDrilldownPayload | null;
  openTurnoDrilldown: (p: TurnoDrilldownPayload) => void;
  closeTurnoDrilldown: () => void;

  // Command palette
  paletteOpen: boolean;
  openPalette: () => void;
  closePalette: () => void;
  togglePalette: () => void;
}

const Ctx = createContext<GestionePersonaleContextValue | null>(null);

interface ProviderProps {
  children: ReactNode;
}

export function GestionePersonaleProvider({ children }: ProviderProps) {
  const [coverageTweak, setCoverageTweak] = useState<CoverageTweak>("current");
  const [drilldownDeposito, setDrilldownDeposito] = useState<DepositoDrilldownPayload | null>(null);
  const [drilldownTurno, setDrilldownTurno] = useState<TurnoDrilldownPayload | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);

  const { coverageOverridePct, coverageOverrideTone } = useMemo(() => {
    if (coverageTweak === "green") return { coverageOverridePct: 96.5, coverageOverrideTone: "ok" as const };
    if (coverageTweak === "yellow") return { coverageOverridePct: 88.4, coverageOverrideTone: "warn" as const };
    if (coverageTweak === "red") return { coverageOverridePct: 62.1, coverageOverrideTone: "bad" as const };
    return { coverageOverridePct: null, coverageOverrideTone: null };
  }, [coverageTweak]);

  const openDepositoDrilldown = useCallback((p: DepositoDrilldownPayload) => {
    setDrilldownDeposito(p);
  }, []);
  const closeDepositoDrilldown = useCallback(() => {
    setDrilldownDeposito(null);
    setDrilldownTurno(null); // chiude anche il livello 2 a cascata
  }, []);
  const openTurnoDrilldown = useCallback((p: TurnoDrilldownPayload) => {
    setDrilldownTurno(p);
  }, []);
  const closeTurnoDrilldown = useCallback(() => setDrilldownTurno(null), []);

  const openPalette = useCallback(() => setPaletteOpen(true), []);
  const closePalette = useCallback(() => setPaletteOpen(false), []);
  const togglePalette = useCallback(() => setPaletteOpen((v) => !v), []);

  // Esc chiude in cascata: prima il turno, poi il deposito, poi la palette.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        if (drilldownTurno !== null) {
          setDrilldownTurno(null);
          return;
        }
        if (drilldownDeposito !== null) {
          setDrilldownDeposito(null);
          return;
        }
        if (paletteOpen) {
          setPaletteOpen(false);
          return;
        }
      }
      // ⌘K / Ctrl+K → toggle palette
      const isMod = e.metaKey || e.ctrlKey;
      if (isMod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [drilldownTurno, drilldownDeposito, paletteOpen]);

  const value = useMemo<GestionePersonaleContextValue>(
    () => ({
      coverageTweak,
      setCoverageTweak,
      coverageOverridePct,
      coverageOverrideTone,
      drilldownDeposito,
      openDepositoDrilldown,
      closeDepositoDrilldown,
      drilldownTurno,
      openTurnoDrilldown,
      closeTurnoDrilldown,
      paletteOpen,
      openPalette,
      closePalette,
      togglePalette,
    }),
    [
      coverageTweak,
      coverageOverridePct,
      coverageOverrideTone,
      drilldownDeposito,
      openDepositoDrilldown,
      closeDepositoDrilldown,
      drilldownTurno,
      openTurnoDrilldown,
      closeTurnoDrilldown,
      paletteOpen,
      openPalette,
      closePalette,
      togglePalette,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useGestionePersonale(): GestionePersonaleContextValue {
  const ctx = useContext(Ctx);
  if (ctx === null) {
    throw new Error("useGestionePersonale richiede <GestionePersonaleProvider>");
  }
  return ctx;
}
