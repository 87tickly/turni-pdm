/**
 * Tokens Gantt v3 — dimensioni e colori per il componente SVG.
 * I valori CSS corrispondenti sono in `frontend/src/index.css`.
 */

export const GANTT_LAYOUT = {
  COL_LEFT: 108,          // label giornata a sinistra
  COL_RIGHT: 168,         // colonna metriche a destra
  PX_PER_HOUR: 46,        // densita' asse orario
  LABEL_BAND: 62,         // banda sopra la barra per label verticali + accessori
  MINUTES_BAND: 24,       // banda sotto la barra per HH:MM / durata
  BAR_HEIGHT: 20,         // altezza default barra (modificabile via prop)
  AXIS_Y: 28,             // offset verticale asse dal top
  ROW_GAP: 8,             // spazio extra tra righe
} as const

export const GANTT_COLORS = {
  BAR_COND: "var(--gantt-bar-cond, #0B6AA8)",
  BAR_COND_INK: "var(--gantt-bar-cond-ink, #084F7F)",
  BAR_DH_LINE: "var(--gantt-bar-dh-line, #4E6A85)",
  BAR_DH_BG: "var(--gantt-bar-dh-bg, #E9EEF5)",
  REFEZ: "var(--gantt-refez, #D97706)",
  REFEZ_INK: "var(--gantt-refez-ink, #B45309)",
  SCOMP: "var(--gantt-scomp, #6C7488)",
  SLEEP: "var(--gantt-sleep, #5B21B6)",
  SLEEP_BG: "var(--gantt-sleep-bg, rgb(91 33 182 / 0.10))",
  FR: "var(--gantt-fr, #7C3AED)",
  CVP: "var(--gantt-cvp, #B45309)",
  CVA: "var(--gantt-cva, #6B21A8)",
  PREHEAT: "var(--gantt-preheat, #0062CC)",
  SUSPECT: "var(--gantt-suspect, #DC2626)",
  INK: "var(--color-on-surface-strong, #0A1322)",
  INK_60: "var(--gantt-ink-60, #3E4C67)",
  INK_40: "var(--gantt-ink-40, #6C7488)",
} as const

export function timeToMin(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number)
  return h * 60 + (m || 0)
}

export function minToTime(min: number): string {
  const m = ((min % 1440) + 1440) % 1440
  const h = Math.floor(m / 60)
  const mm = m % 60
  return String(h).padStart(2, "0") + ":" + String(mm).padStart(2, "0")
}
