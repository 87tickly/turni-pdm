import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  Download,
  RotateCcw,
} from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { useTurniPdcAzienda } from "@/hooks/useTurniPdc";
import { ApiError } from "@/lib/api/client";
import type { TurnoPdcListItem } from "@/lib/api/turniPdc";
import { formatDateIt, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 50;

/**
 * Sprint 7.10 MR 7.10.4 — Lista turni PdC per il PIANIFICATORE_PDC.
 *
 * Variante v1 dal pacchetto Anthropic Design Handoff
 * (`arturo/08-lista-turni-pdc.html`): "Filtri inline nell'header tabella".
 * Stesso pattern di Vista giri (MR 7.10.3): la riga 2 di `<thead>` è
 * una toolbar di input/select per ogni colonna filtrabile, eliminando
 * la form-card sopra che occupava verticale.
 *
 * Filtri implementati: codice (q, via form submit), impianto (onChange
 * diretto), stato (onChange diretto). KPI banda mini in cima
 * (pubblicati/bozza/archiviati + totali). Empty/error preservati.
 *
 * Click su una riga apre il visualizzatore Gantt turno PdC sotto path
 * `/pianificatore-pdc/turni/:id` (MR 7.10.6).
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

  const data = turniQuery.data;
  const total = data?.length ?? 0;
  const filtersActive =
    (debouncedQ.length > 0 ? 1 : 0) +
    (impianto.length > 0 ? 1 : 0) +
    (stato.length > 0 ? 1 : 0);

  const kpis = useMemo(() => {
    if (data === undefined) {
      return { pubblicato: 0, bozza: 0, archiviato: 0, conViolazioni: 0 };
    }
    let p = 0,
      b = 0,
      a = 0,
      v = 0;
    for (const t of data) {
      if (t.stato === "pubblicato") p++;
      else if (t.stato === "bozza") b++;
      else if (t.stato === "archiviato") a++;
      if (t.n_violazioni > 0) v++;
    }
    return { pubblicato: p, bozza: b, archiviato: a, conViolazioni: v };
  }, [data]);

  const impiantiUnique = useMemo(() => {
    if (data === undefined) return 0;
    const s = new Set<string>();
    for (const t of data) s.add(t.impianto);
    return s.size;
  }, [data]);

  function resetFilters() {
    setSearchInput("");
    setDebouncedQ("");
    setImpianto("");
    setStato("");
  }

  return (
    <div className="flex flex-col gap-5">
      {/* breadcrumb */}
      <div className="text-xs text-muted-foreground">
        Home <span className="mx-1 text-muted-foreground/40">/</span> Lista turni
      </div>

      {/* HEADER pagina con KPI mini banda */}
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-primary">
            Lista turni PdC
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Turni del personale di macchina dell'azienda. Filtra per impianto,
            stato e codice. Click su una riga per il visualizzatore Gantt.
          </p>
        </div>
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <KpiPill color="emerald" value={kpis.pubblicato} label="pubblicati" />
          <KpiPill color="muted-strong" value={kpis.bozza} label="bozza" />
          <KpiPill color="muted-soft" value={kpis.archiviato} label="archiviati" />
          {kpis.conViolazioni > 0 && (
            <KpiPill color="amber" value={kpis.conViolazioni} label="con violazioni" />
          )}
          <span className="text-muted-foreground/40">|</span>
          <span>
            <span className="font-mono tabular-nums text-foreground">{total}</span>{" "}
            turni · <span className="font-mono tabular-nums text-foreground">{impiantiUnique}</span>{" "}
            impianto/i
          </span>
        </div>
      </header>

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
      ) : data !== undefined && data.length === 0 && filtersActive === 0 ? (
        <EmptyState />
      ) : data !== undefined ? (
        <section className="overflow-hidden rounded-lg border border-border bg-white">
          <div className="flex items-center justify-between border-b border-border bg-muted/40 px-4 py-2.5">
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span>
                Mostro{" "}
                <span className="font-mono tabular-nums text-foreground">{total}</span>{" "}
                turni
              </span>
              {filtersActive > 0 && (
                <>
                  <span className="text-muted-foreground/40">·</span>
                  <span className="inline-flex items-center gap-1.5 text-primary">
                    <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden />
                    {filtersActive} filtr{filtersActive === 1 ? "o" : "i"} attiv
                    {filtersActive === 1 ? "o" : "i"}
                  </span>
                </>
              )}
            </div>
            <div className="flex items-center gap-2">
              {filtersActive > 0 && (
                <button
                  type="button"
                  onClick={resetFilters}
                  className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                >
                  <RotateCcw className="h-3 w-3" aria-hidden />
                  Reset filtri
                </button>
              )}
              <button
                type="button"
                disabled
                title="Esporta — disponibile da Sprint 7.11"
                className="inline-flex cursor-not-allowed items-center gap-1.5 rounded-md border border-border bg-white px-2.5 py-1.5 text-xs text-muted-foreground opacity-60"
              >
                <Download className="h-3.5 w-3.5" aria-hidden />
                Esporta
              </button>
            </div>
          </div>

          <div className="overflow-x-auto">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                setDebouncedQ(searchInput.trim());
              }}
            >
              <table className="w-full text-sm">
                <thead>
                  {/* Riga 1 — etichette colonna */}
                  <tr className="border-b border-border bg-muted/50 text-[10px] uppercase tracking-wider text-muted-foreground">
                    <th className="w-16 px-3 py-2 text-left font-semibold">ID</th>
                    <th className="px-3 py-2 text-left font-semibold">Codice</th>
                    <th className="w-32 px-3 py-2 text-left font-semibold">Impianto</th>
                    <th className="w-24 px-3 py-2 text-left font-semibold">Profilo</th>
                    <th className="w-20 px-3 py-2 text-right font-semibold">Giorn.</th>
                    <th className="w-24 px-3 py-2 text-right font-semibold">Prest.</th>
                    <th className="w-24 px-3 py-2 text-right font-semibold">Cond.</th>
                    <th className="w-20 px-3 py-2 text-right font-semibold">Violaz.</th>
                    <th className="w-28 px-3 py-2 text-left font-semibold">Stato</th>
                    <th className="w-28 px-3 py-2 text-left font-semibold">Valido da</th>
                    <th className="w-8 px-3 py-2" aria-hidden />
                  </tr>
                  {/* Riga 2 — filtri inline */}
                  <tr className="border-b border-border bg-primary/[0.03]">
                    <th className="px-2 py-1.5">
                      <FilterCellPlaceholder placeholder="#" />
                    </th>
                    <th className="px-2 py-1.5">
                      <input
                        className={FILTER_INPUT_CLASS}
                        placeholder="es. T-G-TCV-001, …"
                        value={searchInput}
                        onChange={(e) => setSearchInput(e.target.value)}
                        aria-label="Cerca turno per codice"
                      />
                    </th>
                    <th className="px-2 py-1.5">
                      <input
                        className={FILTER_INPUT_CLASS}
                        placeholder="MILANO_GA, BRESCIA, …"
                        value={impianto}
                        onChange={(e) => setImpianto(e.target.value)}
                        aria-label="Filtra per impianto"
                      />
                    </th>
                    <th className="px-2 py-1.5" />
                    <th className="px-2 py-1.5" />
                    <th className="px-2 py-1.5" />
                    <th className="px-2 py-1.5" />
                    <th className="px-2 py-1.5" />
                    <th className="px-2 py-1.5">
                      <select
                        className={FILTER_INPUT_CLASS}
                        value={stato}
                        onChange={(e) => setStato(e.target.value)}
                        aria-label="Filtra per stato"
                      >
                        <option value="">Tutti</option>
                        <option value="bozza">Bozza</option>
                        <option value="pubblicato">Pubblicato</option>
                        <option value="archiviato">Archiviato</option>
                      </select>
                    </th>
                    <th className="px-2 py-1.5">
                      <FilterCellPlaceholder placeholder="Qualsiasi" />
                    </th>
                    <th className="px-2 py-1.5" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {data.length === 0 ? (
                    <tr>
                      <td
                        colSpan={11}
                        className="px-3 py-8 text-center text-sm text-muted-foreground"
                      >
                        Nessun turno corrisponde ai filtri attivi.
                      </td>
                    </tr>
                  ) : (
                    data.map((t) => (
                      <TurnoRow
                        key={t.id}
                        t={t}
                        onOpen={() => navigate(`/pianificatore-pdc/turni/${t.id}`)}
                      />
                    ))
                  )}
                </tbody>
              </table>
              <button type="submit" className="sr-only" aria-hidden tabIndex={-1}>
                Cerca
              </button>
            </form>
          </div>
        </section>
      ) : null}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────
// Sub-components
// ────────────────────────────────────────────────────────────────────────

const FILTER_INPUT_CLASS = cn(
  "w-full rounded-sm border border-border bg-white px-1.5 py-1",
  "font-mono text-[11px] text-foreground",
  "focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary",
);

function FilterCellPlaceholder({ placeholder }: { placeholder: string }) {
  return (
    <input
      className={cn(FILTER_INPUT_CLASS, "cursor-not-allowed text-muted-foreground/60")}
      placeholder={placeholder}
      disabled
      aria-hidden
      tabIndex={-1}
    />
  );
}

function TurnoRow({ t, onOpen }: { t: TurnoPdcListItem; onOpen: () => void }) {
  return (
    <tr
      className="cursor-pointer hover:bg-primary/[0.03]"
      onClick={onOpen}
      data-testid={`turno-row-${t.id}`}
    >
      <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground">#{t.id}</td>
      <td className="px-3 py-2.5">
        <span className="flex items-center gap-1.5">
          <span className="font-mono text-[13px] font-semibold text-primary">
            {t.codice}
          </span>
          {t.is_ramo_split && (
            <Badge variant="outline" className="text-xs">
              Ramo {t.split_ramo}/{t.split_totale_rami}
            </Badge>
          )}
        </span>
      </td>
      <td className="px-3 py-2.5 text-sm">{t.impianto}</td>
      <td className="px-3 py-2.5 text-sm text-muted-foreground">{t.profilo}</td>
      <td className="px-3 py-2.5 text-right tabular-nums">{t.n_giornate}</td>
      <td className="px-3 py-2.5 text-right tabular-nums">
        {formatNumber(t.prestazione_totale_min)}
      </td>
      <td className="px-3 py-2.5 text-right tabular-nums">
        {formatNumber(t.condotta_totale_min)}
      </td>
      <td className="px-3 py-2.5 text-right tabular-nums">
        {t.n_violazioni > 0 ? (
          <span className="inline-flex items-center gap-1 text-amber-700">
            <AlertTriangle className="h-3 w-3" aria-hidden />
            {t.n_violazioni}
          </span>
        ) : (
          <span className="text-muted-foreground">0</span>
        )}
      </td>
      <td className="px-3 py-2.5">
        <StatoBadge stato={t.stato} />
      </td>
      <td className="px-3 py-2.5 text-sm text-muted-foreground">
        {formatDateIt(t.valido_da)}
      </td>
      <td className="px-3 py-2.5 text-right">
        <ArrowRight
          className="ml-auto h-4 w-4 text-muted-foreground/40"
          aria-hidden
        />
      </td>
    </tr>
  );
}

function StatoBadge({ stato }: { stato: string }) {
  if (stato === "pubblicato") return <Badge variant="success">pubblicato</Badge>;
  if (stato === "bozza") return <Badge variant="muted">bozza</Badge>;
  if (stato === "archiviato") return <Badge variant="outline">archiviato</Badge>;
  return <Badge variant="outline">{stato}</Badge>;
}

interface KpiPillProps {
  color: "emerald" | "amber" | "muted-strong" | "muted-soft";
  value: number;
  label: string;
}

function KpiPill({ color, value, label }: KpiPillProps) {
  const dotClass =
    color === "emerald"
      ? "bg-emerald-500"
      : color === "amber"
        ? "bg-amber-500"
        : color === "muted-strong"
          ? "bg-muted-foreground/40"
          : "bg-muted-foreground/20";
  return (
    <div className="flex items-center gap-1.5">
      <span className={cn("inline-block h-2 w-2 rounded-full", dotClass)} aria-hidden />
      <span>
        <span className="font-mono tabular-nums text-foreground">{value}</span>{" "}
        {label}
      </span>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-md border border-dashed border-border bg-white py-16 text-center">
      <div className="grid h-16 w-16 place-items-center rounded-full bg-muted">
        <svg
          className="h-8 w-8 text-muted-foreground/40"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden
        >
          <path d="M9 6h11M9 12h11M9 18h11M5 6h.01M5 12h.01M5 18h.01" />
        </svg>
      </div>
      <h2 className="text-base font-semibold">Nessun turno PdC</h2>
      <p className="max-w-md text-sm text-muted-foreground">
        I turni si generano dal dettaglio di un giro materiale (bottone
        &ldquo;Genera turni PdC&rdquo;). Quando ce ne saranno, li vedrai qui
        con i filtri per impianto/stato.
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
