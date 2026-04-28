import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AlertCircle, Archive, ArrowLeft, ListOrdered, Plus, Send } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ProgrammaStatoBadge } from "@/components/domain/ProgrammaStatoBadge";
import { useArchiviaProgramma, useProgramma, usePubblicaProgramma } from "@/hooks/useProgrammi";
import { ApiError } from "@/lib/api/client";
import type { ProgrammaDettaglioRead } from "@/lib/api/programmi";
import { formatDateIt, formatNumber, formatPeriodo } from "@/lib/format";
import { RegolaCard } from "@/routes/pianificatore-giro/regola/RegolaCard";
import { RegolaEditor } from "@/routes/pianificatore-giro/regola/RegolaEditor";

export function ProgrammaDettaglioRoute() {
  const { programmaId: programmaIdParam } = useParams<{ programmaId: string }>();
  const programmaId = programmaIdParam !== undefined ? Number(programmaIdParam) : undefined;
  const navigate = useNavigate();

  const query = useProgramma(programmaId);
  const [editorOpen, setEditorOpen] = useState(false);

  if (programmaId === undefined || Number.isNaN(programmaId)) {
    return <ErrorBlock message="ID programma non valido nell'URL." />;
  }

  if (query.isLoading) {
    return (
      <div className="flex items-center justify-center rounded-md border border-border bg-white py-16">
        <Spinner label="Caricamento programma…" />
      </div>
    );
  }

  if (query.isError) {
    const msg =
      query.error instanceof ApiError ? query.error.message : (query.error as Error).message;
    return <ErrorBlock message={msg} onRetry={() => void query.refetch()} />;
  }

  if (query.data === undefined || query.data === null) {
    return <ErrorBlock message="Programma non trovato." />;
  }

  const programma = query.data;
  const editable = programma.stato === "bozza";

  return (
    <div className="flex flex-col gap-5">
      <Link
        to="/pianificatore-giro/programmi"
        className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-primary"
      >
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> Lista programmi
      </Link>

      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{programma.nome}</h1>
            <ProgrammaStatoBadge stato={programma.stato} />
          </div>
          <p className="text-sm text-muted-foreground">
            #{programma.id} · {formatPeriodo(programma.valido_da, programma.valido_a)}
            {programma.stagione !== null && ` · ${programma.stagione}`}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <ButtonAzioneStato programma={programma} onMutated={() => void query.refetch()} />
          <Button
            variant="outline"
            onClick={() => navigate(`/pianificatore-giro/programmi/${programma.id}/giri`)}
          >
            <ListOrdered className="mr-2 h-4 w-4" aria-hidden /> Giri generati
          </Button>
        </div>
      </header>

      <ConfigurazioneCard programma={programma} />

      <section className="flex flex-col gap-3">
        <div className="flex items-end justify-between">
          <div>
            <h2 className="text-lg font-semibold tracking-tight">Regole di assegnazione</h2>
            <p className="text-sm text-muted-foreground">
              Quali corse vengono coperte e con quale composizione di materiale.
              {!editable && " Modificabili solo in stato bozza."}
            </p>
          </div>
          {editable && (
            <Button onClick={() => setEditorOpen(true)}>
              <Plus className="mr-2 h-4 w-4" aria-hidden /> Nuova regola
            </Button>
          )}
        </div>

        {programma.regole.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 rounded-md border border-dashed border-border bg-white py-12 text-center">
            <p className="text-sm text-muted-foreground">
              Nessuna regola configurata. Almeno una regola è richiesta per pubblicare il programma.
            </p>
            {editable && (
              <Button onClick={() => setEditorOpen(true)}>
                <Plus className="mr-2 h-4 w-4" aria-hidden /> Aggiungi la prima regola
              </Button>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {programma.regole.map((r) => (
              <RegolaCard key={r.id} regola={r} programmaId={programma.id} editable={editable} />
            ))}
          </div>
        )}
      </section>

      <RegolaEditor programmaId={programma.id} open={editorOpen} onOpenChange={setEditorOpen} />
    </div>
  );
}

interface ButtonAzioneStatoProps {
  programma: ProgrammaDettaglioRead;
  onMutated: () => void;
}

function ButtonAzioneStato({ programma, onMutated }: ButtonAzioneStatoProps) {
  const pubblicaMutation = usePubblicaProgramma();
  const archiviaMutation = useArchiviaProgramma();
  const busy = pubblicaMutation.isPending || archiviaMutation.isPending;

  if (programma.stato === "bozza") {
    const canPublish = programma.regole.length > 0;
    return (
      <Button
        disabled={!canPublish || busy}
        onClick={() => {
          if (!window.confirm(`Pubblicare il programma "${programma.nome}"?`)) return;
          pubblicaMutation.mutate(programma.id, {
            onSuccess: onMutated,
            onError: (err) => {
              const msg = err instanceof ApiError ? err.message : err.message;
              window.alert(`Pubblicazione fallita: ${msg}`);
            },
          });
        }}
        title={canPublish ? "Pubblica" : "Aggiungi almeno una regola per pubblicare"}
      >
        <Send className="mr-2 h-4 w-4" aria-hidden /> Pubblica
      </Button>
    );
  }
  if (programma.stato === "attivo") {
    return (
      <Button
        variant="outline"
        disabled={busy}
        onClick={() => {
          if (!window.confirm(`Archiviare il programma "${programma.nome}"?`)) return;
          archiviaMutation.mutate(programma.id, {
            onSuccess: onMutated,
            onError: (err) => {
              const msg = err instanceof ApiError ? err.message : err.message;
              window.alert(`Archiviazione fallita: ${msg}`);
            },
          });
        }}
      >
        <Archive className="mr-2 h-4 w-4" aria-hidden /> Archivia
      </Button>
    );
  }
  return null;
}

function ConfigurazioneCard({ programma }: { programma: ProgrammaDettaglioRead }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Configurazione</CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm md:grid-cols-4">
        <Field label="Periodo" value={formatPeriodo(programma.valido_da, programma.valido_a)} />
        <Field label="Stagione" value={programma.stagione ?? "—"} />
        <Field label="N. giornate (safety)" value={programma.n_giornate_default.toString()} />
        <Field
          label="Tolleranza fascia oraria"
          value={`${programma.fascia_oraria_tolerance_min} min`}
        />
        <Field label="km/giorno max" value={formatNumber(programma.km_max_giornaliero)} />
        <Field label="km/ciclo max" value={formatNumber(programma.km_max_ciclo)} />
        <Field
          label="Sosta notturna extra"
          value={
            programma.stazioni_sosta_extra_json.length > 0
              ? programma.stazioni_sosta_extra_json.join(", ")
              : "—"
          }
        />
        <Field label="Aggiornato" value={formatDateIt(programma.updated_at)} />
      </CardContent>
    </Card>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <span className="text-foreground">{value}</span>
    </div>
  );
}

interface ErrorBlockProps {
  message: string;
  onRetry?: () => void;
}

function ErrorBlock({ message, onRetry }: ErrorBlockProps) {
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
