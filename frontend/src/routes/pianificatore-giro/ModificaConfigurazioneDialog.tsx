/**
 * MR ζ (2026-05-06) — dialog "Modifica configurazione" del programma.
 *
 * Spec utente:
 *
 * > "I tasti modifica non sono abilitati, io non una volta che genero
 * > non posso modificare nulla."
 *
 * Sostituisce i due bottoni "Modifica" + "Modifica configurazione"
 * (entrambi disabilitati in MR pre-ζ con tooltip "TN-UPDATE residuo").
 * Espone in un solo dialog tutti i campi modificabili via PATCH
 * ``/api/programmi/{id}``: nome, periodo validità, lunghezza giri,
 * km cap giornaliero, fascia oraria tolerance, materiali a
 * disposizione (subset).
 *
 * Le regole di assegnazione e le regole invio sosta restano
 * editabili dalle loro UI dedicate (RegolaEditor inline e
 * RegoleInvioSostaSection).
 *
 * Vincolo backend: il PATCH ritorna 409 se ``stato_pipeline_pdc >=
 * MATERIALE_CONFERMATO`` (freeze post handoff Materiale → PdC). Il
 * dialog mostra l'errore se capita.
 */

import { useEffect, useMemo, useState } from "react";
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
import { useMateriali } from "@/hooks/useAnagrafiche";
import { useUpdateProgramma } from "@/hooks/useProgrammi";
import { ApiError } from "@/lib/api/client";
import type { ProgrammaDettaglioRead } from "@/lib/api/programmi";
import { cn } from "@/lib/utils";

interface ModificaConfigurazioneDialogProps {
  programma: ProgrammaDettaglioRead;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved?: () => void;
}

export function ModificaConfigurazioneDialog({
  programma,
  open,
  onOpenChange,
  onSaved,
}: ModificaConfigurazioneDialogProps) {
  const updateMutation = useUpdateProgramma();
  const materialiQuery = useMateriali({ enabled: open });

  const [nome, setNome] = useState(programma.nome);
  const [validoDa, setValidoDa] = useState(programma.valido_da);
  const [validoA, setValidoA] = useState(programma.valido_a);
  const [nGiornateMin, setNGiornateMin] = useState(String(programma.n_giornate_min));
  const [nGiornateMax, setNGiornateMax] = useState(String(programma.n_giornate_max));
  const [kmMaxGiornaliero, setKmMaxGiornaliero] = useState(
    programma.km_max_giornaliero === null ? "" : String(programma.km_max_giornaliero),
  );
  const [fasciaToler, setFasciaToler] = useState(
    String(programma.fascia_oraria_tolerance_min),
  );
  const [materialiSelezionati, setMaterialiSelezionati] = useState<Set<string>>(
    new Set(programma.materiali_disponibili_codici_json),
  );
  const [error, setError] = useState<string | null>(null);

  // Re-init quando il dialog si riapre o cambia il programma sotto.
  useEffect(() => {
    if (!open) return;
    setNome(programma.nome);
    setValidoDa(programma.valido_da);
    setValidoA(programma.valido_a);
    setNGiornateMin(String(programma.n_giornate_min));
    setNGiornateMax(String(programma.n_giornate_max));
    setKmMaxGiornaliero(
      programma.km_max_giornaliero === null ? "" : String(programma.km_max_giornaliero),
    );
    setFasciaToler(String(programma.fascia_oraria_tolerance_min));
    setMaterialiSelezionati(new Set(programma.materiali_disponibili_codici_json));
    setError(null);
  }, [open, programma]);

  const minN = Number.parseInt(nGiornateMin, 10);
  const maxN = Number.parseInt(nGiornateMax, 10);
  const rangeOk =
    Number.isInteger(minN) &&
    Number.isInteger(maxN) &&
    minN >= 1 &&
    minN <= 30 &&
    maxN >= minN &&
    maxN <= 30;

  const fasciaTolNum = Number.parseInt(fasciaToler, 10);
  const fasciaOk = Number.isInteger(fasciaTolNum) && fasciaTolNum >= 0 && fasciaTolNum <= 120;

  const kmMaxNum = kmMaxGiornaliero.trim() === "" ? null : Number(kmMaxGiornaliero);
  const kmMaxOk = kmMaxNum === null || (Number.isFinite(kmMaxNum) && kmMaxNum >= 1);

  const materialiMacro = useMemo(() => {
    const data = materialiQuery.data;
    if (!Array.isArray(data)) return [];
    return data.filter((m) => m != null && m.famiglia != null && m.famiglia.length > 0);
  }, [materialiQuery.data]);

  const tuttiSelezionati =
    materialiMacro.length > 0 && materialiSelezionati.size === materialiMacro.length;
  const isValid =
    nome.length > 0 &&
    validoDa.length > 0 &&
    validoA.length > 0 &&
    validoA >= validoDa &&
    rangeOk &&
    fasciaOk &&
    kmMaxOk &&
    (materialiMacro.length === 0 || materialiSelezionati.size > 0);

  const toggleMateriale = (codice: string) => {
    setMaterialiSelezionati((prev) => {
      const next = new Set(prev);
      if (next.has(codice)) next.delete(codice);
      else next.add(codice);
      return next;
    });
  };

  const toggleTutti = () => {
    if (tuttiSelezionati) {
      setMaterialiSelezionati(new Set());
    } else {
      setMaterialiSelezionati(new Set(materialiMacro.map((m) => m.codice)));
    }
  };

  const handleClose = (next: boolean) => {
    if (!next) setError(null);
    onOpenChange(next);
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!isValid) return;
    setError(null);

    // Calcola subset materiali (vuoto = tutti).
    const materiali_disponibili_codici_json = tuttiSelezionati
      ? []
      : Array.from(materialiSelezionati).sort();

    try {
      await updateMutation.mutateAsync({
        id: programma.id,
        payload: {
          nome: nome.trim(),
          valido_da: validoDa,
          valido_a: validoA,
          n_giornate_min: minN,
          n_giornate_max: maxN,
          km_max_giornaliero: kmMaxNum,
          fascia_oraria_tolerance_min: fasciaTolNum,
          materiali_disponibili_codici_json,
        },
      });
      onSaved?.();
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
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Modifica configurazione programma</DialogTitle>
          <DialogDescription>
            Modifica nome, periodo, lunghezza giri, km cap giornaliero, fascia oraria
            tolerance e subset materiali in flotta. Le regole di assegnazione e le regole
            invio sosta si modificano dalle rispettive sezioni nel dettaglio.
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={handleSubmit}
          className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto"
          noValidate
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="mod-nome">Nome</Label>
            <Input
              id="mod-nome"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              required
              disabled={updateMutation.isPending}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="mod-valido-da">Valido dal</Label>
              <Input
                id="mod-valido-da"
                type="date"
                value={validoDa}
                onChange={(e) => setValidoDa(e.target.value)}
                required
                disabled={updateMutation.isPending}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="mod-valido-a">Valido al</Label>
              <Input
                id="mod-valido-a"
                type="date"
                value={validoA}
                onChange={(e) => setValidoA(e.target.value)}
                required
                disabled={updateMutation.isPending}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="mod-min">Lunghezza giri (min, soft)</Label>
              <Input
                id="mod-min"
                type="number"
                min={1}
                max={30}
                value={nGiornateMin}
                onChange={(e) => setNGiornateMin(e.target.value)}
                disabled={updateMutation.isPending}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="mod-max">Lunghezza giri (max, hard)</Label>
              <Input
                id="mod-max"
                type="number"
                min={1}
                max={30}
                value={nGiornateMax}
                onChange={(e) => setNGiornateMax(e.target.value)}
                disabled={updateMutation.isPending}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="mod-km">Km max / giorno (opzionale)</Label>
              <Input
                id="mod-km"
                type="number"
                min={1}
                value={kmMaxGiornaliero}
                onChange={(e) => setKmMaxGiornaliero(e.target.value)}
                disabled={updateMutation.isPending}
                placeholder="vuoto = nessun limite"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="mod-fascia">Fascia oraria tolerance (min)</Label>
              <Input
                id="mod-fascia"
                type="number"
                min={0}
                max={120}
                value={fasciaToler}
                onChange={(e) => setFasciaToler(e.target.value)}
                disabled={updateMutation.isPending}
              />
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium leading-none">
                Materiali a disposizione
              </span>
              <button
                type="button"
                onClick={toggleTutti}
                disabled={updateMutation.isPending || materialiMacro.length === 0}
                className="text-xs text-primary hover:underline disabled:cursor-not-allowed disabled:opacity-50"
              >
                {tuttiSelezionati ? "Deseleziona tutti" : "Seleziona tutti"}
              </button>
            </div>
            <p className="text-xs text-muted-foreground">
              Subset di materiali ammissibili in questo programma. Tutti selezionati = invia
              `[]` al backend (semantica retrocompat &quot;tutti i materiali della flotta
              azienda&quot;).
            </p>
            {materialiQuery.isLoading ? (
              <div className="flex items-center justify-center rounded-md border border-border bg-muted/30 py-6">
                <Spinner label="Caricamento materiali…" />
              </div>
            ) : materialiMacro.length === 0 ? (
              <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                Nessun materiale registrato per la tua azienda.
              </p>
            ) : (
              <div className="grid max-h-48 grid-cols-2 gap-1 overflow-y-auto rounded-md border border-border bg-secondary/20 p-2">
                {materialiMacro.map((m) => {
                  const checked = materialiSelezionati.has(m.codice);
                  return (
                    <label
                      key={m.codice}
                      className={cn(
                        "flex cursor-pointer items-center gap-2 rounded border px-2 py-1 text-sm",
                        checked
                          ? "border-primary/40 bg-primary/5"
                          : "border-border bg-background hover:bg-muted/40",
                        updateMutation.isPending && "cursor-not-allowed opacity-60",
                      )}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={updateMutation.isPending}
                        onChange={() => toggleMateriale(m.codice)}
                      />
                      <span className="font-mono text-xs">{m.codice}</span>
                      {m.pezzi_disponibili !== null && (
                        <span className="ml-auto text-[10px] text-muted-foreground">
                          ×{m.pezzi_disponibili}
                        </span>
                      )}
                    </label>
                  );
                })}
              </div>
            )}
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
              disabled={updateMutation.isPending}
            >
              Annulla
            </Button>
            <Button type="submit" disabled={!isValid || updateMutation.isPending}>
              {updateMutation.isPending ? <Spinner label="Salvataggio…" /> : "Salva modifiche"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
