import type { ComponentType, SVGProps } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  ListChecks,
  Workflow,
} from "lucide-react";

import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { useAuth } from "@/lib/auth/AuthContext";
import { usePianificatorePdcOverview } from "@/hooks/usePianificatorePdc";
import { cn } from "@/lib/utils";

/**
 * Dashboard home del 2° ruolo (PIANIFICATORE_PDC).
 *
 * Sprint 7.10 MR 7.10.2 — variante v1 dal pacchetto Anthropic Design
 * Handoff (`arturo/06-dashboard-pdc.html`):
 * - HERO grande in alto (eyebrow + h1 + descrizione + onboarding 3-step)
 * - RAIL KPI piccoli a destra (4 KPI: giri / turni / violazioni / rev)
 * - DISTRIBUZIONE turni per impianto con empty state narrativo (no
 *   "cimitero degli zeri")
 * - ACTION CARDS rapidi a Vista giri e Lista turni
 *
 * Hooks/data fetching invariati rispetto al MR precedente
 * (`usePianificatorePdcOverview`).
 */
export function PianificatorePdcDashboardRoute() {
  const { user } = useAuth();
  const overview = usePianificatorePdcOverview();
  const data = overview.data;

  const giriCount = data?.giri_materiali_count ?? null;
  const turniTotali = data === undefined
    ? null
    : data.turni_pdc_per_impianto.reduce((sum, item) => sum + item.count, 0);
  const impiantiCount = data?.turni_pdc_per_impianto.length ?? 0;
  const violazioniHard = data?.turni_con_violazioni_hard ?? null;

  // Stato onboarding: derivato dai KPI reali. Step 1 attivo finché non
  // ci sono turni (l'utente deve aprire Vista giri); step 2/3 indicizzati.
  const turniGenerati = (turniTotali ?? 0) > 0;
  const violazioniDaRisolvere = (violazioniHard ?? 0) > 0;

  return (
    <div className="flex flex-col gap-6">
      {/* Breadcrumb minimo */}
      <div className="text-xs text-muted-foreground">Home</div>

      {/* HERO — grid 12-col: copy+onboarding | rail KPI */}
      <section className="overflow-hidden rounded-lg border border-border bg-white">
        <div className="grid grid-cols-1 lg:grid-cols-12">
          {/* LEFT col-span-8: copy + onboarding 3-step */}
          <div className="p-8 lg:col-span-8">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-primary">
              Pianificatore Turno PdC
            </div>
            <h1 className="mb-2 text-3xl font-bold tracking-tight text-primary">
              Dashboard Pianificatore Turno PdC
            </h1>
            <p className="max-w-[520px] text-sm leading-relaxed text-muted-foreground">
              Benvenuto{user !== null ? `, ${user.username}` : ""}. Da qui
              costruisci i turni del personale di macchina partendo dai giri
              materiali pubblicati dal Pianificatore Giro.{" "}
              {!turniGenerati && (
                <>
                  Non hai ancora generato turni: segui i tre passi qui sotto
                  per iniziare.
                </>
              )}
            </p>

            {/* Onboarding checklist 3-step */}
            <ol className="mt-7 flex flex-col gap-3">
              <OnboardingStep
                n={1}
                title="Apri la Vista giri materiali"
                description={
                  giriCount !== null
                    ? `${giriCount} giri pubblicati dal 1° ruolo, in sola lettura. Scegli un giro pubblicato.`
                    : "Esplora i giri pubblicati dal 1° ruolo, in sola lettura."
                }
                state={!turniGenerati ? "active" : "done"}
                cta={
                  !turniGenerati
                    ? { to: "/pianificatore-pdc/giri", label: "Vai" }
                    : undefined
                }
              />
              <OnboardingStep
                n={2}
                title="Genera i turni dal dettaglio del giro"
                description={
                  <>
                    Apri un giro materiale, premi{" "}
                    <span className="font-medium text-foreground">
                      &ldquo;Genera turni PdC&rdquo;
                    </span>
                    . Il builder costruisce automaticamente prestazione,
                    condotta, refezione e FR.
                  </>
                }
                state={turniGenerati && !violazioniDaRisolvere ? "active" : turniGenerati ? "done" : "todo"}
              />
              <OnboardingStep
                n={3}
                title="Valida turni e risolvi le violazioni hard"
                description="Apri il visualizzatore Gantt del turno per leggere giornata per giornata e segnare le violazioni risolte."
                state={violazioniDaRisolvere ? "active" : turniGenerati ? "done" : "todo"}
              />
            </ol>
          </div>

          {/* RIGHT col-span-4: rail KPI */}
          <aside className="border-t border-border bg-muted/40 p-6 lg:col-span-4 lg:border-l lg:border-t-0">
            <div className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Stato pianificazione
            </div>

            <div className="flex flex-col gap-3">
              <KpiRailCard
                title="Giri materiali"
                icon={Workflow}
                value={giriCount}
                loading={overview.isLoading}
                error={overview.isError}
                hint="sorgente per i turni PdC"
              />
              <KpiRailCard
                title="Turni PdC"
                icon={ListChecks}
                value={turniTotali}
                loading={overview.isLoading}
                error={overview.isError}
                hint={
                  turniGenerati
                    ? `Su ${impiantiCount} impianto/i`
                    : "Nessun turno generato"
                }
                hintAccent={!turniGenerati && !overview.isLoading ? "warning" : "neutral"}
                hintCta={
                  !turniGenerati && !overview.isLoading
                    ? { to: "/pianificatore-pdc/giri", label: "genera ora →" }
                    : undefined
                }
                accent={!turniGenerati && !overview.isLoading ? "warning" : "neutral"}
              />
              <KpiRailCard
                title="Violazioni hard"
                icon={AlertTriangle}
                value={violazioniHard}
                loading={overview.isLoading}
                error={overview.isError}
                hint="Prestazione/condotta fuori cap"
                accent={violazioniDaRisolvere ? "warning" : "neutral"}
              />
              <KpiRailCard
                title="Rev. cascading"
                icon={Workflow}
                value={null}
                loading={false}
                error={false}
                hint="Disponibile da Sprint 7.6"
                placeholder="—"
              />
            </div>
          </aside>
        </div>
      </section>

      {/* ACTION CARDS — accesso rapido alle 2 sezioni operative */}
      <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <ActionCard
          to="/pianificatore-pdc/giri"
          title="Vista giri materiali"
          description={
            giriCount !== null
              ? `Esplora i ${giriCount} giri pubblicati. Da ognuno puoi generare il turno PdC.`
              : "Esplora i giri pubblicati. Da ognuno puoi generare il turno PdC."
          }
          cta="Apri vista giri"
        />
        <ActionCard
          to="/pianificatore-pdc/turni"
          title="Lista turni PdC"
          description="Filtra per impianto, codice, stato. Click riga = visualizzatore Gantt."
          cta="Apri lista turni"
        />
      </section>

      {/* DISTRIBUZIONE turni per impianto */}
      <Card className="p-6">
        <div className="mb-4 flex items-baseline justify-between">
          <h2 className="text-base font-semibold text-primary">
            Distribuzione turni per impianto
          </h2>
          <span className="text-xs text-muted-foreground">25 depositi PdC Trenord</span>
        </div>

        {overview.isLoading ? (
          <Spinner label="Caricamento KPI…" />
        ) : overview.isError ? (
          <p className="text-sm text-destructive" role="alert">
            Errore caricamento KPI: {overview.error?.message ?? "errore sconosciuto"}
          </p>
        ) : data === undefined || data.turni_pdc_per_impianto.length === 0 ? (
          <DistribuzioneEmpty />
        ) : (
          <ul className="flex flex-col gap-1 text-sm">
            {data.turni_pdc_per_impianto.map((item) => (
              <li
                key={item.impianto}
                className="flex justify-between border-b border-border py-1.5 last:border-0"
              >
                <span className="font-medium">{item.impianto}</span>
                <span className="font-mono tabular-nums text-muted-foreground">
                  {item.count}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Footer info */}
      <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
        <span>Auto-refresh 60s</span>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────
// Sub-components
// ────────────────────────────────────────────────────────────────────────

type LucideIcon = ComponentType<SVGProps<SVGSVGElement>>;

interface KpiRailCardProps {
  title: string;
  icon: LucideIcon;
  value: number | null;
  loading: boolean;
  error: boolean;
  hint: string;
  hintAccent?: "neutral" | "warning";
  hintCta?: { to: string; label: string };
  accent?: "neutral" | "warning";
  placeholder?: string;
}

function KpiRailCard({
  title,
  icon: Icon,
  value,
  loading,
  error,
  hint,
  hintAccent = "neutral",
  hintCta,
  accent = "neutral",
  placeholder = "—",
}: KpiRailCardProps) {
  const display = loading ? "…" : error ? "—" : value === null ? placeholder : String(value);
  const isZero = value === 0;

  return (
    <div
      className={cn(
        "rounded-md border bg-white p-3",
        accent === "warning" && !loading
          ? "border-amber-300 ring-1 ring-amber-100"
          : "border-border",
      )}
    >
      <div className="flex items-center justify-between">
        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
          {title}
        </div>
        <Icon className="h-3.5 w-3.5 text-muted-foreground/70" aria-hidden />
      </div>
      <div
        className={cn(
          "mt-1 text-2xl font-semibold tabular-nums",
          isZero || display === "—" || display === "…" ? "text-muted-foreground/50" : "text-foreground",
        )}
      >
        {display}
      </div>
      <div
        className={cn(
          "mt-0.5 flex items-center gap-1 text-[11px]",
          hintAccent === "warning" ? "text-amber-700" : "text-muted-foreground",
        )}
      >
        <span>{hint}</span>
        {hintCta !== undefined && (
          <Link to={hintCta.to} className="font-medium hover:underline">
            {hintCta.label}
          </Link>
        )}
      </div>
    </div>
  );
}

interface OnboardingStepProps {
  n: number;
  title: string;
  description: React.ReactNode;
  state: "active" | "done" | "todo";
  cta?: { to: string; label: string };
}

function OnboardingStep({ n, title, description, state, cta }: OnboardingStepProps) {
  return (
    <li
      className={cn(
        "flex items-start gap-4 rounded-md border p-4",
        state === "active" ? "border-border bg-muted/40" : "border-border",
      )}
    >
      <div
        className={cn(
          "grid h-7 w-7 shrink-0 place-items-center rounded-full text-sm font-semibold",
          state === "active"
            ? "border-2 border-primary bg-white text-primary"
            : state === "done"
              ? "border-2 border-emerald-500 bg-emerald-50 text-emerald-700"
              : "border border-border bg-white text-muted-foreground",
        )}
        aria-label={`Step ${n}${state === "done" ? " completato" : state === "active" ? " attivo" : ""}`}
      >
        {state === "done" ? "✓" : n}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "text-sm font-semibold",
              state === "todo" ? "text-foreground/70" : "text-foreground",
            )}
          >
            {title}
          </span>
          {state === "active" && (
            <span className="inline-flex items-center rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-emerald-800">
              prossimo
            </span>
          )}
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
      </div>
      {cta !== undefined && (
        <Link
          to={cta.to}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition hover:opacity-90"
        >
          {cta.label}
          <span aria-hidden>→</span>
        </Link>
      )}
    </li>
  );
}

interface ActionCardProps {
  to: string;
  title: string;
  description: string;
  cta: string;
}

function ActionCard({ to, title, description, cta }: ActionCardProps) {
  return (
    <Link
      to={to}
      className="group block rounded-lg border border-border bg-white p-6 transition hover:border-primary/50 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-base font-semibold text-foreground">{title}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{description}</p>
        </div>
        <ArrowRight
          className="h-5 w-5 shrink-0 text-muted-foreground/60 transition group-hover:translate-x-1 group-hover:text-primary"
          aria-hidden
        />
      </div>
      <div className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-primary">
        {cta}
        <ArrowRight className="h-4 w-4" aria-hidden />
      </div>
    </Link>
  );
}

function DistribuzioneEmpty() {
  return (
    <div className="rounded-md border border-dashed border-border px-6 py-10 text-center">
      <div className="mx-auto mb-3 grid h-16 w-16 place-items-center rounded-full bg-muted">
        <svg
          className="h-8 w-8 text-muted-foreground/40"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden
        >
          <path d="M3 21l1.5-9 7.5-3 7.5 3L21 21M3 21h18M9 21V13M15 21V13" />
        </svg>
      </div>
      <div className="text-sm font-medium">Nessun turno PdC presente</div>
      <p className="mx-auto mt-1 max-w-md text-xs text-muted-foreground">
        I turni si distribuiscono qui per impianto (MILANO_GA, BRESCIA,
        BERGAMO, …) dopo la prima generazione dal dettaglio di un giro
        materiale.
      </p>
    </div>
  );
}
