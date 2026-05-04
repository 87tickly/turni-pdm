import { useMemo } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, ArrowRight, Building2 } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { useDepots } from "@/hooks/useAnagrafiche";
import { usePianificatorePdcOverview } from "@/hooks/usePianificatorePdc";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";

/**
 * Sprint 7.11 MR 7.11.3 — Depositi PdC Trenord (anagrafica).
 *
 * Anteprima del futuro ruolo GESTIONE_PERSONALE: per ora la route vive
 * sotto path `/pianificatore-pdc/depositi` (drilldown del 2° ruolo) e
 * mostra in lettura le 25 voci canoniche dei depositi PdC Trenord.
 * Quando il ruolo (4) sarà implementato, sposteremo la route sotto
 * `/gestione-personale/depositi` con CRUD + assegnazione personale.
 *
 * Cross-reference con turni: usa l'overview PdC per indicare quanti
 * turni sono assegnati a ciascun deposito (1 sola fetch riusata).
 */
export function PianificatorePdcDepositiRoute() {
  const depotsQuery = useDepots();
  const overview = usePianificatorePdcOverview();

  // Map codice impianto → count turni dall'overview (cross-azienda).
  const turniByImpianto = useMemo(() => {
    const map = new Map<string, number>();
    overview.data?.turni_pdc_per_impianto.forEach((item) => {
      map.set(item.impianto, item.count);
    });
    return map;
  }, [overview.data]);

  const depots = depotsQuery.data ?? [];
  const totale = depots.length;
  const conTurni = useMemo(
    () => depots.filter((d) => (turniByImpianto.get(d.codice) ?? 0) > 0).length,
    [depots, turniByImpianto],
  );

  return (
    <div className="flex flex-col gap-5">
      {/* breadcrumb */}
      <div className="text-xs text-muted-foreground">
        Home <span className="mx-1 text-muted-foreground/40">/</span> Depositi PdC
      </div>

      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-primary">
            <Building2 className="h-6 w-6 text-primary/70" aria-hidden />
            Depositi PdC Trenord
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Anagrafica dei depositi del personale di macchina. Anteprima del
            futuro ruolo{" "}
            <span className="font-medium text-foreground">
              Gestione Personale
            </span>
            : qui in sola lettura, da Sprint 7.6+ aggiungeremo CRUD,
            assegnazioni, indisponibilità.
          </p>
        </div>
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" aria-hidden />
            <span>
              <span className="font-mono tabular-nums text-foreground">{conTurni}</span> con turni
            </span>
          </span>
          <span className="text-muted-foreground/40">|</span>
          <span>
            <span className="font-mono tabular-nums text-foreground">{totale}</span> depositi
            totali
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
                  <th className="w-40 px-3 py-2 text-left font-semibold">
                    Stazione principale
                  </th>
                  <th className="w-32 px-3 py-2 text-right font-semibold">Turni PdC</th>
                  <th className="w-8 px-3 py-2" aria-hidden />
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {depots.map((d, i) => {
                  const turniCount = turniByImpianto.get(d.codice) ?? 0;
                  const hasTurni = turniCount > 0;
                  return (
                    <tr
                      key={d.codice}
                      className={cn(
                        "transition-colors",
                        hasTurni ? "hover:bg-primary/[0.03]" : "hover:bg-muted/40",
                      )}
                    >
                      <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground">
                        {String(i + 1).padStart(2, "0")}
                      </td>
                      <td className="px-3 py-2.5 font-mono text-[13px] font-semibold text-primary">
                        {d.codice}
                      </td>
                      <td className="px-3 py-2.5 text-foreground/80">{d.display_name}</td>
                      <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground">
                        {d.stazione_principale_codice ?? "—"}
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        {hasTurni ? (
                          <Link
                            to={`/pianificatore-pdc/turni?impianto=${encodeURIComponent(d.codice)}`}
                            className="inline-flex items-center gap-1.5 font-mono tabular-nums text-primary hover:underline"
                          >
                            {turniCount}
                            <ArrowRight className="h-3 w-3" aria-hidden />
                          </Link>
                        ) : (
                          <Badge variant="outline" className="text-[9px]">
                            nessun turno
                          </Badge>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        {hasTurni && (
                          <span
                            className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500"
                            aria-hidden
                          />
                        )}
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
            (NORMATIVA-PDC §2.1) inserito dalla migration{" "}
            <span className="font-mono">0002_seed_trenord</span>.
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
