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
import { Input } from "@/components/ui/Input";
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
  /** `programma.valido_da` (ISO date `YYYY-MM-DD`). Usato per default backend e anteprima. */
  validoDa: string;
  /** `programma.valido_a` (ISO date `YYYY-MM-DD`). Usato per default backend e anteprima. */
  validoA: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCompleted?: (result: BuilderResult) => void;
}

/**
 * Modalità di selezione del range temporale (Step A).
 *
 * - `intero`: nessun parametro inviato → backend usa `valido_da..valido_a`.
 * - `da_data`: solo `data_inizio` inviato → backend estende fino a `valido_a`.
 * - `range`: entrambi inviati → range esatto scelto dal pianificatore.
 */
type Modalita = "intero" | "da_data" | "range";

interface FormState {
  modalita: Modalita;
  data_inizio: string;
  n_giornate: string;
  localita_codice: string;
  force: boolean;
}

const INITIAL: FormState = {
  modalita: "intero",
  data_inizio: "",
  n_giornate: "14",
  localita_codice: "",
  force: false,
};

/**
 * Differenza di giorni inclusiva fra due date ISO `YYYY-MM-DD`
 * (convenzione del backend: `n_giornate = (valido_a - valido_da).days + 1`).
 */
function daysBetweenInclusive(fromIso: string, toIso: string): number {
  const from = new Date(`${fromIso}T00:00:00Z`).getTime();
  const to = new Date(`${toIso}T00:00:00Z`).getTime();
  if (Number.isNaN(from) || Number.isNaN(to) || to < from) return 0;
  return Math.round((to - from) / 86_400_000) + 1;
}

/**
 * Dialog di lancio dell'algoritmo `POST /api/programmi/{id}/genera-giri`.
 *
 * Tre stati nel dialog:
 * 1. form (default): scegli data_inizio + n_giornate + località
 * 2. running: spinner durante la chiamata
 * 3. done: stats restituite dal builder (n_giri_creati, residue, warnings)
 *
 * Il programma deve essere in stato 'attivo'. Se ha già giri persistiti
 * il backend ritorna 409 — riprovare con `force: true`.
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
    // Step A: parametri temporali inviati solo nei rami che li richiedono.
    // - "intero":  nessuno → backend usa valido_da..valido_a
    // - "da_data": solo data_inizio → backend estende fino a valido_a
    // - "range":   entrambi → range esatto
    const params: GeneraGiriParams = {
      localita_codice: form.localita_codice,
      force: forceFlag,
    };
    if (form.modalita === "da_data" || form.modalita === "range") {
      params.data_inizio = form.data_inizio;
    }
    if (form.modalita === "range") {
      params.n_giornate = Number.parseInt(form.n_giornate, 10) || 7;
    }
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

  const isValid =
    form.localita_codice.length > 0 &&
    (form.modalita === "intero" ||
      (form.modalita === "da_data" && form.data_inizio.length > 0) ||
      (form.modalita === "range" &&
        form.data_inizio.length > 0 &&
        form.n_giornate.length > 0));

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!isValid) return;
    void submit(form.force);
  };

  const localita = localitaQuery.data ?? [];
  const giorniTotaliProgramma = daysBetweenInclusive(validoDa, validoA);

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-xl">
        {result === null ? (
          <>
            <DialogHeader>
              <DialogTitle>Genera giri materiale</DialogTitle>
              <DialogDescription>
                Lancia l'algoritmo di costruzione giri su un range di giornate, partendo da una
                località manutenzione (sede). Le corse del PdE vengono assegnate alle composizioni
                materiali secondo le regole del programma.
              </DialogDescription>
            </DialogHeader>

            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <fieldset className="flex flex-col gap-2" disabled={generaMutation.isPending}>
                <legend className="text-sm font-semibold">Periodo</legend>
                <p className="text-xs text-muted-foreground">
                  Programma valido dal <strong>{validoDa}</strong> al{" "}
                  <strong>{validoA}</strong> ({giorniTotaliProgramma} giorni totali).
                </p>
                <div className="flex flex-col gap-1.5">
                  <ModalitaRadio
                    name="gg-modalita"
                    value="intero"
                    current={form.modalita}
                    onChange={(m) => setForm((p) => ({ ...p, modalita: m }))}
                    label="Periodo intero del programma"
                    hint="Default: nessun limite, processa tutto."
                  />
                  <ModalitaRadio
                    name="gg-modalita"
                    value="da_data"
                    current={form.modalita}
                    onChange={(m) => setForm((p) => ({ ...p, modalita: m }))}
                    label="Da una data fino a fine programma"
                    hint="Specifica solo la data di inizio."
                  />
                  <ModalitaRadio
                    name="gg-modalita"
                    value="range"
                    current={form.modalita}
                    onChange={(m) => setForm((p) => ({ ...p, modalita: m }))}
                    label="Range parziale (data inizio + numero giornate)"
                    hint="Sotto-finestra esatta del programma."
                  />
                </div>
              </fieldset>

              {(form.modalita === "da_data" || form.modalita === "range") && (
                <div
                  className={
                    form.modalita === "range" ? "grid grid-cols-2 gap-4" : "flex flex-col gap-4"
                  }
                >
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="gg-data">Data inizio</Label>
                    <Input
                      id="gg-data"
                      type="date"
                      min={validoDa}
                      max={validoA}
                      value={form.data_inizio}
                      onChange={(e) => setForm((p) => ({ ...p, data_inizio: e.target.value }))}
                      disabled={generaMutation.isPending}
                      required
                    />
                  </div>
                  {form.modalita === "range" && (
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor="gg-n">N. giornate (1-400)</Label>
                      <Input
                        id="gg-n"
                        type="number"
                        min={1}
                        max={400}
                        value={form.n_giornate}
                        onChange={(e) => setForm((p) => ({ ...p, n_giornate: e.target.value }))}
                        disabled={generaMutation.isPending}
                        required
                      />
                    </div>
                  )}
                </div>
              )}

              <div className="flex flex-col gap-1.5">
                <Label htmlFor="gg-loc">Località manutenzione (sede materiale)</Label>
                <Select
                  id="gg-loc"
                  value={form.localita_codice}
                  onChange={(e) => setForm((p) => ({ ...p, localita_codice: e.target.value }))}
                  disabled={generaMutation.isPending || localitaQuery.isLoading}
                  required
                >
                  <option value="">— seleziona —</option>
                  {localita.map((l) => (
                    <option key={l.codice} value={l.codice}>
                      {l.codice_breve ?? l.codice} — {l.nome_canonico}
                    </option>
                  ))}
                </Select>
                <p className="text-xs text-muted-foreground">
                  La sede determina la whitelist di chiusura giro (km_cap raggiunto + treno vicino
                  sede).
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
                    <strong>Sovrascrivi giri esistenti.</strong> Cancella tutti i giri persistiti di
                    questo programma e ricostruiscili da zero.
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

interface ModalitaRadioProps {
  name: string;
  value: Modalita;
  current: Modalita;
  onChange: (m: Modalita) => void;
  label: string;
  hint: string;
}

function ModalitaRadio({ name, value, current, onChange, label, hint }: ModalitaRadioProps) {
  const checked = current === value;
  return (
    <label
      className={`flex cursor-pointer items-start gap-2 rounded-md border px-3 py-2 text-sm transition-colors ${
        checked ? "border-primary bg-primary/5" : "border-border hover:bg-secondary/40"
      }`}
    >
      <input
        type="radio"
        name={name}
        value={value}
        checked={checked}
        onChange={() => onChange(value)}
        className="mt-0.5"
      />
      <span className="flex flex-col gap-0.5">
        <span className="font-medium">{label}</span>
        <span className="text-xs text-muted-foreground">{hint}</span>
      </span>
    </label>
  );
}
