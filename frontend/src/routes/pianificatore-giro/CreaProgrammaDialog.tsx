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
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import { useCreateProgramma } from "@/hooks/useProgrammi";
import { ApiError } from "@/lib/api/client";
import type { ProgrammaMaterialeRead, Stagione } from "@/lib/api/programmi";

interface CreaProgrammaDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (programma: ProgrammaMaterialeRead) => void;
}

interface FormState {
  nome: string;
  stagione: Stagione | "";
  valido_da: string;
  valido_a: string;
  km_max_ciclo: string;
  n_giornate_default: string;
}

const INITIAL: FormState = {
  nome: "",
  stagione: "",
  valido_da: "",
  valido_a: "",
  km_max_ciclo: "",
  n_giornate_default: "1",
};

/**
 * Form modale di creazione programma.
 *
 * Crea sempre in stato `bozza`, senza regole (le regole si aggiungono
 * in Sub 6.3 — editor regole). I campi opzionali (km_max_ciclo, …)
 * sono inviati solo se compilati.
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
    const nGiornate = form.n_giornate_default.trim();

    try {
      const created = await createMutation.mutateAsync({
        nome: form.nome.trim(),
        stagione: form.stagione === "" ? null : form.stagione,
        valido_da: form.valido_da,
        valido_a: form.valido_a,
        km_max_ciclo: kmCiclo === "" ? null : Number(kmCiclo),
        n_giornate_default: nGiornate === "" ? 1 : Number(nGiornate),
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
              <Label htmlFor="stagione">Stagione</Label>
              <Select
                id="stagione"
                value={form.stagione}
                onChange={(e) => update("stagione", e.target.value as Stagione | "")}
                disabled={createMutation.isPending}
              >
                <option value="">— non specificata —</option>
                <option value="invernale">Invernale</option>
                <option value="estiva">Estiva</option>
                <option value="agosto">Agosto</option>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="n_giornate_default">N. giornate (safety)</Label>
              <Input
                id="n_giornate_default"
                type="number"
                min={1}
                value={form.n_giornate_default}
                onChange={(e) => update("n_giornate_default", e.target.value)}
                disabled={createMutation.isPending}
              />
            </div>
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
