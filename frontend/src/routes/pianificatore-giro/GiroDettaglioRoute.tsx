import { useParams } from "react-router-dom";

import { PlaceholderPage } from "@/routes/pianificatore-giro/PlaceholderPage";

export function GiroDettaglioRoute() {
  const { giroId } = useParams<{ giroId: string }>();
  return (
    <PlaceholderPage
      title={`Giro #${giroId ?? "?"}`}
      description="Visualizzatore Gantt del giro: giornate, blocchi commerciali, vuoti, rientro 9NNNN."
      sub="Sub 6.5"
      endpoint={`GET /api/giri/${giroId ?? ":id"}`}
    />
  );
}
