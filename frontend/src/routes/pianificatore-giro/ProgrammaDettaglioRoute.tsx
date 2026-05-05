import { useContext, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  AlertCircle,
  Archive,
  ArrowLeft,
  CheckCircle2,
  ListOrdered,
  Lock,
  Play,
  Plus,
  Send,
  Unlock,
} from "lucide-react";

import { cn } from "@/lib/utils";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ProgrammaStatoBadge } from "@/components/domain/ProgrammaStatoBadge";
import { useMateriali } from "@/hooks/useAnagrafiche";
import { useGiriProgramma } from "@/hooks/useGiri";
import {
  useArchiviaProgramma,
  useConfermaMateriale,
  useLastBuilderRun,
  useProgramma,
  usePubblicaProgramma,
  useSbloccaProgramma,
} from "@/hooks/useProgrammi";
import { ApiError } from "@/lib/api/client";
import type { GiroListItem } from "@/lib/api/giri";
import {
  materialeFreezato,
  type ProgrammaDettaglioRead,
  type StatoPipelinePdc,
  type StrictOptions,
} from "@/lib/api/programmi";
import { AuthContext } from "@/lib/auth/AuthContext";
import { formatDateIt, formatPeriodo } from "@/lib/format";
import { GeneraGiriDialog } from "@/routes/pianificatore-giro/GeneraGiriDialog";
import { RegoleInvioSostaSection } from "@/routes/pianificatore-giro/RegoleInvioSostaSection";
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

// Sprint 8.0 MR 1 (entry 165): label + tone per il banner pipeline.
const PIPELINE_PDC_LABEL: Record<StatoPipelinePdc, string> = {
  PDE_IN_LAVORAZIONE: "PdE in lavorazione",
  PDE_CONSOLIDATO: "PdE consolidato",
  MATERIALE_GENERATO: "Materiale generato",
  MATERIALE_CONFERMATO: "Materiale confermato",
  PDC_GENERATO: "PdC generato",
  PDC_CONFERMATO: "PdC confermato",
  PERSONALE_ASSEGNATO: "Personale assegnato",
  VISTA_PUBBLICATA: "Vista pubblicata",
};

const STATI_PRE_CONFERMA_MATERIALE: ReadonlySet<StatoPipelinePdc> = new Set([
  "PDE_CONSOLIDATO",
  "MATERIALE_GENERATO",
]);

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
  // Sprint 7.9 MR 13 (entry 119): regole modificabili anche in stato
  // 'attivo'. Solo 'archiviato' è read-only.
  // Sprint 8.0 MR 1 (entry 165): freeze read-only anche post
  // MATERIALE_CONFERMATO — il backend restituirebbe 409 sui write.
  const freezato = materialeFreezato(programma.stato_pipeline_pdc);
  const editable = programma.stato !== "archiviato" && !freezato;
  const canGenerate =
    programma.stato === "attivo" && programma.regole.length > 0 && !freezato;
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

      {/* ═══ 1.5 · PIPELINE BANNER (Sprint 8.0 MR 1) ════════════ */}
      <PipelineBanner programma={programma} onMutated={() => void query.refetch()} />

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

      {/* ═══ 3.5 · REGOLE INVIO SOSTA (Sprint 7.9 MR β2-8) ══════ */}
      <RegoleInvioSostaSection programmaId={programma.id} editable={editable} />

      {/* ═══ 4 · ULTIMO RUN DEL BUILDER ════════════════════════ */}
      {programma.stato === "attivo" && <UltimoRunSection programmaId={programma.id} />}

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
    // Sprint 8.0 MR 1 (entry 165): bottone "Conferma materiale" attivo
    // quando il pipeline è in {PDE_CONSOLIDATO, MATERIALE_GENERATO}.
    // Dopo conferma, il programma è freezato (read-only su parametri,
    // regole, giri); il banner pipeline mostra lo stato + sblocco admin.
    const stato = programma.stato_pipeline_pdc;
    const showConferma = STATI_PRE_CONFERMA_MATERIALE.has(stato);
    const freezato = materialeFreezato(stato);
    const generaTitle = !canGenerate
      ? freezato
        ? "Materiale confermato: i giri sono read-only finché un admin non sblocca"
        : "Aggiungi almeno una regola per generare"
      : "Lancia il builder per costruire i giri";
    return (
      <div className="flex shrink-0 flex-wrap items-center gap-2">
        {showConferma ? (
          <ConfermaMaterialeButton
            programma={programma}
            onMutated={onMutated}
          />
        ) : null}
        <Button
          variant="primary"
          onClick={onGenera}
          disabled={!canGenerate}
          title={generaTitle}
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
// 1.5 · Pipeline banner + Conferma materiale (Sprint 8.0 MR 1, entry 165)
// =====================================================================

function ConfermaMaterialeButton({
  programma,
  onMutated,
}: {
  programma: ProgrammaDettaglioRead;
  onMutated: () => void;
}) {
  const mutation = useConfermaMateriale();
  return (
    <Button
      variant="primary"
      disabled={mutation.isPending}
      onClick={() => {
        if (
          !window.confirm(
            `Confermare il materiale del programma "${programma.nome}"?\n` +
              "Dopo la conferma, regole, parametri e giri saranno read-only " +
              "finché un admin non sblocca il programma.",
          )
        ) {
          return;
        }
        mutation.mutate(programma.id, {
          onSuccess: onMutated,
          onError: (err) => {
            const msg = err instanceof ApiError ? err.message : err.message;
            window.alert(`Conferma fallita: ${msg}`);
          },
        });
      }}
      title="Conferma il materiale e fai partire l'handoff verso il Pianificatore PdC"
    >
      <CheckCircle2 className="mr-2 h-4 w-4" aria-hidden /> Conferma materiale
    </Button>
  );
}

function PipelineBanner({
  programma,
  onMutated,
}: {
  programma: ProgrammaDettaglioRead;
  onMutated: () => void;
}) {
  // Uso ``useContext`` direttamente (anziché ``useAuth``) così se il
  // banner viene renderizzato in un test senza ``AuthProvider`` il
  // fallback è ``isAdmin=false`` (no bottone sblocca, ok per snapshot).
  const auth = useContext(AuthContext);
  const isAdmin = auth?.user?.is_admin === true;
  const stato = programma.stato_pipeline_pdc;
  const freezato = materialeFreezato(stato);
  const sbloccaMutation = useSbloccaProgramma();

  return (
    <Card
      className={cn(
        "p-4",
        freezato
          ? "border-amber-300 bg-amber-50"
          : "border-border bg-muted/40",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          {freezato ? (
            <Lock className="h-5 w-5 shrink-0 text-amber-600" aria-hidden />
          ) : (
            <CheckCircle2
              className="h-5 w-5 shrink-0 text-blue-600"
              aria-hidden
            />
          )}
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Pipeline ramo PdC
            </div>
            <div className="text-sm font-semibold tabular-nums text-foreground">
              {PIPELINE_PDC_LABEL[stato]}
            </div>
            {freezato ? (
              <p className="mt-1 text-xs text-amber-800">
                Materiale confermato: regole, parametri e giri sono read-only.
                {isAdmin
                  ? " Puoi sbloccare il programma per consentire modifiche."
                  : " Per modificare contatta un admin per lo sblocco."}
              </p>
            ) : null}
          </div>
        </div>
        {freezato && isAdmin ? (
          <Button
            variant="outline"
            size="sm"
            disabled={sbloccaMutation.isPending}
            onClick={() => {
              const motivo = window.prompt(
                "Motivo dello sblocco (opzionale):",
                "",
              );
              if (
                !window.confirm(
                  `Sbloccare il programma "${programma.nome}"?\n` +
                    "Lo stato pipeline tornerà a MATERIALE_GENERATO.",
                )
              ) {
                return;
              }
              sbloccaMutation.mutate(
                {
                  id: programma.id,
                  payload: {
                    ramo: "pdc",
                    motivo: motivo !== null && motivo.length > 0 ? motivo : null,
                  },
                },
                {
                  onSuccess: onMutated,
                  onError: (err) => {
                    const msg =
                      err instanceof ApiError ? err.message : err.message;
                    window.alert(`Sblocco fallito: ${msg}`);
                  },
                },
              );
            }}
          >
            <Unlock className="mr-2 h-4 w-4" aria-hidden /> Sblocca materiale
          </Button>
        ) : null}
      </div>
    </Card>
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
              : "Programma archiviato: configurazione read-only"
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
 * Sprint 7.9 entry 113 (decisione utente 2026-05-03): post-MR 10
 * (bin-packing convogli paralleli) ogni giro = **1 convoglio fisico**.
 * I cluster A1 con date di applicazione sovrapposte (= convogli
 * paralleli) sono già stati separati in giri distinti. Quindi:
 *   pezzi_necessari = SUM(giri_regola) × n_pezzi_per_unit_composizione
 *
 * Pre-MR 10 invece il "giro aggregato A2" rappresentava UN turno
 * concettuale a N giornate, e per coprire ogni giorno del periodo
 * servivano N convogli sfasati simultaneamente — formula:
 *   pezzi = SUM(giornate_giri) × n_pezzi
 * Quel calcolo, post-MR 10, è doppio conteggio (es. 23 giri con 5.35
 * giornate medie = 123 pezzi, dovrebbero essere 23).
 */
function ConvogliNecessariSection({
  programma,
  giri,
}: {
  programma: ProgrammaDettaglioRead;
  giri: GiroListItem[];
}) {
  // Sprint 7.9 MR 7E: dotazione per capacity warning.
  const materialiQuery = useMateriali();
  const dotazione: Record<string, number | null> = {};
  for (const m of materialiQuery.data ?? []) {
    dotazione[m.codice] = m.pezzi_disponibili;
  }
  const sintesi = programma.regole.map((r) => {
    const materiali_regola = new Set(
      r.composizione_json.map((c) => c.materiale_tipo_codice),
    );
    const giri_regola = giri.filter(
      (g) => g.materiale_tipo_codice !== null && materiali_regola.has(g.materiale_tipo_codice),
    );
    // Sprint 7.9 entry 113: 1 giro = 1 convoglio fisico (post-MR 10).
    // Niente moltiplicazione per giornate.
    const n_convogli = giri_regola.length;
    const pezzi_per_tipo = r.composizione_json.map((c) => ({
      tipo: c.materiale_tipo_codice,
      pezzi: c.n_pezzi * n_convogli,
    }));
    return {
      regola_id: r.id,
      composizione: r.composizione_json,
      giri_count: giri_regola.length,
      convogli: n_convogli,
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
                {s.pezzi_per_tipo.map((p) => {
                  // Sprint 7.9 MR 7E: capacity check vs dotazione.
                  const disponibili = dotazione[p.tipo];
                  const isOverCapacity =
                    disponibili !== undefined &&
                    disponibili !== null &&
                    p.pezzi > disponibili;
                  const isUnknown = disponibili === undefined;
                  return (
                    <span
                      key={p.tipo}
                      title={
                        isOverCapacity
                          ? `Servono ${p.pezzi} pezzi ma in flotta ce ne sono solo ${disponibili}`
                          : disponibili !== undefined && disponibili !== null
                            ? `${p.pezzi} di ${disponibili} disponibili`
                            : disponibili === null
                              ? "Capacity illimitata (es. FLIRT TILO)"
                              : "Dotazione non registrata"
                      }
                      className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 font-mono text-xs ${
                        isOverCapacity
                          ? "border-destructive bg-destructive/10 text-destructive"
                          : isUnknown
                            ? "border-amber-300 bg-amber-50 text-amber-900"
                            : "border-emerald-300 bg-emerald-50 text-emerald-900"
                      }`}
                    >
                      <span>{p.tipo}</span>
                      <span className="opacity-50">×</span>
                      <span className="font-semibold tabular-nums">{p.pezzi}</span>
                      {disponibili !== undefined && disponibili !== null && (
                        <span className="opacity-70">/ {disponibili}</span>
                      )}
                      {disponibili === null && <span className="opacity-70">/ ∞</span>}
                    </span>
                  );
                })}
              </div>
              {s.pezzi_per_tipo.some((p) => {
                const d = dotazione[p.tipo];
                return d !== undefined && d !== null && p.pezzi > d;
              }) && (
                <p
                  role="alert"
                  className="mt-2 rounded-md border border-destructive/30 bg-destructive/5 px-2 py-1 text-xs text-destructive"
                >
                  ⚠ Questa regola supera la dotazione fisica per almeno un materiale. Aggiungi
                  altre regole per ripartire le corse, o usa filtri più restrittivi.
                </p>
              )}
            </div>
          </div>
        ))}
      </div>

      <p className="mt-4 text-xs italic text-muted-foreground">
        Post-MR 10: ogni giro è 1 convoglio fisico (i convogli paralleli sono già stati
        separati in turni distinti dal bin-packing). Pezzi necessari = numero giri ×
        composizione. Confronta con la dotazione registrata dell&apos;azienda.
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
          title={editable ? "Aggiungi una nuova regola" : "Programma archiviato: regole read-only"}
          data-testid="nuova-regola-assegnazione-btn"
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
// 4 · Ultimo run del builder (Sprint 7.9 MR 11C, entry 116)
// =====================================================================

function UltimoRunSection({ programmaId }: { programmaId: number }) {
  const query = useLastBuilderRun(programmaId);
  const run = query.data;

  if (query.isLoading) {
    return (
      <section>
        <div className="mb-3 flex items-baseline gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-foreground">
            Ultimo run del builder
          </h2>
        </div>
        <Card className="p-5 text-sm text-muted-foreground">Caricamento…</Card>
      </section>
    );
  }

  if (run == null) {
    return (
      <section>
        <div className="mb-3 flex items-baseline gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-foreground">
            Ultimo run del builder
          </h2>
        </div>
        <Card className="flex items-start gap-3 p-5">
          <Badge variant="muted">Mai eseguito</Badge>
          <p className="text-sm text-muted-foreground">
            Avvia la generazione dei giri dal pulsante &ldquo;Genera giri&rdquo; in cima alla
            pagina. Dopo il run vedrai qui le statistiche di copertura e gli eventuali avvisi.
          </p>
        </Card>
      </section>
    );
  }

  const isOk = run.n_giri_creati > 0;
  const eseguitoAt = new Date(run.eseguito_at).toLocaleString("it-IT");
  const totale = run.n_corse_processate + run.n_corse_residue;
  const coperturaPct =
    totale > 0 ? Math.round((run.n_corse_processate / totale) * 100) : 0;
  const warnings = (run.warnings_json ?? []).filter(
    (w): w is string => typeof w === "string",
  );

  return (
    <section>
      <div className="mb-3 flex items-baseline gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-foreground">
          Ultimo run del builder
        </h2>
        <span className="text-xs text-muted-foreground">
          {eseguitoAt} · sede {run.localita_codice}
        </span>
      </div>
      <Card className="p-5">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          {isOk ? (
            <Badge variant="success">{run.n_giri_creati} giri creati</Badge>
          ) : (
            <Badge variant="destructive">Nessun giro creato</Badge>
          )}
          {run.n_giri_chiusi > 0 && (
            <Badge variant="muted">{run.n_giri_chiusi} chiusi naturalmente</Badge>
          )}
          {run.n_giri_non_chiusi > 0 && (
            <Badge variant="warning">{run.n_giri_non_chiusi} non chiusi</Badge>
          )}
          {run.force && <Badge variant="muted">force = true</Badge>}
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div>
            <div className="text-xs uppercase tracking-wide text-muted-foreground">
              Corse processate
            </div>
            <div className="font-mono text-2xl tabular-nums">
              {run.n_corse_processate}
            </div>
          </div>
          <div>
            <div className="text-xs uppercase tracking-wide text-muted-foreground">
              Corse residue (non coperte)
            </div>
            <div
              className={cn(
                "font-mono text-2xl tabular-nums",
                run.n_corse_residue > 0 && "text-amber-600",
              )}
            >
              {run.n_corse_residue}
            </div>
          </div>
          <div>
            <div className="text-xs uppercase tracking-wide text-muted-foreground">
              Copertura PdE
            </div>
            <div className="font-mono text-2xl tabular-nums">{coperturaPct}%</div>
            {totale > 0 && (
              <div className="mt-1 h-1.5 w-full overflow-hidden rounded bg-secondary">
                <div
                  className={cn(
                    "h-full",
                    coperturaPct === 100 ? "bg-emerald-500" : "bg-amber-500",
                  )}
                  style={{ width: `${coperturaPct}%` }}
                />
              </div>
            )}
          </div>
        </div>

        {warnings.length > 0 && (
          <details className="mt-4 rounded border border-amber-300 bg-amber-50 p-3">
            <summary className="cursor-pointer text-sm font-medium text-amber-900">
              <AlertCircle className="mr-2 inline h-4 w-4" aria-hidden />
              {warnings.length} avvisi del builder
            </summary>
            <ul className="mt-2 space-y-1 text-xs text-amber-900">
              {warnings.slice(0, 50).map((w, i) => (
                <li key={i} className="font-mono">
                  • {w}
                </li>
              ))}
              {warnings.length > 50 && (
                <li className="italic">
                  …e altri {warnings.length - 50} (mostrati i primi 50)
                </li>
              )}
            </ul>
          </details>
        )}
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
