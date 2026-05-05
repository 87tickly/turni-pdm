import { useMemo } from "react";
import type { ComponentType, SVGProps } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowRight, Building2, ShieldCheck, Users } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { useDepots } from "@/hooks/useAnagrafiche";
import {
  useGestionePersonaleKpiDepositi,
  usePersoneByDepot,
} from "@/hooks/useGestionePersonale";
import { cn } from "@/lib/utils";

/**
 * Sprint 7.9 MR ζ — Drilldown deposito (Gestione Personale).
 *
 * Mostra l'header del deposito + tabella dei PdC residenti, con stato
 * "in servizio / ferie / malattia / ROL / altro" per ognuno. Il KPI
 * di copertura è ripreso dall'endpoint dashboard.
 */
export function GestionePersonaleDepositoDettaglioRoute() {
  const { codice } = useParams<{ codice: string }>();
  const persone = usePersoneByDepot(codice);
  const depots = useDepots();
  const kpi = useGestionePersonaleKpiDepositi();

  const depot = useMemo(
    () => (depots.data ?? []).find((d) => d.codice === codice),
    [depots.data, codice],
  );
  const kpiDepot = useMemo(
    () => (kpi.data ?? []).find((k) => k.depot_codice === codice),
    [kpi.data, codice],
  );

  const inServizio = useMemo(
    () => (persone.data ?? []).filter((p) => p.indisponibilita_oggi === null).length,
    [persone.data],
  );
  const indisp = useMemo(
    () => (persone.data ?? []).filter((p) => p.indisponibilita_oggi !== null),
    [persone.data],
  );

  const pctClass =
    kpiDepot === undefined || kpiDepot.persone_attive === 0
      ? "text-muted-foreground/40"
      : kpiDepot.copertura_pct >= 90
        ? "text-emerald-700"
        : kpiDepot.copertura_pct >= 80
          ? "text-amber-700"
          : "text-red-700";

  return (
    <div className="flex flex-col gap-5">
      <div className="text-xs text-muted-foreground">
        <Link to="/gestione-personale/dashboard" className="hover:text-primary">
          Home
        </Link>
        <span className="mx-1 text-muted-foreground/40">/</span>
        <Link to="/gestione-personale/depositi" className="hover:text-primary">
          Depositi
        </Link>
        <span className="mx-1 text-muted-foreground/40">/</span>
        <span className="font-mono">{codice}</span>
      </div>

      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-primary">
            <Building2 className="h-6 w-6 text-primary/70" aria-hidden />
            {depot?.display_name ?? codice}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Codice deposito{" "}
            <span className="font-mono text-foreground">{codice}</span>
            {depot?.stazione_principale_codice !== null &&
              depot?.stazione_principale_codice !== undefined && (
                <>
                  {" "}· Stazione principale{" "}
                  <span className="font-mono text-foreground">
                    {depot.stazione_principale_codice}
                  </span>
                </>
              )}
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <KpiPill icon={Users} label="PdC attivi" value={kpiDepot?.persone_attive ?? 0} />
          <KpiPill
            icon={ShieldCheck}
            label="In servizio"
            value={inServizio}
            tone="success"
          />
          {kpiDepot !== undefined && kpiDepot.persone_attive > 0 && (
            <span className={cn("font-mono text-base font-bold tabular-nums", pctClass)}>
              {kpiDepot.copertura_pct.toFixed(1)}%
            </span>
          )}
        </div>
      </header>

      {persone.isLoading ? (
        <div className="flex items-center justify-center rounded-md border border-border bg-white py-16">
          <Spinner label="Caricamento PdC del deposito…" />
        </div>
      ) : persone.isError ? (
        <p className="rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive" role="alert">
          Errore: {persone.error?.message ?? "errore sconosciuto"}
        </p>
      ) : (persone.data ?? []).length === 0 ? (
        <Card className="flex flex-col items-center gap-3 py-12 text-center">
          <Users className="h-10 w-10 text-muted-foreground/40" aria-hidden />
          <h2 className="text-base font-semibold">Nessun PdC assegnato</h2>
          <p className="max-w-md text-sm text-muted-foreground">
            Questo deposito non ha PdC residenti. L'anagrafica si popola
            inserendo persone con sede di residenza{" "}
            <span className="font-mono">{codice}</span>.
          </p>
        </Card>
      ) : (
        <>
          {indisp.length > 0 && (
            <Card className="flex items-start gap-3 border-amber-300 bg-amber-50 p-4">
              <Users className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" aria-hidden />
              <div className="flex-1">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-amber-700">
                  Indisponibilità in corso
                </div>
                <div className="text-sm text-amber-900">
                  {indisp.length} PdC su {(persone.data ?? []).length} non sono in servizio
                  oggi: {indisp.map((p) => `${p.cognome} ${p.nome}`).join(", ")}.
                </div>
              </div>
            </Card>
          )}

          <section className="overflow-hidden rounded-lg border border-border bg-white">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/50 text-[10px] uppercase tracking-wider text-muted-foreground">
                    <th className="w-12 px-3 py-2 text-left font-semibold">#</th>
                    <th className="w-28 px-3 py-2 text-left font-semibold">Matricola</th>
                    <th className="px-3 py-2 text-left font-semibold">Cognome e nome</th>
                    <th className="w-20 px-3 py-2 text-left font-semibold">Profilo</th>
                    <th className="w-32 px-3 py-2 text-left font-semibold">Stato oggi</th>
                    <th className="w-8 px-3 py-2" aria-hidden />
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {(persone.data ?? []).map((p, i) => (
                    <tr key={p.id} className="transition-colors hover:bg-primary/[0.03]">
                      <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground">
                        {String(i + 1).padStart(2, "0")}
                      </td>
                      <td className="px-3 py-2.5 font-mono text-[12px] text-muted-foreground">
                        {p.codice_dipendente}
                      </td>
                      <td className="px-3 py-2.5">
                        <Link
                          to={`/gestione-personale/persone/${p.id}`}
                          className="font-medium text-foreground hover:text-primary hover:underline"
                        >
                          <span className="uppercase">{p.cognome}</span>{" "}
                          <span className="text-foreground/80">{p.nome}</span>
                        </Link>
                      </td>
                      <td className="px-3 py-2.5 text-[12px] text-muted-foreground">
                        {p.profilo}
                      </td>
                      <td className="px-3 py-2.5">
                        <StatoCella tipo={p.indisponibilita_oggi} />
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <ArrowRight className="h-3 w-3 text-muted-foreground/40" aria-hidden />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function StatoCella({ tipo }: { tipo: string | null }) {
  if (tipo === null) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-emerald-700">
        <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" aria-hidden />
        in servizio
      </span>
    );
  }
  return (
    <Badge variant="outline" className="text-[10px]">
      {tipo}
    </Badge>
  );
}

interface KpiPillProps {
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  label: string;
  value: number;
  tone?: "neutral" | "success";
}

function KpiPill({ icon: Icon, label, value, tone = "neutral" }: KpiPillProps) {
  const cls =
    tone === "success"
      ? "border-emerald-300 bg-emerald-50 text-emerald-800"
      : "border-border bg-white text-foreground";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-semibold",
        cls,
      )}
    >
      <Icon className="h-3.5 w-3.5 opacity-60" aria-hidden />
      <span className="text-[10px] uppercase tracking-wider opacity-70">{label}</span>
      <span className="font-mono tabular-nums">{value}</span>
    </span>
  );
}
