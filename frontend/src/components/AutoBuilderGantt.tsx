/**
 * AutoBuilderGantt — visualizzazione orizzontale (Gantt-like) dei turni
 * generati dall'auto-builder.
 *
 * MIGRATO (23/04/2026) alla base `GanttSheet` v3 (falsa riga PDF Trenord,
 * vedi `docs/HANDOFF-gantt-v3.md`). Props pubbliche invariate rispetto
 * alla versione legacy — mappatura internal dei segmenti da
 * `TrainSegment` al tipo `GanttSegment`.
 *
 * Mappatura:
 *   seg.is_deadhead === true               → kind "dh"  (vettura tratteggiata)
 *   seg.is_refezione === true              → kind "refez"
 *   seg.is_preheat  === true (se presente) → preheat: true sul kind "cond"
 *   altrimenti                             → kind "cond" (condotta)
 *
 * Se `mealStart` / `mealEnd` sono forniti e nessun segmento ha
 * `is_refezione`, viene iniettato un segmento virtuale refez al tempo
 * indicato (compatibilita' con API legacy).
 */
import { useMemo } from "react"
import type { TrainSegment } from "@/lib/api"
import { GanttSheet } from "@/components/gantt/GanttSheet"
import type { GanttSegment, GanttRow } from "@/components/gantt/types"


interface Props {
  segments: TrainSegment[]
  presentationTime?: string
  endTime?: string
  mealStart?: string
  mealEnd?: string
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
}: Props) {
  const view = useMemo(() => {
    if (!segments || segments.length === 0) return null

    // ─── Mapping TrainSegment → GanttSegment ───
    const mapped: GanttSegment[] = segments.map((seg) => {
      const s = seg as TrainSegment & {
        is_refezione?: boolean
        is_preheat?: boolean
        cvp?: boolean
        cva?: boolean
      }
      const isRefez = Boolean(s.is_refezione)
      const isDH = !isRefez && Boolean(s.is_deadhead)
      return {
        kind: isRefez ? "refez" : isDH ? "dh" : "cond",
        train_id: s.train_id,
        from_station: s.from_station,
        to_station: s.to_station,
        dep_time: s.dep_time,
        arr_time: s.arr_time,
        preheat: s.is_preheat,
        cvp: s.cvp,
        cva: s.cva,
      }
    })

    // Inietta refezione virtuale se mealStart/End presenti e nessuna refez nei dati
    const hasRefez = mapped.some((s) => s.kind === "refez")
    if (!hasRefez && mealStart && mealEnd) {
      // Trova stazione in cui cade la refezione (per label): usa la
      // stazione di arrivo del segmento precedente al mealStart, se esiste.
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
      // Inserisci ordinato per dep_time
      const insertAt = mapped.findIndex(
        (s) => timeToMin(s.dep_time) > mealStartMin,
      )
      if (insertAt === -1) mapped.push(refezSeg)
      else mapped.splice(insertAt, 0, refezSeg)
    }

    // ─── Range orario ───
    const startAnchor = presentationTime
      ? timeToMin(presentationTime)
      : timeToMin(segments[0].dep_time)
    let endAnchor = endTime
      ? timeToMin(endTime)
      : timeToMin(segments[segments.length - 1].arr_time)
    if (endAnchor < startAnchor) endAnchor += 1440

    const startHour = Math.floor(startAnchor / 60)
    const endHour = Math.ceil(endAnchor / 60)

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

  return (
    <div
      className="overflow-x-auto"
      style={{
        backgroundColor: "var(--color-surface-container-low)",
        borderRadius: 8,
        padding: "4px 4px",
      }}
    >
      <GanttSheet
        rows={view.rows}
        dayHead={view.dayHead}
        metrics={view.metrics}
        range={view.range}
        palette="hybrid"
        labels="auto"
        minutes="hhmm"
      />
    </div>
  )
}
