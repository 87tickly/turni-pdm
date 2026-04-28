import { useParams } from "react-router-dom";

import { PlaceholderPage } from "@/routes/pianificatore-giro/PlaceholderPage";

export function ProgrammaGiriRoute() {
  const { programmaId } = useParams<{ programmaId: string }>();
  return (
    <PlaceholderPage
      title={`Giri del programma #${programmaId ?? "?"}`}
      description="Lista giri persistiti del programma con stats (km, n. giornate, motivo chiusura)."
      sub="Sub 6.4"
      endpoint={`GET /api/programmi/${programmaId ?? ":id"}/giri`}
    />
  );
}
