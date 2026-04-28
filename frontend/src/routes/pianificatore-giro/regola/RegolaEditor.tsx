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
import { Textarea } from "@/components/ui/Textarea";
import { useAddRegola } from "@/hooks/useProgrammi";
import { ApiError } from "@/lib/api/client";
import { makeRowId, rowToPayload, type ComposizioneRow, type FiltroRow } from "@/lib/regola/schema";
import { ComposizioneEditor } from "@/routes/pianificatore-giro/regola/ComposizioneEditor";
import { FiltriEditor } from "@/routes/pianificatore-giro/regola/FiltriEditor";

interface RegolaEditorProps {
  programmaId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Dialog per aggiungere una regola a un programma in stato `bozza`.
 *
 * Edit di una regola esistente non è supportato dal backend (Sub 6.3
 * scope); workflow utente: rimuovere + aggiungere nuova. Quando il
 * backend esporrà PATCH regola, qui si aggiunge `mode: "create" | "edit"`.
 */
export function RegolaEditor({ programmaId, open, onOpenChange }: RegolaEditorProps) {
  const [filtri, setFiltri] = useState<FiltroRow[]>([]);
  const [composizione, setComposizione] = useState<ComposizioneRow[]>([
    { id: makeRowId(), materiale_tipo_codice: "", n_pezzi: 1 },
  ]);
  const [priorita, setPriorita] = useState(60);
  const [isComposizioneManuale, setIsComposizioneManuale] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const addMutation = useAddRegola();

  const handleClose = (next: boolean) => {
    if (!next) {
      setFiltri([]);
      setComposizione([{ id: makeRowId(), materiale_tipo_codice: "", n_pezzi: 1 }]);
      setPriorita(60);
      setIsComposizioneManuale(false);
      setNote("");
      setError(null);
    }
    onOpenChange(next);
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);

    if (composizione.length === 0) {
      setError("Aggiungi almeno un materiale alla composizione.");
      return;
    }
    if (composizione.some((c) => c.materiale_tipo_codice.trim() === "")) {
      setError("Tutti i materiali devono essere selezionati.");
      return;
    }

    let filtriPayload: Array<{ campo: string; op: string; valore: unknown }>;
    try {
      filtriPayload = filtri.map(rowToPayload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Errore nei filtri");
      return;
    }

    try {
      await addMutation.mutateAsync({
        programmaId,
        payload: {
          filtri_json: filtriPayload,
          composizione: composizione.map((c) => ({
            materiale_tipo_codice: c.materiale_tipo_codice,
            n_pezzi: c.n_pezzi,
          })),
          is_composizione_manuale: isComposizioneManuale,
          priorita,
          note: note.trim().length > 0 ? note.trim() : null,
        },
      });
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

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Nuova regola di assegnazione</DialogTitle>
          <DialogDescription>
            Definisci quali corse vengono coperte (filtri) e con quale composizione di materiali.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex max-h-[70vh] flex-col gap-5 overflow-y-auto">
          <section className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold text-foreground">Filtri</h3>
            <FiltriEditor filtri={filtri} onChange={setFiltri} disabled={addMutation.isPending} />
          </section>

          <section className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold text-foreground">Composizione</h3>
            <ComposizioneEditor
              composizione={composizione}
              onChange={setComposizione}
              disabled={addMutation.isPending}
            />
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={isComposizioneManuale}
                onChange={(e) => setIsComposizioneManuale(e.target.checked)}
                disabled={addMutation.isPending}
              />
              Composizione manuale (override del builder automatico)
            </label>
          </section>

          <section className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="priorita">Priorità (0-100)</Label>
              <Input
                id="priorita"
                type="number"
                min={0}
                max={100}
                value={priorita}
                onChange={(e) =>
                  setPriorita(Math.min(100, Math.max(0, Number.parseInt(e.target.value, 10) || 0)))
                }
                disabled={addMutation.isPending}
              />
              <p className="text-xs text-muted-foreground">
                Le regole con priorità più alta vincono in caso di overlap.
              </p>
            </div>
          </section>

          <section className="flex flex-col gap-1.5">
            <Label htmlFor="note">Note (opzionale)</Label>
            <Textarea
              id="note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              disabled={addMutation.isPending}
              placeholder="Es. Solo diretti Mi.Centrale↔Tirano (130 corse direttrice)"
            />
          </section>

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
              disabled={addMutation.isPending}
            >
              Annulla
            </Button>
            <Button type="submit" disabled={addMutation.isPending}>
              {addMutation.isPending ? <Spinner label="Salvataggio…" /> : "Aggiungi regola"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
