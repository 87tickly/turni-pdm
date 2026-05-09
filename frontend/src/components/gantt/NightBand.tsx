import { Moon } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Banda notturna fra giornate consecutive del Gantt — Sprint 8.2 MR-PD6.
 *
 * Pattern PDF Trenord giro: una riga sottile (24px) inserita FRA due
 * `GiornataRow` consecutive che mostra:
 * - icona luna a sinistra (sticky-left)
 * - durata sosta + stazione di sosta + dettagli (timeline area)
 * - badge ok/anomalia a destra (sticky-right)
 *
 * Mantiene la stessa griglia 3-colonne del Gantt
 * (`leftColPx | timelineWidthPx | rightColPx`) per allineamento
 * verticale perfetto con le righe giornata.
 *
 * Usato dal Gantt PdC per visualizzare il riposo notturno fra fine
 * giornata N e inizio giornata N+1; usabile anche dal Gantt giro
 * materiale come `SostaNotturnaRow`.
 */
export interface NightBandProps {
  /** Larghezza in px della colonna sticky-left (label giornata). */
  leftColPx: number;
  /** Larghezza in px dell'area timeline. */
  timelineWidthPx: number;
  /** Larghezza in px della colonna sticky-right (stats). */
  rightColPx: number;
  /** Altezza in px della banda. Default 24. */
  heightPx?: number;
  /** Stazione in cui il PdC sosta (es. nome deposito o FR). */
  stazioneNome?: string | null;
  /** Numero giornata che termina (es. 1). */
  giornataPrev: number;
  /** Numero giornata che riprende (es. 2). */
  giornataNext: number;
  /** Ora fine giornata precedente (es. "22:30"). */
  oraFinePrev?: string | null;
  /** Ora inizio giornata successiva (es. "06:00"). */
  oraInizioNext?: string | null;
  /** Durata sosta in minuti (per badge). */
  durataMin?: number;
  /** Se true: badge anomalia (sosta troppo breve / troppo lunga). */
  anomalia?: boolean;
  /** Etichetta opzionale custom in centro (override del default). */
  labelCustom?: string;
}

function formatHM(mins: number): string {
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `${h}h${String(m).padStart(2, "0")}`;
}

export function NightBand({
  leftColPx,
  timelineWidthPx,
  rightColPx,
  heightPx = 24,
  stazioneNome,
  giornataPrev,
  giornataNext,
  oraFinePrev,
  oraInizioNext,
  durataMin,
  anomalia = false,
  labelCustom,
}: NightBandProps) {
  const label =
    labelCustom ??
    `sosta${stazioneNome ? ` a ${stazioneNome}` : ""}` +
      (oraFinePrev ? ` · da G${giornataPrev} finita ${oraFinePrev}` : "") +
      (oraInizioNext ? ` · ripresa G${giornataNext} ${oraInizioNext}` : "");

  return (
    <div
      className={cn(
        "relative flex border-b border-sky-200/60",
        anomalia ? "bg-amber-50" : "bg-sky-50/70",
      )}
      style={{ height: heightPx }}
      role="row"
      aria-label={label}
    >
      {/* Sticky-left: icona luna + numeri giornate */}
      <div
        className={cn(
          "sticky left-0 z-10 flex items-center justify-center gap-1 border-r border-sky-200/60 px-3 font-mono text-[10px] tabular-nums",
          anomalia ? "bg-amber-50 text-amber-800" : "bg-sky-50/70 text-sky-800",
        )}
        style={{ width: leftColPx }}
      >
        <Moon className="h-3 w-3" aria-hidden />
        <span>
          G{giornataPrev}→G{giornataNext}
        </span>
      </div>
      {/* Area timeline: label centrale */}
      <div
        className="flex items-center px-3"
        style={{ width: timelineWidthPx }}
      >
        <span
          className={cn(
            "truncate text-[11px] italic",
            anomalia ? "text-amber-800" : "text-sky-800",
          )}
        >
          {label}
        </span>
      </div>
      {/* Sticky-right: badge durata sosta */}
      <div
        className={cn(
          "sticky right-0 z-10 flex items-center justify-center border-l border-sky-200/60 font-mono text-[10px] tabular-nums",
          anomalia ? "bg-amber-50 text-amber-800" : "bg-sky-50/70 text-sky-800",
        )}
        style={{ width: rightColPx }}
        aria-label="durata sosta"
      >
        {durataMin !== undefined ? formatHM(durataMin) : "—"}
      </div>
    </div>
  );
}
