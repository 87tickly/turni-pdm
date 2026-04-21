/**
 * AutoBuilderGantt — visualizzazione orizzontale (Gantt-like) dei turni
 * generati dall'auto-builder.
 *
 * Input: lista TrainSegment[] del giorno + presentation/end time.
 * Output: barra temporale con blocchi colorati per ogni treno + spazi
 * vuoti per attese. I segmenti deadhead (rientro in vettura) sono
 * resi tratteggiati per distinguerli dai treni in condotta.
 */

import { Train } from "lucide-react"
import type { TrainSegment } from "@/lib/api"

interface Props {
  segments: TrainSegment[]
  presentationTime?: string
  endTime?: string
  mealStart?: string
  mealEnd?: string
}

const PX_PER_HOUR = 64
const ROW_HEIGHT = 36

function timeToMin(t: string): number {
  if (!t) return 0
  const [h, m] = t.split(":").map(Number)
  return (h || 0) * 60 + (m || 0)
}

function fmtTime(min: number): string {
  const m = ((min % 1440) + 1440) % 1440
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`
}

export function AutoBuilderGantt({
  segments,
  presentationTime,
  endTime,
  mealStart,
  mealEnd,
}: Props) {
  if (!segments || segments.length === 0) return null

  // Calcolo span temporale: presentation -> end (con margine)
  let startMin = presentationTime
    ? timeToMin(presentationTime)
    : timeToMin(segments[0].dep_time)
  let endMin = endTime
    ? timeToMin(endTime)
    : timeToMin(segments[segments.length - 1].arr_time)

  // Gestione overnight
  if (endMin < startMin) endMin += 1440

  // Snap a ora intera (start arrotondato giu', end arrotondato su)
  const startHour = Math.floor(startMin / 60)
  const endHour = Math.ceil(endMin / 60)
  const totalHours = endHour - startHour
  const totalWidth = totalHours * PX_PER_HOUR
  const baseMin = startHour * 60

  function minToX(m: number): number {
    let mm = m
    if (mm < startMin - 60) mm += 1440 // overnight wrap
    return ((mm - baseMin) / 60) * PX_PER_HOUR
  }

  const hourTicks: number[] = []
  for (let h = startHour; h <= endHour; h++) hourTicks.push(h)

  return (
    <div
      className="overflow-x-auto"
      style={{
        backgroundColor: "var(--color-surface-container-low)",
        borderRadius: "8px",
        padding: "8px 4px 8px 4px",
      }}
    >
      <div style={{ position: "relative", width: totalWidth, minHeight: 90 }}>
        {/* Asse orario (top) */}
        <div style={{ position: "relative", height: 18, marginBottom: 6 }}>
          {hourTicks.map((h) => (
            <div
              key={h}
              style={{
                position: "absolute",
                left: minToX(h * 60),
                top: 0,
                height: "100%",
                fontFamily: "var(--font-mono)",
                fontSize: 10,
                color: "var(--color-on-surface-quiet)",
                transform: "translateX(-50%)",
                fontWeight: 600,
              }}
            >
              {String(h % 24).padStart(2, "0")}
            </div>
          ))}
        </div>

        {/* Griglia oraria (linee verticali) */}
        <div
          style={{
            position: "absolute",
            top: 24,
            left: 0,
            right: 0,
            height: ROW_HEIGHT,
          }}
        >
          {hourTicks.map((h) => (
            <div
              key={h}
              style={{
                position: "absolute",
                left: minToX(h * 60),
                top: 0,
                width: 1,
                height: "100%",
                backgroundColor: "var(--color-ghost)",
              }}
            />
          ))}
        </div>

        {/* Banda presentazione/fine (bracket sottile) */}
        {presentationTime && endTime && (
          <div
            style={{
              position: "absolute",
              top: 24,
              left: minToX(timeToMin(presentationTime)),
              width:
                minToX(
                  timeToMin(endTime) < timeToMin(presentationTime)
                    ? timeToMin(endTime) + 1440
                    : timeToMin(endTime),
                ) - minToX(timeToMin(presentationTime)),
              height: ROW_HEIGHT,
              backgroundColor: "var(--color-surface-container-lowest)",
              border: "1px dashed var(--color-on-surface-quiet)",
              borderRadius: 4,
              opacity: 0.4,
            }}
          />
        )}

        {/* Banda refezione (giallo trasparente) */}
        {mealStart && mealEnd && (
          <div
            style={{
              position: "absolute",
              top: 24,
              left: minToX(timeToMin(mealStart)),
              width:
                minToX(timeToMin(mealEnd)) - minToX(timeToMin(mealStart)),
              height: ROW_HEIGHT,
              backgroundColor: "rgba(234, 179, 8, 0.18)",
              border: "1px solid rgba(234, 179, 8, 0.4)",
              borderRadius: 4,
              zIndex: 1,
            }}
            title={`Refezione ${mealStart}-${mealEnd}`}
          />
        )}

        {/* Blocchi treno */}
        {segments.map((seg, i) => {
          const dep = timeToMin(seg.dep_time)
          let arr = timeToMin(seg.arr_time)
          if (arr < dep) arr += 1440
          const x = minToX(dep)
          const w = ((arr - dep) / 60) * PX_PER_HOUR
          const isDh = seg.is_deadhead
          return (
            <div
              key={`${seg.train_id}-${i}`}
              title={`${isDh ? "[IN VETTURA] " : ""}${seg.train_id} ${seg.from_station}(${seg.dep_time})→${seg.to_station}(${seg.arr_time})`}
              style={{
                position: "absolute",
                top: 24,
                left: x,
                width: Math.max(w, 6),
                height: ROW_HEIGHT,
                backgroundColor: isDh
                  ? "transparent"
                  : "var(--color-brand)",
                border: isDh
                  ? "2px dashed var(--color-on-surface-muted)"
                  : "none",
                borderRadius: 4,
                color: isDh
                  ? "var(--color-on-surface-strong)"
                  : "white",
                display: "flex",
                alignItems: "center",
                gap: 4,
                padding: "0 6px",
                fontSize: 10.5,
                fontFamily: "var(--font-mono)",
                fontWeight: 600,
                overflow: "hidden",
                whiteSpace: "nowrap",
                zIndex: 2,
                cursor: "default",
              }}
            >
              <Train size={10} style={{ flexShrink: 0 }} />
              <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>
                {seg.train_id}
                {isDh ? " v" : ""}
              </span>
            </div>
          )
        })}

        {/* Stazione iniziale e finale (sotto asse) */}
        <div
          style={{
            position: "absolute",
            top: 24 + ROW_HEIGHT + 4,
            left: minToX(timeToMin(segments[0].dep_time)),
            fontSize: 9.5,
            fontFamily: "var(--font-mono)",
            color: "var(--color-on-surface-muted)",
            transform: "translateX(0)",
          }}
        >
          {segments[0].from_station}
        </div>
        <div
          style={{
            position: "absolute",
            top: 24 + ROW_HEIGHT + 4,
            left: minToX(
              timeToMin(segments[segments.length - 1].arr_time) <
                timeToMin(segments[0].dep_time)
                ? timeToMin(segments[segments.length - 1].arr_time) + 1440
                : timeToMin(segments[segments.length - 1].arr_time),
            ),
            fontSize: 9.5,
            fontFamily: "var(--font-mono)",
            color: "var(--color-on-surface-muted)",
            transform: "translateX(-100%)",
          }}
        >
          {segments[segments.length - 1].to_station}
        </div>

        {/* Footer riga: timestamps */}
        {presentationTime && (
          <div
            style={{
              position: "absolute",
              top: 24 + ROW_HEIGHT + 18,
              left: minToX(timeToMin(presentationTime)),
              fontSize: 9.5,
              fontFamily: "var(--font-mono)",
              color: "var(--color-on-surface-quiet)",
            }}
          >
            ⊢ {presentationTime}
          </div>
        )}
        {endTime && (
          <div
            style={{
              position: "absolute",
              top: 24 + ROW_HEIGHT + 18,
              left: minToX(
                timeToMin(endTime) < timeToMin(presentationTime || "00:00")
                  ? timeToMin(endTime) + 1440
                  : timeToMin(endTime),
              ),
              fontSize: 9.5,
              fontFamily: "var(--font-mono)",
              color: "var(--color-on-surface-quiet)",
              transform: "translateX(-100%)",
            }}
          >
            {endTime} ⊣
          </div>
        )}
      </div>
    </div>
  )
}

// Helper per evitare warning "imported but unused"
export const _fmtTime = fmtTime
