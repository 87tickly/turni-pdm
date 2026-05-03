import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AlertCircle, Archive, ArrowLeft, ArrowRight, ListOrdered, Play, Plus, Send } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ProgrammaStatoBadge } from "@/components/domain/ProgrammaStatoBadge";
import { useGiriProgramma } from "@/hooks/useGiri";
import { useArchiviaProgramma, useProgramma, usePubblicaProgramma } from "@/hooks/useProgrammi";
import { ApiError } from "@/lib/api/client";
import type { GiroListItem } from "@/lib/api/giri";
import type {
  ProgrammaDettaglioRead,
  StrictOptions,
} from "@/lib/api/programmi";
import { formatDateIt, formatPeriodo } from "@/lib/format";
import { GeneraGiriDialog } from "@/routes/pianificatore-giro/GeneraGiriDialog";
import { RegolaCard } from "@/routes/pianificatore-giro/regola/RegolaCard";
import { RegolaEditor } from "@/routes/pianificatore-giro/regola/RegolaEditor";

const STRICT_OPTION_KEYS: ReadonlyArray<keyof StrictOptions> = [
  "no_corse_residue",
  "no_overcapacity",
  "no_aggancio_non_validato",
  "no_orphan_blocks",
  "no_giro_appeso",
  "no_km_eccesso",
];

export function ProgrammaDettaglioRoute() {
  const { programmaId: programmaIdParam } = useParams<{ programmaId: string }>();
  const programmaId = programmaIdParam !== undefined ? Number(programmaIdParam) : undefined;
  const navigate = useNavigate();

  const query = useProgramma(programmaId);
  const giriQuery = useGiriProgramma(programmaId);
  const [editorOpen, setEditorOpen] = useState(false);
  const [generaOpen, setGeneraOpen] = useState(false);

  if (programmaId === undefined || Number.isNaN(programmaId)) {
    return <ErrorBlock message="ID programma non valido nell'URL." />;
  }

  if (query.isLoading) {
    return (
      <div className="flex items-center justify-center rounded-lg border border-border bg-white py-16">
        <Spinner label="Caricamento programma…" />
      </div>
    );
  }

  if (query.isError) {
    const msg =
      query.error instanceof ApiError ? query.error.message : (query.error as Error).message;
    return <ErrorBlock message={msg} onRetry={() => void query.refetch()} />;
  }

  if (query.data === undefined || query.data === null) {
    return <ErrorBlock message="Programma non trovato." />;
  }

  const programma = query.data;
  const editable = programma.stato === "bozza";
  const canGenerate = programma.stato === "attivo" && programma.regole.length > 0;
  const giri = giriQuery.data ?? [];
  const giriCount = giri.length;

  return (
    <div className="flex flex-col gap-6">
      {/* Back link */}
      <Link
        to="/pianificatore-giro/programmi"
        className="inline-flex w-fit items-center gap-1 text-xs text-muted-foreground hover:text-primary"
      >
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> Lista programmi
      </Link>

      {/* ═══ 1 · HERO HEADER ════════════════════════════════════ */}
      <HeroHeader
        programma={programma}
        giriCount={giriCount}
        giriLoading={giriQuery.isLoading}
        canGenerate={canGenerate}
        onGenera={() => setGeneraOpen(true)}
        onMutated={() => void query.refetch()}
        onVediGiri={() => navigate(`/pianificatore-giro/programmi/${programma.id}/giri`)}
      />

      {/* ═══ 2 · CONFIGURAZIONE ═════════════════════════════════ */}
      <ConfigurazioneSection programma={programma} editable={editable} />

      {/* ═══ 2.5 · CONVOGLI NECESSARI (Sprint 7.8 MR 5) ═════════ */}
      {giri.length > 0 && (
        <ConvogliNecessariSection programma={programma} giri={giri} />
      )}

      {/* ═══ 3 · REGOLE DI ASSEGNAZIONE ═════════════════════════ */}
      <RegoleSection
        programma={programma}
        editable={editable}
        onAddRegola={() => setEditorOpen(true)}
      />

      {/* ═══ 4 · STORICO RUN ════════════════════════════════════ */}
      {programma.stato === "attivo" && <StoricoRunPlaceholder />}

      {/* Dialogs */}
      <RegolaEditor programmaId={programma.id} open={editorOpen} onOpenChange={setEditorOpen} />
      <GeneraGiriDialog
        programmaId={programma.id}
        validoDa={programma.valido_da}
        validoA={programma.valido_a}
        open={generaOpen}
        onOpenChange={setGeneraOpen}
        onCompleted={() => navigate(`/pianificatore-giro/programmi/${programma.id}/giri`)}
      />
    </div>
  );
}

// =====================================================================
// 1 · Hero header
// =====================================================================

interface HeroHeaderProps {
  programma: ProgrammaDettaglioRead;
  giriCount: number;
  giriLoading: boolean;
  canGenerate: boolean;
  onGenera: () => void;
  onMutated: () => void;
  onVediGiri: () => void;
}

function HeroHeader({
  programma,
  giriCount,
  giriLoading,
  canGenerate,
  onGenera,
  onMutated,
  onVediGiri,
}: HeroHeaderProps) {
  const giorni = diffDaysInclusive(programma.valido_da, programma.valido_a);
  // Backend entry 88: la response include `created_by_username` via JOIN.
  // Fallback a `user#id` se l'utente è stato eliminato (relazione NULL).
  const createdBy =
    programma.created_by_username ??
    (programma.created_by_user_id !== null ? `user#${programma.created_by_user_id}` : "—");

  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex items-center gap-2">
            <ProgrammaStatoBadge stato={programma.stato} />
            <span className="font-mono text-xs text-muted-foreground">#{programma.id}</span>
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            {programma.nome}
          </h1>
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span className="tabular-nums">
              {formatPeriodo(programma.valido_da, programma.valido_a)} · {giorni} giorni
            </span>
            <span className="text-border">·</span>
            <span>
              creato da <span className="text-foreground">{createdBy}</span>
            </span>
            <span className="text-border">·</span>
            <span className="tabular-nums">{formatDateIt(programma.created_at)}</span>
          </div>

          {/* KPI inline */}
          <div className="mt-5 flex flex-wrap items-center gap-x-8 gap-y-3">
            <KpiInline label="Regole" value={String(programma.regole.length)} />
            <DividerInline />
            <KpiInline
              label="Giri persistiti"
              value={giriLoading ? "—" : String(giriCount)}
            />
            <DividerInline />
            <KpiInline
              label="Run eseguiti"
              value="—"
              hint="Registro run non ancora persistito (TN-UPDATE entry 86)"
            />
          </div>
        </div>

        {/* Action cluster — state-dependent */}
        <ActionCluster
          programma={programma}
          canGenerate={canGenerate}
          onGenera={onGenera}
          onMutated={onMutated}
          onVediGiri={onVediGiri}
        />
      </div>
    </Card>
  );
}

function KpiInline({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div title={hint}>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 text-2xl font-semibold leading-none tabular-nums text-foreground">
        {value}
      </div>
    </div>
  );
}

function DividerInline() {
  return <div className="h-10 w-px bg-border" />;
}

function ActionCluster({
  programma,
  canGenerate,
  onGenera,
  onMutated,
  onVediGiri,
}: {
  programma: ProgrammaDettaglioRead;
  canGenerate: boolean;
  onGenera: () => void;
  onMutated: () => void;
  onVediGiri: () => void;
}) {
  const pubblicaMutation = usePubblicaProgramma();
  const archiviaMutation = useArchiviaProgramma();
  const busy = pubblicaMutation.isPending || archiviaMutation.isPending;

  if (programma.stato === "bozza") {
    const canPublish = programma.regole.length > 0;
    return (
      <div className="flex shrink-0 flex-wrap items-center gap-2">
        <Button
          variant="primary"
          disabled={!canPublish || busy}
          onClick={() => {
            if (!window.confirm(`Pubblicare il programma "${programma.nome}"?`)) return;
            pubblicaMutation.mutate(programma.id, {
              onSuccess: onMutated,
              onError: (err) => {
                const msg = err instanceof ApiError ? err.message : err.message;
                window.alert(`Pubblicazione fallita: ${msg}`);
              },
            });
          }}
          title={canPublish ? "Pubblica" : "Aggiungi almeno una regola per pubblicare"}
        >
          <Send className="mr-2 h-4 w-4" aria-hidden /> Pubblica
        </Button>
        <Button
          variant="outline"
          disabled
          title="Modifica configurazione: dialog non ancora disponibile (TN-UPDATE residuo)"
        >
          Modifica
        </Button>
        <Button
          variant="ghost"
          disabled
          title="Eliminazione programma non ancora disponibile (richiede endpoint backend)"
        >
          Elimina
        </Button>
      </div>
    );
  }

  if (programma.stato === "attivo") {
    return (
      <div className="flex shrink-0 flex-wrap items-center gap-2">
        <Button
          variant="primary"
          onClick={onGenera}
          disabled={!canGenerate}
          title={
            canGenerate
              ? "Lancia il builder per costruire i giri"
              : "Aggiungi almeno una regola per generare"
          }
        >
          <Play className="mr-2 h-4 w-4" aria-hidden /> Genera giri
        </Button>
        <Button variant="outline" onClick={onVediGiri}>
          <ListOrdered className="mr-2 h-4 w-4" aria-hidden /> Vedi giri generati
        </Button>
        <Button
          variant="ghost"
          disabled={busy}
          onClick={() => {
            if (!window.confirm(`Archiviare il programma "${programma.nome}"?`)) return;
            archiviaMutation.mutate(programma.id, {
              onSuccess: onMutated,
              onError: (err) => {
                const msg = err instanceof ApiError ? err.message : err.message;
                window.alert(`Archiviazione fallita: ${msg}`);
              },
            });
          }}
        >
          <Archive className="mr-2 h-4 w-4" aria-hidden /> Archivia
        </Button>
      </div>
    );
  }

  // archiviato
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-2">
      <Button variant="outline" onClick={onVediGiri}>
        <ListOrdered className="mr-2 h-4 w-4" aria-hidden /> Vedi giri generati
      </Button>
    </div>
  );
}

// =====================================================================
// 2 · Configurazione
// =====================================================================

function ConfigurazioneSection({
  programma,
  editable,
}: {
  programma: ProgrammaDettaglioRead;
  editable: boolean;
}) {
  const strict = programma.strict_options_json;
  const strictActive = STRICT_OPTION_KEYS.filter((k) => strict[k] === true).length;
  const sosta = programma.stazioni_sosta_extra_json;

  return (
    <Card className="p-6">
      <div className="mb-5 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-foreground">
          Configurazione
        </h2>
        <Button
          variant="outline"
          size="sm"
          disabled
          title={
            editable
              ? "Modifica configurazione: dialog non ancora disponibile (TN-UPDATE residuo)"
              : "Modifica disponibile solo in stato bozza"
          }
        >
          Modifica configurazione
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 md:gap-8">
        {/* Sx — parametri scalari */}
        <div className="space-y-3">
          <ScalarRow
            label="Periodo validità"
            value={formatPeriodo(programma.valido_da, programma.valido_a)}
          />
          <ScalarRow
            label="Fascia oraria tolerance"
            value={`${programma.fascia_oraria_tolerance_min} min`}
          />
          <ScalarRow
            label="Km max / giorno"
            value={
              programma.km_max_giornaliero === null
                ? "—"
                : `${programma.km_max_giornaliero.toLocaleString("it-IT")} km`
            }
          />
          <ScalarRow
            label="Lunghezza giri"
            value={`${programma.n_giornate_min}–${programma.n_giornate_max} giornate`}
          />
          <ScalarRow
            label="Km max / ciclo (legacy)"
            value={
              programma.km_max_ciclo === null
                ? "—"
                : `${programma.km_max_ciclo.toLocaleString("it-IT")} km`
            }
            muted
            last
          />
        </div>

        {/* Dx — strict options + stazioni sosta */}
        <div>
          <div className="mb-3 text-xs uppercase tracking-wide text-muted-foreground">
            Strict options · {strictActive} di {STRICT_OPTION_KEYS.length} attive
          </div>
          <div className="mb-6 flex flex-wrap gap-2">
            {STRICT_OPTION_KEYS.map((k) => (
              <StrictChip key={k} name={k} active={strict[k] === true} />
            ))}
          </div>

          <div className="mb-3 text-xs uppercase tracking-wide text-muted-foreground">
            Stazioni sosta extra · {sosta.length}
          </div>
          {sosta.length === 0 ? (
            <p className="text-xs italic text-muted-foreground">Nessuna stazione extra.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {sosta.map((cod) => (
                <span
                  key={cod}
                  className="inline-flex items-center rounded border border-border bg-muted px-2.5 py-1 font-mono text-xs text-foreground"
                >
                  {cod}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

function ScalarRow({
  label,
  value,
  muted = false,
  last = false,
}: {
  label: string;
  value: string;
  muted?: boolean;
  last?: boolean;
}) {
  return (
    <div
      className={`flex items-baseline justify-between ${last ? "" : "border-b border-border pb-3"}`}
    >
      <span
        className={`text-xs uppercase tracking-wide ${muted ? "italic text-muted-foreground/70" : "text-muted-foreground"}`}
      >
        {label}
      </span>
      <span
        className={`text-sm tabular-nums ${muted ? "text-muted-foreground" : "text-foreground"}`}
      >
        {value}
      </span>
    </div>
  );
}

function StrictChip({ name, active }: { name: string; active: boolean }) {
  return (
    <span
      className={
        active
          ? "inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs text-emerald-800"
          : "inline-flex items-center gap-1.5 rounded-full border border-border bg-muted px-2.5 py-1 text-xs text-muted-foreground"
      }
    >
      <span aria-hidden>{active ? "✓" : "—"}</span> {name}
    </span>
  );
}

// =====================================================================
// 2.5 · Convogli necessari (Sprint 7.8 MR 5)
// =====================================================================

/**
 * Sintesi del materiale rotabile necessario per coprire il programma.
 *
 * Modello operativo Trenord (PDF turno 1134, decisione utente
 * 2026-05-03): un giro a N giornate richiede **N convogli simultanei**
 * — uno per ogni giornata-pattern. Ogni convoglio applica la
 * composizione della regola (es. ETR421+ETR421 = 2 pezzi singoli).
 *
 * Output: per ogni regola, il numero di convogli + i pezzi totali per
 * tipo materiale, sommati su tutti i giri della regola (= per
 * materiale_tipo_codice del giro).
 */
function ConvogliNecessariSection({
  programma,
  giri,
}: {
  programma: ProgrammaDettaglioRead;
  giri: GiroListItem[];
}) {
  // Per ogni regola, lega i giri il cui `materiale_tipo_codice` è in
  // `composizione_json` (= materiale principale). Una regola può
  // generare 1+ giri se è multi-sede o se l'aggregazione A2 produce
  // più chiavi (oggi raro: 1 sede × 1 materiale → 1 giro tipico).
  const sintesi = programma.regole.map((r) => {
    const materiali_regola = new Set(
      r.composizione_json.map((c) => c.materiale_tipo_codice),
    );
    const giri_regola = giri.filter(
      (g) => g.materiale_tipo_codice !== null && materiali_regola.has(g.materiale_tipo_codice),
    );
    const giornate_totali = giri_regola.reduce((acc, g) => acc + g.numero_giornate, 0);
    // Pezzi totali per tipo: per ogni pezzo della composizione, conta
    // quanti convogli simultanei × pezzi del componente.
    const pezzi_per_tipo = r.composizione_json.map((c) => ({
      tipo: c.materiale_tipo_codice,
      pezzi: c.n_pezzi * giornate_totali,
    }));
    return {
      regola_id: r.id,
      composizione: r.composizione_json,
      giri_count: giri_regola.length,
      convogli: giornate_totali,
      pezzi_per_tipo,
    };
  });

  // Totali aggregati su tutte le regole.
  const tot_convogli = sintesi.reduce((acc, s) => acc + s.convogli, 0);
  const tot_pezzi: Record<string, number> = {};
  for (const s of sintesi) {
    for (const p of s.pezzi_per_tipo) {
      tot_pezzi[p.tipo] = (tot_pezzi[p.tipo] ?? 0) + p.pezzi;
    }
  }

  return (
    <Card className="p-6">
      <div className="mb-4 flex items-baseline gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-foreground">
          Convogli necessari
        </h2>
        <span className="text-xs text-muted-foreground">
          {tot_convogli} convogli · {Object.values(tot_pezzi).reduce((a, b) => a + b, 0)} pezzi
          singoli totali
        </span>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {sintesi.map((s) => (
          <div
            key={s.regola_id}
            className="rounded-md border border-border bg-secondary/40 p-4"
          >
            <div className="mb-2 flex items-center gap-2">
              <Badge variant="muted">Regola #{s.regola_id}</Badge>
              <span className="font-mono text-xs text-muted-foreground">
                {s.composizione.map((c) => `${c.materiale_tipo_codice} × ${c.n_pezzi}`).join(" + ")}
              </span>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
              <div>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  Giri (turni)
                </div>
                <div className="mt-0.5 text-2xl font-semibold tabular-nums text-foreground">
                  {s.giri_count}
                </div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  Convogli simultanei
                </div>
                <div className="mt-0.5 text-2xl font-semibold tabular-nums text-foreground">
                  {s.convogli}
                </div>
              </div>
            </div>
            <div className="mt-3 border-t border-border pt-3">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                Pezzi singoli necessari
              </div>
              <div className="mt-1 flex flex-wrap gap-2">
                {s.pezzi_per_tipo.map((p) => (
                  <span
                    key={p.tipo}
                    className="inline-flex items-center gap-1 rounded border border-border bg-background px-2 py-0.5 font-mono text-xs"
                  >
                    <span className="text-foreground">{p.tipo}</span>
                    <span className="text-muted-foreground">×</span>
                    <span className="font-semibold tabular-nums text-foreground">{p.pezzi}</span>
                  </span>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>

      <p className="mt-4 text-xs italic text-muted-foreground">
        Sprint 7.8 MR 5: 1 giro a N giornate richiede N convogli simultanei (modello PDF
        Trenord 1134). I pezzi sono dati indicativi calcolati dal builder; il pianificatore
        può rivedere la composizione per regola se la dotazione fisica è inferiore.
      </p>
    </Card>
  );
}


// =====================================================================
// 3 · Regole di assegnazione
// =====================================================================

function RegoleSection({
  programma,
  editable,
  onAddRegola,
}: {
  programma: ProgrammaDettaglioRead;
  editable: boolean;
  onAddRegola: () => void;
}) {
  const regole = [...programma.regole].sort((a, b) => b.priorita - a.priorita);

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-baseline gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-foreground">
            Regole di assegnazione
          </h2>
          <span className="text-xs text-muted-foreground">
            {regole.length} {regole.length === 1 ? "regola" : "regole"} · ordinate per priorità ↓
          </span>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={onAddRegola}
          disabled={!editable}
          title={editable ? "Aggiungi una nuova regola" : "Aggiunta disponibile solo in stato bozza"}
        >
          <Plus className="mr-1 h-3.5 w-3.5" aria-hidden /> Nuova regola
        </Button>
      </div>

      {regole.length === 0 ? (
        <Card className="flex flex-col items-center justify-center gap-3 p-12 text-center">
          <p className="text-sm text-muted-foreground">
            Nessuna regola configurata. Almeno una regola è richiesta per pubblicare il programma.
          </p>
          {editable && (
            <Button onClick={onAddRegola}>
              <Plus className="mr-2 h-4 w-4" aria-hidden /> Aggiungi la prima regola
            </Button>
          )}
        </Card>
      ) : (
        <div className="flex flex-col gap-3">
          {regole.map((r) => (
            <RegolaCard key={r.id} regola={r} programmaId={programma.id} editable={editable} />
          ))}
        </div>
      )}
    </section>
  );
}

// =====================================================================
// 4 · Storico run (placeholder finché non c'è builder_run table)
// =====================================================================

function StoricoRunPlaceholder() {
  return (
    <section>
      <div className="mb-3 flex items-baseline gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-foreground">
          Storico run del builder
        </h2>
        <span className="text-xs text-muted-foreground">in arrivo</span>
      </div>
      <Card className="flex flex-col items-start gap-2 p-5">
        <Badge variant="muted">Registro non ancora persistito</Badge>
        <p className="text-sm text-muted-foreground">
          Il dettaglio dei run del builder (data, sede, eseguito_by, n_giri, residue, warnings,
          force) comparirà qui non appena sarà disponibile la tabella <code>builder_run</code>{" "}
          (vedi TN-UPDATE entry 86). Per ora puoi consultare i giri generati dalla pagina
          dedicata.
        </p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            const el = document.querySelector('a[href*="/giri"]');
            if (el instanceof HTMLAnchorElement) el.click();
          }}
        >
          Apri lista giri <ArrowRight className="ml-2 h-3.5 w-3.5" aria-hidden />
        </Button>
      </Card>
    </section>
  );
}

// =====================================================================
// Utils
// =====================================================================

function diffDaysInclusive(da: string, a: string): number {
  const d1 = new Date(`${da}T00:00:00Z`);
  const d2 = new Date(`${a}T00:00:00Z`);
  const ms = d2.getTime() - d1.getTime();
  return Math.max(1, Math.round(ms / (1000 * 60 * 60 * 24)) + 1);
}

interface ErrorBlockProps {
  message: string;
  onRetry?: () => void;
}

function ErrorBlock({ message, onRetry }: ErrorBlockProps) {
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-4"
    >
      <AlertCircle className="mt-0.5 h-5 w-5 text-destructive" aria-hidden />
      <div className="flex flex-1 flex-col gap-2">
        <p className="text-sm font-medium text-destructive">{message}</p>
        {onRetry !== undefined && (
          <Button variant="outline" size="sm" onClick={onRetry} className="self-start">
            Riprova
          </Button>
        )}
      </div>
    </div>
  );
}
