import type { TimelineBlock } from "@/lib/api"

/**
 * Timeline Gantt orizzontale stile PDF Trenord.
 * Scala FISSA 0-24h. Barre treno più alte, accessori/extra più basse.
 * Sfondo grigio chiaro per staccare dalla pagina bianca.
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
  text: "#0F172A",
  muted: "#64748B",
  dim: "#94A3B8",
  grid: "#CBD5E1",
  gridFaint: "#E2E8F0",
  ganttBg: "#F1F5F9",
}

// Altezze differenziate per tipo blocco
const BAR_H_TRAIN = 22        // treni: barra grande
const BAR_H_SECONDARY = 14    // deadhead, spostamento, giro_return
const BAR_H_MINOR = 10        // accessori, extra

function blockStyle(type: string) {
  switch (type) {
    case "train":
      return { fill: "#0062CC", h: BAR_H_TRAIN, dash: false, showLabel: true }
    case "deadhead":
      return { fill: "#7C3AED", h: BAR_H_SECONDARY, dash: false, showLabel: true }
    case "meal":
      return { fill: "none", h: BAR_H_SECONDARY, dash: true, showLabel: true }
    case "attesa":
      return { fill: "none", h: BAR_H_MINOR, dash: true, showLabel: false }
    case "accessori":
      return { fill: "#F59E0B", h: BAR_H_MINOR, dash: false, showLabel: false }
    case "extra":
      return { fill: "#FB923C", h: BAR_H_MINOR, dash: false, showLabel: false }
    case "spostamento":
      return { fill: "#0891B2", h: BAR_H_SECONDARY, dash: false, showLabel: true }
    case "giro_return":
      return { fill: "#7C3AED", h: BAR_H_SECONDARY, dash: false, showLabel: true }
    default:
      return { fill: "#94A3B8", h: BAR_H_MINOR, dash: false, showLabel: false }
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

  // ── Scala FISSA 0-24 ──
  const startHour = 0
  const endHour = 24
  const spanHours = 24

  // Layout
  const LEFT_MARGIN = 80
  const RIGHT_MARGIN = 120
  const GRID_WIDTH = spanHours * 42 // 42px per ora = 1008px totali
  const TOTAL_W = LEFT_MARGIN + GRID_WIDTH + RIGHT_MARGIN
  const BAR_CENTER_Y = 68 // centro verticale delle barre
  const ROW_H = 110
  const TOTAL_H = ROW_H + 28
  const hourWidth = GRID_WIDTH / spanHours

  function minToX(minutes: number): number {
    const hoursFromStart = minutes / 60 - startHour
    return LEFT_MARGIN + hoursFromStart * hourWidth
  }

  // Pre-calcola posizioni label per evitare sovrapposizioni
  const labelBlocks = blocks
    .map((block, i) => {
      const x1 = minToX(block.start)
      const x2 = minToX(block.end)
      const w = x2 - x1
      const style = blockStyle(block.type)
      return { block, i, x1, x2, w, style }
    })
    .filter((b) => b.style.showLabel && b.w > 6)

  // Rileva sovrapposizioni tra label verticali
  function labelsOverlap(a: typeof labelBlocks[0], b: typeof labelBlocks[0]): boolean {
    const aCenter = a.x1 + a.w / 2
    const bCenter = b.x1 + b.w / 2
    return Math.abs(aCenter - bCenter) < 14 // 14px minimo tra centri
  }

  // Segna blocchi che devono shiftare la label
  const labelShifted = new Set<number>()
  for (let j = 1; j < labelBlocks.length; j++) {
    if (labelsOverlap(labelBlocks[j - 1], labelBlocks[j])) {
      labelShifted.add(labelBlocks[j].i)
    }
  }

  return (
    <div className="overflow-x-auto rounded-lg bg-[#F1F5F9] p-3">
      <svg
        viewBox={`0 0 ${TOTAL_W} ${TOTAL_H}`}
        width="100%"
        height={TOTAL_H}
        style={{ minWidth: Math.min(TOTAL_W, 900) }}
        className="select-none"
      >
        {/* ── Left: tipo giornata + numero ── */}
        <text x="8" y="22" fontSize="15" fontWeight="800" fill={COL.text} fontFamily={FONT}>
          {dayLabel || ""}
        </text>
        {dayNumber !== undefined && (
          <text x="8" y="55" fontSize="28" fontWeight="900" fill={COL.text} fontFamily={FONT}>
            {dayNumber}
          </text>
        )}
        {presentationTime && endTime && (
          <text x="8" y="78" fontSize="11" fill={COL.muted} fontFamily={FONT} fontWeight="700">
            [{presentationTime}] [{endTime}]
          </text>
        )}

        {/* ── Deposito labels (inizio + fine riga) ── */}
        {deposito && (
          <>
            <text
              x={LEFT_MARGIN - 5}
              y={BAR_CENTER_Y + 4}
              fontSize="10"
              fontWeight="800"
              fill={COL.muted}
              textAnchor="end"
              fontFamily={FONT}
            >
              {deposito.length > 10 ? deposito.slice(0, 10) : deposito}
            </text>
            <text
              x={LEFT_MARGIN + GRID_WIDTH + 5}
              y={BAR_CENTER_Y + 4}
              fontSize="10"
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
          const hour = (startHour + i) % 24
          const x = LEFT_MARGIN + i * hourWidth
          return (
            <g key={i}>
              <line x1={x} y1={ROW_H - 4} x2={x} y2={ROW_H + 4} stroke={COL.grid} strokeWidth="1" />
              <line x1={x} y1={22} x2={x} y2={ROW_H - 4} stroke={COL.gridFaint} strokeWidth="0.5" strokeDasharray="2,4" />
              <text x={x} y={ROW_H + 20} fontSize="10" fill={COL.muted} textAnchor="middle" fontFamily={FONT} fontWeight="700">
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

          // Centra verticalmente ogni barra rispetto a BAR_CENTER_Y
          const barY = BAR_CENTER_Y - style.h / 2

          return (
            <g key={i}>
              {/* Barra o linea tratteggiata */}
              {style.dash ? (
                <line
                  x1={x1} y1={BAR_CENTER_Y}
                  x2={x2} y2={BAR_CENTER_Y}
                  stroke={COL.muted} strokeWidth="2" strokeDasharray="6,4"
                />
              ) : (
                <rect
                  x={x1} y={barY}
                  width={Math.max(w, 3)}
                  height={style.h}
                  fill={style.fill}
                  rx="2"
                />
              )}

              {/* Testo verticale sopra la barra */}
              {style.showLabel && w > 6 && (
                <g transform={`translate(${x1 + w / 2}, ${barY - (labelShifted.has(i) ? 18 : 4)}) rotate(-90)`}>
                  <text
                    fontSize="11"
                    fontWeight="900"
                    fill={block.type === "meal" ? COL.muted : COL.text}
                    textAnchor="start"
                    fontFamily={FONT}
                  >
                    {block.type === "meal" ? "REFEZ" : block.label}
                  </text>
                  {block.to_station && (block.type === "train" || block.type === "deadhead") && (
                    <text
                      y="12"
                      fontSize="9"
                      fill={COL.muted}
                      textAnchor="start"
                      fontFamily={FONT}
                      fontWeight="700"
                    >
                      {block.to_station.length > 8 ? block.to_station.slice(0, 8) : block.to_station}
                    </text>
                  )}
                </g>
              )}

              {/* Durata sotto la barra (solo treni e blocchi larghi) */}
              {block.type === "train" && block.duration > 0 && w > 20 && (
                <text
                  x={x1 + w / 2}
                  y={barY + style.h + 13}
                  fontSize="9"
                  fill={COL.muted}
                  textAnchor="middle"
                  fontFamily={FONT}
                  fontWeight="700"
                >
                  {block.duration}&apos;
                </text>
              )}
            </g>
          )
        })}

        {/* ── Totali a destra ── */}
        {(() => {
          const rx = LEFT_MARGIN + GRID_WIDTH + 50
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
                <text x={rx} y={y} fontSize="10" fontWeight="700" fill={COL.muted} fontFamily={FONT}>
                  {item.label}
                </text>
                <text
                  x={rx + 30}
                  y={y}
                  fontSize="11"
                  fontWeight="800"
                  fill={item.label === "Not" && notturno ? "#DC2626" : COL.text}
                  fontFamily={FONT}
                >
                  {item.value || "\u2014"}
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
