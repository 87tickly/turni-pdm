/**
 * PdcGanttV2 — Gantt PdC riprogettato (stile mockup gantt-ideal-v5).
 *
 * Differenze dal PdcGantt v1:
 *  - Chip-card blu indigo per i treni (numero + destinazione dentro)
 *  - Blocchi secondari (vettura/refez/CVp/CVa) con label orizzontali
 *    su 3 livelli Y (stagger) collegate da "zampe" tratteggiate
 *  - Stazioni capolinea orizzontali ai bordi del cluster
 *  - Asse 3→24→1→2→3 a 52 px/h per piu' respiro
 *  - Hover → tooltip dettagli; click → selected + action bar sopra
 *  - API esterna compatibile col vecchio PdcGantt (drop-in)
 *
 * Interazioni in questa versione:
 *  - hover su blocco → tooltip informativo
 *  - click su blocco → onBlockClick + evidenziazione selected
 *  - click su timeline vuota → onTimelineClick (per aggiungere)
 *
 * Drag&resize (onBlocksChange) NON implementati in questa prima versione.
 * Se il parent passa onBlocksChange, viene ignorato — tornera' nella
 * prossima iterazione (Fase 3 step 2).
 */

import { useMemo, useRef, useState, useCallback } from "react"
import type { PdcBlock } from "@/lib/api"

// ============================================================
// Props
// ============================================================
interface PdcGanttV2Props {
  blocks: PdcBlock[]
  startTime?: string
  endTime?: string
  onBlockClick?: (block: PdcBlock, index: number) => void
  onTimelineClick?: (hour: number, minute: number) => void
  /** Ignorato in v2 (drag non ancora supportato) */
  onBlocksChange?: (
    changes: Record<number, { start_time?: string; end_time?: string }>
  ) => void
  label?: string
  depot?: string
  /** Altezza totale area Gantt (default 200) */
  height?: number
  /** Mostra bordi tratteggiati sulle stazioni mancanti (debug) */
  debug?: boolean
}

// ============================================================
// Scala temporale — identica al vecchio Gantt
// ============================================================
const ORIGIN_HOUR = 3
const SPAN_HOURS = 24
const PX_PER_HOUR = 52
const ORIGIN_X = 30
const AXIS_WIDTH = SPAN_HOURS * PX_PER_HOUR
const TOTAL_WIDTH = ORIGIN_X + AXIS_WIDTH + ORIGIN_X

// Y layout (fissato, allineato al mockup v5)
const AXIS_Y = 130
const BLOCK_Y = 95
const BLOCK_H = 22
const CHIP_Y_A = 78 // piu' vicino al blocco
const CHIP_Y_B = 54 // medio
const CHIP_Y_C = 30 // alto
const MINUTES_MAIN_Y = 160
// MINUTES_AUX_Y riservato per la riga "minuti accessori" (riga ausiliaria
// del PDF: 5/27/10 ecc.). Verra' popolata quando il parser v2 esporra'
// il campo minuti_accessori nel PdcBlock.

function hhmmToMinutesRel(hhmm: string): number | null {
  if (!hhmm || !/^\d{1,2}:\d{2}$/.test(hhmm)) return null
  const [h, m] = hhmm.split(":").map(Number)
  let hourAdj = h
  if (h < ORIGIN_HOUR) hourAdj = h + 24
  return (hourAdj - ORIGIN_HOUR) * 60 + m
}

function minToX(minRel: number): number {
  return ORIGIN_X + (minRel / 60) * PX_PER_HOUR
}

function xToMin(x: number): number {
  return ((x - ORIGIN_X) / PX_PER_HOUR) * 60
}

function xToHourMinute(x: number): { hour: number; minute: number } {
  const m = xToMin(x)
  const abs = (ORIGIN_HOUR * 60 + Math.max(0, Math.min(m, SPAN_HOURS * 60))) % (24 * 60)
  const hour = Math.floor(abs / 60)
  const minute = Math.round(abs % 60)
  return { hour, minute }
}

// Estrai "solo minuto" (MM) da una stringa HH:MM, "" se invalida
function minuteOnly(hhmm: string): string {
  if (!hhmm || !/^\d{1,2}:\d{2}$/.test(hhmm)) return ""
  return hhmm.slice(-2)
}

// ============================================================
// Render helpers
// ============================================================
const TICK_HOURS = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 1, 2, 3]
const MAJOR_TICKS = new Set([3, 12, 24])

// Stagger Y automatico per chip-label: se il chip occupa la stessa fascia X di un precedente, sale di livello
function computeChipYs(
  blocks: PdcBlock[],
  approxLabelWidth: number = 60,
): number[] {
  // Ritorna array di Y paralleli ai blocchi (solo per quelli con chip-label)
  const ys: number[] = []
  const usedRanges: { y: number; x0: number; x1: number }[] = []
  const levels = [CHIP_Y_A, CHIP_Y_B, CHIP_Y_C]

  for (let i = 0; i < blocks.length; i++) {
    const b = blocks[i]
    const m = hhmmToMinutesRel(b.start_time || "")
    if (m === null || b.block_type === "train") {
      ys.push(CHIP_Y_A) // treni non usano chip-label (testo dentro)
      continue
    }
    const cx = minToX(m)
    const x0 = cx - approxLabelWidth / 2
    const x1 = cx + approxLabelWidth / 2

    let assignedY = -1
    for (const y of levels) {
      const collide = usedRanges.some(
        (r) => r.y === y && !(x1 < r.x0 || x0 > r.x1),
      )
      if (!collide) {
        assignedY = y
        break
      }
    }
    if (assignedY === -1) assignedY = CHIP_Y_C // tutti presi, usa il più alto
    usedRanges.push({ y: assignedY, x0, x1 })
    ys.push(assignedY)
  }
  return ys
}

// ============================================================
// Tooltip (HTML overlay)
// ============================================================
interface TooltipData {
  x: number
  y: number
  block: PdcBlock
}

function formatBlockLabel(b: PdcBlock): string {
  switch (b.block_type) {
    case "train":
      return `Treno ${b.train_id}`
    case "coach_transfer":
      return `Vettura ${b.vettura_id || b.train_id}`
    case "cv_partenza":
      return `CVp ${b.train_id}`
    case "cv_arrivo":
      return `CVa ${b.train_id}`
    case "meal":
      return `Refezione`
    case "scomp":
      return `S.COMP`
    case "available":
      return "Disponibile"
    default:
      return b.block_type
  }
}

function Tooltip({ data }: { data: TooltipData | null }) {
  if (!data) return null
  const { x, y, block } = data
  const rows: [string, string][] = [
    ["Orario", `${block.start_time || "—"} → ${block.end_time || "—"}`],
  ]
  if (block.from_station || block.to_station) {
    rows.push(["Tratta", `${block.from_station || "—"} → ${block.to_station || "—"}`])
  }
  if (block.accessori_maggiorati) {
    rows.push(["Accessori", "maggiorati (preriscaldo)"])
  }
  return (
    <div
      className="pointer-events-none absolute z-50 rounded-lg bg-slate-900 px-3 py-2 text-xs text-white shadow-xl"
      style={{ left: x + 14, top: y - 48, minWidth: 200 }}
    >
      <div className="mb-1 font-mono text-sm font-bold text-blue-300">
        {formatBlockLabel(block)}
      </div>
      {rows.map(([k, v]) => (
        <div key={k} className="grid grid-cols-[60px_1fr] gap-1.5 py-0.5">
          <span className="font-mono text-[10px] uppercase tracking-wider text-white/50">
            {k}
          </span>
          <span className="font-mono font-semibold tabular-nums">{v}</span>
        </div>
      ))}
    </div>
  )
}

// ============================================================
// Componente principale
// ============================================================
export function PdcGanttV2({
  blocks,
  onBlockClick,
  onTimelineClick,
  height = 200,
  debug = false,
}: PdcGanttV2Props) {
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null)
  const [tooltip, setTooltip] = useState<TooltipData | null>(null)
  const wrapperRef = useRef<HTMLDivElement>(null)

  // Nessun blocco → stato "disponibile"
  const isAvailable = blocks.length === 0 ||
    (blocks.length === 1 && blocks[0].block_type === "available")

  // Chip Y computed
  const chipYs = useMemo(() => computeChipYs(blocks), [blocks])

  // Capolinea di giornata (prima from_station e ultima to_station che trovo)
  const leftStation = useMemo(() => {
    for (const b of blocks) {
      if (b.from_station) return b.from_station
    }
    return ""
  }, [blocks])
  const rightStation = useMemo(() => {
    for (let i = blocks.length - 1; i >= 0; i--) {
      if (blocks[i].to_station) return blocks[i].to_station
    }
    return leftStation
  }, [blocks, leftStation])

  const handleTimelineBgClick = useCallback(
    (e: React.MouseEvent<SVGElement>) => {
      if (!onTimelineClick) return
      const svg = (e.currentTarget as SVGSVGElement).closest("svg")
      if (!svg) return
      const rect = svg.getBoundingClientRect()
      // Coordinate interne al viewBox (proporzionali)
      const xInside = ((e.clientX - rect.left) / rect.width) * TOTAL_WIDTH
      const { hour, minute } = xToHourMinute(xInside)
      onTimelineClick(hour, minute)
    },
    [onTimelineClick],
  )

  const handleBlockEnter = useCallback(
    (e: React.MouseEvent, block: PdcBlock) => {
      if (!wrapperRef.current) return
      const rect = wrapperRef.current.getBoundingClientRect()
      setTooltip({
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
        block,
      })
    },
    [],
  )
  const handleBlockMove = useCallback((e: React.MouseEvent) => {
    if (!wrapperRef.current) return
    const rect = wrapperRef.current.getBoundingClientRect()
    setTooltip((prev) =>
      prev ? { ...prev, x: e.clientX - rect.left, y: e.clientY - rect.top } : null,
    )
  }, [])
  const handleBlockLeave = useCallback(() => setTooltip(null), [])

  const handleBlockClick = useCallback(
    (e: React.MouseEvent, block: PdcBlock, idx: number) => {
      e.stopPropagation()
      setSelectedIdx(idx)
      if (onBlockClick) onBlockClick(block, idx)
    },
    [onBlockClick],
  )

  if (isAvailable) {
    return (
      <div
        className="flex items-center justify-center rounded-md border border-dashed border-slate-300 bg-slate-50 text-sm font-medium text-slate-500"
        style={{ minHeight: 72 }}
      >
        Disponibile · riposo a casa
      </div>
    )
  }

  return (
    <div ref={wrapperRef} className="relative" style={{ minHeight: height }}>
      <svg
        viewBox={`0 0 ${TOTAL_WIDTH} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        className="block w-full select-none"
        style={{ overflow: "visible" }}
      >
        <defs>
          <linearGradient id="pdcGanttV2-trainGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2563eb" />
            <stop offset="100%" stopColor="#1e3a8a" />
          </linearGradient>
        </defs>

        {/* Background timeline clickable per onTimelineClick */}
        {onTimelineClick && (
          <rect
            x={ORIGIN_X}
            y={0}
            width={AXIS_WIDTH}
            height={height}
            fill="transparent"
            style={{ cursor: "crosshair" }}
            onClick={handleTimelineBgClick}
          />
        )}

        {/* Fascia notte 24→03 */}
        <rect
          x={ORIGIN_X + 21 * PX_PER_HOUR}
          y={AXIS_Y - 10}
          width={3 * PX_PER_HOUR}
          height={20}
          fill="#0b0d10"
          fillOpacity={0.03}
          pointerEvents="none"
        />

        {/* Asse */}
        <line
          x1={ORIGIN_X}
          y1={AXIS_Y}
          x2={ORIGIN_X + AXIS_WIDTH}
          y2={AXIS_Y}
          stroke="#cdd1d7"
          strokeWidth={1.2}
          pointerEvents="none"
        />

        {/* Tick + label ore */}
        {TICK_HOURS.map((h, i) => {
          const x = ORIGIN_X + i * PX_PER_HOUR
          const isMajor = MAJOR_TICKS.has(h) && (i === 0 || i === TICK_HOURS.length - 1 || h === 12 || h === 24)
          const tickH = isMajor ? 10 : 6
          return (
            <g key={i} pointerEvents="none">
              <line
                x1={x}
                y1={AXIS_Y - tickH / 2}
                x2={x}
                y2={AXIS_Y + tickH / 2}
                stroke={isMajor ? "#353a42" : "#a1a6ae"}
                strokeWidth={isMajor ? 1.2 : 1}
              />
              <text
                x={x}
                y={AXIS_Y + 18}
                textAnchor="middle"
                fontFamily="ui-monospace, Menlo, monospace"
                fontSize={10}
                fontWeight={isMajor ? 700 : 500}
                fill={isMajor ? "#353a42" : "#6b7280"}
              >
                {h}
              </text>
            </g>
          )
        })}

        {/* Stazione capolinea sinistra */}
        {leftStation && (
          <text
            x={minToX(Math.min(...blocks.map((b) => hhmmToMinutesRel(b.start_time || "") ?? Infinity).filter(Number.isFinite))) - 10}
            y={BLOCK_Y + 16}
            textAnchor="end"
            fontSize={11}
            fontWeight={700}
            fill="#353a42"
            letterSpacing="0.04em"
            pointerEvents="none"
          >
            {leftStation}
          </text>
        )}

        {/* Stazione capolinea destra */}
        {rightStation && (
          <text
            x={minToX(Math.max(...blocks.map((b) => hhmmToMinutesRel(b.end_time || b.start_time || "") ?? 0))) + 10}
            y={BLOCK_Y + 16}
            textAnchor="start"
            fontSize={11}
            fontWeight={700}
            fill="#353a42"
            letterSpacing="0.04em"
            pointerEvents="none"
          >
            {rightStation}
          </text>
        )}

        {/* Blocchi */}
        {blocks.map((b, idx) => {
          const startMin = hhmmToMinutesRel(b.start_time || "")
          if (startMin === null) return null
          const endMin = hhmmToMinutesRel(b.end_time || b.start_time || "") ?? startMin
          const x = minToX(startMin)
          const x2 = minToX(endMin)
          const w = Math.max(2, x2 - x)
          const isSel = selectedIdx === idx
          const chipY = chipYs[idx]

          // Evento comuni
          const eventHandlers = {
            onMouseEnter: (e: React.MouseEvent) => handleBlockEnter(e, b),
            onMouseMove: handleBlockMove,
            onMouseLeave: handleBlockLeave,
            onClick: (e: React.MouseEvent) => handleBlockClick(e, b, idx),
            style: { cursor: "pointer" as const },
          }

          if (b.block_type === "train") {
            const showDest = w >= 85 && b.to_station
            return (
              <g key={idx}>
                {/* chip-card treno */}
                <rect
                  x={x}
                  y={BLOCK_Y}
                  width={w}
                  height={BLOCK_H}
                  rx={3}
                  fill="url(#pdcGanttV2-trainGradient)"
                  stroke={isSel ? "#60a5fa" : "rgba(147,197,253,0.25)"}
                  strokeWidth={isSel ? 2 : 0.5}
                  filter={isSel
                    ? "drop-shadow(0 3px 8px rgba(30,64,175,0.5))"
                    : "drop-shadow(0 1px 2px rgba(30,64,175,0.2))"}
                  {...eventHandlers}
                />
                {/* highlight superiore */}
                <rect
                  x={x}
                  y={BLOCK_Y}
                  width={w}
                  height={BLOCK_H / 2}
                  rx={3}
                  fill="#ffffff"
                  fillOpacity={0.08}
                  pointerEvents="none"
                />
                {/* numero treno */}
                <text
                  x={showDest ? x + 6 : x + w / 2}
                  y={BLOCK_Y + 14}
                  textAnchor={showDest ? "start" : "middle"}
                  fontFamily="ui-monospace, Menlo, monospace"
                  fontSize={w < 40 ? 9 : 10.5}
                  fontWeight={700}
                  fill="#ffffff"
                  pointerEvents="none"
                >
                  {b.train_id}
                </text>
                {/* destinazione se c'è spazio */}
                {showDest && (
                  <text
                    x={x + w - 6}
                    y={BLOCK_Y + 14}
                    textAnchor="end"
                    fontFamily="system-ui, sans-serif"
                    fontSize={8.5}
                    fontWeight={500}
                    fill="rgba(255,255,255,0.7)"
                    pointerEvents="none"
                  >
                    → {b.to_station}
                  </text>
                )}
                {/* pallino accessori maggiorati */}
                {b.accessori_maggiorati ? (
                  <circle cx={x - 5} cy={BLOCK_Y + BLOCK_H / 2} r={3.5} fill="#b91c1c" pointerEvents="none" />
                ) : null}
                {/* minuti sotto */}
                <text className="minute-main" x={x} y={MINUTES_MAIN_Y}
                      textAnchor="middle" fontFamily="ui-monospace, Menlo, monospace"
                      fontSize={9.5} fontWeight={700} fill="#0b0d10" pointerEvents="none">
                  {minuteOnly(b.start_time)}
                </text>
                {b.end_time && (
                  <text x={x2} y={MINUTES_MAIN_Y}
                        textAnchor="middle" fontFamily="ui-monospace, Menlo, monospace"
                        fontSize={9.5} fontWeight={700} fill="#0b0d10" pointerEvents="none">
                    {minuteOnly(b.end_time)}
                  </text>
                )}
              </g>
            )
          }

          if (b.block_type === "coach_transfer") {
            return (
              <g key={idx}>
                <rect x={x} y={BLOCK_Y + 6} width={w} height={BLOCK_H - 12}
                      fill="#6b7280" fillOpacity={0.08} rx={2} pointerEvents="none" />
                <rect x={x} y={BLOCK_Y + 6} width={w} height={BLOCK_H - 12}
                      fill="none" stroke={isSel ? "#60a5fa" : "#6b7280"}
                      strokeWidth={isSel ? 1.8 : 1.2} strokeDasharray="3 2" rx={2}
                      {...eventHandlers} />
                {/* stem */}
                <line x1={x + w / 2} y1={chipY + 4} x2={x + w / 2} y2={BLOCK_Y + 5}
                      stroke="#6b7280" strokeWidth={0.8} strokeDasharray="1 1.5" pointerEvents="none" />
                {/* label */}
                <text x={x + w / 2} y={chipY} textAnchor="middle"
                      fontFamily="ui-monospace, Menlo, monospace" fontSize={9.5}
                      fontWeight={500} fontStyle="italic" fill="#6b7280" pointerEvents="none">
                  ({b.vettura_id || b.train_id}
                  {b.to_station && (
                    <tspan fill="#6b7280" fillOpacity={0.7} fontSize={8.5} fontWeight={400} dx="3">
                      {b.to_station}
                    </tspan>
                  )}
                </text>
                {/* minuti */}
                <text x={x} y={MINUTES_MAIN_Y} textAnchor="middle"
                      fontFamily="ui-monospace, Menlo, monospace" fontSize={9.5}
                      fontWeight={700} fill="#0b0d10" pointerEvents="none">
                  {minuteOnly(b.start_time)}
                </text>
                {b.end_time && (
                  <text x={x2} y={MINUTES_MAIN_Y} textAnchor="middle"
                        fontFamily="ui-monospace, Menlo, monospace" fontSize={9.5}
                        fontWeight={700} fill="#0b0d10" pointerEvents="none">
                    {minuteOnly(b.end_time)}
                  </text>
                )}
              </g>
            )
          }

          if (b.block_type === "meal") {
            return (
              <g key={idx}>
                <rect x={x} y={BLOCK_Y + 6} width={w} height={BLOCK_H - 12}
                      fill="#fef3c7" stroke={isSel ? "#60a5fa" : "#b45309"}
                      strokeWidth={isSel ? 1.8 : 1.2} rx={2} {...eventHandlers} />
                <line x1={x + w / 2} y1={chipY + 4} x2={x + w / 2} y2={BLOCK_Y + 5}
                      stroke="#b45309" strokeWidth={0.8} strokeDasharray="1 1.5" pointerEvents="none" />
                <text x={x + w / 2} y={chipY} textAnchor="middle"
                      fontFamily="ui-monospace, Menlo, monospace" fontSize={9.5}
                      fontWeight={700} fill="#b45309" pointerEvents="none">
                  REFEZ
                  {b.from_station && (
                    <tspan fill="#b45309" fillOpacity={0.7} fontSize={8.5} fontWeight={400} dx="3">
                      {b.from_station}
                    </tspan>
                  )}
                </text>
                <text x={x} y={MINUTES_MAIN_Y} textAnchor="middle"
                      fontFamily="ui-monospace, Menlo, monospace" fontSize={9.5}
                      fontWeight={700} fill="#0b0d10" pointerEvents="none">
                  {minuteOnly(b.start_time)}
                </text>
                {b.end_time && (
                  <text x={x2} y={MINUTES_MAIN_Y} textAnchor="middle"
                        fontFamily="ui-monospace, Menlo, monospace" fontSize={9.5}
                        fontWeight={700} fill="#0b0d10" pointerEvents="none">
                    {minuteOnly(b.end_time)}
                  </text>
                )}
              </g>
            )
          }

          if (b.block_type === "cv_partenza" || b.block_type === "cv_arrivo") {
            const isPartenza = b.block_type === "cv_partenza"
            const label = isPartenza ? "CVp" : "CVa"
            return (
              <g key={idx}>
                <rect x={x - 1.5} y={BLOCK_Y - 2} width={3} height={BLOCK_H + 4}
                      fill="#6d28d9" rx={1} {...eventHandlers}
                      stroke={isSel ? "#60a5fa" : "none"} strokeWidth={isSel ? 1.5 : 0} />
                <line x1={x} y1={chipY + 4} x2={x} y2={BLOCK_Y - 2}
                      stroke="#6d28d9" strokeWidth={0.8} strokeDasharray="1 1.5" pointerEvents="none" />
                <text x={x} y={chipY} textAnchor="middle"
                      fontFamily="ui-monospace, Menlo, monospace" fontSize={9.5}
                      fontWeight={700} fill="#6d28d9" pointerEvents="none">
                  {label} {b.train_id}
                  {b.from_station && (
                    <tspan fill="#6d28d9" fillOpacity={0.7} fontSize={8.5} fontWeight={400} dx="3">
                      {b.from_station}
                    </tspan>
                  )}
                </text>
                <text x={x} y={MINUTES_MAIN_Y} textAnchor="middle"
                      fontFamily="ui-monospace, Menlo, monospace" fontSize={9.5}
                      fontWeight={700} fill="#0b0d10" pointerEvents="none">
                  {minuteOnly(b.start_time)}
                </text>
              </g>
            )
          }

          if (b.block_type === "scomp") {
            return (
              <g key={idx}>
                <rect x={x} y={BLOCK_Y + 4} width={w} height={BLOCK_H - 8}
                      fill="#cffafe" fillOpacity={0.6}
                      stroke={isSel ? "#60a5fa" : "#0e7490"}
                      strokeWidth={isSel ? 1.6 : 1} strokeDasharray="3 2" rx={3}
                      {...eventHandlers} />
                <text x={x + w / 2} y={BLOCK_Y + BLOCK_H / 2 + 4} textAnchor="middle"
                      fontFamily="ui-monospace, Menlo, monospace" fontSize={10}
                      fontWeight={700} fill="#0e7490" letterSpacing="0.06em" pointerEvents="none">
                  S.COMP {b.from_station || ""}
                </text>
                <text x={x} y={MINUTES_MAIN_Y} textAnchor="middle"
                      fontFamily="ui-monospace, Menlo, monospace" fontSize={9.5}
                      fontWeight={700} fill="#0b0d10" pointerEvents="none">
                  {minuteOnly(b.start_time)}
                </text>
                {b.end_time && (
                  <text x={x2} y={MINUTES_MAIN_Y} textAnchor="middle"
                        fontFamily="ui-monospace, Menlo, monospace" fontSize={9.5}
                        fontWeight={700} fill="#0b0d10" pointerEvents="none">
                    {minuteOnly(b.end_time)}
                  </text>
                )}
              </g>
            )
          }

          // fallback: rect grigio debug
          if (debug) {
            return (
              <rect key={idx} x={x} y={BLOCK_Y} width={w} height={BLOCK_H}
                    fill="#e4e6ea" stroke="#a1a6ae" strokeWidth={1} rx={3}
                    {...eventHandlers} />
            )
          }
          return null
        })}
      </svg>

      <Tooltip data={tooltip} />
    </div>
  )
}
