/**
 * Hook React Query per il PdE livello azienda (Sub-MR 5.bis-d, entry 178).
 *
 * 5 hook che mappano i 5 endpoint backend:
 * - usePdEStatus()              → GET /pde/status
 * - useCaricaPdEBase()          → POST /pde/base (multipart)
 * - useVariazioniGlobali()      → GET /variazioni
 * - useRegistraVariazione()     → POST /variazioni
 * - useApplicaVariazione()      → POST /variazioni/{id}/applica (multipart)
 *
 * Strategia cache:
 * - PdE status e variazioni: query con queryKey ["pde", "status"] e
 *   ["pde", "variazioni"]. Mutation chiama queryClient.invalidate per
 *   refresh automatico dopo upload.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  applicaVariazione,
  caricaPdEBase,
  creaForkVariazione,
  getPdEStatus,
  listVariazioni,
  registraVariazione,
  type ApplicaVariazioneResponse,
  type CaricaPdEBaseResponse,
  type CorsaImportRun,
  type CreaForkVariazionePayload,
  type PdEStatus,
  type RegistraVariazionePayload,
} from "@/lib/api/pde";
import type { ProgrammaMaterialeRead } from "@/lib/api/programmi";

const PDE_STATUS_KEY = ["pde", "status"] as const;
const PDE_VARIAZIONI_KEY = ["pde", "variazioni"] as const;

export function usePdEStatus(): UseQueryResult<PdEStatus> {
  return useQuery({
    queryKey: PDE_STATUS_KEY,
    queryFn: getPdEStatus,
  });
}

export function useVariazioniGlobali(
  params: { limit?: number } = {},
): UseQueryResult<CorsaImportRun[]> {
  const limit = params.limit;
  return useQuery({
    queryKey: [...PDE_VARIAZIONI_KEY, { limit }],
    queryFn: () => listVariazioni({ limit }),
  });
}

interface CaricaPdEBaseVars {
  file: File;
  force?: boolean;
}

export function useCaricaPdEBase(): UseMutationResult<
  CaricaPdEBaseResponse,
  Error,
  CaricaPdEBaseVars
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ file, force }: CaricaPdEBaseVars) =>
      caricaPdEBase(file, { force }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: PDE_STATUS_KEY });
      void qc.invalidateQueries({ queryKey: PDE_VARIAZIONI_KEY });
    },
  });
}

export function useRegistraVariazione(): UseMutationResult<
  CorsaImportRun,
  Error,
  RegistraVariazionePayload
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: RegistraVariazionePayload) =>
      registraVariazione(payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: PDE_VARIAZIONI_KEY });
      void qc.invalidateQueries({ queryKey: PDE_STATUS_KEY });
    },
  });
}

interface ApplicaVariazioneVars {
  runId: number;
  file: File;
}

export function useApplicaVariazione(): UseMutationResult<
  ApplicaVariazioneResponse,
  Error,
  ApplicaVariazioneVars
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, file }: ApplicaVariazioneVars) =>
      applicaVariazione(runId, file),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: PDE_VARIAZIONI_KEY });
      void qc.invalidateQueries({ queryKey: PDE_STATUS_KEY });
    },
  });
}

interface CreaForkVariazioneVars {
  runId: number;
  payload: CreaForkVariazionePayload;
}

/**
 * Sub-MR 5.bis-fork (entry 191): crea un programma di variazione
 * figlio. Su success invalida la cache `programmi` (la lista
 * programmi includerà il nuovo figlio).
 */
export function useCreaForkVariazione(): UseMutationResult<
  ProgrammaMaterialeRead,
  Error,
  CreaForkVariazioneVars
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, payload }: CreaForkVariazioneVars) =>
      creaForkVariazione(runId, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["programmi"] });
    },
  });
}
