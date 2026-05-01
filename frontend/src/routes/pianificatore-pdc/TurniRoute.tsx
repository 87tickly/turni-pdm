import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertCircle, AlertTriangle, Search } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Spinner } from "@/components/ui/Spinner";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/Table";
import { useTurniPdcAzienda } from "@/hooks/useTurniPdc";
import { ApiError } from "@/lib/api/client";
import type { TurnoPdcListItem } from "@/lib/api/turniPdc";
import { formatDateIt, formatNumber } from "@/lib/format";

const PAGE_SIZE = 50;

/**
 * Sprint 7.3 MR 2 — Lista turni PdC cross-giro per il PIANIFICATORE_PDC.
 *
 * Tabella con i turni dell'azienda, filtri (ricerca codice, impianto,
 * stato). Click su una riga apre il dettaglio Gantt
 * (`/pianificatore-giro/turni-pdc/:id` per ora — la rotta sotto path PdC
 * è MR 3).
 */
export function PianificatorePdcTurniRoute() {
  const [searchInput, setSearchInput] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [impianto, setImpianto] = useState("");
  const [stato, setStato] = useState("");
  const navigate = useNavigate();

  const turniQuery = useTurniPdcAzienda({
    q: debouncedQ.length > 0 ? debouncedQ : undefined,
    impianto: impianto.length > 0 ? impianto : undefined,
    stato: stato.length > 0 ? stato : undefined,
    limit: PAGE_SIZE,
  });

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Lista turni PdC</h1>
        <p className="text-sm text-muted-foreground">
          Turni del personale di macchina dell'azienda. Filtra per impianto, stato e codice.
          Click su una riga per il visualizzatore Gantt.
        </p>
      </header>

      <form
        className="flex flex-wrap items-end gap-3 rounded-md border border-border bg-white p-3"
        onSubmit={(e) => {
          e.preventDefault();
          setDebouncedQ(searchInput.trim());
        }}
      >
        <div className="flex flex-1 flex-col gap-1">
          <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Cerca per codice
          </label>
          <div className="flex items-center gap-2">
            <Input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="es. T-G-TCV-001, …"
              aria-label="Cerca turno per codice"
            />
            <Button type="submit" variant="outline" size="sm" aria-label="Cerca">
              <Search className="h-4 w-4" aria-hidden />
            </Button>
          </div>
        </div>
        <div className="flex w-44 flex-col gap-1">
          <label
            className="text-xs font-medium uppercase tracking-wider text-muted-foreground"
            htmlFor="impianto-filter"
          >
            Impianto
          </label>
          <Input
            id="impianto-filter"
            value={impianto}
            onChange={(e) => setImpianto(e.target.value)}
            placeholder="MILANO_GA, BRESCIA, …"
            aria-label="Filtra per impianto"
          />
        </div>
        <div className="flex w-40 flex-col gap-1">
          <label
            className="text-xs font-medium uppercase tracking-wider text-muted-foreground"
            htmlFor="stato-filter"
          >
            Stato
          </label>
          <select
            id="stato-filter"
            value={stato}
            onChange={(e) => setStato(e.target.value)}
            className="h-9 rounded-md border border-input bg-transparent px-2 text-sm"
          >
            <option value="">Tutti</option>
            <option value="bozza">Bozza</option>
            <option value="pubblicato">Pubblicato</option>
            <option value="archiviato">Archiviato</option>
          </select>
        </div>
      </form>

      {turniQuery.isLoading ? (
        <div className="flex items-center justify-center rounded-md border border-border bg-white py-16">
          <Spinner label="Caricamento turni…" />
        </div>
      ) : turniQuery.isError ? (
        <ErrorBlock
          message={
            turniQuery.error instanceof ApiError
              ? turniQuery.error.message
              : (turniQuery.error as Error).message
          }
          onRetry={() => void turniQuery.refetch()}
        />
      ) : turniQuery.data !== undefined && turniQuery.data.length === 0 ? (
        <EmptyState />
      ) : turniQuery.data !== undefined ? (
        <TurniTable
          turni={turniQuery.data}
          onOpen={(id) => navigate(`/pianificatore-pdc/turni/${id}`)}
        />
      ) : null}
    </div>
  );
}

function TurniTable({
  turni,
  onOpen,
}: {
  turni: TurnoPdcListItem[];
  onOpen: (id: number) => void;
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-12">ID</TableHead>
          <TableHead>Codice</TableHead>
          <TableHead className="w-28">Impianto</TableHead>
          <TableHead className="w-24">Profilo</TableHead>
          <TableHead className="w-20 text-right">Giornate</TableHead>
          <TableHead className="w-28 text-right">Prest. (min)</TableHead>
          <TableHead className="w-28 text-right">Cond. (min)</TableHead>
          <TableHead className="w-20 text-right">Violaz.</TableHead>
          <TableHead className="w-24">Stato</TableHead>
          <TableHead className="w-28">Valido da</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {turni.map((t) => (
          <TableRow
            key={t.id}
            className="cursor-pointer"
            onClick={() => onOpen(t.id)}
            data-testid={`turno-row-${t.id}`}
          >
            <TableCell className="font-mono text-xs text-muted-foreground">#{t.id}</TableCell>
            <TableCell className="font-medium">
              <span className="flex items-center gap-1.5">
                {t.codice}
                {t.is_ramo_split ? (
                  <Badge variant="outline" className="text-xs">
                    Ramo {t.split_ramo}/{t.split_totale_rami}
                  </Badge>
                ) : null}
              </span>
            </TableCell>
            <TableCell className="text-sm">{t.impianto}</TableCell>
            <TableCell className="text-sm text-muted-foreground">{t.profilo}</TableCell>
            <TableCell className="text-right tabular-nums">{t.n_giornate}</TableCell>
            <TableCell className="text-right tabular-nums">
              {formatNumber(t.prestazione_totale_min)}
            </TableCell>
            <TableCell className="text-right tabular-nums">
              {formatNumber(t.condotta_totale_min)}
            </TableCell>
            <TableCell className="text-right tabular-nums">
              {t.n_violazioni > 0 ? (
                <span className="inline-flex items-center gap-1 text-amber-700">
                  <AlertTriangle className="h-3 w-3" aria-hidden />
                  {t.n_violazioni}
                </span>
              ) : (
                <span className="text-muted-foreground">0</span>
              )}
            </TableCell>
            <TableCell>
              <StatoBadge stato={t.stato} />
            </TableCell>
            <TableCell className="text-sm text-muted-foreground">
              {formatDateIt(t.valido_da)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function StatoBadge({ stato }: { stato: string }) {
  if (stato === "pubblicato") return <Badge variant="success">pubblicato</Badge>;
  if (stato === "bozza") return <Badge variant="muted">bozza</Badge>;
  if (stato === "archiviato") return <Badge variant="outline">archiviato</Badge>;
  return <Badge variant="outline">{stato}</Badge>;
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-md border border-dashed border-border bg-white py-16 text-center">
      <h2 className="text-base font-semibold">Nessun turno PdC</h2>
      <p className="max-w-md text-sm text-muted-foreground">
        I turni si generano dal dettaglio di un giro materiale (bottone "Genera turni
        PdC"). Quando ce ne saranno, li vedrai qui con i filtri per impianto/stato.
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
