/**
 * Sprint 8.0 MR-C (entry 229) — wizard "materiale + linee → giri".
 *
 * Decisione utente:
 * > "imposto un materiale, scrivo uno per scriverne 100, e gli do le
 * > linee, lui prende tutti i treni presenti sul PdE per quelle linee
 * > e crea tutti i giri materiali per quelle linee con il treno che
 * > ho impostato"
 *
 * Wizard a 3 step:
 *  1. Materiale (select dalla dotazione azienda).
 *  2. Sede manutentiva (select da anagrafica).
 *  3. Linee (multi-select con conteggio corse per linea, search).
 *  → Submit: crea/aggiorna regole + rigenera giri della sede.
 *
 * Risolve il problema "il builder produce turni mono-giornata mono-corsa
 * quando non riesce a concatenare". Forzando un solo materiale su molte
 * linee, il builder ha un pool di corse molto più ampio da concatenare.
 */

import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Search,
} from "lucide-react";

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
import {
  useLocalitaManutenzione,
  useMateriali,
} from "@/hooks/useAnagrafiche";
import { useLineeDistinct, useWizardDaLinee } from "@/hooks/useGiri";
import { ApiError } from "@/lib/api/client";
import type { WizardDaLineeResponse } from "@/lib/api/giri";
import { cn } from "@/lib/utils";

interface WizardDaLineeDialogProps {
  programmaId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: (response: WizardDaLineeResponse) => void;
}

type Step = 1 | 2 | 3;

export function WizardDaLineeDialog({
  programmaId,
  open,
  onOpenChange,
  onSuccess,
}: WizardDaLineeDialogProps) {
  const materialiQuery = useMateriali({ enabled: open });
  const localitaQuery = useLocalitaManutenzione({ enabled: open });
  const lineeQuery = useLineeDistinct(programmaId, { enabled: open });
  const wizard = useWizardDaLinee();

  const [step, setStep] = useState<Step>(1);
  const [materialeCodice, setMaterialeCodice] = useState<string>("");
  const [localitaCodice, setLocalitaCodice] = useState<string>("");
  const [lineeSelezionate, setLineeSelezionate] = useState<Set<string>>(
    () => new Set(),
  );
  const [confirmDeletePdc, setConfirmDeletePdc] = useState(false);
  const [searchLinea, setSearchLinea] = useState("");
  // Sprint 8.0 MR-D (entry 236): di default mostra solo materiali con
  // dotazione effettiva (pezzi_disponibili != null E > 0). Toggle
  // "Mostra tutti" per override.
  const [mostraTuttiMateriali, setMostraTuttiMateriali] = useState(false);

  // Reset state ogni volta che il dialog si apre.
  useEffect(() => {
    if (open) {
      setStep(1);
      setMaterialeCodice("");
      setLocalitaCodice("");
      setLineeSelezionate(new Set());
      setConfirmDeletePdc(false);
      setSearchLinea("");
      setMostraTuttiMateriali(false);
      wizard.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // MR-D entry 236: filtra materiali per dotazione disponibile.
  const materialiVisibili = useMemo(() => {
    const all = materialiQuery.data ?? [];
    if (mostraTuttiMateriali) return all;
    return all.filter(
      (m) => m.pezzi_disponibili !== null && m.pezzi_disponibili > 0,
    );
  }, [materialiQuery.data, mostraTuttiMateriali]);

  const lineeFiltrate = useMemo(() => {
    const q = searchLinea.trim().toLowerCase();
    const all = lineeQuery.data ?? [];
    if (q === "") return all;
    return all.filter((l) => l.codice_linea.toLowerCase().includes(q));
  }, [lineeQuery.data, searchLinea]);

  const totCorseSelezionate = useMemo(() => {
    let tot = 0;
    for (const l of lineeQuery.data ?? []) {
      if (lineeSelezionate.has(l.codice_linea)) tot += l.n_corse;
    }
    return tot;
  }, [lineeQuery.data, lineeSelezionate]);

  const canStep2 = materialeCodice !== "";
  const canStep3 = localitaCodice !== "";
  const canSubmit = lineeSelezionate.size > 0 && !wizard.isPending;

  const isPdcConflict =
    wizard.error instanceof ApiError &&
    wizard.error.status === 409 &&
    isPdcDipendentiError(wizard.error);

  function toggleLinea(codice: string) {
    setLineeSelezionate((prev) => {
      const next = new Set(prev);
      if (next.has(codice)) next.delete(codice);
      else next.add(codice);
      return next;
    });
  }

  function selezionaTutte() {
    setLineeSelezionate(
      new Set((lineeFiltrate ?? []).map((l) => l.codice_linea)),
    );
  }

  function deselezionaTutte() {
    setLineeSelezionate(new Set());
  }

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!canSubmit) return;
    wizard.mutate(
      {
        programmaId,
        payload: {
          materiale_tipo_codice: materialeCodice,
          localita_codice: localitaCodice,
          linee: Array.from(lineeSelezionate).sort(),
          confirm_delete_pdc: confirmDeletePdc,
        },
      },
      {
        onSuccess: (data) => onSuccess?.(data),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            Wizard: materiale + linee → giri
          </DialogTitle>
          <DialogDescription>
            Imposta un materiale e le linee da coprire. Il builder
            creerà tutti i giri necessari per coprire i treni del PdE
            su quelle linee.{" "}
            <strong>Step {step} / 3</strong>
          </DialogDescription>
        </DialogHeader>

        {wizard.isSuccess && wizard.data !== undefined ? (
          <SuccessSummary response={wizard.data} />
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <StepIndicator current={step} />

            {step === 1 && (
              <div>
                <Label htmlFor="wzl-materiale">
                  Materiale (1) — scegli il materiale da assegnare
                </Label>
                <select
                  id="wzl-materiale"
                  value={materialeCodice}
                  onChange={(e) => setMaterialeCodice(e.target.value)}
                  className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                  disabled={materialiQuery.isLoading}
                >
                  <option value="">— seleziona —</option>
                  {materialiVisibili.map((m) => (
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
                {!materialiQuery.isLoading && (
                  <label className="mt-2 inline-flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
                    <input
                      type="checkbox"
                      checked={mostraTuttiMateriali}
                      onChange={(e) =>
                        setMostraTuttiMateriali(e.target.checked)
                      }
                      className="h-3.5 w-3.5 rounded border-border accent-primary"
                    />
                    Mostra tutti i materiali (anche senza dotazione
                    registrata)
                  </label>
                )}
                {!mostraTuttiMateriali && materialiQuery.data && (
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    {materialiVisibili.length} di{" "}
                    {materialiQuery.data.length} materiali con dotazione
                    disponibile.
                  </p>
                )}
              </div>
            )}

            {step === 2 && (
              <div>
                <Label htmlFor="wzl-localita">
                  Sede manutentiva (2) — dove vive il materiale
                </Label>
                <select
                  id="wzl-localita"
                  value={localitaCodice}
                  onChange={(e) => setLocalitaCodice(e.target.value)}
                  className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                  disabled={localitaQuery.isLoading}
                >
                  <option value="">— seleziona —</option>
                  {localitaQuery.data?.map((l) => (
                    <option key={l.codice} value={l.codice}>
                      {l.codice_breve ?? l.codice} · {l.nome_canonico}
                    </option>
                  ))}
                </select>
                {localitaQuery.isLoading && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Carico anagrafica sedi…
                  </p>
                )}
                <p className="mt-2 text-xs text-muted-foreground">
                  I giri verranno rigenerati per la sede selezionata
                  (force=true). Eventuali giri esistenti di quella sede
                  vengono cancellati.
                </p>
              </div>
            )}

            {step === 3 && (
              <div className="space-y-3">
                <div>
                  <Label htmlFor="wzl-search">
                    Linee (3) — seleziona quali coprire
                  </Label>
                  <div className="relative mt-1">
                    <Search
                      className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground"
                      aria-hidden
                    />
                    <input
                      id="wzl-search"
                      type="text"
                      placeholder="Filtra linee (es. S5, R20…)"
                      value={searchLinea}
                      onChange={(e) => setSearchLinea(e.target.value)}
                      className="w-full rounded-md border border-border bg-background py-2 pl-8 pr-3 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                </div>

                <div className="flex items-center gap-2 text-xs">
                  <button
                    type="button"
                    onClick={selezionaTutte}
                    className="rounded border border-border bg-white px-2 py-1 text-foreground hover:bg-muted"
                    disabled={lineeFiltrate.length === 0}
                  >
                    Seleziona{" "}
                    {searchLinea.trim() !== "" ? "filtrate" : "tutte"} (
                    {lineeFiltrate.length})
                  </button>
                  <button
                    type="button"
                    onClick={deselezionaTutte}
                    className="rounded border border-border bg-white px-2 py-1 text-foreground hover:bg-muted"
                    disabled={lineeSelezionate.size === 0}
                  >
                    Deseleziona tutte
                  </button>
                  <span className="ml-auto text-muted-foreground">
                    Selezionate: {lineeSelezionate.size} (
                    {totCorseSelezionate} corse)
                  </span>
                </div>

                <div className="max-h-72 overflow-y-auto rounded-md border border-border bg-background">
                  {lineeQuery.isLoading ? (
                    <div className="p-4 text-center text-sm text-muted-foreground">
                      <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />
                      Carico linee del PdE…
                    </div>
                  ) : lineeFiltrate.length === 0 ? (
                    <div className="p-4 text-center text-sm text-muted-foreground">
                      {searchLinea.trim() !== ""
                        ? "Nessuna linea corrisponde al filtro."
                        : "Nessuna linea trovata nel periodo del programma."}
                    </div>
                  ) : (
                    <ul className="divide-y divide-border">
                      {lineeFiltrate.map((l) => (
                        <li key={l.codice_linea}>
                          <label className="flex cursor-pointer items-center gap-3 px-3 py-2 hover:bg-muted/40">
                            <input
                              type="checkbox"
                              checked={lineeSelezionate.has(
                                l.codice_linea,
                              )}
                              onChange={() => toggleLinea(l.codice_linea)}
                              className="h-4 w-4 rounded border-border accent-primary"
                            />
                            <span className="font-mono text-sm font-medium">
                              {l.codice_linea}
                            </span>
                            <span className="ml-auto text-xs text-muted-foreground tabular-nums">
                              {l.n_corse} corse
                            </span>
                          </label>
                        </li>
                      ))}
                    </ul>
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
                      onChange={(e) =>
                        setConfirmDeletePdc(e.target.checked)
                      }
                      className="mt-0.5 h-4 w-4 rounded border-border accent-primary"
                    />
                    <span className="leading-snug">
                      Confermo la cancellazione dei{" "}
                      <strong>turni PdC dipendenti</strong> dei giri
                      rigenerati. Senza questa conferma, se esistono
                      PdC il rigenera viene bloccato (409).
                    </span>
                  </label>
                </div>
              </div>
            )}

            {wizard.isError && (
              <ErrorBox
                error={wizard.error}
                isPdcConflict={isPdcConflict}
              />
            )}

            <DialogFooter>
              <div className="flex w-full items-center justify-between gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setStep((s) => (s === 1 ? 1 : ((s - 1) as Step)))
                  }
                  disabled={step === 1 || wizard.isPending}
                >
                  <ChevronLeft className="mr-1 h-3.5 w-3.5" /> Indietro
                </Button>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => onOpenChange(false)}
                    disabled={wizard.isPending}
                  >
                    Annulla
                  </Button>
                  {step < 3 ? (
                    <Button
                      type="button"
                      onClick={() =>
                        setStep((s) => ((s + 1) as Step))
                      }
                      disabled={
                        (step === 1 && !canStep2) ||
                        (step === 2 && !canStep3)
                      }
                    >
                      Avanti{" "}
                      <ChevronRight className="ml-1 h-3.5 w-3.5" />
                    </Button>
                  ) : (
                    <Button type="submit" disabled={!canSubmit}>
                      {wizard.isPending ? (
                        <>
                          <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                          Genero giri…
                        </>
                      ) : (
                        "Crea regole + rigenera giri"
                      )}
                    </Button>
                  )}
                </div>
              </div>
            </DialogFooter>
          </form>
        )}

        {wizard.isSuccess && (
          <DialogFooter>
            <Button onClick={() => onOpenChange(false)}>Chiudi</Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}

function StepIndicator({ current }: { current: Step }) {
  const labels: Record<Step, string> = {
    1: "Materiale",
    2: "Sede",
    3: "Linee",
  };
  return (
    <div className="flex items-center gap-2">
      {([1, 2, 3] as const).map((s) => (
        <div key={s} className="flex flex-1 items-center gap-2">
          <div
            className={cn(
              "flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold",
              s === current
                ? "bg-primary text-primary-foreground"
                : s < current
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-muted text-muted-foreground",
            )}
          >
            {s < current ? "✓" : s}
          </div>
          <span
            className={cn(
              "text-xs",
              s === current
                ? "font-medium text-foreground"
                : "text-muted-foreground",
            )}
          >
            {labels[s]}
          </span>
          {s < 3 && (
            <div className="h-px flex-1 bg-border" aria-hidden />
          )}
        </div>
      ))}
    </div>
  );
}

function isPdcDipendentiError(err: ApiError): boolean {
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
      <AlertTriangle
        className="mt-0.5 h-4 w-4 flex-shrink-0"
        aria-hidden
      />
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

function SuccessSummary({
  response,
}: {
  response: WizardDaLineeResponse;
}) {
  return (
    <div className="space-y-3">
      <div
        className={cn(
          "flex items-start gap-2 rounded-md border p-3 text-sm",
          response.errore !== null
            ? "border-amber-300 bg-amber-50 text-amber-900"
            : "border-emerald-300 bg-emerald-50 text-emerald-900",
        )}
      >
        {response.errore !== null ? (
          <AlertTriangle
            className="mt-0.5 h-4 w-4 flex-shrink-0"
            aria-hidden
          />
        ) : (
          <CheckCircle2
            className="mt-0.5 h-4 w-4 flex-shrink-0"
            aria-hidden
          />
        )}
        <div>
          <strong>
            {response.errore !== null
              ? "Regole salvate, ma rigenera fallito"
              : "Wizard completato"}
          </strong>
          <div className="mt-1 text-xs">
            {response.n_regole_create} create ·{" "}
            {response.n_regole_aggiornate} aggiornate · {" "}
            {response.n_giri_creati} giri rigenerati ·{" "}
            {response.n_corse_processate} corse coperte ·{" "}
            {response.n_corse_residue} residue
          </div>
          {response.errore !== null && (
            <div className="mt-1 text-xs">
              Errore: <code>{response.errore}</code>. Le regole sono
              salvate; puoi ritentare il rigenera dalla schermata
              standard.
            </div>
          )}
        </div>
      </div>

      {response.warnings.length > 0 && (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <strong>Warning del builder:</strong>
          <ul className="mt-1 list-disc pl-5 text-xs">
            {response.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
