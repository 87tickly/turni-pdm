import { PlaceholderPage } from "@/routes/pianificatore-giro/PlaceholderPage";

/** Vista giri materiali (sola lettura) — placeholder Sprint 7.3 MR 2. */
export function PianificatorePdcGiriRoute() {
  return (
    <PlaceholderPage
      title="Vista giri materiali"
      description="Lista dei giri pubblicati dal Pianificatore Giro, in sola lettura."
      sub="Sprint 7.3 MR 2"
      endpoint="GET /api/giri (read-only, scoped azienda)"
    />
  );
}
