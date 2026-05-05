import { useMemo } from "react";
import type { ComponentType, SVGProps } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  BedDouble,
  Building2,
  CalendarDays,
  Heart,
  Plane,
  ShieldCheck,
  Users,
} from "lucide-react";

import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { useAuth } from "@/lib/auth/AuthContext";
import {
  useGestionePersonaleKpi,
  useGestionePersonaleKpiDepositi,
} from "@/hooks/useGestionePersonale";
import { cn } from "@/lib/utils";

/**
 * Sprint 7.9 MR ζ — Home Gestione Personale (4° ruolo).
 *
 * Layout (allineato al pattern PianificatorePdcDashboardRoute):
 * 1. Breadcrumb + header
 * 2. Banner copertura (verde se ≥ 90%, ambra 80-90%, rosso < 80%)
 * 3. 4 KPI grandi (attivi, in servizio, ferie, malattia)
 * 4. Card mini "Altre assenze" (ROL/sciopero/formazione/congedo)
 * 5. Tabella copertura per deposito (con drilldown)
 * 6. Footer scorciatoie
 */
export function GestionePersonaleDashboardRoute() {
  const { user } = useAuth();
  const kpi = useGestionePersonaleKpi();
  const kpiDepositi = useGestionePersonaleKpiDepositi();

  const data = kpi.data;
  const banner = useMemo(() => {
    if (kpi.isLoading) return { kind: "loading" as const };
    if (kpi.isError || data === undefined) return { kind: "error" as const };
    const pct = data.copertura_pct;
    if (pct >= 90) return { kind: "ok" as const, pct };
    if (pct >= 80) return { kind: "warning" as const, pct };
    return { kind: "danger" as const, pct };
  }, [kpi.isLoading, kpi.isError, data]);

  const altreAssenze = data === undefined ? 0 : data.in_altra_assenza;

  return (
    <div className="flex flex-col gap-5">
      {/* breadcrumb */}
      <div className="text-xs text-muted-foreground">Home</div>

      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold tracking-tight text-primary">
          Dashboard Gestione Personale
        </h1>
        <p className="text-sm text-muted-foreground">
          Benvenuto{user !== null ? `, ${user.username}` : ""}. Da qui gestisci
          anagrafica PdC, depositi, ferie, malattie e copertura turni.
        </p>
      </header>

      <CopertureBanner banner={banner} />

      {/* 4 KPI principali */}
      <section className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          icon={Users}
          label="PdC attivi"
          value={data?.persone_attive ?? 0}
          loading={kpi.isLoading}
          error={kpi.isError}
          hint="Matricole attive in azienda"
        />
        <KpiCard
          icon={ShieldCheck}
          label="In servizio oggi"
          value={data?.in_servizio_oggi ?? 0}
          loading={kpi.isLoading}
          error={kpi.isError}
          hint={`${data?.copertura_pct ?? 0}% di copertura`}
          accent={banner.kind === "ok" ? "success" : banner.kind === "warning" ? "warning" : banner.kind === "danger" ? "danger" : "neutral"}
        />
        <KpiCard
          icon={Plane}
          label="In ferie"
          value={data?.in_ferie ?? 0}
          loading={kpi.isLoading}
          error={kpi.isError}
          hint="Ferie approvate in corso"
        />
        <KpiCard
          icon={Heart}
          label="In malattia"
          value={data?.in_malattia ?? 0}
          loading={kpi.isLoading}
          error={kpi.isError}
          hint="Certificate attive oggi"
          accent={(data?.in_malattia ?? 0) > 0 ? "warning" : "neutral"}
        />
      </section>

      {/* riga "altre assenze" piccola */}
      <section className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Card className="flex items-center gap-3 p-4">
          <BedDouble className="h-5 w-5 text-muted-foreground/70" aria-hidden />
          <div className="flex-1">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              ROL
            </div>
            <div className="text-2xl font-bold tabular-nums">
              {data?.in_rol ?? 0}
            </div>
          </div>
        </Card>
        <Card className="flex items-center gap-3 p-4">
          <CalendarDays className="h-5 w-5 text-muted-foreground/70" aria-hidden />
          <div className="flex-1">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Altre assenze
            </div>
            <div className="text-2xl font-bold tabular-nums">{altreAssenze}</div>
            <div className="mt-0.5 text-[10px] text-muted-foreground">
              sciopero · formazione · congedo
            </div>
          </div>
        </Card>
        <Link
          to="/gestione-personale/indisponibilita"
          className="flex items-center justify-between gap-3 rounded-lg border border-border bg-white p-4 transition hover:border-primary/50 hover:bg-primary/[0.03]"
        >
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Gestisci ferie & assenze
            </div>
            <div className="text-sm font-semibold text-foreground">
              Apri elenco indisponibilità
            </div>
          </div>
          <ArrowRight className="h-4 w-4 text-muted-foreground/40" aria-hidden />
        </Link>
      </section>

      {/* copertura per deposito */}
      <Card className="flex flex-col p-4">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold text-primary">
            Copertura per deposito
          </h2>
          <span className="text-xs text-muted-foreground">
            {kpiDepositi.data?.length ?? 0} depositi PdC
          </span>
        </div>
        {kpiDepositi.isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Spinner label="Caricamento depositi…" />
          </div>
        ) : kpiDepositi.isError ? (
          <p className="py-4 text-sm text-destructive" role="alert">
            Errore caricamento depositi: {kpiDepositi.error?.message ?? "errore sconosciuto"}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50 text-[10px] uppercase tracking-wider text-muted-foreground">
                  <th className="px-3 py-2 text-left font-semibold">Deposito</th>
                  <th className="w-20 px-3 py-2 text-right font-semibold">Attivi</th>
                  <th className="w-24 px-3 py-2 text-right font-semibold">In servizio</th>
                  <th className="w-24 px-3 py-2 text-right font-semibold">Assenti</th>
                  <th className="w-32 px-3 py-2 text-right font-semibold">Copertura</th>
                  <th className="w-8 px-3 py-2" aria-hidden />
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {(kpiDepositi.data ?? []).map((d) => {
                  const pctClass =
                    d.persone_attive === 0
                      ? "text-muted-foreground/40"
                      : d.copertura_pct >= 90
                        ? "text-emerald-700"
                        : d.copertura_pct >= 80
                          ? "text-amber-700"
                          : "text-red-700";
                  return (
                    <tr
                      key={d.depot_codice}
                      className="transition-colors hover:bg-primary/[0.03]"
                    >
                      <td className="px-3 py-2.5">
                        <Link
                          to={`/gestione-personale/depositi/${encodeURIComponent(d.depot_codice)}`}
                          className="flex items-center gap-2 font-mono text-[13px] font-semibold text-primary hover:underline"
                        >
                          <Building2 className="h-3.5 w-3.5 opacity-70" aria-hidden />
                          {d.depot_codice}
                        </Link>
                        <div className="text-[10px] text-muted-foreground">
                          {d.depot_display_name}
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono tabular-nums">
                        {d.persone_attive}
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono tabular-nums">
                        {d.in_servizio_oggi}
                      </td>
                      <td
                        className={cn(
                          "px-3 py-2.5 text-right font-mono tabular-nums",
                          d.indisponibili_oggi > 0 && "text-amber-700",
                        )}
                      >
                        {d.indisponibili_oggi}
                      </td>
                      <td className={cn("px-3 py-2.5 text-right font-mono tabular-nums font-semibold", pctClass)}>
                        {d.persone_attive > 0 ? `${d.copertura_pct.toFixed(1)}%` : "—"}
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <ArrowRight className="h-3 w-3 text-muted-foreground/40" aria-hidden />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* shortcut footer */}
      <section className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <FooterShortcut to="/gestione-personale/persone" title="Anagrafica PdC" cta="Apri anagrafica" />
        <FooterShortcut to="/gestione-personale/depositi" title="Depositi PdC" cta="Apri elenco depositi" />
        <FooterShortcut to="/gestione-personale/calendario" title="Calendario assegnazioni" cta="Apri calendario" />
      </section>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────
// Sub-components
// ────────────────────────────────────────────────────────────────────────

type LucideIcon = ComponentType<SVGProps<SVGSVGElement>>;

type CopertureBannerState =
  | { kind: "loading" }
  | { kind: "error" }
  | { kind: "ok"; pct: number }
  | { kind: "warning"; pct: number }
  | { kind: "danger"; pct: number };

function CopertureBanner({ banner }: { banner: CopertureBannerState }) {
  if (banner.kind === "loading") {
    return (
      <div className="rounded-lg border border-border bg-muted/30 px-5 py-4 text-sm text-muted-foreground">
        Calcolo copertura PdC in corso…
      </div>
    );
  }
  if (banner.kind === "error") {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-5 py-4 text-sm text-destructive">
        KPI copertura non disponibili.
      </div>
    );
  }
  const tone = {
    ok: {
      border: "border-emerald-300",
      bg: "bg-emerald-50",
      icon: ShieldCheck,
      iconColor: "text-emerald-600",
      eyebrowColor: "text-emerald-700",
      titleColor: "text-emerald-900",
      title: "Copertura PdC ottima",
      desc: "Quasi tutti i PdC attivi sono in servizio oggi.",
    },
    warning: {
      border: "border-amber-300",
      bg: "bg-amber-50",
      icon: AlertTriangle,
      iconColor: "text-amber-600",
      eyebrowColor: "text-amber-700",
      titleColor: "text-amber-900",
      title: "Copertura PdC sotto target",
      desc: "Coordinati con il Pianificatore PdC per eventuali sostituzioni.",
    },
    danger: {
      border: "border-red-300",
      bg: "bg-red-50",
      icon: AlertTriangle,
      iconColor: "text-red-600",
      eyebrowColor: "text-red-700",
      titleColor: "text-red-900",
      title: "Copertura PdC critica",
      desc: "Ferie/malattie superano la soglia. Verifica i depositi più colpiti.",
    },
  }[banner.kind];

  const Icon = tone.icon;
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-4 rounded-lg border px-5 py-4",
        tone.border,
        tone.bg,
      )}
    >
      <div className="flex items-start gap-3">
        <Icon className={cn("mt-0.5 h-5 w-5 shrink-0", tone.iconColor)} aria-hidden />
        <div>
          <div
            className={cn(
              "text-[10px] font-semibold uppercase tracking-wider",
              tone.eyebrowColor,
            )}
          >
            Stato copertura
          </div>
          <div className={cn("text-base font-semibold", tone.titleColor)}>
            {tone.title} · {banner.pct.toFixed(1)}%
          </div>
          <div className="text-xs text-muted-foreground">{tone.desc}</div>
        </div>
      </div>
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
  accent?: "neutral" | "success" | "warning" | "danger";
}

function KpiCard({
  icon: Icon,
  label,
  value,
  loading,
  error,
  hint,
  accent = "neutral",
}: KpiCardProps) {
  const display = loading ? "…" : error ? "—" : String(value);
  const accentBorder = {
    neutral: "border-border",
    success: "border-emerald-300 ring-1 ring-emerald-100",
    warning: "border-amber-300 ring-1 ring-amber-100",
    danger: "border-red-300 ring-1 ring-red-100",
  }[accent];
  const accentValueColor = {
    neutral: "text-foreground",
    success: "text-emerald-700",
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

function FooterShortcut({ to, title, cta }: { to: string; title: string; cta: string }) {
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
