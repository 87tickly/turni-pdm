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

export interface PianificatorePdcOverview {
  giri_materiali_count: number;
  turni_pdc_per_impianto: TurniPerImpiantoItem[];
  turni_con_violazioni_hard: number;
  revisioni_cascading_attive: number;
}

export async function fetchPianificatorePdcOverview(): Promise<PianificatorePdcOverview> {
  return apiJson<PianificatorePdcOverview>("/api/pianificatore-pdc/overview", {
    method: "GET",
  });
}
