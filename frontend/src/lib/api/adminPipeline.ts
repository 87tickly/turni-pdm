/**
 * Wrapper API per `/api/admin/pipeline-overview` (Sprint 8.0 MR 6).
 *
 * Tipi allineati a `colazione.api.pipeline_overview`.
 */

import { apiJson } from "@/lib/api/client";

export interface PipelineProgrammaItem {
  programma_id: number;
  nome: string;
  stato_pipeline_pdc: string;
  stato_manutenzione: string;
  pdc_responsabile_prossimo: string;
  manutenzione_responsabile_prossimo: string;
  giorni_in_stato: number;
  is_bloccato: boolean;
}

export interface PipelineOverviewResponse {
  programmi: PipelineProgrammaItem[];
  counters_per_stato_pdc: Record<string, number>;
  counters_per_stato_manutenzione: Record<string, number>;
  n_bloccati: number;
}

export async function getPipelineOverview(): Promise<PipelineOverviewResponse> {
  return apiJson<PipelineOverviewResponse>(
    "/api/admin/pipeline-overview",
    { method: "GET" },
  );
}
