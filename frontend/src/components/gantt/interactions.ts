/**
 * useGanttInteractions — hook che aggiunge il layer interazioni
 * opt-in sopra GanttSheet.
 *
 * Spec: docs/HANDOFF-gantt-v3-interactions.md
 * Sorgente autoritativo: docs/claude-design-bundles/gantt-interactions/
 *
 * Il hook e' stateless se nessuna callback e' fornita. Attiva
 * gradualmente: drag se onSegmentDrag, cross-day se onCrossDrop+ganttId,
 * action bar se onAction && !hideActionBar, ecc.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import type { RefObject } from "react"
import type {
  CrossDragPayload,
  DragKind,
  GanttAction,
  GanttInteractionCallbacks,
  GanttRow,
  GanttSegment,
  SegmentDragChange,
} from "./types"
import { CROSS_DAY_MIME } from "./types"
import { timeToMin, minToTime } from "./tokens"


export interface DragState {
  rowIdx: number
  segIdx: number
  kind: DragKind
  initialDepMin: number
  initialArrMin: number
  initialMouseX: number
  active: boolean
  linkedCvpIdx: number | null
  linkedCvaIdx: number | null
  currentDepMin: number
  currentArrMin: number
}

export interface ActionBarState {
  rowIdx: number
  segIdx: number
  seg: GanttSegment
}


export interface UseGanttInteractionsOptions
  extends GanttInteractionCallbacks {
  svgRef: RefObject<SVGSVGElement | null>
  containerRef: RefObject<HTMLDivElement | null>
  rows: GanttRow[]
  totalW: number
  xFor: (min: number) => number
  hStart: number
  ganttId?: string
  hideActionBar?: boolean
  snapMinutes?: number
  dragThresholdPx?: number
}


export interface UseGanttInteractionsResult {
  selectedSegIdx: number | null
  selectedRowIdx: number | null
  dragState: DragState | null
  actionBarState: ActionBarState | null

  // Binding helpers — il GanttSheet li chiama e li distribuisce sui <g> segment
  bindSegment: (rowIdx: number, segIdx: number) => {
    onMouseDown: (ev: React.MouseEvent) => void
    onClick: (ev: React.MouseEvent) => void
    onDragStart?: (ev: React.DragEvent) => void
    onDragEnd?: (ev: React.DragEvent) => void
    draggable?: boolean
    tabIndex: number
    onKeyDown: (ev: React.KeyboardEvent) => void
  }

  bindTimeline: () => {
    onClick: (ev: React.MouseEvent, rowIdx: number) => void
    onDragOver?: (ev: React.DragEvent) => void
    onDrop?: (ev: React.DragEvent, rowIdx: number) => void
    cursor: string
  }

  // Avvio esplicito di un drag (usato dalle handle resize-start / resize-end
  // che vivono fuori dal rect principale del segment)
  startDrag: (
    ev: React.MouseEvent,
    rowIdx: number,
    segIdx: number,
    kind: DragKind,
  ) => void

  // Dismiss action bar
  dismiss: () => void

  // Richiede action (usato dal click su icona della bar)
  triggerAction: (action: GanttAction) => void
}


export function useGanttInteractions(
  opts: UseGanttInteractionsOptions,
): UseGanttInteractionsResult {
  const {
    svgRef,
    containerRef,
    rows,
    totalW,
    xFor,
    hStart,
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
  } = opts

  const [selectedRowIdx, setSelectedRowIdx] = useState<number | null>(null)
  const [selectedSegIdx, setSelectedSegIdx] = useState<number | null>(null)
  const [dragState, setDragState] = useState<DragState | null>(null)
  const didDragRef = useRef(false)

  const crossDayEnabled = !!ganttId &&
    (!!onCrossDragStart || !!onCrossDrop || !!onCrossRemove)

  // ─── clientX → minRel (relativo a hStart * 60) ───
  const clientXToMin = useCallback(
    (clientX: number): number => {
      const svg = svgRef.current
      if (!svg) return 0
      const rect = svg.getBoundingClientRect()
      const svgX = ((clientX - rect.left) / rect.width) * totalW
      // Inverti xFor: x = COL_LEFT + ((min - hStart*60) / 60) * PX_PER_HOUR
      // quindi: min = hStart*60 + (x - COL_LEFT) / PX_PER_HOUR * 60
      // Non conosciamo COL_LEFT/PX_PER_HOUR qui → usiamo xFor inverso numerico
      // via approssimazione: sample xFor(hStart*60) per trovare COL_LEFT
      const colLeftX = xFor(hStart * 60)
      const oneHourX = xFor(hStart * 60 + 60) - colLeftX
      if (oneHourX <= 0) return hStart * 60
      return hStart * 60 + ((svgX - colLeftX) / oneHourX) * 60
    },
    [svgRef, totalW, xFor, hStart],
  )

  // ─── CVp/CVa linkage: dato il segIdx del treno padrone, restituisce
  // gli indici dei CVp (prima) e CVa (dopo) adiacenti nella stessa row ───
  const findLinkedCvs = useCallback(
    (rowIdx: number, segIdx: number): {
      cvpIdx: number | null
      cvaIdx: number | null
    } => {
      const row = rows[rowIdx]
      if (!row) return { cvpIdx: null, cvaIdx: null }
      const seg = row.segments[segIdx]
      if (!seg || seg.kind !== "cond") return { cvpIdx: null, cvaIdx: null }
      // Nel modello GanttSegment cvp/cva sono flag sul treno stesso,
      // non segmenti separati. Quindi non ci sono segmenti adiacenti da
      // linkare — il drag del treno gia' porta con se' i flag.
      // Lasciamo la funzione per estensioni future (es. CV satellite)
      return { cvpIdx: null, cvaIdx: null }
    },
    [rows],
  )

  // ─── Drag intra-Gantt: mousedown ───
  const startDrag = useCallback(
    (
      ev: React.MouseEvent,
      rowIdx: number,
      segIdx: number,
      kind: DragKind,
    ) => {
      if (!onSegmentDrag) return
      ev.stopPropagation()
      didDragRef.current = false
      const row = rows[rowIdx]
      const seg = row?.segments[segIdx]
      if (!seg) return
      const depMin = timeToMin(seg.dep_time)
      let arrMin = timeToMin(seg.arr_time)
      if (arrMin < depMin) arrMin += 1440
      const { cvpIdx, cvaIdx } = findLinkedCvs(rowIdx, segIdx)
      setDragState({
        rowIdx,
        segIdx,
        kind,
        initialDepMin: depMin,
        initialArrMin: arrMin,
        initialMouseX: ev.clientX,
        active: false,
        linkedCvpIdx: cvpIdx,
        linkedCvaIdx: cvaIdx,
        currentDepMin: depMin,
        currentArrMin: arrMin,
      })
    },
    [onSegmentDrag, rows, findLinkedCvs],
  )

  // ─── Drag intra-Gantt: mousemove / mouseup globali ───
  useEffect(() => {
    if (!dragState || !onSegmentDrag) return

    const handleMove = (ev: MouseEvent) => {
      const deltaPx = Math.abs(ev.clientX - dragState.initialMouseX)
      if (!dragState.active && deltaPx < dragThresholdPx) return
      if (!dragState.active) {
        setDragState((s) => (s ? { ...s, active: true } : s))
        didDragRef.current = true
      }

      // Converti delta px → delta min usando xFor
      const startMin = clientXToMin(dragState.initialMouseX)
      const nowMin = clientXToMin(ev.clientX)
      const rawDelta = nowMin - startMin
      const snappedDelta = Math.round(rawDelta / snapMinutes) * snapMinutes

      let newDep = dragState.initialDepMin
      let newArr = dragState.initialArrMin
      if (dragState.kind === "move") {
        newDep = dragState.initialDepMin + snappedDelta
        newArr = dragState.initialArrMin + snappedDelta
      } else if (dragState.kind === "resize-start") {
        newDep = dragState.initialDepMin + snappedDelta
        if (newDep > dragState.initialArrMin - snapMinutes) {
          newDep = dragState.initialArrMin - snapMinutes
        }
      } else if (dragState.kind === "resize-end") {
        newArr = dragState.initialArrMin + snappedDelta
        if (newArr < dragState.initialDepMin + snapMinutes) {
          newArr = dragState.initialDepMin + snapMinutes
        }
      }

      setDragState((s) =>
        s ? { ...s, currentDepMin: newDep, currentArrMin: newArr } : s,
      )
    }

    const handleUp = () => {
      if (dragState.active) {
        const changes: SegmentDragChange = {}
        if (dragState.currentDepMin !== dragState.initialDepMin) {
          changes.dep_time = minToTime(dragState.currentDepMin)
        }
        if (dragState.currentArrMin !== dragState.initialArrMin) {
          changes.arr_time = minToTime(dragState.currentArrMin)
        }
        if (Object.keys(changes).length > 0) {
          onSegmentDrag(dragState.rowIdx, dragState.segIdx, changes)
        }
      }
      setDragState(null)
    }

    window.addEventListener("mousemove", handleMove)
    window.addEventListener("mouseup", handleUp)
    return () => {
      window.removeEventListener("mousemove", handleMove)
      window.removeEventListener("mouseup", handleUp)
    }
  }, [dragState, onSegmentDrag, snapMinutes, dragThresholdPx, clientXToMin])

  // ─── Cross-day HTML5 DnD ───
  const handleCrossDragStart = useCallback(
    (ev: React.DragEvent, rowIdx: number, segIdx: number) => {
      if (!crossDayEnabled || !ganttId) return
      // Cancella eventuale drag intra-Gantt in corso
      setDragState(null)
      const row = rows[rowIdx]
      const seg = row?.segments[segIdx]
      if (!seg) return
      const payload: CrossDragPayload = {
        ganttId,
        seg,
        rowIdx,
        segIdx,
      }
      try {
        ev.dataTransfer.effectAllowed = "move"
        ev.dataTransfer.setData(CROSS_DAY_MIME, JSON.stringify(payload))
        ev.dataTransfer.setData(
          "text/plain",
          `${seg.kind}:${seg.train_id}`,
        )
      } catch {
        // no-op
      }
      if (onCrossDragStart) onCrossDragStart(payload)
    },
    [crossDayEnabled, ganttId, rows, onCrossDragStart],
  )

  const handleCrossDragEnd = useCallback(
    (ev: React.DragEvent, segIdx: number) => {
      setDragState(null)
      didDragRef.current = false
      if (!crossDayEnabled) return
      if (ev.dataTransfer.dropEffect === "move" && onCrossRemove) {
        // withLinkedCvs: se il seg padrone e' un treno con CVp/CVa flag,
        // il parent potrebbe voler rimuovere anche i blocchi CV adiacenti
        // (nel modello PdcBlock).
        const rowIdx = 0
        const row = rows[rowIdx]
        const seg = row?.segments[segIdx]
        const withLinkedCvs =
          !!seg && seg.kind === "cond" && !!(seg.cvp || seg.cva)
        onCrossRemove(segIdx, withLinkedCvs)
      }
    },
    [crossDayEnabled, onCrossRemove, rows],
  )

  const handleTimelineDragOver = useCallback(
    (ev: React.DragEvent) => {
      if (!crossDayEnabled || !onCrossDrop) return
      if (Array.from(ev.dataTransfer.types).includes(CROSS_DAY_MIME)) {
        ev.preventDefault()
        ev.dataTransfer.dropEffect = "move"
      }
    },
    [crossDayEnabled, onCrossDrop],
  )

  const handleTimelineDrop = useCallback(
    (ev: React.DragEvent, rowIdx: number) => {
      if (!crossDayEnabled || !onCrossDrop || !ganttId) return
      const raw = ev.dataTransfer.getData(CROSS_DAY_MIME)
      if (!raw) return
      ev.preventDefault()
      let payload: CrossDragPayload
      try {
        payload = JSON.parse(raw)
      } catch {
        return
      }
      if (payload.ganttId === ganttId && payload.rowIdx === rowIdx) return
      const minRel = clientXToMin(ev.clientX)
      const snapped = Math.round(minRel / snapMinutes) * snapMinutes
      const abs = ((snapped % 1440) + 1440) % 1440
      const hour = Math.floor(abs / 60)
      const minute = Math.round(abs % 60)
      onCrossDrop(payload, ganttId, { hour, minute, rowIdx })
    },
    [crossDayEnabled, onCrossDrop, ganttId, clientXToMin, snapMinutes],
  )

  // ─── Timeline click (add block) ───
  const handleTimelineClick = useCallback(
    (ev: React.MouseEvent, rowIdx: number) => {
      if (!onTimelineClick) return
      if (didDragRef.current) {
        didDragRef.current = false
        return
      }
      const minRel = clientXToMin(ev.clientX)
      const snapped = Math.round(minRel / snapMinutes) * snapMinutes
      const abs = ((snapped % 1440) + 1440) % 1440
      const hour = Math.floor(abs / 60)
      const minute = Math.round(abs % 60)
      onTimelineClick(hour, minute, rowIdx)
    },
    [onTimelineClick, clientXToMin, snapMinutes],
  )

  // ─── Click su segment (selection + action bar) ───
  const handleSegmentClick = useCallback(
    (ev: React.MouseEvent, rowIdx: number, segIdx: number) => {
      ev.stopPropagation()
      if (didDragRef.current) {
        didDragRef.current = false
        return
      }
      if (hideActionBar) {
        // Pass-through to onSegmentClick handled by GanttSheet itself
        return
      }
      setSelectedRowIdx(rowIdx)
      setSelectedSegIdx(segIdx)
    },
    [hideActionBar],
  )

  // ─── Keyboard: Esc deseleziona, click fuori SVG deseleziona ───
  useEffect(() => {
    if (selectedSegIdx === null) return
    const onDocClick = (ev: MouseEvent) => {
      const svg = svgRef.current
      const container = containerRef.current
      if (!svg) return
      // Click DENTRO il container (action bar inclusa) → non deselezionare
      if (container && container.contains(ev.target as Node)) return
      if (!svg.contains(ev.target as Node)) {
        setSelectedRowIdx(null)
        setSelectedSegIdx(null)
      }
    }
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") {
        setSelectedRowIdx(null)
        setSelectedSegIdx(null)
      }
    }
    document.addEventListener("mousedown", onDocClick)
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("mousedown", onDocClick)
      document.removeEventListener("keydown", onKey)
    }
  }, [selectedSegIdx, svgRef, containerRef])

  // ─── Action bar trigger ───
  const triggerAction = useCallback(
    (action: GanttAction) => {
      if (selectedRowIdx === null || selectedSegIdx === null) return
      const seg = rows[selectedRowIdx]?.segments[selectedSegIdx]
      if (!seg) return
      if (onAction) onAction(action, seg, selectedRowIdx, selectedSegIdx)
      setSelectedRowIdx(null)
      setSelectedSegIdx(null)
    },
    [selectedRowIdx, selectedSegIdx, rows, onAction],
  )

  // ─── Dismiss ───
  const dismiss = useCallback(() => {
    setSelectedRowIdx(null)
    setSelectedSegIdx(null)
  }, [])

  // ─── Action bar state derivato ───
  const actionBarState = useMemo((): ActionBarState | null => {
    if (hideActionBar) return null
    if (selectedRowIdx === null || selectedSegIdx === null) return null
    const seg = rows[selectedRowIdx]?.segments[selectedSegIdx]
    if (!seg) return null
    return { rowIdx: selectedRowIdx, segIdx: selectedSegIdx, seg }
  }, [hideActionBar, selectedRowIdx, selectedSegIdx, rows])

  // ─── Binding helpers ───
  const bindSegment = useCallback(
    (rowIdx: number, segIdx: number) => ({
      onMouseDown: (ev: React.MouseEvent) => {
        if (!onSegmentDrag) return
        startDrag(ev, rowIdx, segIdx, "move")
      },
      onClick: (ev: React.MouseEvent) => handleSegmentClick(ev, rowIdx, segIdx),
      onDragStart: crossDayEnabled
        ? (ev: React.DragEvent) => handleCrossDragStart(ev, rowIdx, segIdx)
        : undefined,
      onDragEnd: crossDayEnabled
        ? (ev: React.DragEvent) => handleCrossDragEnd(ev, segIdx)
        : undefined,
      draggable: crossDayEnabled,
      tabIndex: 0,
      onKeyDown: (ev: React.KeyboardEvent) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault()
          handleSegmentClick(ev as unknown as React.MouseEvent, rowIdx, segIdx)
        }
      },
    }),
    [
      onSegmentDrag,
      crossDayEnabled,
      startDrag,
      handleSegmentClick,
      handleCrossDragStart,
      handleCrossDragEnd,
    ],
  )

  const bindTimeline = useCallback(
    () => ({
      onClick: (ev: React.MouseEvent, rowIdx: number) =>
        handleTimelineClick(ev, rowIdx),
      onDragOver: crossDayEnabled ? handleTimelineDragOver : undefined,
      onDrop: crossDayEnabled
        ? (ev: React.DragEvent, rowIdx: number) =>
            handleTimelineDrop(ev, rowIdx)
        : undefined,
      cursor: onTimelineClick ? "crosshair" : "default",
    }),
    [
      handleTimelineClick,
      crossDayEnabled,
      handleTimelineDragOver,
      handleTimelineDrop,
      onTimelineClick,
    ],
  )

  return {
    selectedRowIdx,
    selectedSegIdx,
    dragState,
    actionBarState,
    bindSegment,
    bindTimeline,
    startDrag,
    dismiss,
    triggerAction,
  }
}


// ─── Configurazione action bar (8 icone + 3 separatori) ───
export interface ActionBarButton {
  action: GanttAction
  icon: string
  title: string
  separatorAfter?: boolean
  variant?: "warn" | "danger"
}

export const ACTION_BAR_CONFIG: ActionBarButton[] = [
  { action: "edit", icon: "✎", title: "Modifica blocco" },
  { action: "move", icon: "↔", title: "Sposta (drag temporale o inter-turno)" },
  { action: "duplicate", icon: "⧉", title: "Duplica blocco", separatorAfter: true },
  { action: "link", icon: "🔗", title: "Collega al giro materiale" },
  { action: "warn", icon: "⚠", title: "Verifica discrepanze ARTURO Live", variant: "warn", separatorAfter: true },
  { action: "detail", icon: "↗", title: "Apri dettaglio treno" },
  { action: "history", icon: "⧗", title: "Storico ritardi (30gg)", separatorAfter: true },
  { action: "delete", icon: "×", title: "Elimina blocco", variant: "danger" },
]
