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
  suggerisciDepositi,
  type DepositoSuggerimentoResponse,
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

/**
 * Sprint 7.9 MR η.1 — auto-suggerimento deposito PdC.
 *
 * Idempotente sul backend: nessun TurnoPdc viene creato. Lo invochiamo
 * quando il dialog di generazione si apre, così l'utente vede i top-3
 * depositi pre-classificati per minimizzare i FR.
 *
 * `enabled=false` di default per evitare la chiamata se il dialog non
 * è ancora aperto: il chiamante setta `enabled=open && giroId !== undefined`.
 */
export function useSuggerisciDepositi(
  giroId: number | undefined,
  enabled: boolean,
  topN: number = 3,
): UseQueryResult<DepositoSuggerimentoResponse[]> {
  return useQuery({
    queryKey: [...TURNI_PDC_KEY, "suggerisci-depositi", giroId, topN],
    queryFn: () => {
      if (giroId === undefined) throw new Error("giroId mancante");
      return suggerisciDepositi(giroId, topN);
    },
    enabled: enabled && giroId !== undefined,
    // I suggerimenti dipendono solo dalla composizione del giro e dai
    // depositi dell'azienda; entrambi cambiano raramente nella stessa
    // sessione. Cache 5 min per non rifare la simulazione ogni volta
    // che riapri il dialog.
    staleTime: 5 * 60 * 1000,
  });
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
