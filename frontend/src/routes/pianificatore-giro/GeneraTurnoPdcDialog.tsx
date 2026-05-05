import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  BedDouble,
  Building2,
  CheckCircle2,
  Sparkles,
} from "lucide-react";

import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Spinner } from "@/components/ui/Spinner";
import { useGeneraTurnoPdc } from "@/hooks/useTurniPdc";
import { ApiError } from "@/lib/api/client";
import type { TurnoPdcGenerazioneResponse } from "@/lib/api/turniPdc";

interface GeneraTurnoPdcDialogProps {
  giroId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Dialog per `POST /api/giri/{id}/genera-turno-pdc`.
 *
 * Flusso:
 * 1. open: card iniziale con CTA "Genera"
 * 2. running: spinner
 * 3. done: card risultato con stats e CTA "Apri turno PdC"
 *
 * Se il backend ritorna 409 (turno PdC esistente), mostra opzione
 * "Sovrascrivi" e ri-tenta con `force=true`.
 */
export function GeneraTurnoPdcDialog({
  giroId,
  open,
  onOpenChange,
}: GeneraTurnoPdcDialogProps) {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [needsForce, setNeedsForce] = useState(false);
  // Sprint 7.5 MR 5: la mutation ritorna `TurnoPdcGenerazioneResponse[]`.
  // Con il builder multi-turno (Sprint 7.10 α.2) la lista contiene N
  // elementi: un turno PdC autonomo per ogni segmento DP del giro.
  const [results, setResults] = useState<TurnoPdcGenerazioneResponse[] | null>(null);

  const generaMutation = useGeneraTurnoPdc();

  const handleClose = (next: boolean) => {
    if (!next) {
      setError(null);
      setNeedsForce(false);
      setResults(null);
    }
    onOpenChange(next);
  };

  const submit = async (forceFlag: boolean) => {
    setError(null);
    try {
      // Sprint 7.10 MR α.2: niente più deposito_pdc_id a livello giro.
      // Il backend multi-turno sceglie il deposito ottimale per ogni
      // segmento DP via heuristic post-DP. Il param è ancora accettato
      // dall'API per backward compat ma viene ignorato.
      const r = await generaMutation.mutateAsync({
        giroId,
        params: { force: forceFlag },
      });
      setResults(r);
      setNeedsForce(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setNeedsForce(true);
        setError(e.message);
      } else {
        const msg = e instanceof Error ? e.message : "Errore sconosciuto";
        setError(msg);
      }
    }
  };

  const running = generaMutation.isPending;
  const showForm = results === null;
  const showResult = results !== null;

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Genera turno PdC</DialogTitle>
          <DialogDescription>
            Genera <strong>N turni PdC</strong> autonomi che coprono questo
            giro materiale. L&apos;algoritmo segmenta ogni giornata-giro in
            sotto-segmenti entro cap normativi (prestazione 8h30, condotta
            5h30) e assegna ad ogni segmento il deposito più vicino alla
            sua tratta.
          </DialogDescription>
        </DialogHeader>

        {showForm && (
          <div className="flex flex-col gap-3 text-sm">
            {/* Sprint 7.10 MR α.2 — il builder è ora multi-turno con DP.
                L'algoritmo segmenta ogni giornata-giro in N sotto-turni e
                sceglie autonomamente il deposito ottimale per ognuno.
                Niente più scelta manuale del singolo deposito a livello
                giro. */}
            <div className="flex items-start gap-2 rounded-md border border-emerald-200 bg-emerald-50/70 px-3 py-2.5 text-xs text-emerald-900">
              <Sparkles
                className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600"
                aria-hidden
              />
              <div className="flex flex-col gap-0.5">
                <span className="font-semibold">
                  Builder multi-turno (Sprint 7.10 α.2)
                </span>
                <span className="leading-snug">
                  L&apos;algoritmo DP segmenta il giro in N turni PdC
                  autonomi entro cap normativi (prestazione 8h30, condotta
                  5h30) e assegna a ciascuno il deposito più vicino alla
                  sua tratta. Niente scelta manuale per giro: il deposito
                  è per-segmento.
                </span>
              </div>
            </div>
            {needsForce && error !== null && (
              <div className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                <div className="flex flex-col gap-1">
                  <span>{error}</span>
                  <span>
                    Cliccando &quot;Sovrascrivi&quot; tutti i turni PdC
                    associati a questo giro vengono eliminati e ricreati.
                  </span>
                </div>
              </div>
            )}
            {error !== null && !needsForce && (
              <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
                {error}
              </div>
            )}
          </div>
        )}

        {running && (
          <div className="flex items-center justify-center py-6">
            <Spinner label="Generazione in corso…" />
          </div>
        )}

        {showResult && results !== null && <ResultsCard results={results} />}

        <DialogFooter>
          {showForm && !needsForce && (
            <>
              <Button variant="outline" onClick={() => handleClose(false)} disabled={running}>
                Annulla
              </Button>
              <Button onClick={() => void submit(false)} disabled={running}>
                Genera
              </Button>
            </>
          )}
          {showForm && needsForce && (
            <>
              <Button variant="outline" onClick={() => handleClose(false)} disabled={running}>
                Annulla
              </Button>
              <Button
                variant="destructive"
                onClick={() => void submit(true)}
                disabled={running}
              >
                Sovrascrivi
              </Button>
            </>
          )}
          {showResult && results !== null && results.length > 0 && (
            <>
              <Button variant="outline" onClick={() => handleClose(false)}>
                Chiudi
              </Button>
              <Button
                onClick={() => {
                  handleClose(false);
                  navigate(
                    `/pianificatore-giro/turni-pdc/${results[0].turno_pdc_id}`,
                  );
                }}
              >
                {results.length === 1
                  ? "Apri turno PdC"
                  : `Apri primo turno (${results.length} totali)`}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ResultsCard({ results }: { results: TurnoPdcGenerazioneResponse[] }) {
  // Sprint 7.10 MR α.2: ogni elemento è un turno PdC autonomo prodotto
  // dal DP multi-turno. Per giri lunghi/complessi la lista può
  // contenere 10-20+ turni distinti, ognuno con il suo deposito.
  if (results.length === 0) return null;
  const depositiDistinti = new Set(
    results
      .map((r) => r.deposito_pdc_codice)
      .filter((c): c is string => c !== null),
  );
  const nLegacy = results.filter((r) => r.deposito_pdc_codice === null).length;
  const nFrTotali = results.reduce((s, r) => s + r.n_dormite_fr, 0);
  const nViolazioniHard = results.reduce(
    (s, r) => s + r.violazioni.length + r.fr_cap_violazioni.length,
    0,
  );
  return (
    <div className="flex flex-col gap-3 text-sm">
      {results.length > 1 && (
        <div className="flex flex-col gap-1 rounded-md border border-blue-200 bg-blue-50 px-3 py-2.5 text-xs text-blue-900">
          <span className="font-semibold">
            Generati {results.length} turni PdC autonomi
          </span>
          <span>
            Coperti da {depositiDistinti.size} deposit
            {depositiDistinti.size === 1 ? "o" : "i"} distint
            {depositiDistinti.size === 1 ? "o" : "i"}
            {nLegacy > 0 && (
              <>
                {" "}
                · {nLegacy} segment{nLegacy === 1 ? "o" : "i"} senza
                deposito (tratta non coperta da CV)
              </>
            )}
            {nFrTotali > 0 && (
              <>
                {" "}
                · {nFrTotali} dormit{nFrTotali === 1 ? "a" : "e"} FR
                totali
              </>
            )}
            {nViolazioniHard > 0 && (
              <>
                {" "}
                · <span className="text-red-700 font-medium">
                  {nViolazioniHard} violazion{nViolazioniHard === 1 ? "e" : "i"}
                  {" "}normativa
                </span>
              </>
            )}
            .
          </span>
        </div>
      )}
      {results.map((r) => (
        <ResultCard key={r.turno_pdc_id} result={r} />
      ))}
    </div>
  );
}

function ResultCard({ result }: { result: TurnoPdcGenerazioneResponse }) {
  const violazioni = result.violazioni;
  const ramoLabel =
    result.is_ramo_split &&
    result.split_ramo !== null &&
    result.split_totale_rami !== null &&
    result.split_origine_giornata !== null
      ? `Ramo ${result.split_ramo} di ${result.split_totale_rami} (giornata ${result.split_origine_giornata} split CV)`
      : null;
  const frCap = result.fr_cap_violazioni;
  return (
    <div className="flex flex-col gap-3 text-sm">
      <div className="flex items-start gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-emerald-900">
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        <div className="flex flex-col gap-0.5">
          <span className="font-medium">{result.codice} creato</span>
          {ramoLabel !== null && (
            <span className="text-xs text-emerald-700">{ramoLabel}</span>
          )}
          {result.deposito_pdc_codice !== null && (
            <span className="inline-flex items-center gap-1 text-xs text-emerald-800">
              <Building2 className="h-3 w-3" aria-hidden />
              Deposito{" "}
              <span className="font-mono font-semibold">
                {result.deposito_pdc_codice}
              </span>
            </span>
          )}
          <span className="text-xs text-emerald-800">
            {result.n_giornate} giornate · {formatHM(result.prestazione_totale_min)} prestazione
            totale · {formatHM(result.condotta_totale_min)} condotta totale
          </span>
          {result.n_dormite_fr > 0 && (
            <span className="inline-flex items-center gap-1 text-xs text-emerald-800">
              <BedDouble className="h-3 w-3" aria-hidden />
              {result.n_dormite_fr} dormit
              {result.n_dormite_fr === 1 ? "a" : "e"} FR nel ciclo
            </span>
          )}
        </div>
      </div>
      {frCap.length > 0 && (
        <div className="flex items-start gap-2 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <div className="flex flex-col gap-1">
            <span className="font-semibold">
              Cap FR violato: {frCap.length} regola
              {frCap.length === 1 ? "" : "/e"}
            </span>
            <ul className="space-y-0.5 font-mono">
              {frCap.map((v, i) => (
                <li key={i}>· {v}</li>
              ))}
            </ul>
            <span className="text-[11px] text-red-800">
              Considera un deposito più vicino alle stazioni di chiusura
              giornata, oppure un giro materiale con meno pernotti fuori
              sede.
            </span>
          </div>
        </div>
      )}
      {violazioni.length > 0 && (
        <details className="rounded-md border border-amber-300 bg-amber-50 text-xs text-amber-900">
          <summary className="cursor-pointer px-3 py-2 font-medium">
            {violazioni.length} violazion{violazioni.length === 1 ? "e" : "i"} normativa rilevate
          </summary>
          <ul className="space-y-1 px-4 pb-2 font-mono">
            {violazioni.map((v, i) => (
              <li key={i}>· {v}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function formatHM(min: number): string {
  const h = Math.floor(min / 60);
  const m = min % 60;
  return `${h}h${m.toString().padStart(2, "0")}`;
}

// NB: il blocco "Suggerimenti automatici" del MR η.1 è stato rimosso
// con MR α.2 perché il builder multi-turno sceglie autonomamente il
// deposito ottimale per ogni segmento DP. L'hook useSuggerisciDepositi
// resta disponibile in `useTurniPdc.ts` per usi futuri.
