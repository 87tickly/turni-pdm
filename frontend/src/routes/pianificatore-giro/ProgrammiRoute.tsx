import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertCircle, ChevronLeft, ChevronRight, Plus } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { useGiriProgramma } from "@/hooks/useGiri";
import {
  useArchiviaProgramma,
  useProgramma,
  useProgrammi,
  usePubblicaProgramma,
} from "@/hooks/useProgrammi";
import { ApiError } from "@/lib/api/client";
import type {
  ListProgrammiParams,
  ProgrammaMaterialeRead,
  ProgrammaStato,
} from "@/lib/api/programmi";
import { formatDateIt, formatPeriodo } from "@/lib/format";
import { cn } from "@/lib/utils";
import { CreaProgrammaDialog } from "@/routes/pianificatore-giro/CreaProgrammaDialog";

type ViewMode = "calendario" | "tabella";

const STATO_OPTIONS: ReadonlyArray<{ value: "" | ProgrammaStato; label: string }> = [
  { value: "", label: "Tutti" },
  { value: "bozza", label: "Bozza" },
  { value: "attivo", label: "Attivo" },
  { value: "archiviato", label: "Archiviato" },
];

const MONTHS_SHORT = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"];

export function ProgrammiRoute() {
  const [viewMode, setViewMode] = useState<ViewMode>("calendario");
  const [statoFilter, setStatoFilter] = useState<"" | ProgrammaStato>("");
  const [dialogOpen, setDialogOpen] = useState(false);

  const params = useMemo<ListProgrammiParams>(() => {
    const p: ListProgrammiParams = {};
    if (statoFilter !== "") p.stato = statoFilter;
    return p;
  }, [statoFilter]);

  const programmiQuery = useProgrammi(params);
  // Lista globale (no filtro stato) per il counter "X attivi · Y bozze · Z archiviati".
  const allProgrammiQuery = useProgrammi({});
  const navigate = useNavigate();

  const programmi = programmiQuery.data ?? [];
  const counts = useMemo(
    () => countByStato(allProgrammiQuery.data ?? []),
    [allProgrammiQuery.data],
  );
  const hasFilters = statoFilter !== "";

  return (
    <div className="flex flex-col gap-5">
      {/* ─── Title row ───────────────────────────────────────── */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">Programmi</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            <ProgrammiCounter counts={counts} loading={allProgrammiQuery.isLoading} />
          </p>
        </div>
        <Button onClick={() => setDialogOpen(true)}>
          <Plus className="mr-2 h-4 w-4" aria-hidden /> Nuovo programma
        </Button>
      </div>

      {/* ─── Controls bar ────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ViewSwitcher value={viewMode} onChange={setViewMode} />
        <StatoSegmented value={statoFilter} onChange={setStatoFilter} />
      </div>

      {/* ─── Body ────────────────────────────────────────────── */}
      {programmiQuery.isLoading ? (
        <div className="flex items-center justify-center rounded-lg border border-border bg-white py-16">
          <Spinner label="Caricamento programmi…" />
        </div>
      ) : programmiQuery.isError ? (
        <ErrorBanner error={programmiQuery.error} onRetry={() => void programmiQuery.refetch()} />
      ) : programmi.length === 0 ? (
        <EmptyState
          hasFilters={hasFilters}
          onCreate={() => setDialogOpen(true)}
          onClearFilters={() => setStatoFilter("")}
        />
      ) : viewMode === "calendario" ? (
        <CalendarioView
          programmi={programmi}
          onOpen={(id) => navigate(`/pianificatore-giro/programmi/${id}`)}
        />
      ) : (
        <TabellaView
          programmi={programmi}
          onOpen={(id) => navigate(`/pianificatore-giro/programmi/${id}`)}
        />
      )}

      <CreaProgrammaDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onCreated={(p) => navigate(`/pianificatore-giro/programmi/${p.id}`)}
      />
    </div>
  );
}

// =====================================================================
// Counter "N programmi · X attivi, Y bozze, Z archiviati"
// =====================================================================

interface ProgrammiCounts {
  total: number;
  attivo: number;
  bozza: number;
  archiviato: number;
}

function countByStato(programmi: ProgrammaMaterialeRead[]): ProgrammiCounts {
  return programmi.reduce<ProgrammiCounts>(
    (acc, p) => {
      acc.total += 1;
      acc[p.stato] += 1;
      return acc;
    },
    { total: 0, attivo: 0, bozza: 0, archiviato: 0 },
  );
}

function ProgrammiCounter({ counts, loading }: { counts: ProgrammiCounts; loading: boolean }) {
  if (loading) return <span>caricamento…</span>;
  if (counts.total === 0) return <span>Nessun programma · crea il primo dalla CTA in alto.</span>;
  const parts: string[] = [];
  if (counts.attivo > 0) parts.push(`${counts.attivo} attiv${counts.attivo === 1 ? "o" : "i"}`);
  if (counts.bozza > 0) parts.push(`${counts.bozza} bozz${counts.bozza === 1 ? "a" : "e"}`);
  if (counts.archiviato > 0)
    parts.push(`${counts.archiviato} archiviat${counts.archiviato === 1 ? "o" : "i"}`);
  return (
    <span>
      {counts.total} {counts.total === 1 ? "programma" : "programmi"}
      {parts.length > 0 && ` · ${parts.join(", ")}`}
    </span>
  );
}

// =====================================================================
// View switcher (Tabella | Calendario)
// =====================================================================

function ViewSwitcher({
  value,
  onChange,
}: {
  value: ViewMode;
  onChange: (v: ViewMode) => void;
}) {
  return (
    <div className="inline-flex items-center rounded-md border border-border bg-white p-0.5 text-sm">
      <SegButton active={value === "tabella"} onClick={() => onChange("tabella")} aria-label="Vista tabella">
        Tabella
      </SegButton>
      <SegButton active={value === "calendario"} onClick={() => onChange("calendario")} aria-label="Vista calendario">
        Calendario
      </SegButton>
    </div>
  );
}

function SegButton({
  active,
  onClick,
  children,
  ...rest
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded px-3 py-1.5 transition-colors",
        active ? "bg-foreground text-white font-medium" : "text-muted-foreground hover:bg-muted",
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

// =====================================================================
// Stato segmented filter
// =====================================================================

function StatoSegmented({
  value,
  onChange,
}: {
  value: "" | ProgrammaStato;
  onChange: (v: "" | ProgrammaStato) => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <label
        id="stato-filter-label"
        className="text-xs uppercase tracking-wide text-muted-foreground"
      >
        Stato
      </label>
      <div
        role="group"
        aria-labelledby="stato-filter-label"
        className="inline-flex items-center divide-x divide-border rounded-md border border-border bg-white text-sm"
      >
        {STATO_OPTIONS.map((opt) => {
          const isActive = value === opt.value;
          return (
            <button
              key={opt.value || "all"}
              type="button"
              onClick={() => onChange(opt.value)}
              aria-pressed={isActive}
              className={cn(
                "px-3 py-1.5 first:rounded-l-md last:rounded-r-md transition-colors",
                isActive
                  ? "bg-muted font-medium text-foreground"
                  : "text-muted-foreground hover:bg-muted/60",
              )}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// =====================================================================
// Calendario view
// =====================================================================

function CalendarioView({
  programmi,
  onOpen,
}: {
  programmi: ProgrammaMaterialeRead[];
  onOpen: (id: number) => void;
}) {
  const programYears = useMemo(() => listProgramYears(programmi), [programmi]);
  const currentYear = new Date().getFullYear();
  const [selectedYear, setSelectedYear] = useState<number>(() => {
    if (programYears.includes(currentYear)) return currentYear;
    return programYears[0] ?? currentYear;
  });

  // Se la lista cambia (es. filtro stato) e l'anno selezionato non ha più
  // alcun programma, riposiziona su un anno valido.
  useEffect(() => {
    if (programYears.length > 0 && !programYears.includes(selectedYear)) {
      setSelectedYear(programYears[0] ?? currentYear);
    }
  }, [programYears, selectedYear, currentYear]);

  const ordered = useMemo(
    () => [...programmi].sort((a, b) => a.valido_da.localeCompare(b.valido_da)),
    [programmi],
  );
  const fuoriAnno = ordered.filter((p) => !programmaSpansYear(p, selectedYear));

  const todayPct = todayPctInYear(selectedYear);

  return (
    <section className="rounded-lg border border-border bg-white">
      {/* Year nav */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-3">
        <YearNav
          years={programYears}
          selected={selectedYear}
          onSelect={setSelectedYear}
        />
        <Legend />
      </div>

      {/* Gantt */}
      <div className="px-5 py-5">
        {/* Header mesi */}
        <div className="grid grid-cols-[180px_1fr] gap-4">
          <div></div>
          <div className="grid grid-cols-12 border-b border-border pb-2 text-[11px] uppercase tracking-wide text-muted-foreground">
            {MONTHS_SHORT.map((m) => (
              <div key={m}>{m}</div>
            ))}
          </div>
        </div>

        {/* Rows */}
        <div className="relative mt-2 grid grid-cols-[180px_1fr] gap-4">
          {/* Etichette riga (sx) */}
          <div className="flex flex-col">
            {ordered.map((p) => (
              <CalendarRowLabel key={p.id} programma={p} />
            ))}
          </div>

          {/* Tracce + barre (dx) */}
          <div className="relative">
            {/* Vertical month grid */}
            <div className="pointer-events-none absolute inset-0 grid grid-cols-12">
              {Array.from({ length: 12 }, (_, i) => (
                <div key={i} className="border-l border-border/40" />
              ))}
            </div>

            {/* Today line */}
            {todayPct !== null && (
              <div
                className="pointer-events-none absolute top-0 z-10 h-full"
                style={{ left: `${todayPct}%` }}
              >
                <div className="h-full w-0.5 bg-destructive" />
                <div className="absolute -top-5 -left-3 text-[10px] font-medium uppercase tracking-wide text-destructive">
                  oggi
                </div>
              </div>
            )}

            {/* Rows */}
            {ordered.map((p) => (
              <CalendarRow key={p.id} programma={p} year={selectedYear} onOpen={onOpen} />
            ))}
          </div>
        </div>

        {/* Footer note */}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3 text-xs text-muted-foreground">
          {fuoriAnno.length > 0 ? (
            <span>
              {fuoriAnno.length} programm{fuoriAnno.length === 1 ? "a ricade" : "i ricadono"} fuori
              dal {selectedYear} — usa la navigazione anno per visualizzar
              {fuoriAnno.length === 1 ? "lo" : "li"}.
            </span>
          ) : (
            <span>Tutti i programmi sono visibili in questo anno.</span>
          )}
          <span className="font-mono tabular-nums">
            {ordered.length} programm{ordered.length === 1 ? "a" : "i"} totali
          </span>
        </div>
      </div>
    </section>
  );
}

function YearNav({
  years,
  selected,
  onSelect,
}: {
  years: number[];
  selected: number;
  onSelect: (y: number) => void;
}) {
  const idx = years.indexOf(selected);
  const prev = idx > 0 ? years[idx - 1] : null;
  const next = idx >= 0 && idx < years.length - 1 ? years[idx + 1] : null;
  // Buttons mostrano sempre prev/curr/next con highlight su quello selezionato.
  const display = years.length === 0 ? [selected] : windowAround(years, selected, 1);

  return (
    <div className="inline-flex items-center gap-1 text-sm">
      <button
        type="button"
        onClick={() => prev !== null && onSelect(prev)}
        disabled={prev === null}
        aria-label="Anno precedente"
        className="rounded px-1.5 py-1 text-muted-foreground hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40"
      >
        <ChevronLeft className="h-4 w-4" aria-hidden />
      </button>
      {display.map((y) => (
        <button
          key={y}
          type="button"
          onClick={() => onSelect(y)}
          aria-pressed={y === selected}
          className={cn(
            "rounded px-2.5 py-1 transition-colors",
            y === selected
              ? "bg-foreground font-medium text-white"
              : "text-muted-foreground hover:bg-muted",
          )}
        >
          {y}
        </button>
      ))}
      <button
        type="button"
        onClick={() => next !== null && onSelect(next)}
        disabled={next === null}
        aria-label="Anno successivo"
        className="rounded px-1.5 py-1 text-muted-foreground hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40"
      >
        <ChevronRight className="h-4 w-4" aria-hidden />
      </button>
    </div>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
      <span className="inline-flex items-center gap-1.5">
        <span className="h-3 w-3 rounded-sm bg-emerald-500" /> Attivo
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span
          className="h-3 w-3 rounded-sm border border-muted-foreground/40"
          style={{
            backgroundImage:
              "repeating-linear-gradient(45deg, hsl(var(--border-rgb, 0 0% 80%)) 0 4px, transparent 4px 8px)",
          }}
        />{" "}
        Bozza
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="h-3 w-3 rounded-sm bg-muted-foreground/40" /> Archiviato
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="inline-block h-3.5 w-0.5 bg-destructive" /> Oggi
      </span>
    </div>
  );
}

function CalendarRowLabel({ programma }: { programma: ProgrammaMaterialeRead }) {
  const detailQuery = useProgramma(programma.id);
  const giriQuery = useGiriProgramma(programma.id);
  const regole = detailQuery.data?.regole.length;
  const giri = giriQuery.data?.length;
  return (
    <div className="mt-1 flex h-9 flex-col justify-center pr-2 text-right">
      <div
        className={cn(
          "truncate text-sm font-medium",
          programma.stato === "archiviato" ? "text-muted-foreground" : "text-foreground",
        )}
      >
        {programma.nome}
      </div>
      <div className="font-mono text-[10px] text-muted-foreground">
        #{programma.id}
        {regole !== undefined && ` · ${regole} reg`}
        {giri !== undefined && ` · ${giri} giri`}
      </div>
    </div>
  );
}

function CalendarRow({
  programma,
  year,
  onOpen,
}: {
  programma: ProgrammaMaterialeRead;
  year: number;
  onOpen: (id: number) => void;
}) {
  const inYear = programmaSpansYear(programma, year);

  if (!inYear) {
    const yStart = parseInt(programma.valido_da.slice(0, 4), 10);
    const yEnd = parseInt(programma.valido_a.slice(0, 4), 10);
    const range = yStart === yEnd ? `${yStart}` : `${yStart}-${yEnd}`;
    return (
      <div className="relative h-9">
        <span className="absolute left-2 top-2 text-[11px] italic text-muted-foreground">
          — ricade nel {range} —
        </span>
      </div>
    );
  }

  const pos = barPosition(programma, year);
  const tooltip = `#${programma.id} · ${programma.nome} · ${formatPeriodo(programma.valido_da, programma.valido_a)} · ${programma.stato.toUpperCase()}`;

  return (
    <div className="relative h-9">
      <button
        type="button"
        title={tooltip}
        onClick={() => onOpen(programma.id)}
        aria-label={tooltip}
        className={cn(
          "absolute top-1.5 bottom-1.5 flex items-center rounded px-2 text-xs transition-opacity",
          programma.stato === "attivo" &&
            "bg-emerald-500 text-white hover:bg-emerald-600 font-medium",
          programma.stato === "bozza" && "bar-bozza text-foreground hover:opacity-80 font-medium",
          programma.stato === "archiviato" &&
            "bg-muted-foreground/40 text-foreground hover:bg-muted-foreground/60",
        )}
        style={{
          left: `${pos.leftPct}%`,
          width: `${pos.widthPct}%`,
        }}
      >
        <span className="truncate">{programma.nome}</span>
      </button>
    </div>
  );
}

// =====================================================================
// Tabella view (alt) — match design columns
// =====================================================================

function TabellaView({
  programmi,
  onOpen,
}: {
  programmi: ProgrammaMaterialeRead[];
  onOpen: (id: number) => void;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-white">
      <table className="w-full text-sm">
        <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="w-16 px-4 py-2.5 text-left font-medium">ID</th>
            <th className="px-4 py-2.5 text-left font-medium">Nome</th>
            <th className="px-4 py-2.5 text-left font-medium">Periodo</th>
            <th className="w-24 px-4 py-2.5 text-left font-medium">Stato</th>
            <th className="w-20 px-4 py-2.5 text-right font-medium">Regole</th>
            <th className="w-20 px-4 py-2.5 text-right font-medium">Giri</th>
            <th className="w-28 px-4 py-2.5 text-left font-medium">Aggiornato</th>
            <th className="px-4 py-2.5 text-right font-medium">Azioni</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {programmi.map((p) => (
            <ProgrammaRow key={p.id} programma={p} onOpen={onOpen} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProgrammaRow({
  programma,
  onOpen,
}: {
  programma: ProgrammaMaterialeRead;
  onOpen: (id: number) => void;
}) {
  const detailQuery = useProgramma(programma.id);
  const giriQuery = useGiriProgramma(programma.id);
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
    <tr
      className="cursor-pointer hover:bg-muted/30"
      onClick={() => onOpen(programma.id)}
      data-testid={`programma-row-${programma.id}`}
    >
      <td className="px-4 py-3 font-mono text-xs text-muted-foreground">#{programma.id}</td>
      <td
        className={cn(
          "px-4 py-3 font-medium",
          programma.stato === "archiviato" ? "text-muted-foreground" : "text-foreground",
        )}
      >
        {programma.nome}
      </td>
      <td className="whitespace-nowrap px-4 py-3 text-foreground tabular-nums">
        {formatPeriodo(programma.valido_da, programma.valido_a)}
      </td>
      <td className="px-4 py-3">
        <StatoTag stato={programma.stato} />
      </td>
      <td className="px-4 py-3 text-right text-foreground tabular-nums">
        {detailQuery.data === undefined ? "—" : detailQuery.data.regole.length}
      </td>
      <td className="px-4 py-3 text-right text-foreground tabular-nums">
        {giriQuery.data === undefined
          ? programma.stato === "bozza"
            ? "—"
            : "…"
          : giriQuery.data.length}
      </td>
      <td className="px-4 py-3 text-xs text-muted-foreground">
        {formatDateIt(programma.updated_at)}
      </td>
      <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-end gap-1">
          {programma.stato === "bozza" && (
            <Button
              size="sm"
              variant="ghost"
              onClick={handlePubblica}
              disabled={busy}
              aria-label={`Pubblica ${programma.nome}`}
              className="h-7 px-2 text-xs text-primary hover:underline"
            >
              Pubblica
            </Button>
          )}
          {programma.stato === "attivo" && (
            <Button
              size="sm"
              variant="ghost"
              onClick={handleArchivia}
              disabled={busy}
              aria-label={`Archivia ${programma.nome}`}
              className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground"
            >
              Archivia
            </Button>
          )}
          <span className="text-xs text-primary hover:underline">Apri →</span>
        </div>
      </td>
    </tr>
  );
}

function StatoTag({ stato }: { stato: ProgrammaStato }) {
  const map: Record<ProgrammaStato, string> = {
    bozza: "bg-muted text-muted-foreground",
    attivo: "bg-emerald-100 text-emerald-800",
    archiviato: "bg-muted/60 text-muted-foreground",
  };
  const label = stato === "bozza" ? "Bozza" : stato === "attivo" ? "Attivo" : "Archiviato";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
        map[stato],
      )}
    >
      {label}
    </span>
  );
}

// =====================================================================
// Empty + error
// =====================================================================

function EmptyState({
  hasFilters,
  onCreate,
  onClearFilters,
}: {
  hasFilters: boolean;
  onCreate: () => void;
  onClearFilters: () => void;
}) {
  if (hasFilters) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-white py-16 text-center">
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
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-white py-16 text-center">
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
      className="flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-4"
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

// =====================================================================
// Calendar utils
// =====================================================================

function isLeapYear(year: number): boolean {
  return (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
}

function dayOfYear(date: Date, year: number): number {
  const yearStart = Date.UTC(year, 0, 1);
  return Math.floor((date.getTime() - yearStart) / (24 * 3600 * 1000));
}

function programmaSpansYear(p: ProgrammaMaterialeRead, year: number): boolean {
  const yStart = Date.UTC(year, 0, 1);
  const yEnd = Date.UTC(year, 11, 31);
  const da = Date.parse(`${p.valido_da}T00:00:00Z`);
  const a = Date.parse(`${p.valido_a}T00:00:00Z`);
  return !(a < yStart || da > yEnd);
}

function barPosition(p: ProgrammaMaterialeRead, year: number) {
  const yStart = new Date(Date.UTC(year, 0, 1));
  const yEnd = new Date(Date.UTC(year, 11, 31));
  const da = new Date(`${p.valido_da}T00:00:00Z`);
  const a = new Date(`${p.valido_a}T00:00:00Z`);
  const startClipped = da < yStart ? yStart : da;
  const endClipped = a > yEnd ? yEnd : a;
  const totalDays = isLeapYear(year) ? 366 : 365;
  const startDay = dayOfYear(startClipped, year);
  const endDay = dayOfYear(endClipped, year);
  return {
    leftPct: (startDay / totalDays) * 100,
    widthPct: ((endDay - startDay + 1) / totalDays) * 100,
  };
}

function todayPctInYear(year: number): number | null {
  const now = new Date();
  if (now.getUTCFullYear() !== year) return null;
  const day = dayOfYear(now, year);
  const totalDays = isLeapYear(year) ? 366 : 365;
  return (day / totalDays) * 100;
}

function listProgramYears(programmi: ProgrammaMaterialeRead[]): number[] {
  const years = new Set<number>();
  for (const p of programmi) {
    const start = parseInt(p.valido_da.slice(0, 4), 10);
    const end = parseInt(p.valido_a.slice(0, 4), 10);
    for (let y = start; y <= end; y++) years.add(y);
  }
  if (years.size > 0) {
    const cur = new Date().getFullYear();
    years.add(cur); // sempre includere anno corrente
  }
  return Array.from(years).sort();
}

function windowAround(years: number[], selected: number, radius: number): number[] {
  const idx = years.indexOf(selected);
  if (idx === -1) return [selected];
  const start = Math.max(0, idx - radius);
  const end = Math.min(years.length, idx + radius + 1);
  return years.slice(start, end);
}
