import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "@/components/layout/AppLayout";
import { ForbiddenRoute } from "@/routes/ForbiddenRoute";
import { LoginRoute } from "@/routes/LoginRoute";
import { NotFoundRoute } from "@/routes/NotFoundRoute";
import { ProtectedRoute } from "@/routes/ProtectedRoute";
import { DashboardRoute } from "@/routes/pianificatore-giro/DashboardRoute";
import { GiroDettaglioRoute } from "@/routes/pianificatore-giro/GiroDettaglioRoute";
import { ProgrammaDettaglioRoute } from "@/routes/pianificatore-giro/ProgrammaDettaglioRoute";
import { ProgrammaGiriRoute } from "@/routes/pianificatore-giro/ProgrammaGiriRoute";
import { ProgrammiRoute } from "@/routes/pianificatore-giro/ProgrammiRoute";
import { TurniPdcGiroRoute } from "@/routes/pianificatore-giro/TurniPdcGiroRoute";
import { TurnoPdcDettaglioRoute } from "@/routes/pianificatore-giro/TurnoPdcDettaglioRoute";

const ROLE_PIANIFICATORE_GIRO = "PIANIFICATORE_GIRO";

/**
 * Tabella route dichiarativa.
 *
 * Pubblico: /login, /forbidden, fallback 404.
 * Protetto (ruolo PIANIFICATORE_GIRO o admin):
 *   /, /pianificatore-giro/* (5 schermate, Sub 6.1-6.5).
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginRoute />} />
      <Route path="/forbidden" element={<ForbiddenRoute />} />

      <Route element={<ProtectedRoute requiredRole={ROLE_PIANIFICATORE_GIRO} />}>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/pianificatore-giro/dashboard" replace />} />
          <Route path="/pianificatore-giro">
            <Route index element={<Navigate to="/pianificatore-giro/dashboard" replace />} />
            <Route path="dashboard" element={<DashboardRoute />} />
            <Route path="programmi" element={<ProgrammiRoute />} />
            <Route path="programmi/:programmaId" element={<ProgrammaDettaglioRoute />} />
            <Route path="programmi/:programmaId/giri" element={<ProgrammaGiriRoute />} />
            <Route path="giri/:giroId" element={<GiroDettaglioRoute />} />
            <Route path="giri/:giroId/turni-pdc" element={<TurniPdcGiroRoute />} />
            <Route path="turni-pdc/:turnoId" element={<TurnoPdcDettaglioRoute />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<NotFoundRoute />} />
    </Routes>
  );
}
