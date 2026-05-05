/**
 * React Query hooks per i programmi materiale.
 *
 * Le mutation invalidano la query list (`["programmi"]`) per refresh
 * automatico. La query list accetta i filtri come parte della key.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  addRegola,
  archiviaProgramma,
  confermaMateriale,
  confermaManutenzione,
  confermaPdc,
  confermaPersonale,
  createProgramma,
  deleteRegola,
  getLastBuilderRun,
  getProgramma,
  listProgrammi,
  pubblicaProgramma,
  pubblicaVistaPdc,
  sbloccaProgramma,
  type BuilderRunRead,
  type ListProgrammiParams,
  type ProgrammaDettaglioRead,
  type ProgrammaMaterialeCreate,
  type ProgrammaMaterialeRead,
  type ProgrammaRegolaAssegnazioneCreate,
  type ProgrammaRegolaAssegnazioneRead,
  type SbloccaProgrammaPayload,
} from "@/lib/api/programmi";

const PROGRAMMI_KEY = ["programmi"] as const;

export function useProgrammi(
  params: ListProgrammiParams = {},
): UseQueryResult<ProgrammaMaterialeRead[]> {
  return useQuery({
    queryKey: [...PROGRAMMI_KEY, "list", params],
    queryFn: () => listProgrammi(params),
  });
}

export function useProgramma(id: number | undefined): UseQueryResult<ProgrammaDettaglioRead> {
  return useQuery({
    queryKey: [...PROGRAMMI_KEY, "detail", id],
    queryFn: () => {
      if (id === undefined) {
        throw new Error("id mancante");
      }
      return getProgramma(id);
    },
    enabled: id !== undefined,
  });
}

/** Sprint 7.9 MR 11C entry 116: ultimo run del builder per il programma. */
export function useLastBuilderRun(
  id: number | undefined,
): UseQueryResult<BuilderRunRead | null> {
  return useQuery({
    queryKey: [...PROGRAMMI_KEY, "last-run", id],
    queryFn: () => {
      if (id === undefined) {
        throw new Error("id mancante");
      }
      return getLastBuilderRun(id);
    },
    enabled: id !== undefined,
  });
}

export function useCreateProgramma(): UseMutationResult<
  ProgrammaMaterialeRead,
  Error,
  ProgrammaMaterialeCreate
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createProgramma,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: PROGRAMMI_KEY });
    },
  });
}

export function usePubblicaProgramma(): UseMutationResult<ProgrammaMaterialeRead, Error, number> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: pubblicaProgramma,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: PROGRAMMI_KEY });
    },
  });
}

export function useArchiviaProgramma(): UseMutationResult<ProgrammaMaterialeRead, Error, number> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: archiviaProgramma,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: PROGRAMMI_KEY });
    },
  });
}

interface AddRegolaArgs {
  programmaId: number;
  payload: ProgrammaRegolaAssegnazioneCreate;
}

export function useAddRegola(): UseMutationResult<
  ProgrammaRegolaAssegnazioneRead,
  Error,
  AddRegolaArgs
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ programmaId, payload }) => addRegola(programmaId, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: PROGRAMMI_KEY });
    },
  });
}

interface DeleteRegolaArgs {
  programmaId: number;
  regolaId: number;
}

export function useDeleteRegola(): UseMutationResult<void, Error, DeleteRegolaArgs> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ programmaId, regolaId }) => deleteRegola(programmaId, regolaId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: PROGRAMMI_KEY });
    },
  });
}

// =====================================================================
// Pipeline state machine — Sprint 8.0 MR 0/MR 1 (entry 164/165)
// =====================================================================
//
// Le mutation invalidano l'intera ``PROGRAMMI_KEY`` + le query "giri"
// del programma toccato (la conferma materiale freezza il ramo,
// PdC potrebbe ora vederlo nelle list filtrate per ruolo). I dettagli
// ``"detail" id`` sono coperti dall'invalidazione globale.

const GIRI_KEY = ["giri"] as const;

function invalidatePipelineQueries(qc: ReturnType<typeof useQueryClient>): void {
  void qc.invalidateQueries({ queryKey: PROGRAMMI_KEY });
  void qc.invalidateQueries({ queryKey: GIRI_KEY });
}

export function useConfermaMateriale(): UseMutationResult<
  ProgrammaMaterialeRead,
  Error,
  number
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: confermaMateriale,
    onSuccess: () => invalidatePipelineQueries(qc),
  });
}

export function useConfermaPdc(): UseMutationResult<ProgrammaMaterialeRead, Error, number> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: confermaPdc,
    onSuccess: () => invalidatePipelineQueries(qc),
  });
}

export function useConfermaPersonale(): UseMutationResult<
  ProgrammaMaterialeRead,
  Error,
  number
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: confermaPersonale,
    onSuccess: () => invalidatePipelineQueries(qc),
  });
}

export function usePubblicaVistaPdc(): UseMutationResult<
  ProgrammaMaterialeRead,
  Error,
  number
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: pubblicaVistaPdc,
    onSuccess: () => invalidatePipelineQueries(qc),
  });
}

export function useConfermaManutenzione(): UseMutationResult<
  ProgrammaMaterialeRead,
  Error,
  number
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: confermaManutenzione,
    onSuccess: () => invalidatePipelineQueries(qc),
  });
}

interface SbloccaArgs {
  id: number;
  payload: SbloccaProgrammaPayload;
}

export function useSbloccaProgramma(): UseMutationResult<
  ProgrammaMaterialeRead,
  Error,
  SbloccaArgs
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }) => sbloccaProgramma(id, payload),
    onSuccess: () => invalidatePipelineQueries(qc),
  });
}
