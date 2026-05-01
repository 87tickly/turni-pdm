import { PlaceholderPage } from "@/routes/pianificatore-giro/PlaceholderPage";

/** Lista turni PdC cross-giro — placeholder Sprint 7.3 MR 2. */
export function PianificatorePdcTurniRoute() {
  return (
    <PlaceholderPage
      title="Lista turni PdC"
      description="Tutti i turni PdC dell'azienda con filtri per impianto, stato, validità."
      sub="Sprint 7.3 MR 2"
      endpoint="GET /api/turni-pdc?azienda_id=…&impianto=…"
    />
  );
}
