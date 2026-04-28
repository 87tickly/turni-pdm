import { Link, useParams } from "react-router-dom";
import { AlertCircle, ArrowLeft, AlertTriangle, Bed } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { useGiroDettaglio } from "@/hooks/useGiri";
import { useTurniPdcGiro } from "@/hooks/useTurniPdc";
import { ApiError } from "@/lib/api/client";
import type { TurnoPdcListItem } from "@/lib/api/turniPdc";

export function TurniPdcGiroRoute() {
  const { giroId: giroIdParam } = useParams<{ giroId: string }>();
  const giroId = giroIdParam !== undefined ? Number(giroIdParam) : undefined;
  const giroQuery = useGiroDettaglio(giroId);
  const turniQuery = useTurniPdcGiro(giroId);

  if (giroId === undefined || Number.isNaN(giroId)) {
    return <ErrorBlock message="ID giro non valido nell'URL." />;
  }

  if (giroQuery.isLoading || turniQuery.isLoading) {
    return (
      <div className="flex items-center justify-center rounded-md border border-border bg-white py-16">
        <Spinner label="Caricamento turni PdC…" />
      </div>
    );
  }

  if (turniQuery.isError) {
    const msg =
      turniQuery.error instanceof ApiError
        ? turniQuery.error.message
        : (turniQuery.error as Error).message;
    return <ErrorBlock message={msg} onRetry={() => void turniQuery.refetch()} />;
  }

  const giro = giroQuery.data;
  const turni = turniQuery.data ?? [];

  return (
    <div className="flex flex-col gap-5">
      <Link
        to={`/pianificatore-giro/giri/${giroId}`}
        className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-primary"
      >
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> Dettaglio giro
      </Link>

      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">
          Turni PdC del giro {giro?.numero_turno ?? `#${giroId}`}
        </h1>
        <p className="text-sm text-muted-foreground">
          {turni.length} turn{turni.length === 1 ? "o" : "i"} PdC associat
          {turni.length === 1 ? "o" : "i"} a questo giro materiale.
        </p>
      </header>

      {turni.length === 0 && (
        <div className="rounded-md border border-border bg-white p-8 text-center text-sm text-muted-foreground">
          Nessun turno PdC ancora generato per questo giro. Torna al dettaglio
          e clicca &quot;Genera turno PdC&quot;.
        </div>
      )}

      {turni.length > 0 && <TurniTable turni={turni} />}
    </div>
  );
}

function TurniTable({ turni }: { turni: TurnoPdcListItem[] }) {
  return (
    <div className="overflow-hidden rounded-md border border-border bg-white">
      <table className="w-full text-sm">
        <thead className="bg-secondary/40 text-[10px] uppercase tracking-wider text-muted-foreground">
          <tr>
            <th className="px-3 py-2 text-left">Codice</th>
            <th className="px-3 py-2 text-left">Impianto</th>
            <th className="px-3 py-2 text-left">Profilo</th>
            <th className="px-3 py-2 text-right">Giornate</th>
            <th className="px-3 py-2 text-right">Prestazione</th>
            <th className="px-3 py-2 text-right">Condotta</th>
            <th className="px-3 py-2 text-center">Avvisi</th>
            <th className="px-3 py-2 text-left">Stato</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {turni.map((t) => (
            <tr key={t.id} className="hover:bg-secondary/20">
              <td className="px-3 py-2 font-mono">
                <Link
                  to={`/pianificatore-giro/turni-pdc/${t.id}`}
                  className="text-primary hover:underline"
                >
                  {t.codice}
                </Link>
              </td>
              <td className="px-3 py-2">{t.impianto}</td>
              <td className="px-3 py-2">{t.profilo}</td>
              <td className="px-3 py-2 text-right tabular-nums">{t.n_giornate}</td>
              <td className="px-3 py-2 text-right tabular-nums">
                {formatHM(t.prestazione_totale_min)}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">
                {formatHM(t.condotta_totale_min)}
              </td>
              <td className="px-3 py-2">
                <div className="flex items-center justify-center gap-2">
                  {t.n_violazioni > 0 && (
                    <Badge variant="warning" className="gap-1">
                      <AlertTriangle className="h-3 w-3" aria-hidden /> {t.n_violazioni}
                    </Badge>
                  )}
                  {t.n_dormite_fr > 0 && (
                    <Badge variant="secondary" className="gap-1">
                      <Bed className="h-3 w-3" aria-hidden /> {t.n_dormite_fr}
                    </Badge>
                  )}
                  {t.n_violazioni === 0 && t.n_dormite_fr === 0 && (
                    <span className="text-xs text-muted-foreground">—</span>
                  )}
                </div>
              </td>
              <td className="px-3 py-2">
                <Badge variant="outline">{t.stato}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatHM(min: number): string {
  const h = Math.floor(min / 60);
  const m = min % 60;
  return `${h}h${m.toString().padStart(2, "0")}`;
}

function ErrorBlock({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-4"
    >
      <AlertCircle className="mt-0.5 h-5 w-5 text-destructive" aria-hidden />
      <div className="flex flex-1 flex-col gap-2">
        <p className="text-sm font-medium text-destructive">{message}</p>
        {onRetry !== undefined && (
          <Button variant="outline" size="sm" onClick={onRetry} className="self-start">
            Riprova
          </Button>
        )}
      </div>
    </div>
  );
}
