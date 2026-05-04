import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

/**
 * Context per lo stato "collapsed" della Sidebar (Sprint 7.11 MR 7.11.5).
 *
 * La sidebar può essere ridotta a icon-only (~56px) per liberare spazio
 * orizzontale a chi lavora con il Gantt giro / Gantt PdC. Lo stato è
 * persistito in localStorage chiave `arturo:sidebar:collapsed` così
 * sopravvive ai reload e ai cambi pagina.
 *
 * Il toggle è esposto sia nell'header (più visibile, a sinistra) sia in
 * fondo alla sidebar stessa (utile in modalità collapsed).
 */

const STORAGE_KEY = "arturo:sidebar:collapsed";

interface SidebarContextValue {
  collapsed: boolean;
  toggle: () => void;
  setCollapsed: (v: boolean) => void;
}

const SidebarContext = createContext<SidebarContextValue | null>(null);

function readInitial(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export function SidebarProvider({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsedState] = useState<boolean>(() => readInitial());

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
    } catch {
      /* noop */
    }
  }, [collapsed]);

  const setCollapsed = useCallback((v: boolean) => setCollapsedState(v), []);
  const toggle = useCallback(() => setCollapsedState((v) => !v), []);

  const value = useMemo<SidebarContextValue>(
    () => ({ collapsed, toggle, setCollapsed }),
    [collapsed, toggle, setCollapsed],
  );

  return <SidebarContext.Provider value={value}>{children}</SidebarContext.Provider>;
}

export function useSidebar(): SidebarContextValue {
  const ctx = useContext(SidebarContext);
  if (ctx === null) {
    throw new Error("useSidebar deve essere usato dentro <SidebarProvider>");
  }
  return ctx;
}
