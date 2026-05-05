/**
 * React Query hooks per il ruolo GESTIONE_PERSONALE (Sprint 7.9 MR ζ).
 *
 * `staleTime: 30s` per le liste persone/indisponibilità — più volatili
 * rispetto alle anagrafiche pure (aggiornamenti durante il giorno
 * lavorativo per ferie/malattie segnalate). I KPI sono ricalcolati
 * server-side ogni richiesta, quindi anch'essi ~30s.
 */

import {
  useQuery,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  getGestionePersonaleKpi,
  getGestionePersonaleKpiDepositi,
  getPersona,
  listIndisponibilita,
  listPersone,
  listPersoneByDepot,
  type GestionePersonaleKpiPerDepositoRead,
  type GestionePersonaleKpiRead,
  type IndisponibilitaWithPersonaRead,
  type ListIndisponibilitaParams,
  type ListPersoneParams,
  type PersonaWithDepositoRead,
} from "@/lib/api/gestione-personale";

const HALF_MIN = 30 * 1000;
const FIVE_MIN = 5 * 60 * 1000;

export function usePersone(
  params: ListPersoneParams = {},
): UseQueryResult<PersonaWithDepositoRead[]> {
  return useQuery({
    queryKey: ["gestione-personale", "persone", params],
    queryFn: () => listPersone(params),
    staleTime: HALF_MIN,
  });
}

export function usePersona(
  id: number | undefined,
): UseQueryResult<PersonaWithDepositoRead> {
  return useQuery({
    queryKey: ["gestione-personale", "persona", id],
    queryFn: () => {
      if (id === undefined) throw new Error("id mancante");
      return getPersona(id);
    },
    enabled: id !== undefined,
    staleTime: HALF_MIN,
  });
}

export function usePersoneByDepot(
  depotCodice: string | undefined,
): UseQueryResult<PersonaWithDepositoRead[]> {
  return useQuery({
    queryKey: ["gestione-personale", "persone-by-depot", depotCodice],
    queryFn: () => {
      if (depotCodice === undefined) throw new Error("depotCodice mancante");
      return listPersoneByDepot(depotCodice);
    },
    enabled: depotCodice !== undefined,
    staleTime: HALF_MIN,
  });
}

export function useIndisponibilita(
  params: ListIndisponibilitaParams = {},
): UseQueryResult<IndisponibilitaWithPersonaRead[]> {
  return useQuery({
    queryKey: ["gestione-personale", "indisponibilita", params],
    queryFn: () => listIndisponibilita(params),
    staleTime: HALF_MIN,
  });
}

export function useGestionePersonaleKpi(): UseQueryResult<GestionePersonaleKpiRead> {
  return useQuery({
    queryKey: ["gestione-personale", "kpi"],
    queryFn: getGestionePersonaleKpi,
    staleTime: HALF_MIN,
  });
}

export function useGestionePersonaleKpiDepositi(): UseQueryResult<
  GestionePersonaleKpiPerDepositoRead[]
> {
  return useQuery({
    queryKey: ["gestione-personale", "kpi-depositi"],
    queryFn: getGestionePersonaleKpiDepositi,
    staleTime: FIVE_MIN,
  });
}
