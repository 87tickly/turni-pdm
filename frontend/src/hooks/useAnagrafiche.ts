/**
 * React Query hooks per anagrafiche (read-only, raramente cambiano).
 *
 * `staleTime: 5min` per evitare refetch inutili: stazioni/materiali/
 * depots cambiano solo dopo seed o operazioni admin, non durante la
 * pianificazione.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  createRegolaInvioSosta,
  deleteRegolaInvioSosta,
  getCalendario,
  listDepots,
  listDirettrici,
  listLocalitaManutenzione,
  listLocalitaSosta,
  listMateriali,
  listMaterialeIstanze,
  listRegoleInvioSosta,
  listStazioni,
  type CalendarioRead,
  type DepotRead,
  type LocalitaManutenzioneRead,
  type LocalitaSostaRead,
  type MaterialeIstanzaRead,
  type MaterialeRead,
  type RegolaInvioSostaCreate,
  type RegolaInvioSostaRead,
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

/** Sprint 7.9 MR β2-0: località di sosta intermedia (es. Misr). */
export function useLocalitaSosta(): UseQueryResult<LocalitaSostaRead[]> {
  return useQuery({
    queryKey: ["anagrafiche", "localita-sosta"],
    queryFn: listLocalitaSosta,
    staleTime: FIVE_MIN,
  });
}

/** Sprint 7.9 MR β2-1: istanze materiale (matricole L3). */
export function useMaterialeIstanze(
  params: { tipo_materiale_codice?: string; sede_codice?: string } = {},
): UseQueryResult<MaterialeIstanzaRead[]> {
  return useQuery({
    queryKey: ["anagrafiche", "materiale-istanze", params],
    queryFn: () => listMaterialeIstanze(params),
    staleTime: FIVE_MIN,
  });
}

/** Sprint 7.9 MR β2-7: regole invio sosta per programma. */
export function useRegoleInvioSosta(
  programmaId: number | undefined,
): UseQueryResult<RegolaInvioSostaRead[]> {
  return useQuery({
    queryKey: ["anagrafiche", "regole-invio-sosta", programmaId],
    queryFn: () => {
      if (programmaId === undefined) throw new Error("programmaId mancante");
      return listRegoleInvioSosta(programmaId);
    },
    enabled: programmaId !== undefined,
  });
}

interface CreateRegolaArgs {
  programmaId: number;
  body: RegolaInvioSostaCreate;
}

export function useCreateRegolaInvioSosta(): UseMutationResult<
  RegolaInvioSostaRead,
  Error,
  CreateRegolaArgs
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ programmaId, body }) =>
      createRegolaInvioSosta(programmaId, body),
    onSuccess: (_, vars) => {
      void qc.invalidateQueries({
        queryKey: ["anagrafiche", "regole-invio-sosta", vars.programmaId],
      });
    },
  });
}

interface DeleteRegolaArgs {
  programmaId: number;
  regolaId: number;
}

export function useDeleteRegolaInvioSosta(): UseMutationResult<
  void,
  Error,
  DeleteRegolaArgs
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ programmaId, regolaId }) =>
      deleteRegolaInvioSosta(programmaId, regolaId),
    onSuccess: (_, vars) => {
      void qc.invalidateQueries({
        queryKey: ["anagrafiche", "regole-invio-sosta", vars.programmaId],
      });
    },
  });
}

/**
 * Sprint 7.7 MR 2 — calendario ufficiale (festività nazionali +
 * locali) per l'anno indicato. ``staleTime: 1h`` perché le festività
 * cambiano raramente entro la stessa sessione utente.
 */
export function useCalendario(anno: number): UseQueryResult<CalendarioRead> {
  return useQuery({
    queryKey: ["anagrafiche", "calendario", anno],
    queryFn: () => getCalendario(anno),
    staleTime: 60 * 60 * 1000,
  });
}
