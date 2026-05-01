import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertCircle, Search } from "lucide-react";

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
import { useGiriAzienda } from "@/hooks/useGiri";
import { ApiError } from "@/lib/api/client";
import type { GiroListItem } from "@/lib/api/giri";
import { formatDateIt, formatNumber } from "@/lib/format";

const PAGE_SIZE = 50;

/**
 * Sprint 7.3 MR 2 — Vista giri materiali per il PIANIFICATORE_PDC.
 *
 * Sola lettura: la modifica del giro è competenza del 1° ruolo.
 * Click su una riga apre il dettaglio Gantt esistente
 * (`/pianificatore-giro/giri/:id`) — l'editor sotto path PdC è MR 3.
 */
export function PianificatorePdcGiriRoute() {
  const [searchInput, setSearchInput] = useState("");
  const [statoFilter, setStatoFilter] = useState<string>("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const navigate = useNavigate();

  // Debounce manuale leggero: il submit del form fa il commit del search input
  // (no useEffect ricorrente per evitare query a ogni keystroke).

  const giriQuery = useGiriAzienda({
    q: debouncedQ.length > 0 ? debouncedQ : undefined,
    stato: statoFilter.length > 0 ? statoFilter : undefined,
    limit: PAGE_SIZE,
  });

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Vista giri materiali</h1>
        <p className="text-sm text-muted-foreground">
          Giri pubblicati dal Pianificatore Giro, in sola lettura. Click su una riga per il
          visualizzatore Gantt.
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
            Cerca per turno
          </label>
          <div className="flex items-center gap-2">
            <Input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="es. A001, FIO-12, …"
              aria-label="Cerca giro per numero turno"
            />
            <Button type="submit" variant="outline" size="sm" aria-label="Cerca">
              <Search className="h-4 w-4" aria-hidden />
            </Button>
          </div>
        </div>
        <div className="flex w-44 flex-col gap-1">
          <label
            className="text-xs font-medium uppercase tracking-wider text-muted-foreground"
            htmlFor="stato-filter"
          >
            Stato
          </label>
          <select
            id="stato-filter"
            value={statoFilter}
            onChange={(e) => setStatoFilter(e.target.value)}
            className="h-9 rounded-md border border-input bg-transparent px-2 text-sm"
          >
            <option value="">Tutti</option>
            <option value="bozza">Bozza</option>
            <option value="pubblicato">Pubblicato</option>
            <option value="archiviato">Archiviato</option>
          </select>
        </div>
      </form>

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
        <EmptyState />
      ) : giriQuery.data !== undefined ? (
        <GiriTable
          giri={giriQuery.data}
          onOpen={(id) => navigate(`/pianificatore-giro/giri/${id}`)}
        />
      ) : null}
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
          <TableHead className="w-24">Stato</TableHead>
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
              <StatoBadge stato={g.stato} />
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

function StatoBadge({ stato }: { stato: string }) {
  if (stato === "pubblicato") return <Badge variant="success">pubblicato</Badge>;
  if (stato === "bozza") return <Badge variant="muted">bozza</Badge>;
  if (stato === "archiviato") return <Badge variant="outline">archiviato</Badge>;
  return <Badge variant="outline">{stato}</Badge>;
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-md border border-dashed border-border bg-white py-16 text-center">
      <h2 className="text-base font-semibold">Nessun giro materiale</h2>
      <p className="max-w-md text-sm text-muted-foreground">
        I giri vengono creati dal Pianificatore Giro Materiale. Quando ce ne saranno, li
        vedrai qui in sola lettura.
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
