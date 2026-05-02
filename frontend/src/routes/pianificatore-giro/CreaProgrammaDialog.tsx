import { useState } from "react";
import type { FormEvent } from "react";

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
import { Spinner } from "@/components/ui/Spinner";
import { useCreateProgramma } from "@/hooks/useProgrammi";
import { ApiError } from "@/lib/api/client";
import type { ProgrammaMaterialeRead } from "@/lib/api/programmi";

interface CreaProgrammaDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (programma: ProgrammaMaterialeRead) => void;
}

interface FormState {
  nome: string;
  valido_da: string;
  valido_a: string;
  km_max_ciclo: string;
}

const INITIAL: FormState = {
  nome: "",
  valido_da: "",
  valido_a: "",
  km_max_ciclo: "",
};

/**
 * Form modale di creazione programma.
 *
 * Crea sempre in stato `bozza`, senza regole (le regole si aggiungono
 * in Sub 6.3 — editor regole). I campi opzionali (km_max_ciclo, …)
 * sono inviati solo se compilati.
 *
 * NB Sprint 7.6 (decisione utente 2026-05-02): il programma materiale
 * è UN turno unico per la sua finestra di validità. Le giornate del
 * turno emergono dalla generazione dei giri (una per materiale/regola)
 * e si sommano nel programma — quindi NON si dichiarano in fase di
 * creazione del programma. Il campo `n_giornate_default` è oggi solo
 * un valore safety lato backend (default 1) usato dal builder come
 * limite, non una promessa al pianificatore.
 */
export function CreaProgrammaDialog({ open, onOpenChange, onCreated }: CreaProgrammaDialogProps) {
  const [form, setForm] = useState<FormState>(INITIAL);
  const [error, setError] = useState<string | null>(null);
  const createMutation = useCreateProgramma();

  const isValid =
    form.nome.length > 0 &&
    form.valido_da.length > 0 &&
    form.valido_a.length > 0 &&
    form.valido_a >= form.valido_da;

  const handleClose = (next: boolean) => {
    if (!next) {
      setForm(INITIAL);
      setError(null);
    }
    onOpenChange(next);
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!isValid) return;
    setError(null);

    const kmCiclo = form.km_max_ciclo.trim();

    try {
      const created = await createMutation.mutateAsync({
        nome: form.nome.trim(),
        valido_da: form.valido_da,
        valido_a: form.valido_a,
        km_max_ciclo: kmCiclo === "" ? null : Number(kmCiclo),
        // n_giornate_default: backend default 1, non chiesto al pianificatore
        // (le giornate emergono dalla generazione dei giri per materiale).
      });
      onCreated?.(created);
      handleClose(false);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Errore sconosciuto",
      );
    }
  };

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nuovo programma materiale</DialogTitle>
          <DialogDescription>
            Crea il programma in stato bozza. Le regole di assegnazione si configurano
            successivamente nel dettaglio.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="nome">Nome</Label>
            <Input
              id="nome"
              value={form.nome}
              onChange={(e) => update("nome", e.target.value)}
              required
              autoFocus
              placeholder="Es. Trenord 2025-2026 invernale Tirano"
              disabled={createMutation.isPending}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="valido_da">Valido dal</Label>
              <Input
                id="valido_da"
                type="date"
                value={form.valido_da}
                onChange={(e) => update("valido_da", e.target.value)}
                required
                disabled={createMutation.isPending}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="valido_a">Valido al</Label>
              <Input
                id="valido_a"
                type="date"
                value={form.valido_a}
                onChange={(e) => update("valido_a", e.target.value)}
                required
                disabled={createMutation.isPending}
              />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="km_max_ciclo">km max per ciclo (opzionale)</Label>
            <Input
              id="km_max_ciclo"
              type="number"
              min={1}
              value={form.km_max_ciclo}
              onChange={(e) => update("km_max_ciclo", e.target.value)}
              placeholder="Es. 10000 (cap chiusura ciclo dinamico)"
              disabled={createMutation.isPending}
            />
          </div>

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
              disabled={createMutation.isPending}
            >
              Annulla
            </Button>
            <Button type="submit" disabled={!isValid || createMutation.isPending}>
              {createMutation.isPending ? <Spinner label="Creazione…" /> : "Crea programma"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
