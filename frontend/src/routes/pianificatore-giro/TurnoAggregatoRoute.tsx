/**
 * Sprint 8.0 MR-A (entry 231) — Vista aggregata "1 turno con N giornate".
 *
 * Decisione utente entry 230:
 * > "lo spostamento funziona, solo che posso solo spostarlo tra treni
 * > dello stesso turno/giornata. perchè non hai aggregato tutti i giri
 * > con un solo materiale?"
 *
 * Risolve: sul programma reale ci sono N turni separati per stesso
 * (materiale, sede) — es. 10 turni ATR803 a CRE con 4g/3g/2g/1g
 * giornate. Questa vista li combina in 1 Gantt unico, dove tutte le
 * giornate sono righe sequenziali e il drag&drop attraversa i turni
 * (`giro_target_id` nel payload backend).
 *
 * Path: `/pianificatore-giro/programmi/:programmaId/turno-aggregato/:materiale/:sede`
 */

import { useCallback, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { useQueries } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Loader2,
} from "lucide-react";
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";

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
import { Spinner } from "@/components/ui/Spinner";
import { useGiriProgramma, useSpostaBlocco } from "@/hooks/useGiri";
import { useProgramma } from "@/hooks/useProgrammi";
import { ApiError } from "@/lib/api/client";
import { getGiroDettaglio } from "@/lib/api/giri";
import type {
  GiroBlocco,
  GiroDettaglio,
  SpostaBloccoResponse,
  ViolazioneFattibilita,
} from "@/lib/api/giri";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  AXIS_TOTAL_MIN,
  DraggableBloccoSegment,
  DroppableTimeline,
  GIORNATA_LABEL_COL_PX,
  GanttScaleContext,
  PER_KM_COL_PX,
  TIMELINE_ROW_HEIGHT_PX,
  buildGanttScale,
  useGanttScale,
} from "@/routes/pianificatore-giro/GiroDettaglioRoute";

const ZOOM_LEVELS = [0.75, 1, 1.5, 2] as const;
type ZoomLevel = (typeof ZOOM_LEVELS)[number];

interface AggregatedRow {
  /** Chiave stabile per React key. */
  rowKey: string;
  /** Id del giro proprietario (per drag&drop cross-turno). */
  giroId: number;
  /** Numero turno per UI (es. "G-CRE-001-ATR803-4g"). */
  giroNumeroTurno: string;
  /** Sequenza dell'AGGREGATO (1..N totale tutte giornate). */
  giornataAggregata: number;
  /** Numero giornata originale del giro (1..n_giornate). */
  giornataNumero: number;
  /** Indice variante. */
  variantIndex: number;
  varianteId: number;
  varianteEtichetta: string;
  /** km della giornata canonica (variant 0). */
  kmGiornata: number | null;
  blocchi: GiroBlocco[];
}

export function TurnoAggregatoRoute() {
  const params = useParams<{
    programmaId: string;
    materiale: string;
    sede: string;
  }>();
  const programmaId = params.programmaId !== undefined
    ? Number(params.programmaId)
    : undefined;
  const materiale = params.materiale ?? "";
  const sedeBreve = params.sede ?? "";

  const programmaQuery = useProgramma(programmaId);
  const giriListQuery = useGiriProgramma(programmaId);

  // Filtra i giri del programma per (materiale, sede). La sede breve
  // viene estratta da `numero_turno` formato `G-{SEDE}-NNN[-MAT-Ng]`.
  const giriFiltrati = useMemo(() => {
    const all = giriListQuery.data ?? [];
    return all
      .filter((g) => {
        const matchMat =
          (g.materiale_tipo_codice ?? g.tipo_materiale) === materiale;
        const sedeFromTurno = parseSedeBreve(g.numero_turno);
        return matchMat && sedeFromTurno === sedeBreve;
      })
      .sort((a, b) => a.numero_turno.localeCompare(b.numero_turno));
  }, [giriListQuery.data, materiale, sedeBreve]);

  // Fetcha in parallelo il dettaglio di ognuno.
  const dettagliQueries = useQueries({
    queries: giriFiltrati.map((g) => ({
      queryKey: ["giri", "dettaglio", g.id],
      queryFn: () => getGiroDettaglio(g.id),
      enabled: programmaId !== undefined,
    })),
  });

  const dettagli = useMemo(
    () =>
      dettagliQueries
        .map((q) => q.data)
        .filter((d): d is GiroDettaglio => d !== undefined),
    [dettagliQueries],
  );

  const isLoading =
    giriListQuery.isLoading ||
    dettagliQueries.some((q) => q.isLoading) ||
    (giriFiltrati.length > 0 && dettagli.length < giriFiltrati.length);

  // Combina in righe sequenziali.
  const rows = useMemo<AggregatedRow[]>(() => {
    const out: AggregatedRow[] = [];
    let aggregata = 0;
    for (const giro of dettagli) {
      for (const giornata of giro.giornate) {
        aggregata += 1;
        for (const variante of giornata.varianti) {
          out.push({
            rowKey: `${giro.id}-${giornata.id}-${variante.id}`,
            giroId: giro.id,
            giroNumeroTurno: giro.numero_turno,
            giornataAggregata: aggregata,
            giornataNumero: giornata.numero_giornata,
            variantIndex: variante.variant_index,
            varianteId: variante.id,
            varianteEtichetta: variante.etichetta_parlante,
            kmGiornata: giornata.km_giornata,
            blocchi: variante.blocchi,
          });
        }
      }
    }
    return out;
  }, [dettagli]);

  // Stats aggregate.
  const stats = useMemo(() => {
    const nGiornate = new Set(
      rows.map((r) => `${r.giroId}-${r.giornataNumero}`),
    ).size;
    const nVarianti = rows.length;
    const nBlocchiCommerciali = rows.reduce(
      (s, r) =>
        s +
        r.blocchi.filter((b) => b.tipo_blocco === "corsa_commerciale").length,
      0,
    );
    const kmCumulato = rows.reduce(
      (s, r) =>
        s + (r.variantIndex === 0 ? Math.round(r.kmGiornata ?? 0) : 0),
      0,
    );
    return { nGiornate, nVarianti, nBlocchiCommerciali, kmCumulato };
  }, [rows]);

  // Drag&drop state + handlers (riusa pattern di GiroDettaglioRoute).
  const [zoom, setZoom] = useState<ZoomLevel>(1.5);
  const ganttScale = useMemo(() => buildGanttScale(zoom), [zoom]);
  const [dragActive, setDragActive] = useState<GiroBlocco | null>(null);
  const [pendingMove, setPendingMove] = useState<{
    blocco: GiroBlocco;
    sourceGiroId: number;
    giornataTarget: number;
    variantIndexTarget: number;
    giroTargetIdPayload: number | null;
    response: SpostaBloccoResponse;
  } | null>(null);
  const spostaMutation = useSpostaBlocco();

  // Sprint 8.0 MR-B.4 (entry 233 fix Fausto #4 #5): distance 10px +
  // KeyboardSensor per accessibility.
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 10 },
    }),
    useSensor(KeyboardSensor),
  );

  const handleDragStart = useCallback((event: DragStartEvent) => {
    const blocco = event.active.data.current?.blocco as
      | GiroBlocco
      | undefined;
    setDragActive(blocco ?? null);
  }, []);

  const handleDragEnd = useCallback(
    async (event: DragEndEvent) => {
      setDragActive(null);
      const { active, over } = event;
      if (over === null) return;
      const blocco = active.data.current?.blocco as
        | GiroBlocco
        | undefined;
      const sourceGiroId = active.data.current?.giroId as
        | number
        | undefined;
      const sourceVarianteId = active.data.current?.varianteId as
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
      if (
        blocco === undefined ||
        target === undefined ||
        sourceGiroId === undefined
      )
        return;
      if (sourceVarianteId === target.varianteId) return;

      const targetGiroId = target.giroId ?? sourceGiroId;
      const giroTargetIdPayload =
        targetGiroId !== sourceGiroId ? targetGiroId : null;

      try {
        const dryRes = await spostaMutation.mutateAsync({
          giroId: sourceGiroId,
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
            giroId: sourceGiroId,
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
            sourceGiroId,
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
    [spostaMutation],
  );

  const confermaForce = useCallback(async () => {
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

  if (programmaId === undefined || Number.isNaN(programmaId)) {
    return (
      <Card className="p-6 text-sm text-destructive">
        ID programma non valido nell'URL.
      </Card>
    );
  }

  if (giriListQuery.isError) {
    return (
      <Card className="p-6 text-sm text-destructive">
        Errore caricamento giri:{" "}
        {giriListQuery.error instanceof Error
          ? giriListQuery.error.message
          : "errore sconosciuto"}
      </Card>
    );
  }

  return (
    <DndContext
      sensors={sensors}
      onDragStart={handleDragStart}
      onDragEnd={(e) => {
        void handleDragEnd(e);
      }}
      onDragCancel={() => setDragActive(null)}
    >
      <div className="flex min-w-0 flex-col gap-4">
        {/* Header + breadcrumb */}
        <div className="flex items-center justify-between gap-2">
          <Link
            to={`/pianificatore-giro/programmi/${programmaId}/giri`}
            className="inline-flex w-fit items-center gap-1 text-xs text-muted-foreground hover:text-primary"
          >
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> Lista giri
          </Link>
        </div>

        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              Vista aggregata · {materiale} · {sedeBreve}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {programmaQuery.data?.nome !== undefined && (
                <>
                  Programma{" "}
                  <span className="font-medium text-foreground">
                    {programmaQuery.data.nome}
                  </span>{" "}
                  ·{" "}
                </>
              )}
              {giriFiltrati.length} turni aggregati ·{" "}
              {stats.nGiornate} giornate · {stats.nVarianti} varianti ·{" "}
              {stats.nBlocchiCommerciali} corse · {formatNumber(stats.kmCumulato)} km/g cumul.
            </p>
          </div>
          <ZoomToolbar zoom={zoom} onChange={setZoom} />
        </div>

        {/* Body */}
        {isLoading ? (
          <Card className="grid place-items-center p-16">
            <Spinner label="Caricamento turni…" />
          </Card>
        ) : giriFiltrati.length === 0 ? (
          <Card className="p-8 text-center text-sm text-muted-foreground">
            Nessun turno trovato per ({materiale}, {sedeBreve}) nel
            programma.
          </Card>
        ) : (
          <GanttScaleContext.Provider value={ganttScale}>
            <Card className="overflow-x-auto">
              <AxisTimeline />
              <div className="divide-y divide-border">
                {rows.map((r) => (
                  <AggregatedVarianteRow key={r.rowKey} row={r} />
                ))}
              </div>
            </Card>
          </GanttScaleContext.Provider>
        )}

        {/* Dialog conferma violazioni */}
        <SpostaBloccoConfirmDialog
          pending={pendingMove}
          isPending={spostaMutation.isPending}
          onCancel={() => setPendingMove(null)}
          onConfirm={() => {
            void confermaForce();
          }}
        />
      </div>

      {/* DragOverlay ghost Mac-like */}
      <DragOverlay
        dropAnimation={{
          duration: 220,
          easing: "cubic-bezier(0.18, 0.67, 0.6, 1.22)",
        }}
      >
        {dragActive !== null ? <DragGhost blocco={dragActive} /> : null}
      </DragOverlay>
    </DndContext>
  );
}

// =====================================================================
// Sub-components
// =====================================================================

function AxisTimeline() {
  const { timelineWidthPx, minToPx } = useGanttScale();
  // Ticks 04, 05, 06, ..., 03 (24h ciclo).
  const ticks = useMemo(() => {
    const arr: { hour: number; left: number }[] = [];
    for (let h = 0; h < 24; h += 1) {
      const min = (4 + h) * 60;
      const minMod = min >= AXIS_TOTAL_MIN ? min - AXIS_TOTAL_MIN : min;
      const hourLabel = Math.floor(minMod / 60);
      arr.push({ hour: hourLabel, left: minToPx(min) });
    }
    return arr;
  }, [minToPx]);
  return (
    <div className="flex border-b border-border bg-muted/30">
      <div
        className="sticky left-0 z-20 border-r border-border bg-muted/30 px-3 py-2 text-[10px] uppercase tracking-wide text-muted-foreground"
        style={{ width: GIORNATA_LABEL_COL_PX }}
      >
        Riga
      </div>
      <div className="relative" style={{ width: timelineWidthPx, height: 30 }}>
        {ticks.map((t, i) => (
          <div
            key={i}
            className="absolute top-0 flex h-full items-center text-[10px] tabular-nums text-muted-foreground"
            style={{ left: t.left }}
          >
            {String(t.hour).padStart(2, "0")}
          </div>
        ))}
      </div>
      <div
        className="sticky right-0 z-20 border-l border-border bg-muted/30 px-3 py-2 text-right text-[10px] uppercase tracking-wide text-muted-foreground"
        style={{ width: PER_KM_COL_PX }}
      >
        km/g
      </div>
    </div>
  );
}

function ZoomToolbar({
  zoom,
  onChange,
}: {
  zoom: ZoomLevel;
  onChange: (z: ZoomLevel) => void;
}) {
  return (
    <div className="flex items-center gap-1 rounded-md border border-border bg-white p-0.5">
      {ZOOM_LEVELS.map((z) => (
        <button
          key={z}
          type="button"
          onClick={() => onChange(z)}
          className={cn(
            "rounded px-2 py-1 text-xs tabular-nums transition",
            zoom === z
              ? "bg-primary text-primary-foreground"
              : "text-foreground hover:bg-muted",
          )}
        >
          {Math.round(z * 100)}%
        </button>
      ))}
    </div>
  );
}

function AggregatedVarianteRow({ row }: { row: AggregatedRow }) {
  const { timelineWidthPx } = useGanttScale();
  // Sprint 8.0 MR-D (entry 236): mostra etichetta_parlante della
  // variante (es. "LV 1:5", "F", "Si eff. 21-28/3") per distinguere
  // varianti calendariali della stessa giornata-tipo.
  const etichettaTrunc =
    row.varianteEtichetta.length > 16
      ? row.varianteEtichetta.slice(0, 14) + "…"
      : row.varianteEtichetta;
  const blocchiOrdinati = useMemo(
    () =>
      [...row.blocchi].sort((a, b) => {
        const ta = parseTimeMin(a.ora_inizio) ?? 0;
        const tb = parseTimeMin(b.ora_inizio) ?? 0;
        return ta - tb;
      }),
    [row.blocchi],
  );
  const firstId = blocchiOrdinati[0]?.id ?? null;
  const lastId =
    blocchiOrdinati[blocchiOrdinati.length - 1]?.id ?? null;

  return (
    <div className="flex">
      {/* Etichetta riga sx — Sprint 8.0 MR-D (entry 236):
          aggiunta `etichetta_parlante` della variante (es. "LV 1:5"),
          indentazione visuale per varianti non-canoniche per
          raggrupparle visivamente con la canonica della stessa
          giornata. */}
      <div
        className={cn(
          "sticky left-0 z-20 flex flex-col justify-center border-r border-border bg-white px-3 py-3",
          row.variantIndex > 0 && "border-l-2 border-l-primary/30",
        )}
        style={{ width: GIORNATA_LABEL_COL_PX }}
      >
        <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          #{row.giornataAggregata}
        </div>
        <div
          className="truncate font-mono text-[11px] font-medium text-foreground"
          title={row.giroNumeroTurno}
        >
          T-{shortTurno(row.giroNumeroTurno)}
        </div>
        <div className="text-[9px] text-muted-foreground">
          G{row.giornataNumero}
          {row.variantIndex > 0 && (
            <span className="text-primary"> · V{row.variantIndex}</span>
          )}
        </div>
        <div
          className="mt-0.5 truncate text-[9px] italic text-foreground/70"
          title={row.varianteEtichetta}
        >
          {etichettaTrunc}
        </div>
      </div>

      {/* Timeline droppable */}
      <DroppableTimeline
        varianteId={row.varianteId}
        giornataNumero={row.giornataNumero}
        variantIndex={row.variantIndex}
        giroId={row.giroId}
        widthPx={timelineWidthPx}
        heightPx={TIMELINE_ROW_HEIGHT_PX}
      >
        <div
          className="pointer-events-none absolute left-0 right-0 h-px bg-border"
          style={{ top: 44 }}
        />
        {row.blocchi.map((b) => (
          <DraggableBloccoSegment
            key={b.id}
            blocco={b}
            varianteId={row.varianteId}
            giroId={row.giroId}
            selected={false}
            isFirstOfRow={b.id === firstId}
            isLastOfRow={b.id === lastId}
            onSelect={() => {
              /* no-op: nella vista aggregata il click apre dettaglio */
            }}
          />
        ))}
      </DroppableTimeline>

      {/* km/g sticky-right */}
      <div
        className="sticky right-0 z-20 flex items-center justify-center border-l border-border bg-white font-mono text-sm tabular-nums text-foreground"
        style={{ width: PER_KM_COL_PX }}
      >
        {row.variantIndex === 0 && row.kmGiornata !== null
          ? formatNumber(Math.round(row.kmGiornata))
          : "—"}
      </div>
    </div>
  );
}

function DragGhost({ blocco }: { blocco: GiroBlocco }) {
  const tipo = blocco.tipo_blocco;
  return (
    <div
      className={cn(
        "pointer-events-none flex items-center gap-2 rounded-lg border bg-white/95 px-3 py-1.5 shadow-2xl",
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
        {blocco.numero_treno ?? `#${blocco.id}`}
      </span>
    </div>
  );
}

function SpostaBloccoConfirmDialog({
  pending,
  isPending,
  onCancel,
  onConfirm,
}: {
  pending: {
    blocco: GiroBlocco;
    sourceGiroId: number;
    giornataTarget: number;
    variantIndexTarget: number;
    giroTargetIdPayload: number | null;
    response: SpostaBloccoResponse;
  } | null;
  isPending: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const open = pending !== null;
  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    onConfirm();
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle
              className="h-5 w-5 text-amber-600"
              aria-hidden
            />
            Spostamento con violazioni
          </DialogTitle>
          <DialogDescription>
            {pending !== null && (
              <>
                Lo spostamento del blocco{" "}
                <span className="font-mono font-medium">
                  {pending.blocco.numero_treno ?? `#${pending.blocco.id}`}
                </span>{" "}
                {pending.giroTargetIdPayload !== null
                  ? "verso un altro turno"
                  : "nello stesso turno"}{" "}
                a giornata {pending.giornataTarget} (variante{" "}
                {pending.variantIndexTarget}) genera{" "}
                {pending.response.violazioni.length} segnalazioni.
              </>
            )}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit}>
          {pending !== null && (
            <ul className="max-h-72 space-y-1.5 overflow-y-auto rounded-md border border-border bg-muted/20 p-3 text-sm">
              {pending.response.violazioni.map((v, i) => (
                <ViolazioneRow key={i} v={v} />
              ))}
            </ul>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={onCancel}
              disabled={isPending}
            >
              Annulla
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? (
                <>
                  <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                  Sposto…
                </>
              ) : (
                "Forza spostamento"
              )}
            </Button>
          </DialogFooter>
        </form>
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
        {v.severity === "error" ? (
          <AlertTriangle className="h-3 w-3" />
        ) : (
          <CheckCircle2 className="h-3 w-3" />
        )}
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
// Helpers
// =====================================================================

/** Estrae sede breve da `numero_turno` formato `G-{SEDE}-NNN[-MAT-...]`. */
function parseSedeBreve(numeroTurno: string): string | null {
  const m = numeroTurno.match(/^G-([A-Z]+)-/);
  return m !== null ? m[1] : null;
}

/** Estrae il segmento sequenza dal numero turno. Es. "G-CRE-001-..." → "001". */
function shortTurno(numeroTurno: string): string {
  const m = numeroTurno.match(/^G-[A-Z]+-(\d+)/);
  return m !== null ? m[1] : numeroTurno;
}

function parseTimeMin(t: string | null): number | null {
  if (t === null) return null;
  const parts = t.split(":");
  if (parts.length < 2) return null;
  const h = Number(parts[0]);
  const m = Number(parts[1]);
  if (Number.isNaN(h) || Number.isNaN(m)) return null;
  return h * 60 + m;
}
