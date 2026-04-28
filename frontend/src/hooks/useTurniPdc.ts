import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  generaTurnoPdc,
  getTurnoPdcDettaglio,
  listTurniPdcGiro,
  type GeneraTurnoPdcParams,
  type TurnoPdcDettaglio,
  type TurnoPdcGenerazioneResponse,
  type TurnoPdcListItem,
} from "@/lib/api/turniPdc";

const TURNI_PDC_KEY = ["turni-pdc"] as const;

export function useTurniPdcGiro(
  giroId: number | undefined,
): UseQueryResult<TurnoPdcListItem[]> {
  return useQuery({
    queryKey: [...TURNI_PDC_KEY, "giro", giroId],
    queryFn: () => {
      if (giroId === undefined) throw new Error("giroId mancante");
      return listTurniPdcGiro(giroId);
    },
    enabled: giroId !== undefined,
  });
}

export function useTurnoPdcDettaglio(
  turnoId: number | undefined,
): UseQueryResult<TurnoPdcDettaglio> {
  return useQuery({
    queryKey: [...TURNI_PDC_KEY, "dettaglio", turnoId],
    queryFn: () => {
      if (turnoId === undefined) throw new Error("turnoId mancante");
      return getTurnoPdcDettaglio(turnoId);
    },
    enabled: turnoId !== undefined,
  });
}

interface GeneraTurnoPdcArgs {
  giroId: number;
  params?: GeneraTurnoPdcParams;
}

export function useGeneraTurnoPdc(): UseMutationResult<
  TurnoPdcGenerazioneResponse,
  Error,
  GeneraTurnoPdcArgs
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ giroId, params }) => generaTurnoPdc(giroId, params ?? {}),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: TURNI_PDC_KEY });
    },
  });
}
