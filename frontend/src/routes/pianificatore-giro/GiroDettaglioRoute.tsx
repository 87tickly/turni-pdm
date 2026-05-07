import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Copy,
  FileDown,
  Maximize2,
  Minimize2,
  Pencil,
  Search,
  Trash2,
  Unlink,
  Users,
} from "lucide-react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
  type DraggableAttributes,
} from "@dnd-kit/core";
import type { SyntheticListenerMap } from "@dnd-kit/core/dist/hooks/utilities";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Label } from "@/components/ui/Label";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/Popover";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import { useMateriali } from "@/hooks/useAnagrafiche";
import {
  useDuplicaGiro,
  useEliminaBlocco,
  useGiroDettaglio,
  usePatchBlocco,
  usePatchGiro,
  useSpostaBlocco,
  useThreadsGiro,
} from "@/hooks/useGiri";
import { useTurniPdcGiro } from "@/hooks/useTurniPdc";
import { ApiError } from "@/lib/api/client";
import type {
  GiroBlocco,
  GiroDettaglio,
  GiroGiornata,
  GiroVariante,
  SpostaBloccoResponse,
  ViolazioneFattibilita,
} from "@/lib/api/giri";
import { formatDateIt, formatNumber } from "@/lib/format";
import { stazioneAcronimo } from "@/lib/stazioni-acronimi";
import { cn } from "@/lib/utils";
import { CercaTrenoDialog } from "@/routes/pianificatore-giro/CercaTrenoDialog";
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

export const AXIS_START_MIN = 4 * 60; // 04:00 reference
export const AXIS_TOTAL_MIN = 24 * 60; // 1440 min

// Sprint 7.9 MR γ (2026-05-04) ha portato il default da 1h=60px a
// 1h=40px (960px totale) per evitare scroll orizzontale su schermi
// ≥1280px. Sprint 7.9 MR δ (2026-05-05): scala parametrizzata via
// `GanttScaleContext`, l'utente sceglie 75/100/150/200% in toolbar
// (default 100% = 960px = scala MR γ). Risolve il troncamento di
// numeri/orari sui giri densi tipo direttrice Tirano (~26 treni/g).
export const BASE_TIMELINE_WIDTH_PX = 960;
export const GIORNATA_LABEL_COL_PX = 100;
export const PER_KM_COL_PX = 120;
export const TIMELINE_ROW_HEIGHT_PX = 88;
const NOTTE_ROW_HEIGHT_PX = 24;

const ZOOM_LEVELS = [0.75, 1, 1.5, 2] as const;
type ZoomLevel = (typeof ZOOM_LEVELS)[number];
const DEFAULT_ZOOM: ZoomLevel = 1;
const LS_KEY_GANTT_ZOOM = "colazione.gantt-giro.zoom";

// Sprint 8.0 entry 204 (sotto-MR 9 Step A): nesting varianti collassabile.
// Default: ogni giornata mostra solo la variante canonica (idx 0); click
// sull'header espande TUTTE le varianti come righe separate. Persistito
// per id-giornata in localStorage così la scelta sopravvive a refresh.
const LS_KEY_GANTT_EXPANDED = "colazione.gantt-giro.expanded";

export interface GanttScale {
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

export const GanttScaleContext = createContext<GanttScale>({
  timelineWidthPx: BASE_TIMELINE_WIDTH_PX,
  pxPerHour: BASE_TIMELINE_WIDTH_PX / 24,
  minToPx: (min) => _baseMinToPx(min, BASE_TIMELINE_WIDTH_PX),
});

export function useGanttScale(): GanttScale {
  return useContext(GanttScaleContext);
}

/**
 * Sprint 8.0 MR-A (entry 231) — factory di GanttScale per la vista
 * aggregata, che ha bisogno di settare il provider esternamente.
 * Il GiroDettaglioRoute usa il proprio provider interno con zoom
 * persisted; la TurnoAggregatoRoute riusa la stessa logica.
 */
export function buildGanttScale(zoom: number): GanttScale {
  const timelineWidthPx = BASE_TIMELINE_WIDTH_PX * zoom;
  return {
    timelineWidthPx,
    pxPerHour: timelineWidthPx / 24,
    minToPx: (min) => _baseMinToPx(min, timelineWidthPx),
  };
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

function readPersistedExpanded(): Set<number> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = window.localStorage.getItem(LS_KEY_GANTT_EXPANDED);
    if (raw === null) return new Set();
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((x): x is number => typeof x === "number"));
  } catch {
    return new Set();
  }
}

function persistExpanded(ids: Set<number>): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(LS_KEY_GANTT_EXPANDED, JSON.stringify([...ids]));
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
  const navigate = useNavigate();
  const duplicaMutation = useDuplicaGiro();

  const [selectedBlocco, setSelectedBlocco] = useState<GiroBlocco | null>(null);
  const [pdcDialogOpen, setPdcDialogOpen] = useState(false);
  // MR η: dialog di modifica materiale del giro post-generazione.
  const [editMaterialeOpen, setEditMaterialeOpen] = useState(false);
  // Sprint 8.0 MR-1 (entry 214): popup cerca treno + focus blocco da URL.
  const [cercaTrenoOpen, setCercaTrenoOpen] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
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

  // Sprint 8.0 MR-B.1 (entry 230): drag&drop blocchi tra giornate.
  // - `dragActiveBlocco`: blocco in dragging, visualizzato in DragOverlay.
  // - `pendingMove`: spostamento in attesa di conferma utente (dopo
  //   dry_run con violazioni `severity=error`).
  const [dragActiveBlocco, setDragActiveBlocco] =
    useState<GiroBlocco | null>(null);
  const [pendingMove, setPendingMove] = useState<{
    blocco: GiroBlocco;
    sourceGiroId: number;
    giornataTarget: number;
    variantIndexTarget: number;
    giroTargetIdPayload: number | null;
    response: SpostaBloccoResponse;
  } | null>(null);
  const spostaMutation = useSpostaBlocco();

  // Sensors dnd-kit: PointerSensor con activation distance 5px → click
  // puro non triggera drag (utile per onClick selezione blocco).
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 5 },
    }),
  );

  const handleDragStart = useCallback((event: DragStartEvent) => {
    const blocco = event.active.data.current?.blocco as
      | GiroBlocco
      | undefined;
    setDragActiveBlocco(blocco ?? null);
  }, []);

  const handleDragEnd = useCallback(
    async (event: DragEndEvent) => {
      setDragActiveBlocco(null);
      const { active, over } = event;
      if (over === null) return;
      const blocco = active.data.current?.blocco as
        | GiroBlocco
        | undefined;
      const sourceVarianteId = active.data.current?.varianteId as
        | number
        | undefined;
      const sourceGiroId = active.data.current?.giroId as
        | number
        | undefined;
      const target = over.data.current as
        | {
            varianteId: number;
            giornataNumero: number;
            variantIndex: number;
            giroId?: number;
          }
        | undefined;
      if (blocco === undefined || target === undefined) return;
      // No-op se rilascio sulla stessa variante (intra-variante reorder
      // fuori scope MR-B.1).
      if (sourceVarianteId === target.varianteId) return;
      const giroDettaglio = query.data;
      if (giroDettaglio === undefined) return;

      // Sprint 8.0 MR-A entry 231: cross-turno via giro_target_id.
      // Source = sourceGiroId (o giroDettaglio.id come fallback).
      // Target = target.giroId (o stesso source, intra-turno).
      const sourceGiro = sourceGiroId ?? giroDettaglio.id;
      const targetGiro = target.giroId ?? sourceGiro;
      const giroTargetIdPayload =
        targetGiro !== sourceGiro ? targetGiro : null;

      try {
        const dryRes = await spostaMutation.mutateAsync({
          giroId: sourceGiro,
          bloccoId: blocco.id,
          payload: {
            giornata_target: target.giornataNumero,
            variant_index_target: target.variantIndex,
            giro_target_id: giroTargetIdPayload,
            dry_run: true,
            force: false,
          },
        });
        const hasErrors = dryRes.violazioni.some(
          (v) => v.severity === "error",
        );
        if (!hasErrors) {
          await spostaMutation.mutateAsync({
            giroId: sourceGiro,
            bloccoId: blocco.id,
            payload: {
              giornata_target: target.giornataNumero,
              variant_index_target: target.variantIndex,
              giro_target_id: giroTargetIdPayload,
              dry_run: false,
              force: false,
            },
          });
        } else {
          setPendingMove({
            blocco,
            sourceGiroId: sourceGiro,
            giornataTarget: target.giornataNumero,
            variantIndexTarget: target.variantIndex,
            giroTargetIdPayload,
            response: dryRes,
          });
        }
      } catch (err) {
        const msg =
          err instanceof ApiError ? err.message : (err as Error).message;
        window.alert(`Spostamento fallito: ${msg}`);
      }
    },
    [query.data, spostaMutation],
  );

  const confermaSpostamentoForce = useCallback(async () => {
    if (pendingMove === null) return;
    try {
      await spostaMutation.mutateAsync({
        giroId: pendingMove.sourceGiroId,
        bloccoId: pendingMove.blocco.id,
        payload: {
          giornata_target: pendingMove.giornataTarget,
          variant_index_target: pendingMove.variantIndexTarget,
          giro_target_id: pendingMove.giroTargetIdPayload,
          dry_run: false,
          force: true,
        },
      });
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : (err as Error).message;
      window.alert(`Spostamento forzato fallito: ${msg}`);
    } finally {
      setPendingMove(null);
    }
  }, [pendingMove, spostaMutation]);

  // Sprint 8.0 MR-1 (entry 214 + 217 hotfix UX): se presente
  // ``?focusBlocco=<id>`` in URL (arrivo dal popup Cerca treno):
  //
  // 1. Attivo la variante giusta della giornata che contiene il blocco
  //    (così il blocco è effettivamente renderizzato nel Gantt).
  // 2. Scrollo la viewport del Gantt per portare il blocco in vista
  //    (smooth, centro orizzontale).
  // 3. Applico classe ``gantt-blocco-highlight`` per ~3.5s con outline
  //    pulse giallo/arancio così l'utente lo identifica immediatamente.
  // 4. Pulisco il param dall'URL così il refresh non riapplica il focus.
  //
  // Importante: NON imposto ``setSelectedBlocco`` qui — apriva il
  // ``BloccoDialog`` modal centrato che oscurava il Gantt e l'utente
  // doveva chiuderlo manualmente per vedere dove sta il treno
  // (segnalazione utente entry 217: "mi apre solo il turno ma non me
  // lo identifica portandomi comunque a cercarlo").
  useEffect(() => {
    const focusBloccoStr = searchParams.get("focusBlocco");
    if (focusBloccoStr === null) return;
    const target = Number(focusBloccoStr);
    if (Number.isNaN(target)) return;
    if (query.data === undefined) return;
    for (const g of query.data.giornate) {
      for (let vi = 0; vi < g.varianti.length; vi += 1) {
        const v = g.varianti[vi];
        const b = v.blocchi.find((x) => x.id === target);
        if (b !== undefined) {
          setActiveVariantByGiornata((prev) => ({ ...prev, [g.id]: vi }));
          // Ritardo per dare tempo al render della variante attivata
          // (la riga del Gantt potrebbe non esistere ancora se la
          // variante non era quella canonica).
          window.setTimeout(() => {
            const el = document.getElementById(`gantt-blocco-${target}`);
            if (el !== null) {
              el.scrollIntoView({
                behavior: "smooth",
                block: "center",
                inline: "center",
              });
              el.classList.add("gantt-blocco-highlight");
              window.setTimeout(() => {
                el.classList.remove("gantt-blocco-highlight");
              }, 3600);
            }
          }, 350);
          const next = new URLSearchParams(searchParams);
          next.delete("focusBlocco");
          setSearchParams(next, { replace: true });
          return;
        }
      }
    }
  }, [searchParams, query.data, setSearchParams]);

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

  return (
    <DndContext
      sensors={sensors}
      onDragStart={handleDragStart}
      onDragEnd={(e) => {
        void handleDragEnd(e);
      }}
      onDragCancel={() => setDragActiveBlocco(null)}
    >
    <div className="flex min-w-0 flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
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
        {programmaId !== null && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setCercaTrenoOpen(true)}
            title="Cerca treno tra i giri di questo programma"
          >
            <Search className="mr-1.5 h-3.5 w-3.5" aria-hidden />
            Cerca treno
          </Button>
        )}
      </div>

      <CercaTrenoDialog
        programmaId={programmaId ?? undefined}
        open={cercaTrenoOpen}
        onOpenChange={setCercaTrenoOpen}
        onSelect={(_it, b) => {
          setCercaTrenoOpen(false);
          // Stesso giro: attivo la variante + scroll + pulse direttamente
          // (no navigation). Giro diverso: navigo con ``?focusBlocco=...``
          // → l'effetto al mount fa lo stesso pattern.
          if (b.giro_id === giro.id) {
            for (const g of giro.giornate) {
              for (let vi = 0; vi < g.varianti.length; vi += 1) {
                const found = g.varianti[vi].blocchi.find((x) => x.id === b.blocco_id);
                if (found !== undefined) {
                  setActiveVariantByGiornata((prev) => ({ ...prev, [g.id]: vi }));
                  window.setTimeout(() => {
                    const el = document.getElementById(`gantt-blocco-${b.blocco_id}`);
                    if (el !== null) {
                      el.scrollIntoView({
                        behavior: "smooth",
                        block: "center",
                        inline: "center",
                      });
                      el.classList.add("gantt-blocco-highlight");
                      window.setTimeout(() => {
                        el.classList.remove("gantt-blocco-highlight");
                      }, 3600);
                    }
                  }, 250);
                  return;
                }
              }
            }
          } else {
            navigate(
              `/pianificatore-giro/giri/${b.giro_id}?focusBlocco=${b.blocco_id}`,
            );
          }
        }}
      />

      <HeroSection
        giro={giro}
        onGeneraPdc={() => setPdcDialogOpen(true)}
        onModificaMateriale={() => setEditMaterialeOpen(true)}
        onDuplica={() => {
          if (
            !window.confirm(
              `Duplicare il turno "${giro.numero_turno}" per doppia macchina?\n\n` +
                "Verrà creato un nuovo giro con suffisso -DUP-N e tutte le " +
                "giornate/varianti/blocchi clonati. Le corse referenziate restano le stesse.",
            )
          ) {
            return;
          }
          duplicaMutation.mutate(giro.id, {
            onSuccess: (res) => {
              window.alert(
                `Giro duplicato: ${res.nuovo_numero_turno}\n` +
                  `${res.n_giornate_copiate} giornate, ${res.n_varianti_copiate} varianti, ` +
                  `${res.n_blocchi_copiati} blocchi clonati.`,
              );
              navigate(`/pianificatore-giro/giri/${res.nuovo_giro_id}`);
            },
            onError: (err) => {
              const msg = err instanceof ApiError ? err.message : (err as Error).message;
              window.alert(`Duplicazione fallita: ${msg}`);
            },
          });
        }}
        duplicaPending={duplicaMutation.isPending}
      />
      <ModificaMaterialeGiroDialog
        giro={giro}
        open={editMaterialeOpen}
        onOpenChange={setEditMaterialeOpen}
      />

      <section className="flex min-w-0 flex-col gap-4">
        <div className="flex min-w-0 flex-col gap-4">
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
      </section>

      <BloccoDialog
        blocco={selectedBlocco}
        giro={giro}
        activeVariantByGiornata={activeVariantByGiornata}
        onClose={() => setSelectedBlocco(null)}
      />

      <DateApplicazioneSection giro={giro} />

      <ConvogliDelTurnoSection giroId={giro.id} />

      <GeneraTurnoPdcDialog
        giroId={giro.id}
        open={pdcDialogOpen}
        onOpenChange={setPdcDialogOpen}
      />

      {/* Sprint 8.0 MR-B.1 (entry 230) — dialog conferma spostamento
          con violazioni di fattibilità. */}
      <SpostaBloccoConfirmDialog
        pending={pendingMove}
        isPending={spostaMutation.isPending}
        onCancel={() => setPendingMove(null)}
        onConfirm={() => {
          void confermaSpostamentoForce();
        }}
      />
    </div>
    {/* DragOverlay: ghost preview del blocco trascinato, fluido stile Mac
        (segue il cursore con animation framer-style built-in di dnd-kit). */}
    <DragOverlay dropAnimation={{ duration: 220, easing: "cubic-bezier(0.18, 0.67, 0.6, 1.22)" }}>
      {dragActiveBlocco !== null ? (
        <DragGhost blocco={dragActiveBlocco} />
      ) : null}
    </DragOverlay>
    </DndContext>
  );
}

/**
 * Sprint 8.0 MR-B.1 (entry 230) — preview "ghost" del blocco trascinato.
 * Stile compatto Mac-like: pillola bianca con ombra elevata.
 */
function DragGhost({ blocco }: { blocco: GiroBlocco }) {
  const tipo = blocco.tipo_blocco;
  const numero = blocco.numero_treno ?? "—";
  return (
    <div
      className={cn(
        "pointer-events-none flex items-center gap-2 rounded-lg border bg-white/95 px-3 py-1.5 shadow-2xl backdrop-blur",
        tipo === "corsa_commerciale"
          ? "border-emerald-500/60 ring-2 ring-emerald-300/40"
          : "border-rose-400/60 ring-2 ring-rose-300/40",
      )}
      style={{ transform: "rotate(-2deg) scale(1.04)" }}
    >
      <span
        className={cn(
          "h-2 w-2 rounded-full",
          tipo === "corsa_commerciale" ? "bg-emerald-500" : "bg-rose-400",
        )}
      />
      <span className="font-mono text-[12px] font-semibold tabular-nums text-foreground">
        {numero}
      </span>
      <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
        {tipoBloccoLabel(tipo)}
      </span>
    </div>
  );
}

/**
 * Sprint 8.0 MR-B.1 (entry 230) — dialog di conferma per uno
 * spostamento che genera violazioni di fattibilità (severity=error).
 *
 * Lista le violazioni; l'utente può forzare l'operazione (force=true)
 * o annullare. Le violazioni warning (es. `pdc_stale`, gap > 5h) sono
 * mostrate come info ma non bloccano lo spostamento.
 */
function SpostaBloccoConfirmDialog({
  pending,
  isPending,
  onCancel,
  onConfirm,
}: {
  pending: {
    blocco: GiroBlocco;
    giornataTarget: number;
    variantIndexTarget: number;
    response: SpostaBloccoResponse;
  } | null;
  isPending: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const open = pending !== null;
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-600" aria-hidden />
            Spostamento con violazioni
          </DialogTitle>
          <DialogDescription>
            {pending !== null && (
              <>
                Lo spostamento del blocco{" "}
                <span className="font-mono font-medium">
                  {pending.blocco.numero_treno ?? `#${pending.blocco.id}`}
                </span>{" "}
                a giornata {pending.giornataTarget} (variante{" "}
                {pending.variantIndexTarget}) genera{" "}
                {pending.response.violazioni.length} segnalazioni.
                Verifica e conferma se vuoi forzare l'operazione.
              </>
            )}
          </DialogDescription>
        </DialogHeader>

        {pending !== null && (
          <ul className="max-h-72 space-y-1.5 overflow-y-auto rounded-md border border-border bg-muted/20 p-3 text-sm">
            {pending.response.violazioni.map((v, i) => (
              <ViolazioneRow key={i} v={v} />
            ))}
          </ul>
        )}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={onCancel}
            disabled={isPending}
          >
            Annulla
          </Button>
          <Button onClick={onConfirm} disabled={isPending}>
            {isPending ? "Sposto…" : "Forza spostamento"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ViolazioneRow({ v }: { v: ViolazioneFattibilita }) {
  return (
    <li
      className={cn(
        "flex items-start gap-2 rounded px-2 py-1.5",
        v.severity === "error"
          ? "bg-destructive/5 text-destructive"
          : "bg-amber-50 text-amber-900",
      )}
    >
      <span className="mt-0.5 inline-flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-full text-[9px] font-bold uppercase">
        {v.severity === "error" ? "!" : "i"}
      </span>
      <div className="flex-1">
        <div className="text-xs font-medium uppercase tracking-wide">
          {v.codice} · {v.variante_label}
        </div>
        <div className="text-[13px] leading-snug">{v.descrizione}</div>
      </div>
    </li>
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
    <Card id="convogli-del-turno" className="overflow-hidden scroll-mt-4">
      <div className="border-b border-border bg-muted/40 px-4 py-2.5 text-xs">
        <div>
          <span className="font-medium uppercase tracking-wide text-foreground">
            Convogli del turno (thread L2)
          </span>
          <span className="ml-3 text-muted-foreground">
            {threads.length} pezz{threads.length === 1 ? "o" : "i"} fisic
            {threads.length === 1 ? "o" : "i"} proiettat{threads.length === 1 ? "o" : "i"}
          </span>
        </div>
        {/* Sprint 7.9 MR δ.3 (entry 143): paragrafo esplicativo. Decisione
            utente: "non capisco il senso del secondo screen" — chiarire
            che ogni riga è un convoglio fisico (pezzo) che gira in
            parallelo agli altri per coprire il giro intero. */}
        <p className="mt-1 max-w-3xl text-[11px] leading-snug text-muted-foreground/90">
          {threads.length > 0 ? (
            <>
              {threads.length === 1
                ? "Un singolo convoglio fisico"
                : `I ${threads.length} convogli fisici`}{" "}
              che servono per coprire questo giro contemporaneamente: ogni
              riga è un pezzo distinto del materiale, con la sua sequenza di
              corse (km, minuti, n° corse del singolo pezzo). La matricola
              effettiva (es. ETR421-007) viene assegnata dal ruolo
              Manutenzione. "Apri →" mostra la timeline dettagliata del
              singolo convoglio.
            </>
          ) : null}
        </p>
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
  onModificaMateriale,
  onDuplica,
  duplicaPending,
}: {
  giro: GiroDettaglio;
  onGeneraPdc: () => void;
  onModificaMateriale: () => void;
  onDuplica: () => void;
  duplicaPending: boolean;
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
            onClick={onModificaMateriale}
            title="MR η: modifica il materiale assegnato a questo giro"
          >
            <Pencil className="mr-2 h-4 w-4" aria-hidden /> Modifica materiale
          </Button>
          <Button
            variant="outline"
            size="md"
            onClick={onDuplica}
            disabled={duplicaPending}
            title="MR η-bis: clona giro completo per doppia macchina"
          >
            <Copy className="mr-2 h-4 w-4" aria-hidden />
            {duplicaPending ? "Duplicazione…" : "Duplica turno"}
          </Button>
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
            // Sprint 7.9 MR η.1 — entry-point ridondante: oltre al
            // bottone "Genera turno PdC" nell'header card, rendo
            // cliccabile anche questa meta-cell. Difesa contro estensioni
            // browser / regole CSS site-wide che a volte nascondono i
            // button primary nell'header.
            <button
              type="button"
              onClick={onGeneraPdc}
              className="inline-flex items-center gap-1 text-primary underline-offset-2 hover:underline"
              title="Genera turno PdC da questo giro materiale"
            >
              non generati · genera ora →
            </button>
          )}
        </MetaItem>
      </div>

      {/* Sprint 7.9 MR η.1 — banda CTA "Genera turno PdC" sotto la
          Hero. È RIDONDANTE rispetto al bottone primary in alto a
          destra ma serve come safety-net se l'header collassa per
          qualche motivo (vedi screenshot smoke 2026-05-05) o se
          l'utente non lo vede subito. Non viene renderizzata se
          esistono già turni PdC: l'utente li ha, vede solo il link
          "N generati →" sopra. */}
      {turni.length === 0 && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-primary/30 bg-primary/[0.04] px-4 py-3">
          <div className="flex flex-col gap-0.5 text-sm">
            <span className="font-semibold text-foreground">
              Pronto per generare il turno PdC
            </span>
            <span className="text-xs text-muted-foreground">
              Il builder propone automaticamente i 3 depositi PdC che
              minimizzano i pernotti fuori sede. Cliccando sotto si apre
              il dialog di generazione.
            </span>
          </div>
          <Button variant="primary" size="md" onClick={onGeneraPdc}>
            <Users className="mr-2 h-4 w-4" aria-hidden /> Genera turno PdC
          </Button>
        </div>
      )}
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

// =====================================================================
// MR η — Dialog "Modifica materiale del giro"
// =====================================================================

/**
 * MR η (2026-05-06) — dialog per modificare il materiale del giro
 * generato. Apre dropdown con tutti i ``MaterialeTipo`` macro
 * dell'azienda; al submit invia ``PATCH /api/giri/{id}`` aggiornando
 * sia il codice (``materiale_tipo_codice``) sia i campi denormalizzati
 * (``tipo_materiale``, ``descrizione_materiale``).
 *
 * Errori 409 dal backend (freeze pipeline ``>= MATERIALE_CONFERMATO``)
 * mostrati inline.
 *
 * Scope MVP: solo cambio materiale dell'header del giro. Le azioni
 * "doppia composizione" (doppia macchina) e "sgancio" agiscono sui
 * blocchi e sono scope di un MR η-bis futuro.
 */
function ModificaMaterialeGiroDialog({
  giro,
  open,
  onOpenChange,
}: {
  giro: GiroDettaglio;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const materialiQuery = useMateriali({ enabled: open });
  const patchMutation = usePatchGiro();
  const [selected, setSelected] = useState(giro.materiale_tipo_codice ?? "");
  const [error, setError] = useState<string | null>(null);

  // Resync quando il giro o l'open cambia.
  useEffect(() => {
    if (open) {
      setSelected(giro.materiale_tipo_codice ?? "");
      setError(null);
    }
  }, [open, giro.materiale_tipo_codice]);

  const materialiMacro = useMemo(() => {
    const data = materialiQuery.data;
    if (!Array.isArray(data)) return [];
    return data.filter((m) => m != null && m.famiglia != null && m.famiglia.length > 0);
  }, [materialiQuery.data]);

  const handleClose = (next: boolean) => {
    if (!next) setError(null);
    onOpenChange(next);
  };

  const handleSubmit = async () => {
    if (selected.length === 0) {
      setError("Seleziona un materiale.");
      return;
    }
    setError(null);
    const m = materialiMacro.find((x) => x.codice === selected);
    try {
      await patchMutation.mutateAsync({
        giroId: giro.id,
        payload: {
          materiale_tipo_codice: selected,
          tipo_materiale: m?.codice ?? selected,
          descrizione_materiale: m?.nome_commerciale ?? null,
        },
      });
      handleClose(false);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Errore sconosciuto",
      );
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Modifica materiale del giro</DialogTitle>
          <DialogDescription>
            Cambia il materiale assegnato a <strong>{giro.numero_turno}</strong>. La
            modifica aggiorna l&apos;header del giro; non modifica gli orari né i blocchi
            del Gantt.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="giro-materiale">Materiale</Label>
            <Select
              id="giro-materiale"
              value={selected}
              disabled={patchMutation.isPending || materialiQuery.isLoading}
              onChange={(e) => setSelected(e.target.value)}
            >
              <option value="">— scegli —</option>
              {materialiMacro.map((m) => (
                <option key={m.codice} value={m.codice}>
                  {m.codice}
                  {m.nome_commerciale != null && m.nome_commerciale !== ""
                    ? ` — ${m.nome_commerciale}`
                    : ""}
                </option>
              ))}
            </Select>
            <p className="text-xs text-muted-foreground">
              MR η scope MVP: cambia solo il materiale dell&apos;header. Doppia composizione
              (doppia macchina) e sgancio sui blocchi sono in arrivo come MR η-bis.
            </p>
          </div>

          {error !== null && (
            <p
              role="alert"
              className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
            >
              {error}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => handleClose(false)} disabled={patchMutation.isPending}>
            Annulla
          </Button>
          <Button
            onClick={() => void handleSubmit()}
            disabled={patchMutation.isPending || selected.length === 0}
          >
            {patchMutation.isPending ? <Spinner label="Salvataggio…" /> : "Salva"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
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

  // Sprint 8.0 entry 204 (sotto-MR 9 Step A): nesting varianti.
  // Default per ogni giornata = collapsed (mostra solo la variante
  // canonica idx 0); click sull'header espande tutte le varianti come
  // righe separate. Stato persistito in localStorage per giornata.id.
  const [expandedGiornate, setExpandedGiornate] = useState<Set<number>>(() =>
    readPersistedExpanded(),
  );
  const toggleExpanded = (giornataId: number) => {
    setExpandedGiornate((prev) => {
      const next = new Set(prev);
      if (next.has(giornataId)) {
        next.delete(giornataId);
      } else {
        next.add(giornataId);
      }
      persistExpanded(next);
      return next;
    });
  };
  // Helper: espandi/comprimi tutte le giornate con varianti multiple.
  const giornateConVariantiMultiple = useMemo(
    () => giro.giornate.filter((g) => g.varianti.length > 1).map((g) => g.id),
    [giro.giornate],
  );
  const allExpanded =
    giornateConVariantiMultiple.length > 0 &&
    giornateConVariantiMultiple.every((id) => expandedGiornate.has(id));
  const expandAll = () => {
    setExpandedGiornate(() => {
      const next = new Set(giornateConVariantiMultiple);
      persistExpanded(next);
      return next;
    });
  };
  const collapseAll = () => {
    setExpandedGiornate(() => {
      const next = new Set<number>();
      persistExpanded(next);
      return next;
    });
  };

  // Sprint 7.10 MR α.8 (2026-05-05): vista fullscreen del Gantt giro
  // materiale. Decisione utente "non si vede tutto il turno, viene
  // tagliato ai lati" — il Gantt incastrato fra HeroSection e
  // ConvogliDelTurnoSection ha poco respiro verticale e la sidebar
  // toglie 240+ px in orizzontale. Il fullscreen lo rende
  // protagonista della viewport, mantenendo zoom + scroll + click
  // blocco (BloccoDialog si apre sopra il fullscreen).
  const [isFullscreen, setIsFullscreen] = useState(false);
  useEffect(() => {
    if (!isFullscreen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsFullscreen(false);
    };
    window.addEventListener("keydown", handler);
    const orig = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", handler);
      document.body.style.overflow = orig;
    };
  }, [isFullscreen]);

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
  // Sprint 7.9 MR δ.4 (entry 144): su Mac/Chrome la scrollbar orizzontale
  // è nascosta di default → l'utente non capisce di poter scrollare. Se
  // il content eccede il container mostriamo bottoni ← / → in toolbar
  // che scrollano programmaticamente (anche con shift+wheel come prima).
  const hasOverflow = containerWidth > 0 && innerWidth > containerWidth + 1;
  const handleScrollBy = (delta: number) => {
    scrollWrapperRef.current?.scrollBy({ left: delta, behavior: "smooth" });
  };

  return (
    <GanttScaleContext.Provider value={scale}>
      {isFullscreen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
          onClick={() => setIsFullscreen(false)}
          aria-hidden
        />
      )}
      <Card
        className={cn(
          // Sprint 7.10 MR α.8.fix: `min-w-0` sul Card è il vero
          // firewall. Il Card è flex-item del wrapper esterno della
          // pagina (anche lui min-w-0). Senza min-w-0 sul Card
          // stesso, il scroll-wrapper interno con `style={{ width:
          // 2140px }}` (a zoom 200%) propaga la min-content fino al
          // Card e oltre, espandendo la toolbar e spingendo la
          // sezione destra fuori viewport.
          "min-w-0 overflow-hidden",
          selectedBlocco !== null && "gantt-selecting",
          // Sprint 7.10 MR α.8: in fullscreen il Card occupa la
          // viewport (inset-2 = 8px da ogni bordo) e diventa flex-col
          // così lo scroll wrapper sotto può prendersi tutto lo
          // spazio verticale residuo (flex-1 min-h-0).
          isFullscreen && "fixed inset-2 z-50 flex flex-col shadow-2xl",
        )}
      >
        {/* Toolbar — sticky così resta visibile (zoom + bottoni scroll)
            anche quando l'utente scrolla la pagina principale per leggere
            il Gantt esteso. */}
        <div className="sticky top-0 z-40 flex flex-wrap items-center justify-between gap-3 border-b border-border bg-muted/95 px-4 py-2.5 text-xs backdrop-blur-sm">
          {/* Sezione sinistra: titolo + meta. `min-w-0` permette il
              truncate sulla label lunga; senza, il flex-wrap non si
              attiva mai e la sezione destra finisce fuori viewport. */}
          <div className="flex min-w-0 items-center gap-3 text-muted-foreground">
            <span className="font-medium uppercase tracking-wide text-foreground">Gantt giro</span>
            <span className="text-border">·</span>
            <span className="truncate">
              {giro.giornate.length} giornat{giro.giornate.length === 1 ? "a" : "e"} ·{" "}
              {stats.nVariantiTotale} variant{stats.nVariantiTotale === 1 ? "e" : "i"} calendarial
              {stats.nVariantiTotale === 1 ? "e" : "i"}
            </span>
          </div>
          {/* Sezione destra: zoom + scroll + fullscreen. `shrink-0`
              così questi controlli restano sempre visibili anche
              quando la sezione sinistra è larga. */}
          <div className="flex shrink-0 items-center gap-3 text-muted-foreground/80">
            {hasOverflow && (
              <div className="inline-flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => handleScrollBy(-Math.round(containerWidth * 0.6))}
                  aria-label="Scorri Gantt a sinistra"
                  title="Scorri a sinistra (anche shift+wheel)"
                  className="rounded border border-border bg-white p-1 text-muted-foreground hover:bg-muted"
                >
                  <ChevronLeft className="h-3.5 w-3.5" aria-hidden />
                </button>
                <button
                  type="button"
                  onClick={() => handleScrollBy(Math.round(containerWidth * 0.6))}
                  aria-label="Scorri Gantt a destra"
                  title="Scorri a destra (anche shift+wheel)"
                  className="rounded border border-border bg-white p-1 text-muted-foreground hover:bg-muted"
                >
                  <ChevronRight className="h-3.5 w-3.5" aria-hidden />
                </button>
                <span className="text-border">·</span>
              </div>
            )}
            <ZoomToggle current={zoom} onChange={handleZoomChange} />
            <span className="text-border">·</span>
            <span className="tabular-nums">
              1h = {Math.round(scale.pxPerHour)}px
            </span>
            {giornateConVariantiMultiple.length > 0 && (
              <>
                <span className="text-border">·</span>
                <button
                  type="button"
                  onClick={allExpanded ? collapseAll : expandAll}
                  aria-label={
                    allExpanded
                      ? "Comprimi tutte le varianti"
                      : "Espandi tutte le varianti"
                  }
                  title={
                    allExpanded
                      ? "Comprimi tutte le varianti calendariali"
                      : `Espandi tutte le varianti calendariali (${giornateConVariantiMultiple.length} giornate con varianti multiple)`
                  }
                  className="inline-flex items-center gap-1 rounded border border-border bg-white px-2 py-1 text-[10px] font-medium text-muted-foreground hover:bg-muted"
                >
                  {allExpanded ? (
                    <ChevronDown className="h-3 w-3" aria-hidden />
                  ) : (
                    <ChevronRight className="h-3 w-3" aria-hidden />
                  )}
                  {allExpanded ? "Comprimi varianti" : "Espandi varianti"}
                </button>
              </>
            )}
            <span className="text-border">·</span>
            <button
              type="button"
              onClick={() => setIsFullscreen((v) => !v)}
              aria-label={isFullscreen ? "Riduci Gantt" : "Espandi Gantt a tutta pagina"}
              title={isFullscreen ? "Riduci Gantt (Esc)" : "Espandi Gantt a tutta pagina"}
              className="rounded border border-border bg-white p-1 text-muted-foreground hover:bg-muted"
            >
              {isFullscreen ? (
                <Minimize2 className="h-3.5 w-3.5" aria-hidden />
              ) : (
                <Maximize2 className="h-3.5 w-3.5" aria-hidden />
              )}
            </button>
          </div>
        </div>

        {/* Scroll wrapper — overflow-x esplicito + scrollbar sempre visibile
            anche su macOS (Chrome/Safari nascondono la barra di default,
            l'utente non si accorge di poter scrollare). Sprint 7.9 MR δ.5
            (entry 145): rimosso `maxHeight: 700px` che causava scroll-y
            interno → la scrollbar-x finiva in fondo ai 700px e non era
            visibile. Ora lo scroll-y è a livello pagina (main overflow-auto)
            e la scrollbar-x sta subito sotto il Gantt. */}
        <div
          ref={scrollWrapperRef}
          className={cn(
            "gantt-scroll relative overflow-x-auto pb-1",
            // In fullscreen il wrapper deve prendersi tutto lo spazio
            // verticale del Card (Card è flex-col) e abilitare lo
            // scroll-y interno: senza min-h-0 il flex-1 collassa.
            isFullscreen && "flex-1 min-h-0 overflow-y-auto",
          )}
        >
          <div className="relative" style={{ width: `${innerWidth}px` }}>
            {/* Sticky header X axis */}
            <AxisHeader />

            {/* Per giornata: header row + 1 o N variante row + (notte band se non ultima)
                Sprint 8.0 entry 204: nesting collassabile. Default = solo
                la variante "active" (canonica idx 0). Se la giornata è in
                expandedGiornate → tutte le varianti come righe separate. */}
            {giro.giornate.map((g, idx) => {
              const activeIdx = activeVariantByGiornata[g.id] ?? 0;
              const isExpanded = expandedGiornate.has(g.id);
              const hasMultiple = g.varianti.length > 1;
              const variantiDaMostrare = isExpanded
                ? g.varianti
                : g.varianti.slice(activeIdx, activeIdx + 1);
              const next = giro.giornate[idx + 1];
              return (
                <div key={g.id}>
                  <GiornataHeaderRow
                    giornata={g}
                    activeIdx={activeIdx}
                    selectedClusterA1Ids={selectedClusterA1Ids}
                    onChangeActive={(i) => onChangeActiveVariant(g.id, i)}
                    expanded={isExpanded}
                    onToggleExpand={
                      hasMultiple ? () => toggleExpanded(g.id) : null
                    }
                  />
                  {variantiDaMostrare.map((v) => (
                    <VarianteRow
                      key={v.id}
                      giornata={g}
                      variante={v}
                      isCanonica={v.variant_index === 0}
                      isInExpandedGroup={isExpanded && hasMultiple}
                      selectedBloccoId={selectedBlocco?.id ?? null}
                      onSelectBlocco={onSelectBlocco}
                    />
                  ))}
                  {next !== undefined && (
                    <NotteRow giornataPrev={g} giornataNext={next} activeVariantByGiornata={activeVariantByGiornata} />
                  )}
                </div>
              );
            })}

            {/* Totali */}
            <TotaliRow giro={giro} stats={stats} />

            {/* Sprint 8.0 entry 204 (Step B): banner ciclo chiuso
                G_N → G_1. Mostra se l'ultima stazione del giro coincide
                con la prima (= il convoglio fisico chiude il loop e
                ricomincia). */}
            <CicloChiusoBanner giro={giro} />
          </div>
        </div>

        {/* Legenda */}
        <Legenda />
      </Card>
    </GanttScaleContext.Provider>
  );
}

/**
 * Sprint 8.0 entry 204 (sotto-MR 9 Step B): banner finale del Gantt che
 * riassume la chiusura del ciclo. Calcola la stazione di terminazione
 * della variante canonica dell'ultima giornata e quella di partenza
 * della variante canonica della prima. Se coincidono, il giro materiale
 * "chiude" e il convoglio è pronto a ripartire dal G1 il giorno dopo
 * (rotazione realistica). Se non coincidono, c'è un cap di km/sede o
 * un'anomalia.
 */
function CicloChiusoBanner({ giro }: { giro: GiroDettaglio }) {
  const giornate = giro.giornate;
  if (giornate.length === 0) return null;
  const prima = giornate[0];
  const ultima = giornate[giornate.length - 1];
  const variantePrima = prima.varianti[0];
  const varianteUltima = ultima.varianti[0];
  if (variantePrima === undefined || varianteUltima === undefined) return null;
  // Stazione di partenza G1 = primo blocco (per ora_inizio).
  const blocchiPrimaOrd = [...variantePrima.blocchi]
    .filter((b) => parseTimeToMin(b.ora_inizio) !== null)
    .sort(
      (a, b) =>
        (parseTimeToMin(a.ora_inizio) ?? 0) - (parseTimeToMin(b.ora_inizio) ?? 0),
    );
  // Stazione di terminazione GN = ultimo blocco (per ora_fine).
  const blocchiUltOrd = [...varianteUltima.blocchi]
    .filter((b) => parseTimeToMin(b.ora_fine) !== null)
    .sort(
      (a, b) =>
        (parseTimeToMin(b.ora_fine) ?? 0) - (parseTimeToMin(a.ora_fine) ?? 0),
    );
  const primoBlocco = blocchiPrimaOrd[0];
  const ultimoBlocco = blocchiUltOrd[0];
  if (primoBlocco === undefined || ultimoBlocco === undefined) return null;
  const stazPartenza = primoBlocco.stazione_da_codice;
  const stazArrivo = ultimoBlocco.stazione_a_codice;
  const stazPartenzaLabel =
    primoBlocco.stazione_da_nome ?? stazPartenza ?? "?";
  const stazArrivoLabel = ultimoBlocco.stazione_a_nome ?? stazArrivo ?? "?";
  const chiude =
    stazPartenza !== null &&
    stazArrivo !== null &&
    stazPartenza === stazArrivo;
  return (
    <div
      className={cn(
        "flex items-center gap-2 border-t px-4 py-2 text-[11px]",
        chiude
          ? "border-emerald-200 bg-emerald-50 text-emerald-900"
          : "border-amber-300 bg-amber-50 text-amber-900",
      )}
      title={
        chiude
          ? `Il giro chiude il ciclo: G${ultima.numero_giornata} termina nella stessa stazione (${stazArrivoLabel}) da cui parte G1 — il convoglio è pronto a ripartire.`
          : `Il giro NON chiude il ciclo: G${ultima.numero_giornata} termina a ${stazArrivoLabel}, ma G1 parte da ${stazPartenzaLabel}. Possibili cause: cap km raggiunto, sede di rientro diversa, o anomalia builder.`
      }
    >
      <span className="text-base leading-none">{chiude ? "🔁" : "⚠"}</span>
      <span className="font-medium uppercase tracking-wide">
        {chiude ? "Ciclo chiuso" : "Ciclo aperto"}
      </span>
      <span className="text-border">·</span>
      <span>
        G{ultima.numero_giornata} termina a{" "}
        <span className="font-mono font-semibold">{stazArrivoLabel}</span>
      </span>
      <span className="text-border">→</span>
      <span>
        G1 parte da{" "}
        <span className="font-mono font-semibold">{stazPartenzaLabel}</span>
      </span>
      {chiude ? (
        <span className="ml-auto italic opacity-80">
          stessa stazione · convoglio pronto al ciclo successivo
        </span>
      ) : (
        <span className="ml-auto italic opacity-80">stazioni diverse</span>
      )}
    </div>
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
  expanded,
  onToggleExpand,
}: {
  giornata: GiroGiornata;
  activeIdx: number;
  selectedClusterA1Ids: Set<number> | null;
  onChangeActive: (idx: number) => void;
  /** Sprint 8.0 entry 204: stato "varianti espanse" per la giornata. */
  expanded: boolean;
  /** ``null`` se la giornata ha 1 sola variante (toggle non ha senso). */
  onToggleExpand: (() => void) | null;
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
        {/* Sprint 8.0 entry 204 — Step A: bottone expand/collapse per
            mostrare TUTTE le varianti come righe separate. Visibile solo
            se la giornata ha 2+ varianti. Quando collapsed, le tab sono
            interattive (cambia variante visualizzata); quando expanded,
            le tab diventano evidenziatori della variante "active" perché
            tutte sono già rese come righe sotto. */}
        {hasMultiple && onToggleExpand !== null && (
          <button
            type="button"
            onClick={onToggleExpand}
            aria-expanded={expanded}
            aria-label={
              expanded
                ? `Comprimi varianti giornata ${giornata.numero_giornata}`
                : `Espandi ${varianti.length} varianti giornata ${giornata.numero_giornata}`
            }
            title={
              expanded
                ? "Comprimi: mostra solo la variante canonica"
                : `Espandi: mostra tutte le ${varianti.length} varianti calendariali`
            }
            className="inline-flex items-center gap-1 rounded border border-border bg-white px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground hover:bg-muted"
          >
            {expanded ? (
              <ChevronDown className="h-3 w-3" aria-hidden />
            ) : (
              <ChevronRight className="h-3 w-3" aria-hidden />
            )}
            {varianti.length} varianti
          </button>
        )}
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
        {hasMultiple && !expanded && (
          <span className="ml-2 text-[10px] italic text-muted-foreground/70">
            stai vedendo "{truncateLabel(active?.etichetta_parlante ?? "")}"
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

/**
 * Sprint 8.0 entry 204 — Step A: prestazione (durata) della variante in
 * minuti. Calcolato client-side da `ora_inizio` del primo blocco
 * significativo a `ora_fine` dell'ultimo, gestendo cross-mezzanotte
 * (se ora_fine < ora_inizio, +1440). Ritorna ``null`` se non ci sono
 * blocchi o gli orari mancano.
 *
 * In futuro (sotto-MR 6 persister v2) il backend popolerà direttamente
 * `prestazione_minuti` su ``GiroVariante`` — basterà sostituire la
 * fonte senza toccare l'UI.
 */
function computePrestazioneVariante(
  blocchiOrdinati: GiroBlocco[],
): number | null {
  if (blocchiOrdinati.length === 0) return null;
  const primo = blocchiOrdinati[0];
  const ultimo = blocchiOrdinati[blocchiOrdinati.length - 1];
  const inizio = parseTimeToMin(primo.ora_inizio);
  const fineUlt = parseTimeToMin(ultimo.ora_fine);
  if (inizio === null || fineUlt === null) return null;
  // Anche l'ora_inizio dell'ultimo, per intercettare cross-mezzanotte
  // (se ora_inizio dell'ultimo > ora_fine, l'ultimo blocco stesso
  // attraversa la mezzanotte → ora_fine_corretto = ora_fine + 1440).
  const inizioUlt = parseTimeToMin(ultimo.ora_inizio) ?? fineUlt;
  let fineCorretto = fineUlt;
  if (fineUlt < inizioUlt) fineCorretto = fineUlt + 1440;
  if (fineCorretto < inizio) fineCorretto = fineCorretto + 1440;
  return fineCorretto - inizio;
}

/** Sprint 8.0 entry 204 — Step A: formatta minuti come "Xh Ym" / "Ym". */
function formatPrestazione(min: number): string {
  if (min < 60) return `${min}m`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m === 0 ? `${h}h` : `${h}h${String(m).padStart(2, "0")}`;
}

// =====================================================================
// Variante row — single-line timeline
// =====================================================================

function VarianteRow({
  giornata,
  variante,
  isCanonica,
  isInExpandedGroup,
  selectedBloccoId,
  onSelectBlocco,
}: {
  giornata: GiroGiornata;
  variante: GiroVariante;
  /** Sprint 8.0 entry 204: la variante 0 è "canonica" — usiamo
   * `giornata.km_giornata` come km della variante (il backend persiste
   * solo il km della canonica). Per le altre, fallback "—". */
  isCanonica: boolean;
  /** ``true`` se la giornata è espansa e questa è una delle N righe
   * sorelle. Aggiunge un indicatore visuale (rientro + barra colorata)
   * per leggere il gruppo. */
  isInExpandedGroup: boolean;
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

  // Sprint 8.0 entry 204 — Step A: Per/Km PER variante (non più per
  // giornata). "Per" = prestazione minuti calcolata client-side (primo
  // ora_inizio → ultimo ora_fine, gestione cross-mezzanotte). "Km" =
  // backend espone solo `giornata.km_giornata` per la variante canonica
  // (variant_index 0); per le altre varianti mostriamo "—" finché il
  // sotto-MR 6 (persister v2) popola km per variante. Né più né meno.
  const prestazioneMinuti = useMemo(
    () => computePrestazioneVariante(blocchiOrdinati),
    [blocchiOrdinati],
  );
  const per =
    prestazioneMinuti !== null ? formatPrestazione(prestazioneMinuti) : "—";
  const km =
    isCanonica && giornata.km_giornata !== null
      ? formatNumber(Math.round(giornata.km_giornata))
      : "—";

  return (
    <div
      className={cn(
        "relative flex border-b border-border",
        // In modalità "espansa", aggiunge una sottile barra a sinistra
        // per legare visivamente le N varianti come gruppo della stessa
        // giornata. La canonica ha barra più pronunciata.
        isInExpandedGroup && "border-l-2",
        isInExpandedGroup && (isCanonica ? "border-l-foreground/40" : "border-l-foreground/15"),
      )}
    >
      {/* Label col sticky-left */}
      <div
        className="sticky left-0 z-20 flex flex-col justify-center border-r border-border bg-white px-3 py-3"
        style={{ width: GIORNATA_LABEL_COL_PX }}
      >
        <div
          className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground"
          title={variante.etichetta_parlante}
        >
          {truncateLabel(variante.etichetta_parlante)}
        </div>
        {isInExpandedGroup && isCanonica && (
          <div className="mt-0.5 text-[9px] font-medium uppercase tracking-wider text-foreground/60">
            canonica
          </div>
        )}
        {variante.dates_apply_json.length > 0 && (
          <div className="text-[9px] italic text-muted-foreground/70">
            {variante.dates_apply_json.length} dat
            {variante.dates_apply_json.length === 1 ? "a" : "e"}
          </div>
        )}
      </div>

      {/* Timeline — Sprint 8.0 MR-B.1 (entry 230): droppable per
          drag&drop blocchi tra giornate/varianti. */}
      <DroppableTimeline
        varianteId={variante.id}
        giornataNumero={giornata.numero_giornata}
        variantIndex={variante.variant_index}
        widthPx={timelineWidthPx}
        heightPx={TIMELINE_ROW_HEIGHT_PX}
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

        {/* Blocchi posizionati — Sprint 8.0 MR-B.1 (entry 230):
            ognuno wrappato in DraggableBloccoSegment per il drag&drop
            tra giornate/varianti. */}
        {blocchi.map((b) => (
          <DraggableBloccoSegment
            key={b.id}
            blocco={b}
            varianteId={variante.id}
            selected={b.id === selectedBloccoId}
            isFirstOfRow={b.id === firstId}
            isLastOfRow={b.id === lastId}
            onSelect={() => onSelectBlocco(b)}
          />
        ))}
      </DroppableTimeline>

      {/* Per + Km sticky-right (Sprint 8.0 entry 204: per variante) */}
      <div
        className="sticky right-0 z-20 flex border-l border-border bg-white"
        style={{ width: PER_KM_COL_PX }}
      >
        <div
          className="flex w-1/2 items-center justify-center border-r border-border font-mono text-sm tabular-nums text-foreground"
          title={
            prestazioneMinuti !== null
              ? `Prestazione variante: ${prestazioneMinuti} min`
              : "Prestazione non calcolabile (blocchi senza orari)"
          }
        >
          {per}
        </div>
        <div
          className="flex w-1/2 items-center justify-center font-mono text-sm tabular-nums text-foreground"
          title={
            isCanonica
              ? giornata.km_giornata !== null
                ? `Km giornata canonica: ${Math.round(giornata.km_giornata)}`
                : "Km giornata non disponibile"
              : "Km variante non canonica: il backend popola km solo per la canonica (sotto-MR 6 persister v2)"
          }
        >
          {km}
        </div>
      </div>
    </div>
  );
}

// =====================================================================
// Blocco segment — render diverso per tipo
// =====================================================================

/**
 * Sprint 8.0 MR-B.1 (entry 230) — wrapper droppable della timeline di
 * una variante. Sprint 8.0 MR-A (entry 231): aggiunto `giroId`
 * opzionale per drag&drop cross-turno (vista aggregata).
 */
export function DroppableTimeline({
  varianteId,
  giornataNumero,
  variantIndex,
  giroId,
  widthPx,
  heightPx,
  children,
}: {
  varianteId: number;
  giornataNumero: number;
  variantIndex: number;
  /** MR-A entry 231: id del giro proprietario della variante. */
  giroId?: number;
  widthPx: number;
  heightPx: number;
  children: React.ReactNode;
}) {
  const { setNodeRef, isOver } = useDroppable({
    id: `variante-${varianteId}`,
    data: { varianteId, giornataNumero, variantIndex, giroId },
  });
  return (
    <div
      ref={setNodeRef}
      className={cn(
        "ticks-bg relative transition-colors",
        isOver && "bg-primary/8 ring-2 ring-primary/40 ring-inset",
      )}
      style={{ width: widthPx, height: heightPx }}
    >
      {children}
    </div>
  );
}

/**
 * Sprint 8.0 MR-B.1 (entry 230) — wrapper draggable per BloccoSegment.
 * Sprint 8.0 MR-A (entry 231): aggiunto `giroId` opzionale per
 * drag&drop cross-turno (vista aggregata).
 */
export function DraggableBloccoSegment({
  varianteId,
  giroId,
  ...rest
}: {
  blocco: GiroBlocco;
  varianteId: number;
  /** MR-A entry 231: id del giro proprietario del blocco. */
  giroId?: number;
  selected: boolean;
  isFirstOfRow: boolean;
  isLastOfRow: boolean;
  onSelect: () => void;
}) {
  const { setNodeRef, listeners, attributes, isDragging } = useDraggable({
    id: `blocco-${rest.blocco.id}`,
    data: { blocco: rest.blocco, varianteId, giroId },
  });
  return (
    <BloccoSegment
      {...rest}
      dragRef={setNodeRef}
      dragListeners={listeners}
      dragAttributes={attributes}
      isDragging={isDragging}
    />
  );
}

interface DragProps {
  dragRef?: (el: HTMLElement | null) => void;
  dragListeners?: SyntheticListenerMap | undefined;
  dragAttributes?: DraggableAttributes;
  isDragging?: boolean;
}

function BloccoSegment({
  blocco,
  selected,
  isFirstOfRow,
  isLastOfRow,
  onSelect,
  dragRef,
  dragListeners,
  dragAttributes,
  isDragging,
}: {
  blocco: GiroBlocco;
  selected: boolean;
  isFirstOfRow: boolean;
  isLastOfRow: boolean;
  onSelect: () => void;
} & DragProps) {
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
        dragRef={dragRef}
        dragListeners={dragListeners}
        dragAttributes={dragAttributes}
        isDragging={isDragging}
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
    // Sprint 7.9 MR δ.3 (entry 143): soglie abbassate ora che le label
    // intermedie sono acronimi 2-4 char ("MiPG", "Lc"); 30/25 px
    // bastano a renderizzare leggibilmente. Era 47/33 quando le label
    // erano nomi pieni troncati (MR γ).
    const showStazioni = widthPx >= 30;
    const showOrari = widthPx >= 25;
    return (
      <button
        type="button"
        id={`gantt-blocco-${blocco.id}`}
        ref={dragRef}
        {...(dragListeners ?? {})}
        {...(dragAttributes ?? {})}
        onClick={onSelect}
        title={tooltip}
        aria-pressed={selected}
        className={cn(
          "blk absolute overflow-hidden",
          selected && "is-selected",
          isDragging === true && "opacity-30",
        )}
        style={{
          left: startPx,
          top: 24,
          width: widthPx,
          touchAction: "none",
        }}
      >
        {/* Sprint 8.0 MR-B.3 (entry 233): badge ×N + sgancio anche su vuoti. */}
        {(() => {
          const m = blocco.metadata_json ?? {};
          const np = typeof m.n_pezzi === "number" ? m.n_pezzi : 1;
          if (np >= 2) {
            return (
              <span
                className="absolute right-0.5 top-0.5 z-10 inline-flex items-center rounded bg-amber-500 px-1 py-px text-[9px] font-bold leading-none text-white shadow"
                title={`Doppia composizione (${np} pezzi)`}
              >
                ×{np}
              </span>
            );
          }
          return null;
        })()}
        {(blocco.metadata_json?.is_sgancio === true) && (
          <span
            className="absolute -right-1 top-1/2 z-10 -translate-y-1/2 rounded-full bg-orange-600 p-0.5 text-white shadow"
            title="Sgancio: il materiale si separa dopo questo blocco"
          >
            <Unlink className="h-2.5 w-2.5" aria-hidden />
          </span>
        )}
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
  dragRef,
  dragListeners,
  dragAttributes,
  isDragging,
}: {
  blocco: GiroBlocco;
  startPx: number;
  widthPx: number;
  selected: boolean;
  isFirstOfRow: boolean;
  isLastOfRow: boolean;
  onSelect: () => void;
  tooltip: string;
} & DragProps) {
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
  // 2/3): 70→47, 50→33. Sprint 7.9 MR δ.3 (entry 143): abbassate
  // ulteriormente a 30/25 ora che le label intermedie sono acronimi
  // 2-4 char (vedi `lib/stazioni-acronimi.ts`).
  const showStazioni = widthPx >= 30;
  const showOrari = widthPx >= 25;
  // Sprint 8.0 MR-B.3 (entry 233): feedback visuale doppia composizione.
  const meta = blocco.metadata_json ?? {};
  const nPezzi = typeof meta.n_pezzi === "number" ? meta.n_pezzi : 1;
  const isSgancio = meta.is_sgancio === true;
  return (
    <button
      type="button"
      id={`gantt-blocco-${blocco.id}`}
      ref={dragRef}
      {...(dragListeners ?? {})}
      {...(dragAttributes ?? {})}
      onClick={onSelect}
      title={tooltip}
      aria-pressed={selected}
      className={cn(
        "blk absolute overflow-hidden",
        selected && "is-selected",
        isDragging === true && "opacity-30",
      )}
      style={{
        left: startPx,
        top: 24,
        width: widthPx,
        touchAction: "none",
      }}
    >
      {showStazioni ? (
        <div className="flex justify-between gap-1 font-mono text-[10px] font-semibold leading-none text-emerald-700">
          <span className="min-w-0 flex-1 truncate text-left">{stazioneDa}</span>
          <span className="min-w-0 flex-1 truncate text-right">{stazioneA}</span>
        </div>
      ) : (
        <div className="h-[10px]" aria-hidden="true" />
      )}
      {/* Badge ×2 in alto a destra se doppia composizione. */}
      {nPezzi >= 2 && (
        <span
          className="absolute right-0.5 top-0.5 z-10 inline-flex items-center rounded bg-amber-500 px-1 py-px text-[9px] font-bold leading-none text-white shadow"
          title={`Doppia composizione (${nPezzi} pezzi)`}
        >
          ×{nPezzi}
        </span>
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
        {/* Icona sgancio in fondo al blocco se is_sgancio. */}
        {isSgancio && (
          <span
            className="absolute -right-1 top-1/2 z-10 -translate-y-1/2 rounded-full bg-orange-600 p-0.5 text-white shadow"
            title="Sgancio: il materiale si separa dopo questo blocco"
          >
            <Unlink className="h-2.5 w-2.5" aria-hidden />
          </span>
        )}
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
  /** Sprint 7.9 MR δ.2 (entry 142): id thread L2 collegato all'evento, se popolato. */
  materialeThreadId: number | null;
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
    const threadId =
      typeof meta.materiale_thread_id === "number"
        ? (meta.materiale_thread_id as number)
        : null;
    out.push({
      oraMin: min,
      tipo: b.tipo_blocco,
      materiale,
      pezziDelta: delta,
      stazione: b.stazione_da_codice ?? b.stazione_a_codice,
      sourceDescrizione: sourceDescr,
      destDescrizione: destDescr,
      capacityWarning: capWarn,
      materialeThreadId: threadId,
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
        {evento.materialeThreadId !== null ? (
          <Link
            to={`/pianificatore-giro/thread/${evento.materialeThreadId}`}
            className="mt-3 block rounded border border-primary/40 bg-primary/5 px-2 py-1.5 text-center text-[11px] font-medium text-primary hover:bg-primary/10"
          >
            Apri thread del convoglio →
          </Link>
        ) : (
          <a
            href="#convogli-del-turno"
            className="mt-3 block rounded border border-border bg-muted/40 px-2 py-1.5 text-center text-[11px] font-medium text-muted-foreground hover:bg-muted"
          >
            Vedi convogli del turno ↓
          </a>
        )}
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

  // Sprint 8.0 entry 204 (Step B): indicatore visivo concatenazione
  // G_K → G_(K+1). ✓ verde se la stazione di terminazione di G_K
  // coincide con la stazione di partenza di G_(K+1); ✗ rosso se
  // discontinua (anomalia builder).
  const concatenazioneOk =
    sostaInfo.terminaA !== null &&
    sostaInfo.iniziaDa !== null &&
    !sostaInfo.discontinua;

  return (
    <div className="flex" style={{ height: NOTTE_ROW_HEIGHT_PX }}>
      <div
        className="night-band sticky left-0 z-20 flex items-center gap-1.5 border-r border-border px-3"
        style={{ width: GIORNATA_LABEL_COL_PX }}
      >
        {concatenazioneOk && (
          <span
            className="inline-flex items-center justify-center rounded-full bg-emerald-100 text-[10px] font-bold leading-none text-emerald-700"
            style={{ width: 14, height: 14 }}
            title={`Concatenazione G${giornataPrev.numero_giornata} → G${giornataNext.numero_giornata}: stessa stazione (${sostaInfo.stazione ?? sostaInfo.terminaA ?? "?"})`}
            aria-label="Concatenazione corretta"
          >
            ✓
          </span>
        )}
        {sostaInfo.discontinua && (
          <span
            className="inline-flex items-center justify-center rounded-full bg-destructive/15 text-[10px] font-bold leading-none text-destructive"
            style={{ width: 14, height: 14 }}
            title={`Discontinuità G${giornataPrev.numero_giornata} → G${giornataNext.numero_giornata}: ${sostaInfo.terminaA ?? "?"} ≠ ${sostaInfo.iniziaDa ?? "?"} (anomalia builder)`}
            aria-label="Discontinuità: stazioni diverse"
          >
            ✗
          </span>
        )}
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
// Sprint 7.9 MR δ.2 (entry 142): Dialog modal "Dettaglio blocco /
// turno". Sostituisce il SidePanel laterale (lg:col-span-4) per
// rispondere al feedback utente "non hai messo la possibilità di
// aprire un pop up per aprire il turno in una pagina tutta sua e
// dedicata". Il dialog è centrato, full-width main libero per il
// Gantt, e include link al thread del convoglio + ai convogli del
// turno (sezione esistente sotto la pagina).
// =====================================================================

function BloccoDialog({
  blocco,
  giro,
  activeVariantByGiornata,
  onClose,
}: {
  blocco: GiroBlocco | null;
  giro: GiroDettaglio;
  activeVariantByGiornata: Record<number, number>;
  onClose: () => void;
}) {
  return (
    <Dialog
      open={blocco !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="max-w-2xl">
        {blocco !== null && (
          <BloccoDialogBody
            blocco={blocco}
            giro={giro}
            activeVariantByGiornata={activeVariantByGiornata}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function BloccoDialogBody({
  blocco,
  giro,
  activeVariantByGiornata,
}: {
  blocco: GiroBlocco;
  giro: GiroDettaglio;
  activeVariantByGiornata: Record<number, number>;
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

  // Sprint 7.9 MR δ.2: estraggo materiale_thread_id dal metadata se
  // presente (popolato dal builder MR β2-4 sui blocchi che attraversano
  // un thread fisico). Quando c'è, il dialog mostra link diretto alla
  // pagina /pianificatore-giro/thread/{id}.
  const meta = blocco.metadata_json ?? {};
  const threadId =
    typeof meta.materiale_thread_id === "number"
      ? (meta.materiale_thread_id as number)
      : null;

  return (
    <>
      <DialogTitle className="sr-only">
        Dettaglio blocco {blocco.numero_treno ?? "—"}
      </DialogTitle>
      <div>
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

        {/* KPI mini: durata + direzione + tipo */}
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

        {/* MR η-bis: configurazione doppia/sgancio sul blocco. */}
        <BloccoConfigDoppiaSgancio giroId={giro.id} blocco={blocco} />

        {/* Sprint 8.0 MR-B.2 (entry 232): elimina blocco vuoto. */}
        {blocco.tipo_blocco === "materiale_vuoto" && (
          <BloccoEliminaVuoto giroId={giro.id} blocco={blocco} />
        )}

        {/* Metadata */}
        <BloccoMetadata blocco={blocco} />

        {blocco.descrizione !== null && blocco.descrizione !== "" && (
          <div className="mt-4 rounded border border-border bg-muted/40 p-3 text-[11px] italic text-muted-foreground">
            Note: {blocco.descrizione}
          </div>
        )}

        {/* Link "pagina dedicata" */}
        <div className="mt-5 flex flex-col gap-2">
          {threadId !== null && (
            <Link
              to={`/pianificatore-giro/thread/${threadId}`}
              className="inline-flex items-center justify-center rounded border border-primary/40 bg-primary/5 px-3 py-2 text-xs font-medium text-primary hover:bg-primary/10"
            >
              Apri thread del convoglio →
            </Link>
          )}
          <a
            href="#convogli-del-turno"
            onClick={() => {
              // Chiudi il dialog dopo lo scroll per non oscurare la sezione.
              setTimeout(() => {
                document
                  .getElementById("convogli-del-turno")
                  ?.scrollIntoView({ behavior: "smooth" });
              }, 50);
            }}
            className="inline-flex items-center justify-center rounded border border-border bg-muted/40 px-3 py-2 text-xs font-medium text-muted-foreground hover:bg-muted"
          >
            Vedi convogli del turno ↓
          </a>
        </div>
      </div>
    </>
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

/**
 * MR η-bis (2026-05-06) — Pannello inline nel dialog blocco per
 * marcare doppia composizione (``n_pezzi=2``) o sgancio. I valori
 * vivono in ``metadata_json`` del blocco (no migration). Persistiti
 * via ``PATCH /api/giri/{giro}/blocchi/{blocco}``. UI minimale: 2
 * checkbox + bottone Salva.
 */
function BloccoConfigDoppiaSgancio({
  giroId,
  blocco,
}: {
  giroId: number;
  blocco: GiroBlocco;
}) {
  const meta = (blocco.metadata_json ?? {}) as Record<string, unknown>;
  const initialNPezzi = typeof meta.n_pezzi === "number" ? meta.n_pezzi : 1;
  const initialIsSgancio = meta.is_sgancio === true;

  const [doppia, setDoppia] = useState(initialNPezzi >= 2);
  const [isSgancio, setIsSgancio] = useState(initialIsSgancio);
  const [error, setError] = useState<string | null>(null);
  const patchMutation = usePatchBlocco();

  // Risincronizza quando cambia il blocco selezionato.
  useEffect(() => {
    setDoppia(initialNPezzi >= 2);
    setIsSgancio(initialIsSgancio);
    setError(null);
  }, [blocco.id, initialNPezzi, initialIsSgancio]);

  const dirty =
    doppia !== initialNPezzi >= 2 || isSgancio !== initialIsSgancio;

  const onSalva = async () => {
    setError(null);
    try {
      await patchMutation.mutateAsync({
        giroId,
        bloccoId: blocco.id,
        payload: {
          n_pezzi: doppia ? 2 : 1,
          is_sgancio: isSgancio,
          is_validato_utente: true,
        },
      });
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      setError(msg);
    }
  };

  return (
    <div className="mt-4 rounded-md border border-primary/30 bg-primary/5 p-3">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-primary">
        Configurazione operativa (MR η-bis)
      </div>
      <div className="flex flex-col gap-2 text-sm">
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            checked={doppia}
            disabled={patchMutation.isPending}
            onChange={(e) => setDoppia(e.target.checked)}
            className="mt-0.5"
          />
          <span>
            <strong>Doppia composizione</strong> (2 pezzi accoppiati su questo blocco).
          </span>
        </label>
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            checked={isSgancio}
            disabled={patchMutation.isPending}
            onChange={(e) => setIsSgancio(e.target.checked)}
            className="mt-0.5"
          />
          <span className="inline-flex items-center gap-1">
            <Unlink className="h-3.5 w-3.5" aria-hidden />
            <strong>Sgancio</strong>: il materiale si separa dopo questo blocco.
          </span>
        </label>
        {error !== null && (
          <p
            role="alert"
            className="rounded-md border border-destructive/30 bg-destructive/5 px-2 py-1 text-xs text-destructive"
          >
            {error}
          </p>
        )}
        <div className="flex justify-end">
          <Button
            variant={dirty ? "primary" : "outline"}
            size="sm"
            onClick={() => void onSalva()}
            disabled={patchMutation.isPending || !dirty}
          >
            {patchMutation.isPending ? "Salvataggio…" : "Salva"}
          </Button>
        </div>
      </div>
    </div>
  );
}

/**
 * Sprint 8.0 MR-B.2 (entry 232) — pannello inline "Elimina vuoto".
 *
 * Decisione utente entry 230: "io posso decidere di eliminare un
 * vuoto perchè può dormire a milano centrale". Solo blocchi
 * `materiale_vuoto` mostrano questo pannello.
 *
 * Flusso 2 fasi:
 *  1. dry_run → anteprima violazioni di fattibilità.
 *  2. apply (con `force` se l'utente conferma le violazioni).
 */
function BloccoEliminaVuoto({
  giroId,
  blocco,
}: {
  giroId: number;
  blocco: GiroBlocco;
}) {
  const eliminaMutation = useEliminaBlocco();
  const [violazioni, setViolazioni] = useState<
    ViolazioneFattibilita[] | null
  >(null);
  const [error, setError] = useState<string | null>(null);

  const onElimina = async () => {
    setError(null);
    try {
      const dryRes = await eliminaMutation.mutateAsync({
        giroId,
        bloccoId: blocco.id,
        dryRun: true,
      });
      const hasErrors = dryRes.violazioni.some(
        (v) => v.severity === "error",
      );
      if (!hasErrors) {
        // Anche con violazioni warning, applichiamo direttamente.
        await eliminaMutation.mutateAsync({
          giroId,
          bloccoId: blocco.id,
          dryRun: false,
          force: false,
        });
      } else {
        // Mostra dialog di conferma con violazioni.
        setViolazioni(dryRes.violazioni);
      }
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : (err as Error).message;
      setError(msg);
    }
  };

  const onForzaElimina = async () => {
    setError(null);
    try {
      await eliminaMutation.mutateAsync({
        giroId,
        bloccoId: blocco.id,
        dryRun: false,
        force: true,
      });
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : (err as Error).message;
      setError(msg);
    } finally {
      setViolazioni(null);
    }
  };

  return (
    <>
      <div className="mt-4 rounded-md border border-rose-300/50 bg-rose-50/40 p-3">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-rose-800">
          Elimina vuoto
        </div>
        <p className="mb-2 text-sm text-rose-900/80">
          Rimuovi questo blocco se il convoglio non deve fare il
          posizionamento (es. "dorme" qui). I seq successivi vengono
          ricompattati automaticamente.
        </p>
        {error !== null && (
          <p
            role="alert"
            className="mb-2 rounded-md border border-destructive/30 bg-destructive/5 px-2 py-1 text-xs text-destructive"
          >
            {error}
          </p>
        )}
        <div className="flex justify-end">
          <Button
            variant="outline"
            size="sm"
            onClick={() => void onElimina()}
            disabled={eliminaMutation.isPending}
          >
            <Trash2
              className="mr-1.5 h-3.5 w-3.5 text-rose-600"
              aria-hidden
            />
            {eliminaMutation.isPending ? "Elimino…" : "Elimina vuoto"}
          </Button>
        </div>
      </div>

      {/* Dialog conferma se violazioni */}
      <Dialog
        open={violazioni !== null}
        onOpenChange={(o) => !o && setViolazioni(null)}
      >
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle
                className="h-5 w-5 text-amber-600"
                aria-hidden
              />
              Eliminazione con violazioni
            </DialogTitle>
            <DialogDescription>
              Eliminando questo vuoto si genereranno{" "}
              {violazioni?.length ?? 0} segnalazioni nella variante.
              Verifica e conferma se vuoi forzare comunque.
            </DialogDescription>
          </DialogHeader>
          {violazioni !== null && (
            <ul className="max-h-72 space-y-1.5 overflow-y-auto rounded-md border border-border bg-muted/20 p-3 text-sm">
              {violazioni.map((v, i) => (
                <li
                  key={i}
                  className={cn(
                    "flex items-start gap-2 rounded px-2 py-1.5",
                    v.severity === "error"
                      ? "bg-destructive/5 text-destructive"
                      : "bg-amber-50 text-amber-900",
                  )}
                >
                  <span className="mt-0.5 inline-flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-full text-[9px] font-bold uppercase">
                    {v.severity === "error" ? "!" : "i"}
                  </span>
                  <div className="flex-1">
                    <div className="text-xs font-medium uppercase tracking-wide">
                      {v.codice} · {v.variante_label}
                    </div>
                    <div className="text-[13px] leading-snug">
                      {v.descrizione}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setViolazioni(null)}
              disabled={eliminaMutation.isPending}
            >
              Annulla
            </Button>
            <Button
              onClick={() => void onForzaElimina()}
              disabled={eliminaMutation.isPending}
            >
              {eliminaMutation.isPending
                ? "Elimino…"
                : "Forza eliminazione"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
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
