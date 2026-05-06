import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronRight, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import { useLocalitaManutenzione, useMateriali } from "@/hooks/useAnagrafiche";
import { useGeneraGiri } from "@/hooks/useGiri";
import { useProgramma, useUpdateRegola } from "@/hooks/useProgrammi";
import { ApiError } from "@/lib/api/client";
import type { MaterialeRead } from "@/lib/api/anagrafiche";
import type { BuilderResult } from "@/lib/api/giri";
import type { ProgrammaRegolaAssegnazioneRead } from "@/lib/api/programmi";
import { cn } from "@/lib/utils";

interface GeneraGiriDialogProps {
  programmaId: number;
  /** `programma.valido_da` (ISO date `YYYY-MM-DD`). Mostrato come info di contesto. */
  validoDa: string;
  /** `programma.valido_a` (ISO date `YYYY-MM-DD`). Mostrato come info di contesto. */
  validoA: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCompleted?: (result: AggregatedResult) => void;
}

/**
 * MR β (2026-05-06) — wizard pre-generazione multi-step.
 *
 * Spec utente:
 *
 * > "Quando schiaccio su genera giri, lui prima di farlo, mi apre una
 * > pagina con tutte le linee che io ho deciso di voler generare, lì
 * > assegno i materiali e il deposito e successivamente genero il giro."
 *
 * Step 1 — **Anteprima regole**: tabella con tutte le regole del
 * programma. Per ogni regola: nome (filtri compatti) + dropdown sede
 * (precompilato da `regola.localita_codice` se memorizzata).
 *
 * Step 2 — **Esecuzione sequenziale**: il wizard raggruppa le regole
 * per sede unica e invoca `POST /api/programmi/{id}/genera-giri` una
 * volta per ogni sede. Le sedi modificate dall'utente vengono
 * auto-salvate sulla regola via PATCH (idempotente).
 *
 * Step 3 — **Riepilogo**: counters aggregati su tutte le sedi
 * processate.
 *
 * Il composizione (materiale ipotesi) resta sulla regola in MR β
 * (composizione obbligatoria, come oggi). MR γ la renderà opzionale e
 * il wizard avrà anche un dropdown materiale per regola.
 */

interface PerRegolaState {
  regola: ProgrammaRegolaAssegnazioneRead;
  /** Codice sede scelto/modificato per questo run. */
  localita: string;
  /** True se la sede differisce da `regola.localita_codice` (auto-save al lancio). */
  localita_modificata: boolean;
  /**
   * MR γ: materiale "ipotesi" — codice del MaterialeTipo che il builder
   * userà come composizione. Precompilato dal primo elemento di
   * `regola.composizione_json` se presente, altrimenti vuoto (l'utente
   * deve sceglierlo nel wizard, non si lancia builder senza).
   */
  materiale: string;
  /** True se il materiale differisce da quello memorizzato sulla regola. */
  materiale_modificato: boolean;
}

export interface AggregatedResult {
  n_sedi_processate: number;
  n_giri_creati_totale: number;
  n_corse_processate_totale: number;
  n_corse_residue_totale: number;
  n_giri_chiusi_totale: number;
  n_giri_non_chiusi_totale: number;
  warnings: string[];
  errori_per_sede: Array<{ sede: string; messaggio: string }>;
  per_sede: Array<{ sede: string; result: BuilderResult }>;
}

type Step = "form" | "running" | "done";

export function GeneraGiriDialog({
  programmaId,
  validoDa,
  validoA,
  open,
  onOpenChange,
  onCompleted,
}: GeneraGiriDialogProps) {
  const programmaQuery = useProgramma(open ? programmaId : undefined);
  const localitaQuery = useLocalitaManutenzione({ enabled: open });
  const materialiQuery = useMateriali({ enabled: open });
  const generaMutation = useGeneraGiri();
  const updateRegolaMutation = useUpdateRegola();

  const [step, setStep] = useState<Step>("form");
  const [perRegola, setPerRegola] = useState<Record<number, PerRegolaState>>({});
  /** Sede correntemente in corso di generazione (UX progress). */
  const [sedeCorrente, setSedeCorrente] = useState<string | null>(null);
  /** Sede totale per il progress. */
  const [sediTotali, setSediTotali] = useState<number>(0);
  const [aggregato, setAggregato] = useState<AggregatedResult | null>(null);
  const [globalError, setGlobalError] = useState<string | null>(null);
  /** Sprint 7.9 strategy A: conferma cancellazione cascata PdC su tutte le sedi. */
  const [confirmDeletePdc, setConfirmDeletePdc] = useState(false);

  const regole = programmaQuery.data?.regole ?? [];
  const localita = localitaQuery.data ?? [];
  const materialiMacro = useMemo(() => {
    const data = materialiQuery.data;
    if (!Array.isArray(data)) return [] as MaterialeRead[];
    return data.filter(
      (m) => m != null && m.famiglia != null && m.famiglia.length > 0,
    );
  }, [materialiQuery.data]);

  // Pre-popola lo state per regola quando il dialog si apre o le regole arrivano.
  useEffect(() => {
    if (!open || regole.length === 0) return;
    setPerRegola((prev) => {
      const next: Record<number, PerRegolaState> = {};
      for (const r of regole) {
        const esistente = prev[r.id];
        const localitaPrecompilata = esistente?.localita ?? r.localita_codice ?? "";
        const materialeMemorizzato = r.composizione_json[0]?.materiale_tipo_codice ?? "";
        const materialePrecompilato = esistente?.materiale ?? materialeMemorizzato;
        next[r.id] = {
          regola: r,
          localita: localitaPrecompilata,
          localita_modificata:
            esistente?.localita_modificata === true
              ? true
              : (r.localita_codice ?? "") !== localitaPrecompilata,
          materiale: materialePrecompilato,
          materiale_modificato:
            esistente?.materiale_modificato === true
              ? true
              : materialeMemorizzato !== materialePrecompilato,
        };
      }
      return next;
    });
  }, [open, regole]);

  const handleClose = (next: boolean) => {
    if (!next) {
      setStep("form");
      setPerRegola({});
      setSedeCorrente(null);
      setSediTotali(0);
      setAggregato(null);
      setGlobalError(null);
      setConfirmDeletePdc(false);
    }
    onOpenChange(next);
  };

  const cambiaLocalita = (regolaId: number, value: string) => {
    setPerRegola((prev) => {
      const stato = prev[regolaId];
      if (stato === undefined) return prev;
      const persistita = stato.regola.localita_codice ?? "";
      return {
        ...prev,
        [regolaId]: {
          ...stato,
          localita: value,
          localita_modificata: value !== persistita,
        },
      };
    });
  };

  const cambiaMateriale = (regolaId: number, value: string) => {
    setPerRegola((prev) => {
      const stato = prev[regolaId];
      if (stato === undefined) return prev;
      const memorizzato = stato.regola.composizione_json[0]?.materiale_tipo_codice ?? "";
      return {
        ...prev,
        [regolaId]: {
          ...stato,
          materiale: value,
          materiale_modificato: value !== memorizzato,
        },
      };
    });
  };

  const tutteSediCompilate = useMemo(() => {
    if (regole.length === 0) return false;
    return regole.every((r) => (perRegola[r.id]?.localita ?? "").length > 0);
  }, [regole, perRegola]);

  const tuttiMaterialiCompilati = useMemo(() => {
    if (regole.length === 0) return false;
    return regole.every((r) => (perRegola[r.id]?.materiale ?? "").length > 0);
  }, [regole, perRegola]);

  // Sedi uniche da processare (1 chiamata builder per sede).
  const sediUniche = useMemo(() => {
    const set = new Set<string>();
    for (const r of regole) {
      const sede = perRegola[r.id]?.localita ?? "";
      if (sede.length > 0) set.add(sede);
    }
    return Array.from(set).sort();
  }, [regole, perRegola]);

  const avviaGenerazione = async () => {
    if (!tutteSediCompilate || !tuttiMaterialiCompilati) return;
    setStep("running");
    setGlobalError(null);
    setSediTotali(sediUniche.length);

    const aggregato_local: AggregatedResult = {
      n_sedi_processate: 0,
      n_giri_creati_totale: 0,
      n_corse_processate_totale: 0,
      n_corse_residue_totale: 0,
      n_giri_chiusi_totale: 0,
      n_giri_non_chiusi_totale: 0,
      warnings: [],
      errori_per_sede: [],
      per_sede: [],
    };

    // Auto-save: per ogni regola con sede o materiale modificato (o
    // entrambi), un solo PATCH idempotente. Non blocca il run su errore
    // singolo: il builder userà comunque i valori del payload (che
    // sono coerenti con quelli appena scelti dall'utente).
    for (const stato of Object.values(perRegola)) {
      if (!stato.localita_modificata && !stato.materiale_modificato) continue;
      const patchPayload: {
        localita_codice?: string | null;
        composizione?: Array<{ materiale_tipo_codice: string; n_pezzi: number }>;
      } = {};
      if (stato.localita_modificata) {
        patchPayload.localita_codice = stato.localita || null;
      }
      if (stato.materiale_modificato) {
        // MR γ: il wizard scrive composizione "singola" di default
        // (1 pezzo). Per doppia/personalizzata l'utente deve passare
        // dall'editor regola.
        patchPayload.composizione = stato.materiale
          ? [{ materiale_tipo_codice: stato.materiale, n_pezzi: 1 }]
          : [];
      }
      try {
        await updateRegolaMutation.mutateAsync({
          programmaId,
          regolaId: stato.regola.id,
          payload: patchPayload,
        });
      } catch (err) {
        const msg = err instanceof ApiError ? err.message : (err as Error).message;
        aggregato_local.warnings.push(
          `Auto-save regola #${stato.regola.id} fallito: ${msg}`,
        );
      }
    }

    // Esegue il builder per ogni sede unica, in serie.
    for (const sede of sediUniche) {
      setSedeCorrente(sede);
      try {
        const result = await generaMutation.mutateAsync({
          programmaId,
          params: {
            localita_codice: sede,
            // force=true: il backend cancella e ricostruisce solo i giri
            // della sede target; le altre sedi del programma restano
            // intatte (vedi `genera_giri` Sprint 7.9 strategy A).
            force: true,
            confirm_delete_pdc: confirmDeletePdc,
          },
        });
        aggregato_local.n_sedi_processate += 1;
        aggregato_local.n_giri_creati_totale += result.n_giri_creati;
        aggregato_local.n_corse_processate_totale += result.n_corse_processate;
        aggregato_local.n_corse_residue_totale += result.n_corse_residue;
        aggregato_local.n_giri_chiusi_totale += result.n_giri_chiusi;
        aggregato_local.n_giri_non_chiusi_totale += result.n_giri_non_chiusi;
        aggregato_local.warnings.push(
          ...result.warnings.map((w) => `[${sede}] ${w}`),
        );
        aggregato_local.per_sede.push({ sede, result });
      } catch (err) {
        const msg =
          err instanceof ApiError
            ? err.message
            : err instanceof Error
              ? err.message
              : "Errore sconosciuto";
        aggregato_local.errori_per_sede.push({ sede, messaggio: msg });
      }
    }

    setAggregato(aggregato_local);
    setSedeCorrente(null);
    setStep("done");
    onCompleted?.(aggregato_local);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-3xl">
        {step === "form" && (
          <FormStep
            programmaQueryLoading={programmaQuery.isLoading}
            validoDa={validoDa}
            validoA={validoA}
            regole={regole}
            perRegola={perRegola}
            cambiaLocalita={cambiaLocalita}
            cambiaMateriale={cambiaMateriale}
            localita={localita}
            materialiMacro={materialiMacro}
            confirmDeletePdc={confirmDeletePdc}
            setConfirmDeletePdc={setConfirmDeletePdc}
            tutteSediCompilate={tutteSediCompilate}
            tuttiMaterialiCompilati={tuttiMaterialiCompilati}
            sediUniche={sediUniche}
            onAnnulla={() => handleClose(false)}
            onAvvia={avviaGenerazione}
            error={globalError}
          />
        )}
        {step === "running" && (
          <RunningStep sedeCorrente={sedeCorrente} sediTotali={sediTotali} />
        )}
        {step === "done" && aggregato !== null && (
          <DoneStep aggregato={aggregato} onClose={() => handleClose(false)} />
        )}
      </DialogContent>
    </Dialog>
  );
}

// =====================================================================
// Step 1 — Form
// =====================================================================

function FormStep({
  programmaQueryLoading,
  validoDa,
  validoA,
  regole,
  perRegola,
  cambiaLocalita,
  cambiaMateriale,
  localita,
  materialiMacro,
  confirmDeletePdc,
  setConfirmDeletePdc,
  tutteSediCompilate,
  tuttiMaterialiCompilati,
  sediUniche,
  onAnnulla,
  onAvvia,
  error,
}: {
  programmaQueryLoading: boolean;
  validoDa: string;
  validoA: string;
  regole: ProgrammaRegolaAssegnazioneRead[];
  perRegola: Record<number, PerRegolaState>;
  cambiaLocalita: (regolaId: number, value: string) => void;
  cambiaMateriale: (regolaId: number, value: string) => void;
  localita: ReturnType<typeof useLocalitaManutenzione>["data"];
  materialiMacro: MaterialeRead[];
  confirmDeletePdc: boolean;
  setConfirmDeletePdc: (v: boolean) => void;
  tutteSediCompilate: boolean;
  tuttiMaterialiCompilati: boolean;
  sediUniche: string[];
  onAnnulla: () => void;
  onAvvia: () => void;
  error: string | null;
}) {
  return (
    <>
      <DialogHeader>
        <DialogTitle>Genera giri materiale — wizard</DialogTitle>
        <DialogDescription>
          Per ogni regola del programma, conferma il deposito assegnato. Periodo:{" "}
          <strong>{validoDa}</strong> → <strong>{validoA}</strong>. Una volta lanciato, il
          builder gira in sequenza per ogni sede distinta.
        </DialogDescription>
      </DialogHeader>

      {programmaQueryLoading ? (
        <div className="flex items-center justify-center py-12">
          <Spinner label="Caricamento regole…" />
        </div>
      ) : regole.length === 0 ? (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          Nessuna regola configurata. Aggiungi almeno una regola prima di lanciare il builder.
        </div>
      ) : (
        <div className="flex max-h-[55vh] flex-col gap-3 overflow-y-auto">
          <div className="overflow-hidden rounded-md border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-left">Regola</th>
                  <th className="px-3 py-2 text-left">Materiale</th>
                  <th className="px-3 py-2 text-left">Deposito</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {regole.map((r) => {
                  const stato = perRegola[r.id];
                  const sede = stato?.localita ?? "";
                  const sedeModificata = stato?.localita_modificata === true;
                  const materiale = stato?.materiale ?? "";
                  const materialeModificato = stato?.materiale_modificato === true;
                  return (
                    <tr key={r.id} className="bg-white">
                      <td className="px-3 py-2 align-top">
                        <div className="text-xs font-mono text-muted-foreground">
                          #{r.id}
                        </div>
                        <FiltriCompatti filtri={r.filtri_json} />
                      </td>
                      <td className="px-3 py-2 align-top">
                        <Select
                          value={materiale}
                          onChange={(e) => cambiaMateriale(r.id, e.target.value)}
                          aria-label={`Materiale ipotesi regola ${r.id}`}
                          className={cn(
                            materialeModificato &&
                              materiale.length > 0 &&
                              "border-amber-400 bg-amber-50",
                          )}
                        >
                          <option value="">— scegli materiale —</option>
                          {materialiMacro.map((m) => (
                            <option key={m.codice} value={m.codice}>
                              {m.codice}
                              {m.nome_commerciale != null && m.nome_commerciale !== ""
                                ? ` — ${m.nome_commerciale}`
                                : ""}
                            </option>
                          ))}
                        </Select>
                        {materialeModificato && materiale.length > 0 && (
                          <p className="mt-1 text-[11px] text-amber-700">
                            ipotesi modificata · auto-save sulla regola
                          </p>
                        )}
                        {r.composizione_json.length > 1 && (
                          <p className="mt-1 text-[11px] text-muted-foreground">
                            composizione multi-pezzo:{" "}
                            <ComposizioneCompatta composizione={r.composizione_json} />
                          </p>
                        )}
                      </td>
                      <td className="px-3 py-2 align-top">
                        <Select
                          value={sede}
                          onChange={(e) => cambiaLocalita(r.id, e.target.value)}
                          aria-label={`Deposito regola ${r.id}`}
                          className={cn(
                            sedeModificata && sede.length > 0 && "border-amber-400 bg-amber-50",
                          )}
                        >
                          <option value="">— scegli sede —</option>
                          {(localita ?? []).map((l) => (
                            <option key={l.codice} value={l.codice}>
                              {l.codice_breve ?? l.codice} — {l.nome_canonico}
                            </option>
                          ))}
                        </Select>
                        {sedeModificata && sede.length > 0 && (
                          <p className="mt-1 text-[11px] text-amber-700">
                            sede modificata · auto-save sulla regola
                          </p>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <p className="text-xs text-muted-foreground">
            Il builder verrà lanciato {sediUniche.length}{" "}
            {sediUniche.length === 1 ? "volta" : "volte"} (una per sede unica).
            {sediUniche.length > 0 && (
              <> Sedi: <span className="font-mono">{sediUniche.join(", ")}</span>.</>
            )}
          </p>

          <label className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm">
            <input
              type="checkbox"
              checked={confirmDeletePdc}
              onChange={(e) => setConfirmDeletePdc(e.target.checked)}
              className="mt-0.5"
            />
            <span>
              <strong>Conferma cancellazione PdC dipendenti</strong>: la rigenerazione
              cancella eventuali turni PdC costruiti sui giri precedenti delle sedi
              processate. Senza questa conferma il builder restituisce un errore se trova
              PdC dipendenti.
            </span>
          </label>
        </div>
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
        <Button variant="ghost" type="button" onClick={onAnnulla}>
          Annulla
        </Button>
        <Button
          type="button"
          onClick={onAvvia}
          disabled={
            !tutteSediCompilate || !tuttiMaterialiCompilati || regole.length === 0
          }
          title={
            !tuttiMaterialiCompilati
              ? "Compila il materiale per tutte le regole"
              : !tutteSediCompilate
                ? "Compila il deposito per tutte le regole"
                : `Lancia builder per ${sediUniche.length} ${
                    sediUniche.length === 1 ? "sede" : "sedi"
                  }`
          }
        >
          <ChevronRight className="mr-1 h-4 w-4" aria-hidden /> Avvia generazione
        </Button>
      </DialogFooter>
    </>
  );
}

// =====================================================================
// Step 2 — Running
// =====================================================================

function RunningStep({
  sedeCorrente,
  sediTotali,
}: {
  sedeCorrente: string | null;
  sediTotali: number;
}) {
  return (
    <>
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          <Loader2 className="h-5 w-5 animate-spin text-primary" aria-hidden />
          Generazione giri in corso…
        </DialogTitle>
        <DialogDescription>
          Builder lanciato per ogni sede unica delle regole. Non chiudere la finestra fino al
          completamento.
        </DialogDescription>
      </DialogHeader>
      <div className="flex flex-col gap-3 py-6">
        <div className="text-sm">
          {sedeCorrente !== null ? (
            <>
              In esecuzione su sede <span className="font-mono font-semibold">{sedeCorrente}</span>
              …
            </>
          ) : (
            "Preparazione…"
          )}
        </div>
        <div className="text-xs text-muted-foreground">
          {sediTotali} {sediTotali === 1 ? "sede" : "sedi"} in coda.
        </div>
      </div>
    </>
  );
}

// =====================================================================
// Step 3 — Done
// =====================================================================

function DoneStep({
  aggregato,
  onClose,
}: {
  aggregato: AggregatedResult;
  onClose: () => void;
}) {
  const ok =
    aggregato.errori_per_sede.length === 0 &&
    aggregato.n_corse_residue_totale === 0 &&
    aggregato.warnings.length === 0;

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
          {aggregato.n_sedi_processate} {aggregato.n_sedi_processate === 1 ? "sede" : "sedi"}{" "}
          processate · {aggregato.n_giri_creati_totale} giri creati
          {aggregato.errori_per_sede.length > 0 && (
            <> · {aggregato.errori_per_sede.length} errori</>
          )}
          .
        </DialogDescription>
      </DialogHeader>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 rounded-md border border-border bg-secondary/40 p-4 text-sm">
        <Stat label="Giri creati" value={String(aggregato.n_giri_creati_totale)} />
        <Stat label="Corse processate" value={String(aggregato.n_corse_processate_totale)} />
        <Stat
          label="Corse residue"
          value={String(aggregato.n_corse_residue_totale)}
          warn={aggregato.n_corse_residue_totale > 0}
        />
        <Stat label="Giri chiusi naturalmente" value={String(aggregato.n_giri_chiusi_totale)} />
        <Stat
          label="Giri con motivo non standard"
          value={String(aggregato.n_giri_non_chiusi_totale)}
          warn={aggregato.n_giri_non_chiusi_totale > 0}
        />
      </dl>

      {aggregato.errori_per_sede.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <p className="text-xs font-semibold uppercase tracking-wider text-destructive">
            Errori ({aggregato.errori_per_sede.length})
          </p>
          <ul className="max-h-32 list-disc overflow-y-auto rounded-md border border-destructive/30 bg-destructive/5 px-6 py-2 text-xs text-destructive">
            {aggregato.errori_per_sede.map((e, i) => (
              <li key={i}>
                <span className="font-mono">{e.sede}</span>: {e.messaggio}
              </li>
            ))}
          </ul>
        </div>
      )}

      {aggregato.warnings.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Warning ({aggregato.warnings.length})
          </p>
          <ul className="max-h-32 list-disc overflow-y-auto rounded-md bg-amber-50 px-6 py-2 text-xs text-amber-900">
            {aggregato.warnings.slice(0, 30).map((w, i) => (
              <li key={i}>{w}</li>
            ))}
            {aggregato.warnings.length > 30 && (
              <li className="italic">…e altri {aggregato.warnings.length - 30}</li>
            )}
          </ul>
        </div>
      )}

      <DialogFooter>
        <Button onClick={onClose}>Chiudi</Button>
      </DialogFooter>
    </>
  );
}

// =====================================================================
// Helpers
// =====================================================================

function FiltriCompatti({ filtri }: { filtri: { campo: string; op: string; valore: unknown }[] }) {
  if (filtri.length === 0) {
    return <span className="text-xs italic text-muted-foreground">nessun filtro</span>;
  }
  const linea = filtri.find((f) => f.campo === "direttrice");
  const tipoTreno = filtri.find(
    (f) =>
      f.campo === "categoria" ||
      f.campo === "is_treno_garantito_feriale" ||
      f.campo === "is_treno_garantito_festivo",
  );
  const fmt = (f: { campo: string; op: string; valore: unknown }) => {
    if (Array.isArray(f.valore)) return f.valore.join(", ");
    return String(f.valore);
  };
  return (
    <div className="flex flex-col gap-0.5 text-xs">
      {linea !== undefined && (
        <div>
          <span className="text-muted-foreground">linea: </span>
          <span className="font-medium">{fmt(linea)}</span>
        </div>
      )}
      {tipoTreno !== undefined && (
        <div>
          <span className="text-muted-foreground">tipo: </span>
          <span className="font-medium">{fmt(tipoTreno)}</span>
        </div>
      )}
      {linea === undefined && tipoTreno === undefined && (
        <div className="text-muted-foreground">{filtri.length} filtri</div>
      )}
    </div>
  );
}

function ComposizioneCompatta({
  composizione,
}: {
  composizione: { materiale_tipo_codice: string; n_pezzi: number }[];
}) {
  if (composizione.length === 0) {
    return <span className="text-xs italic text-muted-foreground">—</span>;
  }
  return (
    <div className="flex flex-wrap gap-1">
      {composizione.map((c, i) => (
        <span
          key={i}
          className="inline-flex items-center gap-0.5 rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[11px]"
        >
          {c.materiale_tipo_codice}
          {c.n_pezzi > 1 && <span className="opacity-60">×{c.n_pezzi}</span>}
        </span>
      ))}
    </div>
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
