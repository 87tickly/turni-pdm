import { useMemo, useState } from "react";
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
import { useDepots } from "@/hooks/useAnagrafiche";
import { useGeneraTurnoPdc, useSuggerisciDepositi } from "@/hooks/useTurniPdc";
import { ApiError } from "@/lib/api/client";
import type {
  DepositoSuggerimentoResponse,
  TurnoPdcGenerazioneResponse,
} from "@/lib/api/turniPdc";

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
  // Sprint 7.5 MR 5: la mutation ritorna `TurnoPdcGenerazioneResponse[]`
  // (1 elemento per variante calendario del giro). Con A1 strict default
  // = 1 elemento, con varianti multiple cresce.
  const [results, setResults] = useState<TurnoPdcGenerazioneResponse[] | null>(null);
  // Sprint 7.9 MR η — deposito PdC target per minimizzare FR.
  const [depositoPdcId, setDepositoPdcId] = useState<number | "">("");

  const generaMutation = useGeneraTurnoPdc();
  const depotsQuery = useDepots();
  // Sprint 7.9 MR η.1 — suggerimenti automatici top-3 quando il dialog
  // è aperto. Cache 5 min: non rifa la simulazione se l'utente riapre
  // il dialog sullo stesso giro.
  const suggerimentiQuery = useSuggerisciDepositi(giroId, open, 3);

  const depotOptions = useMemo(
    () =>
      (depotsQuery.data ?? [])
        .slice()
        .sort((a, b) => a.display_name.localeCompare(b.display_name, "it")),
    [depotsQuery.data],
  );

  const handleClose = (next: boolean) => {
    if (!next) {
      setError(null);
      setNeedsForce(false);
      setResults(null);
      setDepositoPdcId("");
    }
    onOpenChange(next);
  };

  const submit = async (forceFlag: boolean) => {
    setError(null);
    try {
      const r = await generaMutation.mutateAsync({
        giroId,
        params: {
          force: forceFlag,
          deposito_pdc_id:
            depositoPdcId === "" ? undefined : Number(depositoPdcId),
        },
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
  const depotChosen = depositoPdcId !== "";

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Genera turno PdC</DialogTitle>
          <DialogDescription>
            Costruisce un turno PdC dai blocchi di questo giro materiale: una
            giornata PdC per ogni giornata del giro, con presa servizio,
            accessori, refezione (se &gt;6h), e dormite FR per i pernotti
            fuori sede.
          </DialogDescription>
        </DialogHeader>

        {showForm && (
          <div className="flex flex-col gap-3 text-sm">
            {/* Sprint 7.9 MR η.1 — suggerimenti automatici top-3 */}
            <SuggerimentiBlock
              query={suggerimentiQuery}
              selectedId={depositoPdcId === "" ? null : Number(depositoPdcId)}
              onSelect={(id) => setDepositoPdcId(id)}
            />
            {/* Sprint 7.9 MR η — selettore deposito PdC target */}
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="genera-pdc-depot"
                className="flex items-center gap-1.5 text-xs font-semibold text-foreground"
              >
                <Building2 className="h-3.5 w-3.5 text-primary" aria-hidden />
                Deposito PdC che coprirà il turno
              </label>
              <select
                id="genera-pdc-depot"
                value={depositoPdcId}
                onChange={(e) => {
                  const v = e.target.value;
                  setDepositoPdcId(v === "" ? "" : Number(v));
                }}
                disabled={running || depotsQuery.isLoading}
                className="h-9 rounded-md border border-border bg-background px-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-60"
              >
                <option value="">— Nessun deposito (legacy: usa sede materiale) —</option>
                {depotOptions.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.display_name} ({d.codice})
                  </option>
                ))}
              </select>
              <p className="text-[11px] text-muted-foreground">
                Quando scegli un deposito, il builder usa la sua stazione
                principale come residenza del PdC e applica i cap FR
                normativi (max 1 dormita/settimana, 3 ogni 28 giorni).
                L&apos;obiettivo è minimizzare i pernotti fuori sede.
              </p>
            </div>
            <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              <strong>MVP Sprint 7.2.</strong> Il builder costruisce un turno
              monolitico per giornata. Il CV intermedio (split per
              prestazione/condotta) arriva nello Sprint 7.4: aspettati
              violazioni di prestazione/condotta che evidenziano i punti
              dove servirà uno scambio PdC.
            </p>
            {needsForce && error !== null && (
              <div className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                <div className="flex flex-col gap-1">
                  <span>{error}</span>
                  <span>
                    Cliccando &quot;Sovrascrivi&quot; il vecchio turno PdC
                    {depotChosen
                      ? " del deposito selezionato"
                      : " associato al giro"}{" "}
                    viene eliminato e ricreato.
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
  // Sprint 7.5 MR 5: render lista di turni generati. Per A1 strict
  // (default) la lista ha 1 elemento; con varianti calendario multiple
  // cresce — ogni turno ha codice `T-{numero_turno}-V{NN}`.
  // Sprint 7.4 MR 3: la lista può contenere anche turni "ramo split"
  // (giornate di giro lunghe spezzate in più turni PdC con CV
  // intermedio).
  if (results.length === 0) return null;
  const nRamiSplit = results.filter((r) => r.is_ramo_split).length;
  return (
    <div className="flex flex-col gap-3 text-sm">
      {results.length > 1 && (
        <p className="rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-900">
          Generati {results.length} turni PdC
          {nRamiSplit > 0 && (
            <>
              , di cui {nRamiSplit} ram{nRamiSplit === 1 ? "o" : "i"} da
              split CV intermedio (giornate eccedenti i limiti
              prestazione/condotta divise in più turni)
            </>
          )}
          .
        </p>
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

// =====================================================================
// Sprint 7.9 MR η.1 — blocco "Suggerimenti automatici"
// =====================================================================

interface SuggerimentiBlockProps {
  query: ReturnType<typeof useSuggerisciDepositi>;
  selectedId: number | null;
  onSelect: (id: number) => void;
}

function SuggerimentiBlock({
  query,
  selectedId,
  onSelect,
}: SuggerimentiBlockProps) {
  if (query.isLoading) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-900">
        <Spinner label="" />
        <span>
          Calcolo dei depositi migliori in corso (simulazione builder per
          ciascun deposito)…
        </span>
      </div>
    );
  }
  if (query.isError) {
    // Non blocca il flusso: l'utente può sempre scegliere manualmente.
    return (
      <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
        Auto-suggerimento non disponibile. Scegli manualmente il deposito
        dal selettore qui sotto.
      </div>
    );
  }
  const top = query.data ?? [];
  if (top.length === 0) return null;
  return (
    <div className="flex flex-col gap-2 rounded-md border border-blue-200 bg-blue-50/50 px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-xs font-semibold text-blue-900">
        <Sparkles className="h-3.5 w-3.5" aria-hidden />
        Suggerimenti automatici (top {top.length} per minor numero di FR)
      </div>
      <div className="flex flex-col gap-1.5">
        {top.map((s, idx) => (
          <SuggerimentoCard
            key={s.deposito_pdc_id}
            sug={s}
            rank={idx}
            isSelected={selectedId === s.deposito_pdc_id}
            onClick={() => onSelect(s.deposito_pdc_id)}
          />
        ))}
      </div>
      <p className="text-[11px] leading-snug text-blue-900/80">
        Cliccando uno dei suggerimenti il selettore qui sotto viene
        impostato automaticamente. Premi poi “Genera” per creare il turno.
      </p>
    </div>
  );
}

interface SuggerimentoCardProps {
  sug: DepositoSuggerimentoResponse;
  rank: number;
  isSelected: boolean;
  onClick: () => void;
}

function SuggerimentoCard({
  sug,
  rank,
  isSelected,
  onClick,
}: SuggerimentoCardProps) {
  const hasCapViolato = sug.n_fr_cap_violazioni > 0;
  const isFallback = sug.stazione_sede_fallback;
  const isBest = rank === 0 && !hasCapViolato && !isFallback;
  const tone = hasCapViolato
    ? "border-red-300 bg-red-50/70 hover:bg-red-50"
    : isFallback
      ? "border-amber-300 bg-amber-50/70 hover:bg-amber-50"
      : isBest
        ? "border-emerald-400 bg-emerald-50/70 hover:bg-emerald-50"
        : "border-blue-200 bg-white hover:bg-blue-50/40";
  const selectedRing = isSelected ? "ring-2 ring-primary ring-offset-1" : "";
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full items-start gap-2.5 rounded-md border px-2.5 py-2 text-left text-xs transition-colors ${tone} ${selectedRing}`}
    >
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white font-mono text-[11px] font-semibold text-foreground shadow-sm">
        #{rank + 1}
      </div>
      <div className="flex flex-1 flex-col gap-0.5">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="font-semibold text-foreground">
            {sug.deposito_pdc_display}
          </span>
          <span className="font-mono text-[10px] text-muted-foreground">
            {sug.deposito_pdc_codice}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-foreground/80">
          <span className="inline-flex items-center gap-1">
            <BedDouble className="h-3 w-3" aria-hidden />
            {sug.n_dormite_fr} FR
          </span>
          <span>{sug.n_giornate} gg</span>
          <span>{formatHM(sug.prestazione_totale_min)} prest.</span>
        </div>
        <div className="text-[11px] italic text-foreground/70">{sug.motivo}</div>
      </div>
      {isSelected && (
        <CheckCircle2
          className="mt-0.5 h-4 w-4 shrink-0 text-primary"
          aria-hidden
        />
      )}
    </button>
  );
}
