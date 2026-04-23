/**
 * Tipi Gantt v3 — da HANDOFF-gantt-v3.md §4.
 *
 * Verranno esportati anche da `frontend/src/lib/api.ts` quando il
 * backend espone i nuovi campi (suspect_reason, cvp, cva).
 */

export type GanttSegmentKind =
  | "cond"    // condotta (produttivo, nero inchiostro)
  | "dh"      // deadhead / vettura (tratteggiata)
  | "refez"   // refezione in stazione (barra sottile ambra)
  | "scomp"   // S.COMP giornata in disponibilita' (grigio tenue)
  | "sleep"   // dormita FR fuori residenza (viola)

export interface GanttSegment {
  kind: GanttSegmentKind
  train_id: string
  from_station: string
  to_station: string
  dep_time: string          // "HH:MM"
  arr_time: string          // "HH:MM"
  preheat?: boolean         // bullet ● prima del numero treno
  suspect_reason?: string   // vettura sospetta (ciclo); se set -> rosso punteggiato + ⚠
  cvp?: boolean             // prefix CVp nell'etichetta
  cva?: boolean             // prefix CVa nell'etichetta
  // Accessori (backend: src/turn_builder/accessori.py)
  accp_min?: number         // accessori in partenza (es. 40 cond, 15 vett, 80 preheat)
  acca_min?: number         // accessori in arrivo (es. 40 cond, 10 vett)
  // Cambio volante minuti (backend: src/turn_builder/cv_registry.py)
  cv_before_min?: number    // CVp minuti (l'utente entra sul mezzo)
  cv_after_min?: number     // CVa minuti (l'utente esce dal mezzo)
}

export interface GanttMetrics {
  lav: string   // "7h31"
  cct: string   // "03h03"
  km: number    // 153
  not: "sì" | "no"
  rip: string   // "14h55"
  fr?: boolean  // badge "FR · notturno"
}

export interface GanttRow {
  label: string                            // "LMXGV" | "S" | "D" | "F" | "SD" | "G6 · LMXGV"
  segments: GanttSegment[]
  metrics_override?: Partial<GanttMetrics>
  warn?: boolean                           // pallino rosso a destra
  meta?: string                            // override "[07:18] → [14:49]"
}

export interface GanttDayHead {
  num: number
  pres: string
  end: string
  variant?: string
}

export type GanttPalette = "hybrid" | "mono" | "brand"
export type GanttLabelsMode = "auto" | "vertical" | "horizontal"
export type GanttMinutesMode = "hhmm" | "duration" | "off"

// ─── Interactions layer (opt-in) ───────────────────────────────

export type GanttAction =
  | "edit"
  | "move"
  | "duplicate"
  | "link"
  | "warn"
  | "detail"
  | "history"
  | "delete"

export interface CrossDragPayload {
  ganttId: string
  seg: GanttSegment
  rowIdx: number
  segIdx: number
  // CVp/CVa linkati al treno padrone (seguono durante drag)
  linkedCvp?: GanttSegment
  linkedCva?: GanttSegment
}

export const CROSS_DAY_MIME = "application/x-colazione-block"

export type DragKind = "move" | "resize-start" | "resize-end"

export interface SegmentDragChange {
  dep_time?: string
  arr_time?: string
}

export interface GanttInteractionCallbacks {
  onSegmentDrag?: (
    rowIdx: number,
    segIdx: number,
    changes: SegmentDragChange,
  ) => void
  onTimelineClick?: (hour: number, minute: number, rowIdx: number) => void
  onCrossDragStart?: (p: CrossDragPayload) => void
  onCrossDrop?: (
    p: CrossDragPayload,
    targetGanttId: string,
    dropTime: { hour: number; minute: number; rowIdx: number },
  ) => void
  onCrossRemove?: (segIdx: number, withLinkedCvs: boolean) => void
  onAction?: (
    action: GanttAction,
    seg: GanttSegment,
    rowIdx: number,
    segIdx: number,
  ) => void
}
