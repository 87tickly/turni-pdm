import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertCircle,
  ArrowRight,
  Download,
  RotateCcw,
  Users,
} from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { useGiriAzienda } from "@/hooks/useGiri";
import { ApiError } from "@/lib/api/client";
import type { GiroListItem } from "@/lib/api/giri";
import { formatDateIt, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import { GeneraTurnoPdcDialog } from "@/routes/pianificatore-giro/GeneraTurnoPdcDialog";

const PAGE_SIZE = 50;

/**
 * Sprint 7.10 MR 7.10.3 — Vista giri materiali per il PIANIFICATORE_PDC.
 *
 * Variante v1 dal pacchetto Anthropic Design Handoff
 * (`arturo/07-vista-giri-pdc.html`): "Filtri inline nell'header tabella".
 * I filtri ricerca/stato si integrano nella riga 2 del `<thead>` (toolbar
 * di input/select), eliminando la form-card sopra che occupava verticale.
 *
 * Sopra la tabella: mini-toolbar con counter + filtri attivi + reset.
 * Sopra il main: KPI mini (pubblicati / bozza / archiviati / totali) come
 * banda informativa orizzontale.
 *
 * Sola lettura: la modifica del giro è competenza del 1° ruolo. Click su
 * una riga apre il visualizzatore Gantt esistente del 1° ruolo.
 */
export function PianificatorePdcGiriRoute() {
  const [searchInput, setSearchInput] = useState("");
  const [statoFilter, setStatoFilter] = useState<string>("");
  const [debouncedQ, setDebouncedQ] = useState("");
  // Sprint 7.9 MR η.1 — dialog generazione turno PdC accessibile dal
  // ruolo Pianificatore PdC senza dover passare per il 1° ruolo.
  const [generaPdcGiroId, setGeneraPdcGiroId] = useState<number | null>(null);
  const navigate = useNavigate();

  const giriQuery = useGiriAzienda({
    q: debouncedQ.length > 0 ? debouncedQ : undefined,
    stato: statoFilter.length > 0 ? statoFilter : undefined,
    limit: PAGE_SIZE,
  });

  const data = giriQuery.data;
  const total = data?.length ?? 0;
  const filtersActive =
    (debouncedQ.length > 0 ? 1 : 0) + (statoFilter.length > 0 ? 1 : 0);

  // KPI banda — derivati dai dati locali; quando l'API esporrà aggregati
  // server-side passeremo a quelli (facet count). Nel frattempo il campo
  // `total` è il count della pagina corrente.
  const kpis = useMemo(() => {
    if (data === undefined) {
      return { pubblicato: 0, bozza: 0, archiviato: 0 };
    }
    let p = 0,
      b = 0,
      a = 0;
    for (const g of data) {
      if (g.stato === "pubblicato") p++;
      else if (g.stato === "bozza") b++;
      else if (g.stato === "archiviato") a++;
    }
    return { pubblicato: p, bozza: b, archiviato: a };
  }, [data]);

  function resetFilters() {
    setSearchInput("");
    setStatoFilter("");
    setDebouncedQ("");
  }

  return (
    <div className="flex flex-col gap-5">
      {/* breadcrumb */}
      <div className="text-xs text-muted-foreground">
        Home <span className="mx-1 text-muted-foreground/40">/</span> Vista giri
      </div>

      {/* HEADER pagina con KPI mini banda */}
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-primary">
            Vista giri materiali
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Giri pubblicati dal Pianificatore Giro, in sola lettura. Click su
            una riga per il visualizzatore Gantt. Da un giro pubblicato puoi{" "}
            <span className="font-medium text-foreground">
              generare il turno PdC
            </span>
            .
          </p>
        </div>
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <KpiPill color="emerald" value={kpis.pubblicato} label="pubblicati" />
          <KpiPill color="muted-strong" value={kpis.bozza} label="bozza" />
          <KpiPill color="muted-soft" value={kpis.archiviato} label="archiviati" />
          <span className="text-muted-foreground/40">|</span>
          <span>
            <span className="font-mono tabular-nums text-foreground">{total}</span>{" "}
            giri totali
          </span>
        </div>
      </header>

      {/* Stati di caricamento / errore / empty / lista */}
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
      ) : data !== undefined && data.length === 0 && filtersActive === 0 ? (
        <EmptyState />
      ) : data !== undefined ? (
        <section className="overflow-hidden rounded-lg border border-border bg-white">
          {/* Mini-toolbar: counter + filtri attivi + reset + export */}
          <div className="flex items-center justify-between border-b border-border bg-muted/40 px-4 py-2.5">
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span>
                Mostro{" "}
                <span className="font-mono tabular-nums text-foreground">
                  {total}
                </span>{" "}
                giri
              </span>
              {filtersActive > 0 && (
                <>
                  <span className="text-muted-foreground/40">·</span>
                  <span className="inline-flex items-center gap-1.5 text-primary">
                    <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden />
                    {filtersActive} filtr{filtersActive === 1 ? "o" : "i"} attiv{filtersActive === 1 ? "o" : "i"}
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

          {/* TABELLA con filtri inline in thead riga 2 */}
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
                    <th className="w-20 px-3 py-2 text-left font-semibold">ID</th>
                    <th className="px-3 py-2 text-left font-semibold">Turno</th>
                    <th className="px-3 py-2 text-left font-semibold">Materiale</th>
                    <th className="w-20 px-3 py-2 text-right font-semibold">Giorn.</th>
                    <th className="w-20 px-3 py-2 text-right font-semibold">Var.</th>
                    <th className="w-24 px-3 py-2 text-right font-semibold">km/g</th>
                    <th className="w-24 px-3 py-2 text-right font-semibold">km/anno</th>
                    <th className="w-28 px-3 py-2 text-left font-semibold">Stato</th>
                    <th className="w-28 px-3 py-2 text-left font-semibold">Creato</th>
                    {/* Sprint 7.9 MR η.1 — colonna azioni: Genera PdC */}
                    <th className="w-32 px-3 py-2 text-right font-semibold">
                      Azioni
                    </th>
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
                        placeholder="es. A001, FIO-12, …"
                        value={searchInput}
                        onChange={(e) => setSearchInput(e.target.value)}
                        aria-label="Cerca giro per numero turno"
                      />
                    </th>
                    <th className="px-2 py-1.5">
                      <FilterCellPlaceholder placeholder="Tutti" />
                    </th>
                    <th className="px-2 py-1.5" />
                    <th className="px-2 py-1.5" />
                    <th className="px-2 py-1.5" />
                    <th className="px-2 py-1.5" />
                    <th className="px-2 py-1.5">
                      <select
                        className={FILTER_INPUT_CLASS}
                        value={statoFilter}
                        onChange={(e) => setStatoFilter(e.target.value)}
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
                        Nessun giro corrisponde ai filtri attivi.
                      </td>
                    </tr>
                  ) : (
                    data.map((g) => (
                      <GiroRow
                        key={g.id}
                        g={g}
                        onOpen={() => navigate(`/pianificatore-giro/giri/${g.id}`)}
                        onGeneraPdc={() => setGeneraPdcGiroId(g.id)}
                      />
                    ))
                  )}
                </tbody>
              </table>
              {/* Submit button hidden but presente per Enter dentro l'input */}
              <button type="submit" className="sr-only" aria-hidden tabIndex={-1}>
                Cerca
              </button>
            </form>
          </div>
        </section>
      ) : null}

      {/* Sprint 7.9 MR η.1 — dialog generazione PdC accessibile dalla
          vista giri del 2° ruolo (Pianificatore PdC). */}
      {generaPdcGiroId !== null && (
        <GeneraTurnoPdcDialog
          giroId={generaPdcGiroId}
          open
          onOpenChange={(o) => {
            if (!o) setGeneraPdcGiroId(null);
          }}
        />
      )}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────
// Constants & sub-components
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

function GiroRow({
  g,
  onOpen,
  onGeneraPdc,
}: {
  g: GiroListItem;
  onOpen: () => void;
  onGeneraPdc: () => void;
}) {
  return (
    <tr
      className="cursor-pointer hover:bg-primary/[0.03]"
      onClick={onOpen}
      data-testid={`giro-row-${g.id}`}
    >
      <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground">#{g.id}</td>
      <td className="px-3 py-2.5 font-mono text-[13px] font-semibold text-primary">
        {g.numero_turno}
      </td>
      <td className="px-3 py-2.5 font-mono text-xs text-foreground/80">
        {g.tipo_materiale}
      </td>
      <td className="px-3 py-2.5 text-right tabular-nums">{g.numero_giornate}</td>
      <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">
        {g.n_varianti_totale}
      </td>
      <td className="px-3 py-2.5 text-right tabular-nums">
        {g.km_media_giornaliera !== null
          ? formatNumber(Math.round(g.km_media_giornaliera))
          : "—"}
      </td>
      <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">
        {g.km_media_annua !== null ? formatNumber(Math.round(g.km_media_annua)) : "—"}
      </td>
      <td className="px-3 py-2.5">
        <StatoBadge stato={g.stato} />
      </td>
      <td className="px-3 py-2.5 text-xs text-muted-foreground">
        {formatDateIt(g.created_at)}
      </td>
      <td className="px-3 py-2.5 text-right">
        {/* Sprint 7.9 MR η.1 — punto di ingresso "Genera PdC" dal ruolo
            Pianificatore PdC. stopPropagation evita la navigazione di
            riga (onOpen). */}
        <Button
          variant="primary"
          size="sm"
          onClick={(e) => {
            e.stopPropagation();
            onGeneraPdc();
          }}
          title="Genera turno PdC da questo giro"
        >
          <Users className="mr-1.5 h-3.5 w-3.5" aria-hidden /> Genera PdC
        </Button>
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
  color: "emerald" | "muted-strong" | "muted-soft";
  value: number;
  label: string;
}

function KpiPill({ color, value, label }: KpiPillProps) {
  const dotClass =
    color === "emerald"
      ? "bg-emerald-500"
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
          <path d="M14 4l6 6m0-6l-6 6M3 8h7m-7 4h11m-11 4h7" />
        </svg>
      </div>
      <h2 className="text-base font-semibold">Nessun giro materiale</h2>
      <p className="max-w-md text-sm text-muted-foreground">
        I giri vengono creati dal Pianificatore Giro Materiale. Quando ce ne
        saranno, li vedrai qui in sola lettura.
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
