import { useState } from "react";
import type { FormEvent } from "react";
import { CheckCircle2, AlertTriangle } from "lucide-react";

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
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import { useLocalitaManutenzione } from "@/hooks/useAnagrafiche";
import { useGeneraGiri } from "@/hooks/useGiri";
import { ApiError } from "@/lib/api/client";
import type { BuilderResult, GeneraGiriParams } from "@/lib/api/giri";
import { formatNumber } from "@/lib/format";

interface GeneraGiriDialogProps {
  programmaId: number;
  /** `programma.valido_da` (ISO date `YYYY-MM-DD`). Mostrato come info di contesto. */
  validoDa: string;
  /** `programma.valido_a` (ISO date `YYYY-MM-DD`). Mostrato come info di contesto. */
  validoA: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCompleted?: (result: BuilderResult) => void;
}

interface FormState {
  localita_codice: string;
  force: boolean;
}

const INITIAL: FormState = {
  localita_codice: "",
  force: false,
};

/**
 * Dialog di lancio dell'algoritmo `POST /api/programmi/{id}/genera-giri`.
 *
 * Sprint 7.6 (post-MR3, decisione utente 2026-05-02 "non capisco questa
 * schermata"): semplificato a un unico campo (sede) + bottone Avvia.
 * Il backend usa di default il **periodo intero del programma** (vedi
 * Sprint 7.5 MR 4 default = `valido_da..valido_a`). Niente più scelte
 * "periodo intero / da data / range parziale" — il pianificatore vuole
 * click-and-go.
 *
 * Tre stati nel dialog:
 * 1. form: scegli la sede materiale → "Avvia generazione"
 * 2. running: spinner durante la chiamata
 * 3. done: stats restituite dal builder (n_giri_creati, residue, warnings)
 *
 * Anti-rigenerazione (MR 3.1): se la sede ha già giri persistiti il
 * backend ritorna 409 — il dialog mostra una checkbox "Sovrascrivi"
 * scoped per sede. Le altre sedi del programma NON vengono toccate.
 */
export function GeneraGiriDialog({
  programmaId,
  validoDa,
  validoA,
  open,
  onOpenChange,
  onCompleted,
}: GeneraGiriDialogProps) {
  const [form, setForm] = useState<FormState>(INITIAL);
  const [error, setError] = useState<string | null>(null);
  const [needsForce, setNeedsForce] = useState(false);
  const [result, setResult] = useState<BuilderResult | null>(null);

  const localitaQuery = useLocalitaManutenzione();
  const generaMutation = useGeneraGiri();

  const handleClose = (next: boolean) => {
    if (!next) {
      setForm(INITIAL);
      setError(null);
      setNeedsForce(false);
      setResult(null);
    }
    onOpenChange(next);
  };

  const submit = async (forceFlag: boolean) => {
    setError(null);
    // Periodo intero del programma sempre — niente data_inizio/n_giornate
    // (backend default Sprint 7.5 MR 4 = valido_da..valido_a).
    const params: GeneraGiriParams = {
      localita_codice: form.localita_codice,
      force: forceFlag,
    };
    try {
      const r = await generaMutation.mutateAsync({ programmaId, params });
      setResult(r);
      onCompleted?.(r);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setNeedsForce(true);
        setError(err.message);
        return;
      }
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Errore sconosciuto",
      );
    }
  };

  const isValid = form.localita_codice.length > 0;

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!isValid) return;
    void submit(form.force);
  };

  const localita = localitaQuery.data ?? [];

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-md">
        {result === null ? (
          <>
            <DialogHeader>
              <DialogTitle>Genera giri materiale</DialogTitle>
              <DialogDescription>
                Costruisce i giri delle corse del programma per la sede selezionata. Periodo:
                tutto il programma (dal <strong>{validoDa}</strong> al{" "}
                <strong>{validoA}</strong>).
              </DialogDescription>
            </DialogHeader>

            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="gg-loc">Sede materiale</Label>
                <Select
                  id="gg-loc"
                  value={form.localita_codice}
                  onChange={(e) => setForm((p) => ({ ...p, localita_codice: e.target.value }))}
                  disabled={generaMutation.isPending || localitaQuery.isLoading}
                  required
                >
                  <option value="">— seleziona una sede —</option>
                  {localita.map((l) => (
                    <option key={l.codice} value={l.codice}>
                      {l.codice_breve ?? l.codice} — {l.nome_canonico}
                    </option>
                  ))}
                </Select>
                <p className="text-xs text-muted-foreground">
                  Per coprire più sedi, lancia la generazione una volta per ogni sede: i giri
                  delle altre sedi del programma non vengono toccati.
                </p>
              </div>

              {needsForce && (
                <label className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm">
                  <input
                    type="checkbox"
                    checked={form.force}
                    onChange={(e) => setForm((p) => ({ ...p, force: e.target.checked }))}
                    className="mt-0.5"
                  />
                  <span>
                    <strong>Rigenera questa sede.</strong> Cancella e ricostruisce i giri
                    della sede selezionata. I giri delle altre sedi del programma NON vengono
                    toccati.
                  </span>
                </label>
              )}

              {error !== null && (
                <p
                  role="alert"
                  className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
                >
                  {error}
                </p>
              )}

              <DialogFooter>
                <Button
                  variant="ghost"
                  type="button"
                  onClick={() => handleClose(false)}
                  disabled={generaMutation.isPending}
                >
                  Annulla
                </Button>
                <Button type="submit" disabled={!isValid || generaMutation.isPending}>
                  {generaMutation.isPending ? (
                    <Spinner label="Generazione…" />
                  ) : (
                    "Avvia generazione"
                  )}
                </Button>
              </DialogFooter>
            </form>
          </>
        ) : (
          <RisultatoBuilder result={result} onClose={() => handleClose(false)} />
        )}
      </DialogContent>
    </Dialog>
  );
}

interface RisultatoBuilderProps {
  result: BuilderResult;
  onClose: () => void;
}

function RisultatoBuilder({ result, onClose }: RisultatoBuilderProps) {
  const ok = result.n_corse_residue === 0 && result.warnings.length === 0;
  return (
    <>
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          {ok ? (
            <CheckCircle2 className="h-5 w-5 text-emerald-600" aria-hidden />
          ) : (
            <AlertTriangle className="h-5 w-5 text-amber-600" aria-hidden />
          )}
          Generazione completata
        </DialogTitle>
        <DialogDescription>
          {result.n_giri_creati} giri creati ({result.n_giri_chiusi} chiusi naturalmente,{" "}
          {result.n_giri_non_chiusi} con motivo di chiusura non standard).
        </DialogDescription>
      </DialogHeader>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 rounded-md border border-border bg-secondary/40 p-4 text-sm">
        <Stat label="Giri creati" value={formatNumber(result.n_giri_creati)} />
        <Stat label="Corse processate" value={formatNumber(result.n_corse_processate)} />
        <Stat
          label="Corse residue"
          value={formatNumber(result.n_corse_residue)}
          warn={result.n_corse_residue > 0}
        />
        <Stat label="Eventi composizione" value={formatNumber(result.n_eventi_composizione)} />
        <Stat
          label="Incompatibilità materiale"
          value={formatNumber(result.n_incompatibilita_materiale)}
          warn={result.n_incompatibilita_materiale > 0}
        />
      </dl>

      {result.warnings.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Warning ({result.warnings.length})
          </p>
          <ul className="max-h-40 list-disc overflow-y-auto rounded-md bg-amber-50 px-6 py-3 text-sm text-amber-900">
            {result.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <DialogFooter>
        <Button onClick={onClose}>Chiudi</Button>
      </DialogFooter>
    </>
  );
}

function Stat({ label, value, warn = false }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <span className={warn ? "text-amber-700" : "text-foreground"}>{value}</span>
    </div>
  );
}
