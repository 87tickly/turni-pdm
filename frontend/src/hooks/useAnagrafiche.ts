/**
 * React Query hooks per anagrafiche (read-only, raramente cambiano).
 *
 * `staleTime: 5min` per evitare refetch inutili: stazioni/materiali/
 * depots cambiano solo dopo seed o operazioni admin, non durante la
 * pianificazione.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import {
  listDepots,
  listDirettrici,
  listLocalitaManutenzione,
  listMateriali,
  listStazioni,
  type DepotRead,
  type LocalitaManutenzioneRead,
  type MaterialeRead,
  type StazioneRead,
} from "@/lib/api/anagrafiche";

const FIVE_MIN = 5 * 60 * 1000;

export function useStazioni(): UseQueryResult<StazioneRead[]> {
  return useQuery({
    queryKey: ["anagrafiche", "stazioni"],
    queryFn: listStazioni,
    staleTime: FIVE_MIN,
  });
}

export function useMateriali(): UseQueryResult<MaterialeRead[]> {
  return useQuery({
    queryKey: ["anagrafiche", "materiali"],
    queryFn: listMateriali,
    staleTime: FIVE_MIN,
  });
}

export function useDepots(): UseQueryResult<DepotRead[]> {
  return useQuery({
    queryKey: ["anagrafiche", "depots"],
    queryFn: listDepots,
    staleTime: FIVE_MIN,
  });
}

export function useDirettrici(): UseQueryResult<string[]> {
  return useQuery({
    queryKey: ["anagrafiche", "direttrici"],
    queryFn: listDirettrici,
    staleTime: FIVE_MIN,
  });
}

export function useLocalitaManutenzione(): UseQueryResult<LocalitaManutenzioneRead[]> {
  return useQuery({
    queryKey: ["anagrafiche", "localita-manutenzione"],
    queryFn: listLocalitaManutenzione,
    staleTime: FIVE_MIN,
  });
}
