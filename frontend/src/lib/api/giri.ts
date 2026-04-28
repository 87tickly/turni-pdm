/**
 * Wrapper API per i giri materiale (Sprint 4.4.5b backend +
 * Sprint 5.6 R1 read-side).
 *
 * Endpoint:
 *   POST /api/programmi/{id}/genera-giri  → lancia il builder
 *   GET  /api/programmi/{id}/giri         → lista giri del programma
 *   GET  /api/giri/{id}                   → dettaglio Gantt giro
 *
 * Tipi allineati a `colazione.api.giri` (BuilderResultResponse,
 * GiroMaterialeListItem, GiroMaterialeDettaglioRead).
 */

import { apiJson } from "@/lib/api/client";

export interface BuilderResult {
  giri_ids: number[];
  n_giri_creati: number;
  n_corse_processate: number;
  n_corse_residue: number;
  n_giri_chiusi: number;
  n_giri_non_chiusi: number;
  n_eventi_composizione: number;
  n_incompatibilita_materiale: number;
  warnings: string[];
}

export interface GeneraGiriParams {
  data_inizio: string;
  n_giornate: number;
  localita_codice: string;
  force?: boolean;
}

export interface GiroListItem {
  id: number;
  numero_turno: string;
  tipo_materiale: string;
  materiale_tipo_codice: string | null;
  numero_giornate: number;
  km_media_giornaliera: number | null;
  km_media_annua: number | null;
  motivo_chiusura: string | null;
  chiuso: boolean;
  stato: string;
  created_at: string;
}

export interface GiroBlocco {
  id: number;
  seq: number;
  tipo_blocco: string;
  corsa_commerciale_id: number | null;
  corsa_materiale_vuoto_id: number | null;
  stazione_da_codice: string | null;
  stazione_a_codice: string | null;
  stazione_da_nome: string | null;
  stazione_a_nome: string | null;
  numero_treno: string | null;
  ora_inizio: string | null;
  ora_fine: string | null;
  descrizione: string | null;
  is_validato_utente: boolean;
  metadata_json: Record<string, unknown>;
}

export interface GiroVariante {
  id: number;
  variant_index: number;
  validita_testo: string | null;
  validita_dates_apply_json: unknown[];
  validita_dates_skip_json: unknown[];
  blocchi: GiroBlocco[];
}

export interface GiroGiornata {
  id: number;
  numero_giornata: number;
  varianti: GiroVariante[];
}

export interface GiroDettaglio {
  id: number;
  numero_turno: string;
  tipo_materiale: string;
  materiale_tipo_codice: string | null;
  numero_giornate: number;
  km_media_giornaliera: number | null;
  km_media_annua: number | null;
  localita_manutenzione_partenza_id: number | null;
  localita_manutenzione_arrivo_id: number | null;
  stato: string;
  generation_metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  giornate: GiroGiornata[];
}

export async function generaGiri(
  programmaId: number,
  params: GeneraGiriParams,
): Promise<BuilderResult> {
  const search = new URLSearchParams();
  search.set("data_inizio", params.data_inizio);
  search.set("n_giornate", String(params.n_giornate));
  search.set("localita_codice", params.localita_codice);
  if (params.force === true) search.set("force", "true");
  return apiJson<BuilderResult>(`/api/programmi/${programmaId}/genera-giri?${search.toString()}`, {
    method: "POST",
  });
}

export async function listGiriProgramma(programmaId: number): Promise<GiroListItem[]> {
  return apiJson<GiroListItem[]>(`/api/programmi/${programmaId}/giri`, { method: "GET" });
}

export async function getGiroDettaglio(giroId: number): Promise<GiroDettaglio> {
  return apiJson<GiroDettaglio>(`/api/giri/${giroId}`, { method: "GET" });
}
