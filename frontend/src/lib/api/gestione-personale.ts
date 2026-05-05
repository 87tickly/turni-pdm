/**
 * Wrapper API per il ruolo GESTIONE_PERSONALE (Sprint 7.9 MR ζ).
 *
 * Endpoint read-side per popolare la dashboard:
 * - /api/persone (lista anagrafica con filtri)
 * - /api/persone/:id (scheda persona)
 * - /api/depots/:codice/persone (drilldown deposito)
 * - /api/indisponibilita (ferie/malattie/ROL)
 * - /api/gestione-personale/kpi (riepilogo)
 * - /api/gestione-personale/kpi-depositi (breakdown per deposito)
 *
 * Multi-tenant: azienda dal JWT, niente input client.
 */

import { apiJson } from "@/lib/api/client";

export interface PersonaWithDepositoRead {
  id: number;
  codice_dipendente: string;
  nome: string;
  cognome: string;
  profilo: string;
  is_matricola_attiva: boolean;
  data_assunzione: string | null;
  depot_codice: string | null;
  depot_display_name: string | null;
  qualifiche: string[];
  /** Tipo indisponibilità in corso oggi (ferie/malattia/ROL/...), o null se in servizio. */
  indisponibilita_oggi: string | null;
}

export interface IndisponibilitaWithPersonaRead {
  id: number;
  persona_id: number;
  persona_nome: string;
  persona_cognome: string;
  persona_codice_dipendente: string;
  depot_codice: string | null;
  depot_display_name: string | null;
  tipo: string;
  data_inizio: string;
  data_fine: string;
  giorni_totali: number;
  is_approvato: boolean;
  note: string | null;
}

export interface GestionePersonaleKpiRead {
  persone_attive: number;
  in_servizio_oggi: number;
  in_ferie: number;
  in_malattia: number;
  in_rol: number;
  in_altra_assenza: number;
  copertura_pct: number;
}

export interface GestionePersonaleKpiPerDepositoRead {
  depot_codice: string;
  depot_display_name: string;
  persone_attive: number;
  in_servizio_oggi: number;
  indisponibili_oggi: number;
  copertura_pct: number;
}

export interface ListPersoneParams {
  depot?: string;
  profilo?: string;
  search?: string;
  only_active?: boolean;
}

function _query(params: Record<string, string | boolean | undefined>): string {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined) continue;
    usp.set(k, String(v));
  }
  const s = usp.toString();
  return s.length > 0 ? `?${s}` : "";
}

export async function listPersone(
  params: ListPersoneParams = {},
): Promise<PersonaWithDepositoRead[]> {
  return apiJson<PersonaWithDepositoRead[]>(
    `/api/persone${_query({ ...params })}`,
    { method: "GET" },
  );
}

export async function getPersona(id: number): Promise<PersonaWithDepositoRead> {
  return apiJson<PersonaWithDepositoRead>(`/api/persone/${id}`, { method: "GET" });
}

export async function listPersoneByDepot(
  depotCodice: string,
): Promise<PersonaWithDepositoRead[]> {
  return apiJson<PersonaWithDepositoRead[]>(
    `/api/depots/${encodeURIComponent(depotCodice)}/persone`,
    { method: "GET" },
  );
}

export interface ListIndisponibilitaParams {
  tipo?: string;
  attive_oggi?: boolean;
  depot?: string;
}

export async function listIndisponibilita(
  params: ListIndisponibilitaParams = {},
): Promise<IndisponibilitaWithPersonaRead[]> {
  return apiJson<IndisponibilitaWithPersonaRead[]>(
    `/api/indisponibilita${_query({ ...params })}`,
    { method: "GET" },
  );
}

export async function getGestionePersonaleKpi(): Promise<GestionePersonaleKpiRead> {
  return apiJson<GestionePersonaleKpiRead>("/api/gestione-personale/kpi", {
    method: "GET",
  });
}

export async function getGestionePersonaleKpiDepositi(): Promise<
  GestionePersonaleKpiPerDepositoRead[]
> {
  return apiJson<GestionePersonaleKpiPerDepositoRead[]>(
    "/api/gestione-personale/kpi-depositi",
    { method: "GET" },
  );
}
