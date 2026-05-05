/**
 * Dashboard Manutenzione (Sprint 8.0 MR 4, entry 169).
 *
 * Layout minimo per il ruolo ``MANUTENZIONE``:
 *
 * 1. Widget "Pipeline programmi" — programmi visibili al ruolo
 *    (filter list-route MR 0: ``stato_pipeline_pdc >= MATERIALE_CONFERMATO``).
 *    Per ogni programma, mostra lo stato del ramo Manutenzione
 *    (`IN_ATTESA`, `IN_LAVORAZIONE`, `MATRICOLE_ASSEGNATE`).
 * 2. Bottone "Conferma matricole" su programmi in `IN_LAVORAZIONE`
 *    (chiama `POST /api/programmi/{id}/conferma-manutenzione`).
 *
 * Scope rinviato a MR 4.bis: l'algoritmo di assegnazione matricole
 * fisiche `{TIPO}-{NNN}` ai giri (vedi memoria utente
 * `project_matricole_materiali`). Per ora lo schema esiste, ma
 * l'UI di gestione materiali non è ancora cablata.
 */

import { useMemo } from "react";
import { CheckCircle2, Lock, Wrench } from "lucide-react";

import { ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { useAuth } from "@/lib/auth/AuthContext";
import { useConfermaManutenzione, useProgrammi } from "@/hooks/useProgrammi";
import type {
  ProgrammaMaterialeRead,
  StatoManutenzione,
} from "@/lib/api/programmi";
import { cn } from "@/lib/utils";

const STATO_MANUTENZIONE_LABEL: Record<StatoManutenzione, string> = {
  IN_ATTESA: "In attesa di conferma materiale",
  IN_LAVORAZIONE: "In lavorazione — assegna le matricole",
  MATRICOLE_ASSEGNATE: "Matricole assegnate",
};

export function ManutenzioneDashboardRoute() {
  const { user } = useAuth();
  const programmiQuery = useProgrammi();

  const programmi = useMemo(() => {
    const data = programmiQuery.data;
    return Array.isArray(data) ? data : [];
  }, [programmiQuery.data]);

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold tracking-tight text-primary">
          Dashboard Manutenzione
        </h1>
        <p className="text-sm text-muted-foreground">
          Benvenuto{user !== null ? `, ${user.username}` : ""}. Qui assegni le
          matricole materiali ai programmi confermati dal Pianificatore Giro
          Materiale. Il ramo Manutenzione è parallelo e indipendente dal
          ramo PdC.
        </p>
      </header>

      <PipelineSection
        programmi={programmi}
        isLoading={programmiQuery.isLoading}
        isError={programmiQuery.isError}
      />
    </div>
  );
}

function PipelineSection({
  programmi,
  isLoading,
  isError,
}: {
  programmi: ProgrammaMaterialeRead[];
  isLoading: boolean;
  isError: boolean;
}) {
  if (isLoading) {
    return (
      <Card className="flex items-center justify-center p-8">
        <Spinner label="Caricamento programmi…" />
      </Card>
    );
  }
  if (isError) {
    return (
      <Card className="border-amber-300 bg-amber-50 p-4 text-sm text-amber-800">
        Impossibile caricare i programmi. Riprova più tardi.
      </Card>
    );
  }
  if (programmi.length === 0) {
    return (
      <Card className="border-border bg-muted/30 p-6 text-center text-sm text-muted-foreground">
        <Wrench className="mx-auto mb-2 h-6 w-6 text-muted-foreground/50" aria-hidden />
        Nessun programma in pipeline. La Manutenzione si attiva quando il
        Pianificatore Giro Materiale conferma un programma.
      </Card>
    );
  }

  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-baseline gap-2">
        <Wrench className="h-4 w-4 text-primary" aria-hidden />
        <h2 className="text-sm font-semibold uppercase tracking-wide text-foreground">
          Pipeline programmi · ramo Manutenzione
        </h2>
        <span className="text-xs text-muted-foreground">
          {programmi.length} programmi
        </span>
      </div>
      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {programmi.map((p) => (
          <ManutenzioneProgrammaCard key={p.id} programma={p} />
        ))}
      </div>
    </section>
  );
}

function ManutenzioneProgrammaCard({
  programma,
}: {
  programma: ProgrammaMaterialeRead;
}) {
  const stato = programma.stato_manutenzione;
  const confermaMutation = useConfermaManutenzione();
  const isInLavorazione = stato === "IN_LAVORAZIONE";
  const isAssegnate = stato === "MATRICOLE_ASSEGNATE";

  return (
    <Card
      className={cn(
        "flex items-center justify-between gap-3 p-3",
        isInLavorazione && "border-blue-300 bg-blue-50",
        isAssegnate && "border-emerald-300 bg-emerald-50",
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold truncate text-foreground">
            {programma.nome}
          </span>
          {isAssegnate ? (
            <CheckCircle2
              className="h-3.5 w-3.5 shrink-0 text-emerald-600"
              aria-hidden
            />
          ) : null}
          {!isInLavorazione && !isAssegnate ? (
            <Lock className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
          ) : null}
        </div>
        <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
          {STATO_MANUTENZIONE_LABEL[stato]}
        </div>
      </div>
      {isInLavorazione ? (
        <Button
          variant="primary"
          size="sm"
          disabled={confermaMutation.isPending}
          onClick={() => {
            if (
              !window.confirm(
                `Confermare l'assegnazione delle matricole del programma "${programma.nome}"?\n` +
                  "Il ramo Manutenzione passerà allo stato MATRICOLE_ASSEGNATE.",
              )
            ) {
              return;
            }
            confermaMutation.mutate(programma.id, {
              onError: (err) => {
                const msg = err instanceof ApiError ? err.message : err.message;
                window.alert(`Conferma fallita: ${msg}`);
              },
            });
          }}
        >
          <CheckCircle2 className="mr-2 h-4 w-4" aria-hidden /> Conferma matricole
        </Button>
      ) : null}
    </Card>
  );
}
