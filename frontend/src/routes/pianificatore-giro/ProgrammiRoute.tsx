import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Send, Archive, AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Label } from "@/components/ui/Label";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/Table";
import { ProgrammaStatoBadge } from "@/components/domain/ProgrammaStatoBadge";
import { useArchiviaProgramma, useProgrammi, usePubblicaProgramma } from "@/hooks/useProgrammi";
import { ApiError } from "@/lib/api/client";
import type {
  ListProgrammiParams,
  ProgrammaMaterialeRead,
  ProgrammaStato,
} from "@/lib/api/programmi";
import { formatDateIt, formatNumber, formatPeriodo } from "@/lib/format";
import { CreaProgrammaDialog } from "@/routes/pianificatore-giro/CreaProgrammaDialog";

const STATI: ReadonlyArray<{ value: "" | ProgrammaStato; label: string }> = [
  { value: "", label: "Tutti gli stati" },
  { value: "bozza", label: "Bozza" },
  { value: "attivo", label: "Attivo" },
  { value: "archiviato", label: "Archiviato" },
];

export function ProgrammiRoute() {
  const [statoFilter, setStatoFilter] = useState<"" | ProgrammaStato>("");
  const [dialogOpen, setDialogOpen] = useState(false);

  const params = useMemo<ListProgrammiParams>(() => {
    const p: ListProgrammiParams = {};
    if (statoFilter !== "") p.stato = statoFilter;
    return p;
  }, [statoFilter]);

  const programmiQuery = useProgrammi(params);
  const navigate = useNavigate();

  const hasFilters = statoFilter !== "";

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Programmi materiale</h1>
          <p className="text-sm text-muted-foreground">
            Ogni programma è <strong>un turno materiale unico</strong> per la sua finestra di
            validità: cresce aggiungendo regole/materiali. Da qui crei nuovi programmi (in bozza),
            entri nel dettaglio per configurare le regole, pubblichi o archivi.
          </p>
        </div>
        <Button onClick={() => setDialogOpen(true)}>
          <Plus className="mr-2 h-4 w-4" aria-hidden /> Nuovo programma
        </Button>
      </header>

      <section className="flex flex-wrap items-end gap-4 rounded-md border border-border bg-white p-3">
        <div className="flex flex-col gap-1">
          <Label htmlFor="filtro-stato">Stato</Label>
          <Select
            id="filtro-stato"
            value={statoFilter}
            onChange={(e) => setStatoFilter(e.target.value as "" | ProgrammaStato)}
          >
            {STATI.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </Select>
        </div>
        {hasFilters && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setStatoFilter("");
            }}
          >
            Azzera filtri
          </Button>
        )}
        <div className="ml-auto text-sm text-muted-foreground">
          {Array.isArray(programmiQuery.data) && (
            <span>
              {programmiQuery.data.length}{" "}
              {programmiQuery.data.length === 1 ? "programma" : "programmi"}
            </span>
          )}
        </div>
      </section>

      {programmiQuery.isLoading ? (
        <div className="flex items-center justify-center rounded-md border border-border bg-white py-16">
          <Spinner label="Caricamento programmi…" />
        </div>
      ) : programmiQuery.isError ? (
        <ErrorBanner error={programmiQuery.error} onRetry={() => void programmiQuery.refetch()} />
      ) : Array.isArray(programmiQuery.data) && programmiQuery.data.length === 0 ? (
        <EmptyState
          hasFilters={hasFilters}
          onCreate={() => setDialogOpen(true)}
          onClearFilters={() => {
            setStatoFilter("");
          }}
        />
      ) : Array.isArray(programmiQuery.data) ? (
        <ProgrammiTable
          programmi={programmiQuery.data}
          onOpen={(id) => navigate(`/pianificatore-giro/programmi/${id}`)}
        />
      ) : null}

      <CreaProgrammaDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onCreated={(p) => navigate(`/pianificatore-giro/programmi/${p.id}`)}
      />
    </div>
  );
}

interface ProgrammiTableProps {
  programmi: ProgrammaMaterialeRead[];
  onOpen: (id: number) => void;
}

function ProgrammiTable({ programmi, onOpen }: ProgrammiTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-12">ID</TableHead>
          <TableHead>Nome</TableHead>
          <TableHead className="w-44">Periodo</TableHead>
          <TableHead className="w-24">Stato</TableHead>
          <TableHead className="w-28 text-right">km/ciclo</TableHead>
          <TableHead className="w-28">Aggiornato</TableHead>
          <TableHead className="w-44">Azioni</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {programmi.map((p) => (
          <ProgrammaRow key={p.id} programma={p} onOpen={onOpen} />
        ))}
      </TableBody>
    </Table>
  );
}

interface ProgrammaRowProps {
  programma: ProgrammaMaterialeRead;
  onOpen: (id: number) => void;
}

function ProgrammaRow({ programma, onOpen }: ProgrammaRowProps) {
  const pubblicaMutation = usePubblicaProgramma();
  const archiviaMutation = useArchiviaProgramma();
  const busy = pubblicaMutation.isPending || archiviaMutation.isPending;

  const handlePubblica = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm(`Pubblicare il programma "${programma.nome}"?`)) return;
    pubblicaMutation.mutate(programma.id, {
      onError: (err) => {
        const msg = err instanceof ApiError ? err.message : err.message;
        window.alert(`Pubblicazione fallita: ${msg}`);
      },
    });
  };

  const handleArchivia = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm(`Archiviare il programma "${programma.nome}"?`)) return;
    archiviaMutation.mutate(programma.id, {
      onError: (err) => {
        const msg = err instanceof ApiError ? err.message : err.message;
        window.alert(`Archiviazione fallita: ${msg}`);
      },
    });
  };

  return (
    <TableRow
      className="cursor-pointer"
      onClick={() => onOpen(programma.id)}
      data-testid={`programma-row-${programma.id}`}
    >
      <TableCell className="font-mono text-xs text-muted-foreground">#{programma.id}</TableCell>
      <TableCell className="font-medium">{programma.nome}</TableCell>
      <TableCell className="whitespace-nowrap text-sm">
        {formatPeriodo(programma.valido_da, programma.valido_a)}
      </TableCell>
      <TableCell>
        <ProgrammaStatoBadge stato={programma.stato} />
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {formatNumber(programma.km_max_ciclo)}
      </TableCell>
      <TableCell className="text-sm text-muted-foreground">
        {formatDateIt(programma.updated_at)}
      </TableCell>
      <TableCell onClick={(e) => e.stopPropagation()}>
        <div className="flex gap-1">
          {programma.stato === "bozza" && (
            <Button
              size="sm"
              variant="primary"
              onClick={handlePubblica}
              disabled={busy}
              aria-label={`Pubblica ${programma.nome}`}
            >
              <Send className="mr-1.5 h-3.5 w-3.5" aria-hidden /> Pubblica
            </Button>
          )}
          {programma.stato === "attivo" && (
            <Button
              size="sm"
              variant="outline"
              onClick={handleArchivia}
              disabled={busy}
              aria-label={`Archivia ${programma.nome}`}
            >
              <Archive className="mr-1.5 h-3.5 w-3.5" aria-hidden /> Archivia
            </Button>
          )}
        </div>
      </TableCell>
    </TableRow>
  );
}

interface EmptyStateProps {
  hasFilters: boolean;
  onCreate: () => void;
  onClearFilters: () => void;
}

function EmptyState({ hasFilters, onCreate, onClearFilters }: EmptyStateProps) {
  if (hasFilters) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-md border border-dashed border-border bg-white py-16 text-center">
        <p className="text-sm text-muted-foreground">
          Nessun programma corrisponde ai filtri attuali.
        </p>
        <Button variant="ghost" size="sm" onClick={onClearFilters}>
          Azzera filtri
        </Button>
      </div>
    );
  }
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-md border border-dashed border-border bg-white py-16 text-center">
      <h2 className="text-base font-semibold">Nessun programma materiale</h2>
      <p className="max-w-md text-sm text-muted-foreground">
        Inizia creando il primo programma materiale della tua azienda. Ogni programma è un{" "}
        <strong>turno materiale unico</strong>: definisce un periodo di validità + le regole di
        assegnazione tra corse e materiali, e cresce ogni volta che aggiungi un materiale.
      </p>
      <Button onClick={onCreate}>
        <Plus className="mr-2 h-4 w-4" aria-hidden /> Crea il primo programma
      </Button>
    </div>
  );
}

function ErrorBanner({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const msg =
    error instanceof ApiError
      ? error.message
      : error instanceof Error
        ? error.message
        : "Errore sconosciuto";
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-4"
    >
      <AlertCircle className="mt-0.5 h-5 w-5 text-destructive" aria-hidden />
      <div className="flex flex-1 flex-col gap-2">
        <p className="text-sm font-medium text-destructive">Impossibile caricare i programmi.</p>
        <p className="text-sm text-muted-foreground">{msg}</p>
        <Button variant="outline" size="sm" onClick={onRetry} className="self-start">
          Riprova
        </Button>
      </div>
    </div>
  );
}
