/**
 * Sprint 8.0 MR-5 (entry 228) — dialog "Modifica gruppo" della vista
 * aggregata in `ProgrammaGiriRoute`.
 *
 * Gruppo = `(materiale_tipo_codice, localita_codice)`. L'utente può
 * cambiare uno o entrambi i due. Il backend è chirurgico: aggiorna
 * le regole `programma_regola_assegnazione` corrispondenti + rigenera
 * (`force=true`) i giri delle sedi toccate. Decisione utente entry 224
 * + risposte di scope sessione 2026-05-07: "chirurgico" per entrambi.
 *
 * Avviso PdC: la rigenerazione cancella eventuali turni PdC dipendenti
 * dei giri rigenerati. Se ce ne sono, il backend torna 409 con
 * `code: "pdc_dipendenti"` e l'utente deve dare conferma esplicita.
 */

import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Label } from "@/components/ui/Label";
import { useLocalitaManutenzione, useMateriali } from "@/hooks/useAnagrafiche";
import { useAggregaModifica } from "@/hooks/useGiri";
import { ApiError } from "@/lib/api/client";
import type { AggregaModificaResponse } from "@/lib/api/giri";
import { cn } from "@/lib/utils";

interface ModificaGruppoDialogProps {
  programmaId: number;
  materialeOld: string;
  localitaCodiceOld: string;
  /** Solo per display: numero di giri del gruppo (sull'header). */
  nGiri: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: (response: AggregaModificaResponse) => void;
}

export function ModificaGruppoDialog({
  programmaId,
  materialeOld,
  localitaCodiceOld,
  nGiri,
  open,
  onOpenChange,
  onSuccess,
}: ModificaGruppoDialogProps) {
  const materialiQuery = useMateriali({ enabled: open });
  const localitaQuery = useLocalitaManutenzione({ enabled: open });
  const aggrega = useAggregaModifica();

  const [materialeNew, setMaterialeNew] = useState<string>("");
  const [localitaNew, setLocalitaNew] = useState<string>("");
  const [confirmDeletePdc, setConfirmDeletePdc] = useState(false);

  // Reset state ogni volta che il dialog si apre.
  useEffect(() => {
    if (open) {
      setMaterialeNew("");
      setLocalitaNew("");
      setConfirmDeletePdc(false);
      aggrega.reset();
    }
    // Volutamente non includiamo `aggrega` nelle deps: la mutation è
    // referenzialmente stabile per istanza di provider; aggiungerla
    // farebbe scattare il reset a ogni cambio interno della mutation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const localitaOld = useMemo(
    () => localitaQuery.data?.find((l) => l.codice === localitaCodiceOld),
    [localitaQuery.data, localitaCodiceOld],
  );
  const localitaOldNome =
    localitaOld?.codice_breve ?? localitaOld?.nome_canonico ?? localitaCodiceOld;

  const cambiaMat = materialeNew !== "" && materialeNew !== materialeOld;
  const cambiaLoc =
    localitaNew !== "" && localitaNew !== localitaCodiceOld;
  const canSubmit =
    (cambiaMat || cambiaLoc) && !aggrega.isPending;

  const isPdcConflict =
    aggrega.error instanceof ApiError &&
    aggrega.error.status === 409 &&
    isPdcDipendentiError(aggrega.error);

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!canSubmit) return;
    aggrega.mutate(
      {
        programmaId,
        payload: {
          materiale_tipo_codice_old: materialeOld,
          localita_codice_old: localitaCodiceOld,
          materiale_tipo_codice_new: cambiaMat ? materialeNew : null,
          localita_codice_new: cambiaLoc ? localitaNew : null,
          confirm_delete_pdc: confirmDeletePdc,
        },
      },
      {
        onSuccess: (data) => {
          onSuccess?.(data);
        },
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Modifica gruppo</DialogTitle>
          <DialogDescription>
            Gruppo{" "}
            <span className="font-mono font-medium">
              {materialeOld} · {localitaOldNome}
            </span>{" "}
            ({nGiri} {nGiri === 1 ? "giro" : "giri"}). La modifica
            aggiorna le regole del programma e rigenera tutti i giri
            delle sedi toccate.
          </DialogDescription>
        </DialogHeader>

        {aggrega.isSuccess && aggrega.data !== undefined ? (
          <SuccessSummary response={aggrega.data} />
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <Label htmlFor="mr5-materiale-new">Nuovo materiale</Label>
              <select
                id="mr5-materiale-new"
                value={materialeNew}
                onChange={(e) => setMaterialeNew(e.target.value)}
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                disabled={materialiQuery.isLoading}
              >
                <option value="">— invariato ({materialeOld}) —</option>
                {materialiQuery.data?.map((m) => (
                  <option key={m.codice} value={m.codice}>
                    {m.codice}
                    {m.nome_commerciale !== null
                      ? ` · ${m.nome_commerciale}`
                      : ""}
                    {m.pezzi_disponibili !== null
                      ? ` (${m.pezzi_disponibili} pezzi)`
                      : ""}
                  </option>
                ))}
              </select>
              {materialiQuery.isLoading && (
                <p className="mt-1 text-xs text-muted-foreground">
                  Carico anagrafica materiali…
                </p>
              )}
            </div>

            <div>
              <Label htmlFor="mr5-localita-new">Nuovo deposito</Label>
              <select
                id="mr5-localita-new"
                value={localitaNew}
                onChange={(e) => setLocalitaNew(e.target.value)}
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                disabled={localitaQuery.isLoading}
              >
                <option value="">
                  — invariato ({localitaOldNome}) —
                </option>
                {localitaQuery.data?.map((l) => (
                  <option key={l.codice} value={l.codice}>
                    {l.codice_breve ?? l.codice} · {l.nome_canonico}
                  </option>
                ))}
              </select>
              {localitaQuery.isLoading && (
                <p className="mt-1 text-xs text-muted-foreground">
                  Carico anagrafica località…
                </p>
              )}
              {cambiaLoc && (
                <p className="mt-1 text-xs text-amber-700">
                  Cambiando il deposito verranno rigenerati i giri di
                  entrambe le sedi (origine + destinazione).
                </p>
              )}
            </div>

            <div
              className={cn(
                "rounded-md border p-3 text-sm",
                isPdcConflict
                  ? "border-amber-300 bg-amber-50 text-amber-900"
                  : "border-border bg-muted/30 text-muted-foreground",
              )}
            >
              <label className="flex items-start gap-2">
                <input
                  type="checkbox"
                  checked={confirmDeletePdc}
                  onChange={(e) => setConfirmDeletePdc(e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-border accent-primary"
                />
                <span className="leading-snug">
                  Confermo la cancellazione dei{" "}
                  <strong>turni PdC dipendenti</strong> dei giri
                  rigenerati. Senza questa conferma, se esistono PdC
                  collegati la rigenerazione viene bloccata (409).
                </span>
              </label>
            </div>

            {aggrega.isError && (
              <ErrorBox
                error={aggrega.error}
                isPdcConflict={isPdcConflict}
              />
            )}

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={aggrega.isPending}
              >
                Annulla
              </Button>
              <Button type="submit" disabled={!canSubmit}>
                {aggrega.isPending ? (
                  <>
                    <Loader2
                      className="mr-2 h-3.5 w-3.5 animate-spin"
                      aria-hidden
                    />
                    Modifico…
                  </>
                ) : (
                  "Applica modifica"
                )}
              </Button>
            </DialogFooter>
          </form>
        )}

        {aggrega.isSuccess && (
          <DialogFooter>
            <Button onClick={() => onOpenChange(false)}>Chiudi</Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}

function isPdcDipendentiError(err: ApiError): boolean {
  // FastAPI body: `{ "detail": { code, message, ... } }` → ApiError.detail
  // contiene già il valore di `body.detail` parsato.
  const d = err.detail as { code?: string } | undefined;
  return typeof d === "object" && d !== null && d.code === "pdc_dipendenti";
}

function ErrorBox({
  error,
  isPdcConflict,
}: {
  error: Error;
  isPdcConflict: boolean;
}) {
  const message =
    error instanceof ApiError ? formatApiError(error) : error.message;
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-md border p-3 text-sm",
        isPdcConflict
          ? "border-amber-300 bg-amber-50 text-amber-900"
          : "border-destructive/30 bg-destructive/5 text-destructive",
      )}
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden />
      <div>
        {isPdcConflict ? (
          <>
            <strong>PdC dipendenti</strong>: la rigenerazione
            cancellerebbe turni PdC esistenti. Spunta la conferma sopra
            e riprova.
          </>
        ) : (
          message
        )}
      </div>
    </div>
  );
}

function formatApiError(err: ApiError): string {
  if (typeof err.detail === "string") return err.detail;
  if (typeof err.detail === "object" && err.detail !== null) {
    const d = err.detail as { message?: unknown };
    if (typeof d.message === "string") return d.message;
  }
  return err.message;
}

function SuccessSummary({ response }: { response: AggregaModificaResponse }) {
  return (
    <div className="space-y-3">
      <div className="flex items-start gap-2 rounded-md border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-900">
        <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden />
        <div>
          <strong>Modifica applicata.</strong>{" "}
          {response.n_regole_aggiornate}{" "}
          {response.n_regole_aggiornate === 1
            ? "regola aggiornata"
            : "regole aggiornate"}
          , {response.n_giri_totali_creati}{" "}
          {response.n_giri_totali_creati === 1 ? "giro" : "giri"}{" "}
          rigenerati su {response.risultati_per_sede.length}{" "}
          {response.risultati_per_sede.length === 1 ? "sede" : "sedi"}.
        </div>
      </div>

      <div className="space-y-2">
        {response.risultati_per_sede.map((r) => (
          <div
            key={r.localita_codice}
            className="rounded-md border border-border bg-muted/20 p-3 text-sm"
          >
            <div className="flex items-center justify-between">
              <span className="font-mono font-medium">
                {r.localita_codice}
              </span>
              {r.errore !== null ? (
                <span className="text-xs text-destructive">
                  errore: {r.errore}
                </span>
              ) : (
                <span className="text-xs text-muted-foreground">
                  {r.n_giri_creati} giri · {r.n_corse_processate} corse
                  · {r.n_corse_residue} residue
                </span>
              )}
            </div>
            {r.warnings.length > 0 && (
              <ul className="mt-1 list-disc pl-5 text-xs text-amber-800">
                {r.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
