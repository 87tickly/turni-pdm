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
  listTurniPdcAzienda,
  listTurniPdcGiro,
  type GeneraTurnoPdcParams,
  type ListTurniPdcAziendaParams,
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

/**
 * Sprint 7.3 MR 2 — lista turni PdC azienda con filtri (cross-giro).
 * Alimenta `/pianificatore-pdc/turni`.
 */
export function useTurniPdcAzienda(
  params: ListTurniPdcAziendaParams = {},
): UseQueryResult<TurnoPdcListItem[]> {
  return useQuery({
    queryKey: [...TURNI_PDC_KEY, "azienda", params],
    queryFn: () => listTurniPdcAzienda(params),
  });
}

interface GeneraTurnoPdcArgs {
  giroId: number;
  params?: GeneraTurnoPdcParams;
}

export function useGeneraTurnoPdc(): UseMutationResult<
  TurnoPdcGenerazioneResponse[],
  Error,
  GeneraTurnoPdcArgs
> {
  // Sprint 7.5 MR 5 (decisione utente D1): la mutation ora ritorna una
  // lista di turni PdC (1 per combinazione di varianti calendario del
  // giro). Con A1 strict default = 1 elemento.
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ giroId, params }) => generaTurnoPdc(giroId, params ?? {}),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: TURNI_PDC_KEY });
    },
  });
}
