/**
 * Sprint 7.9 MR β2-8 — UI gestione regole invio sosta intermedia.
 *
 * Pannello inline nella `ProgrammaDettaglioRoute` che permette al
 * pianificatore di configurare regole pre-builder per gli sganci che
 * non riagganciano: es. "ETR421 sganciato a Garibaldi 06:00-19:00 →
 * invio a Misr". Il backend espone già le API CRUD (β2-7); β2-8
 * chiude la UI mancante.
 *
 * Backlog β3 (citato in TN-UPDATE entry 137 limitazione 6):
 * integrazione builder ↔ regole resta da fare. Oggi `arricchisci_sourcing`
 * ignora queste regole e ricade su "Pezzi a deposito {SEDE}".
 */

import { useState } from "react";
import { Loader2, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import {
  Dialog,
  DialogClose,
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
  useDeleteRegolaInvioSosta,
  useLocalitaSosta,
  useMateriali,
  useRegoleInvioSosta,
  useStazioni,
} from "@/hooks/useAnagrafiche";
// Nota: useMateriali è usato solo nel Dialog di creazione qui sotto.
import { ApiError } from "@/lib/api/client";
import type { RegolaInvioSostaCreate, RegolaInvioSostaRead } from "@/lib/api/anagrafiche";

interface Props {
  programmaId: number;
  editable: boolean;
}

export function RegoleInvioSostaSection({ programmaId, editable }: Props) {
  const [open, setOpen] = useState(false);
  const regoleQuery = useRegoleInvioSosta(programmaId);
  const stazioniQuery = useStazioni();
  const sosteQuery = useLocalitaSosta();
  const deleteRegola = useDeleteRegolaInvioSosta();

  const stazioniByCodice = new Map(
    (stazioniQuery.data ?? []).map((s) => [s.codice, s]),
  );
  const sosteById = new Map(
    (sosteQuery.data ?? []).map((s) => [s.id, s]),
  );

  const regole = regoleQuery.data ?? [];

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-baseline gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-foreground">
            Regole invio sosta
          </h2>
          <span className="text-xs text-muted-foreground">
            {regole.length} {regole.length === 1 ? "regola" : "regole"}
            {regole.length === 0
              ? " · sganci senza regola → fallback deposito sede"
              : null}
          </span>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setOpen(true)}
          disabled={!editable}
          title={
            editable
              ? "Aggiungi una regola di invio sosta"
              : "Programma archiviato: regole read-only"
          }
        >
          <Plus className="mr-1 h-3.5 w-3.5" aria-hidden /> Nuova regola
        </Button>
      </div>

      <Card className="p-0">
        {regoleQuery.isLoading ? (
          <div className="flex items-center justify-center p-8 text-sm text-muted-foreground">
            <Spinner className="mr-2 h-4 w-4" /> Caricamento…
          </div>
        ) : regole.length === 0 ? (
          <div className="p-6 text-center text-sm text-muted-foreground">
            Nessuna regola configurata. Gli sganci che non trovano riaggancio
            vengono inviati al deposito di sede.
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {regole.map((r) => (
              <RegolaRow
                key={r.id}
                regola={r}
                stazioneNome={stazioniByCodice.get(r.stazione_sgancio_codice)?.nome ?? null}
                sostaNome={sosteById.get(r.localita_sosta_id)?.nome ?? null}
                fallbackNome={
                  r.fallback_sosta_id !== null
                    ? sosteById.get(r.fallback_sosta_id)?.nome ?? null
                    : null
                }
                onDelete={() =>
                  deleteRegola.mutate({ programmaId, regolaId: r.id })
                }
                disabled={!editable || deleteRegola.isPending}
              />
            ))}
          </ul>
        )}
      </Card>

      <NuovaRegolaDialog
        programmaId={programmaId}
        open={open}
        onOpenChange={setOpen}
      />
    </section>
  );
}

// =====================================================================
// Riga regola
// =====================================================================

function RegolaRow({
  regola,
  stazioneNome,
  sostaNome,
  fallbackNome,
  onDelete,
  disabled,
}: {
  regola: RegolaInvioSostaRead;
  stazioneNome: string | null;
  sostaNome: string | null;
  fallbackNome: string | null;
  onDelete: () => void;
  disabled: boolean;
}) {
  return (
    <li className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
      <div className="flex flex-1 flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="font-medium text-foreground">
          {regola.tipo_materiale_codice}
        </span>
        <span className="text-muted-foreground">sganciato a</span>
        <span className="font-medium text-foreground">
          {stazioneNome ?? regola.stazione_sgancio_codice}
        </span>
        <span className="text-muted-foreground">
          tra {fmtTime(regola.finestra_oraria_inizio)}–
          {fmtTime(regola.finestra_oraria_fine)}
        </span>
        <span className="text-muted-foreground">→</span>
        <span className="font-medium text-foreground">
          {sostaNome ?? `sosta #${regola.localita_sosta_id}`}
        </span>
        {fallbackNome !== null ? (
          <span className="text-xs text-muted-foreground">
            (fallback: {fallbackNome})
          </span>
        ) : null}
      </div>
      <Button
        variant="ghost"
        size="sm"
        onClick={onDelete}
        disabled={disabled}
        aria-label={`Elimina regola ${regola.id}`}
        title="Elimina regola"
      >
        <Trash2 className="h-3.5 w-3.5" aria-hidden />
      </Button>
    </li>
  );
}

function fmtTime(t: string): string {
  // Backend serializza time come "HH:MM:SS"; UI mostra HH:MM.
  return t.length >= 5 ? t.slice(0, 5) : t;
}

// =====================================================================
// Dialog "Nuova regola"
// =====================================================================

function NuovaRegolaDialog({
  programmaId,
  open,
  onOpenChange,
}: {
  programmaId: number;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const stazioniQuery = useStazioni();
  const materialiQuery = useMateriali();
  const sosteQuery = useLocalitaSosta();
  const create = useCreateRegolaInvioSosta();

  const [stazione, setStazione] = useState("");
  const [materiale, setMateriale] = useState("");
  const [oraInizio, setOraInizio] = useState("06:00");
  const [oraFine, setOraFine] = useState("19:00");
  const [sostaId, setSostaId] = useState<string>("");
  const [fallbackId, setFallbackId] = useState<string>("");
  const [note, setNote] = useState("");
  const [errMsg, setErrMsg] = useState<string | null>(null);

  const sosteAttive = (sosteQuery.data ?? []).filter((s) => s.is_attiva);

  function reset() {
    setStazione("");
    setMateriale("");
    setOraInizio("06:00");
    setOraFine("19:00");
    setSostaId("");
    setFallbackId("");
    setNote("");
    setErrMsg(null);
  }

  function handleClose(v: boolean) {
    if (!v) reset();
    onOpenChange(v);
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErrMsg(null);
    if (stazione === "" || materiale === "" || sostaId === "") {
      setErrMsg("Compila stazione, materiale e località di sosta.");
      return;
    }
    if (oraFine <= oraInizio) {
      setErrMsg("Ora fine deve essere successiva all'ora inizio.");
      return;
    }
    const body: RegolaInvioSostaCreate = {
      stazione_sgancio_codice: stazione,
      tipo_materiale_codice: materiale,
      finestra_oraria_inizio: `${oraInizio}:00`,
      finestra_oraria_fine: `${oraFine}:00`,
      localita_sosta_id: Number(sostaId),
      fallback_sosta_id: fallbackId !== "" ? Number(fallbackId) : null,
      note: note.trim().length > 0 ? note.trim() : null,
    };
    try {
      await create.mutateAsync({ programmaId, body });
      handleClose(false);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrMsg(err.message);
      } else {
        setErrMsg("Errore nella creazione della regola.");
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nuova regola invio sosta</DialogTitle>
          <DialogDescription>
            Quando un materiale di tipo X viene sganciato alla stazione Y in
            una finestra oraria, viene inviato a una località di sosta invece
            che al deposito di sede.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="grid gap-3">
          <div className="grid gap-1">
            <Label htmlFor="reg-stazione">Stazione di sgancio</Label>
            <Select
              id="reg-stazione"
              value={stazione}
              onChange={(e) => setStazione(e.target.value)}
              disabled={stazioniQuery.isLoading}
            >
              <option value="">— scegli stazione —</option>
              {(stazioniQuery.data ?? []).map((s) => (
                <option key={s.codice} value={s.codice}>
                  {s.nome} ({s.codice})
                </option>
              ))}
            </Select>
          </div>

          <div className="grid gap-1">
            <Label htmlFor="reg-materiale">Tipo materiale</Label>
            <Select
              id="reg-materiale"
              value={materiale}
              onChange={(e) => setMateriale(e.target.value)}
              disabled={materialiQuery.isLoading}
            >
              <option value="">— scegli materiale —</option>
              {(materialiQuery.data ?? []).map((m) => (
                <option key={m.codice} value={m.codice}>
                  {m.codice}
                  {m.nome_commerciale !== null ? ` · ${m.nome_commerciale}` : ""}
                </option>
              ))}
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1">
              <Label htmlFor="reg-ora-inizio">Finestra inizio</Label>
              <Input
                id="reg-ora-inizio"
                type="time"
                value={oraInizio}
                onChange={(e) => setOraInizio(e.target.value)}
              />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="reg-ora-fine">Finestra fine</Label>
              <Input
                id="reg-ora-fine"
                type="time"
                value={oraFine}
                onChange={(e) => setOraFine(e.target.value)}
              />
            </div>
          </div>

          <div className="grid gap-1">
            <Label htmlFor="reg-sosta">Località di sosta</Label>
            <Select
              id="reg-sosta"
              value={sostaId}
              onChange={(e) => setSostaId(e.target.value)}
              disabled={sosteQuery.isLoading}
            >
              <option value="">— scegli località —</option>
              {sosteAttive.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.nome} ({s.codice})
                </option>
              ))}
            </Select>
          </div>

          <div className="grid gap-1">
            <Label htmlFor="reg-fallback">Fallback (opzionale)</Label>
            <Select
              id="reg-fallback"
              value={fallbackId}
              onChange={(e) => setFallbackId(e.target.value)}
              disabled={sosteQuery.isLoading}
            >
              <option value="">— nessun fallback (= deposito sede) —</option>
              {sosteAttive
                .filter((s) => String(s.id) !== sostaId)
                .map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.nome} ({s.codice})
                  </option>
                ))}
            </Select>
          </div>

          <div className="grid gap-1">
            <Label htmlFor="reg-note">Note</Label>
            <Textarea
              id="reg-note"
              rows={2}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Es. capacità Garibaldi limitata 06-19, dirottare a Misr"
            />
          </div>

          {errMsg !== null ? (
            <p className="text-sm text-destructive">{errMsg}</p>
          ) : null}

          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Annulla
              </Button>
            </DialogClose>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? (
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" aria-hidden />
              ) : null}
              Crea regola
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
