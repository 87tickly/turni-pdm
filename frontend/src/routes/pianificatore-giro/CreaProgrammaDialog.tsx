import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Plus, Trash2 } from "lucide-react";

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
import { Textarea } from "@/components/ui/Textarea";
import {
  useCreateRegolaInvioSosta,
  useLocalitaSosta,
  useMateriali,
  useStazioni,
} from "@/hooks/useAnagrafiche";
import { useCreateProgramma } from "@/hooks/useProgrammi";
import { ApiError } from "@/lib/api/client";
import type { MaterialeRead, RegolaInvioSostaCreate } from "@/lib/api/anagrafiche";
import type { ProgrammaMaterialeRead } from "@/lib/api/programmi";
import { cn } from "@/lib/utils";

interface CreaProgrammaDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (programma: ProgrammaMaterialeRead) => void;
}

interface FormState {
  nome: string;
  valido_da: string;
  valido_a: string;
  /** Sprint 7.8: lunghezza minima giri (soft, default 4). */
  n_giornate_min: string;
  /** Sprint 7.8: lunghezza massima giri (hard cap, default 12). */
  n_giornate_max: string;
}

const INITIAL: FormState = {
  nome: "",
  valido_da: "",
  valido_a: "",
  n_giornate_min: "4",
  n_giornate_max: "12",
};

/**
 * Form modale di creazione programma.
 *
 * Crea sempre in stato `bozza`, senza regole (le regole si aggiungono
 * dopo nel dettaglio).
 *
 * NB Sprint 7.6/7.7 (decisione utente 2026-05-02): il programma materiale
 * è UN turno unico per la sua finestra di validità. Le giornate del
 * turno emergono dalla generazione dei giri (una per materiale/regola)
 * e si sommano nel programma — quindi NON si dichiarano in fase di
 * creazione del programma.
 *
 * Sprint 7.7 MR 1: il `km_max_ciclo` non si dichiara più sul programma
 * ma sotto la singola REGOLA (sotto materiale), perché ogni materiale
 * ha autonomie diverse. La colonna programma resta come legacy/fallback
 * lato backend.
 *
 * MR α (2026-05-06): aggiunto pannello "Materiali a disposizione" che
 * permette al pianificatore di selezionare il subset di MaterialeTipo
 * ammissibili nel programma. Default = tutti i materiali della dotazione
 * azienda checked → invia `[]` al backend (semantica "tutti", retrocompat).
 * Se l'utente deseleziona almeno un materiale, viene inviata la lista
 * esplicita dei codici checked.
 */
export function CreaProgrammaDialog({ open, onOpenChange, onCreated }: CreaProgrammaDialogProps) {
  const [form, setForm] = useState<FormState>(INITIAL);
  const [error, setError] = useState<string | null>(null);
  const createMutation = useCreateProgramma();
  const createRegolaInvioSostaMutation = useCreateRegolaInvioSosta();

  // MR α: anagrafica materiali azienda. La query è cached 5min, riusata
  // dagli altri pannelli, costo trascurabile. Lazy: parte solo quando il
  // dialog è aperto (evita fetch inutili in liste programmi).
  const materialiQuery = useMateriali({ enabled: open });
  const [materialiSelezionati, setMaterialiSelezionati] = useState<Set<string>>(
    new Set(),
  );

  // MR ε: regole invio sosta inline (mini-editor nel dialog di creazione).
  // Gestite come state locale; persistite via N POST sequenziali DOPO la
  // creazione del programma (servono il programma_id).
  const [regoleInvioSosta, setRegoleInvioSosta] = useState<RegolaInvioSostaDraft[]>([]);

  // Quando il dialog si apre per la prima volta o l'anagrafica arriva,
  // pre-popola tutti i materiali come selezionati (= "tutti", default).
  // Difensivo: se la query ritorna shape inattesa (test mock generici),
  // ignoriamo silenziosamente per non far crashare il dialog.
  useEffect(() => {
    if (!open) return;
    const data = materialiQuery.data;
    if (!Array.isArray(data)) return;
    const codiciMacro = data
      .filter((m) => m != null && m.famiglia != null && m.famiglia.length > 0)
      .map((m) => m.codice);
    setMaterialiSelezionati((prev) => (prev.size === 0 ? new Set(codiciMacro) : prev));
  }, [open, materialiQuery.data]);

  const minN = Number.parseInt(form.n_giornate_min, 10);
  const maxN = Number.parseInt(form.n_giornate_max, 10);
  const rangeOk =
    Number.isInteger(minN) &&
    Number.isInteger(maxN) &&
    minN >= 1 &&
    minN <= 30 &&
    maxN >= minN &&
    maxN <= 30;

  // Materiali macro raggruppati per famiglia per UX più ordinata.
  // Difensivo: se data non è un array, ritorniamo lista vuota.
  const materialiMacro = useMemo(() => {
    const data = materialiQuery.data;
    if (!Array.isArray(data)) return [];
    return data.filter(
      (m) => m != null && m.famiglia != null && m.famiglia.length > 0,
    );
  }, [materialiQuery.data]);

  const isValid =
    form.nome.length > 0 &&
    form.valido_da.length > 0 &&
    form.valido_a.length > 0 &&
    form.valido_a >= form.valido_da &&
    rangeOk &&
    // Se l'azienda non ha materiali registrati, permettiamo la creazione
    // del programma con `materiali_disponibili_codici_json=[]` (semantica
    // "tutti i materiali della dotazione", coerente con default backend).
    (materialiMacro.length === 0 || materialiSelezionati.size > 0);

  const handleClose = (next: boolean) => {
    if (!next) {
      setForm(INITIAL);
      setError(null);
      setMaterialiSelezionati(new Set());
      setRegoleInvioSosta([]);
    }
    onOpenChange(next);
  };

  const toggleMateriale = (codice: string) => {
    setMaterialiSelezionati((prev) => {
      const next = new Set(prev);
      if (next.has(codice)) {
        next.delete(codice);
      } else {
        next.add(codice);
      }
      return next;
    });
  };

  const materialiPerFamiglia = useMemo(() => {
    const map: Record<string, MaterialeRead[]> = {};
    for (const m of materialiMacro) {
      const fam = m.famiglia ?? "Altro";
      map[fam] = map[fam] ?? [];
      map[fam].push(m);
    }
    return Object.entries(map).sort(([a], [b]) => a.localeCompare(b));
  }, [materialiMacro]);

  const tuttiSelezionati =
    materialiMacro.length > 0 && materialiSelezionati.size === materialiMacro.length;

  const toggleTutti = () => {
    if (tuttiSelezionati) {
      setMaterialiSelezionati(new Set());
    } else {
      setMaterialiSelezionati(new Set(materialiMacro.map((m) => m.codice)));
    }
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!isValid) return;
    setError(null);

    try {
      // MR α: se l'utente ha lasciato TUTTI i materiali selezionati, mandiamo
      // `[]` al backend per coerenza con la semantica "tutti = lista vuota"
      // (retrocompat con i programmi esistenti). Solo se ha deselezionato
      // qualcosa mandiamo la lista esplicita.
      const materiali_disponibili_codici_json = tuttiSelezionati
        ? []
        : Array.from(materialiSelezionati).sort();

      const created = await createMutation.mutateAsync({
        nome: form.nome.trim(),
        valido_da: form.valido_da,
        valido_a: form.valido_a,
        n_giornate_min: minN,
        n_giornate_max: maxN,
        materiali_disponibili_codici_json,
        // Sprint 7.7 MR 1: niente km_max_ciclo qui (sposta sotto regola).
        // Sprint 7.6: niente n_giornate_default (backend default 1).
      });

      // MR ε: post-creazione, persiste le regole invio sosta inline.
      // Errori singoli vengono raccolti ma non bloccano il flusso (il
      // programma è già stato creato; l'utente potrà ritentare le regole
      // dalla sezione dedicata nel dettaglio).
      const sostaErrors: string[] = [];
      for (const regola of regoleInvioSosta) {
        if (!isRegolaSostaCompilata(regola)) continue;
        try {
          await createRegolaInvioSostaMutation.mutateAsync({
            programmaId: created.id,
            body: draftToCreatePayload(regola),
          });
        } catch (err) {
          const msg = err instanceof ApiError ? err.message : (err as Error).message;
          sostaErrors.push(msg);
        }
      }
      if (sostaErrors.length > 0) {
        // Mostra warning all'utente ma chiude comunque (programma creato).
        window.alert(
          `Programma creato. Alcune regole invio sosta non sono state salvate (` +
            `${sostaErrors.length} errori): ${sostaErrors.join("; ")}. Puoi aggiungerle ` +
            `dal dettaglio programma.`,
        );
      }

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
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Nuovo programma materiale</DialogTitle>
          <DialogDescription>
            Crea il programma in stato bozza. Le regole di assegnazione si configurano
            successivamente nel dettaglio.
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={handleSubmit}
          className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto"
          noValidate
        >
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
            <Label>Lunghezza giri (giornate)</Label>
            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-1">
                <Input
                  id="n_giornate_min"
                  type="number"
                  min={1}
                  max={30}
                  value={form.n_giornate_min}
                  onChange={(e) => update("n_giornate_min", e.target.value)}
                  disabled={createMutation.isPending}
                  aria-label="Lunghezza minima giri"
                />
                <span className="text-xs text-muted-foreground">
                  Minimo (soft) — il builder può scendere sotto solo per chiudere le
                  corse residue.
                </span>
              </div>
              <div className="flex flex-col gap-1">
                <Input
                  id="n_giornate_max"
                  type="number"
                  min={1}
                  max={30}
                  value={form.n_giornate_max}
                  onChange={(e) => update("n_giornate_max", e.target.value)}
                  disabled={createMutation.isPending}
                  aria-label="Lunghezza massima giri"
                />
                <span className="text-xs text-muted-foreground">
                  Massimo (hard) — nessun giro supera questa lunghezza.
                </span>
              </div>
            </div>
            {!rangeOk && (form.n_giornate_min !== "" || form.n_giornate_max !== "") && (
              <p className="text-xs text-destructive">
                Inserisci due interi tra 1 e 30 con max ≥ min.
              </p>
            )}
          </div>

          {/* MR α: pannello multi-select "Materiali a disposizione".
              NB: usiamo `<span>` invece di `<Label>` per il titolo della
              sezione perché non punta a un singolo input (è un raggruppamento
              multi-checkbox); così non interferisce con `getByLabelText` di
              testing-library, che richiede un input "labellable" per ogni
              `<label>`. */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium leading-none">
                Materiali a disposizione
              </span>
              <button
                type="button"
                onClick={toggleTutti}
                disabled={createMutation.isPending || materialiMacro.length === 0}
                className="text-xs text-primary hover:underline disabled:cursor-not-allowed disabled:opacity-50"
              >
                {tuttiSelezionati ? "Deseleziona tutti" : "Seleziona tutti"}
              </button>
            </div>
            <p className="text-xs text-muted-foreground">
              Spunta i materiali della dotazione che vuoi rendere ammissibili in questo
              programma. Lasciandoli tutti selezionati, il programma può usare l&apos;intera
              flotta. Quando assegnerai un materiale a una regola, potrai scegliere solo da
              questo elenco.
            </p>
            {materialiQuery.isLoading ? (
              <div className="flex items-center justify-center rounded-md border border-border bg-muted/30 py-6">
                <Spinner label="Caricamento materiali…" />
              </div>
            ) : materialiMacro.length === 0 ? (
              <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                Nessun materiale registrato per la tua azienda. Contatta un admin per
                popolare l&apos;anagrafica.
              </p>
            ) : (
              <div className="flex flex-col gap-3 rounded-md border border-border bg-secondary/20 p-3">
                {materialiPerFamiglia.map(([famiglia, items]) => (
                  <div key={famiglia} className="flex flex-col gap-1.5">
                    <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                      {famiglia}
                    </div>
                    <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
                      {items.map((m) => {
                        const checked = materialiSelezionati.has(m.codice);
                        const dotazione = m.pezzi_disponibili;
                        return (
                          <label
                            key={m.codice}
                            className={cn(
                              "flex cursor-pointer items-start gap-2 rounded border px-2 py-1.5 text-sm",
                              checked
                                ? "border-primary/40 bg-primary/5"
                                : "border-border bg-background hover:bg-muted/40",
                              createMutation.isPending && "cursor-not-allowed opacity-60",
                            )}
                          >
                            <input
                              type="checkbox"
                              checked={checked}
                              disabled={createMutation.isPending}
                              onChange={() => toggleMateriale(m.codice)}
                              className="mt-0.5"
                            />
                            <div className="min-w-0 flex-1">
                              <div className="flex items-baseline justify-between gap-1">
                                <span className="font-mono text-xs font-semibold">
                                  {m.codice}
                                </span>
                                <span className="text-[11px] text-muted-foreground">
                                  {dotazione === null
                                    ? "∞"
                                    : `× ${dotazione.toLocaleString("it-IT")}`}
                                </span>
                              </div>
                              {m.nome_commerciale !== null && m.nome_commerciale !== "" && (
                                <div className="truncate text-[11px] text-muted-foreground">
                                  {m.nome_commerciale}
                                </div>
                              )}
                            </div>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                ))}
                <div className="border-t border-border pt-2 text-xs text-muted-foreground">
                  {materialiSelezionati.size} di {materialiMacro.length} selezionati
                </div>
              </div>
            )}
            {materialiSelezionati.size === 0 && materialiMacro.length > 0 && (
              <p className="text-xs text-destructive">
                Seleziona almeno un materiale per il programma.
              </p>
            )}
          </div>

          {/* MR ε: mini-editor regole invio sosta (opzionale). */}
          <RegoleInvioSostaInlineEditor
            open={open}
            disabled={createMutation.isPending || createRegolaInvioSostaMutation.isPending}
            regole={regoleInvioSosta}
            onChange={setRegoleInvioSosta}
          />

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

// =====================================================================
// MR ε — Mini-editor regole invio sosta inline
// =====================================================================

interface RegolaInvioSostaDraft {
  id: string;
  stazione_sgancio_codice: string;
  tipo_materiale_codice: string;
  /** Formato "HH:MM" (UI). */
  finestra_oraria_inizio: string;
  /** Formato "HH:MM" (UI). */
  finestra_oraria_fine: string;
  localita_sosta_id: string;
  fallback_sosta_id: string;
  note: string;
}

function makeRegolaSostaDraft(): RegolaInvioSostaDraft {
  return {
    id: `r-${Math.random().toString(36).slice(2, 10)}`,
    stazione_sgancio_codice: "",
    tipo_materiale_codice: "",
    finestra_oraria_inizio: "06:00",
    finestra_oraria_fine: "19:00",
    localita_sosta_id: "",
    fallback_sosta_id: "",
    note: "",
  };
}

function isRegolaSostaCompilata(d: RegolaInvioSostaDraft): boolean {
  return (
    d.stazione_sgancio_codice.length > 0 &&
    d.tipo_materiale_codice.length > 0 &&
    d.localita_sosta_id.length > 0
  );
}

function draftToCreatePayload(d: RegolaInvioSostaDraft): RegolaInvioSostaCreate {
  return {
    stazione_sgancio_codice: d.stazione_sgancio_codice,
    tipo_materiale_codice: d.tipo_materiale_codice,
    finestra_oraria_inizio: `${d.finestra_oraria_inizio}:00`,
    finestra_oraria_fine: `${d.finestra_oraria_fine}:00`,
    localita_sosta_id: Number(d.localita_sosta_id),
    fallback_sosta_id:
      d.fallback_sosta_id.length > 0 ? Number(d.fallback_sosta_id) : null,
    note: d.note.trim().length > 0 ? d.note.trim() : null,
  };
}

function RegoleInvioSostaInlineEditor({
  open,
  disabled,
  regole,
  onChange,
}: {
  open: boolean;
  disabled: boolean;
  regole: RegolaInvioSostaDraft[];
  onChange: (regole: RegolaInvioSostaDraft[]) => void;
}) {
  const stazioniQuery = useStazioni();
  const materialiQuery = useMateriali({ enabled: open });
  const sosteQuery = useLocalitaSosta();
  const sosteAttive = (sosteQuery.data ?? []).filter((s) => s.is_attiva);

  const aggiungi = () => onChange([...regole, makeRegolaSostaDraft()]);
  const rimuovi = (id: string) => onChange(regole.filter((r) => r.id !== id));
  const aggiorna = (id: string, patch: Partial<RegolaInvioSostaDraft>) =>
    onChange(regole.map((r) => (r.id === id ? { ...r, ...patch } : r)));

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium leading-none">
          Regole invio sosta (opzionali)
        </span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={aggiungi}
          disabled={disabled}
        >
          <Plus className="mr-1 h-3.5 w-3.5" aria-hidden /> Nuova regola
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Quando un materiale viene sganciato a una stazione in una finestra oraria, viene
        inviato a una località di sosta invece che al deposito di sede. Le regole non sono
        obbligatorie: se vuoto, gli sganci ricadono sul fallback &quot;deposito sede&quot;.
      </p>
      {regole.length === 0 ? (
        <p className="rounded-md border border-dashed border-border bg-muted/30 px-3 py-3 text-xs italic text-muted-foreground">
          Nessuna regola configurata.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {regole.map((r) => (
            <div
              key={r.id}
              className="flex flex-col gap-2 rounded-md border border-border bg-secondary/20 p-3"
            >
              <div className="grid grid-cols-2 gap-2">
                <div className="flex flex-col gap-1">
                  <Label className="text-xs">Stazione di sgancio</Label>
                  <Select
                    value={r.stazione_sgancio_codice}
                    disabled={disabled || stazioniQuery.isLoading}
                    onChange={(e) =>
                      aggiorna(r.id, { stazione_sgancio_codice: e.target.value })
                    }
                  >
                    <option value="">— scegli —</option>
                    {(stazioniQuery.data ?? []).map((s) => (
                      <option key={s.codice} value={s.codice}>
                        {s.nome} ({s.codice})
                      </option>
                    ))}
                  </Select>
                </div>
                <div className="flex flex-col gap-1">
                  <Label className="text-xs">Tipo materiale</Label>
                  <Select
                    value={r.tipo_materiale_codice}
                    disabled={disabled || materialiQuery.isLoading}
                    onChange={(e) =>
                      aggiorna(r.id, { tipo_materiale_codice: e.target.value })
                    }
                  >
                    <option value="">— scegli —</option>
                    {(materialiQuery.data ?? []).map((m) => (
                      <option key={m.codice} value={m.codice}>
                        {m.codice}
                      </option>
                    ))}
                  </Select>
                </div>
                <div className="flex flex-col gap-1">
                  <Label className="text-xs">Finestra inizio</Label>
                  <Input
                    type="time"
                    value={r.finestra_oraria_inizio}
                    disabled={disabled}
                    onChange={(e) =>
                      aggiorna(r.id, { finestra_oraria_inizio: e.target.value })
                    }
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <Label className="text-xs">Finestra fine</Label>
                  <Input
                    type="time"
                    value={r.finestra_oraria_fine}
                    disabled={disabled}
                    onChange={(e) =>
                      aggiorna(r.id, { finestra_oraria_fine: e.target.value })
                    }
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <Label className="text-xs">Località di sosta</Label>
                  <Select
                    value={r.localita_sosta_id}
                    disabled={disabled || sosteQuery.isLoading}
                    onChange={(e) => aggiorna(r.id, { localita_sosta_id: e.target.value })}
                  >
                    <option value="">— scegli —</option>
                    {sosteAttive.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.nome} ({s.codice})
                      </option>
                    ))}
                  </Select>
                </div>
                <div className="flex flex-col gap-1">
                  <Label className="text-xs">Fallback (opzionale)</Label>
                  <Select
                    value={r.fallback_sosta_id}
                    disabled={disabled || sosteQuery.isLoading}
                    onChange={(e) => aggiorna(r.id, { fallback_sosta_id: e.target.value })}
                  >
                    <option value="">— deposito sede —</option>
                    {sosteAttive
                      .filter((s) => String(s.id) !== r.localita_sosta_id)
                      .map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.nome} ({s.codice})
                        </option>
                      ))}
                  </Select>
                </div>
              </div>
              <div className="flex flex-col gap-1">
                <Label className="text-xs">Note (opzionale)</Label>
                <Textarea
                  rows={1}
                  value={r.note}
                  disabled={disabled}
                  onChange={(e) => aggiorna(r.id, { note: e.target.value })}
                  placeholder="Es. capacità Garibaldi limitata 06-19, dirottare a Misr"
                />
              </div>
              <div className="flex justify-end">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => rimuovi(r.id)}
                  disabled={disabled}
                  aria-label="Rimuovi regola"
                >
                  <Trash2 className="mr-1 h-3.5 w-3.5" aria-hidden /> Rimuovi
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
