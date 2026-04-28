import { Link, useNavigate, useParams } from "react-router-dom";
import { AlertCircle, ArrowLeft } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/Table";
import { useGiriProgramma } from "@/hooks/useGiri";
import { useProgramma } from "@/hooks/useProgrammi";
import { ApiError } from "@/lib/api/client";
import type { GiroListItem } from "@/lib/api/giri";
import { formatDateIt, formatNumber } from "@/lib/format";

export function ProgrammaGiriRoute() {
  const { programmaId: programmaIdParam } = useParams<{ programmaId: string }>();
  const programmaId = programmaIdParam !== undefined ? Number(programmaIdParam) : undefined;
  const navigate = useNavigate();

  const programmaQuery = useProgramma(programmaId);
  const giriQuery = useGiriProgramma(programmaId);

  if (programmaId === undefined || Number.isNaN(programmaId)) {
    return <ErrorBlock message="ID programma non valido nell'URL." />;
  }

  return (
    <div className="flex flex-col gap-5">
      <Link
        to={`/pianificatore-giro/programmi/${programmaId}`}
        className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-primary"
      >
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> Dettaglio programma
      </Link>

      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">
          Giri generati
          {programmaQuery.data !== undefined && (
            <span className="ml-2 text-base font-normal text-muted-foreground">
              · {programmaQuery.data.nome}
            </span>
          )}
        </h1>
        <p className="text-sm text-muted-foreground">
          Convogli persistiti dall'algoritmo. Click su una riga per il visualizzatore Gantt (Sub
          6.5).
        </p>
      </header>

      {giriQuery.isLoading ? (
        <div className="flex items-center justify-center rounded-md border border-border bg-white py-16">
          <Spinner label="Caricamento giri…" />
        </div>
      ) : giriQuery.isError ? (
        <ErrorBlock
          message={
            giriQuery.error instanceof ApiError
              ? giriQuery.error.message
              : (giriQuery.error as Error).message
          }
          onRetry={() => void giriQuery.refetch()}
        />
      ) : giriQuery.data !== undefined && giriQuery.data.length === 0 ? (
        <EmptyState programmaId={programmaId} />
      ) : giriQuery.data !== undefined ? (
        <>
          <StatsBar giri={giriQuery.data} />
          <GiriTable
            giri={giriQuery.data}
            onOpen={(id) => navigate(`/pianificatore-giro/giri/${id}`)}
          />
        </>
      ) : null}
    </div>
  );
}

function StatsBar({ giri }: { giri: GiroListItem[] }) {
  const totaleKmGiornaliera = giri.reduce((s, g) => s + (g.km_media_giornaliera ?? 0), 0);
  const totaleKmAnnua = giri.reduce((s, g) => s + (g.km_media_annua ?? 0), 0);
  const chiusiNaturalmente = giri.filter(
    (g) => g.motivo_chiusura === "naturale" || g.motivo_chiusura === null,
  ).length;
  return (
    <div className="grid grid-cols-2 gap-3 rounded-md border border-border bg-white p-4 md:grid-cols-4">
      <Stat label="Giri totali" value={formatNumber(giri.length)} />
      <Stat
        label="Chiusi naturalmente"
        value={`${formatNumber(chiusiNaturalmente)} / ${formatNumber(giri.length)}`}
      />
      <Stat label="km/giorno cumulati" value={formatNumber(Math.round(totaleKmGiornaliera))} />
      <Stat label="km/anno cumulati" value={formatNumber(Math.round(totaleKmAnnua))} />
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <span className="text-lg font-semibold tabular-nums text-foreground">{value}</span>
    </div>
  );
}

function GiriTable({ giri, onOpen }: { giri: GiroListItem[]; onOpen: (id: number) => void }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-12">ID</TableHead>
          <TableHead className="w-28">Turno</TableHead>
          <TableHead>Tipo materiale</TableHead>
          <TableHead className="w-20 text-right">Giornate</TableHead>
          <TableHead className="w-28 text-right">km/giorno</TableHead>
          <TableHead className="w-28 text-right">km/anno</TableHead>
          <TableHead className="w-32">Chiusura</TableHead>
          <TableHead className="w-28">Creato</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {giri.map((g) => (
          <TableRow
            key={g.id}
            className="cursor-pointer"
            onClick={() => onOpen(g.id)}
            data-testid={`giro-row-${g.id}`}
          >
            <TableCell className="font-mono text-xs text-muted-foreground">#{g.id}</TableCell>
            <TableCell className="font-medium">{g.numero_turno}</TableCell>
            <TableCell className="text-sm">{g.tipo_materiale}</TableCell>
            <TableCell className="text-right tabular-nums">{g.numero_giornate}</TableCell>
            <TableCell className="text-right tabular-nums">
              {g.km_media_giornaliera !== null
                ? formatNumber(Math.round(g.km_media_giornaliera))
                : "—"}
            </TableCell>
            <TableCell className="text-right tabular-nums">
              {g.km_media_annua !== null ? formatNumber(Math.round(g.km_media_annua)) : "—"}
            </TableCell>
            <TableCell>
              <MotivoChiusuraBadge motivo={g.motivo_chiusura} chiuso={g.chiuso} />
            </TableCell>
            <TableCell className="text-sm text-muted-foreground">
              {formatDateIt(g.created_at)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function MotivoChiusuraBadge({ motivo, chiuso }: { motivo: string | null; chiuso: boolean }) {
  if (motivo === "naturale") return <Badge variant="success">naturale</Badge>;
  if (!chiuso) return <Badge variant="warning">non chiuso</Badge>;
  if (motivo !== null) return <Badge variant="outline">{motivo}</Badge>;
  return <Badge variant="muted">—</Badge>;
}

function EmptyState({ programmaId }: { programmaId: number }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-md border border-dashed border-border bg-white py-16 text-center">
      <h2 className="text-base font-semibold">Nessun giro generato</h2>
      <p className="max-w-md text-sm text-muted-foreground">
        Per generare i giri torna al dettaglio programma e clicca <strong>"Genera giri"</strong>. Il
        programma deve essere in stato <em>attivo</em> e avere almeno una regola di assegnazione.
      </p>
      <Link
        to={`/pianificatore-giro/programmi/${programmaId}`}
        className="text-sm font-medium text-primary hover:underline"
      >
        Vai al dettaglio programma →
      </Link>
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
