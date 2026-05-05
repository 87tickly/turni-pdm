import { useMemo } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, ArrowRight, Building2 } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { useDepots } from "@/hooks/useAnagrafiche";
import { useGestionePersonaleKpiDepositi } from "@/hooks/useGestionePersonale";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";

/**
 * Sprint 7.9 MR ζ — Depositi PdC (Gestione Personale).
 *
 * Migrazione della precedente `pianificatore-pdc/DepositiRoute.tsx` sotto
 * il ruolo Gestione Personale (a cui i depositi PdC concettualmente
 * appartengono). Arricchita con KPI per deposito: PdC attivi, in
 * servizio oggi, copertura % — tutti drill-downable cliccando sulla
 * riga.
 */
export function GestionePersonaleDepositiRoute() {
  const depotsQuery = useDepots();
  const kpi = useGestionePersonaleKpiDepositi();

  const kpiByDepot = useMemo(() => {
    const m = new Map<string, { attivi: number; in_servizio: number; copertura: number }>();
    (kpi.data ?? []).forEach((k) =>
      m.set(k.depot_codice, {
        attivi: k.persone_attive,
        in_servizio: k.in_servizio_oggi,
        copertura: k.copertura_pct,
      }),
    );
    return m;
  }, [kpi.data]);

  const depots = useMemo(() => depotsQuery.data ?? [], [depotsQuery.data]);
  const totale = depots.length;
  const conPersone = useMemo(
    () => depots.filter((d) => (kpiByDepot.get(d.codice)?.attivi ?? 0) > 0).length,
    [depots, kpiByDepot],
  );

  return (
    <div className="flex flex-col gap-5">
      <div className="text-xs text-muted-foreground">
        <Link to="/gestione-personale/dashboard" className="hover:text-primary">
          Home
        </Link>
        <span className="mx-1 text-muted-foreground/40">/</span>
        Depositi PdC
      </div>

      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-primary">
            <Building2 className="h-6 w-6 text-primary/70" aria-hidden />
            Depositi PdC Trenord
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Anagrafica depositi del personale di macchina con conta PdC
            assegnati e copertura giornaliera. Click su un deposito per il
            drilldown.
          </p>
        </div>
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" aria-hidden />
            <span>
              <span className="font-mono tabular-nums text-foreground">{conPersone}</span> con PdC
            </span>
          </span>
          <span className="text-muted-foreground/40">|</span>
          <span>
            <span className="font-mono tabular-nums text-foreground">{totale}</span> totali
          </span>
        </div>
      </header>

      {depotsQuery.isLoading ? (
        <div className="flex items-center justify-center rounded-md border border-border bg-white py-16">
          <Spinner label="Caricamento depositi…" />
        </div>
      ) : depotsQuery.isError ? (
        <ErrorBlock
          message={
            depotsQuery.error instanceof ApiError
              ? depotsQuery.error.message
              : (depotsQuery.error as Error).message
          }
          onRetry={() => void depotsQuery.refetch()}
        />
      ) : depots.length === 0 ? (
        <EmptyState />
      ) : (
        <section className="overflow-hidden rounded-lg border border-border bg-white">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50 text-[10px] uppercase tracking-wider text-muted-foreground">
                  <th className="w-12 px-3 py-2 text-left font-semibold">#</th>
                  <th className="w-44 px-3 py-2 text-left font-semibold">Codice</th>
                  <th className="px-3 py-2 text-left font-semibold">Nome esteso</th>
                  <th className="w-24 px-3 py-2 text-right font-semibold">PdC</th>
                  <th className="w-28 px-3 py-2 text-right font-semibold">In servizio</th>
                  <th className="w-32 px-3 py-2 text-right font-semibold">Copertura</th>
                  <th className="w-8 px-3 py-2" aria-hidden />
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {depots.map((d, i) => {
                  const k = kpiByDepot.get(d.codice);
                  const attivi = k?.attivi ?? 0;
                  const inServ = k?.in_servizio ?? 0;
                  const cop = k?.copertura ?? 0;
                  const pctClass =
                    attivi === 0
                      ? "text-muted-foreground/40"
                      : cop >= 90
                        ? "text-emerald-700"
                        : cop >= 80
                          ? "text-amber-700"
                          : "text-red-700";
                  return (
                    <tr
                      key={d.codice}
                      className="transition-colors hover:bg-primary/[0.03]"
                    >
                      <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground">
                        {String(i + 1).padStart(2, "0")}
                      </td>
                      <td className="px-3 py-2.5">
                        <Link
                          to={`/gestione-personale/depositi/${encodeURIComponent(d.codice)}`}
                          className="font-mono text-[13px] font-semibold text-primary hover:underline"
                        >
                          {d.codice}
                        </Link>
                      </td>
                      <td className="px-3 py-2.5 text-foreground/80">{d.display_name}</td>
                      <td className="px-3 py-2.5 text-right font-mono tabular-nums">
                        {attivi > 0 ? (
                          attivi
                        ) : (
                          <Badge variant="outline" className="text-[9px]">
                            vuoto
                          </Badge>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono tabular-nums text-emerald-700">
                        {attivi > 0 ? inServ : "—"}
                      </td>
                      <td className={cn("px-3 py-2.5 text-right font-mono tabular-nums font-semibold", pctClass)}>
                        {attivi > 0 ? `${cop.toFixed(1)}%` : "—"}
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <ArrowRight className="h-3 w-3 text-muted-foreground/40" aria-hidden />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="border-t border-border bg-muted/30 px-4 py-2 text-[11px] text-muted-foreground">
            Anagrafica caricata da{" "}
            <span className="font-mono">/api/depots</span> · seed Trenord
            (NORMATIVA-PDC §2.1) — KPI da{" "}
            <span className="font-mono">/api/gestione-personale/kpi-depositi</span>
            .
          </div>
        </section>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-md border border-dashed border-border bg-white py-16 text-center">
      <Building2 className="h-10 w-10 text-muted-foreground/40" aria-hidden />
      <h2 className="text-base font-semibold">Nessun deposito PdC</h2>
      <p className="max-w-md text-sm text-muted-foreground">
        L'anagrafica depositi PdC è alimentata da{" "}
        <span className="font-mono">/api/depots</span>. Se il backend è
        appena inizializzato, la migration{" "}
        <span className="font-mono">0002_seed_trenord</span> popolerà
        automaticamente i 25 depositi Trenord.
      </p>
    </div>
  );
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
