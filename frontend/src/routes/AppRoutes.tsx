import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "@/components/layout/AppLayout";
import { ForbiddenRoute } from "@/routes/ForbiddenRoute";
import { LoginRoute } from "@/routes/LoginRoute";
import { NotFoundRoute } from "@/routes/NotFoundRoute";
import { ProtectedRoute } from "@/routes/ProtectedRoute";
import { DashboardRoute } from "@/routes/pianificatore-giro/DashboardRoute";
import { GiroDettaglioRoute } from "@/routes/pianificatore-giro/GiroDettaglioRoute";
import { MaterialeThreadRoute } from "@/routes/pianificatore-giro/MaterialeThreadRoute";
import { ProgrammaDettaglioRoute } from "@/routes/pianificatore-giro/ProgrammaDettaglioRoute";
import { ProgrammaGiriRoute } from "@/routes/pianificatore-giro/ProgrammaGiriRoute";
import { ProgrammiRoute } from "@/routes/pianificatore-giro/ProgrammiRoute";
import { TurniPdcGiroRoute } from "@/routes/pianificatore-giro/TurniPdcGiroRoute";
import { TurnoPdcDettaglioRoute } from "@/routes/pianificatore-giro/TurnoPdcDettaglioRoute";
import { PianificatorePdcDashboardRoute } from "@/routes/pianificatore-pdc/DashboardRoute";
import { PianificatorePdcDepositiRoute } from "@/routes/pianificatore-pdc/DepositiRoute";
import { PianificatorePdcGiriRoute } from "@/routes/pianificatore-pdc/GiriRoute";
import { PianificatorePdcRevisioniCascadingRoute } from "@/routes/pianificatore-pdc/RevisioniCascadingRoute";
import { PianificatorePdcTurniRoute } from "@/routes/pianificatore-pdc/TurniRoute";
import { PianificatorePdcTurnoDettaglioRoute } from "@/routes/pianificatore-pdc/TurnoDettaglioRoute";
// Note: GiriRoute e TurniRoute (Sprint 7.3 MR 2) non sono più placeholder
// ma componenti completi che usano gli endpoint cross-azienda backend.

const ROLE_PIANIFICATORE_GIRO = "PIANIFICATORE_GIRO";
const ROLE_PIANIFICATORE_PDC = "PIANIFICATORE_PDC";

/**
 * Tabella route dichiarativa.
 *
 * Pubblico: /login, /forbidden, fallback 404.
 *
 * Protetto:
 *   /pianificatore-giro/* (5 schermate Sub 6.1-6.5) — ruolo PIANIFICATORE_GIRO
 *   /pianificatore-pdc/*  (5 schermate Sprint 7.3) — ruolo PIANIFICATORE_PDC
 *
 * L'index `/` redirige al ruolo principale dell'utente: PIANIFICATORE_GIRO
 * se presente, altrimenti PIANIFICATORE_PDC. Admin (che bypassa entrambi
 * i check) cade sull'ordinamento default → /pianificatore-giro.
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginRoute />} />
      <Route path="/forbidden" element={<ForbiddenRoute />} />

      {/* Index route: redirige al primo ruolo riconosciuto. */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/pianificatore-giro/dashboard" replace />} />
        </Route>
      </Route>

      {/* Dashboard 1 — Pianificatore Giro Materiale */}
      <Route element={<ProtectedRoute requiredRole={ROLE_PIANIFICATORE_GIRO} />}>
        <Route element={<AppLayout />}>
          <Route path="/pianificatore-giro">
            <Route index element={<Navigate to="/pianificatore-giro/dashboard" replace />} />
            <Route path="dashboard" element={<DashboardRoute />} />
            <Route path="programmi" element={<ProgrammiRoute />} />
            <Route path="programmi/:programmaId" element={<ProgrammaDettaglioRoute />} />
            <Route path="programmi/:programmaId/giri" element={<ProgrammaGiriRoute />} />
            <Route path="giri/:giroId" element={<GiroDettaglioRoute />} />
            <Route path="giri/:giroId/turni-pdc" element={<TurniPdcGiroRoute />} />
            <Route path="thread/:threadId" element={<MaterialeThreadRoute />} />
            <Route path="turni-pdc/:turnoId" element={<TurnoPdcDettaglioRoute />} />
          </Route>
        </Route>
      </Route>

      {/* Dashboard 2 — Pianificatore Turno PdC (Sprint 7.3) */}
      <Route element={<ProtectedRoute requiredRole={ROLE_PIANIFICATORE_PDC} />}>
        <Route element={<AppLayout />}>
          <Route path="/pianificatore-pdc">
            <Route index element={<Navigate to="/pianificatore-pdc/dashboard" replace />} />
            <Route path="dashboard" element={<PianificatorePdcDashboardRoute />} />
            <Route path="giri" element={<PianificatorePdcGiriRoute />} />
            <Route path="turni" element={<PianificatorePdcTurniRoute />} />
            <Route path="turni/:turnoId" element={<PianificatorePdcTurnoDettaglioRoute />} />
            <Route path="depositi" element={<PianificatorePdcDepositiRoute />} />
            <Route
              path="revisioni-cascading"
              element={<PianificatorePdcRevisioniCascadingRoute />}
            />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<NotFoundRoute />} />
    </Routes>
  );
}
