import { PlaceholderPage } from "@/routes/pianificatore-giro/PlaceholderPage";

/**
 * Editor turno PdC sotto path PIANIFICATORE_PDC — placeholder Sprint 7.3 MR 3.
 *
 * In MR 3 verrà aliasato/integrato il componente Gantt esistente (oggi
 * `routes/pianificatore-giro/TurnoPdcDettaglioRoute.tsx`) sotto questo
 * path, con il ruolo PIANIFICATORE_PDC abilitato alle scritture.
 */
export function PianificatorePdcTurnoDettaglioRoute() {
  return (
    <PlaceholderPage
      title="Editor turno PdC"
      description="Visualizzatore Gantt giornaliero con badge validazioni cap prestazione/condotta/refezione."
      sub="Sprint 7.3 MR 3"
      endpoint="GET /api/turni-pdc/:turnoId"
    />
  );
}
