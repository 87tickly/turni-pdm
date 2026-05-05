import { useMemo } from "react";
import type { ComponentType, SVGProps } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  BedDouble,
  Building2,
  CheckCircle2,
  ListChecks,
  Workflow,
} from "lucide-react";

import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { useAuth } from "@/lib/auth/AuthContext";
import { usePianificatorePdcOverview } from "@/hooks/usePianificatorePdc";
import { useTurniPdcAzienda } from "@/hooks/useTurniPdc";
import { useDepots } from "@/hooks/useAnagrafiche";
import { cn } from "@/lib/utils";

/**
 * Dashboard home del 2° ruolo (PIANIFICATORE_PDC).
 *
 * Sprint 7.11 MR 7.11.1 — riscrittura "intuitiva" (single-screen,
 * action-driven). Sostituisce la variante v1 (hero + checklist 3-step)
 * che funzionava bene per lo zero-state ma diventava rumore quando i
 * dati operativi erano presenti.
 *
 * Layout:
 * 1. Banner CTA "Cosa fare ora" — derivato dallo stato:
 *    - violazioni > 0 → apri il primo turno violato
 *    - turni < giri pubblicati → c'è ancora da convertire
 *    - tutto ok → Lista turni
 * 2. 4 KPI grandi (giri / turni / violazioni / impianti coperti)
 * 3. Layout 2-col: ultimi turni (sx) + distribuzione impianti (dx)
 * 4. Footer scorciatoie compatto
 *
 * Hooks: usePianificatorePdcOverview (KPI) + useTurniPdcAzienda (lista
 * per CTA + ultimi turni). La lista turni è soft-failure: se l'hook
 * fallisce, il banner CTA cade in stato di default e la sezione "ultimi
 * turni" mostra empty state — KPI e distribuzione restano funzionanti.
 */
export function PianificatorePdcDashboardRoute() {
  const { user } = useAuth();
  const overview = usePianificatorePdcOverview();
  const turniQuery = useTurniPdcAzienda({ limit: 10 });
  // Sprint 7.11 MR 7.11.2: anagrafica depot per il denominatore del KPI
  // "Impianti coperti" (N / TOTALE_DEPOSITI). Senza anagrafica resta solo
  // il numeratore.
  const depotsQuery = useDepots();

  const data = overview.data;
  const giriCount = data?.giri_materiali_count ?? 0;
  const turniTotali = data === undefined
    ? 0
    : data.turni_pdc_per_impianto.reduce((sum, item) => sum + item.count, 0);
  // Sprint 7.9 MR η — ora usiamo la distribuzione per deposito FK
  // (`turni_pdc_per_deposito`); i turni con FK valorizzata danno i
  // depositi "veri", quelli legacy hanno deposito_pdc_id null.
  const depositiCoperti = useMemo(() => {
    if (data === undefined) return 0;
    return data.turni_pdc_per_deposito.filter(
      (d) => d.deposito_pdc_id !== null && d.count > 0,
    ).length;
  }, [data]);
  const impiantiTotali =
    data?.depositi_pdc_totali ?? depotsQuery.data?.length ?? null;
  const violazioniHard = data?.turni_con_violazioni_hard ?? 0;
  const dormiteFr = data?.dormite_fr_totali ?? 0;
  const turniFrCap = data?.turni_con_fr_cap_violazioni ?? 0;

  // Stabilizziamo l'array per evitare di invalidare i useMemo a valle
  // ad ogni render (regola react-hooks/exhaustive-deps).
  const turniList = useMemo(() => turniQuery.data ?? [], [turniQuery.data]);

  // Primo turno con violazioni (per CTA banner). Lista sortata da API
  // per created_at desc; client-side filtra per n_violazioni > 0.
  // Sprint 7.9 MR η: prioritizza turni con cap FR violato — più urgente
  // di un'eccedenza prestazione perché tocca il vincolo PdC normativo.
  const turnoFrCap = useMemo(
    () => turniList.find((t) => t.n_fr_cap_violazioni > 0),
    [turniList],
  );
  const turnoViolato = useMemo(
    () => turniList.find((t) => t.n_violazioni > 0),
    [turniList],
  );

  // CTA contestuale derivata dallo stato del lavoro.
  const cta = useMemo(() => {
    if (overview.isLoading) {
      return { kind: "loading" as const };
    }
    if (overview.isError) {
      return { kind: "error" as const };
    }
    if (turniFrCap > 0 && turnoFrCap !== undefined) {
      return {
        kind: "fr-cap" as const,
        count: turniFrCap,
        primoTurno: turnoFrCap.codice,
        href: `/pianificatore-pdc/turni/${turnoFrCap.id}`,
      };
    }
    if (violazioniHard > 0 && turnoViolato !== undefined) {
      return {
        kind: "violazioni" as const,
        count: violazioniHard,
        primoTurno: turnoViolato.codice,
        href: `/pianificatore-pdc/turni/${turnoViolato.id}`,
      };
    }
    if (violazioniHard > 0) {
      return {
        kind: "violazioni-no-link" as const,
        count: violazioniHard,
      };
    }
    if (giriCount > 0 && turniTotali === 0) {
      return {
        kind: "primo-turno" as const,
        giri: giriCount,
        href: "/pianificatore-pdc/giri",
      };
    }
    if (giriCount > turniTotali) {
      return {
        kind: "altri-da-convertire" as const,
        residui: giriCount - turniTotali,
        href: "/pianificatore-pdc/giri",
      };
    }
    if (turniTotali > 0) {
      return {
        kind: "tutto-ok" as const,
        turni: turniTotali,
        href: "/pianificatore-pdc/turni",
      };
    }
    return { kind: "empty" as const };
  }, [
    overview.isLoading,
    overview.isError,
    turniFrCap,
    turnoFrCap,
    violazioniHard,
    turnoViolato,
    giriCount,
    turniTotali,
  ]);

  const ultimiTurni = useMemo(() => turniList.slice(0, 5), [turniList]);

  return (
    <div className="flex flex-col gap-5">
      {/* breadcrumb */}
      <div className="text-xs text-muted-foreground">Home</div>

      {/* HEADER pagina compatto (h1 conservato per heading ARIA + test) */}
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold tracking-tight text-primary">
          Dashboard Pianificatore Turno PdC
        </h1>
        <p className="text-sm text-muted-foreground">
          Benvenuto{user !== null ? `, ${user.username}` : ""}. Da qui costruisci
          i turni del personale di macchina partendo dai giri materiali pubblicati.
        </p>
      </header>

      {/* BANNER CTA "Cosa fare ora" */}
      <CtaBanner cta={cta} />

      {/* 5 KPI grandi (Sprint 7.9 MR η: aggiunto FR) */}
      <section className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-5">
        <KpiCard
          icon={Workflow}
          label="Giri materiali"
          value={giriCount}
          loading={overview.isLoading}
          error={overview.isError}
          hint="Sorgente per i turni PdC"
        />
        <KpiCard
          icon={ListChecks}
          label="Turni PdC"
          value={turniTotali}
          loading={overview.isLoading}
          error={overview.isError}
          hint={
            turniTotali > 0
              ? `Su ${depositiCoperti} deposito/i`
              : "Nessuno generato"
          }
          accent={turniTotali === 0 && !overview.isLoading ? "warning" : "neutral"}
        />
        <KpiCard
          icon={AlertTriangle}
          label="Violazioni hard"
          value={violazioniHard}
          loading={overview.isLoading}
          error={overview.isError}
          hint="Prestazione/condotta fuori cap"
          accent={violazioniHard > 0 ? "danger" : "neutral"}
        />
        <KpiCard
          icon={BedDouble}
          label="Dormite FR"
          value={dormiteFr}
          loading={overview.isLoading}
          error={overview.isError}
          hint={
            turniFrCap > 0
              ? `${turniFrCap} turno/i con cap FR violato`
              : "Pernotti fuori sede totali"
          }
          accent={turniFrCap > 0 ? "danger" : dormiteFr > 0 ? "warning" : "neutral"}
        />
        <KpiCard
          icon={Building2}
          label="Depositi coperti"
          value={depositiCoperti}
          loading={overview.isLoading}
          error={overview.isError}
          hint={
            impiantiTotali !== null
              ? `Su ${impiantiTotali} depositi PdC totali`
              : "Depositi PdC con almeno 1 turno"
          }
          denominator={impiantiTotali}
        />
      </section>

      {/* LAYOUT 2-COL: ultimi turni (sx) + distribuzione impianti (dx) */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="flex flex-col p-4">
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-sm font-semibold text-primary">Ultimi turni</h2>
            <Link
              to="/pianificatore-pdc/turni"
              className="text-xs font-medium text-muted-foreground hover:text-primary"
            >
              vedi tutti →
            </Link>
          </div>
          {turniQuery.isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Spinner label="Caricamento turni…" />
            </div>
          ) : ultimiTurni.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-8 text-center text-xs text-muted-foreground">
              <span>Nessun turno generato finora.</span>
              <Link
                to="/pianificatore-pdc/giri"
                className="font-medium text-primary hover:underline"
              >
                Apri vista giri →
              </Link>
            </div>
          ) : (
            <ul className="flex flex-col divide-y divide-border/60">
              {ultimiTurni.map((t) => (
                <li key={t.id}>
                  <Link
                    to={`/pianificatore-pdc/turni/${t.id}`}
                    className="flex items-center justify-between gap-3 py-2 text-sm transition-colors hover:bg-primary/[0.03]"
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="font-mono text-[13px] font-semibold text-primary">
                        {t.codice}
                      </span>
                      <span className="truncate text-xs text-muted-foreground">
                        {t.impianto}
                      </span>
                    </span>
                    <span className="flex shrink-0 items-center gap-2 text-xs">
                      {t.n_violazioni > 0 && (
                        <span className="inline-flex items-center gap-1 text-amber-700">
                          <AlertTriangle className="h-3 w-3" aria-hidden />
                          {t.n_violazioni}
                        </span>
                      )}
                      <span className="font-mono tabular-nums text-muted-foreground">
                        {t.n_giornate}g
                      </span>
                      <ArrowRight className="h-3 w-3 text-muted-foreground/40" aria-hidden />
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="flex flex-col p-4">
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-sm font-semibold text-primary">
              Distribuzione per deposito PdC
            </h2>
            {impiantiTotali !== null && (
              <span className="text-xs text-muted-foreground">
                {impiantiTotali} depositi PdC totali
              </span>
            )}
          </div>
          {overview.isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Spinner label="Caricamento KPI…" />
            </div>
          ) : overview.isError ? (
            <p className="py-4 text-sm text-destructive" role="alert">
              Errore caricamento KPI: {overview.error?.message ?? "errore sconosciuto"}
            </p>
          ) : data === undefined || data.turni_pdc_per_deposito.length === 0 ? (
            <p className="py-4 text-sm text-muted-foreground">
              Nessun turno PdC presente per la tua azienda.
            </p>
          ) : (
            <ul className="flex flex-col gap-1 text-sm">
              {data.turni_pdc_per_deposito.map((item) => {
                // Mini-bar proporzionale al max nella lista (visual quick-scan)
                const max = Math.max(
                  ...data.turni_pdc_per_deposito.map((x) => x.count),
                  1,
                );
                const widthPct = (item.count / max) * 100;
                const label =
                  item.deposito_pdc_codice ?? "(senza deposito)";
                const tooltip = item.deposito_pdc_display ?? "Turni legacy senza FK deposito";
                return (
                  <li
                    key={`${item.deposito_pdc_id ?? "legacy"}-${label}`}
                    className="flex items-center justify-between gap-3 py-1"
                  >
                    <span
                      className={cn(
                        "font-medium truncate",
                        item.deposito_pdc_id === null && "italic text-muted-foreground",
                      )}
                      title={tooltip}
                    >
                      {label}
                    </span>
                    <span className="flex shrink-0 items-center gap-2">
                      {item.n_dormite_fr_totali > 0 && (
                        <span
                          className="inline-flex items-center gap-0.5 text-[10px] text-amber-700"
                          title={`${item.n_dormite_fr_totali} dormite FR`}
                        >
                          <BedDouble className="h-3 w-3" aria-hidden />
                          {item.n_dormite_fr_totali}
                        </span>
                      )}
                      <span
                        className="h-1.5 rounded-full bg-primary/30"
                        style={{ width: `${widthPct * 0.8}px` }}
                        aria-hidden
                      />
                      <span className="font-mono tabular-nums text-muted-foreground">
                        {item.count}
                      </span>
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      </section>

      {/* FOOTER scorciatoie compatto */}
      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <FooterShortcut
          to="/pianificatore-pdc/giri"
          title="Vista giri materiali"
          cta="Apri vista giri"
        />
        <FooterShortcut
          to="/pianificatore-pdc/turni"
          title="Lista turni PdC"
          cta="Apri lista turni"
        />
      </section>

      {/* Footer info: rev. cascading (preserva hint per test) */}
      <p className="text-[11px] text-muted-foreground">
        Revisioni cascading —{" "}
        <span className="text-muted-foreground">Disponibile da Sprint 7.6</span>
      </p>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────
// Sub-components
// ────────────────────────────────────────────────────────────────────────

type LucideIcon = ComponentType<SVGProps<SVGSVGElement>>;

type CtaState =
  | { kind: "loading" }
  | { kind: "error" }
  | { kind: "fr-cap"; count: number; primoTurno: string; href: string }
  | { kind: "violazioni"; count: number; primoTurno: string; href: string }
  | { kind: "violazioni-no-link"; count: number }
  | { kind: "primo-turno"; giri: number; href: string }
  | { kind: "altri-da-convertire"; residui: number; href: string }
  | { kind: "tutto-ok"; turni: number; href: string }
  | { kind: "empty" };

function CtaBanner({ cta }: { cta: CtaState }) {
  if (cta.kind === "loading" || cta.kind === "error") {
    return (
      <div className="rounded-lg border border-border bg-muted/30 px-5 py-4 text-sm text-muted-foreground">
        {cta.kind === "loading" ? "Verifico lo stato della pianificazione…" : "Stato pianificazione non disponibile."}
      </div>
    );
  }

  if (cta.kind === "fr-cap") {
    return (
      <div className="flex items-center justify-between gap-4 rounded-lg border border-red-300 bg-red-50 px-5 py-4">
        <div className="flex items-start gap-3">
          <BedDouble className="mt-0.5 h-5 w-5 shrink-0 text-red-600" aria-hidden />
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-red-700">
              Cosa fare ora · Cap FR violato
            </div>
            <div className="text-base font-semibold text-red-900">
              Hai {cta.count} turno
              {cta.count === 1 ? "" : "/i"} oltre il limite FR di NORMATIVA-PDC §10.6
            </div>
            <div className="text-xs text-red-800">
              Inizia dal turno{" "}
              <span className="font-mono font-semibold">{cta.primoTurno}</span>:
              valuta un deposito più vicino al fine giornata, oppure rigenera
              senza FR.
            </div>
          </div>
        </div>
        <Link
          to={cta.href}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-md bg-red-600 px-3 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-red-700"
        >
          Apri il turno
          <ArrowRight className="h-4 w-4" aria-hidden />
        </Link>
      </div>
    );
  }

  if (cta.kind === "violazioni" || cta.kind === "violazioni-no-link") {
    return (
      <div className="flex items-center justify-between gap-4 rounded-lg border border-amber-300 bg-amber-50 px-5 py-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" aria-hidden />
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-amber-700">
              Cosa fare ora
            </div>
            <div className="text-base font-semibold text-amber-900">
              Hai {cta.count} violazion{cta.count === 1 ? "e" : "i"} hard da risolvere
            </div>
            {cta.kind === "violazioni" && (
              <div className="text-xs text-amber-800">
                Inizia dal turno{" "}
                <span className="font-mono font-semibold">{cta.primoTurno}</span>.
              </div>
            )}
          </div>
        </div>
        {cta.kind === "violazioni" && (
          <Link
            to={cta.href}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-md bg-amber-600 px-3 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-amber-700"
          >
            Apri il turno
            <ArrowRight className="h-4 w-4" aria-hidden />
          </Link>
        )}
      </div>
    );
  }

  if (cta.kind === "primo-turno") {
    return (
      <CtaSimple
        icon={Workflow}
        eyebrow="Cosa fare ora"
        title={`Genera il primo turno PdC dai ${cta.giri} giri pubblicati`}
        description="Apri Vista giri, scegli un giro pubblicato, premi 'Genera turni PdC'."
        href={cta.href}
        ctaLabel="Apri vista giri"
        tone="primary"
      />
    );
  }

  if (cta.kind === "altri-da-convertire") {
    return (
      <CtaSimple
        icon={Workflow}
        eyebrow="Cosa fare ora"
        title={`${cta.residui} giri ancora da convertire in turni`}
        description="Apri Vista giri per generare i turni PdC mancanti."
        href={cta.href}
        ctaLabel="Apri vista giri"
        tone="primary"
      />
    );
  }

  if (cta.kind === "tutto-ok") {
    return (
      <CtaSimple
        icon={CheckCircle2}
        eyebrow="Cosa fare ora"
        title={`Tutto in linea: ${cta.turni} turni pubblicati, niente violazioni`}
        description="Puoi continuare con la lista turni o le revisioni cascading quando arriveranno."
        href={cta.href}
        ctaLabel="Apri lista turni"
        tone="success"
      />
    );
  }

  // empty: niente giri, niente turni
  return (
    <div className="rounded-lg border border-dashed border-border bg-white px-5 py-6 text-center">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Cosa fare ora
      </div>
      <div className="mt-1 text-base font-semibold text-foreground">
        Aspetta che il Pianificatore Giro pubblichi un giro materiale
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        Da quel momento potrai generare i turni PdC qui.
      </p>
    </div>
  );
}

interface CtaSimpleProps {
  icon: LucideIcon;
  eyebrow: string;
  title: string;
  description: string;
  href: string;
  ctaLabel: string;
  tone: "primary" | "success";
}

function CtaSimple({
  icon: Icon,
  eyebrow,
  title,
  description,
  href,
  ctaLabel,
  tone,
}: CtaSimpleProps) {
  const tones = {
    primary: {
      border: "border-primary/30",
      bg: "bg-primary/[0.04]",
      iconColor: "text-primary",
      eyebrowColor: "text-primary",
      titleColor: "text-foreground",
      btn: "bg-primary text-primary-foreground hover:opacity-90",
    },
    success: {
      border: "border-emerald-300",
      bg: "bg-emerald-50",
      iconColor: "text-emerald-600",
      eyebrowColor: "text-emerald-700",
      titleColor: "text-emerald-900",
      btn: "bg-emerald-600 text-white hover:bg-emerald-700",
    },
  }[tone];
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-4 rounded-lg border px-5 py-4",
        tones.border,
        tones.bg,
      )}
    >
      <div className="flex items-start gap-3">
        <Icon className={cn("mt-0.5 h-5 w-5 shrink-0", tones.iconColor)} aria-hidden />
        <div>
          <div
            className={cn(
              "text-[10px] font-semibold uppercase tracking-wider",
              tones.eyebrowColor,
            )}
          >
            {eyebrow}
          </div>
          <div className={cn("text-base font-semibold", tones.titleColor)}>{title}</div>
          <div className="text-xs text-muted-foreground">{description}</div>
        </div>
      </div>
      <Link
        to={href}
        className={cn(
          "inline-flex shrink-0 items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium shadow-sm transition",
          tones.btn,
        )}
      >
        {ctaLabel}
        <ArrowRight className="h-4 w-4" aria-hidden />
      </Link>
    </div>
  );
}

interface KpiCardProps {
  icon: LucideIcon;
  label: string;
  value: number;
  loading: boolean;
  error: boolean;
  hint: string;
  accent?: "neutral" | "warning" | "danger";
  /** Se presente, il valore è renderizzato come `value/denominator`. */
  denominator?: number | null;
}

function KpiCard({
  icon: Icon,
  label,
  value,
  loading,
  error,
  hint,
  accent = "neutral",
  denominator = null,
}: KpiCardProps) {
  const display = loading
    ? "…"
    : error
      ? "—"
      : denominator !== null
        ? `${value}/${denominator}`
        : String(value);
  const accentBorder = {
    neutral: "border-border",
    warning: "border-amber-300 ring-1 ring-amber-100",
    danger: "border-red-300 ring-1 ring-red-100",
  }[accent];
  const accentValueColor = {
    neutral: "text-foreground",
    warning: "text-amber-700",
    danger: "text-red-700",
  }[accent];
  return (
    <Card className={cn("p-5", accentBorder)}>
      <div className="flex items-center justify-between">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          {label}
        </div>
        <Icon className="h-4 w-4 text-muted-foreground/60" aria-hidden />
      </div>
      <div
        className={cn(
          "mt-2 text-4xl font-bold tabular-nums",
          value === 0 && !loading && !error ? "text-muted-foreground/40" : accentValueColor,
        )}
      >
        {display}
      </div>
      <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
    </Card>
  );
}

function FooterShortcut({
  to,
  title,
  cta,
}: {
  to: string;
  title: string;
  cta: string;
}) {
  return (
    <Link
      to={to}
      className="group flex items-center justify-between rounded-md border border-border bg-white px-4 py-3 transition hover:border-primary/50 hover:bg-primary/[0.03]"
    >
      <span className="flex flex-col">
        <span className="text-sm font-semibold text-foreground">{title}</span>
        <span className="text-xs text-muted-foreground">{cta}</span>
      </span>
      <ArrowRight
        className="h-4 w-4 text-muted-foreground/40 transition group-hover:translate-x-0.5 group-hover:text-primary"
        aria-hidden
      />
    </Link>
  );
}
