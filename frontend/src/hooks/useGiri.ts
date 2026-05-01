import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  generaGiri,
  getGiroDettaglio,
  listGiriAzienda,
  listGiriProgramma,
  type BuilderResult,
  type GeneraGiriParams,
  type GiroDettaglio,
  type GiroListItem,
  type ListGiriAziendaParams,
} from "@/lib/api/giri";

const GIRI_KEY = ["giri"] as const;

export function useGiriProgramma(programmaId: number | undefined): UseQueryResult<GiroListItem[]> {
  return useQuery({
    queryKey: [...GIRI_KEY, "programma", programmaId],
    queryFn: () => {
      if (programmaId === undefined) throw new Error("programmaId mancante");
      return listGiriProgramma(programmaId);
    },
    enabled: programmaId !== undefined,
  });
}

/**
 * Sprint 7.3 MR 2 — lista giri azienda con filtri (cross-programma).
 * Alimenta `/pianificatore-pdc/giri` (vista readonly del 2° ruolo).
 */
export function useGiriAzienda(
  params: ListGiriAziendaParams = {},
): UseQueryResult<GiroListItem[]> {
  return useQuery({
    queryKey: [...GIRI_KEY, "azienda", params],
    queryFn: () => listGiriAzienda(params),
  });
}

export function useGiroDettaglio(giroId: number | undefined): UseQueryResult<GiroDettaglio> {
  return useQuery({
    queryKey: [...GIRI_KEY, "dettaglio", giroId],
    queryFn: () => {
      if (giroId === undefined) throw new Error("giroId mancante");
      return getGiroDettaglio(giroId);
    },
    enabled: giroId !== undefined,
  });
}

interface GeneraGiriArgs {
  programmaId: number;
  params: GeneraGiriParams;
}

export function useGeneraGiri(): UseMutationResult<BuilderResult, Error, GeneraGiriArgs> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ programmaId, params }) => generaGiri(programmaId, params),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: GIRI_KEY });
    },
  });
}
