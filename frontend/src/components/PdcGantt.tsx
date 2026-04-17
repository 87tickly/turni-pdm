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
 * Interazione (solo se `onBlockChange` è fornito):
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
   * Riceve l'indice del blocco e i nuovi orari (start_time / end_time).
   */
  onBlockChange?: (
    index: number,
    changes: { start_time?: string; end_time?: string }
  ) => void
  label?: string
  depot?: string
  height?: number
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
const BAR_H_TRAIN = 28
const BAR_H_COACH = 20
const BAR_H_MEAL = 20
const BAR_H_SCOMP = 16
const MARKER_H = 30

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
        dash: "4 3",
        opacity: 0.55,
      }
    case "meal":
      return {
        fill: "#34D399",
        stroke: "#059669",
        h: BAR_H_MEAL,
        dash: "4 3",
        opacity: 0.55,
      }
    case "scomp":
      return {
        fill: "#CBD5E1",
        stroke: "#94A3B8",
        h: BAR_H_SCOMP,
        dash: "4 3",
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
  index: number
  kind: "move" | "resize-start" | "resize-end"
  initialSm: number
  initialEm: number
  initialMouseX: number
}

export function PdcGantt({
  blocks: rawBlocks,
  startTime,
  endTime,
  onBlockClick,
  onTimelineClick,
  onBlockChange,
  label,
  depot,
  height = 220,
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
  const startDrag = (
    e: React.MouseEvent,
    index: number,
    kind: DragState["kind"]
  ) => {
    if (!onBlockChange) return
    e.stopPropagation()
    e.preventDefault()
    const b = blocks[index]
    const sm = hhmmToMinutesRel(b.start_time)
    const em = hhmmToMinutesRel(b.end_time)
    if (sm === null) return
    const emEff = em !== null && em > sm ? em : sm
    setDragState({
      index,
      kind,
      initialSm: sm,
      initialEm: emEff,
      initialMouseX: e.clientX,
    })
  }

  useEffect(() => {
    if (!dragState) return
    const handleMove = (e: MouseEvent) => {
      const dxSvg =
        clientXToSvgX(e.clientX) - clientXToSvgX(dragState.initialMouseX)
      const deltaMin = (dxSvg / plotW) * SPAN_HOURS * 60
      let newSm = dragState.initialSm
      let newEm = dragState.initialEm

      if (dragState.kind === "move") {
        newSm = Math.round(dragState.initialSm + deltaMin)
        newEm = Math.round(dragState.initialEm + deltaMin)
      } else if (dragState.kind === "resize-start") {
        newSm = Math.round(dragState.initialSm + deltaMin)
        if (newSm > dragState.initialEm - 5) newSm = dragState.initialEm - 5
      } else if (dragState.kind === "resize-end") {
        newEm = Math.round(dragState.initialEm + deltaMin)
        if (newEm < dragState.initialSm + 5) newEm = dragState.initialSm + 5
      }

      // Clamp
      const maxMin = SPAN_HOURS * 60
      newSm = Math.max(0, Math.min(newSm, maxMin))
      newEm = Math.max(0, Math.min(newEm, maxMin))

      setOverrides((prev) => ({
        ...prev,
        [dragState.index]: {
          start_time: minutesRelToHhmm(newSm),
          end_time: minutesRelToHhmm(newEm),
        },
      }))
    }
    const handleUp = () => {
      if (!onBlockChange || !dragState) return
      const ov = overrides[dragState.index]
      if (ov) {
        onBlockChange(dragState.index, ov)
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
  }, [dragState, overrides, plotW, clientXToSvgX, onBlockChange])

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

        {/* Blocchi */}
        {blocks.map((b, i) => {
          const bs = blockStyle(b.block_type)
          const sm = hhmmToMinutesRel(b.start_time)
          const em = hhmmToMinutesRel(b.end_time)
          const labelTxt = blockLabel(b)
          const isDragging = dragState?.index === i

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
                  cursor: onBlockChange
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
                  cursor: onBlockChange
                    ? isDragging
                      ? "grabbing"
                      : "grab"
                    : onBlockClick
                    ? "pointer"
                    : "default",
                }}
              />

              {/* Handle RESIZE-START (a sinistra) */}
              {onBlockChange && w > 14 && (
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
              {onBlockChange && w > 14 && (
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
        {onBlockChange && (
          <span className="ml-auto italic text-primary">
            🖱 Trascina il centro per spostare • Trascina i bordi per ridimensionare
          </span>
        )}
      </div>
    </div>
  )
}
