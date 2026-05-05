import {
  createContext,
  useContext,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Link, useParams } from "react-router-dom";
import { AlertCircle, ArrowLeft, FileDown, Users, X } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/Popover";
import { Spinner } from "@/components/ui/Spinner";
import { useGiroDettaglio, useThreadsGiro } from "@/hooks/useGiri";
import { useTurniPdcGiro } from "@/hooks/useTurniPdc";
import { ApiError } from "@/lib/api/client";
import type {
  GiroBlocco,
  GiroDettaglio,
  GiroGiornata,
  GiroVariante,
} from "@/lib/api/giri";
import { formatDateIt, formatNumber } from "@/lib/format";
import { stazioneAcronimo } from "@/lib/stazioni-acronimi";
import { cn } from "@/lib/utils";
import { GeneraTurnoPdcDialog } from "@/routes/pianificatore-giro/GeneraTurnoPdcDialog";

/**
 * Schermata 5 v3 — Visualizzatore Gantt giro materiale.
 * Design: `arturo/05-gantt-giro.html` v3 (handoff bundle 2026-05-03).
 *
 * Layout single-line PDF Trenord (NO matrice multi-row): per ogni
 * giornata-variante una sola riga timeline con stazioni come label
 * testo, numero treno dentro il segmento rosso, gap minuti, banda
 * notte fra giornate, eventi composizione marker, side panel destro
 * sul blocco selezionato, sotto-Gantt con date di applicazione.
 *
 * Must-have v2 brief implementati cumulativamente (entry 90, 92, 94, 95):
 *   1. ✅ numero_treno DENTRO barra (mono semibold bianco)
 *   2. ✅ stazioni come label testo verde sopra/sotto i segmenti
 *      (sostituisce la matrice ore × stazioni di entry 92)
 *   3. ✅ gap minuti label + tratteggio se ≥30'
 *   4. ✅ eventi composizione marker arancione 4px (entry 95)
 *   5. ✅ banda notte fra giornate + verifica congruenza stazione
 *      (entry 95)
 *   6. ✅ selezione blocco: outline + side panel + dim altri 55%
 *   7. ✅ sticky scroll: asse X top + Giornata col left + Per/Km dx
 *   8. ✅ is_validato_utente: bordo dx 4px emerald (via .validato)
 *   ✅ cross-mezzanotte: span 04:00→04:00 next day, marker 24:00
 */

// =====================================================================
// Constants — time axis 04:00 → 04:00 next day (24h, 1440 min)
// =====================================================================

const AXIS_START_MIN = 4 * 60; // 04:00 reference
const AXIS_TOTAL_MIN = 24 * 60; // 1440 min

// Sprint 7.9 MR γ (2026-05-04) ha portato il default da 1h=60px a
// 1h=40px (960px totale) per evitare scroll orizzontale su schermi
// ≥1280px. Sprint 7.9 MR δ (2026-05-05): scala parametrizzata via
// `GanttScaleContext`, l'utente sceglie 75/100/150/200% in toolbar
// (default 100% = 960px = scala MR γ). Risolve il troncamento di
// numeri/orari sui giri densi tipo direttrice Tirano (~26 treni/g).
const BASE_TIMELINE_WIDTH_PX = 960;
const GIORNATA_LABEL_COL_PX = 100;
const PER_KM_COL_PX = 120;
const TIMELINE_ROW_HEIGHT_PX = 88;
const NOTTE_ROW_HEIGHT_PX = 24;

const ZOOM_LEVELS = [0.75, 1, 1.5, 2] as const;
type ZoomLevel = (typeof ZOOM_LEVELS)[number];
const DEFAULT_ZOOM: ZoomLevel = 1;
const LS_KEY_GANTT_ZOOM = "colazione.gantt-giro.zoom";

interface GanttScale {
  /** Larghezza totale della timeline in px (24h scalate da zoom). */
  timelineWidthPx: number;
  /** Pixel per ora effettivi (per UI/tick). */
  pxPerHour: number;
  /** Mappa minuti-da-mezzanotte → pixel sull'asse 04:00→04:00. */
  minToPx: (min: number) => number;
}

function _baseMinToPx(min: number, totalWidthPx: number): number {
  let rel = min - AXIS_START_MIN;
  if (rel < 0) rel += AXIS_TOTAL_MIN;
  return (rel / AXIS_TOTAL_MIN) * totalWidthPx;
}

const GanttScaleContext = createContext<GanttScale>({
  timelineWidthPx: BASE_TIMELINE_WIDTH_PX,
  pxPerHour: BASE_TIMELINE_WIDTH_PX / 24,
  minToPx: (min) => _baseMinToPx(min, BASE_TIMELINE_WIDTH_PX),
});

function useGanttScale(): GanttScale {
  return useContext(GanttScaleContext);
}

function readPersistedZoom(): ZoomLevel {
  if (typeof window === "undefined") return DEFAULT_ZOOM;
  const raw = window.localStorage.getItem(LS_KEY_GANTT_ZOOM);
  if (raw === null) return DEFAULT_ZOOM;
  const parsed = Number.parseFloat(raw);
  return (ZOOM_LEVELS as readonly number[]).includes(parsed)
    ? (parsed as ZoomLevel)
    : DEFAULT_ZOOM;
}

function persistZoom(z: ZoomLevel): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(LS_KEY_GANTT_ZOOM, String(z));
}

/** Soglia gap "long" (tratteggio aggiuntivo). */
const GAP_LONG_THRESHOLD = 30;
/** Soglia minima per renderizzare un gap. */
const GAP_MIN_THRESHOLD = 10;
/** Sopra questa soglia il gap è una "notte" (separato in NotteRow). */
const GAP_NIGHT_THRESHOLD = 6 * 60;

// =====================================================================
// Route component
// =====================================================================

export function GiroDettaglioRoute() {
  const { giroId: giroIdParam } = useParams<{ giroId: string }>();
  const giroId = giroIdParam !== undefined ? Number(giroIdParam) : undefined;
  const query = useGiroDettaglio(giroId);

  const [selectedBlocco, setSelectedBlocco] = useState<GiroBlocco | null>(null);
  const [pdcDialogOpen, setPdcDialogOpen] = useState(false);
  /**
   * Per ogni giornata l'utente sceglie quale variante mostrare. Default:
   * indice 0 (canonica). Stato esposto qui per resilienza ai re-render
   * tipo selezione blocco.
   */
  const [activeVariantByGiornata, setActiveVariantByGiornata] = useState<
    Record<number, number>
  >({});
  // Sprint 7.9 MR 8A: insieme di cluster A1 originari attualmente
  // selezionati (intersezione tra le varianti cliccate). Quando
  // l'utente clicca una variante, si traccia la sua lista
  // `cluster_a1_ids`; per ogni altra giornata, la propagazione
  // sceglie la prima variante con intersezione non vuota.
  const [selectedClusterA1Ids, setSelectedClusterA1Ids] = useState<
    Set<number> | null
  >(null);

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
          <GanttSection
            giro={giro}
            selectedBlocco={selectedBlocco}
            onSelectBlocco={setSelectedBlocco}
            activeVariantByGiornata={activeVariantByGiornata}
            selectedClusterA1Ids={selectedClusterA1Ids}
            onChangeActiveVariant={(giornataId, idx) => {
              // Sprint 7.9 MR 8A: propagazione via cluster_a1_ids.
              // Quando l'utente clicca una variante, prendiamo la sua
              // lista `cluster_a1_ids` (= cluster A1 originali pre-MR6).
              // Per ogni altra giornata, troviamo la PRIMA variante
              // che ha intersezione non vuota → stessa traiettoria
              // del convoglio. Le giornate dove nessuna variante
              // condivide cluster A1 con quella selezionata mostrano
              // "ciclo non si estende qui" via il flag clusterEsteso.
              const giornataK = giro.giornate.find((g) => g.id === giornataId);
              const variante = giornataK?.varianti[idx];
              if (variante === undefined) return;
              const targetIds = new Set(variante.cluster_a1_ids);
              setSelectedClusterA1Ids(targetIds);
              setActiveVariantByGiornata((prev) => {
                const next: Record<number, number> = { ...prev, [giornataId]: idx };
                for (const g of giro.giornate) {
                  if (g.id === giornataId) continue;
                  const matchIdx = g.varianti.findIndex((v) =>
                    v.cluster_a1_ids.some((id) => targetIds.has(id)),
                  );
                  if (matchIdx >= 0) next[g.id] = matchIdx;
                }
                return next;
              });
            }}
          />
        </div>

        {showSide && selectedBlocco !== null && (
          <aside className="self-start lg:col-span-4">
            <BloccoSidePanel
              blocco={selectedBlocco}
              giro={giro}
              activeVariantByGiornata={activeVariantByGiornata}
              onClose={() => setSelectedBlocco(null)}
            />
          </aside>
        )}
      </section>

      <DateApplicazioneSection giro={giro} />

      <ConvogliDelTurnoSection giroId={giro.id} />

      <GeneraTurnoPdcDialog
        giroId={giro.id}
        open={pdcDialogOpen}
        onOpenChange={setPdcDialogOpen}
      />
    </div>
  );
}

// =====================================================================
// Sprint 7.9 MR β2-6 — Pannello "Convogli del turno" (thread L2)
// =====================================================================

function ConvogliDelTurnoSection({ giroId }: { giroId: number }) {
  const query = useThreadsGiro(giroId);
  if (query.isLoading) {
    return (
      <Card className="grid place-items-center p-8">
        <Spinner label="Caricamento convogli…" />
      </Card>
    );
  }
  if (query.isError) return null;
  const threads = query.data ?? [];
  return (
    <Card className="overflow-hidden">
      <div className="border-b border-border bg-muted/40 px-4 py-2.5 text-xs">
        <span className="font-medium uppercase tracking-wide text-foreground">
          Convogli del turno (thread L2)
        </span>
        <span className="ml-3 text-muted-foreground">
          {threads.length} pezz{threads.length === 1 ? "o" : "i"} fisic
          {threads.length === 1 ? "o" : "i"} proiettat{threads.length === 1 ? "o" : "i"}
        </span>
      </div>
      {threads.length === 0 ? (
        <div className="p-6 text-center text-sm text-muted-foreground">
          Nessun thread proiettato. Probabile composizione vuota o giro creato
          prima di MR β2-4 — rigenera per popolare.
        </div>
      ) : (
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/20">
            <tr>
              <th className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Materiale
              </th>
              <th className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Matricola
              </th>
              <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                km totali
              </th>
              <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                min servizio
              </th>
              <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                # corse
              </th>
              <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Timeline
              </th>
            </tr>
          </thead>
          <tbody>
            {threads.map((t) => (
              <tr key={t.id} className="border-b border-border/40 hover:bg-muted/20">
                <td className="px-3 py-2 font-mono text-foreground">
                  {t.tipo_materiale_codice}
                </td>
                <td className="px-3 py-2 text-muted-foreground">
                  {t.matricola_id !== null ? `#${t.matricola_id}` : "non assegnata"}
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums">
                  {Math.round(t.km_totali).toLocaleString("it-IT")}
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums">
                  {t.minuti_servizio.toLocaleString("it-IT")}
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums">
                  {t.n_corse_commerciali}
                </td>
                <td className="px-3 py-2 text-right">
                  <Link
                    to={`/pianificatore-giro/thread/${t.id}`}
                    className="text-xs text-primary hover:underline"
                  >
                    Apri →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
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
              <span className="text-xs text-muted-foreground">{meta.linea_principale}</span>
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
            <Users className="mr-2 h-4 w-4" aria-hidden /> Genera turno PdC
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
        <MetaItem label="Turni PdC">
          {turni.length > 0 ? (
            <Link
              to={`/pianificatore-giro/giri/${giro.id}/turni-pdc`}
              className="text-primary hover:underline"
            >
              {turni.length} generat{turni.length === 1 ? "o" : "i"} →
            </Link>
          ) : (
            <span className="text-muted-foreground">non generati</span>
          )}
        </MetaItem>
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
// Gantt section — wrapper sticky-top axis + per-giornata rows + totali
// =====================================================================

function GanttSection({
  giro,
  selectedBlocco,
  onSelectBlocco,
  activeVariantByGiornata,
  selectedClusterA1Ids,
  onChangeActiveVariant,
}: {
  giro: GiroDettaglio;
  selectedBlocco: GiroBlocco | null;
  onSelectBlocco: (b: GiroBlocco | null) => void;
  activeVariantByGiornata: Record<number, number>;
  selectedClusterA1Ids: Set<number> | null;
  onChangeActiveVariant: (giornataId: number, idx: number) => void;
}) {
  const stats = useMemo(() => computeGiroKpi(giro), [giro]);
  const [zoom, setZoom] = useState<ZoomLevel>(() => readPersistedZoom());
  const handleZoomChange = (z: ZoomLevel) => {
    setZoom(z);
    persistZoom(z);
  };

  // Sprint 7.9 MR δ.1 (entry 141): a zoom < 100% la timeline si stira
  // per riempire la viewport disponibile (decisione utente: "al 75% non
  // si riempie la pagina con sidebar chiusa"). A zoom ≥ 100% mantieni
  // scala fissa con scroll orizzontale interno.
  const scrollWrapperRef = useRef<HTMLDivElement | null>(null);
  const [containerWidth, setContainerWidth] = useState<number>(0);
  useLayoutEffect(() => {
    const el = scrollWrapperRef.current;
    if (el === null) return;
    const update = () => setContainerWidth(el.clientWidth);
    update();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const scale = useMemo<GanttScale>(() => {
    const baseWidth = BASE_TIMELINE_WIDTH_PX * zoom;
    const fitWidth =
      containerWidth > 0
        ? Math.max(0, containerWidth - GIORNATA_LABEL_COL_PX - PER_KM_COL_PX)
        : 0;
    const timelineWidthPx = zoom < 1 ? Math.max(baseWidth, fitWidth) : baseWidth;
    return {
      timelineWidthPx,
      pxPerHour: timelineWidthPx / 24,
      minToPx: (min: number) => _baseMinToPx(min, timelineWidthPx),
    };
  }, [zoom, containerWidth]);
  const innerWidth = GIORNATA_LABEL_COL_PX + scale.timelineWidthPx + PER_KM_COL_PX;

  return (
    <GanttScaleContext.Provider value={scale}>
      <Card className={cn("overflow-hidden", selectedBlocco !== null && "gantt-selecting")}>
        {/* Toolbar */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-muted/40 px-4 py-2.5 text-xs">
          <div className="flex items-center gap-3 text-muted-foreground">
            <span className="font-medium uppercase tracking-wide text-foreground">Gantt giro</span>
            <span className="text-border">·</span>
            <span>
              {giro.giornate.length} giornat{giro.giornate.length === 1 ? "a" : "e"} ·{" "}
              {stats.nVariantiTotale} variant{stats.nVariantiTotale === 1 ? "e" : "i"} calendarial
              {stats.nVariantiTotale === 1 ? "e" : "i"}
            </span>
          </div>
          <div className="flex items-center gap-3 text-muted-foreground/80">
            <ZoomToggle current={zoom} onChange={handleZoomChange} />
            <span className="text-border">·</span>
            <span className="tabular-nums">
              1h = {Math.round(scale.pxPerHour)}px
            </span>
          </div>
        </div>

        {/* Scroll wrapper */}
        <div
          ref={scrollWrapperRef}
          className="relative overflow-auto"
          style={{ maxHeight: "700px" }}
        >
          <div className="relative" style={{ width: `${innerWidth}px` }}>
            {/* Sticky header X axis */}
            <AxisHeader />

            {/* Per giornata: header row + variante row + (notte band se non ultima) */}
            {giro.giornate.map((g, idx) => {
              const activeIdx = activeVariantByGiornata[g.id] ?? 0;
              const active = g.varianti[activeIdx] ?? g.varianti[0];
              const next = giro.giornate[idx + 1];
              return (
                <div key={g.id}>
                  <GiornataHeaderRow
                    giornata={g}
                    activeIdx={activeIdx}
                    selectedClusterA1Ids={selectedClusterA1Ids}
                    onChangeActive={(i) => onChangeActiveVariant(g.id, i)}
                  />
                  {active !== undefined && (
                    <VarianteRow
                      giornata={g}
                      variante={active}
                      selectedBloccoId={selectedBlocco?.id ?? null}
                      onSelectBlocco={onSelectBlocco}
                    />
                  )}
                  {next !== undefined && (
                    <NotteRow giornataPrev={g} giornataNext={next} activeVariantByGiornata={activeVariantByGiornata} />
                  )}
                </div>
              );
            })}

            {/* Totali */}
            <TotaliRow giro={giro} stats={stats} />
          </div>
        </div>

        {/* Legenda */}
        <Legenda />
      </Card>
    </GanttScaleContext.Provider>
  );
}

function ZoomToggle({
  current,
  onChange,
}: {
  current: ZoomLevel;
  onChange: (z: ZoomLevel) => void;
}) {
  return (
    <div
      role="group"
      aria-label="Zoom Gantt"
      className="inline-flex items-center rounded border border-border bg-white p-0.5 text-[10px] font-medium tabular-nums"
    >
      {ZOOM_LEVELS.map((z) => {
        const active = current === z;
        return (
          <button
            key={z}
            type="button"
            onClick={() => onChange(z)}
            aria-pressed={active}
            title={`Zoom Gantt al ${Math.round(z * 100)}% (1h = ${Math.round((BASE_TIMELINE_WIDTH_PX * z) / 24)}px)`}
            className={cn(
              "rounded px-2 py-0.5 transition-colors",
              active
                ? "bg-foreground text-white"
                : "text-muted-foreground hover:bg-muted",
            )}
          >
            {Math.round(z * 100)}%
          </button>
        );
      })}
    </div>
  );
}

// =====================================================================
// Sticky-top axis header
// =====================================================================

const HOUR_TICKS = [
  4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 0, 1, 2, 3,
];

function AxisHeader() {
  const { timelineWidthPx } = useGanttScale();
  const tickWidth = timelineWidthPx / 24;
  return (
    <div
      className="sticky top-0 z-30 flex border-b border-border bg-white"
      style={{ height: 36 }}
    >
      {/* Corner top-left (above giornata col) */}
      <div
        className="sticky left-0 z-40 flex items-end border-r border-border bg-white px-3 pb-1.5 text-[10px] uppercase tracking-wider text-muted-foreground"
        style={{ width: GIORNATA_LABEL_COL_PX }}
      >
        Giornata
      </div>
      {/* 24 tick orari */}
      <div className="relative" style={{ width: timelineWidthPx }}>
        <div className="absolute inset-0 flex">
          {HOUR_TICKS.map((h, i) => (
            <div key={`${h}-${i}`} className="relative" style={{ width: tickWidth }}>
              <span
                className={cn(
                  "absolute left-1 top-1 font-mono text-[10px] tabular-nums",
                  i % 2 === 0 ? "text-foreground" : "text-muted-foreground/70",
                )}
              >
                {String(h).padStart(2, "0")}
              </span>
            </div>
          ))}
        </div>
      </div>
      {/* Corner top-right (Per/Km cols) */}
      <div
        className="sticky right-0 z-40 flex border-l border-border bg-white"
        style={{ width: PER_KM_COL_PX }}
      >
        <div className="flex w-1/2 items-end justify-center border-r border-border pb-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
          Per
        </div>
        <div className="flex w-1/2 items-end justify-center pb-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
          Km
        </div>
      </div>
    </div>
  );
}

// =====================================================================
// Header riga giornata (numero grande + tab varianti + Per/Km vuota)
// =====================================================================

function GiornataHeaderRow({
  giornata,
  activeIdx,
  selectedClusterA1Ids,
  onChangeActive,
}: {
  giornata: GiroGiornata;
  activeIdx: number;
  selectedClusterA1Ids: Set<number> | null;
  onChangeActive: (idx: number) => void;
}) {
  const { timelineWidthPx } = useGanttScale();
  const varianti = giornata.varianti;
  const hasMultiple = varianti.length > 1;
  const active = varianti[activeIdx] ?? varianti[0];
  const giornataLabel = bloccoCategoryFromVariant(active);
  // Sprint 7.9 MR 8A: questa giornata contiene almeno un cluster A1
  // del set selezionato? Se NO, il ciclo si chiude prima qui.
  const clusterEsteso =
    selectedClusterA1Ids === null ||
    varianti.some((v) =>
      v.cluster_a1_ids.some((id) => selectedClusterA1Ids.has(id)),
    );

  return (
    <div className="flex border-b border-border bg-muted/30">
      <div
        className="sticky left-0 z-20 flex items-center gap-2 border-r border-border bg-muted/30 px-3 py-2"
        style={{ width: GIORNATA_LABEL_COL_PX }}
      >
        <span className="font-mono text-2xl font-bold leading-none text-foreground">
          {giornata.numero_giornata}
        </span>
        <div className="text-[10px] uppercase leading-tight tracking-wide text-muted-foreground">
          G{giornata.numero_giornata}
          {giornataLabel !== null && <><br />{giornataLabel}</>}
        </div>
      </div>
      <div
        className="flex flex-1 items-center gap-1.5 overflow-x-auto px-3 py-2"
        style={{ width: timelineWidthPx }}
      >
        {varianti.map((v, idx) => {
          const isActive = idx === activeIdx;
          return (
            <button
              key={v.id}
              type="button"
              onClick={() => onChangeActive(idx)}
              title={`${v.etichetta_parlante}${idx === 0 ? " (canonica)" : ""}`}
              className={cn(
                "whitespace-nowrap rounded px-2.5 py-1 text-[11px] font-medium transition-colors",
                isActive
                  ? "bg-foreground text-white"
                  : "border border-border bg-white text-muted-foreground hover:bg-muted",
              )}
            >
              {truncateLabel(v.etichetta_parlante)}
            </button>
          );
        })}
        {hasMultiple && (
          <span className="ml-2 text-[10px] italic text-muted-foreground/70">
            {varianti.length} varianti · stai vedendo "{truncateLabel(active?.etichetta_parlante ?? "")}"
          </span>
        )}
        {!clusterEsteso && (
          <span
            className="ml-2 inline-flex items-center gap-1 rounded border border-amber-300 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-900"
            title="Il ciclo selezionato in un'altra giornata non copre questa: il convoglio chiude prima."
          >
            ⓘ ciclo non si estende qui
          </span>
        )}
      </div>
      <div
        className="sticky right-0 z-20 border-l border-border bg-muted/30"
        style={{ width: PER_KM_COL_PX }}
      />
    </div>
  );
}

function truncateLabel(testo: string): string {
  const MAX = 36;
  return testo.length <= MAX ? testo : testo.substring(0, MAX - 1) + "…";
}

/**
 * Categoria semantica della variante, derivata dal nome (heuristic per
 * UI). Es. "LV 1:5" → "feriale", "F" → "festivo".
 */
function bloccoCategoryFromVariant(v: GiroVariante | undefined): string | null {
  if (v === undefined) return null;
  const e = v.etichetta_parlante.toLowerCase();
  if (e.startsWith("lv")) return "feriale";
  if (e === "f" || e.includes("festiv")) return "festivo";
  if (e === "s" || e.includes("sabato")) return "sabato";
  if (e.startsWith("solo")) return "specifica";
  return null;
}

// =====================================================================
// Variante row — single-line timeline
// =====================================================================

function VarianteRow({
  giornata,
  variante,
  selectedBloccoId,
  onSelectBlocco,
}: {
  giornata: GiroGiornata;
  variante: GiroVariante;
  selectedBloccoId: number | null;
  onSelectBlocco: (b: GiroBlocco) => void;
}) {
  const { timelineWidthPx, minToPx } = useGanttScale();
  const blocchi = variante.blocchi;
  const gaps = useMemo(() => computeGaps(blocchi), [blocchi]);
  const eventi = useMemo(() => extractEventiComposizione(variante), [variante]);
  // Sprint 7.9 MR δ.1 (entry 141): flag prima/ultima per stazioni col
  // nome pieno (decisione utente: "tranne la prima e l'ultima"). Il
  // criterio è "blocco con ora_inizio min/max tra le corse commerciali
  // e i materiali vuoti del giro" — escludiamo eventi composizione
  // (aggancio/sgancio) che non sono né origine né destinazione del giro.
  const blocchiOrdinati = useMemo(() => {
    const significativi = blocchi.filter(
      (b) => b.tipo_blocco !== "aggancio" && b.tipo_blocco !== "sgancio",
    );
    return [...significativi].sort((a, b) => {
      const ta = parseTimeToMin(a.ora_inizio) ?? 0;
      const tb = parseTimeToMin(b.ora_inizio) ?? 0;
      return ta - tb;
    });
  }, [blocchi]);
  const firstId = blocchiOrdinati[0]?.id ?? null;
  const lastId = blocchiOrdinati[blocchiOrdinati.length - 1]?.id ?? null;

  // Per/Km per giornata: usiamo km_giornata se presente; "Per" è
  // un campo non ancora persistito nel backend (vedi residui TN-UPDATE).
  const km =
    giornata.km_giornata !== null ? formatNumber(Math.round(giornata.km_giornata)) : "—";
  const per = "—"; // personale per giornata: non popolato dal builder

  return (
    <div className="relative flex border-b border-border">
      {/* Label col sticky-left */}
      <div
        className="sticky left-0 z-20 flex flex-col justify-center border-r border-border bg-white px-3 py-3"
        style={{ width: GIORNATA_LABEL_COL_PX }}
      >
        <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          {truncateLabel(variante.etichetta_parlante)}
        </div>
        {variante.dates_apply_json.length > 0 && (
          <div className="text-[9px] italic text-muted-foreground/70">
            {variante.dates_apply_json.length} dat
            {variante.dates_apply_json.length === 1 ? "a" : "e"}
          </div>
        )}
      </div>

      {/* Timeline */}
      <div
        className="ticks-bg relative"
        style={{ width: timelineWidthPx, height: TIMELINE_ROW_HEIGHT_PX }}
      >
        {/* Linea base sottile centrata */}
        <div
          className="pointer-events-none absolute left-0 right-0 h-px bg-border"
          style={{ top: 44 }}
        />

        {/* Marker mezzanotte se esistono blocchi cross-mezzanotte */}
        {blocchi.some((b) => isCrossMidnight(b)) && (
          <div
            className="pointer-events-none absolute top-0 bottom-0 w-px bg-blue-200"
            style={{ left: minToPx(24 * 60) }}
            title="mezzanotte"
          />
        )}

        {/* Eventi composizione (markers verticali arancio) */}
        {eventi.map((e, i) => (
          <EventoCompMarker key={`evt-${i}`} evento={e} />
        ))}

        {/* Gap markers (sotto ai blocchi z-default) */}
        {gaps.map((g, i) => (
          <GapMarker key={`gap-${variante.id}-${i}`} gap={g} />
        ))}

        {/* Blocchi posizionati */}
        {blocchi.map((b) => (
          <BloccoSegment
            key={b.id}
            blocco={b}
            selected={b.id === selectedBloccoId}
            isFirstOfRow={b.id === firstId}
            isLastOfRow={b.id === lastId}
            onSelect={() => onSelectBlocco(b)}
          />
        ))}
      </div>

      {/* Per + Km sticky-right */}
      <div
        className="sticky right-0 z-20 flex border-l border-border bg-white"
        style={{ width: PER_KM_COL_PX }}
      >
        <div className="flex w-1/2 items-center justify-center border-r border-border font-mono text-sm tabular-nums text-foreground">
          {per}
        </div>
        <div className="flex w-1/2 items-center justify-center font-mono text-sm tabular-nums text-foreground">
          {km}
        </div>
      </div>
    </div>
  );
}

// =====================================================================
// Blocco segment — render diverso per tipo
// =====================================================================

function BloccoSegment({
  blocco,
  selected,
  isFirstOfRow,
  isLastOfRow,
  onSelect,
}: {
  blocco: GiroBlocco;
  selected: boolean;
  isFirstOfRow: boolean;
  isLastOfRow: boolean;
  onSelect: () => void;
}) {
  const { minToPx } = useGanttScale();
  const inizio = parseTimeToMin(blocco.ora_inizio);
  const fine = parseTimeToMin(blocco.ora_fine);
  if (inizio === null || fine === null) return null;

  const startPx = minToPx(inizio);
  let endPx = minToPx(fine);
  if (endPx < startPx) endPx = minToPx(fine + AXIS_TOTAL_MIN);
  const widthPx = Math.max(8, endPx - startPx);

  const tipo = blocco.tipo_blocco;
  const tooltip = bloccoTooltip(blocco);

  // Commerciale: layout completo (stazioni sopra, treno+freccia dentro,
  // minuti sotto, validato emerald se applicabile).
  if (tipo === "corsa_commerciale") {
    return (
      <CommercialeBlocco
        blocco={blocco}
        startPx={startPx}
        widthPx={widthPx}
        selected={selected}
        isFirstOfRow={isFirstOfRow}
        isLastOfRow={isLastOfRow}
        onSelect={onSelect}
        tooltip={tooltip}
      />
    );
  }

  // Sprint 7.9 MR β2-2 fix UX: vuoto come VERA RIGA TRENO, identica
  // di layout al commerciale (stazioni sopra, etichetta dentro, orari
  // sotto), distinta solo dallo stile (rosso chiaro + bordo dashed +
  // testo rosso, vs commerciale = rosso pieno + testo bianco). Il
  // numero virtuale 9XXXXX è l'etichetta primaria dentro la barra.
  // Badge β1 ("Vuoto da deposito FIO" ecc.) restano sopra come
  // contesto operativo.
  if (tipo === "materiale_vuoto") {
    const meta = blocco.metadata_json ?? {};
    const tipoVuoto =
      typeof meta.tipo_vuoto === "string" ? (meta.tipo_vuoto as string) : null;
    const sedeCodice =
      typeof meta.sede_codice === "string" ? (meta.sede_codice as string) : null;
    // Sprint 7.9 MR β2-2: numero treno virtuale parlante. Backward
    // compat con `numero_treno_placeholder` per record pre-MR β2-2.
    const numeroVirtuale =
      typeof meta.numero_treno_virtuale === "string"
        ? (meta.numero_treno_virtuale as string)
        : typeof meta.numero_treno_placeholder === "string"
          ? (meta.numero_treno_placeholder as string)
          : null;
    // Fallback per record persistiti pre-MR β1 (nessun `tipo_vuoto`).
    const isUscitaCiclo =
      tipoVuoto === "uscita_deposito" ||
      (tipoVuoto === null && meta.is_uscita_ciclo === true);
    const isRientroDeposito =
      tipoVuoto === "rientro_deposito" ||
      (tipoVuoto === null && meta.motivo === "rientro_sede");
    const isRientroIntraArea = tipoVuoto === "rientro_intra_area";
    const isPosizionamentoIntraArea =
      tipoVuoto === "posizionamento_intra_area" ||
      (tipoVuoto === null && !isUscitaCiclo && !isRientroDeposito);
    const sedeLabel = sedeCodice ?? "deposito";
    const direction = isRientroDeposito || isRientroIntraArea ? "ret" : "out";
    const arrow = direction === "ret" ? "←" : "→";
    const stazioneDa = labelStazione(
      blocco.stazione_da_nome ?? blocco.stazione_da_codice,
      isFirstOfRow,
    );
    const stazioneA = labelStazione(
      blocco.stazione_a_nome ?? blocco.stazione_a_codice,
      isLastOfRow,
    );
    const showStazioni = widthPx >= 47;
    const showOrari = widthPx >= 33;
    return (
      <button
        type="button"
        onClick={onSelect}
        title={tooltip}
        aria-pressed={selected}
        className={cn("blk absolute overflow-hidden", selected && "is-selected")}
        style={{ left: startPx, top: 24, width: widthPx }}
      >
        {isUscitaCiclo && (
          <span
            className="absolute -top-3 left-0 z-10 whitespace-nowrap rounded bg-blue-600 px-1.5 py-0.5 text-[9px] font-semibold text-white"
            title={`Uscita assoluta del convoglio dal deposito ${sedeLabel} (inizio del ciclo)`}
          >
            🏠→ Vuoto da deposito {sedeLabel}
          </span>
        )}
        {isRientroDeposito && (
          <span
            className="absolute -top-3 right-0 z-10 whitespace-nowrap rounded bg-violet-600 px-1.5 py-0.5 text-[9px] font-semibold text-white"
            title={`Rientro al deposito ${sedeLabel} (chiusura del ciclo)`}
          >
            🏠← Vuoto verso deposito {sedeLabel}
          </span>
        )}
        {isRientroIntraArea && (
          <span
            className="absolute -top-3 right-0 z-10 whitespace-nowrap rounded bg-amber-600 px-1.5 py-0.5 text-[9px] font-semibold text-white"
            title={`Posizionamento intra-area verso la stazione collegata al deposito ${sedeLabel}`}
          >
            ↳ Vuoto intra-area
          </span>
        )}
        {isPosizionamentoIntraArea && !isUscitaCiclo && (
          <span
            className="absolute -top-3 left-0 z-10 whitespace-nowrap rounded bg-amber-600 px-1.5 py-0.5 text-[9px] font-semibold text-white"
            title="Posizionamento tecnico intra-area (convoglio già in linea, si sposta dentro la whitelist sede)"
          >
            ↳ Vuoto intra-area
          </span>
        )}
        {showStazioni ? (
          <div className="flex justify-between gap-1 font-mono text-[10px] font-semibold leading-none text-rose-700/80">
            <span className="min-w-0 flex-1 truncate text-left">{stazioneDa}</span>
            <span className="min-w-0 flex-1 truncate text-right">{stazioneA}</span>
          </div>
        ) : (
          <div className="h-[10px]" aria-hidden="true" />
        )}
        <div
          className={cn(
            "seg-line seg-vuoto-pieno relative mt-1.5 flex h-3 items-center justify-center rounded-sm",
            blocco.is_validato_utente && "validato",
            selected && "outline outline-2 outline-primary outline-offset-2",
          )}
        >
          <span className="truncate px-1 font-mono text-[11px] font-semibold tabular-nums text-rose-700">
            {arrow} {numeroVirtuale ?? "—"}
          </span>
        </div>
        {showOrari ? (
          <div className="mt-1 flex justify-between gap-1 font-mono text-[9px] leading-none tabular-nums text-muted-foreground">
            <span className="truncate">{formatTimeShort(blocco.ora_inizio)}</span>
            <span className="truncate">{formatTimeShort(blocco.ora_fine)}</span>
          </div>
        ) : (
          <div className="mt-1 h-[9px]" aria-hidden="true" />
        )}
      </button>
    );
  }

  // Rientro 9NNNN: viola con label
  if (tipo === "rientro_sede") {
    return (
      <button
        type="button"
        onClick={onSelect}
        title={tooltip}
        aria-pressed={selected}
        className={cn("blk absolute", selected && "is-selected")}
        style={{ left: startPx, top: 42, width: widthPx }}
      >
        <div
          className={cn(
            "seg-rientro h-3 rounded-sm",
            blocco.is_validato_utente && "validato",
            selected && "ring-2 ring-primary ring-offset-2",
          )}
        />
        <div className="mt-0.5 font-mono text-[9px] tabular-nums text-purple-700">
          ⟵ {blocco.numero_treno ?? "rientro"}
        </div>
      </button>
    );
  }

  // Accessori (ACCp/ACCa) o sosta_notturna o "accessori_p"/"_a": arancio sottile
  if (
    tipo === "accessori_p" ||
    tipo === "accessori_a" ||
    tipo === "accp" ||
    tipo === "acca" ||
    tipo === "sosta_notturna" ||
    tipo === "sosta"
  ) {
    const isAcc =
      tipo === "accessori_p" ||
      tipo === "accessori_a" ||
      tipo === "accp" ||
      tipo === "acca";
    const label =
      tipo === "accessori_p" || tipo === "accp"
        ? `ACCp ${formatGap(Math.max(0, fine - inizio))}`
        : tipo === "accessori_a" || tipo === "acca"
          ? `ACCa ${formatGap(Math.max(0, fine - inizio))}`
          : "sosta";
    return (
      <button
        type="button"
        onClick={onSelect}
        title={tooltip}
        aria-pressed={selected}
        className={cn("blk absolute", selected && "is-selected")}
        style={{ left: startPx, top: 54, width: widthPx }}
      >
        <div
          className={cn(
            "h-3 rounded-sm",
            isAcc ? "seg-acc" : "seg-sosta",
            blocco.is_validato_utente && "validato",
            selected && "ring-2 ring-primary ring-offset-2",
          )}
        />
        <div
          className={cn(
            "mt-0.5 font-mono text-[9px] tabular-nums",
            isAcc ? "text-orange-700" : "text-muted-foreground",
          )}
        >
          {label}
        </div>
      </button>
    );
  }

  // Manutenzione MA-30 o altri tipi: barra grigia ampia con label
  return (
    <button
      type="button"
      onClick={onSelect}
      title={tooltip}
      aria-pressed={selected}
      className={cn("blk absolute", selected && "is-selected")}
      style={{ left: startPx, top: 24, width: widthPx }}
    >
      <div className="flex items-center gap-1 text-[10px] font-semibold leading-none text-foreground">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-muted-foreground" />
        <span className="font-mono">{tipoBloccoLabel(tipo)}</span>
      </div>
      <div
        className={cn(
          "mt-1.5 h-3 rounded-sm border border-border bg-muted",
          blocco.is_validato_utente && "validato",
          selected && "ring-2 ring-primary ring-offset-2",
        )}
      />
      <div className="mt-1 flex justify-between font-mono text-[9px] leading-none tabular-nums text-muted-foreground">
        <span>{formatTimeShort(blocco.ora_inizio)}</span>
        <span>{formatTimeShort(blocco.ora_fine)}</span>
      </div>
    </button>
  );
}

function CommercialeBlocco({
  blocco,
  startPx,
  widthPx,
  selected,
  isFirstOfRow,
  isLastOfRow,
  onSelect,
  tooltip,
}: {
  blocco: GiroBlocco;
  startPx: number;
  widthPx: number;
  selected: boolean;
  isFirstOfRow: boolean;
  isLastOfRow: boolean;
  onSelect: () => void;
  tooltip: string;
}) {
  const direction = inferDirection(blocco);
  const arrow = direction === "ret" ? "←" : "→";
  // Sprint 7.9 MR δ.1 (entry 141): solo PRIMA stazione del giro (origine
  // del primo blocco) e ULTIMA (destinazione dell'ultimo) mostrano il
  // nome pieno; le intermedie usano l'acronimo della mappa
  // `stazioneAcronimo` (es. MILANO PORTA GARIBALDI → MiPG, LECCO → Lc).
  // Risolve la sovrapposizione visiva @ zoom 200% su giri densi.
  const stazioneDa = labelStazione(
    blocco.stazione_da_nome ?? blocco.stazione_da_codice,
    isFirstOfRow,
  );
  const stazioneA = labelStazione(
    blocco.stazione_a_nome ?? blocco.stazione_a_codice,
    isLastOfRow,
  );
  // Sprint 7.9 entry 110: blocchi stretti mostrano solo arrow+numero
  // per evitare sovrapposizione delle etichette stazione sui blocchi
  // adiacenti. Sopra la soglia stampa entrambe (origine|dest) tronche
  // al 50% della width disponibile.
  // Sprint 7.9 MR γ: soglie scalate da scala 60px/h a 40px/h (factor
  // 2/3): 70→47, 50→33. Mantiene la stessa soglia in MINUTI di durata
  // (~70 min per stazioni, ~50 min per orari).
  const showStazioni = widthPx >= 47;
  const showOrari = widthPx >= 33;
  return (
    <button
      type="button"
      onClick={onSelect}
      title={tooltip}
      aria-pressed={selected}
      className={cn("blk absolute overflow-hidden", selected && "is-selected")}
      style={{ left: startPx, top: 24, width: widthPx }}
    >
      {showStazioni ? (
        <div className="flex justify-between gap-1 font-mono text-[10px] font-semibold leading-none text-emerald-700">
          <span className="min-w-0 flex-1 truncate text-left">{stazioneDa}</span>
          <span className="min-w-0 flex-1 truncate text-right">{stazioneA}</span>
        </div>
      ) : (
        <div className="h-[10px]" aria-hidden="true" />
      )}
      <div
        className={cn(
          "seg-line seg-comm relative mt-1.5 flex h-3 items-center justify-center rounded-sm",
          blocco.is_validato_utente && "validato",
          selected && "outline outline-2 outline-primary outline-offset-2",
        )}
      >
        <span className="truncate px-1 font-mono text-[11px] font-semibold tabular-nums text-white">
          {arrow} {blocco.numero_treno ?? "—"}
        </span>
      </div>
      {showOrari ? (
        <div className="mt-1 flex justify-between gap-1 font-mono text-[9px] leading-none tabular-nums text-muted-foreground">
          <span className="truncate">{formatTimeShort(blocco.ora_inizio)}</span>
          <span className="truncate">{formatTimeShort(blocco.ora_fine)}</span>
        </div>
      ) : (
        <div className="mt-1 h-[9px]" aria-hidden="true" />
      )}
    </button>
  );
}

function inferDirection(b: GiroBlocco): "out" | "ret" {
  // Heuristic: se la stazione_a è la "sede target" (es. FIO, NOV) → ret.
  // Altrimenti → out. In assenza di info univoca, fallback: confronto
  // alfabetico stazione_da vs stazione_a.
  const seStr = b.stazione_a_codice ?? "";
  const isSede = /^(FIO|NOV|CAM|LEC|CRE|ISE)$/i.test(seStr);
  if (isSede) return "ret";
  return "out";
}

/**
 * Sprint 7.9 MR δ.1 (entry 141): label stazione DENTRO il Gantt giro.
 * Per le stazioni intermedie usa l'acronimo compatto (mappa Trenord +
 * fallback algoritmico in `lib/stazioni-acronimi.ts`); per la prima
 * stazione del giro (origine del primo blocco) e l'ultima (destinazione
 * dell'ultimo blocco) restituisce il nome pieno troncato dal CSS
 * `truncate` del container. NotteRow e SidePanel mostrano il nome
 * originale (`sostaInfo.stazione`, `blocco.stazione_*_nome`) senza
 * passare di qui — contesto già verboso.
 */
function labelStazione(label: string | null, useFullName: boolean): string {
  if (label === null) return "—";
  const trimmed = label.trim();
  if (trimmed.length === 0) return "—";
  return useFullName ? trimmed : stazioneAcronimo(trimmed);
}

function formatTimeShort(t: string | null): string {
  if (t === null) return "— —";
  const m = t.match(/^(\d{2}):(\d{2})/);
  if (m === null) return t;
  return `${m[1]} ${m[2]}`;
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
    case "manutenzione":
      return "MA-30";
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
  const validato = b.is_validato_utente ? "\n✓ Validato manualmente" : "";
  return `${tipo} · ${inizio} → ${fine}\n${da} → ${a}${treno}${validato}`;
}

function isCrossMidnight(b: GiroBlocco): boolean {
  const start = parseTimeToMin(b.ora_inizio);
  const end = parseTimeToMin(b.ora_fine);
  if (start === null || end === null) return false;
  return end < start;
}

// =====================================================================
// Gap markers (must-have #3)
// =====================================================================

interface GapInfo {
  startMin: number;
  endMin: number;
  durationMin: number;
}

function computeGaps(blocchi: GiroBlocco[]): GapInfo[] {
  const sorted = blocchi
    .map((b) => {
      const start = parseTimeToMin(b.ora_inizio);
      const end = parseTimeToMin(b.ora_fine);
      if (start === null || end === null) return null;
      let endAdj = end;
      if (endAdj < start) endAdj += AXIS_TOTAL_MIN;
      return { start, end: endAdj };
    })
    .filter((x): x is { start: number; end: number } => x !== null)
    .sort((a, b) => a.start - b.start);
  const gaps: GapInfo[] = [];
  for (let i = 0; i < sorted.length - 1; i += 1) {
    const cur = sorted[i];
    const next = sorted[i + 1];
    const gapDur = next.start - cur.end;
    if (gapDur >= GAP_MIN_THRESHOLD && gapDur < GAP_NIGHT_THRESHOLD) {
      gaps.push({ startMin: cur.end, endMin: next.start, durationMin: gapDur });
    }
  }
  return gaps;
}

function formatGap(min: number): string {
  if (min < 60) return `${min}'`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m === 0 ? `${h}h` : `${h}h${m}'`;
}

function GapMarker({ gap }: { gap: GapInfo }) {
  const { minToPx } = useGanttScale();
  const startPx = minToPx(gap.startMin);
  const endPx = minToPx(gap.endMin);
  const widthPx = Math.max(1, endPx - startPx);
  const showDashed = gap.durationMin >= GAP_LONG_THRESHOLD;
  return (
    <div
      className="pointer-events-none absolute"
      style={{ left: startPx, top: 42, width: widthPx }}
    >
      <div className="text-center font-mono text-[9px] tabular-nums text-muted-foreground">
        {formatGap(gap.durationMin)}
      </div>
      {showDashed && <div className="gap-long mt-0.5 h-px" />}
    </div>
  );
}

// =====================================================================
// Eventi composizione marker (must-have #4)
// =====================================================================

interface EventoComposizione {
  /** minuti dall'inizio giornata. */
  oraMin: number;
  /** "aggancio" (+N) o "sgancio" (-N). */
  tipo: "aggancio" | "sgancio";
  /** Materiale coinvolto (es. "ETR526"). */
  materiale: string;
  /** Variazione signed dei pezzi (+1, -2, ecc.). */
  pezziDelta: number;
  stazione: string | null;
  /** Sprint 7.9 MR β2-3: descrizione sourcing per AGGANCIO ("Pezzi da treno X..."). */
  sourceDescrizione: string | null;
  /** Sprint 7.9 MR β2-3: descrizione destinazione per SGANCIO ("Pezzi verso treno Y..."). */
  destDescrizione: string | null;
  /** Sprint 7.9 MR β2-3: True se il sourcing ha violato la dotazione. */
  capacityWarning: boolean;
}

/**
 * Estrae eventi composizione (aggancio/sgancio) dai blocchi della
 * variante. Sprint 7.9 fix: il backend persiste con
 * `tipo_blocco IN ('aggancio', 'sgancio')` (non
 * 'evento_composizione' come fallback obsoleto).
 *
 * Sprint 7.9 MR β2-3: legge anche source_descrizione / dest_descrizione
 * / capacity_warning dal metadata_json arricchito da `arricchisci_sourcing`.
 */
function extractEventiComposizione(variante: GiroVariante): EventoComposizione[] {
  const out: EventoComposizione[] = [];
  for (const b of variante.blocchi) {
    if (b.tipo_blocco !== "aggancio" && b.tipo_blocco !== "sgancio") {
      continue;
    }
    const min = parseTimeToMin(b.ora_inizio);
    if (min === null) continue;
    const meta = b.metadata_json ?? {};
    const materiale =
      typeof meta.materiale_tipo_codice === "string"
        ? (meta.materiale_tipo_codice as string)
        : "?";
    const delta =
      typeof meta.pezzi_delta === "number" ? (meta.pezzi_delta as number) : 0;
    const sourceDescr =
      typeof meta.source_descrizione === "string"
        ? (meta.source_descrizione as string)
        : null;
    const destDescr =
      typeof meta.dest_descrizione === "string"
        ? (meta.dest_descrizione as string)
        : null;
    const capWarn = meta.capacity_warning === true;
    out.push({
      oraMin: min,
      tipo: b.tipo_blocco,
      materiale,
      pezziDelta: delta,
      stazione: b.stazione_da_codice ?? b.stazione_a_codice,
      sourceDescrizione: sourceDescr,
      destDescrizione: destDescr,
      capacityWarning: capWarn,
    });
  }
  return out;
}

function EventoCompMarker({ evento }: { evento: EventoComposizione }) {
  const { minToPx } = useGanttScale();
  const px = minToPx(evento.oraMin);
  const orario = formatTimeShort(minToTime(evento.oraMin));
  const segno = evento.pezziDelta >= 0 ? "+" : "";
  const descrizione =
    evento.tipo === "aggancio"
      ? evento.sourceDescrizione
      : evento.destDescrizione;
  // Sprint 7.9 MR β2-3 / MR δ.1 (entry 141):
  // - Aggancio: verde (+ pezzi entrano)
  // - Sgancio: rosso (- pezzi escono)
  // - Capacity warning: giallo lampo
  // Label compatta `+1` / `-1` (no MAT code) per non sovrapporre il
  // testo dei blocchi commerciali sotto. Il dettaglio (materiale +
  // descrizione sourcing) finisce nel Popover su click.
  const color = evento.capacityWarning
    ? "#f59e0b"
    : evento.tipo === "aggancio"
      ? "#16a34a"
      : "#dc2626";
  const tipoLabel = evento.tipo === "aggancio" ? "AGGANCIO" : "SGANCIO";
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`${tipoLabel} ${segno}${evento.pezziDelta} ${evento.materiale} alle ${orario}`}
          className="absolute z-10 flex flex-col items-center"
          style={{ left: px - 8, top: 0, width: 16 }}
        >
          <span
            className="rounded-sm px-1 py-0.5 text-[9px] font-bold leading-none text-white tabular-nums"
            style={{ background: color }}
          >
            {segno}
            {evento.pezziDelta}
          </span>
          <div
            className="mt-0.5"
            style={{ width: 2, height: 80, background: color }}
          />
        </button>
      </PopoverTrigger>
      <PopoverContent align="center" sideOffset={4} className="text-xs">
        <div className="flex items-center gap-2">
          <span
            className="rounded-sm px-1.5 py-0.5 text-[10px] font-bold uppercase leading-none text-white"
            style={{ background: color }}
          >
            {tipoLabel}
          </span>
          <span className="font-mono tabular-nums text-foreground">
            {orario}
          </span>
          {evento.stazione !== null && (
            <span className="font-mono text-muted-foreground">
              · {evento.stazione}
            </span>
          )}
        </div>
        <div className="mt-2 font-mono text-sm text-foreground">
          {segno}
          {evento.pezziDelta}{" "}
          <span className="text-muted-foreground">{evento.materiale}</span>
        </div>
        {descrizione !== null && (
          <div className="mt-2 border-t border-border pt-2 text-[11px] leading-snug text-muted-foreground">
            {descrizione}
          </div>
        )}
        {evento.capacityWarning && (
          <div className="mt-2 rounded border border-amber-300 bg-amber-50 px-2 py-1 text-[10px] font-medium text-amber-900">
            ⚠ Capacity warning: dotazione azienda potrebbe essere
            insufficiente per questo aggancio.
          </div>
        )}
        <div className="mt-2 text-[10px] italic text-muted-foreground/70">
          {evento.tipo === "aggancio"
            ? "Pezzo che entra nel turno (composizione cresce)."
            : "Pezzo che esce dal turno (composizione cala)."}
        </div>
      </PopoverContent>
    </Popover>
  );
}

// =====================================================================
// Notte fra giornate (must-have #5)
// =====================================================================

function NotteRow({
  giornataPrev,
  giornataNext,
  activeVariantByGiornata,
}: {
  giornataPrev: GiroGiornata;
  giornataNext: GiroGiornata;
  activeVariantByGiornata: Record<number, number>;
}) {
  const { timelineWidthPx } = useGanttScale();
  const prevVar =
    giornataPrev.varianti[activeVariantByGiornata[giornataPrev.id] ?? 0] ??
    giornataPrev.varianti[0];
  const nextVar =
    giornataNext.varianti[activeVariantByGiornata[giornataNext.id] ?? 0] ??
    giornataNext.varianti[0];

  const sostaInfo = computeSostaNotturna(prevVar, nextVar);

  return (
    <div className="flex" style={{ height: NOTTE_ROW_HEIGHT_PX }}>
      <div
        className="night-band sticky left-0 z-20 flex items-center border-r border-border px-3"
        style={{ width: GIORNATA_LABEL_COL_PX }}
      >
        <span
          className={cn(
            "text-[10px] uppercase tracking-wide",
            sostaInfo.discontinua ? "font-semibold text-destructive" : "text-muted-foreground",
          )}
        >
          {sostaInfo.discontinua ? "⚠ notte" : "notte"}
        </span>
      </div>
      <div
        className={cn(
          "flex items-center px-3",
          sostaInfo.discontinua ? "border-y border-destructive/30 bg-destructive/5" : "night-band",
        )}
        style={{ width: timelineWidthPx }}
      >
        {sostaInfo.stazione !== null ? (
          <>
            {/* Sprint 7.9 MR β1: etichetta esplicita "Materiale in sosta a
                X · da G(K-1) finita alle 22:14 · 7h59'". Niente più
                inferenza implicita per il pianificatore: dichiariamo da
                dove arriva il materiale e quanto resta in sosta. */}
            <span className="text-[10px] text-muted-foreground">
              Materiale in sosta a{" "}
              <span className="font-mono font-semibold text-foreground">
                {sostaInfo.stazione}
              </span>
              {sostaInfo.terminaOra !== null && (
                <>
                  {" "}· da G{giornataPrev.numero_giornata} finita alle{" "}
                  <span className="font-mono tabular-nums text-foreground">
                    {sostaInfo.terminaOra}
                  </span>
                </>
              )}
              {sostaInfo.iniziaOra !== null && (
                <>
                  {" "}· riparte G{giornataNext.numero_giornata} alle{" "}
                  <span className="font-mono tabular-nums text-foreground">
                    {sostaInfo.iniziaOra}
                  </span>
                </>
              )}
              {sostaInfo.duration !== null && ` · ${formatGap(sostaInfo.duration)}`}
            </span>
            {sostaInfo.discontinua && (
              <span
                className="ml-3 inline-flex items-center gap-1 rounded bg-destructive/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-destructive"
                title={`Anomalia builder (post MR α non dovrebbe più esistere): G${giornataPrev.numero_giornata} termina a ${sostaInfo.terminaA ?? "?"}, G${giornataNext.numero_giornata} inizia a ${sostaInfo.iniziaDa ?? "?"}. Segnalare.`}
              >
                ⚠ anomalia builder
              </span>
            )}
          </>
        ) : (
          <span className="text-[10px] italic text-muted-foreground/70">
            notte · stazione di sosta non determinabile
          </span>
        )}
      </div>
      <div
        className="night-band sticky right-0 z-20 border-l border-border"
        style={{ width: PER_KM_COL_PX }}
      />
    </div>
  );
}

interface SostaNotturnaInfo {
  /** Nome leggibile della stazione di sosta (preferito al codice). */
  stazione: string | null;
  /** Durata in minuti, se calcolabile. */
  duration: number | null;
  /** True se stazione_a (G_n) ≠ stazione_da (G_n+1). */
  discontinua: boolean;
  /** Codice tecnico della stazione di terminazione G_n. */
  terminaA: string | null;
  /** Codice tecnico della stazione di partenza G_n+1. */
  iniziaDa: string | null;
  /** Sprint 7.9 MR β1: orario formato "HH:MM" della terminazione G_n. */
  terminaOra: string | null;
  /** Sprint 7.9 MR β1: orario formato "HH:MM" della partenza G_n+1. */
  iniziaOra: string | null;
}

const _SOSTA_VUOTA: SostaNotturnaInfo = {
  stazione: null,
  duration: null,
  discontinua: false,
  terminaA: null,
  iniziaDa: null,
  terminaOra: null,
  iniziaOra: null,
};

function computeSostaNotturna(
  prev: GiroVariante | undefined,
  next: GiroVariante | undefined,
): SostaNotturnaInfo {
  if (prev === undefined || next === undefined) {
    return _SOSTA_VUOTA;
  }
  const lastBlock = [...prev.blocchi]
    .filter((b) => parseTimeToMin(b.ora_fine) !== null)
    .sort((a, b) => (parseTimeToMin(b.ora_fine) ?? 0) - (parseTimeToMin(a.ora_fine) ?? 0))[0];
  const firstBlock = [...next.blocchi]
    .filter((b) => parseTimeToMin(b.ora_inizio) !== null)
    .sort((a, b) => (parseTimeToMin(a.ora_inizio) ?? 0) - (parseTimeToMin(b.ora_inizio) ?? 0))[0];
  if (lastBlock === undefined || firstBlock === undefined) {
    return _SOSTA_VUOTA;
  }
  const terminaA = lastBlock.stazione_a_codice;
  const iniziaDa = firstBlock.stazione_da_codice;
  const discontinua =
    terminaA !== null && iniziaDa !== null && terminaA !== iniziaDa;
  // Calcolo durata: assumiamo il giro continui giorno-dopo, quindi
  // notte = (24h - ora_fine_prev) + ora_inizio_next.
  const fine = parseTimeToMin(lastBlock.ora_fine) ?? 0;
  const inizio = parseTimeToMin(firstBlock.ora_inizio) ?? 0;
  const duration = 24 * 60 - fine + inizio;
  // Sprint 7.9 MR β1: preferisci il nome leggibile al codice tecnico per
  // l'etichetta "Materiale in sosta a X".
  const stazioneLabel =
    lastBlock.stazione_a_nome ?? terminaA ?? firstBlock.stazione_da_nome ?? iniziaDa;
  return {
    stazione: stazioneLabel,
    duration: duration > 0 ? duration : null,
    discontinua,
    terminaA,
    iniziaDa,
    terminaOra: formatTimeShort(lastBlock.ora_fine),
    iniziaOra: formatTimeShort(firstBlock.ora_inizio),
  };
}

// =====================================================================
// Totali row
// =====================================================================

function TotaliRow({ giro, stats }: { giro: GiroDettaglio; stats: GiroKpiStats }) {
  const { timelineWidthPx } = useGanttScale();
  const totalKm =
    giro.km_media_giornaliera !== null && giro.km_media_giornaliera > 0
      ? formatNumber(Math.round(giro.km_media_giornaliera * giro.numero_giornate))
      : "—";
  return (
    <div className="flex bg-muted/40 font-semibold">
      <div
        className="sticky left-0 z-20 border-r border-border bg-muted/40 px-3 py-2 text-[11px] uppercase tracking-wide text-foreground"
        style={{ width: GIORNATA_LABEL_COL_PX }}
      >
        Totale
      </div>
      <div
        className="px-3 py-2 text-[11px] text-muted-foreground"
        style={{ width: timelineWidthPx }}
      >
        {giro.numero_giornate} giornat{giro.numero_giornate === 1 ? "a" : "e"} ·{" "}
        {stats.nBlocchi} blocch{stats.nBlocchi === 1 ? "o" : "i"} · {stats.nVariantiTotale}{" "}
        variant{stats.nVariantiTotale === 1 ? "e" : "i"} calendarial
        {stats.nVariantiTotale === 1 ? "e" : "i"}
      </div>
      <div
        className="sticky right-0 z-20 flex border-l border-border bg-muted/40"
        style={{ width: PER_KM_COL_PX }}
      >
        <div className="flex w-1/2 items-center justify-center border-r border-border font-mono text-sm tabular-nums text-foreground">
          —
        </div>
        <div className="flex w-1/2 items-center justify-center font-mono text-sm tabular-nums text-foreground">
          {totalKm}
        </div>
      </div>
    </div>
  );
}

// =====================================================================
// Legenda
// =====================================================================

function Legenda() {
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-2 border-t border-border px-4 py-3 text-[11px] text-muted-foreground">
      <span className="inline-flex items-center gap-1.5">
        <span className="seg-comm inline-block h-2 w-4" /> commerciale
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="seg-vuoto inline-block h-1 w-4" /> vuoto tecnico
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="seg-rientro inline-block h-2 w-4" /> rientro 9NNNN
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="seg-acc inline-block h-2 w-4" /> accessori
      </span>
      <span className="text-border">|</span>
      <span className="inline-flex items-center gap-1.5">
        <span className="font-mono font-semibold text-emerald-700">CREMONA</span> stazione
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="font-mono font-semibold text-blue-700">→ 28335</span> n° treno · direzione
      </span>
      <span className="inline-flex items-center gap-1.5 font-mono tabular-nums text-muted-foreground">
        14 52 minuti arrivo/partenza
      </span>
      <span className="text-border">|</span>
      <span className="inline-flex items-center gap-1.5">
        <span className="seg-comm validato inline-block h-2 w-4" /> validato manualmente
      </span>
    </div>
  );
}

// =====================================================================
// Side panel — dettaglio blocco selezionato (redesign v3)
// =====================================================================

function BloccoSidePanel({
  blocco,
  giro,
  activeVariantByGiornata,
  onClose,
}: {
  blocco: GiroBlocco;
  giro: GiroDettaglio;
  activeVariantByGiornata: Record<number, number>;
  onClose: () => void;
}) {
  const tipoLabel = tipoBloccoLabel(blocco.tipo_blocco);
  const direction = inferDirection(blocco);
  const arrow = direction === "ret" ? "←" : "→";
  const inizioMin = parseTimeToMin(blocco.ora_inizio);
  const fineMin = parseTimeToMin(blocco.ora_fine);
  const durata =
    inizioMin !== null && fineMin !== null
      ? formatGap(fineMin >= inizioMin ? fineMin - inizioMin : 24 * 60 - inizioMin + fineMin)
      : "—";
  const isCommerciale = blocco.tipo_blocco === "corsa_commerciale";

  // Localizza il blocco nel giro (giornata + variante + posizione).
  const location = useMemo(() => {
    for (const g of giro.giornate) {
      const activeIdx = activeVariantByGiornata[g.id] ?? 0;
      const v = g.varianti[activeIdx];
      if (v === undefined) continue;
      const idx = v.blocchi.findIndex((b) => b.id === blocco.id);
      if (idx !== -1) {
        return {
          giornata: g.numero_giornata,
          varianteEtichetta: v.etichetta_parlante,
          blockIdx: idx + 1,
          totalBlocks: v.blocchi.length,
        };
      }
    }
    return null;
  }, [giro, blocco.id, activeVariantByGiornata]);

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
        <div className="mb-1 flex items-center gap-2">
          <span
            className={cn(
              "inline-flex items-center rounded px-2 py-0.5 text-[10px] uppercase tracking-wide",
              isCommerciale
                ? "bg-blue-100 text-primary"
                : "bg-muted text-muted-foreground",
            )}
          >
            {tipoLabel}
          </span>
          {blocco.is_validato_utente && (
            <span className="inline-flex items-center rounded bg-emerald-100 px-2 py-0.5 text-[10px] uppercase tracking-wide text-emerald-800">
              VALIDATO
            </span>
          )}
        </div>
        <h3 className="font-mono text-2xl font-semibold text-foreground">
          {blocco.numero_treno ?? "—"}
        </h3>
        {location !== null && (
          <p className="mt-0.5 text-xs text-muted-foreground">
            G{location.giornata} · variante "{truncateLabel(location.varianteEtichetta)}" ·
            blocco {location.blockIdx} di {location.totalBlocks} · seq{" "}
            <span className="font-mono">#{blocco.seq}</span>
          </p>
        )}

        {/* O → D */}
        <div className="mt-5 grid grid-cols-[1fr_auto_1fr] items-center gap-3">
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Da</div>
            <div className="text-sm font-medium text-foreground">
              {blocco.stazione_da_nome ?? blocco.stazione_da_codice ?? "—"}
            </div>
            <div className="font-mono text-[10px] text-muted-foreground">
              {blocco.stazione_da_codice ?? "—"} · {formatTimeShort(blocco.ora_inizio)}
            </div>
          </div>
          <span aria-hidden className="text-muted-foreground">
            {arrow}
          </span>
          <div>
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">A</div>
            <div className="text-sm font-medium text-foreground">
              {blocco.stazione_a_nome ?? blocco.stazione_a_codice ?? "—"}
            </div>
            <div className="font-mono text-[10px] text-muted-foreground">
              {blocco.stazione_a_codice ?? "—"} · {formatTimeShort(blocco.ora_fine)}
            </div>
          </div>
        </div>

        {/* KPI mini: durata + tipo + sequenza */}
        <div className="mt-5 grid grid-cols-3 gap-2 border-b border-border pb-4">
          <KpiPanel label="Durata" value={durata} />
          <KpiPanel
            label="Direzione"
            value={direction === "ret" ? "ret (←)" : "out (→)"}
          />
          <KpiPanel label="Tipo" value={tipoLabel.split(" ")[0]} />
        </div>

        {/* Validazione block */}
        {blocco.is_validato_utente && (
          <div className="mt-4 flex items-start gap-2 rounded border border-emerald-200 bg-emerald-50 p-3">
            <span className="text-sm text-emerald-700">✓</span>
            <div className="text-[11px] leading-snug text-emerald-900">
              <div className="font-semibold">Validato manualmente</div>
              <div className="mt-0.5 text-emerald-700">
                Il pianificatore ha confermato questo blocco.
              </div>
            </div>
          </div>
        )}

        {/* Metadata */}
        <BloccoMetadata blocco={blocco} />

        {blocco.descrizione !== null && blocco.descrizione !== "" && (
          <div className="mt-4 rounded border border-border bg-muted/40 p-3 text-[11px] italic text-muted-foreground">
            Note: {blocco.descrizione}
          </div>
        )}

        <p className="mt-4 text-center text-[10px] text-muted-foreground">
          Premi{" "}
          <kbd className="rounded border border-border bg-muted px-1 py-0.5 font-mono text-[10px]">
            Esc
          </kbd>{" "}
          o ✕ per deselezionare.
        </p>
      </div>
    </Card>
  );
}

function KpiPanel({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="text-base font-semibold tabular-nums text-foreground">{value}</div>
    </div>
  );
}

function BloccoMetadata({ blocco }: { blocco: GiroBlocco }) {
  const items: Array<[string, string]> = [];
  if (blocco.corsa_commerciale_id !== null) {
    items.push(["corsa_commerciale_id", `#${blocco.corsa_commerciale_id}`]);
  }
  if (blocco.corsa_materiale_vuoto_id !== null) {
    items.push(["corsa_materiale_vuoto_id", `#${blocco.corsa_materiale_vuoto_id}`]);
  }
  // Espone solo i metadata "leggibili" (string/number primitives).
  for (const [k, v] of Object.entries(blocco.metadata_json)) {
    if (typeof v === "string" || typeof v === "number") {
      items.push([k, String(v)]);
    }
  }
  if (items.length === 0) return null;
  return (
    <div className="mt-5">
      <div className="mb-2 text-[10px] uppercase tracking-wide text-muted-foreground">
        Metadata
      </div>
      <dl className="space-y-1.5 text-xs">
        {items.map(([k, v]) => (
          <div
            key={k}
            className="flex justify-between border-b border-border/50 pb-1 last:border-0 last:pb-0"
          >
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="font-mono text-foreground">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

// =====================================================================
// Sotto-Gantt: date di applicazione (per variante)
// =====================================================================

function DateApplicazioneSection({ giro }: { giro: GiroDettaglio }) {
  const items = useMemo(() => {
    const out: Array<{
      key: string;
      label: string;
      etichetta: string;
      datesApply: string[];
      datesSkip: string[];
      validitaTesto: string | null;
    }> = [];
    for (const g of giro.giornate) {
      for (const v of g.varianti) {
        out.push({
          key: `${g.id}-${v.id}`,
          label: `G${g.numero_giornata} · ${truncateLabel(v.etichetta_parlante)}`,
          etichetta: v.etichetta_parlante,
          datesApply: v.dates_apply_json,
          datesSkip: v.dates_skip_json,
          validitaTesto: v.validita_testo,
        });
      }
    }
    return out;
  }, [giro]);

  if (items.length === 0) return null;

  return (
    <Card className="p-5">
      <div className="mb-3 text-[11px] uppercase tracking-wide text-muted-foreground">
        Date di applicazione (per variante)
      </div>
      <div className="space-y-3">
        {items.map((it) => (
          <div key={it.key} className="grid grid-cols-[140px_1fr] gap-3 items-start">
            <div className="pt-0.5 text-xs text-foreground">
              <span className="font-mono font-semibold">{it.label}</span>
            </div>
            <div>
              <div className="flex flex-wrap gap-1.5">
                {it.datesApply.slice(0, 5).map((d) => (
                  <span
                    key={d}
                    className="inline-flex rounded bg-muted px-2 py-0.5 font-mono text-[10px] text-foreground"
                  >
                    {formatDateShort(d)}
                  </span>
                ))}
                {it.datesApply.length > 5 && (
                  <span className="inline-flex rounded px-2 py-0.5 text-[10px] italic text-muted-foreground">
                    + {it.datesApply.length - 5} altre
                  </span>
                )}
                {it.datesSkip.slice(0, 3).map((d) => (
                  <span
                    key={`skip-${d}`}
                    className="inline-flex rounded bg-destructive/10 px-2 py-0.5 font-mono text-[10px] text-destructive line-through"
                    title="Saltata"
                  >
                    {formatDateShort(d)}
                  </span>
                ))}
              </div>
              {it.validitaTesto !== null && it.validitaTesto !== "" && (
                <div className="mt-1.5 text-[11px] italic text-muted-foreground">
                  "{it.validitaTesto}"
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

function formatDateShort(iso: string): string {
  // "2026-06-15" → "15/06"
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m === null) return formatDateIt(iso);
  return `${m[3]}/${m[2]}`;
}

// =====================================================================
// Time axis math (px-based, 1h = 40px — Sprint 7.9 MR γ)
// =====================================================================

function parseTimeToMin(t: string | null): number | null {
  if (t === null || t.length === 0) return null;
  const parts = t.split(":");
  if (parts.length < 2) return null;
  const h = Number.parseInt(parts[0], 10);
  const m = Number.parseInt(parts[1], 10);
  if (Number.isNaN(h) || Number.isNaN(m)) return null;
  return h * 60 + m;
}

/** Minuti da 00:00 → "HH:MM" (per logging/tooltip). */
function minToTime(min: number): string {
  const m = ((min % AXIS_TOTAL_MIN) + AXIS_TOTAL_MIN) % AXIS_TOTAL_MIN;
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return `${String(h).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
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
