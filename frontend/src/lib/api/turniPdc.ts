import { apiJson } from "@/lib/api/client";

/**
 * Sprint 7.4 MR 3: campi split CV intermedio condivisi fra
 * `TurnoPdcGenerazioneResponse` e `TurnoPdcListItem`.
 *
 * `is_ramo_split` è `true` quando il TurnoPdc è il ramo di una
 * giornata-giro splittata in più rami; quando true, gli altri 3
 * campi sono valorizzati. `false` per il TurnoPdc principale (o per
 * giri/giornate che non richiedono split CV).
 */
export interface SplitCvFields {
  is_ramo_split: boolean;
  split_origine_giornata: number | null;
  split_ramo: number | null;
  split_totale_rami: number | null;
}

export interface TurnoPdcGenerazioneResponse extends SplitCvFields {
  turno_pdc_id: number;
  codice: string;
  n_giornate: number;
  prestazione_totale_min: number;
  condotta_totale_min: number;
  violazioni: string[];
  warnings: string[];
}

export interface TurnoPdcListItem extends SplitCvFields {
  id: number;
  codice: string;
  impianto: string;
  profilo: string;
  ciclo_giorni: number;
  valido_da: string;
  stato: string;
  created_at: string;
  n_giornate: number;
  prestazione_totale_min: number;
  condotta_totale_min: number;
  n_violazioni: number;
  n_dormite_fr: number;
}

export interface TurnoPdcBlocco {
  id: number;
  seq: number;
  tipo_evento: string;
  corsa_commerciale_id: number | null;
  corsa_materiale_vuoto_id: number | null;
  giro_blocco_id: number | null;
  stazione_da_codice: string | null;
  stazione_a_codice: string | null;
  stazione_da_nome: string | null;
  stazione_a_nome: string | null;
  numero_treno: string | null;
  numero_treno_variante_indice: number | null;
  numero_treno_variante_totale: number | null;
  ora_inizio: string | null;
  ora_fine: string | null;
  durata_min: number | null;
  is_accessori_maggiorati: boolean;
  accessori_note: string | null;
  fonte_orario: string;
}

export interface TurnoPdcGiornata {
  id: number;
  numero_giornata: number;
  variante_calendario: string;
  stazione_inizio: string | null;
  stazione_fine: string | null;
  stazione_inizio_nome: string | null;
  stazione_fine_nome: string | null;
  inizio_prestazione: string | null;
  fine_prestazione: string | null;
  prestazione_min: number;
  condotta_min: number;
  refezione_min: number;
  is_notturno: boolean;
  blocchi: TurnoPdcBlocco[];
}

export interface FrGiornata {
  giornata: number;
  stazione: string;
  ore: number;
}

export interface TurnoPdcDettaglio {
  id: number;
  codice: string;
  impianto: string;
  profilo: string;
  ciclo_giorni: number;
  valido_da: string;
  stato: string;
  created_at: string;
  updated_at: string;
  generation_metadata_json: {
    giro_materiale_id?: number;
    giro_numero_turno?: string;
    violazioni?: string[];
    fr_giornate?: FrGiornata[];
    stazione_sede?: string;
    builder_version?: string;
    [key: string]: unknown;
  };
  giornate: TurnoPdcGiornata[];
}

export interface GeneraTurnoPdcParams {
  valido_da?: string;
  force?: boolean;
}

export async function generaTurnoPdc(
  giroId: number,
  params: GeneraTurnoPdcParams = {},
): Promise<TurnoPdcGenerazioneResponse[]> {
  // Sprint 7.5 MR 5 (decisione utente D1): l'endpoint ora ritorna una
  // lista di turni PdC (1 per combinazione di varianti calendario del
  // giro). Con A1 strict default = 1 elemento; con varianti multiple
  // aggiunte manualmente la lista cresce.
  const search = new URLSearchParams();
  if (params.valido_da !== undefined) search.set("valido_da", params.valido_da);
  if (params.force === true) search.set("force", "true");
  const qs = search.toString();
  return apiJson<TurnoPdcGenerazioneResponse[]>(
    `/api/giri/${giroId}/genera-turno-pdc${qs ? `?${qs}` : ""}`,
    { method: "POST" },
  );
}

export async function listTurniPdcGiro(giroId: number): Promise<TurnoPdcListItem[]> {
  return apiJson<TurnoPdcListItem[]>(`/api/giri/${giroId}/turni-pdc`, { method: "GET" });
}

export async function getTurnoPdcDettaglio(turnoId: number): Promise<TurnoPdcDettaglio> {
  return apiJson<TurnoPdcDettaglio>(`/api/turni-pdc/${turnoId}`, { method: "GET" });
}
