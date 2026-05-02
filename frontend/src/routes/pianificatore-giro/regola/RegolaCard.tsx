import { Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
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

/**
 * Card singola regola di assegnazione (layout design `arturo/03-dettaglio-programma.html`):
 * colonna priorità grande a sinistra (14ch), corpo a destra con cap km top-right,
 * filtri come chip grigi (font-mono), composizione come chip blu, eventuale note.
 */
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
    <Card className="p-5">
      <div className="flex items-start gap-5">
        {/* Priorità (sx) */}
        <div className="w-14 shrink-0 text-center">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Prio</div>
          <div className="mt-0.5 text-2xl font-semibold tabular-nums text-foreground">
            {regola.priorita}
          </div>
        </div>

        {/* Corpo (dx) */}
        <div className="min-w-0 flex-1">
          <div className="mb-3 flex items-start justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              {regola.is_composizione_manuale && (
                <Badge variant="warning" className="rounded text-[10px] uppercase">
                  Manuale
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-3">
              <span
                className="text-xs text-muted-foreground tabular-nums"
                title="Cap km del ciclo per questa regola/materiale"
              >
                {regola.km_max_ciclo !== null
                  ? `cap km/ciclo · ${regola.km_max_ciclo.toLocaleString("it-IT")}`
                  : "cap km · ereditato"}
              </span>
              {editable && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={handleDelete}
                  disabled={deleteMutation.isPending}
                  aria-label="Rimuovi regola"
                  title="Rimuovi regola"
                  className="h-7 w-7 p-0"
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden />
                </Button>
              )}
            </div>
          </div>

          {/* Filtri */}
          <div className="mb-3">
            <div className="mb-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">
              Filtri
            </div>
            {regola.filtri_json.length === 0 ? (
              <p className="text-xs italic text-muted-foreground">
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

          {/* Composizione */}
          <div>
            <div className="mb-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">
              Composizione
            </div>
            <div className="flex flex-wrap gap-1.5">
              {regola.composizione_json.map((c, i) => (
                <span
                  key={i}
                  className="inline-flex items-center rounded border border-blue-100 bg-blue-50 px-2 py-0.5 font-mono text-xs text-blue-800"
                >
                  {c.materiale_tipo_codice} × {c.n_pezzi}
                </span>
              ))}
            </div>
          </div>

          {/* Note */}
          {regola.note !== null && regola.note.length > 0 && (
            <div className="mt-3 border-t border-border pt-3 text-xs italic text-muted-foreground">
              Note: {regola.note}
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

function FiltroChip({ filtro }: { filtro: { campo: string; op: string; valore: unknown } }) {
  const label = LABEL_CAMPO[filtro.campo as keyof typeof LABEL_CAMPO] ?? filtro.campo;
  const op = LABEL_OP[filtro.op] ?? filtro.op;
  const valore = formatValore(filtro.valore);
  return (
    <span className="inline-flex items-center rounded bg-muted px-2 py-0.5 font-mono text-xs text-foreground">
      <span>{label}</span>
      <span className="mx-1 text-muted-foreground">{op}</span>
      <span className="text-primary">{valore}</span>
    </span>
  );
}

function formatValore(v: unknown): string {
  if (Array.isArray(v)) return v.map((x) => String(x)).join(" / ");
  if (typeof v === "boolean") return v ? "Sì" : "No";
  return String(v);
}
