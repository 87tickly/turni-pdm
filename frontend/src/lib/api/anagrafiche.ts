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
