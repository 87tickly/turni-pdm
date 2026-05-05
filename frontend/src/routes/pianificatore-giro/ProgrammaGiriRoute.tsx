import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Search,
  Users,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { useGiriProgramma, useGiroDettaglio } from "@/hooks/useGiri";
import { useProgramma } from "@/hooks/useProgrammi";
import { ApiError } from "@/lib/api/client";
import type {
  GiroBlocco,
  GiroDettaglio,
  GiroGiornata,
  GiroListItem,
} from "@/lib/api/giri";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import { GeneraTurnoPdcDialog } from "@/routes/pianificatore-giro/GeneraTurnoPdcDialog";

/**
 * Schermata 4 — Lista giri generati di un programma.
 * Design: `arturo/04-giri.html`. Layout principale a 8/4: tabella sx +
 * preview pane dx (collassabile via ✕). KPI band in cima + filtri sticky.
 */

interface FiltersState {
  search: string;
  sede: string;
  materiale: string;
  motivo: string;
  soloNonChiusi: boolean;
}

const EMPTY_FILTERS: FiltersState = {
  search: "",
  sede: "",
  materiale: "",
  motivo: "",
  soloNonChiusi: false,
};

export function ProgrammaGiriRoute() {
  const { programmaId: programmaIdParam } = useParams<{ programmaId: string }>();
  const programmaId = programmaIdParam !== undefined ? Number(programmaIdParam) : undefined;
  const navigate = useNavigate();

  const programmaQuery = useProgramma(programmaId);
  const giriQuery = useGiriProgramma(programmaId);

  const [filters, setFilters] = useState<FiltersState>(EMPTY_FILTERS);
  const [selectedGiroId, setSelectedGiroId] = useState<number | null>(null);
  const [previewOpen, setPreviewOpen] = useState(true);
  // Sprint 7.9 MR η.1 — dialog generazione PdC mountato a livello
  // pagina, attivato dalla riga giro corrispondente.
  const [generaPdcGiroId, setGeneraPdcGiroId] = useState<number | null>(null);

  const giri = useMemo(() => giriQuery.data ?? [], [giriQuery.data]);

  const distinct = useMemo(() => buildDistinctOptions(giri), [giri]);
  const filtered = useMemo(() => applyFilters(giri, filters), [giri, filters]);
  const stats = useMemo(() => computeStats(giri), [giri]);
  const hasFilters =
    filters.search !== "" ||
    filters.sede !== "" ||
    filters.materiale !== "" ||
    filters.motivo !== "" ||
    filters.soloNonChiusi;

  const showPreview = previewOpen && selectedGiroId !== null;

  if (programmaId === undefined || Number.isNaN(programmaId)) {
    return <ErrorBlock message="ID programma non valido nell'URL." />;
  }

  return (
    <div className="flex flex-col gap-5">
      {/* Back link + title row */}
      <div className="flex flex-col gap-1">
        <Link
          to={`/pianificatore-giro/programmi/${programmaId}`}
          className="inline-flex w-fit items-center gap-1 text-xs text-muted-foreground hover:text-primary"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> Dettaglio programma
          {programmaQuery.data?.nome !== undefined && ` · ${programmaQuery.data.nome}`}
        </Link>
      </div>

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Giri generati</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Output del builder
            {programmaQuery.data?.nome !== undefined && (
              <>
                {" "}
                per <span className="font-medium text-foreground">{programmaQuery.data.nome}</span>
              </>
            )}
          </p>
        </div>
        <Link
          to={`/pianificatore-giro/programmi/${programmaId}`}
          className="inline-flex items-center gap-2 rounded-md border border-border bg-white px-3.5 py-2 text-sm text-foreground hover:bg-muted"
        >
          Apri dettaglio programma
          <ArrowRight className="h-4 w-4" aria-hidden />
        </Link>
      </div>

      {/* Body */}
      {giriQuery.isLoading ? (
        <Card className="grid place-items-center p-16">
          <Spinner label="Caricamento giri…" />
        </Card>
      ) : giriQuery.isError ? (
        <ErrorBlock
          message={
            giriQuery.error instanceof ApiError
              ? giriQuery.error.message
              : (giriQuery.error as Error).message
          }
          onRetry={() => void giriQuery.refetch()}
        />
      ) : giri.length === 0 ? (
        <EmptyState programmaId={programmaId} />
      ) : (
        <>
          {/* KPI band */}
          <KpiBand
            stats={stats}
            onClickNonChiusi={() => setFilters({ ...filters, soloNonChiusi: true })}
          />

          {/* Filters bar */}
          <FiltersBar
            filters={filters}
            distinct={distinct}
            visibleCount={filtered.length}
            totalCount={giri.length}
            hasFilters={hasFilters}
            onChange={setFilters}
            onReset={() => setFilters(EMPTY_FILTERS)}
          />

          {/* Table + preview */}
          <section
            className={cn(
              "grid grid-cols-1 gap-4",
              showPreview ? "lg:grid-cols-12" : "lg:grid-cols-1",
            )}
          >
            <div
              className={cn(
                "overflow-hidden rounded-lg border border-border bg-white",
                showPreview && "lg:col-span-8",
              )}
            >
              {filtered.length === 0 ? (
                <FilteredEmptyState onReset={() => setFilters(EMPTY_FILTERS)} />
              ) : (
                <GiriTable
                  giri={filtered}
                  selectedId={selectedGiroId}
                  onSelect={(id) => {
                    setSelectedGiroId(id);
                    setPreviewOpen(true);
                  }}
                  onOpenFull={(id) => navigate(`/pianificatore-giro/giri/${id}`)}
                  onGeneraPdc={(id) => setGeneraPdcGiroId(id)}
                />
              )}
            </div>

            {showPreview && selectedGiroId !== null && (
              <aside className="self-start lg:col-span-4">
                <PreviewPane
                  giroId={selectedGiroId}
                  onClose={() => setPreviewOpen(false)}
                  onOpenFull={() => navigate(`/pianificatore-giro/giri/${selectedGiroId}`)}
                />
              </aside>
            )}

            {!showPreview && selectedGiroId !== null && (
              <div className="lg:fixed lg:right-8 lg:top-24">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPreviewOpen(true)}
                  className="shadow-sm"
                >
                  Apri anteprima
                </Button>
              </div>
            )}
          </section>
        </>
      )}

      {/* Sprint 7.9 MR η.1 — dialog generazione PdC accessibile da ogni
          riga della lista giri. Il flusso è autocontained: l'utente
          sceglie il deposito (auto-suggerito) e clicca Genera. */}
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

// =====================================================================
// KPI band
// =====================================================================

interface Stats {
  total: number;
  chiusiNaturali: number;
  pctNaturali: number;
  kmGiornoCumulato: number;
  mediaKmGiro: number;
  nonChiusi: number;
  nonChiusiKmCap: number;
  nonChiusiSafety: number;
}

function computeStats(giri: GiroListItem[]): Stats {
  const total = giri.length;
  const chiusiNaturali = giri.filter((g) => g.motivo_chiusura === "naturale").length;
  const pctNaturali = total > 0 ? Math.round((chiusiNaturali / total) * 100) : 0;
  const kmGiornoCumulato = giri.reduce(
    (s, g) => s + (g.km_media_giornaliera ?? 0),
    0,
  );
  const mediaKmGiro = total > 0 ? Math.round(kmGiornoCumulato / total) : 0;
  const nonChiusi = giri.filter((g) => !g.chiuso).length;
  const nonChiusiKmCap = giri.filter(
    (g) => !g.chiuso && g.motivo_chiusura === "km_cap",
  ).length;
  const nonChiusiSafety = giri.filter(
    (g) => !g.chiuso && g.motivo_chiusura === "safety_n_giornate",
  ).length;
  return {
    total,
    chiusiNaturali,
    pctNaturali,
    kmGiornoCumulato: Math.round(kmGiornoCumulato),
    mediaKmGiro,
    nonChiusi,
    nonChiusiKmCap,
    nonChiusiSafety,
  };
}

function KpiBand({ stats, onClickNonChiusi }: { stats: Stats; onClickNonChiusi: () => void }) {
  return (
    <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <Card className="p-4">
        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Giri totali</div>
        <div className="mt-1 text-3xl font-semibold tabular-nums text-foreground">
          {formatNumber(stats.total)}
        </div>
        <div className="mt-1 text-xs text-muted-foreground">in questo programma</div>
      </Card>

      <Card className="p-4">
        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
          Chiusi naturalmente
        </div>
        <div className="mt-1 text-3xl font-semibold tabular-nums text-emerald-700">
          {stats.pctNaturali}
          <span className="text-lg text-emerald-600">%</span>
        </div>
        <div className="mt-1 text-xs text-muted-foreground tabular-nums">
          {stats.chiusiNaturali} / {stats.total}
        </div>
      </Card>

      <Card className="p-4">
        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
          Km/giorno cumulato
        </div>
        <div className="mt-1 text-3xl font-semibold tabular-nums text-foreground">
          {formatNumber(stats.kmGiornoCumulato)}
        </div>
        <div className="mt-1 text-xs text-muted-foreground tabular-nums">
          media {formatNumber(stats.mediaKmGiro)} km/giro
        </div>
      </Card>

      <button
        type="button"
        onClick={onClickNonChiusi}
        disabled={stats.nonChiusi === 0}
        title={
          stats.nonChiusi === 0
            ? "Tutti i giri sono chiusi"
            : "Filtra automaticamente solo non chiusi"
        }
        className={cn(
          "rounded-lg border bg-white p-4 text-left transition",
          stats.nonChiusi > 0
            ? "border-amber-300 hover:bg-amber-50"
            : "border-border opacity-70",
        )}
      >
        <div
          className={cn(
            "text-[11px] uppercase tracking-wide",
            stats.nonChiusi > 0 ? "text-amber-800" : "text-muted-foreground",
          )}
        >
          Giri non chiusi
        </div>
        <div
          className={cn(
            "mt-1 text-3xl font-semibold tabular-nums",
            stats.nonChiusi > 0 ? "text-amber-700" : "text-foreground",
          )}
        >
          {stats.nonChiusi}
        </div>
        {stats.nonChiusi > 0 && (
          <div className="mt-1 flex items-center gap-1 text-xs text-amber-700 tabular-nums">
            {stats.nonChiusiKmCap} km_cap · {stats.nonChiusiSafety} safety
            <ArrowRight className="ml-auto h-3.5 w-3.5" aria-hidden />
          </div>
        )}
      </button>
    </section>
  );
}

// =====================================================================
// Filters
// =====================================================================

interface DistinctOptions {
  sedi: string[];
  materiali: string[];
  motivi: string[];
}

function buildDistinctOptions(giri: GiroListItem[]): DistinctOptions {
  const sedi = new Set<string>();
  const materiali = new Set<string>();
  const motivi = new Set<string>();
  for (const g of giri) {
    const sede = parseSede(g.numero_turno);
    if (sede !== null) sedi.add(sede);
    if (g.materiale_tipo_codice !== null) materiali.add(g.materiale_tipo_codice);
    materiali.add(g.tipo_materiale);
    if (g.motivo_chiusura !== null) motivi.add(g.motivo_chiusura);
    if (!g.chiuso) motivi.add("non_chiuso");
  }
  return {
    sedi: Array.from(sedi).sort(),
    materiali: Array.from(materiali).sort(),
    motivi: Array.from(motivi).sort(),
  };
}

/** Estrae la sede da `numero_turno` formato `G-{SEDE}-NNN[-VAR]` (es. "G-FIO-001-ETR526" → "FIO"). */
function parseSede(numeroTurno: string): string | null {
  const m = numeroTurno.match(/^G-([A-Z]+)-/);
  return m !== null ? m[1] : null;
}

function applyFilters(giri: GiroListItem[], f: FiltersState): GiroListItem[] {
  const search = f.search.trim().toLowerCase();
  return giri.filter((g) => {
    if (search !== "" && !g.numero_turno.toLowerCase().includes(search)) return false;
    if (f.sede !== "" && parseSede(g.numero_turno) !== f.sede) return false;
    if (f.materiale !== "") {
      const mat = g.materiale_tipo_codice ?? g.tipo_materiale;
      if (mat !== f.materiale) return false;
    }
    if (f.motivo !== "") {
      if (f.motivo === "non_chiuso") {
        if (g.chiuso) return false;
      } else if (g.motivo_chiusura !== f.motivo) {
        return false;
      }
    }
    if (f.soloNonChiusi && g.chiuso) return false;
    return true;
  });
}

function FiltersBar({
  filters,
  distinct,
  visibleCount,
  totalCount,
  hasFilters,
  onChange,
  onReset,
}: {
  filters: FiltersState;
  distinct: DistinctOptions;
  visibleCount: number;
  totalCount: number;
  hasFilters: boolean;
  onChange: (f: FiltersState) => void;
  onReset: () => void;
}) {
  return (
    <Card className="sticky top-0 z-20 px-4 py-3">
      <div className="flex flex-wrap items-center gap-3">
        {/* Search */}
        <div className="relative max-w-xs flex-1">
          <Search
            className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <input
            type="text"
            placeholder="Cerca turno (es. G-FIO-001)"
            value={filters.search}
            onChange={(e) => onChange({ ...filters, search: e.target.value })}
            className="w-full rounded-md border border-border bg-background py-1.5 pl-8 pr-3 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            aria-label="Cerca turno"
          />
        </div>

        <div className="hidden h-6 w-px bg-border sm:block" />

        {/* Sede */}
        <FilterSelect
          label="Sede"
          value={filters.sede}
          options={distinct.sedi}
          onChange={(v) => onChange({ ...filters, sede: v })}
        />

        {/* Materiale */}
        <FilterSelect
          label="Materiale"
          value={filters.materiale}
          options={distinct.materiali}
          onChange={(v) => onChange({ ...filters, materiale: v })}
        />

        {/* Motivo */}
        <FilterSelect
          label="Motivo"
          value={filters.motivo}
          options={distinct.motivi}
          onChange={(v) => onChange({ ...filters, motivo: v })}
        />

        <div className="hidden h-6 w-px bg-border sm:block" />

        {/* Toggle solo non chiusi */}
        <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-foreground">
          <input
            type="checkbox"
            checked={filters.soloNonChiusi}
            onChange={(e) => onChange({ ...filters, soloNonChiusi: e.target.checked })}
            className="h-4 w-4 rounded border-border accent-primary"
          />
          Solo non chiusi
        </label>

        {hasFilters && (
          <button
            type="button"
            onClick={onReset}
            className="ml-auto text-xs text-muted-foreground underline hover:text-foreground"
          >
            Azzera filtri
          </button>
        )}
      </div>

      <div className="mt-2.5 flex items-center justify-between border-t border-border pt-2.5 text-xs text-muted-foreground">
        <div>
          Mostro <span className="font-medium tabular-nums text-foreground">{visibleCount}</span> di{" "}
          <span className="font-medium tabular-nums text-foreground">{totalCount}</span> giri
          {hasFilters && (
            <>
              <span className="mx-2 text-border">·</span>
              <span className="text-primary">filtri attivi</span>
            </>
          )}
        </div>
        <div className="text-muted-foreground/80">
          Ordina per <span className="font-medium text-foreground">Turno ↑</span>
        </div>
      </div>
    </Card>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  const isActive = value !== "";
  return (
    <label
      className={cn(
        "inline-flex cursor-pointer items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm transition",
        isActive
          ? "border-primary/50 bg-primary/5 text-primary"
          : "border-border bg-white text-foreground hover:bg-muted",
      )}
    >
      <span>{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="cursor-pointer border-0 bg-transparent text-xs focus:outline-none"
        aria-label={label}
      >
        <option value="">Tutti</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  );
}

// =====================================================================
// Table
// =====================================================================

function GiriTable({
  giri,
  selectedId,
  onSelect,
  onOpenFull,
  onGeneraPdc,
}: {
  giri: GiroListItem[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onOpenFull: (id: number) => void;
  onGeneraPdc: (id: number) => void;
}) {
  return (
    <table className="w-full text-sm">
      <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
        <tr>
          <th className="w-14 px-3 py-2.5 text-left font-medium">ID</th>
          <th className="px-3 py-2.5 text-left font-medium">Turno ↑</th>
          <th className="px-3 py-2.5 text-left font-medium">Materiale</th>
          <th className="px-3 py-2.5 text-left font-medium">Sede</th>
          <th className="px-3 py-2.5 text-right font-medium">Gg</th>
          <th className="px-3 py-2.5 text-right font-medium">km/g</th>
          <th className="px-3 py-2.5 text-right font-medium">km/anno</th>
          <th className="px-3 py-2.5 text-left font-medium">Chiusura</th>
          <th className="px-3 py-2.5 text-left font-medium">Creato</th>
          {/* Sprint 7.9 MR η.1 — colonna azioni */}
          <th className="px-3 py-2.5 text-right font-medium">Azioni</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-border">
        {giri.map((g) => (
          <GiroRow
            key={g.id}
            giro={g}
            selected={g.id === selectedId}
            onSelect={() => onSelect(g.id)}
            onOpenFull={() => onOpenFull(g.id)}
            onGeneraPdc={() => onGeneraPdc(g.id)}
          />
        ))}
      </tbody>
    </table>
  );
}

function GiroRow({
  giro,
  selected,
  onSelect,
  onOpenFull,
  onGeneraPdc,
}: {
  giro: GiroListItem;
  selected: boolean;
  onSelect: () => void;
  onOpenFull: () => void;
  onGeneraPdc: () => void;
}) {
  const sede = parseSede(giro.numero_turno) ?? "—";
  const matCode = giro.materiale_tipo_codice ?? giro.tipo_materiale;
  return (
    <tr
      className={cn(
        "cursor-pointer transition-colors",
        selected
          ? "bg-primary/5 shadow-[inset_3px_0_0_0_theme(colors.primary.DEFAULT)]"
          : "hover:bg-muted/30",
      )}
      onClick={onSelect}
      onDoubleClick={onOpenFull}
      data-testid={`giro-row-${giro.id}`}
    >
      <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground">{giro.id}</td>
      <td className="px-3 py-2.5 font-mono text-[13px] font-medium text-foreground">
        {giro.numero_turno}
      </td>
      <td className="px-3 py-2.5">
        <span className="inline-flex items-center rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-foreground">
          {matCode}
        </span>
      </td>
      <td className="px-3 py-2.5 font-mono text-xs text-foreground">{sede}</td>
      <td className="px-3 py-2.5 text-right text-foreground tabular-nums">{giro.numero_giornate}</td>
      <td className="px-3 py-2.5 text-right text-foreground tabular-nums">
        {giro.km_media_giornaliera !== null
          ? formatNumber(Math.round(giro.km_media_giornaliera))
          : "—"}
      </td>
      <td className="px-3 py-2.5 text-right text-muted-foreground tabular-nums">
        {giro.km_media_annua !== null ? formatNumber(Math.round(giro.km_media_annua)) : "—"}
      </td>
      <td className="px-3 py-2.5">
        <ChiusuraTag motivo={giro.motivo_chiusura} chiuso={giro.chiuso} />
      </td>
      <td className="px-3 py-2.5 text-xs text-muted-foreground">{relativeShort(giro.created_at)}</td>
      <td className="px-3 py-2.5 text-right">
        <Button
          variant="primary"
          size="sm"
          onClick={(e) => {
            e.stopPropagation();
            onGeneraPdc();
          }}
          title="Genera turno PdC da questo giro materiale"
        >
          <Users className="mr-1.5 h-3.5 w-3.5" aria-hidden /> Genera PdC
        </Button>
      </td>
    </tr>
  );
}

function ChiusuraTag({ motivo, chiuso }: { motivo: string | null; chiuso: boolean }) {
  if (!chiuso) {
    return (
      <span className="inline-flex items-center rounded bg-destructive/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-destructive">
        non chiuso
      </span>
    );
  }
  if (motivo === "naturale") {
    return (
      <span className="inline-flex items-center rounded bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-800">
        naturale
      </span>
    );
  }
  if (motivo === null) {
    return (
      <span className="inline-flex items-center rounded bg-muted px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        —
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded border border-border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-foreground">
      {motivo}
    </span>
  );
}

// =====================================================================
// Preview pane
// =====================================================================

function PreviewPane({
  giroId,
  onClose,
  onOpenFull,
}: {
  giroId: number;
  onClose: () => void;
  onOpenFull: () => void;
}) {
  const dettaglio = useGiroDettaglio(giroId);

  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
          Anteprima giro
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-muted-foreground hover:text-foreground"
          title="Chiudi anteprima"
          aria-label="Chiudi anteprima"
        >
          <X className="h-4 w-4" aria-hidden />
        </button>
      </div>

      <div className="p-5">
        {dettaglio.isLoading ? (
          <div className="grid place-items-center py-10">
            <Spinner label="Caricamento" />
          </div>
        ) : dettaglio.isError ? (
          <p className="text-sm text-destructive">
            Impossibile caricare il giro. Riprova.
          </p>
        ) : dettaglio.data === undefined ? (
          <p className="text-sm text-muted-foreground">Giro non trovato.</p>
        ) : (
          <PreviewContent giro={dettaglio.data} onOpenFull={onOpenFull} />
        )}
      </div>
    </Card>
  );
}

function PreviewContent({ giro, onOpenFull }: { giro: GiroDettaglio; onOpenFull: () => void }) {
  const matCode = giro.materiale_tipo_codice ?? giro.tipo_materiale;
  const meta = giro.generation_metadata_json;
  const motivo = (typeof meta.motivo_chiusura === "string" ? meta.motivo_chiusura : null);
  const chiuso = typeof meta.chiuso === "boolean" ? meta.chiuso : motivo === "naturale";
  const kmAnnoK =
    giro.km_media_annua !== null ? `${Math.round(giro.km_media_annua / 1000)}k` : "—";

  return (
    <>
      <div className="mb-2 flex items-center gap-2">
        <span className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
          #{giro.id}
        </span>
      </div>
      <h3 className="mb-3 font-mono text-base font-semibold text-foreground">
        {giro.numero_turno}
      </h3>

      <div className="mb-5 flex flex-wrap gap-1.5">
        <span className="inline-flex items-center rounded bg-muted px-2 py-0.5 font-mono text-[10px] text-foreground">
          {matCode}
        </span>
        <ChiusuraTag motivo={motivo} chiuso={chiuso} />
      </div>

      <div className="mb-4 grid grid-cols-3 gap-3 border-b border-border pb-4">
        <PreviewKpi label="Giornate" value={String(giro.numero_giornate)} />
        <PreviewKpi
          label="km/giorno"
          value={
            giro.km_media_giornaliera !== null
              ? formatNumber(Math.round(giro.km_media_giornaliera))
              : "—"
          }
        />
        <PreviewKpi label="km/anno" value={kmAnnoK} />
      </div>

      {/* Sequenza giornate (mini-Gantt placeholder) */}
      <div className="mb-2 text-[10px] uppercase tracking-wide text-muted-foreground">
        Sequenza giornate
      </div>
      <div className="mb-5 space-y-1.5">
        {giro.giornate.map((g) => (
          <GiornataMiniBar key={g.id} giornata={g} />
        ))}
      </div>

      {/* Legend */}
      <div className="mb-5 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
        <LegendDot color="bg-blue-600" label="commerciale" />
        <LegendDot color="bg-gray-300" label="vuoto" />
        <LegendDot color="bg-purple-500" label="rientro" />
        <LegendDot color="bg-orange-300" label="accessori" />
        <LegendDot color="border border-border" label="sosta" />
      </div>

      <Button variant="primary" onClick={onOpenFull} className="w-full">
        Apri Gantt completo <ArrowRight className="ml-2 h-3.5 w-3.5" aria-hidden />
      </Button>
      <p className="mt-2 text-center text-[11px] text-muted-foreground">
        Doppio-click sulla riga per aprire direttamente.
      </p>
    </>
  );
}

function PreviewKpi({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="text-xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className={cn("inline-block h-2.5 w-2.5", color)} />
      {label}
    </span>
  );
}

/**
 * Mini-bar singola giornata: riga con segmenti colorati per tipo blocco,
 * larghezza proporzionale alla durata. Placeholder visuale del Gantt
 * completo (schermata 5).
 */
function GiornataMiniBar({ giornata }: { giornata: GiroGiornata }) {
  // Usa la prima variante (canonica) per il render. Il giro multi-variante
  // verrà sviluppato in screen 5.
  const variant = giornata.varianti[0];
  if (variant === undefined || variant.blocchi.length === 0) {
    return (
      <div className="flex items-center gap-2">
        <span className="w-8 font-mono text-[10px] text-muted-foreground">G{giornata.numero_giornata}</span>
        <div className="h-3 flex-1 rounded-sm bg-muted/50" />
      </div>
    );
  }

  const segments = computeMiniBarSegments(variant.blocchi);

  return (
    <div className="flex items-center gap-2">
      <span className="w-8 font-mono text-[10px] text-muted-foreground">
        G{giornata.numero_giornata}
      </span>
      <div className="flex h-3 flex-1 overflow-hidden rounded-sm bg-muted/50">
        {segments.map((s, i) => (
          <div
            key={i}
            className={cn("h-full", s.cls)}
            style={{ width: `${s.widthPct}%` }}
            title={s.title}
          />
        ))}
      </div>
    </div>
  );
}

interface MiniBarSegment {
  cls: string;
  widthPct: number;
  title: string;
}

function computeMiniBarSegments(blocchi: GiroBlocco[]): MiniBarSegment[] {
  // Calcolo grezzo: distribuzione uniforme se non riusciamo a parsare orari.
  const items = blocchi.map((b) => {
    const dur = parseDurationMin(b.ora_inizio, b.ora_fine);
    return { dur: dur ?? 1, blocco: b };
  });
  const total = items.reduce((s, x) => s + x.dur, 0);
  if (total === 0) {
    const w = 100 / Math.max(1, blocchi.length);
    return blocchi.map((b) => ({
      cls: classForBlocco(b),
      widthPct: w,
      title: blocco_title(b),
    }));
  }
  return items.map(({ dur, blocco }) => ({
    cls: classForBlocco(blocco),
    widthPct: (dur / total) * 100,
    title: blocco_title(blocco),
  }));
}

function parseDurationMin(start: string | null, end: string | null): number | null {
  if (start === null || end === null) return null;
  const sm = start.match(/(\d{2}):(\d{2})/);
  const em = end.match(/(\d{2}):(\d{2})/);
  if (sm === null || em === null) return null;
  const a = parseInt(sm[1], 10) * 60 + parseInt(sm[2], 10);
  let b = parseInt(em[1], 10) * 60 + parseInt(em[2], 10);
  if (b < a) b += 24 * 60; // cross-mezzanotte
  return Math.max(1, b - a);
}

function classForBlocco(b: GiroBlocco): string {
  const t = b.tipo_blocco.toLowerCase();
  if (t.includes("vuoto")) return "bg-gray-300";
  if (t.includes("rientro") || t === "rientro_sede") return "bg-purple-500";
  if (t.includes("accessori") || t === "accp" || t === "acca") return "bg-orange-300";
  if (t.includes("sosta") || t === "pk") return "border-r border-border bg-white";
  // commerciale è il default
  return "bg-primary";
}

function blocco_title(b: GiroBlocco): string {
  const tipo = b.tipo_blocco;
  const num = b.numero_treno ?? "";
  const da = b.stazione_da_codice ?? "";
  const a = b.stazione_a_codice ?? "";
  return `${tipo}${num !== "" ? " " + num : ""}${da !== "" ? ` ${da}→${a}` : ""}`.trim();
}

// =====================================================================
// Empty / error / utils
// =====================================================================

function EmptyState({ programmaId }: { programmaId: number }) {
  return (
    <Card className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <h2 className="text-base font-semibold">Nessun giro generato</h2>
      <p className="max-w-md text-sm text-muted-foreground">
        Per generare i giri torna al dettaglio programma e clicca{" "}
        <strong>"Genera giri"</strong>. Il programma deve essere in stato{" "}
        <em>attivo</em> e avere almeno una regola di assegnazione.
      </p>
      <Link
        to={`/pianificatore-giro/programmi/${programmaId}`}
        className="inline-flex items-center gap-2 rounded-md border border-border bg-white px-3.5 py-2 text-sm text-foreground hover:bg-muted"
      >
        Apri dettaglio programma <ArrowRight className="h-4 w-4" aria-hidden />
      </Link>
    </Card>
  );
}

function FilteredEmptyState({ onReset }: { onReset: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
      <p className="text-sm text-muted-foreground">
        Nessun giro corrisponde ai filtri attivi.
      </p>
      <Button variant="ghost" size="sm" onClick={onReset}>
        Azzera filtri
      </Button>
    </div>
  );
}

function ErrorBlock({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-4"
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

function relativeShort(iso: string): string {
  const date = new Date(iso);
  const diffMin = Math.round((Date.now() - date.getTime()) / 60_000);
  if (diffMin < 1) return "ora";
  if (diffMin < 60) return `${diffMin} min fa`;
  const diffH = Math.round(diffMin / 60);
  if (diffH < 24) return `${diffH} h fa`;
  const diffD = Math.round(diffH / 24);
  if (diffD === 1) return "ieri";
  if (diffD < 7) return `${diffD} g fa`;
  // fallback DD/MM
  return `${String(date.getDate()).padStart(2, "0")}/${String(date.getMonth() + 1).padStart(2, "0")}`;
}
