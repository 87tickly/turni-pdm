import { useState } from "react";
import type { FormEvent } from "react";
import { HelpCircle } from "lucide-react";

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
import { cn } from "@/lib/utils";
import { makeRowId, rowToPayload, type ComposizioneRow, type FiltroRow } from "@/lib/regola/schema";
import {
  ComposizioneEditor,
  type ModoComposizione,
} from "@/routes/pianificatore-giro/regola/ComposizioneEditor";
import { FiltriEditor } from "@/routes/pianificatore-giro/regola/FiltriEditor";

interface RegolaEditorProps {
  programmaId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const MODI: Array<{ id: ModoComposizione; label: string; hint: string }> = [
  {
    id: "singola",
    label: "Singola",
    hint: "1 unità di un materiale (es. 1×ETR526).",
  },
  {
    id: "doppia",
    label: "Doppia",
    hint: "2 unità accoppiate (anche di tipo diverso, es. ETR526+ETR425). Km contati per entrambi.",
  },
  {
    id: "personalizzata",
    label: "Personalizzata",
    hint: "Composizione libera (es. E464+5×Vivalto) o accoppiamenti speciali non ancora censiti.",
  },
];

const emptyRow = (): ComposizioneRow => ({
  id: makeRowId(),
  materiale_tipo_codice: "",
  n_pezzi: 1,
});

/**
 * Sincronizza la lista composizione con il modo richiesto. Preserva le
 * scelte già fatte dall'utente quando possibile (estende/tronca senza
 * resettare i materiali già selezionati).
 */
function adattaComposizioneAlModo(
  rows: ComposizioneRow[],
  modo: ModoComposizione,
): ComposizioneRow[] {
  if (modo === "singola") {
    const first = rows[0] ?? emptyRow();
    return [{ ...first, n_pezzi: 1 }];
  }
  if (modo === "doppia") {
    const first = rows[0] ?? emptyRow();
    const second = rows[1] ?? emptyRow();
    return [
      { ...first, n_pezzi: 1 },
      { ...second, n_pezzi: 1 },
    ];
  }
  // personalizzata: mantieni le righe esistenti, garantisci almeno 1.
  return rows.length > 0 ? rows : [emptyRow()];
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
  const [modo, setModo] = useState<ModoComposizione>("singola");
  const [composizione, setComposizione] = useState<ComposizioneRow[]>([emptyRow()]);
  const [priorita, setPriorita] = useState(60);
  const [kmMaxCiclo, setKmMaxCiclo] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const addMutation = useAddRegola();

  const handleClose = (next: boolean) => {
    if (!next) {
      setFiltri([]);
      setModo("singola");
      setComposizione([emptyRow()]);
      setPriorita(60);
      setKmMaxCiclo("");
      setNote("");
      setError(null);
    }
    onOpenChange(next);
  };

  const cambiaModo = (next: ModoComposizione) => {
    setModo(next);
    setComposizione((prev) => adattaComposizioneAlModo(prev, next));
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

    const kmCiclo = kmMaxCiclo.trim();
    const kmCicloNum = kmCiclo === "" ? null : Number(kmCiclo);
    if (kmCicloNum !== null && (!Number.isFinite(kmCicloNum) || kmCicloNum < 1)) {
      setError("km max per ciclo deve essere un numero ≥ 1.");
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
          // Solo la modalità Personalizzata bypassa il check
          // `materiale_accoppiamento_ammesso` lato backend.
          is_composizione_manuale: modo === "personalizzata",
          priorita,
          // Sprint 7.7 MR 1: cap km del ciclo specifico per regola.
          km_max_ciclo: kmCicloNum,
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

  const modoCorrente = MODI.find((m) => m.id === modo) ?? MODI[0];

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
            <div
              role="radiogroup"
              aria-label="Modalità composizione"
              className="flex flex-wrap gap-1.5 rounded-md border border-border bg-secondary/30 p-1"
            >
              {MODI.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  role="radio"
                  aria-checked={modo === m.id}
                  onClick={() => cambiaModo(m.id)}
                  disabled={addMutation.isPending}
                  className={cn(
                    "flex-1 rounded px-3 py-1.5 text-sm font-medium transition-colors",
                    "disabled:cursor-not-allowed disabled:opacity-50",
                    modo === m.id
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {m.label}
                </button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">{modoCorrente.hint}</p>
            <ComposizioneEditor
              composizione={composizione}
              modo={modo}
              onChange={setComposizione}
              disabled={addMutation.isPending}
            />
          </section>

          <section className="flex flex-col gap-1.5">
            <Label htmlFor="km-max-ciclo">km max per ciclo (opzionale)</Label>
            <Input
              id="km-max-ciclo"
              type="number"
              min={1}
              value={kmMaxCiclo}
              onChange={(e) => setKmMaxCiclo(e.target.value)}
              disabled={addMutation.isPending}
              placeholder="Es. 4500 — se vuoto, builder considera ~850 km/giorno medio"
            />
            <p className="text-xs text-muted-foreground">
              Cap chilometrico del ciclo per il materiale di questa regola (es. ETR526 ~4500
              km/ciclo, E464 ~6000). Quando raggiunto, il giro chiude appena il treno è in zona
              sede. Se vuoto, nessun limite hard — il giro chiude per safety net o naturalmente.
            </p>
          </section>

          <section className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="priorita" className="flex items-center gap-1.5">
                Priorità (0-100)
                <HelpCircle
                  className="h-3.5 w-3.5 cursor-help text-muted-foreground"
                  aria-hidden
                />
                <span className="sr-only">
                  La priorità serve solo se due regole coprono la stessa corsa: vince quella con
                  numero più alto. Se le tue regole non si sovrappongono, lascia il valore di
                  default.
                </span>
              </Label>
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
                title="Conta solo se due regole coprono la stessa corsa: vince la priorità più alta. Se le tue regole sono disgiunte, lascia 60."
              />
              <p className="text-xs text-muted-foreground">
                Conta solo se due regole coprono la stessa corsa: vince la priorità più alta.
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
              placeholder="Es. Solo diretti Mi.Centrale↔Tirano (130 corse linea)"
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
