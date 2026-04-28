import { useParams } from "react-router-dom";

import { PlaceholderPage } from "@/routes/pianificatore-giro/PlaceholderPage";

export function ProgrammaDettaglioRoute() {
  const { programmaId } = useParams<{ programmaId: string }>();
  return (
    <PlaceholderPage
      title={`Programma #${programmaId ?? "?"}`}
      description="Dettaglio programma + editor regole con menu da anagrafiche (stazioni, materiali, direttrici, sedi, depots)."
      sub="Sub 6.3"
      endpoint={`GET /api/programmi/${programmaId ?? ":id"}`}
    />
  );
}
