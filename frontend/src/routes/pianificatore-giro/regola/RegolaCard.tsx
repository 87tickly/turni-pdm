import { Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { useDeleteRegola } from "@/hooks/useProgrammi";
import { ApiError } from "@/lib/api/client";
import type { ProgrammaRegolaAssegnazioneRead } from "@/lib/api/programmi";
import { LABEL_CAMPO, LABEL_OP } from "@/lib/regola/schema";

interface RegolaCardProps {
  regola: ProgrammaRegolaAssegnazioneRead;
  programmaId: number;
  /** Se false → niente bottone elimina (programma non in bozza). */
  editable: boolean;
}

export function RegolaCard({ regola, programmaId, editable }: RegolaCardProps) {
  const deleteMutation = useDeleteRegola();

  const handleDelete = () => {
    if (!window.confirm(`Rimuovere questa regola (priorità ${regola.priorita})?`)) return;
    deleteMutation.mutate(
      { programmaId, regolaId: regola.id },
      {
        onError: (err) => {
          const msg = err instanceof ApiError ? err.message : err.message;
          window.alert(`Eliminazione fallita: ${msg}`);
        },
      },
    );
  };

  return (
    <Card>
      <CardContent className="flex flex-col gap-3 px-4 py-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="default">priorità {regola.priorita}</Badge>
            {regola.km_max_ciclo !== null && (
              <Badge variant="outline" title="Cap km del ciclo per questa regola/materiale">
                cap {regola.km_max_ciclo.toLocaleString("it-IT")} km
              </Badge>
            )}
            {regola.is_composizione_manuale && (
              <Badge variant="warning">composizione manuale</Badge>
            )}
          </div>
          {editable && (
            <Button
              size="sm"
              variant="ghost"
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
              aria-label="Rimuovi regola"
              title="Rimuovi regola"
            >
              <Trash2 className="h-4 w-4" aria-hidden />
            </Button>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Filtri
          </p>
          {regola.filtri_json.length === 0 ? (
            <p className="text-sm italic text-muted-foreground">
              Nessuno — la regola si applica a tutte le corse del programma.
            </p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {regola.filtri_json.map((f, i) => (
                <FiltroChip key={i} filtro={f} />
              ))}
            </div>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Composizione
          </p>
          <div className="flex flex-wrap gap-1.5">
            {regola.composizione_json.map((c, i) => (
              <Badge key={i} variant="secondary">
                {c.materiale_tipo_codice} × {c.n_pezzi}
              </Badge>
            ))}
          </div>
        </div>

        {regola.note !== null && regola.note.length > 0 && (
          <p className="rounded-md bg-secondary/40 px-3 py-2 text-sm text-muted-foreground">
            {regola.note}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function FiltroChip({ filtro }: { filtro: { campo: string; op: string; valore: unknown } }) {
  const label = LABEL_CAMPO[filtro.campo as keyof typeof LABEL_CAMPO] ?? filtro.campo;
  const op = LABEL_OP[filtro.op] ?? filtro.op;
  const valore = formatValore(filtro.valore);
  return (
    <Badge variant="outline" className="font-normal">
      <span className="text-foreground">{label}</span>
      <span className="mx-1 text-muted-foreground">{op}</span>
      <span className="font-mono text-primary">{valore}</span>
    </Badge>
  );
}

function formatValore(v: unknown): string {
  if (Array.isArray(v)) return v.map((x) => String(x)).join(" / ");
  if (typeof v === "boolean") return v ? "Sì" : "No";
  return String(v);
}
