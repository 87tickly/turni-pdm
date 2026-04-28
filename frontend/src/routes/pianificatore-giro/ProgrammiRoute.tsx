import { PlaceholderPage } from "@/routes/pianificatore-giro/PlaceholderPage";

export function ProgrammiRoute() {
  return (
    <PlaceholderPage
      title="Programmi materiale"
      description="Lista programmi (bozza/attivo/archiviato) della tua azienda."
      sub="Sub 6.2"
      endpoint="GET /api/programmi"
    />
  );
}
