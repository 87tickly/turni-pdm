/**
 * Wrapper API per `/api/aziende/me/pde/*` (Sub-MR 5.bis-d, entry 177).
 *
 * 5 endpoint:
 * - GET  /pde/status            — riepilogo PdE corrente
 * - POST /pde/base               — upload PdE base annuale (multipart)
 * - POST /variazioni             — registra metadati variazione
 * - GET  /variazioni             — timeline variazioni globali
 * - POST /variazioni/{id}/applica — upload + applica file delta (multipart)
 *
 * Tipi allineati a `colazione.schemas.programmi` (PdEStatusRead,
 * CaricaPdEBaseResponse, CorsaImportRunRead, ApplicaVariazionePdEResponse,
 * VariazionePdERequest).
 */

import { ApiError, apiFetch, apiJson } from "@/lib/api/client";

export type TipoVariazione =
  | "INTEGRAZIONE"
  | "VARIAZIONE_INTERRUZIONE"
  | "VARIAZIONE_ORARIO"
  | "VARIAZIONE_CANCELLAZIONE";

export interface CorsaImportRun {
  id: number;
  source_file: string;
  source_hash: string | null;
  n_corse: number;
  n_corse_create: number;
  n_corse_update: number;
  azienda_id: number;
  started_at: string;
  completed_at: string | null;
  note: string | null;
  programma_materiale_id: number | null;
  tipo: string;
}

export interface PdEStatus {
  base_run: CorsaImportRun | null;
  n_corse_attive: number;
  n_corse_totali: number;
  n_variazioni_totali: number;
  n_variazioni_applicate: number;
  ultima_variazione_at: string | null;
  validity_da: string | null;
  validity_a: string | null;
}

export interface CaricaPdEBaseResponse {
  skipped: boolean;
  skip_reason: string | null;
  run_id: number | null;
  n_total: number;
  n_create: number;
  n_delete: number;
  n_kept: number;
  n_warnings: number;
  duration_s: number;
}

export interface RegistraVariazionePayload {
  tipo: TipoVariazione;
  source_file: string;
  n_corse?: number;
  note?: string | null;
}

export interface ApplicaVariazioneResponse {
  run_id: number;
  tipo: string;
  n_corse_lette_da_file: number;
  n_corse_create: number;
  n_corse_update: number;
  n_warnings: number;
  warnings: string[];
  completed_at: string;
}

// =====================================================================
// Calls
// =====================================================================

export async function getPdEStatus(): Promise<PdEStatus> {
  return apiJson<PdEStatus>("/api/aziende/me/pde/status", { method: "GET" });
}

/**
 * Upload PdE base annuale via multipart. Backend wrappa
 * `importa_pde` (CLI-equivalent), idempotente per SHA-256 file.
 *
 * Tempo atteso: 25-30s su PdE Trenord intero (10580 corse). Il client
 * non imposta timeout esplicito; affida a default browser/proxy.
 */
export async function caricaPdEBase(
  file: File,
  options: { force?: boolean } = {},
): Promise<CaricaPdEBaseResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const path = options.force === true
    ? "/api/aziende/me/pde/base?force=true"
    : "/api/aziende/me/pde/base";

  const res = await apiFetch(path, {
    method: "POST",
    body: formData as unknown as BodyInit,
    // FormData richiede che NON impostiamo Content-Type: il browser
    // genera multipart/form-data con boundary corretto.
    headers: {},
  });
  if (!res.ok) {
    let detail: unknown = null;
    try {
      detail = await res.json();
    } catch {
      // ignore
    }
    const detailObj = detail as { detail?: string | unknown } | null;
    const detailVal = detailObj?.detail;
    const msg =
      typeof detailVal === "string"
        ? detailVal
        : detailVal !== undefined
          ? JSON.stringify(detailVal)
          : `HTTP ${res.status}`;
    throw new ApiError(res.status, msg, detailVal);
  }
  return (await res.json()) as CaricaPdEBaseResponse;
}

export async function registraVariazione(
  payload: RegistraVariazionePayload,
): Promise<CorsaImportRun> {
  return apiJson<CorsaImportRun>("/api/aziende/me/variazioni", {
    method: "POST",
    body: payload,
  });
}

export async function listVariazioni(
  params: { limit?: number } = {},
): Promise<CorsaImportRun[]> {
  const query =
    params.limit !== undefined ? `?limit=${params.limit}` : "";
  return apiJson<CorsaImportRun[]>(
    `/api/aziende/me/variazioni${query}`,
    { method: "GET" },
  );
}

export async function applicaVariazione(
  runId: number,
  file: File,
): Promise<ApplicaVariazioneResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await apiFetch(
    `/api/aziende/me/variazioni/${runId}/applica`,
    {
      method: "POST",
      body: formData as unknown as BodyInit,
      headers: {},
    },
  );
  if (!res.ok) {
    let detail: unknown = null;
    try {
      detail = await res.json();
    } catch {
      // ignore
    }
    const detailObj = detail as { detail?: string | unknown } | null;
    const detailVal = detailObj?.detail;
    const msg =
      typeof detailVal === "string"
        ? detailVal
        : detailVal !== undefined
          ? JSON.stringify(detailVal)
          : `HTTP ${res.status}`;
    throw new ApiError(res.status, msg, detailVal);
  }
  return (await res.json()) as ApplicaVariazioneResponse;
}
