/**
 * PdcGanttV2 — wrapper di compatibilita' su `GanttSheet` esteso.
 *
 * Dal 2026-04-23 questo componente e' un wrapper ~200 righe che mappa
 * l'interfaccia legacy (`PdcBlock[]` + callback block-based) sulla
 * nuova base `GanttSheet` con layer interazioni
 * (vedi `docs/HANDOFF-gantt-v3-interactions.md`).
 *
 * Le props pubbliche restano invariate per i 3 consumer
 * (`PdcPage`, `PdcBuilderPage`, `PdcDepotPage`). Cambia solo la
 * resa: ora il Gantt ha l'estetica "falsa riga PDF" v3.
 */

import { useMemo } from "react"
import type { PdcBlock } from "@/lib/api"
import { GanttSheet } from "@/components/gantt/GanttSheet"
import type {
  GanttSegment,
  GanttRow,
  GanttMetrics,
  GanttDayHead,
  CrossDragPayload,
} from "@/components/gantt/types"
import { timeToMin } from "@/components/gantt/tokens"


export type GanttAction =
  | "edit"
  | "move"
  | "duplicate"
  | "link"
  | "warn"
  | "detail"
  | "history"
  | "delete"


export interface CrossDayDragPayload {
  ganttId: string
  block: PdcBlock
  index: number
  linkedCvp?: PdcBlock
  linkedCva?: PdcBlock
}


interface PdcGanttV2Props {
  blocks: PdcBlock[]
  startTime?: string
  endTime?: string
  onBlockClick?: (block: PdcBlock, index: number) => void
  onTimelineClick?: (hour: number, minute: number) => void
  onBlocksChange?: (
    changes: Record<number, { start_time?: string; end_time?: string }>,
  ) => void
  onAction?: (action: GanttAction, block: PdcBlock, index: number) => void
  ganttId?: string
  onCrossDayDrop?: (
    payload: CrossDayDragPayload,
    targetGanttId: string,
    dropHourMinute: { hour: number; minute: number },
  ) => void
  onCrossDayDragStart?: (payload: CrossDayDragPayload) => void
  onCrossDayRemove?: (index: number, withLinkedCvs: boolean) => void
  label?: string
  depot?: string
  height?: number
  snapMinutes?: number
  dragThresholdPx?: number
  debug?: boolean
  hideActionBar?: boolean
  autoFit?: boolean
}


function fmtHM(min: number): string {
  const m = ((min % 1440) + 1440) % 1440
  return (
    String(Math.floor(m / 60)).padStart(2, "0") +
    "h" +
    String(m % 60).padStart(2, "0")
  )
}


interface MappedView {
  segments: GanttSegment[]
  segToBlockIdx: number[]       // segIdx → blockIdx del blocco "principale" (per treni: il treno, non i CVp/CVa merged)
  cvpBlockIdxForSeg: (number | null)[]  // segIdx → blockIdx del CVp adiacente (se merged), altrimenti null
  cvaBlockIdxForSeg: (number | null)[]  // segIdx → blockIdx del CVa adiacente
}


function mapBlocksToSegments(blocks: PdcBlock[]): MappedView {
  const segments: GanttSegment[] = []
  const segToBlockIdx: number[] = []
  const cvpBlockIdxForSeg: (number | null)[] = []
  const cvaBlockIdxForSeg: (number | null)[] = []

  for (let i = 0; i < blocks.length; i++) {
    const b = blocks[i]
    // CVp e CVa vengono fusi nel treno adiacente come flag
    if (b.block_type === "cv_partenza" || b.block_type === "cv_arrivo") continue
    // "available" non ha rendering Gantt (la row diventa vuota — il
    // parent decide di mostrare un placeholder)
    if (b.block_type === "available") continue

    let kind: GanttSegment["kind"] = "cond"
    if (b.block_type === "coach_transfer") kind = "dh"
    else if (b.block_type === "meal") kind = "refez"
    else if (b.block_type === "scomp") kind = "scomp"
    // train -> cond (default)

    // Cerca CVp/CVa adiacenti per il treno
    let cvp = false
    let cva = false
    let cvpBlockIdx: number | null = null
    let cvaBlockIdx: number | null = null
    if (b.block_type === "train") {
      const prev = blocks[i - 1]
      if (prev && prev.block_type === "cv_partenza") {
        cvp = true
        cvpBlockIdx = i - 1
      }
      const next = blocks[i + 1]
      if (next && next.block_type === "cv_arrivo") {
        cva = true
        cvaBlockIdx = i + 1
      }
    }

    const seg: GanttSegment = {
      kind,
      train_id: b.train_id || (b.block_type === "scomp" ? "S.COMP" : b.block_type === "meal" ? "REFEZ" : ""),
      from_station: b.from_station || "",
      to_station: b.to_station || "",
      dep_time: b.start_time || "",
      arr_time: b.end_time || b.start_time || "",
      preheat: Boolean(b.accessori_maggiorati),
      cvp,
      cva,
    }
    segments.push(seg)
    segToBlockIdx.push(i)
    cvpBlockIdxForSeg.push(cvpBlockIdx)
    cvaBlockIdxForSeg.push(cvaBlockIdx)
  }

  return { segments, segToBlockIdx, cvpBlockIdxForSeg, cvaBlockIdxForSeg }
}


export function PdcGanttV2({
  blocks,
  startTime,
  endTime,
  onBlockClick,
  onTimelineClick,
  onBlocksChange,
  onAction,
  ganttId,
  onCrossDayDrop,
  onCrossDayDragStart,
  onCrossDayRemove,
  label,
  snapMinutes = 5,
  dragThresholdPx = 4,
  hideActionBar = false,
  autoFit = false,
}: PdcGanttV2Props) {
  const view = useMemo<{
    mapped: MappedView
    rows: GanttRow[]
    dayHead: GanttDayHead
    metrics: GanttMetrics
    range: [number, number]
  } | null>(() => {
    // Empty / disponibile
    const isAvailable =
      !blocks.length ||
      (blocks.length === 1 && blocks[0].block_type === "available")
    if (isAvailable) return null

    const mapped = mapBlocksToSegments(blocks)
    if (mapped.segments.length === 0) return null

    // Range temporale
    const times: number[] = []
    for (const s of mapped.segments) {
      if (s.dep_time) times.push(timeToMin(s.dep_time))
      if (s.arr_time) {
        const dep = s.dep_time ? timeToMin(s.dep_time) : 0
        let arr = timeToMin(s.arr_time)
        if (s.dep_time && arr < dep) arr += 1440
        times.push(arr)
      }
    }
    if (startTime) times.push(timeToMin(startTime))
    if (endTime) {
      const sT = startTime ? timeToMin(startTime) : 0
      let eT = timeToMin(endTime)
      if (startTime && eT < sT) eT += 1440
      times.push(eT)
    }
    const minT = times.length ? Math.min(...times) : 0
    const maxT = times.length ? Math.max(...times) : 1440

    let hStart: number
    let hEnd: number
    if (autoFit) {
      hStart = Math.max(0, Math.floor((minT - 30) / 60))
      hEnd = Math.min(48, Math.ceil((maxT + 30) / 60))
      if (hEnd - hStart < 4) hEnd = hStart + 4
    } else {
      hStart = Math.floor(minT / 60)
      hEnd = Math.ceil(maxT / 60)
      if (hEnd <= hStart) hEnd = hStart + 4
    }

    // Metriche placeholder (il parent espone le proprie sopra o sotto
    // il Gantt; qui passiamo segnaposti che il consumer ignora via CSS)
    const condottaMin = mapped.segments
      .filter((s) => s.kind === "cond")
      .reduce((acc, s) => {
        const d = timeToMin(s.dep_time)
        let a = timeToMin(s.arr_time)
        if (a < d) a += 1440
        return acc + (a - d)
      }, 0)
    const totalMin = maxT - minT

    const row: GanttRow = {
      label: label || "",
      segments: mapped.segments,
    }

    return {
      mapped,
      rows: [row],
      dayHead: {
        num: 0,
        pres: startTime || mapped.segments[0].dep_time,
        end: endTime || mapped.segments[mapped.segments.length - 1].arr_time,
      },
      metrics: {
        lav: fmtHM(totalMin),
        cct: fmtHM(condottaMin),
        km: 0,
        not: "no" as const,
        rip: "—",
      },
      range: [hStart, hEnd] as [number, number],
    }
  }, [blocks, startTime, endTime, label, autoFit])

  // Placeholder "Disponibile"
  if (
    !blocks.length ||
    (blocks.length === 1 && blocks[0].block_type === "available")
  ) {
    return (
      <div
        className="flex items-center justify-center rounded-md border border-dashed border-slate-300 bg-slate-50 text-sm font-medium text-slate-500"
        style={{ minHeight: 72 }}
      >
        Disponibile · riposo a casa
      </div>
    )
  }

  if (!view) return null

  const { mapped, rows, dayHead, metrics, range } = view

  // ─── Bridge legacy callback → nuove API GanttSheet ───

  const handleSegmentDrag = onBlocksChange
    ? (rowIdx: number, segIdx: number, changes: { dep_time?: string; arr_time?: string }) => {
        void rowIdx
        const blockIdx = mapped.segToBlockIdx[segIdx]
        const cvpIdx = mapped.cvpBlockIdxForSeg[segIdx]
        const cvaIdx = mapped.cvaBlockIdxForSeg[segIdx]
        const legacyChanges: Record<number, { start_time?: string; end_time?: string }> = {}
        const patch: { start_time?: string; end_time?: string } = {}
        if (changes.dep_time !== undefined) patch.start_time = changes.dep_time
        if (changes.arr_time !== undefined) patch.end_time = changes.arr_time
        legacyChanges[blockIdx] = patch
        // CVp segue dep_time del treno
        if (cvpIdx !== null && changes.dep_time !== undefined) {
          legacyChanges[cvpIdx] = {
            start_time: changes.dep_time,
            end_time: changes.dep_time,
          }
        }
        // CVa segue arr_time del treno
        if (cvaIdx !== null && changes.arr_time !== undefined) {
          legacyChanges[cvaIdx] = {
            start_time: changes.arr_time,
            end_time: changes.arr_time,
          }
        }
        onBlocksChange(legacyChanges)
      }
    : undefined

  const handleTimelineClick = onTimelineClick
    ? (hour: number, minute: number, _rowIdx: number) => {
        onTimelineClick(hour, minute)
      }
    : undefined

  const buildLegacyCrossPayload = (p: CrossDragPayload): CrossDayDragPayload => {
    const blockIdx = mapped.segToBlockIdx[p.segIdx]
    const cvpIdx = mapped.cvpBlockIdxForSeg[p.segIdx]
    const cvaIdx = mapped.cvaBlockIdxForSeg[p.segIdx]
    return {
      ganttId: p.ganttId,
      block: blocks[blockIdx],
      index: blockIdx,
      linkedCvp: cvpIdx !== null ? blocks[cvpIdx] : undefined,
      linkedCva: cvaIdx !== null ? blocks[cvaIdx] : undefined,
    }
  }

  const handleCrossDragStart = onCrossDayDragStart
    ? (p: CrossDragPayload) => onCrossDayDragStart(buildLegacyCrossPayload(p))
    : undefined

  const handleCrossDrop = onCrossDayDrop
    ? (
        p: CrossDragPayload,
        targetGanttId: string,
        dropTime: { hour: number; minute: number; rowIdx: number },
      ) =>
        onCrossDayDrop(buildLegacyCrossPayload(p), targetGanttId, {
          hour: dropTime.hour,
          minute: dropTime.minute,
        })
    : undefined

  const handleCrossRemove = onCrossDayRemove
    ? (segIdx: number, withLinkedCvs: boolean) => {
        const blockIdx = mapped.segToBlockIdx[segIdx]
        onCrossDayRemove(blockIdx, withLinkedCvs)
      }
    : undefined

  const handleAction = onAction
    ? (
        action: import("@/components/gantt/types").GanttAction,
        _seg: GanttSegment,
        _rowIdx: number,
        segIdx: number,
      ) => {
        const blockIdx = mapped.segToBlockIdx[segIdx]
        onAction(action, blocks[blockIdx], blockIdx)
      }
    : undefined

  const handleSegmentClick = onBlockClick
    ? (_seg: GanttSegment, _rowIdx: number) => {
        // onSegmentClick del GanttSheet non da' segIdx — lo ritroviamo
        // per reference (match stretto per obj identity)
        const segIdx = mapped.segments.indexOf(_seg)
        if (segIdx < 0) return
        const blockIdx = mapped.segToBlockIdx[segIdx]
        onBlockClick(blocks[blockIdx], blockIdx)
      }
    : undefined

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
        rows={rows}
        dayHead={dayHead}
        metrics={metrics}
        range={range}
        palette="hybrid"
        labels="auto"
        minutes="hhmm"
        ganttId={ganttId}
        hideActionBar={hideActionBar}
        snapMinutes={snapMinutes}
        dragThresholdPx={dragThresholdPx}
        onSegmentClick={handleSegmentClick}
        onSegmentDrag={handleSegmentDrag}
        onTimelineClick={handleTimelineClick}
        onCrossDragStart={handleCrossDragStart}
        onCrossDrop={handleCrossDrop}
        onCrossRemove={handleCrossRemove}
        onAction={handleAction}
      />
    </div>
  )
}
