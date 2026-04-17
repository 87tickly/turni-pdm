/**
 * PdcGantt — Timeline Gantt visuale per una giornata di turno PdC.
 *
 * Scala asse: 3 -> 24 -> 1 -> 2 -> 3 (giornata operativa, passa mezzanotte).
 * Barre colorate per tipo blocco, allineate a partire da start_time/end_time.
 * Marker puntuali per CVp/CVa. Pallino nero per accessori maggiorati.
 *
 * Modalità:
 *  - readonly (default): sola visualizzazione
 *  - onBlockClick: callback per click su un blocco (builder interattivo)
 */

import type { PdcBlock } from "@/lib/api"

interface PdcGanttProps {
  blocks: PdcBlock[]
  startTime?: string          // orario inizio prestazione [HH:MM]
  endTime?: string            // orario fine prestazione [HH:MM]
  onBlockClick?: (block: PdcBlock, index: number) => void
  onTimelineClick?: (hour: number, minute: number) => void  // click su area vuota
  label?: string              // es. "g1 LMXGVSD"
}

// ── Scala temporale ────────────────────────────────────────────
// Asse: 3 -> 24 -> 1 -> 2 -> 3 (il "3" finale è le 3 del giorno successivo)
// 25 tick in totale, 24 intervalli da 1h = 24*60 = 1440 minuti
// L'origine temporale e' 3:00. Un orario HH:MM va convertito in minuti relativi:
//   HH < 3 -> HH + 24 (mattina successiva)
const ORIGIN_HOUR = 3
const SPAN_HOURS = 24

function hhmmToMinutesRel(hhmm: string): number | null {
  if (!hhmm || !/^\d{1,2}:\d{2}$/.test(hhmm)) return null
  const [h, m] = hhmm.split(":").map(Number)
  let hourAdj = h
  if (h < ORIGIN_HOUR) hourAdj = h + 24
  return (hourAdj - ORIGIN_HOUR) * 60 + m
}

/**
 * Riempie gli orari mancanti di una sequenza di blocchi.
 *
 * Regole (mirrorano il layout dei PDF Trenord, dove molti blocchi
 * ereditano gli orari da blocchi adiacenti):
 *
 *  1. Forward pass: blocchi senza start_time ereditano l'end_time del
 *     blocco precedente. Il primissimo eredita startTime della giornata.
 *  2. Backward pass: blocchi senza end_time ereditano lo start_time del
 *     blocco successivo. L'ultimo eredita endTime della giornata.
 *  3. CVp / CVa puntuali: start_time == end_time se solo uno dei due è
 *     popolato.
 *  4. Se dopo i 3 passi manca ancora un orario, lascio null (rendering
 *     saltera' quel blocco come prima).
 */
function fillBlockTimes(
  blocks: PdcBlock[],
  dayStart?: string,
  dayEnd?: string,
): PdcBlock[] {
  const out = blocks.map((b) => ({ ...b }))
  const isPuntual = (bt: string) =>
    bt === "cv_partenza" || bt === "cv_arrivo"

  // Forward pass: ogni blocco eredita start_time dall'end_time del
  // precedente. Per blocchi puntuali, se solo start_time e' noto,
  // mirror su end_time cosi' il successivo puo' ereditare.
  for (let i = 0; i < out.length; i++) {
    const b = out[i]
    if (!b.start_time) {
      const prev = out[i - 1]
      if (prev && prev.end_time) b.start_time = prev.end_time
      else if (prev && prev.start_time && isPuntual(prev.block_type))
        b.start_time = prev.start_time
      else if (i === 0 && dayStart) b.start_time = dayStart
    }
    // Mirror puntuali cosi' contribuiscono al forward pass
    if (isPuntual(b.block_type)) {
      if (!b.end_time && b.start_time) b.end_time = b.start_time
    }
  }

  // Backward pass: ogni blocco eredita end_time dallo start_time del
  // successivo. Mirror puntuali analogamente.
  for (let i = out.length - 1; i >= 0; i--) {
    const b = out[i]
    if (!b.end_time) {
      const next = out[i + 1]
      if (next && next.start_time) b.end_time = next.start_time
      else if (next && next.end_time && isPuntual(next.block_type))
        b.end_time = next.end_time
      else if (i === out.length - 1 && dayEnd) b.end_time = dayEnd
    }
    if (isPuntual(b.block_type)) {
      if (!b.start_time && b.end_time) b.start_time = b.end_time
    }
  }

  return out
}

// ── Colori e altezze per tipo ─────────────────────────────────
const BAR_H_TALL = 22    // train
const BAR_H_MED = 14     // coach_transfer, meal
const BAR_H_LONG = 10    // scomp
const MARKER_H = 20      // cv_partenza/arrivo

function blockStyle(t: PdcBlock["block_type"]) {
  switch (t) {
    case "train":
      return { fill: "#0062CC", stroke: "#0062CC", h: BAR_H_TALL, dash: null, label: "" }
    case "coach_transfer":
      return { fill: "#7C3AED", stroke: "#7C3AED", h: BAR_H_MED, dash: "3 2", label: "" }
    case "meal":
      return { fill: "#10B981", stroke: "#10B981", h: BAR_H_MED, dash: "3 2", label: "REFEZ" }
    case "scomp":
      return { fill: "#94A3B8", stroke: "#94A3B8", h: BAR_H_LONG, dash: "2 2", label: "S.COMP" }
    case "cv_partenza":
      return { fill: "#F59E0B", stroke: "#F59E0B", h: MARKER_H, dash: null, label: "CVp" }
    case "cv_arrivo":
      return { fill: "#F59E0B", stroke: "#F59E0B", h: MARKER_H, dash: null, label: "CVa" }
    case "available":
      return { fill: "#E2E8F0", stroke: "#CBD5E1", h: BAR_H_LONG, dash: null, label: "DISP." }
    default:
      return { fill: "#64748B", stroke: "#64748B", h: BAR_H_MED, dash: null, label: "" }
  }
}

// ── Componente ────────────────────────────────────────────────

export function PdcGantt({
  blocks: rawBlocks,
  startTime,
  endTime,
  onBlockClick,
  onTimelineClick,
  label,
}: PdcGanttProps) {
  // Riempie gli orari mancanti per poter renderizzare TUTTI i blocchi
  // (es. CVp/CVa puntuali o treni con solo end_time per la regola
  // "preceduto da cv_partenza -> solo end").
  const blocks = fillBlockTimes(rawBlocks, startTime, endTime)

  // Layout parametri
  const CHART_W = 1200
  const CHART_H = 100
  const PAD_L = 90
  const PAD_R = 20
  const PAD_T = 34
  const axisY = PAD_T + 30

  const plotW = CHART_W - PAD_L - PAD_R
  const minuteToX = (min: number) => PAD_L + (min / (SPAN_HOURS * 60)) * plotW

  // Tick orari (0..24) che corrispondono alle ore 3..24..1..2..3
  const ticks: { hour: number; x: number }[] = []
  for (let i = 0; i <= SPAN_HOURS; i++) {
    const hour = ((ORIGIN_HOUR + i) % 24)
    ticks.push({ hour, x: minuteToX(i * 60) })
  }

  // Prestazione globale (contorno verde)
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

  return (
    <div className="w-full overflow-x-auto border border-border-subtle rounded-lg bg-[#F8FAFC] p-2">
      <svg
        viewBox={`0 0 ${CHART_W} ${CHART_H}`}
        width="100%"
        preserveAspectRatio="xMinYMid meet"
        style={{ minWidth: 600, cursor: onTimelineClick ? "crosshair" : "default" }}
        onClick={handleTimelineClick}
      >
        {/* Label a sinistra (giornata + periodicità + orari) */}
        {label && (
          <text
            x={PAD_L - 8}
            y={axisY + 4}
            fontSize="11"
            textAnchor="end"
            fill="#0F172A"
            fontFamily="'Exo 2', sans-serif"
            fontWeight="600"
          >
            {label}
          </text>
        )}
        {startTime && endTime && (
          <text
            x={PAD_L - 8}
            y={axisY + 16}
            fontSize="9"
            textAnchor="end"
            fill="#64748B"
            fontFamily="monospace"
          >
            [{startTime}] [{endTime}]
          </text>
        )}

        {/* Prestazione: zona evidenziata */}
        {startMin !== null && endMin !== null && (
          <rect
            x={minuteToX(startMin)}
            y={PAD_T - 4}
            width={Math.max(0, minuteToX(endMin) - minuteToX(startMin))}
            height={axisY + 30 - PAD_T + 4}
            fill="#DBEAFE"
            opacity={0.25}
          />
        )}

        {/* Griglia verticale */}
        {ticks.map((t, i) => (
          <line
            key={i}
            x1={t.x}
            y1={PAD_T}
            x2={t.x}
            y2={axisY + 20}
            stroke="#E2E8F0"
            strokeWidth={0.5}
          />
        ))}

        {/* Asse orizzontale */}
        <line
          x1={PAD_L}
          y1={axisY}
          x2={PAD_L + plotW}
          y2={axisY}
          stroke="#475569"
          strokeWidth={1}
        />

        {/* Tick + numeri ora */}
        {ticks.map((t, i) => (
          <g key={`tick-${i}`}>
            <line x1={t.x} y1={axisY} x2={t.x} y2={axisY + 3} stroke="#475569" />
            <text
              x={t.x}
              y={axisY + 14}
              fontSize="10"
              textAnchor="middle"
              fill="#0F172A"
              fontFamily="monospace"
            >
              {t.hour}
            </text>
          </g>
        ))}

        {/* Blocchi */}
        {blocks.map((b, i) => {
          const bs = blockStyle(b.block_type)
          const sm = hhmmToMinutesRel(b.start_time)
          const em = hhmmToMinutesRel(b.end_time)

          // Gestione blocchi puntuali (CVp/CVa): solo un istante
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
                  y1={axisY - bs.h / 2}
                  x2={x}
                  y2={axisY + bs.h / 2}
                  stroke={bs.stroke}
                  strokeWidth={2.5}
                />
                <text
                  x={x}
                  y={axisY - bs.h / 2 - 4}
                  fontSize="8"
                  textAnchor="middle"
                  fill={bs.stroke}
                  fontWeight="bold"
                >
                  {bs.label}
                </text>
                {b.start_time && (
                  <text
                    x={x}
                    y={axisY + bs.h / 2 + 8}
                    fontSize="8"
                    textAnchor="middle"
                    fill="#64748B"
                    fontFamily="monospace"
                  >
                    {b.start_time}
                  </text>
                )}
              </g>
            )
          }

          // Blocchi di durata: richiedono start + end
          if (sm === null) return null
          const emEff = em !== null && em > sm ? em : sm + 15
          const x1 = minuteToX(sm)
          const x2 = minuteToX(emEff)
          const w = Math.max(2, x2 - x1)
          const y = axisY - bs.h / 2
          const txt = b.train_id || b.vettura_id || bs.label

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
              <rect
                x={x1}
                y={y}
                width={w}
                height={bs.h}
                fill={bs.fill}
                stroke={bs.stroke}
                strokeWidth={1}
                strokeDasharray={bs.dash || undefined}
                fillOpacity={bs.dash ? 0.15 : 0.85}
                rx={1.5}
              />
              {/* Testo treno / vettura sopra */}
              {txt && (
                <text
                  x={x1 + w / 2}
                  y={y - 3}
                  fontSize="9"
                  textAnchor="middle"
                  fill="#0F172A"
                  fontFamily="'Exo 2', sans-serif"
                  fontWeight="600"
                >
                  {txt}
                </text>
              )}
              {/* Stazione destinazione a destra */}
              {b.to_station && w > 40 && (
                <text
                  x={x2 + 2}
                  y={y + bs.h / 2 + 3}
                  fontSize="8"
                  fill="#64748B"
                  fontFamily="monospace"
                >
                  {b.to_station}
                </text>
              )}
              {/* Orari sotto */}
              {b.start_time && (
                <text
                  x={x1}
                  y={y + bs.h + 9}
                  fontSize="8"
                  textAnchor="start"
                  fill="#475569"
                  fontFamily="monospace"
                >
                  {b.start_time}
                </text>
              )}
              {b.end_time && w > 25 && (
                <text
                  x={x2}
                  y={y + bs.h + 9}
                  fontSize="8"
                  textAnchor="end"
                  fill="#475569"
                  fontFamily="monospace"
                >
                  {b.end_time}
                </text>
              )}
              {/* Pallino accessori maggiorati */}
              {b.accessori_maggiorati === 1 && (
                <circle
                  cx={x1 + 4}
                  cy={y + bs.h / 2}
                  r={2.5}
                  fill="#000"
                />
              )}
            </g>
          )
        })}
      </svg>

      {/* Legenda */}
      <div className="flex flex-wrap gap-3 mt-1 text-[10px] text-muted-foreground px-1">
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-2 bg-[#0062CC]" /> Treno
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-2 border border-[#7C3AED] border-dashed bg-[#7C3AED]/20" /> Vettura
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-2 border border-[#10B981] border-dashed bg-[#10B981]/20" /> Refezione
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-2 border border-[#94A3B8] border-dashed bg-[#94A3B8]/20" /> S.COMP
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-0.5 h-2 bg-[#F59E0B]" /> CVp/CVa
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full bg-black" /> Acc. magg.
        </span>
      </div>
    </div>
  )
}
