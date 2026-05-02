/**
 * Wrapper API per `/api/programmi/*` (Sprint 4.3 backend).
 *
 * Tipi allineati a `colazione.schemas.programmi`:
 * - `ProgrammaMaterialeRead` / `ProgrammaDettaglioRead`
 * - `ProgrammaMaterialeCreate` / `ProgrammaMaterialeUpdate`
 * - `ProgrammaRegolaAssegnazioneRead`
 *
 * Le date sono ISO `YYYY-MM-DD`; i timestamp `created_at`/`updated_at`
 * sono ISO 8601 con timezone.
 */

import { apiJson } from "@/lib/api/client";

export type ProgrammaStato = "bozza" | "attivo" | "archiviato";

export interface StrictOptions {
  no_corse_residue: boolean;
  no_overcapacity: boolean;
  no_aggancio_non_validato: boolean;
  no_orphan_blocks: boolean;
  no_giro_appeso: boolean;
  no_km_eccesso: boolean;
}

export interface ProgrammaMaterialeRead {
  id: number;
  azienda_id: number;
  nome: string;
  valido_da: string;
  valido_a: string;
  stato: ProgrammaStato;
  km_max_giornaliero: number | null;
  km_max_ciclo: number | null;
  n_giornate_default: number;
  fascia_oraria_tolerance_min: number;
  strict_options_json: StrictOptions;
  stazioni_sosta_extra_json: string[];
  created_by_user_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface FiltroRegolaPayload {
  campo: string;
  op: string;
  valore: unknown;
}

export interface ComposizioneItemPayload {
  materiale_tipo_codice: string;
  n_pezzi: number;
}

export interface ProgrammaRegolaAssegnazioneRead {
  id: number;
  programma_id: number;
  filtri_json: FiltroRegolaPayload[];
  composizione_json: ComposizioneItemPayload[];
  is_composizione_manuale: boolean;
  materiale_tipo_codice: string | null;
  numero_pezzi: number | null;
  priorita: number;
  /** Sprint 7.7 MR 1: cap km del ciclo specifico per regola (es. ETR526 ~4500). */
  km_max_ciclo: number | null;
  note: string | null;
  created_at: string;
}

export interface ProgrammaDettaglioRead extends ProgrammaMaterialeRead {
  regole: ProgrammaRegolaAssegnazioneRead[];
}

export interface ProgrammaRegolaAssegnazioneCreate {
  filtri_json?: FiltroRegolaPayload[];
  composizione: ComposizioneItemPayload[];
  is_composizione_manuale?: boolean;
  priorita?: number;
  /** Sprint 7.7 MR 1: cap km del ciclo specifico per regola (opzionale). */
  km_max_ciclo?: number | null;
  note?: string | null;
}

export interface ProgrammaMaterialeCreate {
  nome: string;
  valido_da: string;
  valido_a: string;
  km_max_giornaliero?: number | null;
  km_max_ciclo?: number | null;
  n_giornate_default?: number;
  fascia_oraria_tolerance_min?: number;
  strict_options_json?: Partial<StrictOptions>;
  stazioni_sosta_extra_json?: string[];
  regole?: ProgrammaRegolaAssegnazioneCreate[];
}

export interface ProgrammaMaterialeUpdate {
  nome?: string;
  valido_da?: string;
  valido_a?: string;
  km_max_giornaliero?: number | null;
  km_max_ciclo?: number | null;
  n_giornate_default?: number;
  fascia_oraria_tolerance_min?: number;
  strict_options_json?: Partial<StrictOptions>;
  stazioni_sosta_extra_json?: string[];
}

export interface ListProgrammiParams {
  stato?: ProgrammaStato;
}

function buildQuery(params: ListProgrammiParams): string {
  const search = new URLSearchParams();
  if (params.stato !== undefined) search.set("stato", params.stato);
  const qs = search.toString();
  return qs.length > 0 ? `?${qs}` : "";
}

export async function listProgrammi(
  params: ListProgrammiParams = {},
): Promise<ProgrammaMaterialeRead[]> {
  return apiJson<ProgrammaMaterialeRead[]>(`/api/programmi${buildQuery(params)}`, {
    method: "GET",
  });
}

export async function getProgramma(id: number): Promise<ProgrammaDettaglioRead> {
  return apiJson<ProgrammaDettaglioRead>(`/api/programmi/${id}`, { method: "GET" });
}

export async function createProgramma(
  payload: ProgrammaMaterialeCreate,
): Promise<ProgrammaMaterialeRead> {
  return apiJson<ProgrammaMaterialeRead>("/api/programmi", {
    method: "POST",
    body: payload,
  });
}

export async function updateProgramma(
  id: number,
  payload: ProgrammaMaterialeUpdate,
): Promise<ProgrammaMaterialeRead> {
  return apiJson<ProgrammaMaterialeRead>(`/api/programmi/${id}`, {
    method: "PATCH",
    body: payload,
  });
}

export async function pubblicaProgramma(id: number): Promise<ProgrammaMaterialeRead> {
  return apiJson<ProgrammaMaterialeRead>(`/api/programmi/${id}/pubblica`, {
    method: "POST",
  });
}

export async function archiviaProgramma(id: number): Promise<ProgrammaMaterialeRead> {
  return apiJson<ProgrammaMaterialeRead>(`/api/programmi/${id}/archivia`, {
    method: "POST",
  });
}

export async function addRegola(
  programmaId: number,
  payload: ProgrammaRegolaAssegnazioneCreate,
): Promise<ProgrammaRegolaAssegnazioneRead> {
  return apiJson<ProgrammaRegolaAssegnazioneRead>(`/api/programmi/${programmaId}/regole`, {
    method: "POST",
    body: payload,
  });
}

export async function deleteRegola(programmaId: number, regolaId: number): Promise<void> {
  await apiJson<void>(`/api/programmi/${programmaId}/regole/${regolaId}`, {
    method: "DELETE",
  });
}
