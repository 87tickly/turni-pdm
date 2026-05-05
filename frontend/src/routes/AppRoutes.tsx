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
import { GestionePersonaleCalendarioRoute } from "@/routes/gestione-personale/CalendarioRoute";
import { GestionePersonaleDashboardRoute } from "@/routes/gestione-personale/DashboardRoute";
import { GestionePersonaleDepositiRoute } from "@/routes/gestione-personale/DepositiRoute";
import { GestionePersonaleDepositoDettaglioRoute } from "@/routes/gestione-personale/DepositoDettaglioRoute";
import { GestionePersonaleIndisponibilitaRoute } from "@/routes/gestione-personale/IndisponibilitaRoute";
import { GestionePersonaleLayout } from "@/routes/gestione-personale/GestionePersonaleLayout";
import { GestionePersonalePersonaDettaglioRoute } from "@/routes/gestione-personale/PersonaDettaglioRoute";
import { GestionePersonalePersoneRoute } from "@/routes/gestione-personale/PersoneRoute";
import { ManutenzioneDashboardRoute } from "@/routes/manutenzione/DashboardRoute";
import { PersonalePdcMioTurnoRoute } from "@/routes/personale-pdc/MioTurnoRoute";
import { PianificatorePdcDashboardRoute } from "@/routes/pianificatore-pdc/DashboardRoute";
import { PianificatorePdcGiriRoute } from "@/routes/pianificatore-pdc/GiriRoute";
import { PianificatorePdcRevisioniCascadingRoute } from "@/routes/pianificatore-pdc/RevisioniCascadingRoute";
import { PianificatorePdcTurniRoute } from "@/routes/pianificatore-pdc/TurniRoute";
import { PianificatorePdcTurnoDettaglioRoute } from "@/routes/pianificatore-pdc/TurnoDettaglioRoute";
// Note: GiriRoute e TurniRoute (Sprint 7.3 MR 2) non sono più placeholder
// ma componenti completi che usano gli endpoint cross-azienda backend.

const ROLE_PIANIFICATORE_GIRO = "PIANIFICATORE_GIRO";
const ROLE_PIANIFICATORE_PDC = "PIANIFICATORE_PDC";
const ROLE_GESTIONE_PERSONALE = "GESTIONE_PERSONALE";
const ROLE_PERSONALE_PDC = "PERSONALE_PDC";
const ROLE_MANUTENZIONE = "MANUTENZIONE";

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
            {/* Sprint 7.9 MR ζ: i depositi PdC sono migrati sotto Gestione
                Personale. Redirect dalla vecchia path per non rompere
                eventuali bookmark. */}
            <Route
              path="depositi"
              element={<Navigate to="/gestione-personale/depositi" replace />}
            />
            <Route
              path="revisioni-cascading"
              element={<PianificatorePdcRevisioniCascadingRoute />}
            />
          </Route>
        </Route>
      </Route>

      {/* Dashboard 4 — Gestione Personale (Sprint 7.9 MR ζ + 7.10 MR β.1 redesign) */}
      <Route element={<ProtectedRoute requiredRole={ROLE_GESTIONE_PERSONALE} />}>
        <Route element={<AppLayout />}>
          {/* Layout intermedio: GestionePersonaleLayout monta provider + overlays
              + command palette + tweaks panel cross-route. Vedi
              `frontend/src/routes/gestione-personale/GestionePersonaleLayout.tsx`. */}
          <Route element={<GestionePersonaleLayout />}>
            <Route path="/gestione-personale">
              <Route index element={<Navigate to="/gestione-personale/dashboard" replace />} />
              <Route path="dashboard" element={<GestionePersonaleDashboardRoute />} />
              <Route path="persone" element={<GestionePersonalePersoneRoute />} />
              <Route
                path="persone/:personaId"
                element={<GestionePersonalePersonaDettaglioRoute />}
              />
              <Route path="depositi" element={<GestionePersonaleDepositiRoute />} />
              <Route
                path="depositi/:codice"
                element={<GestionePersonaleDepositoDettaglioRoute />}
              />
              <Route path="calendario" element={<GestionePersonaleCalendarioRoute />} />
              <Route
                path="indisponibilita"
                element={<GestionePersonaleIndisponibilitaRoute />}
              />
            </Route>
          </Route>
        </Route>
      </Route>

      {/* Dashboard 5 — Personale PdC (Sprint 8.0 MR 3, entry 168) */}
      <Route element={<ProtectedRoute requiredRole={ROLE_PERSONALE_PDC} />}>
        <Route element={<AppLayout />}>
          <Route path="/personale-pdc">
            <Route index element={<Navigate to="/personale-pdc/mio-turno" replace />} />
            <Route path="mio-turno" element={<PersonalePdcMioTurnoRoute />} />
          </Route>
        </Route>
      </Route>

      {/* Dashboard 6 — Manutenzione (Sprint 8.0 MR 4, entry 169) */}
      <Route element={<ProtectedRoute requiredRole={ROLE_MANUTENZIONE} />}>
        <Route element={<AppLayout />}>
          <Route path="/manutenzione">
            <Route index element={<Navigate to="/manutenzione/dashboard" replace />} />
            <Route path="dashboard" element={<ManutenzioneDashboardRoute />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<NotFoundRoute />} />
    </Routes>
  );
}
