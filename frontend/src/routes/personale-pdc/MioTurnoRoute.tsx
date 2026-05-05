/**
 * Vista PdC finale (Sprint 8.0 MR 3, entry 168).
 *
 * Il singolo macchinista vede le proprie giornate di assegnazione,
 * filtrate server-side per programmi in stato pipeline
 * ``VISTA_PUBBLICATA``. Layout minimale: tabella ordinata per data.
 *
 * Niente edit, niente regenerate: il PdC è il consumatore finale del
 * lavoro di Pianificatori Giro/PdC + Gestione Personale.
 */

import { CalendarDays, Moon } from "lucide-react";

import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { useAuth } from "@/lib/auth/AuthContext";
import { useMioTurno } from "@/hooks/usePersonalePdc";
import { ApiError } from "@/lib/api/client";
import { formatDateIt } from "@/lib/format";
import type { MioTurnoGiornata } from "@/lib/api/personalePdc";

export function PersonalePdcMioTurnoRoute() {
  const { user } = useAuth();
  const query = useMioTurno();

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold tracking-tight text-primary">
          Il mio turno
        </h1>
        <p className="text-sm text-muted-foreground">
          Benvenuto{user !== null ? `, ${user.username}` : ""}. Qui trovi le
          giornate di servizio assegnate, filtrate per programmi pubblicati.
        </p>
      </header>

      {query.isLoading ? (
        <Card className="flex items-center justify-center p-8">
          <Spinner label="Caricamento turni…" />
        </Card>
      ) : query.isError ? (
        <Card className="border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
          {query.error instanceof ApiError
            ? query.error.message
            : (query.error as Error).message}
        </Card>
      ) : (query.data ?? []).length === 0 ? (
        <EmptyState />
      ) : (
        <MioTurnoTable rows={query.data ?? []} />
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <Card className="flex flex-col items-center gap-2 p-8 text-center text-sm text-muted-foreground">
      <CalendarDays className="h-8 w-8 text-muted-foreground/50" aria-hidden />
      <span>Nessuna giornata di servizio disponibile.</span>
      <span className="text-xs text-muted-foreground/70">
        Le tue giornate compariranno qui non appena un programma sarà pubblicato.
      </span>
    </Card>
  );
}

function MioTurnoTable({ rows }: { rows: MioTurnoGiornata[] }) {
  return (
    <Card className="overflow-hidden p-0">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/40 text-left text-[10px] uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="px-3 py-2">Data</th>
              <th className="px-3 py-2">Turno</th>
              <th className="px-3 py-2">Giornata</th>
              <th className="px-3 py-2">Inizio</th>
              <th className="px-3 py-2">Fine</th>
              <th className="px-3 py-2 text-right">Prestaz.</th>
              <th className="px-3 py-2 text-right">Condotta</th>
              <th className="px-3 py-2">Note</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.assegnazione_id}
                className="border-b border-border last:border-b-0 hover:bg-muted/20"
              >
                <td className="px-3 py-2 font-medium tabular-nums">
                  {formatDateIt(r.data)}
                </td>
                <td className="px-3 py-2">
                  <span className="font-mono text-xs">{r.turno_codice}</span>
                  <span className="ml-2 text-xs text-muted-foreground">
                    {r.turno_impianto}
                  </span>
                </td>
                <td className="px-3 py-2 tabular-nums">
                  {r.numero_giornata}
                </td>
                <td className="px-3 py-2 tabular-nums">
                  {r.inizio_prestazione ?? "—"}
                </td>
                <td className="px-3 py-2 tabular-nums">
                  {r.fine_prestazione ?? "—"}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatMin(r.prestazione_min)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatMin(r.condotta_min)}
                </td>
                <td className="px-3 py-2 text-xs text-muted-foreground">
                  {r.is_notturno ? (
                    <span className="inline-flex items-center gap-1">
                      <Moon className="h-3 w-3" aria-hidden /> notturno
                    </span>
                  ) : null}
                  {r.is_riposo ? <span className="ml-2">riposo</span> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function formatMin(minuti: number): string {
  if (minuti <= 0) return "—";
  const h = Math.floor(minuti / 60);
  const m = minuti % 60;
  return `${h}h${m.toString().padStart(2, "0")}`;
}
