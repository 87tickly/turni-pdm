/**
 * Wrapper API per `/api/personale-pdc/*` — Sprint 8.0 MR 3 (entry 168).
 *
 * Tipi allineati a `colazione.api.personale_pdc`:
 * - `MioTurnoGiornata`
 *
 * Il PdC vede solo turni dei programmi in stato pipeline
 * `VISTA_PUBBLICATA` (filter applicato server-side).
 */

import { apiJson } from "@/lib/api/client";

export interface MioTurnoGiornata {
  assegnazione_id: number;
  /** ISO `YYYY-MM-DD`. */
  data: string;
  stato_assegnazione: string;
  turno_pdc_id: number;
  turno_codice: string;
  turno_impianto: string;
  numero_giornata: number;
  variante_calendario: string;
  /** ISO `HH:MM:SS`. */
  inizio_prestazione: string | null;
  fine_prestazione: string | null;
  prestazione_min: number;
  condotta_min: number;
  refezione_min: number;
  is_notturno: boolean;
  is_riposo: boolean;
}

export async function getMioTurno(): Promise<MioTurnoGiornata[]> {
  return apiJson<MioTurnoGiornata[]>("/api/personale-pdc/mio-turno", {
    method: "GET",
  });
}
