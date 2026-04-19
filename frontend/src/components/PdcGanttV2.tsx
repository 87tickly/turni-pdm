/**
 * PdcGanttV2 — Gantt PdC riprogettato (stile mockup gantt-ideal-v5).
 *
 * Design:
 *  - Chip-card blu indigo per i treni (numero + destinazione dentro)
 *  - Blocchi secondari (vettura/refez/CVp/CVa) con label orizzontali
 *    su 3 livelli Y (stagger anti-collisione) collegate da "zampe"
 *  - Stazioni capolinea orizzontali ai bordi del cluster
 *  - Asse 3→24→1→2→3 a 52 px/h
 *
 * Interazioni:
 *  - hover su blocco → tooltip informativo
 *  - click su blocco → onBlockClick + evidenziazione selected
 *  - click su timeline vuota → onTimelineClick
 *  - drag sul centro di un blocco → sposta l'intero blocco (preserva durata).
 *    Per treni: trascina insieme CVp/CVa agganciati.
 *  - drag sui bordi di un treno (6px) → resize start/end; il CVp/CVa
 *    agganciato segue il nuovo estremo.
 *  - CVp/CVa singoli NON si muovono da soli: il drag viene reindirizzato
 *    al treno padrone.
 *  - threshold 4px prima di avviare drag (niente drag accidentale al click)
 *  - snap 5 minuti
 *
 * API esterna drop-in compatibile con PdcGantt v1.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import type { PdcBlock } from "@/lib/api"

// ============================================================
// Props
// ============================================================
export type GanttAction =
  | "edit"
  | "move"
  | "duplicate"
  | "link"
  | "warn"
  | "detail"
  | "history"
  | "delete"

// Payload trasferito via HTML5 dataTransfer per drag cross-day
// (MIME "application/x-colazione-block")
export interface CrossDayDragPayload {
  ganttId: string
  block: PdcBlock
  index: number
  /** CVp/CVa agganciati al treno che si stanno spostando insieme */
  linkedCvp?: PdcBlock
  linkedCva?: PdcBlock
}

interface PdcGanttV2Props {
  blocks: PdcBlock[]
  startTime?: string
  endTime?: string
  onBlockClick?: (block: PdcBlock, index: number) => void
  onTimelineClick?: (hour: number, minute: number) => void
  onBlocksChange?: (
    changes: Record<number, { start_time?: string; end_time?: string }>
  ) => void
  /**
   * Click su una delle 8 icone dell'action bar contestuale che appare
   * al click su una chip selezionata.
   */
  onAction?: (action: GanttAction, block: PdcBlock, index: number) => void
  /**
   * Identificativo univoco del Gantt (es. "turno-42-day-3-LMXGVSD").
   * Serve al drag cross-day per sapere da dove parte e dove arriva.
   * Se omesso, il drag cross-day e' disabilitato.
   */
  ganttId?: string
  /**
   * Un blocco dal Gantt e' stato rilasciato in questo Gantt.
   * Il componente rimuove il blocco dal source (chiamando il parent),
   * e il parent inserisce il blocco nel target. Questi due passi sono
   * gestiti dal parent che ha la vista globale dei turni/giornate.
   */
  onCrossDayDrop?: (
    payload: CrossDayDragPayload,
    targetGanttId: string,
    dropHourMinute: { hour: number; minute: number },
  ) => void
  /**
   * Chiamato quando inizia un drag cross-day (HTML5 DnD). Utile per il
   * parent per preparare lo stato "in spostamento" (source turn/day/idx).
   */
  onCrossDayDragStart?: (payload: CrossDayDragPayload) => void
  /**
   * Chiamato quando l'utente rimuove (via drag uscente) un blocco dal
   * Gantt sorgente. Il parent deve rimuovere il blocco dai suoi blocks.
   * Non e' necessario se onCrossDayDragStart + onCrossDayDrop gestiscono
   * gia' il move atomicamente a livello parent (come PdcDepotPage).
   */
  onCrossDayRemove?: (index: number, withLinkedCvs: boolean) => void
  label?: string
  depot?: string
  height?: number
  snapMinutes?: number
  dragThresholdPx?: number
  debug?: boolean
  /**
   * Nasconde l'action bar 8-icone che appare sopra il blocco selezionato.
   * Utile in PdcPage (sola lettura): l'unica azione sensata e' "detail",
   * raggiunta direttamente via single-click → drawer. In PdcBuilderPage e
   * PdcDepotPage l'action bar resta visibile (edit/move/duplicate/delete).
   */
  hideActionBar?: boolean
}

// ============================================================
// Design system colors per block type
// (mapping: train=brand, vuota/coach=dashed neutral, meal=success,
//  scomp=warning, cvp/cva=viola — vedi HANDOFF §01 Gantt track)
// ============================================================
const DS = {
  brandSolid:    "#0062CC",  // train base
  brandDeep:     "#004B9F",  // train gradient end
  brandRing:     "#0062CC",  // selected ring (brand)
  selectionDot:  "#22C55E",  // kinetic dot (selected halo)
  mealBg:        "#DCFCE7",  // success-container soft (rgba 34,197,94,0.20 ~ flat)
  mealFg:        "#15803D",  // success deep
  mealStroke:    "#16A34A",  // success
  scompBg:       "#FFEDD5",  // warning-container soft
  scompFg:       "#9A3412",  // warning deep
  scompStroke:   "#EA580C",  // warning
  vettBg:        "rgba(15,23,42,0.05)",  // vuota neutral fill
  vettFg:        "#5A6478",  // on-surface-muted
  vettStroke:    "#94A3B8",  // muted gray
  cvViola:       "#6D28D9",  // CVp/CVa viola (preservato)
}

// ============================================================
// Scala temporale
// ============================================================
const ORIGIN_HOUR = 3
const SPAN_HOURS = 24
const PX_PER_HOUR = 52
const ORIGIN_X = 30
const AXIS_WIDTH = SPAN_HOURS * PX_PER_HOUR
const TOTAL_WIDTH = ORIGIN_X + AXIS_WIDTH + ORIGIN_X

// Y layout (aggiornato per blocchi piu alti secondo design Stitch)
const AXIS_Y = 130
const BLOCK_Y = 88   // era 95, alzato per accogliere BLOCK_H=34
const BLOCK_H = 34   // era 22 — Stitch mostra blocchi alti con tag+meta stacked
const CHIP_Y_A = 72  // era 78 — rialzato di 6px per non sovrapporsi ai blocchi piu alti
const CHIP_Y_B = 48
const CHIP_Y_C = 24
const MINUTES_MAIN_Y = 160
const MINUTES_AUX_Y = 175  // riga accessori (minuti PDF ausiliari: 5/27/10)

const TICK_HOURS = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 1, 2, 3]
const MAJOR_TICKS = new Set([3, 12, 24])

// Bordo resize (in px del viewBox)
const RESIZE_HANDLE_PX = 6

function hhmmToMinutesRel(hhmm: string): number | null {
  if (!hhmm || !/^\d{1,2}:\d{2}$/.test(hhmm)) return null
  const [h, m] = hhmm.split(":").map(Number)
  let hourAdj = h
  if (h < ORIGIN_HOUR) hourAdj = h + 24
  return (hourAdj - ORIGIN_HOUR) * 60 + m
}

function minutesRelToHhmm(minRel: number): string {
  const abs = (ORIGIN_HOUR * 60 + Math.max(0, Math.min(minRel, SPAN_HOURS * 60))) % (24 * 60)
  const h = Math.floor(abs / 60)
  const m = abs % 60
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}`
}

function minToX(minRel: number): number {
  return ORIGIN_X + (minRel / 60) * PX_PER_HOUR
}

function minuteOnly(hhmm: string): string {
  if (!hhmm || !/^\d{1,2}:\d{2}$/.test(hhmm)) return ""
  return hhmm.slice(-2)
}

// ============================================================
// Helpers gruppo CVp/CVa (copiati da v1, stessa logica)
// ============================================================
function getLinkedCVs(blocks: PdcBlock[], trainIdx: number): {
  cvPrev: number | null
  cvNext: number | null
} {
  let cvPrev: number | null = null
  let cvNext: number | null = null
  if (blocks[trainIdx]?.block_type !== "train") return { cvPrev, cvNext }
  const prev = blocks[trainIdx - 1]
  if (prev && prev.block_type === "cv_partenza") cvPrev = trainIdx - 1
  const next = blocks[trainIdx + 1]
  if (next && next.block_type === "cv_arrivo") cvNext = trainIdx + 1
  return { cvPrev, cvNext }
}

function getParentTrainIndex(blocks: PdcBlock[], cvIdx: number): number | null {
  const cv = blocks[cvIdx]
  if (!cv) return null
  if (cv.block_type === "cv_partenza") {
    const next = blocks[cvIdx + 1]
    if (next && next.block_type === "train") return cvIdx + 1
  }
  if (cv.block_type === "cv_arrivo") {
    const prev = blocks[cvIdx - 1]
    if (prev && prev.block_type === "train") return cvIdx - 1
  }
  return null
}

// ============================================================
// Stagger Y per chip-label
// ============================================================
function computeChipYs(blocks: PdcBlock[], approxLabelWidth = 60): number[] {
  const ys: number[] = []
  const usedRanges: { y: number; x0: number; x1: number }[] = []
  const levels = [CHIP_Y_A, CHIP_Y_B, CHIP_Y_C]

  for (let i = 0; i < blocks.length; i++) {
    const b = blocks[i]
    const m = hhmmToMinutesRel(b.start_time || "")
    if (m === null || b.block_type === "train") {
      ys.push(CHIP_Y_A)
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
    if (assignedY === -1) assignedY = CHIP_Y_C
    usedRanges.push({ y: assignedY, x0, x1 })
    ys.push(assignedY)
  }
  return ys
}

// ============================================================
// DragState
// ============================================================
type DragState = {
  groupIndices: number[]
  kind: "move" | "resize-start" | "resize-end"
  initial: Record<number, { sm: number; em: number }>
  initialMouseX: number
  active: boolean
}

// ============================================================
// Tooltip overlay
// ============================================================
interface TooltipData {
  x: number
  y: number
  block: PdcBlock
}

function formatBlockLabel(b: PdcBlock): string {
  switch (b.block_type) {
    case "train": return `Treno ${b.train_id}`
    case "coach_transfer": return `Vettura ${b.vettura_id || b.train_id}`
    case "cv_partenza": return `CVp ${b.train_id}`
    case "cv_arrivo": return `CVa ${b.train_id}`
    case "meal": return "Refezione"
    case "scomp": return "S.COMP"
    case "available": return "Disponibile"
    default: return b.block_type
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
// Config delle 8 azioni contestuali (stesso ordine del mockup v5)
const ACTION_DEFS: { act: GanttAction; icon: string; title: string; danger?: boolean; warn?: boolean; separatorAfter?: boolean }[] = [
  { act: "edit",      icon: "✎", title: "Modifica blocco", separatorAfter: false },
  { act: "move",      icon: "↔", title: "Sposta (drag temporale o inter-turno)" },
  { act: "duplicate", icon: "⧉", title: "Duplica blocco", separatorAfter: true },
  { act: "link",      icon: "🔗", title: "Collega al giro materiale" },
  { act: "warn",      icon: "⚠", title: "Verifica discrepanze ARTURO Live", warn: true, separatorAfter: true },
  { act: "detail",    icon: "↗", title: "Apri dettaglio treno" },
  { act: "history",   icon: "⧗", title: "Storico ritardi (ultimi 30 giorni)", separatorAfter: true },
  { act: "delete",    icon: "×", title: "Elimina blocco", danger: true },
]

const CROSS_DAY_MIME = "application/x-colazione-block"

export function PdcGanttV2({
  blocks: rawBlocks,
  onBlockClick,
  onTimelineClick,
  onBlocksChange,
  onAction,
  ganttId,
  onCrossDayDrop,
  onCrossDayDragStart,
  onCrossDayRemove,
  height = 200,
  snapMinutes = 5,
  dragThresholdPx = 4,
  debug = false,
  hideActionBar = false,
}: PdcGanttV2Props) {
  const crossDayEnabled = !!ganttId && (!!onCrossDayDrop || !!onCrossDayRemove || !!onCrossDayDragStart)
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null)
  const [tooltip, setTooltip] = useState<TooltipData | null>(null)
  const [overrides, setOverrides] = useState<
    Record<number, { start_time?: string; end_time?: string }>
  >({})
  const [dragState, setDragState] = useState<DragState | null>(null)
  const didDragRef = useRef(false)

  const svgRef = useRef<SVGSVGElement | null>(null)
  const wrapperRef = useRef<HTMLDivElement>(null)

  // Applica overrides ottimistici ai blocchi durante drag
  const blocks = useMemo(
    () => rawBlocks.map((b, i) => ({ ...b, ...(overrides[i] || {}) })),
    [rawBlocks, overrides],
  )

  const isAvailable = blocks.length === 0 ||
    (blocks.length === 1 && blocks[0].block_type === "available")

  const chipYs = useMemo(() => computeChipYs(blocks), [blocks])

  const leftStation = useMemo(() => {
    for (const b of blocks) if (b.from_station) return b.from_station
    return ""
  }, [blocks])
  const rightStation = useMemo(() => {
    for (let i = blocks.length - 1; i >= 0; i--) {
      if (blocks[i].to_station) return blocks[i].to_station
    }
    return leftStation
  }, [blocks, leftStation])

  // Client X → viewBox X
  const clientXToSvgX = useCallback((clientX: number): number => {
    const svg = svgRef.current
    if (!svg) return 0
    const rect = svg.getBoundingClientRect()
    return ((clientX - rect.left) / rect.width) * TOTAL_WIDTH
  }, [])

  // viewBox X → minuti rel
  const svgXToMinRel = useCallback((svgX: number): number => {
    return ((svgX - ORIGIN_X) / PX_PER_HOUR) * 60
  }, [])

  // ── Drag start ──────────────────────────────────────────────
  const startDrag = useCallback(
    (e: React.MouseEvent, index: number, kind: DragState["kind"]) => {
      if (!onBlocksChange) return
      e.stopPropagation()
      // NB: NON chiamo e.preventDefault() qui, altrimenti l'HTML5 drag
      // (draggable=true sulla chip) non riesce a partire. La selezione
      // di testo durante il drag intra-Gantt e' evitata dalla classe
      // tailwind "select-none" sul <svg>.
      didDragRef.current = false

      // CVp/CVa: reindirizza al treno padrone
      const srcBlock = blocks[index]
      let mainIndex = index
      if (srcBlock.block_type === "cv_partenza" || srcBlock.block_type === "cv_arrivo") {
        const parent = getParentTrainIndex(blocks, index)
        if (parent !== null) mainIndex = parent
      }

      const groupIndices: number[] = [mainIndex]
      if (blocks[mainIndex].block_type === "train") {
        const { cvPrev, cvNext } = getLinkedCVs(blocks, mainIndex)
        if (cvPrev !== null) groupIndices.unshift(cvPrev)
        if (cvNext !== null) groupIndices.push(cvNext)
      }

      const initial: Record<number, { sm: number; em: number }> = {}
      for (const gi of groupIndices) {
        const b = blocks[gi]
        const sm = hhmmToMinutesRel(b.start_time)
        const em = hhmmToMinutesRel(b.end_time)
        if (sm === null) continue
        initial[gi] = { sm, em: em !== null && em > sm ? em : sm }
      }

      setDragState({
        groupIndices,
        kind,
        initial,
        initialMouseX: e.clientX,
        active: false,
      })
    },
    [blocks, onBlocksChange],
  )

  // ── Drag move/up globali ────────────────────────────────────
  useEffect(() => {
    if (!dragState) return

    const handleMove = (e: MouseEvent) => {
      const deltaPx = Math.abs(e.clientX - dragState.initialMouseX)
      if (!dragState.active && deltaPx < dragThresholdPx) return

      if (!dragState.active) {
        setDragState((s) => (s ? { ...s, active: true } : s))
        didDragRef.current = true
      }

      const dxSvg =
        clientXToSvgX(e.clientX) - clientXToSvgX(dragState.initialMouseX)
      const deltaMinRaw = (dxSvg / PX_PER_HOUR) * 60
      const deltaMin = Math.round(deltaMinRaw / snapMinutes) * snapMinutes
      const maxMin = SPAN_HOURS * 60

      const nextOverrides: Record<number, { start_time: string; end_time: string }> = {}

      if (dragState.kind === "move") {
        for (const gi of dragState.groupIndices) {
          const init = dragState.initial[gi]
          if (!init) continue
          let newSm = Math.max(0, Math.min(init.sm + deltaMin, maxMin))
          let newEm = Math.max(0, Math.min(init.em + deltaMin, maxMin))
          nextOverrides[gi] = {
            start_time: minutesRelToHhmm(newSm),
            end_time: minutesRelToHhmm(newEm),
          }
        }
      } else if (dragState.kind === "resize-start") {
        const trainIdx = dragState.groupIndices.find(
          (gi) => blocks[gi].block_type === "train",
        )
        if (trainIdx !== undefined) {
          const init = dragState.initial[trainIdx]
          if (init) {
            let newSm = init.sm + deltaMin
            if (newSm > init.em - snapMinutes) newSm = init.em - snapMinutes
            newSm = Math.max(0, newSm)
            nextOverrides[trainIdx] = {
              start_time: minutesRelToHhmm(newSm),
              end_time: minutesRelToHhmm(init.em),
            }
            const cvpIdx = dragState.groupIndices.find(
              (gi) => blocks[gi].block_type === "cv_partenza",
            )
            if (cvpIdx !== undefined) {
              nextOverrides[cvpIdx] = {
                start_time: minutesRelToHhmm(newSm),
                end_time: minutesRelToHhmm(newSm),
              }
            }
          }
        }
      } else if (dragState.kind === "resize-end") {
        const trainIdx = dragState.groupIndices.find(
          (gi) => blocks[gi].block_type === "train",
        )
        if (trainIdx !== undefined) {
          const init = dragState.initial[trainIdx]
          if (init) {
            let newEm = init.em + deltaMin
            if (newEm < init.sm + snapMinutes) newEm = init.sm + snapMinutes
            newEm = Math.min(maxMin, newEm)
            nextOverrides[trainIdx] = {
              start_time: minutesRelToHhmm(init.sm),
              end_time: minutesRelToHhmm(newEm),
            }
            const cvaIdx = dragState.groupIndices.find(
              (gi) => blocks[gi].block_type === "cv_arrivo",
            )
            if (cvaIdx !== undefined) {
              nextOverrides[cvaIdx] = {
                start_time: minutesRelToHhmm(newEm),
                end_time: minutesRelToHhmm(newEm),
              }
            }
          }
        }
      }

      setOverrides(nextOverrides)
    }

    const handleUp = () => {
      if (!onBlocksChange) return
      if (dragState.active && Object.keys(overrides).length > 0) {
        onBlocksChange(overrides)
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
  }, [dragState, overrides, clientXToSvgX, snapMinutes, dragThresholdPx, blocks, onBlocksChange])

  // ── Click handlers ──────────────────────────────────────────
  const handleTimelineBgClick = useCallback(
    (e: React.MouseEvent<SVGElement>) => {
      if (!onTimelineClick) return
      if (didDragRef.current) return
      const svgX = clientXToSvgX(e.clientX)
      const minRel = svgXToMinRel(svgX)
      const clamped = Math.max(0, Math.min(minRel, SPAN_HOURS * 60))
      const abs = (ORIGIN_HOUR * 60 + clamped) % (24 * 60)
      const hour = Math.floor(abs / 60)
      const minute = Math.round(abs % 60)
      onTimelineClick(hour, minute)
    },
    [onTimelineClick, clientXToSvgX, svgXToMinRel],
  )

  const handleBlockEnter = useCallback((e: React.MouseEvent, block: PdcBlock) => {
    if (dragState?.active) return
    if (!wrapperRef.current) return
    const rect = wrapperRef.current.getBoundingClientRect()
    setTooltip({ x: e.clientX - rect.left, y: e.clientY - rect.top, block })
  }, [dragState])

  const handleBlockMove = useCallback((e: React.MouseEvent) => {
    if (dragState?.active) return
    if (!wrapperRef.current) return
    const rect = wrapperRef.current.getBoundingClientRect()
    setTooltip((prev) =>
      prev ? { ...prev, x: e.clientX - rect.left, y: e.clientY - rect.top } : null,
    )
  }, [dragState])

  const handleBlockLeave = useCallback(() => setTooltip(null), [])

  const handleBlockClick = useCallback(
    (e: React.MouseEvent, block: PdcBlock, idx: number) => {
      e.stopPropagation()
      if (didDragRef.current) {
        didDragRef.current = false
        return
      }
      setSelectedIdx(idx)
      if (onBlockClick) onBlockClick(block, idx)
    },
    [onBlockClick],
  )

  // Click fuori dallo SVG / Esc → deseleziona
  useEffect(() => {
    if (selectedIdx === null) return
    const onDocClick = (e: MouseEvent) => {
      const svg = svgRef.current
      if (!svg) return
      if (!svg.contains(e.target as Node)) setSelectedIdx(null)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelectedIdx(null)
    }
    document.addEventListener("mousedown", onDocClick)
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("mousedown", onDocClick)
      document.removeEventListener("keydown", onKey)
    }
  }, [selectedIdx])

  const fireAction = useCallback(
    (act: GanttAction) => {
      if (selectedIdx === null) {
        console.warn("[PdcGanttV2] fireAction chiamato senza selezione")
        return
      }
      const block = blocks[selectedIdx]
      if (!block) {
        console.warn("[PdcGanttV2] fireAction: blocco non trovato per idx", selectedIdx)
        return
      }
      console.log("[PdcGanttV2] fireAction", act, "block:", block, "hasOnAction:", !!onAction)
      if (onAction) {
        onAction(act, block, selectedIdx)
      }
      // chiudi action bar dopo l'azione (il toast e' renderizzato dal
      // parent fuori dall'SVG, resta visibile anche dopo deselezione)
      setSelectedIdx(null)
    },
    [selectedIdx, blocks, onAction],
  )

  // (Legacy handleTrainMouseDown sostituito dal pattern foreignObject:
  // 3 div HTML separati nel chip-card del treno gestiscono direttamente
  // resize-start, resize-end e move — niente piu' calcolo X locale.)

  // ── Cross-day drag (HTML5 DnD) ─────────────────────────────────
  // Un blocco con draggable=true puo' essere trascinato fuori dal
  // proprio Gantt e rilasciato in un altro Gantt della stessa pagina.

  const handleCrossDragStart = useCallback(
    (e: React.DragEvent, idx: number) => {
      if (!crossDayEnabled || !ganttId) return
      // Cancella drag interno attivo (onMouseDown lo ha potuto avviare)
      setDragState(null)
      setOverrides({})

      const block = blocks[idx]
      if (!block) return
      const linked = block.block_type === "train"
        ? getLinkedCVs(blocks, idx)
        : { cvPrev: null, cvNext: null }
      const payload: CrossDayDragPayload = {
        ganttId,
        block,
        index: idx,
        linkedCvp: linked.cvPrev !== null ? blocks[linked.cvPrev] : undefined,
        linkedCva: linked.cvNext !== null ? blocks[linked.cvNext] : undefined,
      }
      try {
        e.dataTransfer.effectAllowed = "move"
        e.dataTransfer.setData(CROSS_DAY_MIME, JSON.stringify(payload))
        // Fallback text/plain (alcuni browser lo richiedono per iniziare il drag)
        e.dataTransfer.setData("text/plain", `${block.block_type}:${block.train_id || block.vettura_id || ""}`)
      } catch {
        // no-op
      }
      if (onCrossDayDragStart) onCrossDayDragStart(payload)
    },
    [blocks, crossDayEnabled, ganttId, onCrossDayDragStart],
  )

  const handleCrossDragEnd = useCallback((e: React.DragEvent, idx: number) => {
    // Il browser, durante HTML5 drag, NON emette mouseup → il mio
    // dragState interno non viene ripulito dal listener mouseup. Lo faccio qui.
    setDragState(null)
    setOverrides({})
    didDragRef.current = false

    // Se il drop e' riuscito in un altro Gantt (dropEffect === "move"),
    // rimuovi il blocco (con CVp/CVa agganciati se treno) da questo Gantt.
    if (!crossDayEnabled) return
    if (e.dataTransfer.dropEffect === "move" && onCrossDayRemove) {
      const b = blocks[idx]
      const withLinkedCvs = b?.block_type === "train"
      onCrossDayRemove(idx, withLinkedCvs)
    }
  }, [blocks, crossDayEnabled, onCrossDayRemove])

  const handleSvgDragOver = useCallback((e: React.DragEvent) => {
    if (!crossDayEnabled || !onCrossDayDrop) return
    // Accetta il drop solo se il payload ha il MIME giusto
    if (Array.from(e.dataTransfer.types).includes(CROSS_DAY_MIME)) {
      e.preventDefault() // REQUIRED per permettere drop
      e.dataTransfer.dropEffect = "move"
    }
  }, [crossDayEnabled, onCrossDayDrop])

  const handleSvgDrop = useCallback((e: React.DragEvent) => {
    if (!crossDayEnabled || !onCrossDayDrop || !ganttId) return
    const raw = e.dataTransfer.getData(CROSS_DAY_MIME)
    if (!raw) return
    e.preventDefault()
    let payload: CrossDayDragPayload
    try { payload = JSON.parse(raw) } catch { return }

    // Drop nello stesso Gantt d'origine → ignora (il drag interno
    // gestisce gia' move temporale)
    if (payload.ganttId === ganttId) return

    // Calcola l'ora al punto di drop
    const svgX = clientXToSvgX(e.clientX)
    const minRel = svgXToMinRel(svgX)
    const clamped = Math.max(0, Math.min(minRel, SPAN_HOURS * 60))
    // Snap al granulo di minuti
    const snapped = Math.round(clamped / snapMinutes) * snapMinutes
    const abs = (ORIGIN_HOUR * 60 + snapped) % (24 * 60)
    const hour = Math.floor(abs / 60)
    const minute = Math.round(abs % 60)

    onCrossDayDrop(payload, ganttId, { hour, minute })
  }, [crossDayEnabled, onCrossDayDrop, ganttId, clientXToSvgX, svgXToMinRel, snapMinutes])

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

  const startMinsForEdge = blocks
    .map((b) => hhmmToMinutesRel(b.start_time || ""))
    .filter((v): v is number => v !== null)
  const endMinsForEdge = blocks
    .map((b) => hhmmToMinutesRel(b.end_time || b.start_time || ""))
    .filter((v): v is number => v !== null)
  const minStart = startMinsForEdge.length ? Math.min(...startMinsForEdge) : 0
  const maxEnd = endMinsForEdge.length ? Math.max(...endMinsForEdge) : 0

  return (
    <div ref={wrapperRef} className="relative" style={{ minHeight: height }}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${TOTAL_WIDTH} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        className="block w-full select-none"
        style={{ overflow: "visible" }}
        onDragOver={crossDayEnabled ? handleSvgDragOver : undefined}
        onDrop={crossDayEnabled ? handleSvgDrop : undefined}
        data-gantt-id={ganttId}
      >
        <defs>
          <linearGradient id="pdcGanttV2-trainGradient" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={DS.brandDeep} />
            <stop offset="100%" stopColor={DS.brandSolid} />
          </linearGradient>
        </defs>

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

        {/* Fascia notte */}
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

        {TICK_HOURS.map((h, i) => {
          const x = ORIGIN_X + i * PX_PER_HOUR
          const isMajor = MAJOR_TICKS.has(h) && (i === 0 || i === TICK_HOURS.length - 1 || h === 12 || h === 24)
          const tickH = isMajor ? 10 : 6
          return (
            <g key={i} pointerEvents="none">
              <line
                x1={x} y1={AXIS_Y - tickH / 2}
                x2={x} y2={AXIS_Y + tickH / 2}
                stroke={isMajor ? "#353a42" : "#a1a6ae"}
                strokeWidth={isMajor ? 1.2 : 1}
              />
              <text
                x={x} y={AXIS_Y + 18}
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

        {leftStation && Number.isFinite(minStart) && (
          <text
            x={minToX(minStart) - 10} y={BLOCK_Y + BLOCK_H / 2 + 4}
            textAnchor="end" fontSize={10} fontWeight={600}
            fill="var(--color-on-surface-muted)" letterSpacing="0.04em"
            fontFamily="ui-monospace, Menlo, monospace"
            pointerEvents="none"
          >
            {leftStation.length > 10 ? leftStation.slice(0, 3).toUpperCase() : leftStation}
          </text>
        )}
        {rightStation && Number.isFinite(maxEnd) && (
          <text
            x={minToX(maxEnd) + 10} y={BLOCK_Y + BLOCK_H / 2 + 4}
            textAnchor="start" fontSize={10} fontWeight={600}
            fill="var(--color-on-surface-muted)" letterSpacing="0.04em"
            fontFamily="ui-monospace, Menlo, monospace"
            pointerEvents="none"
          >
            {rightStation.length > 10 ? rightStation.slice(0, 3).toUpperCase() : rightStation}
          </text>
        )}

        {blocks.map((b, idx) => {
          const startMin = hhmmToMinutesRel(b.start_time || "")
          if (startMin === null) return null
          const endMin = hhmmToMinutesRel(b.end_time || b.start_time || "") ?? startMin
          const x = minToX(startMin)
          const x2 = minToX(endMin)
          const w = Math.max(2, x2 - x)
          const isSel = selectedIdx === idx
          const chipY = chipYs[idx]
          const draggable = !!onBlocksChange

          const baseHandlers = {
            onMouseEnter: (e: React.MouseEvent) => handleBlockEnter(e, b),
            onMouseMove: handleBlockMove,
            onMouseLeave: handleBlockLeave,
            onClick: (e: React.MouseEvent) => handleBlockClick(e, b, idx),
          }

          if (b.block_type === "train") {
            // Stitch: tag (train_id) + meta (from-to) stacked dentro al blocco
            const showMeta = w >= 48 && (b.from_station || b.to_station)
            const metaText = (() => {
              if (!b.from_station && !b.to_station) return ""
              const from = (b.from_station || "").slice(0, 2).toUpperCase()
              const to = (b.to_station || "").slice(0, 2).toUpperCase()
              if (from && to) return `${from}-${to}`
              return from || to
            })()
            return (
              <g key={idx}>
                {/* Visual rect (NO listeners → eventi su foreignObject sotto) */}
                <rect
                  x={x} y={BLOCK_Y} width={w} height={BLOCK_H} rx={4}
                  fill="url(#pdcGanttV2-trainGradient)"
                  stroke={isSel ? DS.selectionDot : "rgba(255,255,255,0.18)"}
                  strokeWidth={isSel ? 2 : 0.5}
                  filter={isSel
                    ? "drop-shadow(0 3px 8px rgba(0,75,159,0.45))"
                    : "drop-shadow(0 1px 2px rgba(0,75,159,0.18))"}
                  pointerEvents="none"
                />
                {/* Border-l brand piu scuro (accento verticale Stitch) */}
                <rect
                  x={x} y={BLOCK_Y} width={2.5} height={BLOCK_H} rx={1}
                  fill={DS.brandDeep} pointerEvents="none"
                />
                {/* Highlight top 1/3 per effetto glass */}
                <rect
                  x={x} y={BLOCK_Y} width={w} height={BLOCK_H / 3} rx={4}
                  fill="#ffffff" fillOpacity={0.10} pointerEvents="none"
                />
                {/* Tag (train_id) + meta (from-to) stacked */}
                {showMeta ? (
                  <>
                    <text
                      x={x + w / 2} y={BLOCK_Y + 13}
                      textAnchor="middle"
                      fontFamily="ui-monospace, Menlo, monospace"
                      fontSize={w < 55 ? 9.5 : 10.5} fontWeight={700}
                      fill="#ffffff" pointerEvents="none"
                    >
                      {b.train_id}
                    </text>
                    <text
                      x={x + w / 2} y={BLOCK_Y + 25}
                      textAnchor="middle"
                      fontFamily="ui-monospace, Menlo, monospace"
                      fontSize={8.5} fontWeight={500}
                      fill="rgba(255,255,255,0.82)" pointerEvents="none"
                      letterSpacing="0.05em"
                    >
                      {metaText}
                    </text>
                  </>
                ) : (
                  <text
                    x={x + w / 2} y={BLOCK_Y + BLOCK_H / 2 + 4}
                    textAnchor="middle"
                    fontFamily="ui-monospace, Menlo, monospace"
                    fontSize={w < 30 ? 8.5 : 10} fontWeight={700}
                    fill="#ffffff" pointerEvents="none"
                  >
                    {b.train_id}
                  </text>
                )}
                {b.accessori_maggiorati ? (
                  <circle cx={x - 5} cy={BLOCK_Y + BLOCK_H / 2} r={3.5}
                          fill="#b91c1c" pointerEvents="none" />
                ) : null}

                {/* Overlay HTML: gestisce TUTTI gli eventi.
                    foreignObject e' lo standard per applicare HTML5 DnD
                    a forme SVG. I rect sopra restano per il rendering
                    visuale (pointerEvents=none). */}
                <foreignObject x={x} y={BLOCK_Y} width={w} height={BLOCK_H}>
                  <div
                    // @ts-expect-error xmlns serve per browser SSR
                    xmlns="http://www.w3.org/1999/xhtml"
                    style={{
                      position: "relative",
                      width: "100%",
                      height: "100%",
                    }}
                  >
                    {/* Resize start (sx) */}
                    {draggable && (
                      <div
                        style={{
                          position: "absolute", left: 0, top: 0,
                          width: RESIZE_HANDLE_PX, height: "100%",
                          cursor: "ew-resize",
                        }}
                        onMouseDown={(e) => { e.stopPropagation(); startDrag(e, idx, "resize-start") }}
                      />
                    )}
                    {/* Resize end (dx) */}
                    {draggable && (
                      <div
                        style={{
                          position: "absolute", right: 0, top: 0,
                          width: RESIZE_HANDLE_PX, height: "100%",
                          cursor: "ew-resize",
                        }}
                        onMouseDown={(e) => { e.stopPropagation(); startDrag(e, idx, "resize-end") }}
                      />
                    )}
                    {/* Centro: drag/click/hover. Draggable HTML5 per cross-day. */}
                    <div
                      draggable={crossDayEnabled}
                      style={{
                        position: "absolute",
                        top: 0, bottom: 0,
                        left: draggable ? RESIZE_HANDLE_PX : 0,
                        right: draggable ? RESIZE_HANDLE_PX : 0,
                        cursor: draggable ? "grab" : "pointer",
                      }}
                      onMouseDown={(e) => draggable && startDrag(e, idx, "move")}
                      onMouseEnter={(e) => handleBlockEnter(e, b)}
                      onMouseMove={handleBlockMove}
                      onMouseLeave={handleBlockLeave}
                      onClick={(e) => handleBlockClick(e, b, idx)}
                      onDragStart={crossDayEnabled
                        ? (e) => handleCrossDragStart(e, idx)
                        : undefined}
                      onDragEnd={crossDayEnabled
                        ? (e) => handleCrossDragEnd(e, idx)
                        : undefined}
                    />
                  </div>
                </foreignObject>
                <text x={x} y={MINUTES_MAIN_Y} textAnchor="middle"
                      fontFamily="ui-monospace, Menlo, monospace" fontSize={9.5}
                      fontWeight={700} fill="#0b0d10" pointerEvents="none">
                  {minuteOnly(b.start_time)}
                </text>
                {b.minuti_accessori && (
                  <text x={x} y={MINUTES_AUX_Y} textAnchor="middle"
                        fontFamily="ui-monospace, Menlo, monospace" fontSize={8}
                        fontStyle="italic" fill="#a1a6ae" pointerEvents="none">
                    {b.minuti_accessori}
                  </text>
                )}
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

          if (b.block_type === "coach_transfer") {
            // Stitch "VUOTA": solid slate-200, border-l-2 slate-500, tag centrato
            const vuotaId = b.vettura_id || b.train_id
            return (
              <g key={idx}>
                <rect x={x} y={BLOCK_Y} width={w} height={BLOCK_H} rx={4}
                      fill="#E2E8F0"
                      stroke={isSel ? DS.brandRing : "none"}
                      strokeWidth={isSel ? 1.8 : 0}
                      style={{ cursor: draggable ? "grab" : "pointer" }}
                      {...baseHandlers}
                      onMouseDown={(e) => draggable && startDrag(e, idx, "move")} />
                {/* Border-l slate-500 accento verticale */}
                <rect x={x} y={BLOCK_Y} width={2.5} height={BLOCK_H} rx={1}
                      fill="#64748B" pointerEvents="none" />
                <text x={x + w / 2} y={BLOCK_Y + BLOCK_H / 2 + 4}
                      textAnchor="middle"
                      fontFamily="ui-monospace, Menlo, monospace" fontSize={10}
                      fontWeight={700} fill="#334155" letterSpacing="0.05em"
                      pointerEvents="none">
                  {w >= 55 && vuotaId ? `VUOTA ${vuotaId}` : "VUOTA"}
                </text>
                <text x={x} y={MINUTES_MAIN_Y} textAnchor="middle"
                      fontFamily="ui-monospace, Menlo, monospace" fontSize={9.5}
                      fontWeight={700} fill="#0b0d10" pointerEvents="none">
                  {minuteOnly(b.start_time)}
                </text>
                {b.minuti_accessori && (
                  <text x={x} y={MINUTES_AUX_Y} textAnchor="middle"
                        fontFamily="ui-monospace, Menlo, monospace" fontSize={8}
                        fontStyle="italic" fill="#a1a6ae" pointerEvents="none">
                    {b.minuti_accessori}
                  </text>
                )}
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
            // Stitch: bg success-container (verde soft), tag REFEZ centrato,
            // border-l emerald per accento verticale
            return (
              <g key={idx}>
                <rect x={x} y={BLOCK_Y} width={w} height={BLOCK_H} rx={4}
                      fill={DS.mealBg}
                      stroke={isSel ? DS.brandRing : "none"}
                      strokeWidth={isSel ? 1.8 : 0}
                      style={{ cursor: draggable ? "grab" : "pointer" }}
                      {...baseHandlers}
                      onMouseDown={(e) => draggable && startDrag(e, idx, "move")} />
                {/* Border-l verde accento verticale */}
                <rect x={x} y={BLOCK_Y} width={2.5} height={BLOCK_H} rx={1}
                      fill={DS.mealStroke} pointerEvents="none" />
                <text x={x + w / 2} y={BLOCK_Y + BLOCK_H / 2 + 4}
                      textAnchor="middle"
                      fontFamily="ui-monospace, Menlo, monospace" fontSize={10}
                      fontWeight={700} fill={DS.mealFg} letterSpacing="0.05em"
                      pointerEvents="none">
                  REFEZ
                </text>
                <text x={x} y={MINUTES_MAIN_Y} textAnchor="middle"
                      fontFamily="ui-monospace, Menlo, monospace" fontSize={9.5}
                      fontWeight={700} fill="#0b0d10" pointerEvents="none">
                  {minuteOnly(b.start_time)}
                </text>
                {b.minuti_accessori && (
                  <text x={x} y={MINUTES_AUX_Y} textAnchor="middle"
                        fontFamily="ui-monospace, Menlo, monospace" fontSize={8}
                        fontStyle="italic" fill="#a1a6ae" pointerEvents="none">
                    {b.minuti_accessori}
                  </text>
                )}
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
                      fill={DS.cvViola} rx={1}
                      stroke={isSel ? DS.brandRing : "none"} strokeWidth={isSel ? 1.5 : 0}
                      style={{ cursor: draggable ? "grab" : "pointer" }}
                      {...baseHandlers}
                      onMouseDown={(e) => draggable && startDrag(e, idx, "move")} />
                <line x1={x} y1={chipY + 4} x2={x} y2={BLOCK_Y - 2}
                      stroke={DS.cvViola} strokeWidth={0.8} strokeDasharray="1 1.5"
                      pointerEvents="none" />
                <text x={x} y={chipY} textAnchor="middle"
                      fontFamily="ui-monospace, Menlo, monospace" fontSize={9.5}
                      fontWeight={700} fill={DS.cvViola} pointerEvents="none">
                  {label} {b.train_id}
                  {b.from_station && (
                    <tspan fill={DS.cvViola} fillOpacity={0.7} fontSize={8.5}
                           fontWeight={400} dx="3">{b.from_station}</tspan>
                  )}
                </text>
                <text x={x} y={MINUTES_MAIN_Y} textAnchor="middle"
                      fontFamily="ui-monospace, Menlo, monospace" fontSize={9.5}
                      fontWeight={700} fill="#0b0d10" pointerEvents="none">
                  {minuteOnly(b.start_time)}
                </text>
                {b.minuti_accessori && (
                  <text x={x} y={MINUTES_AUX_Y} textAnchor="middle"
                        fontFamily="ui-monospace, Menlo, monospace" fontSize={8}
                        fontStyle="italic" fill="#a1a6ae" pointerEvents="none">
                    {b.minuti_accessori}
                  </text>
                )}
              </g>
            )
          }

          if (b.block_type === "scomp") {
            return (
              <g key={idx}>
                <rect x={x} y={BLOCK_Y} width={w} height={BLOCK_H} rx={4}
                      fill={DS.scompBg}
                      stroke={isSel ? DS.brandRing : "none"}
                      strokeWidth={isSel ? 1.8 : 0}
                      style={{ cursor: draggable ? "grab" : "pointer" }}
                      {...baseHandlers}
                      onMouseDown={(e) => draggable && startDrag(e, idx, "move")} />
                {/* Border-l warning accento verticale */}
                <rect x={x} y={BLOCK_Y} width={2.5} height={BLOCK_H} rx={1}
                      fill={DS.scompStroke} pointerEvents="none" />
                <text x={x + w / 2} y={BLOCK_Y + BLOCK_H / 2 + 4} textAnchor="middle"
                      fontFamily="ui-monospace, Menlo, monospace" fontSize={10}
                      fontWeight={700} fill={DS.scompFg} letterSpacing="0.05em"
                      pointerEvents="none">
                  {w >= 60 && b.from_station ? `S.COMP ${b.from_station}` : "S.COMP"}
                </text>
                <text x={x} y={MINUTES_MAIN_Y} textAnchor="middle"
                      fontFamily="ui-monospace, Menlo, monospace" fontSize={9.5}
                      fontWeight={700} fill="#0b0d10" pointerEvents="none">
                  {minuteOnly(b.start_time)}
                </text>
                {b.minuti_accessori && (
                  <text x={x} y={MINUTES_AUX_Y} textAnchor="middle"
                        fontFamily="ui-monospace, Menlo, monospace" fontSize={8}
                        fontStyle="italic" fill="#a1a6ae" pointerEvents="none">
                    {b.minuti_accessori}
                  </text>
                )}
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

          if (debug) {
            return (
              <rect key={idx} x={x} y={BLOCK_Y} width={w} height={BLOCK_H}
                    fill="#e4e6ea" stroke="#a1a6ae" strokeWidth={1} rx={3}
                    {...baseHandlers} />
            )
          }
          return null
        })}

        {/* ===================================================
            ACTION BAR contestuale (sopra la chip selected)
            Posizionata dinamicamente sopra il blocco, clampata
            ai bordi del viewBox. 8 icone + 3 separatori.
            =================================================== */}
        {!hideActionBar && selectedIdx !== null && blocks[selectedIdx] && (() => {
          const b = blocks[selectedIdx]
          const sm = hhmmToMinutesRel(b.start_time || "")
          if (sm === null) return null
          const em = hhmmToMinutesRel(b.end_time || b.start_time || "") ?? sm
          const bx = minToX(sm)
          const bx2 = minToX(em)
          const bw = Math.max(2, bx2 - bx)

          const BTN_W = 32
          const BTN_H = 24
          const SEP_W = 9
          const PAD = 6
          const contentW = ACTION_DEFS.reduce(
            (acc, a, i) => acc + BTN_W + (a.separatorAfter && i < ACTION_DEFS.length - 1 ? SEP_W : 0),
            0,
          )
          const barW = contentW + PAD * 2
          const barH = BTN_H + 6

          let barX = bx + bw / 2 - barW / 2
          if (barX < 5) barX = 5
          if (barX + barW > TOTAL_WIDTH - 5) barX = TOTAL_WIDTH - 5 - barW
          const barY = BLOCK_Y - 42
          const pointerCenter = Math.min(
            Math.max(bx + bw / 2 - barX, 14),
            barW - 14,
          )

          let cx = PAD
          return (
            <g transform={`translate(${barX}, ${barY})`}
               style={{ filter: "drop-shadow(0 4px 12px rgba(30,64,175,0.25))" }}
               onMouseDown={(e) => e.stopPropagation()}>
              {/* sfondo bianco + border blu */}
              <rect x={0} y={0} width={barW} height={barH}
                    rx={6} fill="#ffffff" stroke="#60a5fa" strokeWidth={1} />
              {/* freccia verso il blocco */}
              <polygon
                points={`${pointerCenter - 10},${barH} ${pointerCenter},${barH + 6} ${pointerCenter + 10},${barH}`}
                fill="#ffffff" stroke="#60a5fa" strokeWidth={1}
              />
              {/* rect bianco per "tagliare" la linea stroke tra bar e freccia */}
              <rect x={pointerCenter - 9} y={barH - 0.5} width={18} height={1} fill="#ffffff" />

              {ACTION_DEFS.map((a, i) => {
                const btnX = cx
                cx += BTN_W
                const sep = a.separatorAfter && i < ACTION_DEFS.length - 1
                const sepX = cx + SEP_W / 2
                if (sep) cx += SEP_W

                const fillHover = a.danger ? "#fee2e2" : a.warn ? "#fef3c7" : "#eff6ff"
                const txtColor = a.danger ? "#b91c1c" : a.warn ? "#b45309" : "#353a42"

                return (
                  <g key={a.act}>
                    <g style={{ cursor: "pointer" }}
                       onMouseDown={(e) => e.stopPropagation()}
                       onClick={(e) => { e.stopPropagation(); fireAction(a.act) }}>
                      <title>{a.title}</title>
                      <rect className="pdc-gantt-action-hit"
                            x={btnX} y={3} width={BTN_W} height={BTN_H}
                            rx={4} fill="transparent"
                            onMouseEnter={(e) => { (e.currentTarget as SVGRectElement).setAttribute("fill", fillHover) }}
                            onMouseLeave={(e) => { (e.currentTarget as SVGRectElement).setAttribute("fill", "transparent") }} />
                      <text x={btnX + BTN_W / 2} y={barH - 7}
                            textAnchor="middle"
                            fontFamily="system-ui, sans-serif"
                            fontSize={12} fontWeight={600} fill={txtColor}
                            pointerEvents="none">
                        {a.icon}
                      </text>
                    </g>
                    {sep && (
                      <line x1={sepX} y1={7} x2={sepX} y2={barH - 4}
                            stroke="#e4e6ea" strokeWidth={1} pointerEvents="none" />
                    )}
                  </g>
                )
              })}
            </g>
          )
        })()}

      </svg>

      <Tooltip data={tooltip} />
    </div>
  )
}
