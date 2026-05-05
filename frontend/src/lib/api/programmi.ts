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

/**
 * Sprint 8.0 MR 0 (entry 164): pipeline state machine ramo PdC.
 * Mantenere allineato con `colazione.domain.pipeline.StatoPipelinePdc`.
 */
export type StatoPipelinePdc =
  | "PDE_IN_LAVORAZIONE"
  | "PDE_CONSOLIDATO"
  | "MATERIALE_GENERATO"
  | "MATERIALE_CONFERMATO"
  | "PDC_GENERATO"
  | "PDC_CONFERMATO"
  | "PERSONALE_ASSEGNATO"
  | "VISTA_PUBBLICATA";

/**
 * Sprint 8.0 MR 0 (entry 164): pipeline state machine ramo Manutenzione.
 * Mantenere allineato con `colazione.domain.pipeline.StatoManutenzione`.
 */
export type StatoManutenzione =
  | "IN_ATTESA"
  | "IN_LAVORAZIONE"
  | "MATRICOLE_ASSEGNATE";

const STATI_PIPELINE_PDC_ORDER: ReadonlyArray<StatoPipelinePdc> = [
  "PDE_IN_LAVORAZIONE",
  "PDE_CONSOLIDATO",
  "MATERIALE_GENERATO",
  "MATERIALE_CONFERMATO",
  "PDC_GENERATO",
  "PDC_CONFERMATO",
  "PERSONALE_ASSEGNATO",
  "VISTA_PUBBLICATA",
];

/**
 * Sprint 8.0 MR 1 (entry 165): replica della logica `materiale_freezato`
 * server-side. Quando `True`, il pianificatore non può modificare
 * regole/parametri/giri (PATCH/POST regole/genera-giri ritornano 409).
 */
export function materialeFreezato(stato: StatoPipelinePdc): boolean {
  const idx = STATI_PIPELINE_PDC_ORDER.indexOf(stato);
  const soglia = STATI_PIPELINE_PDC_ORDER.indexOf("MATERIALE_CONFERMATO");
  return idx >= 0 && idx >= soglia;
}

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
  /** Sprint 8.0 MR 0 (entry 164): stato pipeline ramo PdC. */
  stato_pipeline_pdc: StatoPipelinePdc;
  /** Sprint 8.0 MR 0 (entry 164): stato pipeline ramo Manutenzione. */
  stato_manutenzione: StatoManutenzione;
  km_max_giornaliero: number | null;
  km_max_ciclo: number | null;
  n_giornate_default: number;
  /** Sprint 7.8: lunghezza minima dei giri (soft, sotto solo per chiusure). */
  n_giornate_min: number;
  /** Sprint 7.8: lunghezza massima dei giri (hard cap). */
  n_giornate_max: number;
  fascia_oraria_tolerance_min: number;
  strict_options_json: StrictOptions;
  stazioni_sosta_extra_json: string[];
  created_by_user_id: number | null;
  /** Backend entry 88: popolato via JOIN con `app_user`, `null` se utente eliminato. */
  created_by_username: string | null;
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
  /** Sprint 7.8: default 4. */
  n_giornate_min?: number;
  /** Sprint 7.8: default 12. */
  n_giornate_max?: number;
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
  /** Sprint 7.8: aggiorna lunghezza minima (soft) dei giri. */
  n_giornate_min?: number;
  /** Sprint 7.8: aggiorna lunghezza massima (hard) dei giri. */
  n_giornate_max?: number;
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

// =====================================================================
// Builder run (Sprint 7.9 MR 11C, entry 116)
// =====================================================================

export interface BuilderRunRead {
  id: number;
  programma_id: number;
  localita_codice: string;
  eseguito_at: string;
  eseguito_da_user_id: number | null;
  n_giri_creati: number;
  n_giri_chiusi: number;
  n_giri_non_chiusi: number;
  n_corse_processate: number;
  n_corse_residue: number;
  n_eventi_composizione: number;
  n_incompatibilita_materiale: number;
  warnings_json: string[];
  force: boolean;
}

export async function getLastBuilderRun(
  programmaId: number,
): Promise<BuilderRunRead | null> {
  return apiJson<BuilderRunRead | null>(
    `/api/programmi/${programmaId}/last-run`,
    { method: "GET" },
  );
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

// =====================================================================
// Pipeline state machine — Sprint 8.0 MR 0 (entry 164)
// =====================================================================

export interface SbloccaProgrammaPayload {
  ramo: "pdc" | "manutenzione";
  motivo?: string | null;
}

export async function confermaMateriale(id: number): Promise<ProgrammaMaterialeRead> {
  return apiJson<ProgrammaMaterialeRead>(`/api/programmi/${id}/conferma-materiale`, {
    method: "POST",
  });
}

export async function confermaPdc(id: number): Promise<ProgrammaMaterialeRead> {
  return apiJson<ProgrammaMaterialeRead>(`/api/programmi/${id}/conferma-pdc`, {
    method: "POST",
  });
}

export async function confermaPersonale(id: number): Promise<ProgrammaMaterialeRead> {
  return apiJson<ProgrammaMaterialeRead>(`/api/programmi/${id}/conferma-personale`, {
    method: "POST",
  });
}

export async function pubblicaVistaPdc(id: number): Promise<ProgrammaMaterialeRead> {
  return apiJson<ProgrammaMaterialeRead>(`/api/programmi/${id}/pubblica-vista-pdc`, {
    method: "POST",
  });
}

export async function confermaManutenzione(id: number): Promise<ProgrammaMaterialeRead> {
  return apiJson<ProgrammaMaterialeRead>(
    `/api/programmi/${id}/conferma-manutenzione`,
    { method: "POST" },
  );
}

export async function sbloccaProgramma(
  id: number,
  payload: SbloccaProgrammaPayload,
): Promise<ProgrammaMaterialeRead> {
  return apiJson<ProgrammaMaterialeRead>(`/api/programmi/${id}/sblocca`, {
    method: "POST",
    body: payload,
  });
}

// =====================================================================
// Auto-assegna persone — Sub-MR 2.bis-a (Sprint 8.0)
// =====================================================================

/**
 * Body per `POST /api/programmi/{id}/auto-assegna-persone`.
 *
 * Entrambi i campi sono opzionali. Se omessi, il backend usa
 * `programma.valido_da` / `programma.valido_a`. Le date sono ISO
 * `YYYY-MM-DD`. Validatore Pydantic richiede `data_da ≤ data_a`.
 */
export interface AutoAssegnaPersonePayload {
  data_da?: string | null;
  data_a?: string | null;
}

/** Una nuova assegnazione persona → giornata creata dal greedy. */
export interface AssegnazioneCreata {
  persona_id: number;
  turno_pdc_giornata_id: number;
  data: string;
}

/**
 * Una giornata non coperta dall'algoritmo + motivo. Allineato con enum
 * server-side `MotivoMancanza` (vedi
 * `colazione.domain.normativa.assegnazione_persone`).
 */
export type MotivoMancanza =
  | "nessun_pdc_deposito"
  | "tutti_indisponibili"
  | "tutti_gia_assegnati"
  | "tutti_riposo_intraturno_violato"
  | "nessun_pdc_candidato";

export interface MancanzaAuto {
  turno_pdc_giornata_id: number;
  turno_pdc_id: number;
  data: string;
  motivo: MotivoMancanza;
}

/**
 * Tipo del warning soft. Allineato con enum server-side `TipoWarningSoft`.
 */
export type TipoWarningSoft =
  | "fr_cap_settimana_superato"
  | "fr_cap_28gg_superato"
  | "riposo_settimanale_violato"
  | "primo_giorno_post_riposo_mattina";

export interface WarningSoft {
  persona_id: number;
  data: string;
  tipo: TipoWarningSoft;
  descrizione: string;
}

/** Response dell'auto-assegna. KPI principale: `delta_copertura_pct`. */
export interface AutoAssegnaPersoneResponse {
  finestra_data_da: string;
  finestra_data_a: string;
  n_giornate_totali: number;
  n_giornate_coperte: number;
  n_assegnazioni_create: number;
  delta_copertura_pct: number;
  assegnazioni: AssegnazioneCreata[];
  mancanze: MancanzaAuto[];
  warning_soft: WarningSoft[];
}

export async function autoAssegnaPersone(
  id: number,
  payload: AutoAssegnaPersonePayload,
): Promise<AutoAssegnaPersoneResponse> {
  return apiJson<AutoAssegnaPersoneResponse>(
    `/api/programmi/${id}/auto-assegna-persone`,
    { method: "POST", body: payload },
  );
}

// =====================================================================
// Assegna manuale (override) — Sub-MR 2.bis-b (Sprint 8.0)
// =====================================================================

/**
 * Body per `POST /api/programmi/{id}/assegna-manuale`.
 *
 * Override consapevole del pianificatore: bypassa i vincoli HARD del
 * greedy (sede, indisp, riposo intraturno) ma rispetta uniqueness
 * (no doppia persona/data, no doppia giornata/data).
 */
export interface AssegnaManualePayload {
  persona_id: number;
  turno_pdc_giornata_id: number;
  /** ISO YYYY-MM-DD. */
  data: string;
}

export async function assegnaManuale(
  id: number,
  payload: AssegnaManualePayload,
): Promise<AssegnazioneCreata> {
  return apiJson<AssegnazioneCreata>(
    `/api/programmi/${id}/assegna-manuale`,
    { method: "POST", body: payload },
  );
}
