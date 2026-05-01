import { PlaceholderPage } from "@/routes/pianificatore-giro/PlaceholderPage";

/**
 * Revisioni cascading — placeholder Sprint 7.6+.
 *
 * Scope-out dichiarato di Sprint 7.3: il modello `revisione_provvisoria`
 * non esiste ancora nel codice (è in `MODELLO-DATI.md` ma non implementato).
 * Implementarlo richiede migration + nuova entità + algoritmo di
 * propagazione dalle revisioni giro al turno PdC.
 */
export function PianificatorePdcRevisioniCascadingRoute() {
  return (
    <PlaceholderPage
      title="Revisioni cascading"
      description="Quando il Pianificatore Giro pubblica una revisione provvisoria, qui arriva la proposta di cascading PdC automaticamente calcolata."
      sub="Sprint 7.6+ — richiede modello `revisione_provvisoria`"
      endpoint="GET /api/revisioni-cascading (futuro)"
    />
  );
}
