/**
 * Wrapper API per `/api/pianificatore-pdc/*` (Sprint 7.3 MR 1 backend).
 *
 * Tipi allineati a `colazione.api.pianificatore_pdc.OverviewResponse`.
 */

import { apiJson } from "@/lib/api/client";

export interface TurniPerImpiantoItem {
  impianto: string;
  count: number;
}

/**
 * Sprint 7.9 MR η — distribuzione turni PdC per deposito FK.
 * `deposito_pdc_id == null` corrisponde ai turni legacy senza FK
 * valorizzata (in coda all'ordinamento).
 */
export interface TurniPerDepositoItem {
  deposito_pdc_id: number | null;
  deposito_pdc_codice: string | null;
  deposito_pdc_display: string | null;
  count: number;
  n_dormite_fr_totali: number;
}

export interface PianificatorePdcOverview {
  giri_materiali_count: number;
  turni_pdc_per_impianto: TurniPerImpiantoItem[];
  /** Sprint 7.9 MR η — distribuzione per deposito (FK). */
  turni_pdc_per_deposito: TurniPerDepositoItem[];
  turni_con_violazioni_hard: number;
  revisioni_cascading_attive: number;
  /** Sprint 7.9 MR η — somma dormite FR su tutti i turni. */
  dormite_fr_totali: number;
  /** Sprint 7.9 MR η — turni con cap FR violato (1/sett, 3/28gg). */
  turni_con_fr_cap_violazioni: number;
  /** Sprint 7.9 MR η — anagrafica depot attivi (denominatore "impianti coperti"). */
  depositi_pdc_totali: number;
}

export async function fetchPianificatorePdcOverview(): Promise<PianificatorePdcOverview> {
  return apiJson<PianificatorePdcOverview>("/api/pianificatore-pdc/overview", {
    method: "GET",
  });
}
