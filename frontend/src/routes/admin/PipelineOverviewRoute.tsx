/**
 * Dashboard pipeline trasversale (Sprint 8.0 MR 6, entry 171).
 *
 * Vista admin-only: tabella di tutti i programmi dell'azienda con
 * stato pipeline + tempo in stato + ruolo responsabile dello step
 * successivo. Evidenza dei programmi "bloccati" (> 7 giorni in
 * stato non terminale).
 */

import { useMemo } from "react";
import { Navigate } from "react-router-dom";
import { AlertTriangle, ShieldCheck } from "lucide-react";

import { ApiError } from "@/lib/api/client";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { useAuth } from "@/lib/auth/AuthContext";
import { useAdminPipelineOverview } from "@/hooks/useAdminPipeline";
import { cn } from "@/lib/utils";

export function AdminPipelineOverviewRoute() {
  const { user } = useAuth();
  const overview = useAdminPipelineOverview();

  // Difensivo lato client (server già protegge con require_admin):
  // se l'utente non è admin, redirect a /forbidden.
  if (user !== null && !user.is_admin) {
    return <Navigate to="/forbidden" replace />;
  }

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold tracking-tight text-primary">
          Pipeline trasversale
        </h1>
        <p className="text-sm text-muted-foreground">
          Vista admin: tutti i programmi dell'azienda con lo stato pipeline,
          il tempo passato in quello stato e il ruolo responsabile del
          prossimo step.
        </p>
      </header>

      {overview.isLoading ? (
        <Card className="flex items-center justify-center p-8">
          <Spinner label="Caricamento overview…" />
        </Card>
      ) : overview.isError ? (
        <Card className="border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
          {overview.error instanceof ApiError
            ? overview.error.message
            : (overview.error as Error).message}
        </Card>
      ) : (
        <PipelineOverviewBody data={overview.data!} />
      )}
    </div>
  );
}

function PipelineOverviewBody({
  data,
}: {
  data: import("@/lib/api/adminPipeline").PipelineOverviewResponse;
}) {
  const totaleProgrammi = data.programmi.length;
  const sortedRows = useMemo(
    () =>
      [...data.programmi].sort((a, b) => {
        if (a.is_bloccato !== b.is_bloccato) return a.is_bloccato ? -1 : 1;
        return b.giorni_in_stato - a.giorni_in_stato;
      }),
    [data.programmi],
  );

  return (
    <>
      {/* KPI riga */}
      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <KpiCell label="Programmi totali" value={totaleProgrammi} />
        <KpiCell
          label="Bloccati > 7gg"
          value={data.n_bloccati}
          tone={data.n_bloccati > 0 ? "danger" : "ok"}
          icon={AlertTriangle}
        />
        <KpiCell
          label="In Vista pubblicata"
          value={data.counters_per_stato_pdc["VISTA_PUBBLICATA"] ?? 0}
          tone="ok"
          icon={ShieldCheck}
        />
        <KpiCell
          label="Matricole assegnate"
          value={data.counters_per_stato_manutenzione["MATRICOLE_ASSEGNATE"] ?? 0}
          tone="ok"
        />
      </section>

      {/* Tabella programmi */}
      <Card className="overflow-hidden p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/40 text-left text-[10px] uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-3 py-2">Programma</th>
                <th className="px-3 py-2">Stato PdC</th>
                <th className="px-3 py-2">Stato Manutenzione</th>
                <th className="px-3 py-2">Prossimo PdC</th>
                <th className="px-3 py-2">Prossimo Man.</th>
                <th className="px-3 py-2 text-right">Giorni</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {sortedRows.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-3 py-8 text-center text-muted-foreground">
                    Nessun programma in pipeline.
                  </td>
                </tr>
              ) : (
                sortedRows.map((p) => (
                  <tr
                    key={p.programma_id}
                    className={cn(
                      "border-b border-border last:border-b-0 hover:bg-muted/20",
                      p.is_bloccato && "bg-amber-50",
                    )}
                  >
                    <td className="px-3 py-2 font-medium">
                      <span className="font-mono text-xs text-muted-foreground">
                        #{p.programma_id}
                      </span>
                      <span className="ml-2">{p.nome}</span>
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {p.stato_pipeline_pdc}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {p.stato_manutenzione}
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">
                      {p.pdc_responsabile_prossimo}
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">
                      {p.manutenzione_responsabile_prossimo}
                    </td>
                    <td
                      className={cn(
                        "px-3 py-2 text-right tabular-nums",
                        p.is_bloccato && "font-semibold text-amber-700",
                      )}
                    >
                      {p.giorni_in_stato}
                    </td>
                    <td className="px-3 py-2">
                      {p.is_bloccato ? (
                        <span
                          className="inline-flex items-center gap-1 rounded-md bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-800"
                          title="Bloccato in stato > 7 giorni"
                        >
                          <AlertTriangle className="h-3 w-3" aria-hidden /> bloccato
                        </span>
                      ) : null}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

function KpiCell({
  label,
  value,
  tone = "neutral",
  icon: Icon,
}: {
  label: string;
  value: number;
  tone?: "neutral" | "ok" | "danger";
  icon?: React.ComponentType<React.SVGProps<SVGSVGElement>>;
}) {
  const toneClass =
    tone === "danger"
      ? "border-amber-300 bg-amber-50 text-amber-800"
      : tone === "ok"
        ? "border-emerald-300 bg-emerald-50 text-emerald-800"
        : "border-border bg-muted/30 text-foreground";
  return (
    <Card className={cn("p-3", toneClass)}>
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-wide opacity-70">
        {Icon !== undefined ? <Icon className="h-3 w-3" aria-hidden /> : null}
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
    </Card>
  );
}
