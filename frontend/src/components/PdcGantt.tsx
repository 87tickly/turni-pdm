/**
 * PdcGantt — Timeline Gantt interattivo ispirato al PDF Trenord.
 *
 * Features:
 *  - Barre colorate e ingrandite per tipo blocco
 *  - Asse 3→24→1→2→3 orizzontale
 *  - Etichette sopra + stazioni ai bordi
 *  - Orari al minuto sotto ogni blocco
 *  - Pallino nero ● per accessori maggiorati
 *
 * Interazione (solo se `onBlocksChange` è fornito):
 *  - Drag del CENTRO di una barra → sposta tutto il blocco preservando la durata
 *  - Drag dei BORDI (entro 6px dall'estremo) → resize start/end
 *  - Click singolo → onBlockClick (selezione/edit)
 *  - Click su area vuota → onTimelineClick (aggiungi blocco)
 *
 * Gli altri blocchi non vengono toccati durante il drag di uno solo.
 */

import { useState, useRef, useCallback, useEffect } from "react"
import type { PdcBlock } from "@/lib/api"

interface PdcGanttProps {
  blocks: PdcBlock[]
  startTime?: string
  endTime?: string
  onBlockClick?: (block: PdcBlock, index: number) => void
  onTimelineClick?: (hour: number, minute: number) => void
  /**
   * Callback chiamato al rilascio del mouse dopo drag/resize.
   * Può modificare più blocchi insieme (es. quando si sposta un treno
   * trascina anche CVp/CVa adiacenti).
   */
  onBlocksChange?: (
    changes: Record<number, { start_time?: string; end_time?: string }>
  ) => void
  label?: string
  depot?: string
  height?: number
  /** Snap del drag in minuti (default 5) */
  snapMinutes?: number
  /** Soglia in pixel prima di avviare il drag (default 4) */
  dragThresholdPx?: number
}

// Ritorna gli indici dei CVp precedenti e CVa successivi "agganciati" a un treno.
// Regola: un CVp immediatamente PRIMA di un train è sua "partenza vincolata".
//         Un CVa immediatamente DOPO è il suo "arrivo vincolato".
function getLinkedCVs(blocks: PdcBlock[], trainIdx: number): {
  cvPrev: number | null
  cvNext: number | null
} {
  let cvPrev: number | null = null
  let cvNext: number | null = null
  if (blocks[trainIdx]?.block_type !== "train") return { cvPrev, cvNext }
  const prev = blocks[trainIdx - 1]
  if (prev && prev.block_type === "cv_partenza") cvPrev = trainIdx - 1
  const next = blocks[trainIdx + 1]
  if (next && next.block_type === "cv_arrivo") cvNext = trainIdx + 1
  return { cvPrev, cvNext }
}

// Ritorna l'indice del treno "padrone" di un CVp/CVa (quello a cui è agganciato)
function getParentTrainIndex(
  blocks: PdcBlock[],
  cvIdx: number
): number | null {
  const cv = blocks[cvIdx]
  if (!cv) return null
  if (cv.block_type === "cv_partenza") {
    const next = blocks[cvIdx + 1]
    if (next && next.block_type === "train") return cvIdx + 1
  }
  if (cv.block_type === "cv_arrivo") {
    const prev = blocks[cvIdx - 1]
    if (prev && prev.block_type === "train") return cvIdx - 1
  }
  return null
}

// ── Scala temporale ────────────────────────────────────────────
const ORIGIN_HOUR = 3
const SPAN_HOURS = 24

function hhmmToMinutesRel(hhmm: string): number | null {
  if (!hhmm || !/^\d{1,2}:\d{2}$/.test(hhmm)) return null
  const [h, m] = hhmm.split(":").map(Number)
  let hourAdj = h
  if (h < ORIGIN_HOUR) hourAdj = h + 24
  return (hourAdj - ORIGIN_HOUR) * 60 + m
}

function minutesRelToHhmm(minRel: number): string {
  const abs = (ORIGIN_HOUR * 60 + Math.max(0, Math.min(minRel, SPAN_HOURS * 60)))
    % (24 * 60)
  const h = Math.floor(abs / 60)
  const m = abs % 60
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}`
}

// Fill orari mancanti (per render, non modifica i blocchi originali)
function fillBlockTimes(
  blocks: PdcBlock[],
  dayStart?: string,
  dayEnd?: string,
): PdcBlock[] {
  const out = blocks.map((b) => ({ ...b }))
  const n = out.length
  if (n === 0) return out
  const isPuntual = (bt: string) =>
    bt === "cv_partenza" || bt === "cv_arrivo"

  for (const b of out) {
    if (isPuntual(b.block_type)) {
      if (!b.start_time && b.end_time) b.start_time = b.end_time
      else if (!b.end_time && b.start_time) b.end_time = b.start_time
    }
  }

  type Anchor = { pos: number; time: number }
  const anchors: Anchor[] = []
  const dayStartMin = dayStart ? hhmmToMinutesRel(dayStart) : null
  const dayEndMin = dayEnd ? hhmmToMinutesRel(dayEnd) : null
  if (dayStartMin !== null) anchors.push({ pos: -0.5, time: dayStartMin })
  for (let i = 0; i < n; i++) {
    const t = hhmmToMinutesRel(out[i].start_time)
    if (t !== null) anchors.push({ pos: i, time: t })
  }
  if (dayEndMin !== null) anchors.push({ pos: n - 0.5, time: dayEndMin })

  const findPrev = (i: number): Anchor | null => {
    let best: Anchor | null = null
    for (const a of anchors) {
      if (a.pos < i && (!best || a.pos > best.pos)) best = a
    }
    return best
  }
  const findNext = (i: number): Anchor | null => {
    let best: Anchor | null = null
    for (const a of anchors) {
      if (a.pos > i && (!best || a.pos < best.pos)) best = a
    }
    return best
  }

  for (let i = 0; i < n; i++) {
    if (out[i].start_time) continue
    const before = findPrev(i)
    const after = findNext(i)
    if (before && after) {
      const slot = (after.time - before.time) / (after.pos - before.pos)
      out[i].start_time = minutesRelToHhmm(
        Math.round(before.time + slot * (i - before.pos))
      )
    } else if (before) out[i].start_time = minutesRelToHhmm(before.time)
    else if (after) out[i].start_time = minutesRelToHhmm(after.time)
  }

  for (let i = 0; i < n - 1; i++) {
    if (!out[i].end_time && out[i + 1].start_time) {
      out[i].end_time = out[i + 1].start_time
    }
  }
  if (!out[n - 1].end_time && dayEnd) out[n - 1].end_time = dayEnd

  for (const b of out) {
    if (isPuntual(b.block_type)) {
      if (!b.start_time && b.end_time) b.start_time = b.end_time
      else if (!b.end_time && b.start_time) b.end_time = b.start_time
    }
  }

  return out
}

// ── Stili barre colorate per tipo ──────────────────────────────
// Il treno rimane dominante; gli altri blocchi sono molto piu' sottili
// per metterli in secondo piano (come nel PDF Trenord).
const BAR_H_TRAIN = 26
const BAR_H_COACH = 10
const BAR_H_MEAL = 10
const BAR_H_SCOMP = 8
const MARKER_H = 24

function blockStyle(t: PdcBlock["block_type"]) {
  switch (t) {
    case "train":
      return {
        fill: "#0062CC",
        stroke: "#0050A7",
        h: BAR_H_TRAIN,
        dash: null as string | null,
        opacity: 0.92,
      }
    case "coach_transfer":
      return {
        fill: "#A78BFA",
        stroke: "#7C3AED",
        h: BAR_H_COACH,
        dash: "3 2",
        opacity: 0.5,
      }
    case "meal":
      return {
        fill: "#34D399",
        stroke: "#059669",
        h: BAR_H_MEAL,
        dash: "3 2",
        opacity: 0.5,
      }
    case "scomp":
      return {
        fill: "#CBD5E1",
        stroke: "#94A3B8",
        h: BAR_H_SCOMP,
        dash: "3 2",
        opacity: 0.7,
      }
    case "cv_partenza":
    case "cv_arrivo":
      return {
        fill: "#F59E0B",
        stroke: "#B45309",
        h: MARKER_H,
        dash: null as string | null,
        opacity: 1,
      }
    case "available":
      return {
        fill: "#F1F5F9",
        stroke: "#CBD5E1",
        h: BAR_H_SCOMP,
        dash: null as string | null,
        opacity: 1,
      }
    default:
      return {
        fill: "#94A3B8",
        stroke: "#64748B",
        h: BAR_H_COACH,
        dash: null as string | null,
        opacity: 0.8,
      }
  }
}

function blockLabel(b: PdcBlock): string {
  const id = b.train_id || b.vettura_id || ""
  if (b.block_type === "cv_partenza") return `CVp ${id}`.trim()
  if (b.block_type === "cv_arrivo") return `CVa ${id}`.trim()
  if (b.block_type === "meal") return "REFEZ"
  if (b.block_type === "scomp") return "S.COMP"
  if (b.block_type === "available") return "Disponibile"
  return id
}

// ── Componente ────────────────────────────────────────────────

type DragState = {
  /** Gruppo di indici che si muovono insieme (train + CVp/CVa agganciati) */
  groupIndices: number[]
  kind: "move" | "resize-start" | "resize-end"
  /** Snapshot degli orari iniziali di tutti gli indici del gruppo */
  initial: Record<number, { sm: number; em: number }>
  initialMouseX: number
  /** True quando il movimento ha superato la soglia */
  active: boolean
}

export function PdcGantt({
  blocks: rawBlocks,
  startTime,
  endTime,
  onBlockClick,
  onTimelineClick,
  onBlocksChange,
  label,
  depot,
  height = 220,
  snapMinutes = 5,
  dragThresholdPx = 4,
}: PdcGanttProps) {
  const filled = fillBlockTimes(rawBlocks, startTime, endTime)
  // Override temporanei durante drag (preview ottimistico, non sovrascrive il parent)
  const [overrides, setOverrides] = useState<
    Record<number, { start_time?: string; end_time?: string }>
  >({})
  const [dragState, setDragState] = useState<DragState | null>(null)
  const svgRef = useRef<SVGSVGElement | null>(null)

  // Applica gli overrides sopra i blocchi "filled"
  const blocks = filled.map((b, i) => ({ ...b, ...(overrides[i] || {}) }))

  // Layout parametri
  const CHART_W = 1400
  const PAD_L = 110
  const PAD_R = 30
  const PAD_T = 50
  const axisY = PAD_T + 60
  const plotW = CHART_W - PAD_L - PAD_R
  const minuteToX = (min: number) => PAD_L + (min / (SPAN_HOURS * 60)) * plotW

  const svgXToMinute = useCallback(
    (svgX: number) => {
      if (svgX < PAD_L) return 0
      if (svgX > PAD_L + plotW) return SPAN_HOURS * 60
      return ((svgX - PAD_L) / plotW) * SPAN_HOURS * 60
    },
    [plotW]
  )

  // Converte coordinata mouse (clientX) -> svgX (viewBox space)
  const clientXToSvgX = useCallback((clientX: number): number => {
    const svg = svgRef.current
    if (!svg) return 0
    const rect = svg.getBoundingClientRect()
    return ((clientX - rect.left) / rect.width) * CHART_W
  }, [])

  // Tick orari
  const ticks: { hour: number; x: number }[] = []
  for (let i = 0; i <= SPAN_HOURS; i++) {
    const hour = (ORIGIN_HOUR + i) % 24
    ticks.push({ hour, x: minuteToX(i * 60) })
  }

  const startMin = startTime ? hhmmToMinutesRel(startTime) : null
  const endMin = endTime ? hhmmToMinutesRel(endTime) : null

  // ── Drag handlers ────────────────────────────────────────────
  // Avvia drag calcolando il "gruppo" agganciato (train + CVp + CVa)
  const startDrag = (
    e: React.MouseEvent,
    index: number,
    kind: DragState["kind"]
  ) => {
    if (!onBlocksChange) return
    e.stopPropagation()
    e.preventDefault()

    // I CVp/CVa NON si muovono singolarmente: se l'utente afferra un CV,
    // reindirizza il drag al treno padrone.
    const srcBlock = blocks[index]
    let mainIndex = index
    if (srcBlock.block_type === "cv_partenza" || srcBlock.block_type === "cv_arrivo") {
      const parent = getParentTrainIndex(blocks, index)
      if (parent !== null) {
        mainIndex = parent
      } else {
        // CV "orfano" (senza treno adiacente) → drag sul solo CV
      }
    }

    // Costruisci gruppo: train + CVp (se presente) + CVa (se presente)
    const groupIndices: number[] = [mainIndex]
    if (blocks[mainIndex].block_type === "train") {
      const { cvPrev, cvNext } = getLinkedCVs(blocks, mainIndex)
      if (cvPrev !== null) groupIndices.unshift(cvPrev)
      if (cvNext !== null) groupIndices.push(cvNext)
    }

    // Snapshot degli orari iniziali per ogni membro del gruppo
    const initial: Record<number, { sm: number; em: number }> = {}
    for (const gi of groupIndices) {
      const b = blocks[gi]
      const sm = hhmmToMinutesRel(b.start_time)
      const em = hhmmToMinutesRel(b.end_time)
      if (sm === null) continue
      initial[gi] = { sm, em: em !== null && em > sm ? em : sm }
    }

    setDragState({
      groupIndices,
      kind,
      initial,
      initialMouseX: e.clientX,
      active: false,
    })
  }

  useEffect(() => {
    if (!dragState) return
    const handleMove = (e: MouseEvent) => {
      const deltaPx = Math.abs(e.clientX - dragState.initialMouseX)

      // Threshold anti-click: non avvio il drag finché non supero N pixel
      if (!dragState.active && deltaPx < dragThresholdPx) return

      if (!dragState.active) {
        setDragState((s) => (s ? { ...s, active: true } : s))
      }

      const dxSvg =
        clientXToSvgX(e.clientX) - clientXToSvgX(dragState.initialMouseX)
      const deltaMinRaw = (dxSvg / plotW) * SPAN_HOURS * 60
      // Snap a snapMinutes
      const deltaMin = Math.round(deltaMinRaw / snapMinutes) * snapMinutes
      const maxMin = SPAN_HOURS * 60

      const nextOverrides: Record<number, { start_time: string; end_time: string }> = {}

      if (dragState.kind === "move") {
        // Sposta TUTTO il gruppo (train + CVp/CVa) del medesimo delta
        for (const gi of dragState.groupIndices) {
          const init = dragState.initial[gi]
          if (!init) continue
          let newSm = init.sm + deltaMin
          let newEm = init.em + deltaMin
          newSm = Math.max(0, Math.min(newSm, maxMin))
          newEm = Math.max(0, Math.min(newEm, maxMin))
          nextOverrides[gi] = {
            start_time: minutesRelToHhmm(newSm),
            end_time: minutesRelToHhmm(newEm),
          }
        }
      } else if (dragState.kind === "resize-start") {
        // Resize start del treno. Il CVp associato si aggancia al nuovo start.
        const trainIdx = dragState.groupIndices.find(
          (gi) => blocks[gi].block_type === "train"
        )
        if (trainIdx !== undefined) {
          const init = dragState.initial[trainIdx]
          if (init) {
            let newSm = init.sm + deltaMin
            if (newSm > init.em - snapMinutes) newSm = init.em - snapMinutes
            newSm = Math.max(0, newSm)
            nextOverrides[trainIdx] = {
              start_time: minutesRelToHhmm(newSm),
              end_time: minutesRelToHhmm(init.em),
            }
            // CVp agganciato: spostato al newSm
            const cvpIdx = dragState.groupIndices.find(
              (gi) => blocks[gi].block_type === "cv_partenza"
            )
            if (cvpIdx !== undefined) {
              nextOverrides[cvpIdx] = {
                start_time: minutesRelToHhmm(newSm),
                end_time: minutesRelToHhmm(newSm),
              }
            }
          }
        }
      } else if (dragState.kind === "resize-end") {
        const trainIdx = dragState.groupIndices.find(
          (gi) => blocks[gi].block_type === "train"
        )
        if (trainIdx !== undefined) {
          const init = dragState.initial[trainIdx]
          if (init) {
            let newEm = init.em + deltaMin
            if (newEm < init.sm + snapMinutes) newEm = init.sm + snapMinutes
            newEm = Math.min(maxMin, newEm)
            nextOverrides[trainIdx] = {
              start_time: minutesRelToHhmm(init.sm),
              end_time: minutesRelToHhmm(newEm),
            }
            const cvaIdx = dragState.groupIndices.find(
              (gi) => blocks[gi].block_type === "cv_arrivo"
            )
            if (cvaIdx !== undefined) {
              nextOverrides[cvaIdx] = {
                start_time: minutesRelToHhmm(newEm),
                end_time: minutesRelToHhmm(newEm),
              }
            }
          }
        }
      }

      setOverrides(nextOverrides)
    }
    const handleUp = () => {
      if (!onBlocksChange || !dragState) return
      if (dragState.active && Object.keys(overrides).length > 0) {
        onBlocksChange(overrides)
      }
      setDragState(null)
      setOverrides({})
    }
    window.addEventListener("mousemove", handleMove)
    window.addEventListener("mouseup", handleUp)
    return () => {
      window.removeEventListener("mousemove", handleMove)
      window.removeEventListener("mouseup", handleUp)
    }
  }, [
    dragState,
    overrides,
    plotW,
    clientXToSvgX,
    onBlocksChange,
    snapMinutes,
    dragThresholdPx,
    blocks,
  ])

  const handleTimelineClick = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!onTimelineClick) return
    if (dragState) return  // non aggiungere durante drag
    const viewX = clientXToSvgX(e.clientX)
    if (viewX < PAD_L || viewX > PAD_L + plotW) return
    const m = svgXToMinute(viewX)
    const absHour = (ORIGIN_HOUR + Math.floor(m / 60)) % 24
    const minute = Math.round(m % 60)
    onTimelineClick(absHour, minute)
  }

  const firstStation =
    blocks.find((b) => b.from_station)?.from_station || depot || ""
  const lastStation =
    [...blocks].reverse().find((b) => b.to_station)?.to_station || depot || ""

  const RESIZE_HANDLE_W = 6

  return (
    <div className="w-full overflow-x-auto border border-border-subtle rounded-lg bg-white p-2">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${CHART_W} ${height}`}
        width="100%"
        preserveAspectRatio="xMinYMid meet"
        style={{
          minWidth: 900,
          cursor: dragState
            ? dragState.kind === "move"
              ? "grabbing"
              : "ew-resize"
            : onTimelineClick
            ? "crosshair"
            : "default",
          userSelect: "none",
        }}
        onClick={handleTimelineClick}
      >
        {/* Label giornata + periodicità a sinistra */}
        {label && (
          <text
            x={8}
            y={axisY - 10}
            fontSize="14"
            fill="#0F172A"
            fontFamily="'Exo 2', sans-serif"
            fontWeight="700"
          >
            {label}
          </text>
        )}
        {startTime && endTime && (
          <text
            x={8}
            y={axisY + 6}
            fontSize="11"
            fill="#64748B"
            fontFamily="monospace"
          >
            [{startTime}] [{endTime}]
          </text>
        )}

        {/* Fascia prestazione */}
        {startMin !== null && endMin !== null && (
          <rect
            x={minuteToX(startMin)}
            y={PAD_T - 10}
            width={Math.max(0, minuteToX(endMin) - minuteToX(startMin))}
            height={axisY - PAD_T + 55}
            fill="#DBEAFE"
            opacity={0.22}
          />
        )}

        {/* Griglia verticale ore */}
        {ticks.map((t, i) => (
          <line
            key={i}
            x1={t.x}
            y1={PAD_T - 10}
            x2={t.x}
            y2={axisY + 5}
            stroke="#E5E7EB"
            strokeWidth={0.5}
          />
        ))}

        {/* Asse orizzontale */}
        <line
          x1={PAD_L}
          y1={axisY}
          x2={PAD_L + plotW}
          y2={axisY}
          stroke="#334155"
          strokeWidth={1.2}
        />

        {/* Tick e numeri ora */}
        {ticks.map((t, i) => (
          <g key={`tick-${i}`}>
            <line x1={t.x} y1={axisY} x2={t.x} y2={axisY + 4} stroke="#334155" />
            <text
              x={t.x}
              y={axisY + 16}
              fontSize="11"
              textAnchor="middle"
              fill="#0F172A"
              fontFamily="'Exo 2', sans-serif"
              fontWeight="500"
            >
              {t.hour}
            </text>
          </g>
        ))}

        {/* Stazioni ai bordi */}
        {firstStation && (
          <text
            x={PAD_L - 6}
            y={PAD_T - 14}
            fontSize="12"
            textAnchor="end"
            fill="#0F172A"
            fontFamily="'Exo 2', sans-serif"
            fontWeight="600"
          >
            {firstStation}
          </text>
        )}
        {lastStation && (
          <text
            x={PAD_L + plotW + 6}
            y={PAD_T - 14}
            fontSize="12"
            textAnchor="start"
            fill="#0F172A"
            fontFamily="'Exo 2', sans-serif"
            fontWeight="600"
          >
            {lastStation}
          </text>
        )}

        {/* Stazioni intermedie: mostrate tra ogni coppia di blocchi
            dove lo stato "stazione attuale" cambia. Label piccola in
            corrispondenza della posizione X (tra end del blocco N e
            start del blocco N+1). */}
        {blocks.map((b, i) => {
          if (i === blocks.length - 1) return null
          const next = blocks[i + 1]
          const endStation = b.to_station
          const nextStart = next.from_station || b.to_station
          // Mostra solo se la stazione è significativa e c'è un gap
          if (!endStation) return null
          const sm = hhmmToMinutesRel(b.end_time) ?? hhmmToMinutesRel(b.start_time)
          const emNext = hhmmToMinutesRel(next.start_time) ?? sm
          if (sm === null || emNext === null) return null
          // Nascondo se etichette coincidono con stazioni depot agli estremi
          if (i === 0 && endStation === firstStation) return null
          // Posiziono la label tra end e start successivo
          const xLabel = (minuteToX(sm) + minuteToX(emNext)) / 2
          const showJoin = endStation === nextStart
          return (
            <g key={`st-${i}`} pointerEvents="none">
              <text
                x={xLabel}
                y={PAD_T - 2}
                fontSize="9"
                textAnchor="middle"
                fill="#475569"
                fontFamily="'Exo 2', sans-serif"
                fontWeight="500"
              >
                {showJoin ? endStation : `${endStation}→${nextStart}`}
              </text>
            </g>
          )
        })}

        {/* Blocchi */}
        {blocks.map((b, i) => {
          const bs = blockStyle(b.block_type)
          const sm = hhmmToMinutesRel(b.start_time)
          const em = hhmmToMinutesRel(b.end_time)
          const labelTxt = blockLabel(b)
          const isDragging = dragState?.groupIndices.includes(i) ?? false

          // CVp/CVa puntuali → marker verticale largo + etichetta sopra
          if (b.block_type === "cv_partenza" || b.block_type === "cv_arrivo") {
            if (sm === null) return null
            const x = minuteToX(sm)
            return (
              <g
                key={i}
                onMouseDown={(e) => startDrag(e, i, "move")}
                onClick={(e) => {
                  if (dragState) return
                  if (onBlockClick) {
                    e.stopPropagation()
                    onBlockClick(b, i)
                  }
                }}
                style={{
                  cursor: onBlocksChange
                    ? isDragging
                      ? "grabbing"
                      : "grab"
                    : onBlockClick
                    ? "pointer"
                    : "default",
                }}
              >
                {/* "Bandierina" */}
                <rect
                  x={x - 3}
                  y={axisY - MARKER_H - 4}
                  width={6}
                  height={MARKER_H + 8}
                  fill={bs.fill}
                  stroke={bs.stroke}
                  strokeWidth={1}
                  rx={1}
                  opacity={isDragging ? 0.75 : 1}
                />
                <text
                  x={x}
                  y={axisY - MARKER_H - 8}
                  fontSize="10"
                  textAnchor="middle"
                  fill="#B45309"
                  fontFamily="'Exo 2', sans-serif"
                  fontWeight="700"
                >
                  {labelTxt}
                </text>
                {b.start_time && (
                  <text
                    x={x}
                    y={axisY + 30}
                    fontSize="9"
                    textAnchor="middle"
                    fill="#475569"
                    fontFamily="monospace"
                  >
                    {b.start_time}
                  </text>
                )}
              </g>
            )
          }

          // Blocchi di durata
          if (sm === null) return null
          const emEff = em !== null && em > sm ? em : sm + 5
          const x1 = minuteToX(sm)
          const x2 = minuteToX(emEff)
          const w = Math.max(3, x2 - x1)
          const barY = axisY - bs.h / 2 - 8
          const midX = x1 + w / 2

          return (
            <g key={i}>
              {/* Corpo della barra (zona drag-move) */}
              <rect
                x={x1}
                y={barY}
                width={w}
                height={bs.h}
                rx={3}
                fill={bs.fill}
                stroke={bs.stroke}
                strokeWidth={1}
                strokeDasharray={bs.dash || undefined}
                opacity={isDragging ? 0.7 : bs.opacity}
                onMouseDown={(e) => startDrag(e, i, "move")}
                onClick={(e) => {
                  if (dragState) return
                  if (onBlockClick) {
                    e.stopPropagation()
                    onBlockClick(b, i)
                  }
                }}
                style={{
                  cursor: onBlocksChange
                    ? isDragging
                      ? "grabbing"
                      : "grab"
                    : onBlockClick
                    ? "pointer"
                    : "default",
                }}
              />

              {/* Handle RESIZE-START (a sinistra) */}
              {onBlocksChange && w > 14 && (
                <rect
                  x={x1}
                  y={barY}
                  width={RESIZE_HANDLE_W}
                  height={bs.h}
                  fill="transparent"
                  onMouseDown={(e) => startDrag(e, i, "resize-start")}
                  style={{ cursor: "ew-resize" }}
                />
              )}

              {/* Handle RESIZE-END (a destra) */}
              {onBlocksChange && w > 14 && (
                <rect
                  x={x2 - RESIZE_HANDLE_W}
                  y={barY}
                  width={RESIZE_HANDLE_W}
                  height={bs.h}
                  fill="transparent"
                  onMouseDown={(e) => startDrag(e, i, "resize-end")}
                  style={{ cursor: "ew-resize" }}
                />
              )}

              {/* Label sopra la barra */}
              {labelTxt && w > 14 && (
                <text
                  x={midX}
                  y={barY - 4}
                  fontSize="10.5"
                  textAnchor="middle"
                  fill="#0F172A"
                  fontFamily="'Exo 2', sans-serif"
                  fontWeight="700"
                  pointerEvents="none"
                >
                  {labelTxt}
                </text>
              )}

              {/* Pallino accessori maggiorati */}
              {b.accessori_maggiorati === 1 && (
                <circle
                  cx={x1 + 6}
                  cy={barY + bs.h / 2}
                  r={3}
                  fill="#000"
                  pointerEvents="none"
                />
              )}

              {/* Orario start sotto asse */}
              {b.start_time && (
                <text
                  x={x1}
                  y={axisY + 30}
                  fontSize="9"
                  textAnchor="middle"
                  fill="#475569"
                  fontFamily="monospace"
                  pointerEvents="none"
                >
                  {b.start_time}
                </text>
              )}
              {/* Orario end sotto asse */}
              {b.end_time && w > 24 && (
                <text
                  x={x2}
                  y={axisY + 30}
                  fontSize="9"
                  textAnchor="middle"
                  fill="#475569"
                  fontFamily="monospace"
                  pointerEvents="none"
                >
                  {b.end_time}
                </text>
              )}
            </g>
          )
        })}
      </svg>

      {/* Legenda + hint interattivo */}
      <div className="flex flex-wrap gap-3 mt-1 text-[10px] text-muted-foreground px-1 items-center">
        <span className="flex items-center gap-1">
          <span className="inline-block w-4 h-2 bg-[#0062CC] rounded-sm" /> Treno
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-4 h-2 bg-[#A78BFA]/60 rounded-sm border border-[#7C3AED] border-dashed" />
          Vettura
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-4 h-2 bg-[#34D399]/60 rounded-sm border border-[#059669] border-dashed" />
          Refezione
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-4 h-2 bg-[#CBD5E1] rounded-sm border border-[#94A3B8] border-dashed" />
          S.COMP
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-1 h-3 bg-[#F59E0B] rounded-sm" /> CVp/CVa
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full bg-black" /> Acc. magg.
        </span>
        {onBlocksChange && (
          <span className="ml-auto italic text-primary">
            🖱 Trascina il treno per spostarlo (CVp/CVa lo seguono) • Trascina i bordi per ridimensionare • Snap 5 min
          </span>
        )}
      </div>
    </div>
  )
}
