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
