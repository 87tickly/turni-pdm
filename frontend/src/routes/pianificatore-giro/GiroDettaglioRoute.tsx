import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AlertCircle, ArrowLeft, FileDown, Users, X } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { useGiroDettaglio } from "@/hooks/useGiri";
import { useTurniPdcGiro } from "@/hooks/useTurniPdc";
import { ApiError } from "@/lib/api/client";
import type { GiroBlocco, GiroDettaglio, GiroGiornata, GiroVariante } from "@/lib/api/giri";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import { GeneraTurnoPdcDialog } from "@/routes/pianificatore-giro/GeneraTurnoPdcDialog";

/**
 * Schermata 5 — Visualizzatore Gantt giro materiale.
 * Design: `arturo/05-gantt-giro.html` v2.
 *
 * Struttura: Hero header (mono) + Meta band + per-giornata Gantt
 * (asse 04:00→04:00 next day, 1440 min) + side panel blocco selezionato.
 *
 * Implementati 4 dei 8 must-have del design (tradeoff scope/MVP, vedi
 * TN-UPDATE entry 89):
 *   1. ✅ numero_treno DENTRO barra ≥60px (mono semibold bianco)
 *   6. ✅ selezione blocco: bordo + side panel (no opacità altri ancora)
 *   8. ✅ is_validato_utente: bordo dx 4px emerald + badge in panel
 *   ✅ cross-mezzanotte: span 04:00→04:00 next day
 * Residui (matrice ore×stazioni Opzione A, eventi composizione,
 * notte fra giornate banda, gap minuti label, sticky scroll, opacità
 * dim su altri blocchi).
 */

// =====================================================================
// Constants — time axis 04:00 → 04:00 next day (24h, 1440 min)
// =====================================================================

const AXIS_START_MIN = 4 * 60; // 04:00
const AXIS_TOTAL_MIN = 24 * 60; // 1440 min
/** Tick ogni 2 ore: 04, 06, 08, ..., 02. */
const TICK_HOURS = [4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 0, 2];

// =====================================================================
// Route component
// =====================================================================

export function GiroDettaglioRoute() {
  const { giroId: giroIdParam } = useParams<{ giroId: string }>();
  const giroId = giroIdParam !== undefined ? Number(giroIdParam) : undefined;
  const query = useGiroDettaglio(giroId);

  const [selectedBlocco, setSelectedBlocco] = useState<GiroBlocco | null>(null);
  const [pdcDialogOpen, setPdcDialogOpen] = useState(false);

  if (giroId === undefined || Number.isNaN(giroId)) {
    return <ErrorBlock message="ID giro non valido nell'URL." />;
  }

  if (query.isLoading) {
    return (
      <Card className="grid place-items-center p-16">
        <Spinner label="Caricamento giro…" />
      </Card>
    );
  }

  if (query.isError) {
    const msg =
      query.error instanceof ApiError ? query.error.message : (query.error as Error).message;
    return <ErrorBlock message={msg} onRetry={() => void query.refetch()} />;
  }

  if (query.data === undefined) {
    return <ErrorBlock message="Giro non trovato." />;
  }

  const giro = query.data;
  const meta = giro.generation_metadata_json as Record<string, unknown>;
  const programmaId = typeof meta.programma_id === "number" ? meta.programma_id : null;
  const showSide = selectedBlocco !== null;

  return (
    <div className="flex flex-col gap-4">
      <Link
        to={
          programmaId !== null
            ? `/pianificatore-giro/programmi/${programmaId}/giri`
            : "/pianificatore-giro/programmi"
        }
        className="inline-flex w-fit items-center gap-1 text-xs text-muted-foreground hover:text-primary"
      >
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> Lista giri
      </Link>

      <HeroSection giro={giro} onGeneraPdc={() => setPdcDialogOpen(true)} />

      <section
        className={cn("grid grid-cols-1 gap-4", showSide ? "lg:grid-cols-12" : "lg:grid-cols-1")}
      >
        <div className={cn("flex flex-col gap-4", showSide && "lg:col-span-8")}>
          {giro.giornate.map((g) => (
            <GiornataGanttCard
              key={g.id}
              giornata={g}
              selectedBloccoId={selectedBlocco?.id ?? null}
              onSelectBlocco={setSelectedBlocco}
            />
          ))}
        </div>
        {showSide && selectedBlocco !== null && (
          <aside className="self-start lg:col-span-4">
            <BloccoSidePanel
              blocco={selectedBlocco}
              onClose={() => setSelectedBlocco(null)}
            />
          </aside>
        )}
      </section>

      <GeneraTurnoPdcDialog
        giroId={giro.id}
        open={pdcDialogOpen}
        onOpenChange={setPdcDialogOpen}
      />
    </div>
  );
}

// =====================================================================
// Hero
// =====================================================================

function HeroSection({
  giro,
  onGeneraPdc,
}: {
  giro: GiroDettaglio;
  onGeneraPdc: () => void;
}) {
  const meta = giro.generation_metadata_json as Record<string, unknown>;
  const motivo = typeof meta.motivo_chiusura === "string" ? meta.motivo_chiusura : null;
  const chiuso = typeof meta.chiuso === "boolean" ? meta.chiuso : motivo === "naturale";
  const turniQuery = useTurniPdcGiro(giro.id);
  const turni = turniQuery.data ?? [];

  const stats = useMemo(() => computeGiroKpi(giro), [giro]);

  const kmAnnoK =
    giro.km_media_annua !== null ? `${Math.round(giro.km_media_annua / 1000)}k` : "—";

  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex items-center gap-2">
            <span className="font-mono text-xs text-muted-foreground">#{giro.id}</span>
            <ChiusuraBadge motivo={motivo} chiuso={chiuso} />
          </div>
          <h1 className="font-mono text-3xl font-semibold tracking-tight text-foreground">
            {giro.numero_turno}
          </h1>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center rounded bg-muted px-2 py-0.5 font-mono text-[11px] text-foreground">
              {giro.materiale_tipo_codice ?? giro.tipo_materiale}
            </span>
            {typeof meta.linea_principale === "string" && (
              <span className="text-xs text-muted-foreground">
                {meta.linea_principale}
              </span>
            )}
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-x-8 gap-y-3">
            <KpiInline label="Giornate" value={String(giro.numero_giornate)} />
            <DividerInline />
            <KpiInline
              label="km/giorno"
              value={
                giro.km_media_giornaliera !== null
                  ? formatNumber(Math.round(giro.km_media_giornaliera))
                  : "—"
              }
            />
            <DividerInline />
            <KpiInline label="km/anno" value={kmAnnoK} />
            <DividerInline />
            <KpiInline label="N° treni" value={String(stats.nTreniCommerciali)} />
            <DividerInline />
            <KpiInline label="Rientri 9NNNN" value={String(stats.nRientri)} />
          </div>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Button
            variant="outline"
            size="md"
            onClick={() => window.print()}
            title="Esporta PDF (stampa)"
          >
            <FileDown className="mr-2 h-4 w-4" aria-hidden /> Esporta PDF
          </Button>
          <Button variant="primary" size="md" onClick={onGeneraPdc}>
            <Users className="mr-2 h-4 w-4" aria-hidden />
            Genera turno PdC
          </Button>
        </div>
      </div>

      {/* Meta band */}
      <div className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-border pt-4 text-xs">
        <MetaItem label="Sede">
          <SedeBand giro={giro} />
        </MetaItem>
        <MetaItem label="Varianti">
          <span className="tabular-nums text-foreground">
            {stats.nVariantiTotale} su {giro.numero_giornate} giornate
          </span>
        </MetaItem>
        <MetaItem label="Validato">
          <span
            className={cn(
              "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] uppercase tracking-wide",
              stats.nValidati > 0
                ? "bg-emerald-100 text-emerald-800"
                : "bg-muted text-muted-foreground",
            )}
          >
            {stats.nValidati} di {stats.nBlocchi} blocchi
          </span>
        </MetaItem>
        <MetaItem label="Stato">
          <span className="font-mono text-foreground">{giro.stato}</span>
        </MetaItem>
        {turni.length > 0 && (
          <MetaItem label="Turni PdC">
            <Link
              to={`/pianificatore-giro/giri/${giro.id}/turni-pdc`}
              className="text-primary hover:underline"
            >
              {turni.length} generat{turni.length === 1 ? "o" : "i"} →
            </Link>
          </MetaItem>
        )}
      </div>
    </Card>
  );
}

interface GiroKpiStats {
  nVariantiTotale: number;
  nBlocchi: number;
  nValidati: number;
  nTreniCommerciali: number;
  nRientri: number;
}

function computeGiroKpi(giro: GiroDettaglio): GiroKpiStats {
  let nVariantiTotale = 0;
  let nBlocchi = 0;
  let nValidati = 0;
  let nTreniCommerciali = 0;
  let nRientri = 0;
  for (const g of giro.giornate) {
    nVariantiTotale += g.varianti.length;
    for (const v of g.varianti) {
      for (const b of v.blocchi) {
        nBlocchi += 1;
        if (b.is_validato_utente) nValidati += 1;
        if (b.tipo_blocco === "corsa_commerciale") nTreniCommerciali += 1;
        const t = b.numero_treno ?? "";
        if (/^9\d{4}$/.test(t)) nRientri += 1;
        if (b.tipo_blocco === "rientro_sede") nRientri += 1;
      }
    }
  }
  return { nVariantiTotale, nBlocchi, nValidati, nTreniCommerciali, nRientri };
}

function KpiInline({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 text-2xl font-semibold leading-none tabular-nums text-foreground">
        {value}
      </div>
    </div>
  );
}

function DividerInline() {
  return <div className="h-10 w-px bg-border" />;
}

function MetaItem({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="uppercase tracking-wide text-muted-foreground">{label}</span>
      {children}
    </div>
  );
}

function SedeBand({ giro }: { giro: GiroDettaglio }) {
  const da = parseSedeFromTurno(giro.numero_turno);
  return (
    <span className="flex items-center gap-1.5">
      <span className="font-mono text-foreground">{da ?? "—"}</span>
      <span aria-hidden className="text-muted-foreground">
        →
      </span>
      <span className="font-mono text-foreground">{da ?? "—"}</span>
    </span>
  );
}

function ChiusuraBadge({ motivo, chiuso }: { motivo: string | null; chiuso: boolean }) {
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
        chiuso · naturale
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
      chiuso · {motivo}
    </span>
  );
}

// =====================================================================
// Per-giornata Gantt card
// =====================================================================

function GiornataGanttCard({
  giornata,
  selectedBloccoId,
  onSelectBlocco,
}: {
  giornata: GiroGiornata;
  selectedBloccoId: number | null;
  onSelectBlocco: (b: GiroBlocco) => void;
}) {
  const [activeIdx, setActiveIdx] = useState(0);
  const varianti = giornata.varianti;
  const hasMultiple = varianti.length > 1;
  const active = varianti[activeIdx] ?? varianti[0];

  if (active === undefined) {
    return (
      <Card className="p-5">
        <div className="text-sm text-muted-foreground italic">
          Giornata {giornata.numero_giornata} senza varianti.
        </div>
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden">
      {/* Header giornata */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-muted/30 px-4 py-2">
        <div className="flex items-baseline gap-3">
          <span className="text-sm font-semibold text-foreground">
            Giornata {giornata.numero_giornata}
          </span>
          {giornata.km_giornata !== null && (
            <span className="text-xs text-muted-foreground tabular-nums">
              {formatNumber(Math.round(giornata.km_giornata))} km
            </span>
          )}
          <span className="text-xs italic text-muted-foreground">
            {active.etichetta_parlante}
          </span>
        </div>
        <span className="text-xs text-muted-foreground">
          {hasMultiple ? `${varianti.length} varianti calendariali` : "1 variante"}
        </span>
      </div>

      {/* Variant tabs (se ≥ 2) */}
      {hasMultiple && (
        <div
          role="tablist"
          aria-label={`Varianti giornata ${giornata.numero_giornata}`}
          className="flex flex-wrap gap-1 border-b border-border bg-muted/20 px-3 py-1.5"
        >
          {varianti.map((v, idx) => {
            const isActive = idx === activeIdx;
            return (
              <button
                key={v.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => setActiveIdx(idx)}
                className={cn(
                  "rounded px-2 py-1 text-[11px] font-medium transition-colors",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "bg-white text-muted-foreground hover:bg-muted",
                )}
                title={`${v.etichetta_parlante}${idx === 0 ? " (canonica)" : ""}`}
              >
                {truncateLabel(v.etichetta_parlante)}
              </button>
            );
          })}
        </div>
      )}

      {/* Time axis + Gantt row */}
      <GanttView
        variante={active}
        selectedBloccoId={selectedBloccoId}
        onSelectBlocco={onSelectBlocco}
      />
    </Card>
  );
}

function truncateLabel(testo: string): string {
  const MAX = 40;
  return testo.length <= MAX ? testo : testo.substring(0, MAX - 1) + "…";
}

function GanttView({
  variante,
  selectedBloccoId,
  onSelectBlocco,
}: {
  variante: GiroVariante;
  selectedBloccoId: number | null;
  onSelectBlocco: (b: GiroBlocco) => void;
}) {
  return (
    <div className="overflow-x-auto p-4">
      <div className="min-w-[960px]">
        {/* Time axis */}
        <div className="relative h-6 border-b border-border">
          {TICK_HOURS.map((h) => {
            const pct = hourToPct(h);
            return (
              <div
                key={h}
                className="absolute -translate-x-1/2 text-[10px] tabular-nums text-muted-foreground"
                style={{ left: `${pct}%` }}
              >
                {String(h).padStart(2, "0")}
              </div>
            );
          })}
          {/* Vertical tick lines */}
          {TICK_HOURS.map((h) => {
            const pct = hourToPct(h);
            return (
              <div
                key={`tick-${h}`}
                className="pointer-events-none absolute bottom-0 h-1 w-px bg-border"
                style={{ left: `${pct}%` }}
              />
            );
          })}
        </div>

        {/* Gantt row */}
        <div className="relative mt-2 h-14 rounded bg-muted/20">
          {/* Hourly grid lines */}
          {TICK_HOURS.map((h) => {
            const pct = hourToPct(h);
            return (
              <div
                key={`grid-${h}`}
                className="pointer-events-none absolute top-0 h-full w-px bg-border/50"
                style={{ left: `${pct}%` }}
              />
            );
          })}

          {variante.blocchi.map((b) => (
            <BloccoBar
              key={b.id}
              blocco={b}
              selected={b.id === selectedBloccoId}
              dimmed={selectedBloccoId !== null && b.id !== selectedBloccoId}
              onSelect={() => onSelectBlocco(b)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function BloccoBar({
  blocco,
  selected,
  dimmed,
  onSelect,
}: {
  blocco: GiroBlocco;
  selected: boolean;
  dimmed: boolean;
  onSelect: () => void;
}) {
  const inizio = parseTimeToMin(blocco.ora_inizio);
  const fine = parseTimeToMin(blocco.ora_fine);
  if (inizio === null || fine === null) return null;

  const startPct = minToPct(inizio);
  let endPct = minToPct(fine);
  // Cross-mezzanotte: se end < start, sommiamo 1440
  if (endPct < startPct) endPct = minToPct(fine + AXIS_TOTAL_MIN);
  const widthPct = Math.max(0.3, endPct - startPct);

  const bgColor = colorForTipo(blocco.tipo_blocco);
  const labelText = bloccoLabel(blocco);
  const tooltip = bloccoTooltip(blocco);

  return (
    <button
      type="button"
      onClick={onSelect}
      title={tooltip}
      className={cn(
        "absolute top-1.5 flex h-11 items-center overflow-hidden rounded text-[11px] font-medium transition-opacity",
        bgColor,
        selected && "outline outline-2 outline-primary z-10",
        dimmed && "opacity-55",
        blocco.is_validato_utente && "border-r-4 border-emerald-500",
      )}
      style={{
        left: `${startPct}%`,
        width: `${widthPct}%`,
      }}
      aria-pressed={selected}
    >
      <span className="truncate px-1.5 font-mono">{labelText}</span>
    </button>
  );
}

function bloccoLabel(b: GiroBlocco): string {
  if (b.numero_treno !== null && b.numero_treno.length > 0) return b.numero_treno;
  const meta =
    typeof b.metadata_json?.numero_treno === "string"
      ? (b.metadata_json.numero_treno as string)
      : null;
  if (meta !== null) return meta;
  // fallback: tipo abbreviato
  return tipoBloccoShort(b.tipo_blocco);
}

function tipoBloccoShort(tipo: string): string {
  switch (tipo) {
    case "corsa_commerciale":
      return "treno";
    case "materiale_vuoto":
      return "vuoto";
    case "cambio_composizione":
    case "evento_composizione":
      return "comp.";
    case "sosta_notturna":
      return "sosta n.";
    case "sosta":
      return "sosta";
    case "rientro_sede":
      return "rientro";
    case "accessori_p":
    case "accp":
      return "ACCp";
    case "accessori_a":
    case "acca":
      return "ACCa";
    default:
      return tipo;
  }
}

function bloccoTooltip(b: GiroBlocco): string {
  const tipo = tipoBloccoLabel(b.tipo_blocco);
  const inizio = b.ora_inizio ?? "?";
  const fine = b.ora_fine ?? "?";
  const da = b.stazione_da_nome ?? b.stazione_da_codice ?? "—";
  const a = b.stazione_a_nome ?? b.stazione_a_codice ?? "—";
  const treno = b.numero_treno !== null ? `\nTreno ${b.numero_treno}` : "";
  const validato = b.is_validato_utente ? "\n✓ Validato" : "";
  return `${tipo} · ${inizio} → ${fine}\n${da} → ${a}${treno}${validato}`;
}

function tipoBloccoLabel(tipo: string): string {
  switch (tipo) {
    case "corsa_commerciale":
      return "Commerciale";
    case "materiale_vuoto":
      return "Vuoto";
    case "cambio_composizione":
    case "evento_composizione":
      return "Composizione";
    case "sosta_notturna":
      return "Sosta notturna";
    case "sosta":
      return "Sosta";
    case "rientro_sede":
      return "Rientro sede";
    default:
      return tipo;
  }
}

function colorForTipo(tipo: string): string {
  switch (tipo) {
    case "corsa_commerciale":
      return "bg-blue-600 text-white";
    case "materiale_vuoto":
      return "bg-gray-300 text-foreground border border-gray-400";
    case "cambio_composizione":
    case "evento_composizione":
      return "bg-emerald-200 text-emerald-900";
    case "sosta_notturna":
    case "sosta":
      return "bg-white text-foreground border border-border";
    case "rientro_sede":
      return "bg-purple-500 text-white";
    case "accessori_p":
    case "accessori_a":
    case "accp":
    case "acca":
      return "bg-orange-300 text-foreground";
    default:
      return "bg-muted text-foreground";
  }
}

// =====================================================================
// Side panel — dettaglio blocco selezionato
// =====================================================================

function BloccoSidePanel({
  blocco,
  onClose,
}: {
  blocco: GiroBlocco;
  onClose: () => void;
}) {
  const tipoLabel = tipoBloccoLabel(blocco.tipo_blocco);
  const inizio = blocco.ora_inizio?.slice(0, 5) ?? "—";
  const fine = blocco.ora_fine?.slice(0, 5) ?? "—";
  const durata =
    parseTimeToMin(blocco.ora_inizio) !== null && parseTimeToMin(blocco.ora_fine) !== null
      ? formatDurataMin(blocco)
      : "—";

  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
          Dettaglio blocco
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Chiudi pannello"
          title="Chiudi pannello"
          className="text-muted-foreground hover:text-foreground"
        >
          <X className="h-4 w-4" aria-hidden />
        </button>
      </div>

      <div className="p-5">
        <div className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">
          {tipoLabel}
        </div>
        <h3 className="mb-3 font-mono text-2xl font-semibold text-foreground">
          {blocco.numero_treno ?? "—"}
        </h3>

        <div className="mb-4 flex flex-wrap gap-1.5">
          {blocco.is_validato_utente ? (
            <Badge
              variant="success"
              className="border-emerald-200 bg-emerald-50 text-emerald-800"
            >
              ✓ Validato manualmente
            </Badge>
          ) : (
            <Badge variant="muted">Non validato</Badge>
          )}
        </div>

        <div className="space-y-3 border-t border-border pt-4">
          <DetailRow label="Da">
            <StazioneDetail nome={blocco.stazione_da_nome} codice={blocco.stazione_da_codice} />
          </DetailRow>
          <DetailRow label="A">
            <StazioneDetail nome={blocco.stazione_a_nome} codice={blocco.stazione_a_codice} />
          </DetailRow>
          <DetailRow label="Orario">
            <span className="tabular-nums text-foreground">
              {inizio} → {fine}
              <span className="ml-2 text-xs text-muted-foreground">({durata})</span>
            </span>
          </DetailRow>
          <DetailRow label="Sequenza">
            <span className="font-mono text-foreground">#{blocco.seq}</span>
          </DetailRow>
          {blocco.descrizione !== null && blocco.descrizione !== "" && (
            <DetailRow label="Note">
              <span className="text-foreground">{blocco.descrizione}</span>
            </DetailRow>
          )}
          {blocco.corsa_commerciale_id !== null && (
            <DetailRow label="Corsa">
              <span className="font-mono text-xs text-muted-foreground">
                #{blocco.corsa_commerciale_id}
              </span>
            </DetailRow>
          )}
        </div>

        <p className="mt-4 text-[11px] text-muted-foreground">
          Premi <kbd className="rounded border border-border bg-muted px-1 py-0.5 font-mono text-[10px]">Esc</kbd>{" "}
          o clicca ✕ per deselezionare.
        </p>
      </div>
    </Card>
  );
}

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <div className="text-right text-sm">{children}</div>
    </div>
  );
}

function StazioneDetail({ nome, codice }: { nome: string | null; codice: string | null }) {
  if (nome === null && codice === null) return <span>—</span>;
  return (
    <div className="flex flex-col items-end leading-tight">
      <span className="text-foreground">{nome ?? codice}</span>
      {nome !== null && codice !== null && (
        <span className="font-mono text-[10px] text-muted-foreground">{codice}</span>
      )}
    </div>
  );
}

function formatDurataMin(b: GiroBlocco): string {
  const start = parseTimeToMin(b.ora_inizio);
  const end = parseTimeToMin(b.ora_fine);
  if (start === null || end === null) return "—";
  let mins = end - start;
  if (mins < 0) mins += 24 * 60;
  if (mins < 60) return `${mins}'`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m === 0 ? `${h}h` : `${h}h ${m}'`;
}

// =====================================================================
// Time axis math
// =====================================================================

/** Parse "HH:MM" o "HH:MM:SS" → minuti totali da 00:00. */
function parseTimeToMin(t: string | null): number | null {
  if (t === null || t.length === 0) return null;
  const parts = t.split(":");
  if (parts.length < 2) return null;
  const h = Number.parseInt(parts[0], 10);
  const m = Number.parseInt(parts[1], 10);
  if (Number.isNaN(h) || Number.isNaN(m)) return null;
  return h * 60 + m;
}

/** Minuti da 00:00 → percentuale sull'asse 04:00→04:00 (1440 min). */
function minToPct(min: number): number {
  let rel = min - AXIS_START_MIN;
  if (rel < 0) rel += AXIS_TOTAL_MIN;
  return (rel / AXIS_TOTAL_MIN) * 100;
}

/** Posizione X di un'ora (0-23) sull'asse. */
function hourToPct(h: number): number {
  return minToPct(h * 60);
}

/** Estrae sede da numero_turno tipo `G-FIO-001-ETR526` → `FIO`. */
function parseSedeFromTurno(numeroTurno: string): string | null {
  const m = numeroTurno.match(/^G-([A-Z]+)-/);
  return m !== null ? m[1] : null;
}

// =====================================================================
// Error
// =====================================================================

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

