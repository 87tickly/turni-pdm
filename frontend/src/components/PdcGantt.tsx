/**
 * PdcGantt — Timeline Gantt visuale fedele al PDF Trenord.
 *
 * Layout stile PDF ufficiale Trenord (Modello M704):
 *  - Asse 3→24→1→2→3 orizzontale
 *  - Stazioni ai bordi delle barre (orizzontali, es. ARON, DOMO)
 *  - Numero treno + stazione destinazione scritti VERTICALMENTE sopra la barra
 *  - Linea continua nera per treni, tratteggiata per vetture/refezione
 *  - Marker "CVp"/"CVa" verticali a lato del blocco treno adiacente
 *  - Orari al minuto in piccolo sotto l'asse
 *  - Zona prestazione evidenziata con fascia azzurra
 *  - Pallino nero ● per accessori maggiorati (preriscaldo invernale)
 *
 * Modalità:
 *  - readonly (default): sola visualizzazione
 *  - onBlockClick: click su blocco (builder)
 *  - onTimelineClick: click su area vuota (builder: crea blocco)
 */

import type { PdcBlock } from "@/lib/api"

interface PdcGanttProps {
  blocks: PdcBlock[]
  startTime?: string          // orario inizio prestazione [HH:MM]
  endTime?: string            // orario fine prestazione [HH:MM]
  onBlockClick?: (block: PdcBlock, index: number) => void
  onTimelineClick?: (hour: number, minute: number) => void
  label?: string              // es. "g1 LMXGVSD"
  depot?: string              // label stazione base ai bordi (es. ARON)
  height?: number             // altezza personalizzata in px (default 180)
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
  const abs = (ORIGIN_HOUR * 60 + minRel) % (24 * 60)
  const h = Math.floor(abs / 60)
  const m = abs % 60
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}`
}

// Fill orari mancanti (stesso algoritmo della versione precedente)
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

// ── Stili grafici per tipo blocco ──────────────────────────────
const BAR_H_TRAIN = 3        // linea spessa per treno (style PDF: linea nera)
const BAR_H_VETTURA = 2      // linea tratteggiata sottile per vettura
const BAR_H_MEAL = 2         // linea tratteggiata per refezione
const BAR_H_SCOMP = 2        // linea tratteggiata grigia per scomp
const MARKER_H = 10          // altezza marker CVp/CVa

function blockStyle(t: PdcBlock["block_type"]) {
  switch (t) {
    case "train":
      return {
        stroke: "#111827",
        strokeWidth: BAR_H_TRAIN,
        dash: null as string | null,
        labelColor: "#0062CC",
      }
    case "coach_transfer":
      return {
        stroke: "#111827",
        strokeWidth: BAR_H_VETTURA,
        dash: "2 2",
        labelColor: "#7C3AED",
      }
    case "meal":
      return {
        stroke: "#111827",
        strokeWidth: BAR_H_MEAL,
        dash: "2 2",
        labelColor: "#10B981",
      }
    case "scomp":
      return {
        stroke: "#94A3B8",
        strokeWidth: BAR_H_SCOMP,
        dash: "2 2",
        labelColor: "#64748B",
      }
    case "cv_partenza":
    case "cv_arrivo":
      return {
        stroke: "#111827",
        strokeWidth: 1,
        dash: null as string | null,
        labelColor: "#B45309",
      }
    default:
      return {
        stroke: "#64748B",
        strokeWidth: 1,
        dash: null as string | null,
        labelColor: "#64748B",
      }
  }
}

// Etichetta mostrata sopra la barra (numero + stazione destinazione)
function blockLabel(b: PdcBlock): string {
  const id = b.train_id || b.vettura_id || ""
  const station = b.to_station || ""
  if (b.block_type === "cv_partenza") return `CVp ${id}${station ? " " + station : ""}`.trim()
  if (b.block_type === "cv_arrivo") return `CVa ${id}${station ? " " + station : ""}`.trim()
  if (b.block_type === "meal") return "REFEZ" + (station ? " " + station : "")
  if (b.block_type === "scomp") return "S.COMP" + (station ? " " + station : "")
  if (b.block_type === "coach_transfer") return `(${id}${station ? " " + station : ""}`
  if (b.block_type === "available") return "Disponibile"
  return `${id}${station ? " " + station : ""}`
}

// ── Componente ────────────────────────────────────────────────

export function PdcGantt({
  blocks: rawBlocks,
  startTime,
  endTime,
  onBlockClick,
  onTimelineClick,
  label,
  depot,
  height = 180,
}: PdcGanttProps) {
  const blocks = fillBlockTimes(rawBlocks, startTime, endTime)

  // Layout parametri
  const CHART_W = 1400
  const PAD_L = 110
  const PAD_R = 30
  const PAD_T = 60      // più spazio per label verticali sopra la barra
  const axisY = PAD_T + 40
  const plotW = CHART_W - PAD_L - PAD_R
  const minuteToX = (min: number) => PAD_L + (min / (SPAN_HOURS * 60)) * plotW

  // Tick orari
  const ticks: { hour: number; x: number }[] = []
  for (let i = 0; i <= SPAN_HOURS; i++) {
    const hour = (ORIGIN_HOUR + i) % 24
    ticks.push({ hour, x: minuteToX(i * 60) })
  }

  const startMin = startTime ? hhmmToMinutesRel(startTime) : null
  const endMin = endTime ? hhmmToMinutesRel(endTime) : null

  const handleTimelineClick = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!onTimelineClick) return
    const svg = e.currentTarget
    const rect = svg.getBoundingClientRect()
    const viewX = ((e.clientX - rect.left) / rect.width) * CHART_W
    if (viewX < PAD_L || viewX > PAD_L + plotW) return
    const minFromOrigin = ((viewX - PAD_L) / plotW) * SPAN_HOURS * 60
    const absHour = (ORIGIN_HOUR + Math.floor(minFromOrigin / 60)) % 24
    const minute = Math.round(minFromOrigin % 60)
    onTimelineClick(absHour, minute)
  }

  // Determina stazioni ai bordi dalla sequenza dei blocchi
  const firstStation = blocks.find((b) => b.from_station)?.from_station || depot || ""
  const lastStation =
    [...blocks].reverse().find((b) => b.to_station)?.to_station || depot || ""

  return (
    <div className="w-full overflow-x-auto border border-border-subtle rounded-lg bg-white p-2">
      <svg
        viewBox={`0 0 ${CHART_W} ${height}`}
        width="100%"
        preserveAspectRatio="xMinYMid meet"
        style={{ minWidth: 900, cursor: onTimelineClick ? "crosshair" : "default" }}
        onClick={handleTimelineClick}
      >
        {/* Label giornata + periodicità a sinistra */}
        {label && (
          <text
            x={8}
            y={axisY - 6}
            fontSize="13"
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
            y={axisY + 8}
            fontSize="10"
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
            height={axisY - PAD_T + 40}
            fill="#DBEAFE"
            opacity={0.2}
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

        {/* Asse orizzontale (più spezzato per stile PDF) */}
        {ticks.map((t, i) => {
          if (i === ticks.length - 1) return null
          const x1 = t.x + 4
          const x2 = ticks[i + 1].x - 4
          return (
            <line
              key={`ax-${i}`}
              x1={x1}
              y1={axisY}
              x2={x2}
              y2={axisY}
              stroke="#111827"
              strokeWidth={1}
            />
          )
        })}

        {/* Numeri ora sull'asse */}
        {ticks.map((t, i) => (
          <text
            key={`h-${i}`}
            x={t.x}
            y={axisY + 4}
            fontSize="11"
            textAnchor="middle"
            dominantBaseline="middle"
            fill="#0F172A"
            fontFamily="'Exo 2', sans-serif"
            fontWeight="500"
          >
            {t.hour}
          </text>
        ))}

        {/* Stazione sinistra (depot) */}
        {firstStation && (
          <text
            x={PAD_L - 4}
            y={PAD_T - 2}
            fontSize="11"
            textAnchor="end"
            fill="#0F172A"
            fontFamily="'Exo 2', sans-serif"
            fontWeight="600"
          >
            {firstStation}
          </text>
        )}
        {/* Stazione destra (depot) */}
        {lastStation && (
          <text
            x={PAD_L + plotW + 4}
            y={PAD_T - 2}
            fontSize="11"
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

          // CVp/CVa puntuali → marker verticale
          if (b.block_type === "cv_partenza" || b.block_type === "cv_arrivo") {
            if (sm === null) return null
            const x = minuteToX(sm)
            return (
              <g
                key={i}
                onClick={(e) => {
                  if (onBlockClick) {
                    e.stopPropagation()
                    onBlockClick(b, i)
                  }
                }}
                style={{ cursor: onBlockClick ? "pointer" : "default" }}
              >
                <line
                  x1={x}
                  y1={PAD_T - 2}
                  x2={x}
                  y2={PAD_T + MARKER_H}
                  stroke={bs.labelColor}
                  strokeWidth={1.5}
                />
                {/* Etichetta verticale (ruotata -90) */}
                <text
                  x={x}
                  y={PAD_T - 4}
                  fontSize="9"
                  textAnchor="start"
                  fill={bs.labelColor}
                  fontFamily="'Exo 2', sans-serif"
                  fontWeight="600"
                  transform={`rotate(-90, ${x}, ${PAD_T - 4})`}
                >
                  {labelTxt}
                </text>
                {/* Orario sotto */}
                {b.start_time && (
                  <text
                    x={x}
                    y={axisY + 18}
                    fontSize="8.5"
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
          const w = Math.max(2, x2 - x1)
          const barY = PAD_T + 8

          return (
            <g
              key={i}
              onClick={(e) => {
                if (onBlockClick) {
                  e.stopPropagation()
                  onBlockClick(b, i)
                }
              }}
              style={{ cursor: onBlockClick ? "pointer" : "default" }}
            >
              {/* Linea della barra (spessa per treno, tratteggiata per altri) */}
              <line
                x1={x1}
                y1={barY}
                x2={x2}
                y2={barY}
                stroke={bs.stroke}
                strokeWidth={bs.strokeWidth}
                strokeDasharray={bs.dash || undefined}
              />
              {/* Etichetta verticale sopra la barra */}
              <text
                x={x1 + w / 2}
                y={barY - 4}
                fontSize="9.5"
                textAnchor="start"
                fill={bs.labelColor}
                fontFamily="'Exo 2', sans-serif"
                fontWeight="700"
                transform={`rotate(-90, ${x1 + w / 2}, ${barY - 4})`}
              >
                {labelTxt}
              </text>
              {/* Pallino nero per accessori maggiorati */}
              {b.accessori_maggiorati === 1 && (
                <circle cx={x1 + 3} cy={barY} r={2.5} fill="#000" />
              )}
              {/* Orario partenza sotto asse (in piccolo) */}
              {b.start_time && (
                <text
                  x={x1}
                  y={axisY + 14}
                  fontSize="8"
                  textAnchor="middle"
                  fill="#475569"
                  fontFamily="monospace"
                >
                  {b.start_time.slice(3)}
                </text>
              )}
              {/* Orario arrivo sotto asse */}
              {b.end_time && w > 18 && (
                <text
                  x={x2}
                  y={axisY + 14}
                  fontSize="8"
                  textAnchor="middle"
                  fill="#475569"
                  fontFamily="monospace"
                >
                  {b.end_time.slice(3)}
                </text>
              )}
            </g>
          )
        })}
      </svg>

      {/* Legenda */}
      <div className="flex flex-wrap gap-3 mt-1 text-[10px] text-muted-foreground px-1">
        <span className="flex items-center gap-1">
          <span className="inline-block w-4 h-0.5 bg-[#111827]" /> Treno
        </span>
        <span className="flex items-center gap-1">
          <span
            className="inline-block w-4 h-0"
            style={{ borderTop: "1px dashed #111827" }}
          />
          Vettura
        </span>
        <span className="flex items-center gap-1">
          <span
            className="inline-block w-4 h-0"
            style={{ borderTop: "1px dashed #10B981" }}
          />
          Refezione
        </span>
        <span className="flex items-center gap-1">
          <span
            className="inline-block w-4 h-0"
            style={{ borderTop: "1px dashed #94A3B8" }}
          />
          S.COMP
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-px h-3 bg-[#B45309]" /> CVp/CVa
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full bg-black" /> Acc. magg.
        </span>
      </div>
    </div>
  )
}
