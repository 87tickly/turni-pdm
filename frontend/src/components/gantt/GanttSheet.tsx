/**
 * GanttSheet — componente SVG monolitico per il Gantt giornata PdC v3.
 *
 * Falsa riga del foglio turno PDF Trenord, con interattivita' moderna:
 * hover tooltip, click -> drawer, right-click -> menu contestuale.
 *
 * Il layer "interactions" (drag, resize, cross-day DnD, action bar,
 * timeline click) e' OPT-IN: attivato solo se il consumer passa le
 * callback corrispondenti. Se nessuna callback e' fornita, il
 * comportamento e' identico alla versione precedente (sola resa).
 * Vedi `docs/HANDOFF-gantt-v3-interactions.md` per lo spec completo.
 */
import { useMemo, useRef } from "react"
import type {
  GanttSegment,
  GanttRow,
  GanttMetrics,
  GanttDayHead,
  GanttLabelsMode,
  GanttMinutesMode,
  GanttPalette,
  GanttInteractionCallbacks,
} from "./types"
import { GANTT_LAYOUT, GANTT_COLORS, timeToMin, minToTime } from "./tokens"
import {
  useGanttInteractions,
  ACTION_BAR_CONFIG,
} from "./interactions"


export interface GanttSheetProps extends GanttInteractionCallbacks {
  rows: GanttRow[]
  dayHead: GanttDayHead
  metrics: GanttMetrics
  range: [number, number]            // [hStart, hEnd] — supporta overnight (es. [18, 33])
  barHeight?: number                  // default 20
  labels?: GanttLabelsMode            // default "auto"
  minutes?: GanttMinutesMode          // default "hhmm"
  palette?: GanttPalette              // default "hybrid"
  grid30?: boolean                    // griglia ogni 30 min
  suspect?: boolean                   // highlight vetture sospette (default true)
  onSegmentClick?: (seg: GanttSegment, rowIdx: number) => void
  onSegmentContextMenu?: (
    seg: GanttSegment,
    rowIdx: number,
    ev: React.MouseEvent,
  ) => void

  // Layer interactions — opt-in, ereditati da GanttInteractionCallbacks:
  //   onSegmentDrag, onTimelineClick, onCrossDragStart, onCrossDrop,
  //   onCrossRemove, onAction
  ganttId?: string
  hideActionBar?: boolean
  snapMinutes?: number       // default 5
  dragThresholdPx?: number   // default 4
}


export function GanttSheet({
  rows,
  dayHead,
  metrics,
  range,
  barHeight = GANTT_LAYOUT.BAR_HEIGHT,
  labels = "auto",
  minutes = "hhmm",
  palette: _palette = "hybrid",
  grid30 = false,
  suspect: showSuspect = true,
  onSegmentClick,
  onSegmentContextMenu,
  // Interactions
  ganttId,
  hideActionBar = false,
  snapMinutes = 5,
  dragThresholdPx = 4,
  onSegmentDrag,
  onTimelineClick,
  onCrossDragStart,
  onCrossDrop,
  onCrossRemove,
  onAction,
}: GanttSheetProps) {
  const [hStart, hEnd] = range
  const totalH = hEnd - hStart
  const axisW = totalH * GANTT_LAYOUT.PX_PER_HOUR
  const totalW = GANTT_LAYOUT.COL_LEFT + axisW + GANTT_LAYOUT.COL_RIGHT
  const rowH =
    GANTT_LAYOUT.LABEL_BAND + barHeight + GANTT_LAYOUT.MINUTES_BAND + GANTT_LAYOUT.ROW_GAP
  const svgH = GANTT_LAYOUT.AXIS_Y + rowH * rows.length + 16

  const xFor = useMemo(
    () => (min: number) =>
      GANTT_LAYOUT.COL_LEFT + ((min - hStart * 60) / 60) * GANTT_LAYOUT.PX_PER_HOUR,
    [hStart],
  )

  // Refs per il hook
  const svgRef = useRef<SVGSVGElement | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)

  // Ore asse (numeri sopra)
  const hourTicks: number[] = []
  for (let h = hStart; h <= hEnd; h++) hourTicks.push(h)

  // Mezzore se grid30
  const halfTicks: number[] = grid30
    ? Array.from({ length: hEnd - hStart }, (_, i) => hStart + i)
    : []

  // ─── Interactions hook (opt-in, noop se nessuna callback) ───
  const interactionsEnabled =
    !!onSegmentDrag ||
    !!onTimelineClick ||
    !!onCrossDragStart ||
    !!onCrossDrop ||
    !!onCrossRemove ||
    (!!onAction && !hideActionBar)

  const ix = useGanttInteractions({
    svgRef,
    containerRef,
    rows,
    totalW,
    xFor,
    hStart,
    ganttId,
    hideActionBar,
    snapMinutes,
    dragThresholdPx,
    onSegmentDrag,
    onTimelineClick,
    onCrossDragStart,
    onCrossDrop,
    onCrossRemove,
    onAction,
  })

  const { dragState, actionBarState } = ix

  // Stato derivato: siamo in drag attivo?
  const isDragging = !!dragState?.active

  return (
    <div
      ref={containerRef}
      className="gantt-sheet-container"
      style={{ position: "relative", display: "inline-block", maxWidth: "100%" }}
    >
      <svg
        ref={svgRef}
        viewBox={`0 0 ${totalW} ${svgH}`}
        width={totalW}
        height={svgH}
        xmlns="http://www.w3.org/2000/svg"
        style={{ maxWidth: "100%", fontFamily: "var(--font-sans, Inter)" }}
      >
        {/* ═══ Asse + tick ═══ */}
        <g>
          {rows.map((_, i) => {
            const y =
              GANTT_LAYOUT.AXIS_Y + i * rowH + GANTT_LAYOUT.LABEL_BAND + barHeight / 2
            return (
              <line
                key={`axis-${i}`}
                x1={GANTT_LAYOUT.COL_LEFT}
                x2={GANTT_LAYOUT.COL_LEFT + axisW}
                y1={y}
                y2={y}
                stroke={GANTT_COLORS.INK}
                strokeWidth={1}
              />
            )
          })}
          {hourTicks.map((h) => {
            const x = xFor(h * 60)
            const hourLabel = String(((h % 24) + 24) % 24).padStart(2, "0")
            return (
              <g key={`hour-${h}`}>
                <text
                  x={x}
                  y={16}
                  textAnchor="middle"
                  fontSize={10.5}
                  fontWeight={700}
                  fill={GANTT_COLORS.INK_60}
                  style={{
                    fontFamily:
                      "var(--font-mono, 'JetBrains Mono', monospace)",
                  }}
                >
                  {hourLabel}
                </text>
                {rows.map((_, i) => {
                  const y0 =
                    GANTT_LAYOUT.AXIS_Y +
                    i * rowH +
                    GANTT_LAYOUT.LABEL_BAND +
                    barHeight / 2
                  return (
                    <line
                      key={`tick-${h}-${i}`}
                      x1={x}
                      x2={x}
                      y1={y0 - 5}
                      y2={y0 + 5}
                      stroke={GANTT_COLORS.INK}
                      strokeWidth={1}
                    />
                  )
                })}
              </g>
            )
          })}
          {halfTicks.map((h) => {
            const x = xFor(h * 60 + 30)
            return rows.map((_, i) => {
              const y0 =
                GANTT_LAYOUT.AXIS_Y +
                i * rowH +
                GANTT_LAYOUT.LABEL_BAND +
                barHeight / 2
              return (
                <line
                  key={`half-${h}-${i}`}
                  x1={x}
                  x2={x}
                  y1={y0 - 3}
                  y2={y0 + 3}
                  stroke={GANTT_COLORS.INK_40}
                  strokeWidth={0.6}
                />
              )
            })
          })}
        </g>

        {/* Timeline click zone (opt-in via onTimelineClick) */}
        {onTimelineClick && rows.map((_, i) => {
          const y =
            GANTT_LAYOUT.AXIS_Y + i * rowH + GANTT_LAYOUT.LABEL_BAND
          const bind = ix.bindTimeline()
          return (
            <rect
              key={`timeline-zone-${i}`}
              x={GANTT_LAYOUT.COL_LEFT}
              y={y - 10}
              width={axisW}
              height={barHeight + 20}
              fill="transparent"
              style={{ cursor: bind.cursor }}
              onClick={(ev) => bind.onClick(ev, i)}
              onDragOver={bind.onDragOver}
              onDrop={bind.onDrop ? (ev) => bind.onDrop?.(ev, i) : undefined}
            />
          )
        })}

        {/* Cross-day drop zone (senza onTimelineClick, ma con onCrossDrop) */}
        {!onTimelineClick && onCrossDrop && rows.map((_, i) => {
          const y =
            GANTT_LAYOUT.AXIS_Y + i * rowH + GANTT_LAYOUT.LABEL_BAND
          const bind = ix.bindTimeline()
          return (
            <rect
              key={`dropzone-${i}`}
              x={GANTT_LAYOUT.COL_LEFT}
              y={y - 10}
              width={axisW}
              height={barHeight + 20}
              fill="transparent"
              onDragOver={bind.onDragOver}
              onDrop={bind.onDrop ? (ev) => bind.onDrop?.(ev, i) : undefined}
            />
          )
        })}

        {/* ═══ Colonna sinistra (label variante + meta) ═══ */}
        {rows.map((row, i) => {
          const yBarMid =
            GANTT_LAYOUT.AXIS_Y +
            i * rowH +
            GANTT_LAYOUT.LABEL_BAND +
            barHeight / 2
          const varY = GANTT_LAYOUT.AXIS_Y + i * rowH + 18
          const metaText =
            row.meta ||
            (i === 0
              ? `${dayHead.num}  [${dayHead.pres}]  [${dayHead.end}]`
              : "")
          return (
            <g key={`left-${i}`}>
              <text
                x={14}
                y={varY}
                fontSize={13}
                fontWeight={700}
                fill={GANTT_COLORS.INK}
                style={{
                  fontFamily: "var(--font-display, 'Exo 2', Inter)",
                  letterSpacing: "-0.01em",
                }}
              >
                {row.label}
              </text>
              {metaText && (
                <text
                  x={14}
                  y={yBarMid + 4}
                  fontSize={10.5}
                  fill={GANTT_COLORS.INK_60}
                  style={{
                    fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                  }}
                >
                  {metaText}
                </text>
              )}
            </g>
          )
        })}

        {/* ═══ Colonna destra · metriche ═══ */}
        {(() => {
          const cols = ["Lav", "Cct", "Km", "Not", "Rip"]
          const mxStart = GANTT_LAYOUT.COL_LEFT + axisW + 14
          const colW = (GANTT_LAYOUT.COL_RIGHT - 14) / cols.length
          return (
            <g>
              {cols.map((m, ci) => (
                <text
                  key={`mh-${ci}`}
                  x={mxStart + ci * colW + colW / 2}
                  y={GANTT_LAYOUT.AXIS_Y - 12}
                  textAnchor="middle"
                  fontSize={9.5}
                  fontWeight={700}
                  fill={GANTT_COLORS.INK_60}
                  style={{ textTransform: "uppercase", letterSpacing: "0.08em" }}
                >
                  {m}
                </text>
              ))}
              {rows.map((row, i) => {
                const y =
                  GANTT_LAYOUT.AXIS_Y +
                  i * rowH +
                  GANTT_LAYOUT.LABEL_BAND +
                  barHeight / 2 +
                  4
                const o = row.metrics_override || {}
                const vals: (string | number)[] = [
                  o.lav ?? metrics.lav,
                  o.cct ?? metrics.cct,
                  o.km ?? metrics.km,
                  o.not ?? metrics.not,
                  o.rip ?? metrics.rip,
                ]
                return (
                  <g key={`mrow-${i}`}>
                    {vals.map((v, j) => (
                      <text
                        key={`mc-${i}-${j}`}
                        x={mxStart + j * colW + colW / 2}
                        y={y}
                        textAnchor="middle"
                        fontSize={11}
                        fontWeight={600}
                        fill={GANTT_COLORS.INK}
                        style={{
                          fontFamily:
                            "var(--font-mono, 'JetBrains Mono', monospace)",
                        }}
                      >
                        {v}
                      </text>
                    ))}
                    {row.warn && (
                      <circle
                        cx={mxStart + cols.length * colW + 4}
                        cy={y - 4}
                        r={3.5}
                        fill={GANTT_COLORS.SUSPECT}
                      />
                    )}
                  </g>
                )
              })}
            </g>
          )
        })()}

        {/* ═══ Segmenti ═══ */}
        {rows.map((row, i) => {
          const yBarTop =
            GANTT_LAYOUT.AXIS_Y + i * rowH + GANTT_LAYOUT.LABEL_BAND
          const yBarMid = yBarTop + barHeight / 2
          const yBarBot = yBarTop + barHeight
          return (
            <g key={`segs-${i}`}>
              {row.segments.map((seg, si) => {
                let depM = timeToMin(seg.dep_time)
                let arrM = timeToMin(seg.arr_time)
                if (arrM < depM) arrM += 1440
                if (depM < hStart * 60 - 60) depM += 1440
                if (arrM < hStart * 60) arrM += 1440

                // Ghost back-reference durante drag (rendering alla posizione
                // originale semi-trasparente)
                const isThisSegDragging =
                  isDragging &&
                  dragState?.rowIdx === i &&
                  dragState?.segIdx === si
                let x1 = xFor(depM)
                let x2 = xFor(arrM)
                // Se sto trascinando QUESTO segment, sposta visualmente
                // il rendering alla posizione corrente
                if (isThisSegDragging && dragState) {
                  x1 = xFor(dragState.currentDepMin)
                  x2 = xFor(dragState.currentArrMin)
                }
                const w = Math.max(x2 - x1, 2)
                const durMin = arrM - depM

                const isSelected =
                  actionBarState?.rowIdx === i &&
                  actionBarState?.segIdx === si

                // Binding da hook — eventi drag / click / keyboard
                const segBind = ix.bindSegment(i, si)

                // Click handler finale: se action bar disabilitata o non fornito
                // onAction, fallback su onSegmentClick storico
                const handleClick = (ev: React.MouseEvent) => {
                  if (!onAction || hideActionBar) {
                    // Legacy behaviour
                    ev.stopPropagation()
                    onSegmentClick?.(seg, i)
                    return
                  }
                  segBind.onClick(ev)
                }

                return (
                  <g key={`seg-${i}-${si}`}>
                    {/* Ghost back-reference: se QUESTO seg e' in drag, mostra
                        la sua posizione originale semi-trasparente */}
                    {isThisSegDragging && dragState && (
                      <rect
                        x={xFor(dragState.initialDepMin)}
                        y={yBarTop}
                        width={Math.max(
                          xFor(dragState.initialArrMin) -
                            xFor(dragState.initialDepMin),
                          2,
                        )}
                        height={barHeight}
                        fill="rgba(11,106,168,0.08)"
                        stroke={GANTT_COLORS.DRAG_GHOST_BORDER}
                        strokeWidth={1}
                        strokeDasharray="3 2"
                        opacity={0.5}
                        pointerEvents="none"
                      />
                    )}

                    <SegmentGroup
                      seg={seg}
                      x1={x1}
                      x2={x2}
                      w={w}
                      yBarTop={yBarTop}
                      yBarMid={yBarMid}
                      yBarBot={yBarBot}
                      barH={barHeight}
                      durMin={durMin}
                      labelsMode={labels}
                      minutesMode={minutes}
                      showSuspect={showSuspect}
                      isSelected={isSelected}
                      isDragging={isThisSegDragging}
                      onClick={handleClick}
                      onContextMenu={(ev) => {
                        ev.preventDefault()
                        onSegmentContextMenu?.(seg, i, ev)
                      }}
                      onMouseDown={interactionsEnabled ? segBind.onMouseDown : undefined}
                      onKeyDown={segBind.onKeyDown}
                      draggable={segBind.draggable}
                      onDragStart={segBind.onDragStart}
                      onDragEnd={segBind.onDragEnd}
                      tabIndex={segBind.tabIndex}
                    />

                    {/* Resize handles — solo se onSegmentDrag fornito e
                        segment e' di tipo cond/dh (ha range editabile) */}
                    {onSegmentDrag && (seg.kind === "cond" || seg.kind === "dh") && (
                      <>
                        <rect
                          x={x1}
                          y={yBarTop}
                          width={6}
                          height={barHeight}
                          fill="transparent"
                          style={{ cursor: "ew-resize" }}
                          onMouseDown={(ev) => {
                            ev.stopPropagation()
                            ix.startDrag(ev, i, si, "resize-start")
                          }}
                        />
                        <rect
                          x={x2 - 6}
                          y={yBarTop}
                          width={6}
                          height={barHeight}
                          fill="transparent"
                          style={{ cursor: "ew-resize" }}
                          onMouseDown={(ev) => {
                            ev.stopPropagation()
                            ix.startDrag(ev, i, si, "resize-end")
                          }}
                        />
                      </>
                    )}
                  </g>
                )
              })}
            </g>
          )
        })}

        {/* Drop slot indicator (cross-day target durante dragover) — se
            servisse, si posizionerebbe qui in SVG. Per ora lo slot e'
            HTML (vedi sotto overlay). */}
      </svg>

      {/* ═══ HTML overlays ═══ */}

      {/* Action bar (selected state) */}
      {actionBarState && !hideActionBar && (
        <ActionBarOverlay
          segRef={{
            rowIdx: actionBarState.rowIdx,
            segIdx: actionBarState.segIdx,
          }}
          seg={actionBarState.seg}
          totalW={totalW}
          rowH={rowH}
          xFor={xFor}
          onTrigger={ix.triggerAction}
        />
      )}

      {/* Sticky time tooltip durante drag */}
      {isDragging && dragState && (
        <StickyTimeTooltip
          depMin={dragState.currentDepMin}
          arrMin={dragState.currentArrMin}
          xFor={xFor}
          rowIdx={dragState.rowIdx}
          rowH={rowH}
        />
      )}
    </div>
  )
}


// ─────────────────────────────────────────────────────────────
// Action bar HTML overlay
// ─────────────────────────────────────────────────────────────

function ActionBarOverlay({
  segRef,
  seg,
  totalW,
  rowH,
  xFor,
  onTrigger,
}: {
  segRef: { rowIdx: number; segIdx: number }
  seg: GanttSegment
  totalW: number
  rowH: number
  xFor: (min: number) => number
  onTrigger: (action: import("./types").GanttAction) => void
}) {
  const depMin = timeToMin(seg.dep_time)
  let arrMin = timeToMin(seg.arr_time)
  if (arrMin < depMin) arrMin += 1440
  const x1 = xFor(depMin)
  const x2 = xFor(arrMin)
  const segCenterX = (x1 + x2) / 2

  // Posizione verticale: 42px sopra la barra del row
  // rowH = LABEL_BAND + barHeight + MINUTES_BAND + ROW_GAP
  // Bar inizia a AXIS_Y + row*rowH + LABEL_BAND
  const yBarTop =
    GANTT_LAYOUT.AXIS_Y + segRef.rowIdx * rowH + GANTT_LAYOUT.LABEL_BAND
  const yBarTopPct = yBarTop - 42 // 42px sopra

  // Clamp orizzontale: action bar larga ~350px, non deve uscire dal container
  const BAR_W_APPROX = 350
  const leftPx = Math.max(
    4,
    Math.min(totalW - BAR_W_APPROX - 4, segCenterX - BAR_W_APPROX / 2),
  )
  // Freccia posizionata sul centro del blocco (relativa all'origine bar)
  const arrowXPx = segCenterX - leftPx

  return (
    <div
      className="gantt-sheet-action-bar"
      style={
        {
          position: "absolute",
          left: `${(leftPx / totalW) * 100}%`,
          top: yBarTopPct,
          display: "flex",
          alignItems: "center",
          padding: "5px 4px",
          background: GANTT_COLORS.ACTION_BAR_BG,
          boxShadow:
            "0 8px 24px rgba(11, 13, 16, 0.16), 0 2px 4px rgba(11, 13, 16, 0.08)",
          zIndex: 20,
          transformOrigin: "bottom center",
          animation:
            "ganttActionBarIn 140ms cubic-bezier(0.18, 0.9, 0.32, 1.15)",
          ["--arrow-x" as string]: `${arrowXPx}px`,
        } as React.CSSProperties
      }
      onMouseDown={(ev) => ev.stopPropagation()}
    >
      {ACTION_BAR_CONFIG.map((btn, i) => {
        const color =
          btn.variant === "warn"
            ? "#B45309"
            : btn.variant === "danger"
            ? "#B91C1C"
            : "var(--color-on-surface-strong, #0A1322)"
        const hoverBg =
          btn.variant === "warn"
            ? "rgb(234 88 12 / 0.10)"
            : btn.variant === "danger"
            ? "rgb(220 38 38 / 0.10)"
            : "var(--color-surface-container, #E8ECF2)"
        return (
          <span key={btn.action} style={{ display: "inline-flex", alignItems: "center" }}>
            <button
              title={btn.title}
              onClick={(ev) => {
                ev.stopPropagation()
                onTrigger(btn.action)
              }}
              onMouseDown={(ev) => ev.stopPropagation()}
              onMouseEnter={(ev) =>
                ((ev.currentTarget as HTMLButtonElement).style.background = hoverBg)
              }
              onMouseLeave={(ev) =>
                ((ev.currentTarget as HTMLButtonElement).style.background = "transparent")
              }
              style={{
                width: 28,
                height: 28,
                display: "grid",
                placeItems: "center",
                background: "transparent",
                border: "none",
                cursor: "pointer",
                fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                fontSize: 13,
                fontWeight: 700,
                color,
                lineHeight: 1,
                transition: "background 0.12s, color 0.12s",
                padding: 0,
              }}
            >
              {btn.icon}
            </button>
            {btn.separatorAfter && i < ACTION_BAR_CONFIG.length - 1 && (
              <span
                style={{
                  width: 1,
                  height: 16,
                  background: "var(--color-ghost, #E1E5EC)",
                  margin: "0 3px",
                }}
              />
            )}
          </span>
        )
      })}
      {/* Freccia puntatore verso il blocco */}
      <span
        aria-hidden
        style={{
          position: "absolute",
          bottom: -5,
          left: `var(--arrow-x, 50%)`,
          transform: "translateX(-50%) rotate(45deg)",
          width: 8,
          height: 8,
          background: GANTT_COLORS.ACTION_BAR_BG,
          boxShadow: "2px 2px 4px rgba(11, 13, 16, 0.06)",
        }}
      />
    </div>
  )
}


// ─────────────────────────────────────────────────────────────
// Sticky time tooltip (mostrato durante drag)
// ─────────────────────────────────────────────────────────────

function StickyTimeTooltip({
  depMin,
  arrMin,
  xFor,
  rowIdx,
  rowH,
}: {
  depMin: number
  arrMin: number
  xFor: (min: number) => number
  rowIdx: number
  rowH: number
}) {
  const midMin = (depMin + arrMin) / 2
  const x = xFor(midMin)
  const yBarTop =
    GANTT_LAYOUT.AXIS_Y + rowIdx * rowH + GANTT_LAYOUT.LABEL_BAND
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: yBarTop - 28,
        padding: "4px 8px",
        background: GANTT_COLORS.STICKY_TIME_BG,
        color: "#fff",
        fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
        fontSize: 11,
        fontWeight: 700,
        pointerEvents: "none",
        zIndex: 30,
        boxShadow: "0 4px 12px rgba(0, 0, 0, 0.25)",
        whiteSpace: "nowrap",
        transform: "translateX(-50%)",
      }}
    >
      {minToTime(depMin)} → {minToTime(arrMin)}
    </div>
  )
}


// ─────────────────────────────────────────────────────────────
// SegmentGroup — render per kind (cond / dh / refez / scomp / sleep)
// ─────────────────────────────────────────────────────────────

interface SegProps {
  seg: GanttSegment
  x1: number
  x2: number
  w: number
  yBarTop: number
  yBarMid: number
  yBarBot: number
  barH: number
  durMin: number
  labelsMode: GanttLabelsMode
  minutesMode: GanttMinutesMode
  showSuspect: boolean
  isSelected?: boolean
  isDragging?: boolean
  onClick: (ev: React.MouseEvent) => void
  onContextMenu: (ev: React.MouseEvent) => void
  onMouseDown?: (ev: React.MouseEvent) => void
  onKeyDown?: (ev: React.KeyboardEvent) => void
  onDragStart?: (ev: React.DragEvent) => void
  onDragEnd?: (ev: React.DragEvent) => void
  draggable?: boolean
  tabIndex?: number
}

function SegmentGroup(props: SegProps) {
  const { seg } = props
  switch (seg.kind) {
    case "scomp":
      return <ScompBar {...props} />
    case "sleep":
      return <SleepBar {...props} />
    case "refez":
      return <RefezBar {...props} />
    case "cond":
    case "dh":
    default:
      return <TrainBar {...props} />
  }
}

function SegHit({
  x1,
  w,
  yBarTop,
  barH,
  tip,
  onClick,
  onContextMenu,
  onMouseDown,
  onKeyDown,
  onDragStart,
  onDragEnd,
  draggable,
  tabIndex,
}: {
  x1: number
  w: number
  yBarTop: number
  barH: number
  tip: string
  onClick: (ev: React.MouseEvent) => void
  onContextMenu: (ev: React.MouseEvent) => void
  onMouseDown?: (ev: React.MouseEvent) => void
  onKeyDown?: (ev: React.KeyboardEvent) => void
  onDragStart?: (ev: React.DragEvent) => void
  onDragEnd?: (ev: React.DragEvent) => void
  draggable?: boolean
  tabIndex?: number
}) {
  return (
    <rect
      x={x1}
      y={yBarTop - 16}
      width={w}
      height={barH + 32}
      fill="transparent"
      style={{ cursor: onMouseDown ? "grab" : "pointer" }}
      onClick={onClick}
      onContextMenu={onContextMenu}
      onMouseDown={onMouseDown}
      onKeyDown={onKeyDown}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      // @ts-expect-error draggable su SVG rect supportato dai browser moderni
      draggable={draggable}
      tabIndex={tabIndex}
    >
      <title>{tip}</title>
    </rect>
  )
}

function ScompBar(p: SegProps) {
  const { seg, x1, x2, w, yBarTop, yBarMid, barH, isSelected } = p
  return (
    <g>
      <rect
        x={x1}
        y={yBarTop - 2}
        width={w}
        height={barH + 4}
        fill={GANTT_COLORS.SCOMP}
        opacity={0.12}
      />
      <line
        x1={x1}
        x2={x1 + w}
        y1={yBarMid}
        y2={yBarMid}
        stroke={GANTT_COLORS.SCOMP}
        strokeWidth={1}
        strokeDasharray="2 3"
      />
      <text
        x={(x1 + x2) / 2}
        y={yBarMid + 4}
        textAnchor="middle"
        fontSize={11}
        fontWeight={700}
        fill={GANTT_COLORS.INK_60}
        style={{ textTransform: "uppercase", letterSpacing: "0.06em" }}
      >
        {seg.train_id}
      </text>
      {isSelected && (
        <rect
          x={x1 - 2}
          y={yBarTop - 4}
          width={w + 4}
          height={barH + 8}
          fill="none"
          stroke={GANTT_COLORS.SELECTED_RING}
          strokeWidth={2}
          rx={2}
          pointerEvents="none"
        />
      )}
      <SegHit
        x1={x1}
        w={w}
        yBarTop={yBarTop}
        barH={barH}
        tip={`S.COMP · ${seg.train_id} · ${seg.dep_time} → ${seg.arr_time}`}
        onClick={p.onClick}
        onContextMenu={p.onContextMenu}
        onMouseDown={p.onMouseDown}
        onKeyDown={p.onKeyDown}
        onDragStart={p.onDragStart}
        onDragEnd={p.onDragEnd}
        draggable={p.draggable}
        tabIndex={p.tabIndex}
      />
    </g>
  )
}

function SleepBar(p: SegProps) {
  const { seg, x1, x2, w, yBarTop, yBarMid, barH, isSelected } = p
  return (
    <g>
      <rect
        x={x1}
        y={yBarTop}
        width={w}
        height={barH}
        fill={GANTT_COLORS.SLEEP_BG}
        stroke={GANTT_COLORS.SLEEP}
        strokeWidth={1}
        rx={2}
      />
      <text
        x={(x1 + x2) / 2}
        y={yBarMid + 4}
        textAnchor="middle"
        fontSize={10.5}
        fontWeight={600}
        fill={GANTT_COLORS.SLEEP}
        style={{ fontFamily: "var(--font-sans, Inter)" }}
      >
        🌙 {seg.train_id}
      </text>
      {isSelected && (
        <rect
          x={x1 - 2}
          y={yBarTop - 2}
          width={w + 4}
          height={barH + 4}
          fill="none"
          stroke={GANTT_COLORS.SELECTED_RING}
          strokeWidth={2}
          rx={2}
          pointerEvents="none"
        />
      )}
      <SegHit
        x1={x1}
        w={w}
        yBarTop={yBarTop}
        barH={barH}
        tip={`🌙 Dormita · ${seg.train_id} · ${seg.dep_time} → ${seg.arr_time} (giorno dopo)`}
        onClick={p.onClick}
        onContextMenu={p.onContextMenu}
        onMouseDown={p.onMouseDown}
        onKeyDown={p.onKeyDown}
        onDragStart={p.onDragStart}
        onDragEnd={p.onDragEnd}
        draggable={p.draggable}
        tabIndex={p.tabIndex}
      />
    </g>
  )
}

function RefezBar(p: SegProps) {
  const { seg, x1, x2, w, yBarTop, barH, isSelected } = p
  const labelText = "REFEZ " + (seg.from_station || "")
  const short = w < 50
  return (
    <g>
      <rect
        x={x1}
        y={yBarTop + barH * 0.25}
        width={w}
        height={barH * 0.5}
        fill={GANTT_COLORS.REFEZ}
        rx={1}
      />
      {isSelected && (
        <rect
          x={x1 - 2}
          y={yBarTop - 2}
          width={w + 4}
          height={barH + 4}
          fill="none"
          stroke={GANTT_COLORS.SELECTED_RING}
          strokeWidth={2}
          rx={2}
          pointerEvents="none"
        />
      )}
      {short ? (
        <g transform={`translate(${(x1 + x2) / 2}, ${yBarTop - 6}) rotate(-90)`}>
          <text
            x={0}
            y={0}
            textAnchor="start"
            dominantBaseline="central"
            fontSize={9.5}
            fontWeight={700}
            fill={GANTT_COLORS.REFEZ_INK}
            style={{ textTransform: "uppercase", letterSpacing: "0.04em" }}
          >
            {labelText}
          </text>
        </g>
      ) : (
        <text
          x={(x1 + x2) / 2}
          y={yBarTop - 6}
          textAnchor="middle"
          fontSize={10}
          fontWeight={700}
          fill={GANTT_COLORS.REFEZ_INK}
          style={{ textTransform: "uppercase", letterSpacing: "0.04em" }}
        >
          {labelText}
        </text>
      )}
      <SegHit
        x1={x1}
        w={w}
        yBarTop={yBarTop}
        barH={barH}
        tip={`REFEZ · ${seg.from_station} · ${seg.dep_time} → ${seg.arr_time}`}
        onClick={p.onClick}
        onContextMenu={p.onContextMenu}
        onMouseDown={p.onMouseDown}
        onKeyDown={p.onKeyDown}
        onDragStart={p.onDragStart}
        onDragEnd={p.onDragEnd}
        draggable={p.draggable}
        tabIndex={p.tabIndex}
      />
    </g>
  )
}

function TrainBar(p: SegProps) {
  const {
    seg,
    x1,
    x2,
    w,
    yBarTop,
    yBarMid,
    yBarBot,
    barH,
    durMin,
    labelsMode,
    minutesMode,
    showSuspect,
    isSelected,
    isDragging,
  } = p
  const isDH = seg.kind === "dh"
  const isSuspect = !!seg.suspect_reason && showSuspect

  const fill = isSuspect
    ? "rgba(220, 38, 38, 0.06)"
    : isDH
    ? GANTT_COLORS.BAR_DH_BG
    : GANTT_COLORS.BAR_COND
  const strokeColor = isSuspect ? GANTT_COLORS.SUSPECT : GANTT_COLORS.BAR_DH_LINE

  const wantVertical =
    labelsMode === "vertical" || (labelsMode === "auto" && w < 60)
  const prefix = seg.cvp ? "CVp " : seg.cva ? "CVa " : ""
  const labelMain = prefix + seg.train_id
  const labelSub = seg.to_station || ""
  const accColor = seg.cvp
    ? GANTT_COLORS.CVP
    : seg.cva
    ? GANTT_COLORS.CVA
    : GANTT_COLORS.PREHEAT
  const accLabel = seg.cvp
    ? `CVp ${seg.dep_time}`
    : seg.cva
    ? `CVa ${seg.dep_time}`
    : seg.preheat
    ? `● Preriscaldo ${seg.dep_time}`
    : null

  const tipParts = [
    seg.preheat ? "● preriscaldo · " : "",
    isDH ? "[vettura] " : "",
    seg.train_id,
    ` · ${seg.from_station} ${seg.dep_time} → ${seg.to_station} ${seg.arr_time}`,
    isSuspect ? ` · ⚠ ${seg.suspect_reason}` : "",
  ]
  const tip = tipParts.join("")

  return (
    <g>
      {/* Selected ring */}
      {isSelected && (
        <rect
          x={x1 - 3}
          y={yBarTop - 3}
          width={w + 6}
          height={barH + 6}
          fill="none"
          stroke={GANTT_COLORS.SELECTED_RING}
          strokeWidth={2}
          rx={2}
          style={{ filter: `drop-shadow(${GANTT_COLORS.SELECTED_SHADOW})` }}
          pointerEvents="none"
        />
      )}

      {/* Barra base */}
      <rect
        x={x1}
        y={yBarTop}
        width={w}
        height={barH}
        fill={fill}
        opacity={isDragging ? 0.85 : 1}
      />

      {/* Drag ghost border (durante drag) */}
      {isDragging && (
        <rect
          x={x1 - 2}
          y={yBarTop - 2}
          width={w + 4}
          height={barH + 4}
          fill="none"
          stroke={GANTT_COLORS.DRAG_GHOST_BORDER}
          strokeWidth={1.2}
          strokeDasharray="4 3"
          pointerEvents="none"
        />
      )}

      {/* Contorno tratteggiato per vettura */}
      {isDH && (
        <rect
          x={x1 + 0.5}
          y={yBarTop + 0.5}
          width={w - 1}
          height={barH - 1}
          fill="none"
          stroke={strokeColor}
          strokeWidth={isSuspect ? 1.2 : 1}
          strokeDasharray="3 2.5"
        />
      )}
      {/* Preheat bullet */}
      {seg.preheat && (
        <circle cx={x1 + 5} cy={yBarMid} r={2.8} fill={GANTT_COLORS.INK} />
      )}
      {/* Striscia verticale accessorio */}
      {accLabel && (
        <g>
          <line
            x1={x1}
            x2={x1}
            y1={yBarTop - 5}
            y2={yBarBot + 5}
            stroke={accColor}
            strokeWidth={1.5}
          />
          <text
            x={x1 - 2}
            y={yBarTop - 26}
            textAnchor="end"
            fontSize={9}
            fontWeight={600}
            fill={accColor}
            style={{ fontFamily: "var(--font-mono, monospace)" }}
          >
            {accLabel}
          </text>
        </g>
      )}

      {/* Label treno */}
      {wantVertical ? (
        <g
          transform={`translate(${(x1 + x2) / 2}, ${yBarTop - 6}) rotate(-90)`}
        >
          <text
            x={0}
            y={-5}
            textAnchor="start"
            dominantBaseline="central"
            fontSize={10.5}
            fontWeight={700}
            fill={isDH ? GANTT_COLORS.INK : "#ffffff"}
            style={{
              fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
            }}
          >
            {labelMain}
          </text>
          {labelSub && (
            <text
              x={0}
              y={6}
              textAnchor="start"
              dominantBaseline="central"
              fontSize={9}
              fontWeight={500}
              fill={isDH ? GANTT_COLORS.INK_60 : "rgba(255,255,255,0.85)"}
              style={{
                fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
              }}
            >
              {labelSub}
            </text>
          )}
        </g>
      ) : (
        <text
          x={x1 + (seg.preheat ? 14 : 4)}
          y={yBarTop - 6}
          fontSize={10.5}
          fontWeight={700}
          fill={GANTT_COLORS.INK}
          style={{
            fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
          }}
        >
          {labelMain}
          {labelSub && (
            <tspan fontWeight={500} fill={GANTT_COLORS.INK_60}>
              {" "}
              · {labelSub}
            </tspan>
          )}
        </text>
      )}

      {/* Minuti sotto barra */}
      {minutesMode !== "off" && (
        <g>
          {minutesMode === "hhmm" ? (
            w > 40 ? (
              <>
                <text
                  x={x1}
                  y={yBarBot + 12}
                  textAnchor="start"
                  fontSize={9}
                  fill={GANTT_COLORS.INK_60}
                  style={{ fontFamily: "var(--font-mono, monospace)" }}
                >
                  {seg.dep_time}
                </text>
                <text
                  x={x2}
                  y={yBarBot + 12}
                  textAnchor="end"
                  fontSize={9}
                  fill={GANTT_COLORS.INK_60}
                  style={{ fontFamily: "var(--font-mono, monospace)" }}
                >
                  {seg.arr_time}
                </text>
              </>
            ) : (
              <text
                x={(x1 + x2) / 2}
                y={yBarBot + 12}
                textAnchor="middle"
                fontSize={9}
                fill={GANTT_COLORS.INK_60}
                style={{ fontFamily: "var(--font-mono, monospace)" }}
              >
                {seg.dep_time}
              </text>
            )
          ) : (
            <text
              x={(x1 + x2) / 2}
              y={yBarBot + 12}
              textAnchor="middle"
              fontSize={9}
              fontWeight={600}
              fill={GANTT_COLORS.INK_60}
              style={{ fontFamily: "var(--font-mono, monospace)" }}
            >
              {durMin}
            </text>
          )}
        </g>
      )}

      {/* ⚠ vettura sospetta */}
      {isSuspect && (
        <text
          x={x1 + w / 2}
          y={yBarTop - 46}
          textAnchor="middle"
          fontSize={14}
          fill={GANTT_COLORS.SUSPECT}
        >
          ⚠
        </text>
      )}

      <SegHit
        x1={x1}
        w={w}
        yBarTop={yBarTop}
        barH={barH}
        tip={tip}
        onClick={p.onClick}
        onContextMenu={p.onContextMenu}
        onMouseDown={p.onMouseDown}
        onKeyDown={p.onKeyDown}
        onDragStart={p.onDragStart}
        onDragEnd={p.onDragEnd}
        draggable={p.draggable}
        tabIndex={p.tabIndex}
      />
    </g>
  )
}
