import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  aggiungiVuoto,
  aggregaModifica,
  cercaTreno,
  duplicaGiro,
  generaDaResidue,
  generaGiri,
  getGiroDettaglio,
  getThreadDettaglio,
  inserisciCorsaManuale,
  listCorseNonCoperte,
  listGiriAzienda,
  listGiriProgramma,
  eliminaBlocco,
  listLineeDistinct,
  listThreadsGiro,
  patchBlocco,
  patchGiro,
  riempiGap,
  spostaBlocco,
  wizardDaLinee,
  type AggiungiVuotoPayload,
  type AggiungiVuotoResponse,
  type AggregaModificaPayload,
  type AggregaModificaResponse,
  type BuilderResult,
  type CercaTrenoItem,
  type CorsaNonCopertaItem,
  type DuplicaGiroResult,
  type EliminaBloccoResponse,
  type FillGapResult,
  type GeneraDaResidueResponse,
  type GeneraGiriParams,
  type GiroBlocco,
  type GiroDettaglio,
  type GiroListItem,
  type InserisciCorsaManualePayload,
  type InserisciCorsaManualeResponse,
  type LineaDistinct,
  type ListGiriAziendaParams,
  type MaterialeThreadDettaglio,
  type MaterialeThreadListItem,
  type PatchBloccoPayload,
  type PatchGiroPayload,
  type SpostaBloccoPayload,
  type SpostaBloccoResponse,
  type WizardDaLineePayload,
  type WizardDaLineeResponse,
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

/** Sprint 7.9 MR β2-6: lista thread di un giro per "Convogli del turno". */
export function useThreadsGiro(
  giroId: number | undefined,
): UseQueryResult<MaterialeThreadListItem[]> {
  return useQuery({
    queryKey: [...GIRI_KEY, "threads", giroId],
    queryFn: () => {
      if (giroId === undefined) throw new Error("giroId mancante");
      return listThreadsGiro(giroId);
    },
    enabled: giroId !== undefined,
  });
}

/** Sprint 7.9 MR β2-6: dettaglio thread + timeline eventi per viewer. */
export function useThreadDettaglio(
  threadId: number | undefined,
): UseQueryResult<MaterialeThreadDettaglio> {
  return useQuery({
    queryKey: [...GIRI_KEY, "thread", threadId],
    queryFn: () => {
      if (threadId === undefined) throw new Error("threadId mancante");
      return getThreadDettaglio(threadId);
    },
    enabled: threadId !== undefined,
  });
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

interface PatchGiroArgs {
  giroId: number;
  payload: PatchGiroPayload;
}

/** MR η — PATCH giro (oggi: solo materiale del giro). */
export function usePatchGiro(): UseMutationResult<GiroListItem, Error, PatchGiroArgs> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ giroId, payload }) => patchGiro(giroId, payload),
    onSuccess: (_data, vars) => {
      // Invalida sia la lista cross-programma sia il dettaglio del singolo
      // giro (che mostra il materiale).
      void qc.invalidateQueries({ queryKey: GIRI_KEY });
      void qc.invalidateQueries({
        queryKey: [...GIRI_KEY, "dettaglio", vars.giroId],
      });
    },
  });
}

interface PatchBloccoArgs {
  giroId: number;
  bloccoId: number;
  payload: PatchBloccoPayload;
}

/** MR η-bis — PATCH blocco (doppia composizione, sgancio, validazione). */
export function usePatchBlocco(): UseMutationResult<GiroBlocco, Error, PatchBloccoArgs> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ giroId, bloccoId, payload }) =>
      patchBlocco(giroId, bloccoId, payload),
    onSuccess: (_data, vars) => {
      // Invalida il dettaglio del giro (i blocchi sono renderizzati dentro
      // GiroDettaglio + dipendenze sub-views).
      void qc.invalidateQueries({
        queryKey: [...GIRI_KEY, "dettaglio", vars.giroId],
      });
    },
  });
}

/** MR η-bis — POST /api/giri/{id}/duplica per scenario "doppia macchina". */
export function useDuplicaGiro(): UseMutationResult<DuplicaGiroResult, Error, number> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (giroId: number) => duplicaGiro(giroId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: GIRI_KEY });
    },
  });
}

/**
 * Sprint 8.0 MR-2.7 (entry 221) — "Genera-da-residue": secondo run del
 * builder che genera giri AGGIUNTIVI per le corse non coperte usando
 * i materiali liberi della dotazione, senza wipe degli esistenti.
 *
 * Mutation diretta (no dry_run): l'utente conferma sul dialog UI prima
 * di lanciare. Sull'apply invalida ``GIRI_KEY`` → si aggiornano lista
 * giri, dettagli, corse non coperte (la sezione amber dovrebbe
 * mostrare meno corse residue).
 */
export function useGeneraDaResidue(): UseMutationResult<
  GeneraDaResidueResponse,
  Error,
  number
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (programmaId: number) => generaDaResidue(programmaId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: GIRI_KEY });
    },
  });
}

interface AggregaModificaArgs {
  programmaId: number;
  payload: AggregaModificaPayload;
}

/**
 * Sprint 8.0 MR-5 (entry 228) — modifica chirurgica di un gruppo
 * `(materiale_tipo_codice, localita_codice)`.
 *
 * Backend aggiorna le regole `programma_regola_assegnazione` del
 * gruppo + rigenera (`force=true`) i giri delle sedi toccate.
 *
 * Sull'apply invalida ``GIRI_KEY`` → si aggiornano lista giri,
 * dettagli, corse non coperte (la composizione delle regole è cambiata
 * → la coverage è ricalcolata).
 */
export function useAggregaModifica(): UseMutationResult<
  AggregaModificaResponse,
  Error,
  AggregaModificaArgs
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ programmaId, payload }) =>
      aggregaModifica(programmaId, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: GIRI_KEY });
    },
  });
}

/**
 * Sprint 8.0 MR-C (entry 229) — linee distinte del PdE per il wizard.
 * Read-only, abilitato solo quando il dialog è aperto.
 */
export function useLineeDistinct(
  programmaId: number | undefined,
  options: { enabled?: boolean } = {},
): UseQueryResult<LineaDistinct[]> {
  return useQuery({
    queryKey: [...GIRI_KEY, "linee-distinct", programmaId],
    queryFn: () => {
      if (programmaId === undefined) throw new Error("programmaId mancante");
      return listLineeDistinct(programmaId);
    },
    enabled:
      programmaId !== undefined && (options.enabled ?? true),
    staleTime: 60_000,
  });
}

interface WizardDaLineeArgs {
  programmaId: number;
  payload: WizardDaLineePayload;
}

/**
 * Sprint 8.0 MR-C (entry 229) — wizard "materiale + linee → giri".
 * Crea/aggiorna regole `programma_regola_assegnazione` (priorità 90)
 * e rigenera (force=True) i giri della sede target.
 *
 * Sull'apply invalida ``GIRI_KEY`` → si aggiornano lista giri, dettagli,
 * corse non coperte (la coverage è ricalcolata).
 */
export function useWizardDaLinee(): UseMutationResult<
  WizardDaLineeResponse,
  Error,
  WizardDaLineeArgs
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ programmaId, payload }) =>
      wizardDaLinee(programmaId, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: GIRI_KEY });
    },
  });
}

interface SpostaBloccoArgs {
  giroId: number;
  bloccoId: number;
  payload: SpostaBloccoPayload;
}

/**
 * Sprint 8.0 MR-B.1 (entry 230) — sposta un blocco tra giornate/varianti
 * dello stesso giro. Mutation in 2 fasi:
 *  1. `dry_run=true` per ottenere violazioni prima del commit (anteprima).
 *  2. `dry_run=false` per applicare. Se ci sono violazioni `severity=error`
 *     e `force=false` il backend ritorna `applied=false`.
 *
 * Sull'apply invalida ``GIRI_KEY`` → si aggiorna il dettaglio giro.
 */
export function useSpostaBlocco(): UseMutationResult<
  SpostaBloccoResponse,
  Error,
  SpostaBloccoArgs
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ giroId, bloccoId, payload }) =>
      spostaBlocco(giroId, bloccoId, payload),
    onSuccess: (data, vars) => {
      if (data.applied) {
        void qc.invalidateQueries({
          queryKey: [...GIRI_KEY, "dettaglio", vars.giroId],
        });
        void qc.invalidateQueries({ queryKey: GIRI_KEY });
      }
    },
  });
}

interface EliminaBloccoArgs {
  giroId: number;
  bloccoId: number;
  dryRun?: boolean;
  force?: boolean;
}

/**
 * Sprint 8.0 MR-B.2 (entry 232) — elimina blocco vuoto (DELETE).
 * Solo `materiale_vuoto`. Backend rifiuta blocchi commerciali.
 * Sull'apply invalida `GIRI_KEY` + dettaglio giro.
 */
export function useEliminaBlocco(): UseMutationResult<
  EliminaBloccoResponse,
  Error,
  EliminaBloccoArgs
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ giroId, bloccoId, dryRun, force }) =>
      eliminaBlocco(giroId, bloccoId, { dryRun, force }),
    onSuccess: (data, vars) => {
      if (data.applied) {
        void qc.invalidateQueries({
          queryKey: [...GIRI_KEY, "dettaglio", vars.giroId],
        });
        void qc.invalidateQueries({ queryKey: GIRI_KEY });
      }
    },
  });
}

interface AggiungiVuotoArgs {
  giroId: number;
  payload: AggiungiVuotoPayload;
}

/**
 * Sprint 8.0 MR-B.2.2 (entry 235) — aggiungi vuoto manuale.
 * `corsa_materiale_vuoto_id=null` lo distingue dai vuoti del builder.
 * Sull'apply (data.applied) invalida `GIRI_KEY` + dettaglio giro.
 */
export function useAggiungiVuoto(): UseMutationResult<
  AggiungiVuotoResponse,
  Error,
  AggiungiVuotoArgs
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ giroId, payload }) => aggiungiVuoto(giroId, payload),
    onSuccess: (data, vars) => {
      if (data.applied) {
        void qc.invalidateQueries({
          queryKey: [...GIRI_KEY, "dettaglio", vars.giroId],
        });
        void qc.invalidateQueries({ queryKey: GIRI_KEY });
      }
    },
  });
}

interface RiempiGapArgs {
  programmaId: number;
  dryRun: boolean;
}

/**
 * Sprint 8.0 MR-2.5 (entry 219) — "Fill gap": riprende le corse non
 * coperte e prova a inserirle nei gap intra-giornata dei giri
 * esistenti del programma.
 *
 * Mutation in 2 fasi (UX):
 *  1. ``dry_run=true`` → anteprima per dialog conferma utente.
 *  2. ``dry_run=false`` → apply (INSERT giro_blocco + shift seq).
 *
 * Sull'apply invalida ``GIRI_KEY`` → si riaggiornano lista giri,
 * dettagli giro, corse non coperte.
 */
export function useRiempiGap(): UseMutationResult<
  FillGapResult,
  Error,
  RiempiGapArgs
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ programmaId, dryRun }) => riempiGap(programmaId, dryRun),
    onSuccess: (data) => {
      // Solo apply (applied=true) invalida la cache: il dry_run è
      // anteprima, non modifica nulla.
      if (data.applied) {
        void qc.invalidateQueries({ queryKey: GIRI_KEY });
      }
    },
  });
}

/**
 * Sprint 8.0 MR-2 (entry 218) — corse del PdE nel perimetro del
 * programma (matching regole + periodo) che NON sono state coperte
 * da nessun giro generato. Iterazione 1: solo 0 istanze coperte.
 *
 * La query è invalidata da ``useGeneraGiri.onSuccess`` (entrambe
 * caricano da ``GIRI_KEY``) → dopo una rigenerazione, la sezione
 * "Corse non coperte" si aggiorna in automatico.
 */
export function useCorseNonCoperte(
  programmaId: number | undefined,
): UseQueryResult<CorsaNonCopertaItem[]> {
  return useQuery({
    queryKey: [...GIRI_KEY, "corse-non-coperte", programmaId],
    queryFn: () => {
      if (programmaId === undefined) throw new Error("programmaId mancante");
      return listCorseNonCoperte(programmaId);
    },
    enabled: programmaId !== undefined,
  });
}

/**
 * Sprint 8.0 MR-1 (entry 214) — cerca treno (commerciale o vuoto)
 * tra i giri persistiti del programma.
 *
 * Match partial case-insensitive su ``numero_treno``. Hook attivo
 * solo se ``programmaId`` definito e ``q`` non vuoto/spazi.
 *
 * Convenzione UX: il chiamante deve già aver applicato il debounce
 * (es. ~250ms) sulla query — questo hook non lo fa, perché vive
 * dentro React Query (cache + stale time bastano).
 */
/**
 * Sprint 8.4 G1 — inserimento manuale corsa scoperta in un giro
 * (Gantt unificato). Mutation: l'UI conferma → invia → invalida lista
 * giri + corse non coperte.
 */
interface InserisciCorsaManualeArgs {
  giroId: number;
  payload: InserisciCorsaManualePayload;
}

export function useInserisciCorsaManuale(): UseMutationResult<
  InserisciCorsaManualeResponse,
  Error,
  InserisciCorsaManualeArgs
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ giroId, payload }) =>
      inserisciCorsaManuale(giroId, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: GIRI_KEY });
    },
  });
}

export function useCercaTreno(
  programmaId: number | undefined,
  q: string,
): UseQueryResult<CercaTrenoItem[]> {
  const qTrim = q.trim();
  return useQuery({
    queryKey: [...GIRI_KEY, "cerca-treno", programmaId, qTrim],
    queryFn: () => {
      if (programmaId === undefined) throw new Error("programmaId mancante");
      return cercaTreno(programmaId, qTrim);
    },
    enabled: programmaId !== undefined && qTrim.length >= 1,
    // Risultati stabili per ~10s — l'utente che digita più volte
    // beneficia della cache, riapertura del popup è instant se la
    // query è la stessa.
    staleTime: 10_000,
  });
}
