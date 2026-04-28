import { Badge } from "@/components/ui/Badge";
import type { ProgrammaStato } from "@/lib/api/programmi";

const LABELS: Record<ProgrammaStato, string> = {
  bozza: "Bozza",
  attivo: "Attivo",
  archiviato: "Archiviato",
};

const VARIANTS: Record<ProgrammaStato, "warning" | "success" | "muted"> = {
  bozza: "warning",
  attivo: "success",
  archiviato: "muted",
};

export function ProgrammaStatoBadge({ stato }: { stato: ProgrammaStato }) {
  return <Badge variant={VARIANTS[stato]}>{LABELS[stato]}</Badge>;
}
