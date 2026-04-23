/**
 * AutoBuilderGantt — visualizzazione orizzontale (Gantt-like) dei turni
 * generati dall'auto-builder.
 *
 * MIGRATO (23/04/2026) alla base `GanttSheet` v3 (falsa riga PDF Trenord).
 * Mappa internamente `TrainSegment` → `GanttSegment`.
 *
 * Update 23/04/2026 (pm): label verticali forzate (segmenti spesso
 * adiacenti → label orizzontali si accavallavano). Click su segmento
 * apre popover HTML con dettagli treno (numero, tratta, orari,
 * preheat/CV). Click fuori o Esc chiude.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import type { TrainSegment } from "@/lib/api"
import { GanttSheet } from "@/components/gantt/GanttSheet"
import type {
  CrossDragPayload,
  GanttSegment,
  GanttRow,
} from "@/components/gantt/types"


interface Props {
  segments: TrainSegment[]
  presentationTime?: string
  endTime?: string
  mealStart?: string
  mealEnd?: string
  onSegmentClick?: (seg: TrainSegment, index: number) => void
  /**
   * Abilita cross-turn drag fra piu' AutoBuilderGantt in pagina.
   * Il consumer passa un ID univoco (es. "D2-LMXGV"), gli handler
   * di drop/remove mutano gli array di segmenti a livello parent.
   */
  ganttId?: string
  onCrossDragStart?: (p: { seg: TrainSegment; segIdx: number; ganttId: string }) => void
  onCrossDrop?: (
    sourceGanttId: string,
    sourceSegIdx: number,
    sourceSeg: TrainSegment,
    targetGanttId: string,
    dropTime: { hour: number; minute: number },
  ) => void
  onCrossRemove?: (segIdx: number) => void
}


/** Converte GanttSegment -> TrainSegment perdendo solo i flag visivi che
 * non esistono sul modello backend (preheat, cvp, cva diventano boolean
 * su TrainSegment se presenti, altrimenti scartati). */
function ganttSegToTrainSeg(gs: GanttSegment): TrainSegment {
  return {
    train_id: gs.train_id,
    from_station: gs.from_station,
    to_station: gs.to_station,
    dep_time: gs.dep_time,
    arr_time: gs.arr_time,
    is_deadhead: gs.kind === "dh",
    ...(gs.kind === "refez" ? { is_refezione: true } : {}),
    ...(gs.preheat ? { is_preheat: true } : {}),
    ...(gs.cvp ? { cvp: true } : {}),
    ...(gs.cva ? { cva: true } : {}),
  } as TrainSegment
}


function timeToMin(t: string): number {
  if (!t) return 0
  const [h, m] = t.split(":").map(Number)
  return (h || 0) * 60 + (m || 0)
}

function fmtHM(min: number): string {
  const m = ((min % 1440) + 1440) % 1440
  return (
    String(Math.floor(m / 60)).padStart(2, "0") +
    "h" +
    String(m % 60).padStart(2, "0")
  )
}


export function AutoBuilderGantt({
  segments,
  presentationTime,
  endTime,
  mealStart,
  mealEnd,
  onSegmentClick,
  ganttId,
  onCrossDragStart,
  onCrossDrop,
  onCrossRemove,
}: Props) {
  const [popover, setPopover] = useState<{
    seg: TrainSegment
    index: number
    x: number
    y: number
  } | null>(null)

  const containerRef = useRef<HTMLDivElement | null>(null)

  const closePopover = useCallback(() => setPopover(null), [])

  // Esc + click fuori dal popover chiudono
  useEffect(() => {
    if (!popover) return
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") setPopover(null)
    }
    const onClick = (ev: MouseEvent) => {
      const pop = document.getElementById("auto-builder-popover")
      if (pop && pop.contains(ev.target as Node)) return
      setPopover(null)
    }
    document.addEventListener("keydown", onKey)
    document.addEventListener("mousedown", onClick)
    return () => {
      document.removeEventListener("keydown", onKey)
      document.removeEventListener("mousedown", onClick)
    }
  }, [popover])

  const view = useMemo(() => {
    if (!segments || segments.length === 0) return null

    // ─── Mapping TrainSegment → GanttSegment ───
    // mappedToOriginalIdx[i] = index della TrainSegment sorgente in
    // `segments`, oppure -1 se il segment e' virtuale (es. refez
    // iniettata).
    const mapped: GanttSegment[] = []
    const mappedToOriginalIdx: number[] = []
    segments.forEach((seg, origIdx) => {
      const isRefez = Boolean(seg.is_refezione)
      const isDH = !isRefez && Boolean(seg.is_deadhead)
      const cvp = (seg.cv_before_min ?? 0) > 0
      const cva = (seg.cv_after_min ?? 0) > 0
      mapped.push({
        kind: isRefez ? "refez" : isDH ? "dh" : "cond",
        train_id: seg.train_id,
        from_station: seg.from_station,
        to_station: seg.to_station,
        dep_time: seg.dep_time,
        arr_time: seg.arr_time,
        preheat: seg.is_preheat,
        cvp,
        cva,
        accp_min: seg.accp_min,
        acca_min: seg.acca_min,
        cv_before_min: seg.cv_before_min,
        cv_after_min: seg.cv_after_min,
      })
      mappedToOriginalIdx.push(origIdx)
    })

    // Inietta refezione virtuale se mealStart/End presenti e nessuna refez nei dati
    const hasRefez = mapped.some((s) => s.kind === "refez")
    if (!hasRefez && mealStart && mealEnd) {
      const mealStartMin = timeToMin(mealStart)
      let pivotStation = segments[0]?.from_station ?? ""
      for (const s of segments) {
        const arr = timeToMin(s.arr_time)
        if (arr <= mealStartMin) pivotStation = s.to_station
      }
      const refezSeg: GanttSegment = {
        kind: "refez",
        train_id: `REFEZ ${pivotStation}`,
        from_station: pivotStation,
        to_station: pivotStation,
        dep_time: mealStart,
        arr_time: mealEnd,
      }
      const insertAt = mapped.findIndex(
        (s) => timeToMin(s.dep_time) > mealStartMin,
      )
      if (insertAt === -1) {
        mapped.push(refezSeg)
        mappedToOriginalIdx.push(-1)
      } else {
        mapped.splice(insertAt, 0, refezSeg)
        mappedToOriginalIdx.splice(insertAt, 0, -1)
      }
    }

    // ─── Range orario ───
    // Richiesta utente 23/04/2026: asse sempre 00-24, non auto-fit —
    // cosi' tutti i Gantt hanno la stessa scala e il dispatcher
    // riconosce a colpo d'occhio "che orario occupa un turno".
    const startAnchor = presentationTime
      ? timeToMin(presentationTime)
      : timeToMin(segments[0].dep_time)
    let endAnchor = endTime
      ? timeToMin(endTime)
      : timeToMin(segments[segments.length - 1].arr_time)
    if (endAnchor < startAnchor) endAnchor += 1440
    const startHour = 0
    const endHour = 24

    // ─── Metriche placeholder ───
    // AutoBuilderPage non passa metriche al Gantt (sono mostrate a parte
    // nell'header della giornata). Usiamo "—" per tutti i campi della
    // colonna destra cosi' la riga risulta pulita.
    const totalMin = endAnchor - startAnchor
    const condotta = segments
      .filter((s) => !s.is_deadhead && !(s as any).is_refezione)
      .reduce((acc, s) => {
        const d = timeToMin(s.dep_time)
        let a = timeToMin(s.arr_time)
        if (a < d) a += 1440
        return acc + (a - d)
      }, 0)

    const row: GanttRow = {
      label: "", // niente label variante: giornata singola
      segments: mapped,
    }

    return {
      rows: [row],
      mappedToOriginalIdx,
      dayHead: {
        num: 0,
        pres: presentationTime || segments[0].dep_time,
        end: endTime || segments[segments.length - 1].arr_time,
      },
      metrics: {
        lav: fmtHM(totalMin),
        cct: fmtHM(condotta),
        km: 0,
        not: "no" as const,
        rip: "—",
      },
      range: [startHour, endHour] as [number, number],
    }
  }, [segments, presentationTime, endTime, mealStart, mealEnd])

  if (!view) return null

  const handleSegmentClick = (seg: GanttSegment, _rowIdx: number) => {
    const segIdx = view.rows[0].segments.indexOf(seg)
    if (segIdx < 0) return
    const origIdx = view.mappedToOriginalIdx[segIdx]
    if (origIdx < 0) {
      // Segmento virtuale (refez iniettata) — niente info da mostrare
      return
    }
    const origSeg = segments[origIdx]
    // Se il consumer fornisce onSegmentClick, delega tutto a lui
    if (onSegmentClick) {
      onSegmentClick(origSeg, origIdx)
      return
    }
    // Default: mostra popover interno
    const rect = containerRef.current?.getBoundingClientRect()
    // Centro popover rispetto al container (l'utente dovra' solo cliccare
    // sul blocco e il popover apparira' in alto a sinistra del container).
    // Posizionamento preciso sul segmento richiederebbe le coordinate x
    // del segment rect — accettabile questo fallback semplice per ora.
    setPopover({
      seg: origSeg,
      index: origIdx,
      x: rect ? 16 : 0,
      y: rect ? 16 : 0,
    })
  }

  return (
    <div
      ref={containerRef}
      className="overflow-x-auto"
      style={{
        backgroundColor: "var(--color-surface-container-low)",
        borderRadius: 8,
        padding: "4px 4px",
        position: "relative",
      }}
    >
      <GanttSheet
        rows={view.rows}
        dayHead={view.dayHead}
        metrics={view.metrics}
        range={view.range}
        palette="hybrid"
        labels="vertical"
        minutes="hhmm"
        onSegmentClick={handleSegmentClick}
        ganttId={ganttId}
        onCrossDragStart={
          onCrossDragStart && ganttId
            ? (payload: CrossDragPayload) => {
                const segIdx = view.rows[0].segments.indexOf(payload.seg)
                if (segIdx < 0) return
                const origIdx = view.mappedToOriginalIdx[segIdx]
                if (origIdx < 0) return  // refez virtuale: non trascinabile
                onCrossDragStart({
                  seg: segments[origIdx],
                  segIdx: origIdx,
                  ganttId: payload.ganttId,
                })
              }
            : undefined
        }
        onCrossDrop={
          onCrossDrop && ganttId
            ? (payload: CrossDragPayload, targetGanttId: string, dropTime) => {
                // Il source puo' essere un altro AutoBuilderGantt — il
                // payload ha il GanttSegment ma non il TrainSegment
                // originale. Ricostruiamo TrainSegment dai campi del GS.
                const sourceSeg = ganttSegToTrainSeg(payload.seg)
                onCrossDrop(
                  payload.ganttId,
                  payload.segIdx,
                  sourceSeg,
                  targetGanttId,
                  { hour: dropTime.hour, minute: dropTime.minute },
                )
              }
            : undefined
        }
        onCrossRemove={
          onCrossRemove
            ? (_segIdx: number, _withLinkedCvs: boolean) => {
                // segIdx arriva indicizzato sulla view (mappedToOriginalIdx).
                // Lo ritraduciamo all'indice originale di `segments`.
                const origIdx = view.mappedToOriginalIdx[_segIdx]
                if (origIdx < 0) return
                onCrossRemove(origIdx)
              }
            : undefined
        }
      />

      {popover && (
        <div
          id="auto-builder-popover"
          style={{
            position: "absolute",
            left: popover.x,
            top: popover.y,
            zIndex: 40,
            minWidth: 240,
            maxWidth: 320,
            padding: "10px 12px",
            background: "var(--color-surface-container-lowest, #FEFEFD)",
            boxShadow:
              "0 12px 32px rgba(11,13,16,.18), 0 2px 8px rgba(11,13,16,.08)",
            fontFamily: "var(--font-sans, Inter)",
            fontSize: 12,
            lineHeight: 1.5,
            color: "var(--color-on-surface-strong, #0A1322)",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              marginBottom: 6,
              paddingBottom: 6,
              boxShadow: "inset 0 -1px 0 var(--color-ghost, #E1E5EC)",
            }}
          >
            <span
              style={{
                fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                fontSize: 14,
                fontWeight: 700,
                color: "var(--color-brand, #0062CC)",
              }}
            >
              {popover.seg.is_deadhead ? "[VET] " : ""}
              {(popover.seg as TrainSegment & { is_refezione?: boolean }).is_refezione
                ? "REFEZ"
                : popover.seg.train_id}
              {(popover.seg as TrainSegment & { is_preheat?: boolean }).is_preheat ? " ●" : ""}
              {(popover.seg as TrainSegment & { cvp?: boolean }).cvp ? " · CVp" : ""}
              {(popover.seg as TrainSegment & { cva?: boolean }).cva ? " · CVa" : ""}
            </span>
            <button
              onClick={closePopover}
              style={{
                background: "transparent",
                border: "none",
                cursor: "pointer",
                color: "var(--color-on-surface-quiet, #6B7280)",
                fontSize: 14,
                lineHeight: 1,
                padding: "2px 4px",
              }}
              aria-label="Chiudi"
            >
              ×
            </button>
          </div>
          <div
            style={{
              fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
              fontSize: 11.5,
            }}
          >
            <div style={{ marginBottom: 2 }}>
              <span style={{ color: "var(--color-on-surface-quiet, #6B7280)" }}>
                Tratta:{" "}
              </span>
              <strong>{popover.seg.from_station}</strong>
              {" → "}
              <strong>{popover.seg.to_station}</strong>
            </div>
            <div style={{ marginBottom: 2 }}>
              <span style={{ color: "var(--color-on-surface-quiet, #6B7280)" }}>
                Orario:{" "}
              </span>
              <strong>{popover.seg.dep_time}</strong>
              {" → "}
              <strong>{popover.seg.arr_time}</strong>
            </div>
            <div style={{ marginBottom: 2 }}>
              <span style={{ color: "var(--color-on-surface-quiet, #6B7280)" }}>
                Tipo:{" "}
              </span>
              <strong>
                {popover.seg.is_deadhead
                  ? "Vettura (deadhead)"
                  : popover.seg.is_refezione
                  ? "Refezione"
                  : "Condotta"}
              </strong>
            </div>

            {/* Accessori ACCp/ACCa (solo se presenti e > 0) */}
            {((popover.seg.accp_min ?? 0) > 0 || (popover.seg.acca_min ?? 0) > 0) && (
              <div
                style={{
                  marginTop: 6,
                  paddingTop: 6,
                  boxShadow: "inset 0 1px 0 var(--color-ghost, #E1E5EC)",
                }}
              >
                {(popover.seg.accp_min ?? 0) > 0 && (
                  <div style={{ marginBottom: 2 }}>
                    <span style={{ color: "var(--color-on-surface-quiet, #6B7280)" }}>
                      ACCp (preparazione):{" "}
                    </span>
                    <strong>{popover.seg.accp_min}&apos;</strong>
                    {popover.seg.is_preheat && (
                      <span style={{ marginLeft: 6, color: "#0062CC" }}>
                        ● preriscaldo
                      </span>
                    )}
                  </div>
                )}
                {(popover.seg.acca_min ?? 0) > 0 && (
                  <div style={{ marginBottom: 2 }}>
                    <span style={{ color: "var(--color-on-surface-quiet, #6B7280)" }}>
                      ACCa (spegnimento):{" "}
                    </span>
                    <strong>{popover.seg.acca_min}&apos;</strong>
                  </div>
                )}
              </div>
            )}

            {/* Cambio volante CVp/CVa (solo se presenti) */}
            {((popover.seg.cv_before_min ?? 0) > 0 || (popover.seg.cv_after_min ?? 0) > 0) && (
              <div
                style={{
                  marginTop: 6,
                  paddingTop: 6,
                  boxShadow: "inset 0 1px 0 var(--color-ghost, #E1E5EC)",
                }}
              >
                {(popover.seg.cv_before_min ?? 0) > 0 && (
                  <div style={{ marginBottom: 2 }}>
                    <span style={{ color: "#B45309" }}>CVp (cambio volante in):</span>{" "}
                    <strong>{popover.seg.cv_before_min}&apos;</strong>
                  </div>
                )}
                {(popover.seg.cv_after_min ?? 0) > 0 && (
                  <div style={{ marginBottom: 2 }}>
                    <span style={{ color: "#6B21A8" }}>CVa (cambio volante out):</span>{" "}
                    <strong>{popover.seg.cv_after_min}&apos;</strong>
                  </div>
                )}
              </div>
            )}

            {/* Diagnostica gap materiale */}
            {(popover.seg.gap_before != null || popover.seg.gap_after != null) && (
              <div
                style={{
                  marginTop: 6,
                  paddingTop: 6,
                  boxShadow: "inset 0 1px 0 var(--color-ghost, #E1E5EC)",
                  fontSize: 10.5,
                  color: "var(--color-on-surface-quiet, #6B7280)",
                }}
              >
                Gap materiale:{" "}
                {popover.seg.gap_before != null ? `${popover.seg.gap_before}' prima` : "primo"}
                {" · "}
                {popover.seg.gap_after != null ? `${popover.seg.gap_after}' dopo` : "ultimo"}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
