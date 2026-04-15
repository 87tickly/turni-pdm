import type { TimelineBlock } from "@/lib/api"

/**
 * Timeline Gantt orizzontale stile PDF Trenord.
 * Scala DINAMICA: mostra solo le ore rilevanti al turno.
 * Barre grandi con testo verticale (treno + stazione).
 * Deposito a inizio e fine. Totali a destra.
 */

interface GanttTimelineProps {
  blocks: TimelineBlock[]
  dayLabel?: string
  dayNumber?: number
  presentationTime?: string
  endTime?: string
  prestazione?: string
  condotta?: string
  km?: number
  notturno?: boolean
  riposo?: string
  deposito?: string
}

const FONT = "'Exo 2', sans-serif"
const COL = {
  text: "#F1F5F9",
  muted: "#94A3B8",
  dim: "#64748b",
  grid: "#475569",
  gridFaint: "#334155",
  bg: "transparent",
}

function blockStyle(type: string) {
  switch (type) {
    case "train":
      return { fill: COL.text, dash: false, showLabel: true }
    case "deadhead":
      return { fill: "#64748b", dash: false, showLabel: true }
    case "meal":
      return { fill: "none", dash: true, showLabel: true }
    case "attesa":
      return { fill: "none", dash: true, showLabel: false }
    case "accessori":
      return { fill: "#334155", dash: false, showLabel: false }
    case "extra":
      return { fill: "#1e293b", dash: false, showLabel: false }
    case "spostamento":
      return { fill: "#0070B5", dash: false, showLabel: true }
    case "giro_return":
      return { fill: "#64748b", dash: false, showLabel: true }
    default:
      return { fill: "#334155", dash: false, showLabel: false }
  }
}

export function GanttTimeline({
  blocks,
  dayLabel,
  dayNumber,
  presentationTime,
  endTime,
  prestazione,
  condotta,
  km,
  notturno,
  riposo,
  deposito,
}: GanttTimelineProps) {
  if (!blocks.length) return null

  // ── Calcola range ore DINAMICO ──
  const minStart = Math.min(...blocks.map((b) => b.start))
  const maxEnd = Math.max(...blocks.map((b) => b.end))

  // Arrotonda: inizia 1h prima, finisce 1h dopo
  const startHour = Math.floor(minStart / 60) - 1
  const endHour = Math.ceil(maxEnd / 60) + 1
  const spanHours = endHour - startHour

  // Layout
  const LEFT_MARGIN = 80
  const RIGHT_MARGIN = 180
  const GRID_WIDTH = Math.max(spanHours * 55, 400) // min 55px/ora
  const TOTAL_W = LEFT_MARGIN + GRID_WIDTH + RIGHT_MARGIN
  const BAR_Y = 60
  const BAR_H = 18
  const ROW_H = 110
  const TOTAL_H = ROW_H + 28
  const hourWidth = GRID_WIDTH / spanHours

  function minToX(minutes: number): number {
    const hoursFromStart = minutes / 60 - startHour
    return LEFT_MARGIN + hoursFromStart * hourWidth
  }

  return (
    <div className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${TOTAL_W} ${TOTAL_H}`}
        width="100%"
        height={TOTAL_H}
        style={{ minWidth: Math.min(TOTAL_W, 800) }}
        className="select-none"
      >
        {/* ── Left: tipo giornata + numero ── */}
        <text x="8" y="22" fontSize="14" fontWeight="800" fill={COL.text} fontFamily={FONT}>
          {dayLabel || ""}
        </text>
        {dayNumber !== undefined && (
          <text x="8" y="55" fontSize="28" fontWeight="900" fill={COL.text} fontFamily={FONT}>
            {dayNumber}
          </text>
        )}
        {presentationTime && endTime && (
          <text x="8" y="78" fontSize="11" fill={COL.muted} fontFamily={FONT} fontWeight="600">
            [{presentationTime}] [{endTime}]
          </text>
        )}

        {/* ── Deposito labels (inizio + fine riga) ── */}
        {deposito && (
          <>
            {/* A sinistra, prima del primo blocco */}
            <text
              x={LEFT_MARGIN - 5}
              y={BAR_Y + BAR_H / 2 + 4}
              fontSize="11"
              fontWeight="800"
              fill={COL.muted}
              textAnchor="end"
              fontFamily={FONT}
            >
              {deposito.length > 10 ? deposito.slice(0, 10) : deposito}
            </text>
            {/* A destra, dopo l'ultimo blocco */}
            <text
              x={LEFT_MARGIN + GRID_WIDTH + 5}
              y={BAR_Y + BAR_H / 2 + 4}
              fontSize="11"
              fontWeight="800"
              fill={COL.muted}
              textAnchor="start"
              fontFamily={FONT}
            >
              {deposito.length > 10 ? deposito.slice(0, 10) : deposito}
            </text>
          </>
        )}

        {/* ── Griglia ore ── */}
        {Array.from({ length: spanHours + 1 }, (_, i) => {
          const hour = ((startHour + i) % 24 + 24) % 24
          const x = LEFT_MARGIN + i * hourWidth
          return (
            <g key={i}>
              {/* Tick mark */}
              <line x1={x} y1={ROW_H - 4} x2={x} y2={ROW_H + 4} stroke={COL.grid} strokeWidth="1" />
              {/* Vertical guide */}
              <line x1={x} y1={22} x2={x} y2={ROW_H - 4} stroke={COL.gridFaint} strokeWidth="0.5" strokeDasharray="2,4" />
              {/* Hour label */}
              <text x={x} y={ROW_H + 20} fontSize="10" fill={COL.dim} textAnchor="middle" fontFamily={FONT} fontWeight="600">
                {hour}
              </text>
            </g>
          )
        })}

        {/* Asse orizzontale */}
        <line x1={LEFT_MARGIN} y1={ROW_H} x2={LEFT_MARGIN + GRID_WIDTH} y2={ROW_H} stroke={COL.grid} strokeWidth="1.5" />

        {/* ── Blocchi timeline ── */}
        {blocks.map((block, i) => {
          const x1 = minToX(block.start)
          const x2 = minToX(block.end)
          const w = x2 - x1
          const style = blockStyle(block.type)

          if (w < 1 && !style.showLabel) return null

          return (
            <g key={i}>
              {/* Barra o linea tratteggiata */}
              {style.dash ? (
                <line
                  x1={x1} y1={BAR_Y + BAR_H / 2}
                  x2={x2} y2={BAR_Y + BAR_H / 2}
                  stroke={COL.muted} strokeWidth="2" strokeDasharray="6,4"
                />
              ) : (
                <rect
                  x={x1} y={BAR_Y}
                  width={Math.max(w, 3)}
                  height={BAR_H}
                  fill={style.fill}
                  rx="1"
                />
              )}

              {/* Testo verticale sopra la barra */}
              {style.showLabel && w > 10 && (
                <g transform={`translate(${x1 + w / 2}, ${BAR_Y - 5}) rotate(-90)`}>
                  {/* Nome treno / label */}
                  <text
                    fontSize="10"
                    fontWeight="800"
                    fill={block.type === "meal" ? COL.muted : COL.text}
                    textAnchor="start"
                    fontFamily={FONT}
                  >
                    {block.type === "meal" ? "REFEZ" : block.label}
                  </text>
                  {/* Stazione destinazione */}
                  {block.to_station && (block.type === "train" || block.type === "deadhead") && (
                    <text
                      y="11"
                      fontSize="9"
                      fill={COL.muted}
                      textAnchor="start"
                      fontFamily={FONT}
                      fontWeight="600"
                    >
                      {block.to_station.length > 8 ? block.to_station.slice(0, 8) : block.to_station}
                    </text>
                  )}
                </g>
              )}

              {/* Durata sotto la barra */}
              {block.duration > 0 && w > 18 && (
                <text
                  x={x1 + w / 2}
                  y={BAR_Y + BAR_H + 14}
                  fontSize="9"
                  fill={COL.dim}
                  textAnchor="middle"
                  fontFamily={FONT}
                  fontWeight="600"
                >
                  {block.duration}
                </text>
              )}

              {/* Orario sopra barre treno (se c'è spazio) */}
              {(block.type === "train" || block.type === "deadhead") && w > 40 && (
                <>
                  <text
                    x={x1 + 2}
                    y={ROW_H + 14}
                    fontSize="8"
                    fill={COL.dim}
                    fontFamily={FONT}
                  >
                    {block.start_time}
                  </text>
                </>
              )}
            </g>
          )
        })}

        {/* ── Totali a destra ── */}
        {(() => {
          const rx = LEFT_MARGIN + GRID_WIDTH + 60
          const items = [
            { label: "Lav", value: prestazione || "" },
            { label: "Cct", value: condotta || "" },
            { label: "Km", value: km !== undefined ? String(km) : "" },
            { label: "Not", value: notturno ? "si" : "no" },
            { label: "Rip", value: riposo || "" },
          ]
          return items.map((item, idx) => {
            const y = 22 + idx * 18
            return (
              <g key={item.label}>
                <text x={rx} y={y} fontSize="10" fontWeight="600" fill={COL.dim} fontFamily={FONT}>
                  {item.label}
                </text>
                <text
                  x={rx + 30}
                  y={y}
                  fontSize="11"
                  fontWeight="700"
                  fill={item.label === "Not" && notturno ? "#F59E0B" : COL.text}
                  fontFamily={FONT}
                >
                  {item.value || "—"}
                </text>
              </g>
            )
          })
        })()}
      </svg>
    </div>
  )
}

/**
 * Wrapper per dati di validazione.
 */
export function GanttFromValidation({
  blocks,
  dayLabel,
  dayNumber,
  presentationTime,
  endTime,
  prestazioneMin,
  condottaMin,
  isNotturno,
  deposito,
}: {
  blocks: TimelineBlock[]
  dayLabel?: string
  dayNumber?: number
  presentationTime?: string
  endTime?: string
  prestazioneMin?: number
  condottaMin?: number
  isNotturno?: boolean
  deposito?: string
}) {
  const fmtHM = (min: number) => {
    const h = Math.floor(min / 60)
    const m = min % 60
    return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}`
  }

  return (
    <GanttTimeline
      blocks={blocks}
      dayLabel={dayLabel}
      dayNumber={dayNumber}
      presentationTime={presentationTime}
      endTime={endTime}
      prestazione={prestazioneMin !== undefined ? fmtHM(prestazioneMin) : undefined}
      condotta={condottaMin !== undefined ? fmtHM(condottaMin) : undefined}
      notturno={isNotturno}
      deposito={deposito}
    />
  )
}
