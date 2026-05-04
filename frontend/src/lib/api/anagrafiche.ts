/**
 * Wrapper API per `/api/{stazioni,materiali,depots,direttrici,
 * localita-manutenzione}` (Sprint 5.6 R1, read-side).
 *
 * Usato dai menu a tendina dell'editor regola e dal selettore sede
 * del programma. Tutti gli endpoint sono multi-tenant (azienda dal JWT)
 * e richiedono ruolo PIANIFICATORE_GIRO (admin bypassa).
 */

import { apiJson } from "@/lib/api/client";

export interface StazioneRead {
  codice: string;
  nome: string;
}

export interface MaterialeRead {
  codice: string;
  nome_commerciale: string | null;
  famiglia: string | null;
  /** Sprint 7.9 MR 7D: pezzi singoli in dotazione per l'azienda corrente.
   * `null` = capacity illimitata (es. ETR524 FLIRT TILO) o non registrata.
   */
  pezzi_disponibili: number | null;
}

export interface DepotRead {
  codice: string;
  display_name: string;
  stazione_principale_codice: string | null;
}

export interface LocalitaManutenzioneRead {
  codice: string;
  codice_breve: string | null;
  nome_canonico: string;
  stazione_collegata_codice: string | null;
  is_pool_esterno: boolean;
}

export async function listStazioni(): Promise<StazioneRead[]> {
  return apiJson<StazioneRead[]>("/api/stazioni", { method: "GET" });
}

export async function listMateriali(): Promise<MaterialeRead[]> {
  return apiJson<MaterialeRead[]>("/api/materiali", { method: "GET" });
}

export async function listDepots(): Promise<DepotRead[]> {
  return apiJson<DepotRead[]>("/api/depots", { method: "GET" });
}

export async function listDirettrici(): Promise<string[]> {
  return apiJson<string[]>("/api/direttrici", { method: "GET" });
}

export async function listLocalitaManutenzione(): Promise<LocalitaManutenzioneRead[]> {
  return apiJson<LocalitaManutenzioneRead[]>("/api/localita-manutenzione", {
    method: "GET",
  });
}

// =====================================================================
// Sprint 7.9 MR β2-0 + β2-1 — LocalitaSosta + MaterialeIstanza
// =====================================================================

export interface LocalitaSostaRead {
  id: number;
  codice: string;
  nome: string;
  stazione_collegata_codice: string | null;
  is_attiva: boolean;
  note: string | null;
}

export async function listLocalitaSosta(): Promise<LocalitaSostaRead[]> {
  return apiJson<LocalitaSostaRead[]>("/api/localita-sosta", { method: "GET" });
}

export interface MaterialeIstanzaRead {
  id: number;
  tipo_materiale_codice: string;
  matricola: string;
  sede_codice: string | null;
  stato: string;
  note: string | null;
}

export async function listMaterialeIstanze(
  params: { tipo_materiale_codice?: string; sede_codice?: string } = {},
): Promise<MaterialeIstanzaRead[]> {
  const search = new URLSearchParams();
  if (params.tipo_materiale_codice !== undefined) {
    search.set("tipo_materiale_codice", params.tipo_materiale_codice);
  }
  if (params.sede_codice !== undefined) {
    search.set("sede_codice", params.sede_codice);
  }
  const qs = search.toString();
  return apiJson<MaterialeIstanzaRead[]>(
    `/api/materiale-istanze${qs.length > 0 ? `?${qs}` : ""}`,
    { method: "GET" },
  );
}

// =====================================================================
// Sprint 7.9 MR β2-7 — Regole pre-builder invio a sosta intermedia
// =====================================================================

export interface RegolaInvioSostaRead {
  id: number;
  programma_id: number;
  stazione_sgancio_codice: string;
  tipo_materiale_codice: string;
  /** Formato "HH:MM:SS" o "HH:MM". */
  finestra_oraria_inizio: string;
  finestra_oraria_fine: string;
  localita_sosta_id: number;
  fallback_sosta_id: number | null;
  note: string | null;
}

export interface RegolaInvioSostaCreate {
  stazione_sgancio_codice: string;
  tipo_materiale_codice: string;
  finestra_oraria_inizio: string;
  finestra_oraria_fine: string;
  localita_sosta_id: number;
  fallback_sosta_id?: number | null;
  note?: string | null;
}

export async function listRegoleInvioSosta(
  programmaId: number,
): Promise<RegolaInvioSostaRead[]> {
  return apiJson<RegolaInvioSostaRead[]>(
    `/api/programmi/${programmaId}/regole-invio-sosta`,
    { method: "GET" },
  );
}

export async function createRegolaInvioSosta(
  programmaId: number,
  body: RegolaInvioSostaCreate,
): Promise<RegolaInvioSostaRead> {
  return apiJson<RegolaInvioSostaRead>(
    `/api/programmi/${programmaId}/regole-invio-sosta`,
    { method: "POST", body },
  );
}

export async function deleteRegolaInvioSosta(
  programmaId: number,
  regolaId: number,
): Promise<void> {
  await apiJson<void>(
    `/api/programmi/${programmaId}/regole-invio-sosta/${regolaId}`,
    { method: "DELETE" },
  );
}

// =====================================================================
// Sprint 7.7 MR 2 — Calendario ufficiale festività
// =====================================================================

export interface FestivitaRead {
  /** ISO date `YYYY-MM-DD`. */
  data: string;
  nome: string;
  /** "nazionale" | "religiosa" | "patronale" */
  tipo: string;
  /** NULL = festività nazionale; altrimenti azienda-specifica (es. patrono). */
  azienda_id: number | null;
}

export interface CalendarioRead {
  anno: number;
  festivita: FestivitaRead[];
}

/**
 * Festività dell'anno per l'azienda corrente (nazionali + locali).
 *
 * Anni seedati nella migration 0015: 2025-2030. Anni fuori range
 * → 404. Per anni futuri estendere la migration.
 */
export async function getCalendario(anno: number): Promise<CalendarioRead> {
  return apiJson<CalendarioRead>(`/api/calendario/${anno}`, { method: "GET" });
}
