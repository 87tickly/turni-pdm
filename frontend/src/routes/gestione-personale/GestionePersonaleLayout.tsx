import { Outlet } from "react-router-dom";

import { CommandPalette } from "@/routes/gestione-personale/_shared/CommandPalette";
import { CoverageTweaksPanel } from "@/routes/gestione-personale/_shared/CoverageTweaksPanel";
import { DepositoDrilldownOverlay } from "@/routes/gestione-personale/_shared/DepositoDrilldownOverlay";
import { GestionePersonaleProvider } from "@/routes/gestione-personale/_shared/GestionePersonaleContext";
import { TurnoDrilldownOverlay } from "@/routes/gestione-personale/_shared/TurnoDrilldownOverlay";

/**
 * Sprint 7.10 MR β.1 — Layout shell del 4° ruolo Gestione Personale
 * (editorial redesign).
 *
 * Wrappa l'`<Outlet />` di react-router con:
 * - `GestionePersonaleProvider` per stato cross-route (tweak copertura,
 *   drilldown deposito + turno, command palette)
 * - mount globale di `<CommandPalette />` (apertura via ⌘K / Ctrl+K)
 * - mount globale di `<DepositoDrilldownOverlay />` + `<TurnoDrilldownOverlay />`
 *   (apertura cascading da Dashboard / Lista Depositi)
 * - mount globale di `<CoverageTweaksPanel />` (simulatore design+demo
 *   verde/giallo/rosso per vedere reazioni stripe/callout/coverage band)
 *
 * Le route GP figlie restano focalizzate sui contenuti; tutto lo "shell"
 * cross-route vive qui per evitare duplicazione di stato per route.
 */
export function GestionePersonaleLayout() {
  return (
    <GestionePersonaleProvider>
      <Outlet />
      <CommandPalette />
      <DepositoDrilldownOverlay />
      <TurnoDrilldownOverlay />
      <CoverageTweaksPanel />
    </GestionePersonaleProvider>
  );
}
