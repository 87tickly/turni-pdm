/**
 * GanttSheet — componente SVG monolitico per il Gantt giornata PdC v3.
 *
 * Falsa riga del foglio turno PDF Trenord, con interattivita' moderna:
 * hover tooltip, click -> drawer, right-click -> menu contestuale.
 *
 * L'handoff (docs/HANDOFF-gantt-v3.md) prevede 7 file separati; qui
 * scegliamo un'implementazione monolitica piu' pragmatica per React:
 * un singolo componente SVG con sub-render per kind di segmento.
 * La struttura interna mappa 1:1 alla JS del mockup (screen-gantt-v3.html).
 *
 * Da HANDOFF §1: le props sono pensate per essere consumate da
 * AutoBuilderGantt e PdcGanttV2 (uniformati in futuro). Per ora viene
 * usato dalla pagina preview (/gantt-preview).
 */
import { useMemo } from "react"
import type {
  GanttSegment,
  GanttRow,
  GanttMetrics,
  GanttDayHead,
  GanttLabelsMode,
  GanttMinutesMode,
  GanttPalette,
} from "./types"
import { GANTT_LAYOUT, GANTT_COLORS, timeToMin } from "./tokens"


export interface GanttSheetProps {
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

  // Ore asse (numeri sopra)
  const hourTicks: number[] = []
  for (let h = hStart; h <= hEnd; h++) hourTicks.push(h)

  // Mezzore se grid30
  const halfTicks: number[] = grid30
    ? Array.from({ length: hEnd - hStart }, (_, i) => hStart + i)
    : []

  return (
    <svg
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
              const x1 = xFor(depM)
              const x2 = xFor(arrM)
              const w = Math.max(x2 - x1, 2)
              const durMin = arrM - depM

              return (
                <SegmentGroup
                  key={`seg-${i}-${si}`}
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
                  onClick={(ev) => {
                    onSegmentClick?.(seg, i)
                    ev.stopPropagation()
                  }}
                  onContextMenu={(ev) => {
                    ev.preventDefault()
                    onSegmentContextMenu?.(seg, i, ev)
                  }}
                />
              )
            })}
          </g>
        )
      })}
    </svg>
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
  onClick: (ev: React.MouseEvent) => void
  onContextMenu: (ev: React.MouseEvent) => void
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

function SegHit({ x1, w, yBarTop, barH, tip, onClick, onContextMenu }: {
  x1: number; w: number; yBarTop: number; barH: number; tip: string;
  onClick: (ev: React.MouseEvent) => void
  onContextMenu: (ev: React.MouseEvent) => void
}) {
  return (
    <rect
      x={x1}
      y={yBarTop - 16}
      width={w}
      height={barH + 32}
      fill="transparent"
      style={{ cursor: "pointer" }}
      onClick={onClick}
      onContextMenu={onContextMenu}
    >
      <title>{tip}</title>
    </rect>
  )
}

function ScompBar(p: SegProps) {
  const { seg, x1, x2, w, yBarTop, yBarMid, barH, onClick, onContextMenu } = p
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
      {/* pattern fascia tratteggiata sottile */}
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
      <SegHit
        x1={x1} w={w} yBarTop={yBarTop} barH={barH}
        tip={`S.COMP · ${seg.train_id} · ${seg.dep_time} → ${seg.arr_time}`}
        onClick={onClick}
        onContextMenu={onContextMenu}
      />
    </g>
  )
}

function SleepBar(p: SegProps) {
  const { seg, x1, x2, w, yBarTop, yBarMid, barH, onClick, onContextMenu } = p
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
      <SegHit
        x1={x1} w={w} yBarTop={yBarTop} barH={barH}
        tip={`🌙 Dormita · ${seg.train_id} · ${seg.dep_time} → ${seg.arr_time} (giorno dopo)`}
        onClick={onClick}
        onContextMenu={onContextMenu}
      />
    </g>
  )
}

function RefezBar(p: SegProps) {
  const { seg, x1, x2, w, yBarTop, barH, onClick, onContextMenu } = p
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
        x1={x1} w={w} yBarTop={yBarTop} barH={barH}
        tip={`REFEZ · ${seg.from_station} · ${seg.dep_time} → ${seg.arr_time}`}
        onClick={onClick}
        onContextMenu={onContextMenu}
      />
    </g>
  )
}

function TrainBar(p: SegProps) {
  const {
    seg, x1, x2, w, yBarTop, yBarMid, yBarBot, barH,
    durMin, labelsMode, minutesMode, showSuspect,
    onClick, onContextMenu,
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
      {/* Barra base */}
      <rect x={x1} y={yBarTop} width={w} height={barH} fill={fill} />
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
        <circle
          cx={x1 + 5}
          cy={yBarMid}
          r={2.8}
          fill={GANTT_COLORS.INK}
        />
      )}
      {/* Striscia verticale accessorio (CVp/CVa/Preheat) */}
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
              {" "}· {labelSub}
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
                  style={{
                    fontFamily: "var(--font-mono, monospace)",
                  }}
                >
                  {seg.dep_time}
                </text>
                <text
                  x={x2}
                  y={yBarBot + 12}
                  textAnchor="end"
                  fontSize={9}
                  fill={GANTT_COLORS.INK_60}
                  style={{
                    fontFamily: "var(--font-mono, monospace)",
                  }}
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
        x1={x1} w={w} yBarTop={yBarTop} barH={barH}
        tip={tip}
        onClick={onClick}
        onContextMenu={onContextMenu}
      />
    </g>
  )
}
