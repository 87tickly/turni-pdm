import { cn } from "@/lib/utils"
import type { TimelineBlock } from "@/lib/api"

/**
 * Timeline Gantt orizzontale stile PDF Trenord.
 * - Asse orario 3→4→...→24→1→2→3 in basso
 * - Barre proporzionali per durata
 * - Testo verticale sopra le barre (numero treno + stazione)
 * - Linee tratteggiate per attese/spostamenti
 * - Totali a destra
 */

interface GanttTimelineProps {
  blocks: TimelineBlock[]
  dayLabel?: string          // es. "LMXGVSD", "D", "SD"
  dayNumber?: number         // es. 1, 2, 3
  presentationTime?: string  // es. "18:20"
  endTime?: string           // es. "00:25"
  prestazione?: string       // es. "06:05"
  condotta?: string          // es. "03:22"
  km?: number
  notturno?: boolean
  riposo?: string            // es. "15:45"
  deposito?: string
}

// Orario → posizione X sulla griglia (3:00 = inizio)
const GRID_START_HOUR = 3 // la griglia parte dalle 3:00
const TOTAL_HOURS = 24
const GRID_LEFT = 80   // px margine sinistro (per label giornata)
const GRID_RIGHT = 180 // px margine destro (per totali)
const GRID_WIDTH = 900 // px area griglia
const ROW_HEIGHT = 100  // px altezza riga
const BAR_Y = 55       // y posizione barre
const BAR_HEIGHT = 14   // altezza barre
const HOUR_WIDTH = GRID_WIDTH / TOTAL_HOURS // ~37.5 px/ora

function minToGridX(minutes: number): number {
  // Converti minuti dall'inizio giornata (0:00=0) in posizione sulla griglia
  let hours = minutes / 60
  // La griglia parte da 3:00, quindi shifta
  hours = hours - GRID_START_HOUR
  if (hours < 0) hours += 24
  return GRID_LEFT + hours * HOUR_WIDTH
}

// Tipo blocco → stile
function blockStyle(type: string): { fill: string; stroke: string; dash: boolean; label: boolean } {
  switch (type) {
    case "train":
      return { fill: "#F1F5F9", stroke: "#F1F5F9", dash: false, label: true }
    case "deadhead":
      return { fill: "#64748b", stroke: "#94A3B8", dash: false, label: true }
    case "meal":
      return { fill: "none", stroke: "#94A3B8", dash: true, label: true }
    case "attesa":
      return { fill: "none", stroke: "#334155", dash: true, label: false }
    case "accessori":
      return { fill: "#334155", stroke: "#334155", dash: false, label: false }
    case "extra":
      return { fill: "#1e293b", stroke: "#1e293b", dash: false, label: false }
    case "spostamento":
      return { fill: "#0070B5", stroke: "#0070B5", dash: false, label: true }
    case "giro_return":
      return { fill: "#64748b", stroke: "#94A3B8", dash: false, label: true }
    default:
      return { fill: "#334155", stroke: "#334155", dash: false, label: false }
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

  const totalW = GRID_LEFT + GRID_WIDTH + GRID_RIGHT
  const totalH = ROW_HEIGHT + 25 // extra for hour labels

  return (
    <div className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${totalW} ${totalH}`}
        width={totalW}
        height={totalH}
        className="font-sans"
        style={{ minWidth: totalW }}
      >
        {/* ── Background ── */}
        <rect width={totalW} height={totalH} fill="transparent" />

        {/* ── Left label: day type + number ── */}
        <text x="8" y="20" fontSize="13" fontWeight="800" fill="#F1F5F9" fontFamily="'Exo 2', sans-serif">
          {dayLabel || ""}
        </text>
        {dayNumber !== undefined && (
          <text x="8" y="50" fontSize="22" fontWeight="900" fill="#F1F5F9" fontFamily="'Exo 2', sans-serif">
            {dayNumber}
          </text>
        )}
        {presentationTime && endTime && (
          <text x="8" y="70" fontSize="10" fill="#94A3B8" fontFamily="'Exo 2', sans-serif">
            [{presentationTime}] [{endTime}]
          </text>
        )}

        {/* ── Deposito labels ── */}
        {deposito && (
          <>
            <text
              x={GRID_LEFT - 5}
              y={BAR_Y + BAR_HEIGHT / 2 + 4}
              fontSize="10"
              fontWeight="700"
              fill="#94A3B8"
              textAnchor="end"
              fontFamily="'Exo 2', sans-serif"
            >
              {deposito.length > 8 ? deposito.slice(0, 8) : deposito}
            </text>
          </>
        )}

        {/* ── Hour grid ── */}
        {Array.from({ length: TOTAL_HOURS + 1 }, (_, i) => {
          const hour = (GRID_START_HOUR + i) % 24
          const x = GRID_LEFT + i * HOUR_WIDTH
          return (
            <g key={i}>
              <line x1={x} y1={ROW_HEIGHT - 5} x2={x} y2={ROW_HEIGHT + 5} stroke="#334155" strokeWidth="1" />
              <line x1={x} y1={20} x2={x} y2={ROW_HEIGHT - 5} stroke="#1e293b" strokeWidth="0.5" strokeDasharray="2,4" />
              <text
                x={x}
                y={ROW_HEIGHT + 18}
                fontSize="9"
                fill="#64748b"
                textAnchor="middle"
                fontFamily="'Exo 2', sans-serif"
              >
                {hour}
              </text>
            </g>
          )
        })}

        {/* ── Hour axis line ── */}
        <line
          x1={GRID_LEFT}
          y1={ROW_HEIGHT}
          x2={GRID_LEFT + GRID_WIDTH}
          y2={ROW_HEIGHT}
          stroke="#334155"
          strokeWidth="1"
        />

        {/* ── Timeline blocks ── */}
        {blocks.map((block, i) => {
          const x1 = minToGridX(block.start)
          const x2 = minToGridX(block.end)
          const w = x2 - x1
          const style = blockStyle(block.type)

          if (w < 1 && !style.label) return null

          return (
            <g key={i}>
              {/* Bar */}
              {style.dash ? (
                <line
                  x1={x1}
                  y1={BAR_Y + BAR_HEIGHT / 2}
                  x2={x2}
                  y2={BAR_Y + BAR_HEIGHT / 2}
                  stroke={style.stroke}
                  strokeWidth="2"
                  strokeDasharray="4,3"
                />
              ) : (
                <rect
                  x={x1}
                  y={BAR_Y}
                  width={Math.max(w, 2)}
                  height={BAR_HEIGHT}
                  fill={style.fill}
                  rx="1"
                />
              )}

              {/* Vertical label above bar (train name + station) */}
              {style.label && w > 8 && (
                <g transform={`translate(${x1 + w / 2}, ${BAR_Y - 4}) rotate(-90)`}>
                  <text
                    fontSize="9"
                    fontWeight="700"
                    fill={block.type === "meal" ? "#94A3B8" : "#F1F5F9"}
                    textAnchor="start"
                    fontFamily="'Exo 2', sans-serif"
                  >
                    {block.type === "meal" ? "REFEZ" : block.label}
                  </text>
                  {block.to_station && block.type === "train" && (
                    <text
                      y="10"
                      fontSize="8"
                      fill="#94A3B8"
                      textAnchor="start"
                      fontFamily="'Exo 2', sans-serif"
                    >
                      {block.to_station.length > 6
                        ? block.to_station.slice(0, 6)
                        : block.to_station}
                    </text>
                  )}
                </g>
              )}

              {/* Duration below bar */}
              {block.duration > 0 && w > 15 && (
                <text
                  x={x1 + w / 2}
                  y={BAR_Y + BAR_HEIGHT + 12}
                  fontSize="8"
                  fill="#64748b"
                  textAnchor="middle"
                  fontFamily="'Exo 2', sans-serif"
                >
                  {block.duration}
                </text>
              )}
            </g>
          )
        })}

        {/* ── Right totals ── */}
        {(() => {
          const rx = GRID_LEFT + GRID_WIDTH + 15
          const items = [
            { label: "Lav", value: prestazione || "" },
            { label: "Cct", value: condotta || "" },
            { label: "Km", value: km !== undefined ? String(km) : "" },
            { label: "Not", value: notturno ? "si" : "no" },
            { label: "Rip", value: riposo || "" },
          ]
          return items.map((item, i) => (
            <g key={item.label}>
              <text
                x={rx + i * 32}
                y={30}
                fontSize="9"
                fontWeight="600"
                fill="#64748b"
                textAnchor="middle"
                fontFamily="'Exo 2', sans-serif"
              >
                {item.label}
              </text>
              <text
                x={rx + i * 32}
                y={50}
                fontSize="10"
                fontWeight="700"
                fill={item.label === "Not" && notturno ? "#F59E0B" : "#F1F5F9"}
                textAnchor="middle"
                fontFamily="'Exo 2', sans-serif"
              >
                {item.value || "—"}
              </text>
            </g>
          ))
        })()}
      </svg>
    </div>
  )
}

/**
 * Wrapper che converte i dati di validazione nel formato Gantt.
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
