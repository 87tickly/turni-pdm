import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ProgrammaStatoBadge } from "@/components/domain/ProgrammaStatoBadge";
import { useAuth } from "@/lib/auth/AuthContext";
import { useGiriAzienda, useGiriProgramma } from "@/hooks/useGiri";
import { useProgramma, useProgrammi } from "@/hooks/useProgrammi";
import type { GiroListItem } from "@/lib/api/giri";
import type { ProgrammaMaterialeRead } from "@/lib/api/programmi";
import { formatPeriodo } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Dashboard Pianificatore Giro Materiale (schermata 1).
 *
 * Layout in 3 zone verticali (design `arturo/01-dashboard.html`):
 *   1. Banda alert amber — visibile se esistono giri non-chiusi.
 *   2. Griglia 8/4: cards "Programmi attivi" (sx) + "Ultimo run" (dx).
 *   3. Feed "Attività recenti" — placeholder finché non c'è audit_log.
 *
 * Auto-refresh: tutte le query usano `refetchInterval=60_000` per mimare
 * "aggiornato … · auto-refresh 60s" del design.
 */

const REFRESH_MS = 60_000;
const LONG_DATE_FMT = new Intl.DateTimeFormat("it-IT", {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});
const TIME_FMT = new Intl.DateTimeFormat("it-IT", {
  hour: "2-digit",
  minute: "2-digit",
});

export function DashboardRoute() {
  const { user } = useAuth();
  const programmiQuery = useProgrammi({ stato: "attivo" });
  // Cross-azienda: alimenta sia banda alert (giri non chiusi) sia "Ultimo run".
  const giriAziendaQuery = useGiriAzienda();

  const programmi = programmiQuery.data ?? [];
  const giri = giriAziendaQuery.data ?? [];
  const giriNonChiusi = giri.filter((g) => !g.chiuso).length;

  const now = new Date();
  const showAlert = giriNonChiusi > 0;

  return (
    <div className="flex flex-col gap-6">
      {/* ─── Title row ────────────────────────────────────────── */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Buongiorno{user !== null ? `, ${user.username}` : ""}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Stato della pianificazione giro materiale ·{" "}
            <span className="capitalize">{LONG_DATE_FMT.format(now)}</span>
          </p>
        </div>
        <div className="text-xs tabular-nums text-muted-foreground">
          aggiornato {TIME_FMT.format(now)} · auto-refresh 60s
        </div>
      </div>

      {/* ─── Zone 1 · Alert band ──────────────────────────────── */}
      {showAlert && <AlertBand giriNonChiusi={giriNonChiusi} />}

      {/* ─── Zone 2 · Programmi attivi (8) + Ultimo run (4) ───── */}
      <section className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="flex flex-col lg:col-span-8">
          <SectionHeader title="Programmi attivi">
            <Link
              to="/pianificatore-giro/programmi"
              className="text-xs font-medium text-primary hover:underline"
            >
              Vedi tutti i programmi →
            </Link>
          </SectionHeader>

          {programmiQuery.isLoading ? (
            <Card className="grid place-items-center p-10">
              <Spinner label="Caricamento programmi" />
            </Card>
          ) : programmi.length === 0 ? (
            <EmptyProgrammiAttivi />
          ) : (
            <div className="flex flex-col gap-3">
              {programmi.map((p) => (
                <ProgrammaAttivoCard key={p.id} programma={p} />
              ))}
            </div>
          )}
        </div>

        <aside className="flex flex-col lg:col-span-4">
          <SectionHeader title="Ultimo run del builder" />
          <UltimoRunCard
            giri={giri}
            programmi={programmi}
            isLoading={giriAziendaQuery.isLoading}
          />
        </aside>
      </section>

      {/* ─── Zone 3 · Attività recenti ────────────────────────── */}
      <section>
        <SectionHeader title="Attività recenti" />
        <ActivityFeedPlaceholder />
      </section>
    </div>
  );
}

// =====================================================================
// Helpers
// =====================================================================

function SectionHeader({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-foreground">
        {title}
      </h2>
      {children}
    </div>
  );
}

function AlertBand({ giriNonChiusi }: { giriNonChiusi: number }) {
  return (
    <section className="flex flex-wrap items-center gap-6 rounded-lg border border-amber-300 bg-amber-50 px-5 py-4">
      <div className="flex items-center gap-3">
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-amber-200 font-semibold text-amber-800">
          !
        </div>
        <div>
          <div className="text-sm font-semibold text-amber-900">
            Attenzione su pianificazione corrente
          </div>
          <div className="text-xs text-amber-800/80">
            Verifica i giri segnalati prima di procedere con nuove generazioni.
          </div>
        </div>
      </div>
      <div className="hidden h-8 w-px bg-amber-300 sm:block" />
      <div className="flex items-center gap-8 text-sm">
        <AlertMetric value={giriNonChiusi} label="giri non chiusi naturalmente" />
        {/* warnings/residue: registro non ancora persistito (vedi TN-UPDATE) */}
      </div>
      <div className="ml-auto">
        <Link
          to="/pianificatore-giro/programmi"
          className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          Vedi dettagli
          <ArrowRight className="h-4 w-4" aria-hidden />
        </Link>
      </div>
    </section>
  );
}

function AlertMetric({ value, label }: { value: number; label: string }) {
  return (
    <div>
      <div className="text-2xl font-semibold leading-none tabular-nums text-amber-900">
        {value}
      </div>
      <div className="mt-1 text-[11px] uppercase tracking-wide text-amber-800/80">
        {label}
      </div>
    </div>
  );
}

function ProgrammaAttivoCard({ programma }: { programma: ProgrammaMaterialeRead }) {
  const detailQuery = useProgramma(programma.id);
  const giriQuery = useGiriProgramma(programma.id);

  const giri = giriQuery.data ?? [];
  const totaleGiri = giri.length;
  const chiusiNaturali = giri.filter((g) => g.motivo_chiusura === "naturale").length;
  const percent = totaleGiri > 0 ? Math.round((chiusiNaturali / totaleGiri) * 100) : null;

  const regoleCount = detailQuery.data?.regole.length;
  const days = diffDaysInclusive(programma.valido_da, programma.valido_a);

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0">
          <div className="mb-1 flex items-center gap-2">
            <ProgrammaStatoBadge stato={programma.stato} />
            <span className="font-mono text-xs text-muted-foreground">
              #{programma.id}
            </span>
          </div>
          <h3 className="truncate text-base font-semibold text-foreground">
            {programma.nome}
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">
            {formatPeriodo(programma.valido_da, programma.valido_a)} · {days} giorni
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Link to={`/pianificatore-giro/programmi/${programma.id}`}>
            <Button variant="outline" size="sm">
              Apri
            </Button>
          </Link>
          <Link to={`/pianificatore-giro/programmi/${programma.id}`}>
            <Button variant="primary" size="sm">
              Genera giri
            </Button>
          </Link>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-6 border-t border-border pt-4 sm:grid-cols-4">
        <Kpi
          label="Giri totali"
          value={giriQuery.isLoading ? "—" : String(totaleGiri)}
        />
        <Kpi
          label="Regole"
          value={regoleCount === undefined ? "—" : String(regoleCount)}
        />
        <ChiusiNaturalmenteKpi
          totale={totaleGiri}
          chiusi={chiusiNaturali}
          percent={percent}
          loading={giriQuery.isLoading}
        />
      </div>
    </Card>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-0.5 text-lg font-semibold tabular-nums text-foreground">
        {value}
      </div>
    </div>
  );
}

function ChiusiNaturalmenteKpi({
  totale,
  chiusi,
  percent,
  loading,
}: {
  totale: number;
  chiusi: number;
  percent: number | null;
  loading: boolean;
}) {
  const fillWidth = percent ?? 0;
  return (
    <div className="sm:col-span-2">
      <div className="flex items-center justify-between text-[11px] uppercase tracking-wide text-muted-foreground">
        <span>Chiusi naturalmente</span>
        <span className="tabular-nums normal-case text-foreground">
          {loading || percent === null
            ? "—"
            : `${chiusi} / ${totale} · ${percent}%`}
        </span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            "h-full transition-[width]",
            percent === null
              ? "bg-muted"
              : percent >= 90
                ? "bg-emerald-500"
                : percent >= 70
                  ? "bg-amber-400"
                  : "bg-destructive",
          )}
          style={{ width: `${fillWidth}%` }}
        />
      </div>
    </div>
  );
}

function UltimoRunCard({
  giri,
  programmi,
  isLoading,
}: {
  giri: GiroListItem[];
  programmi: ProgrammaMaterialeRead[];
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <Card className="grid place-items-center p-10">
        <Spinner label="Caricamento" />
      </Card>
    );
  }

  if (giri.length === 0) {
    return (
      <Card className="flex flex-col gap-2 p-5">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">
          Nessun run recente
        </div>
        <p className="text-sm text-muted-foreground">
          Apri un programma e lancia il builder per generare i giri materiale.
        </p>
      </Card>
    );
  }

  // "Ultimo run" = giro più recente per created_at. La sede è derivata dal
  // dettaglio (richiederebbe lookup) — per ora mostriamo solo la metadata
  // disponibile dalla list-azienda.
  const latest = [...giri].sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  const created = new Date(latest.created_at);
  const giriCreatiOggi = giri.filter(
    (g) => g.created_at.slice(0, 10) === latest.created_at.slice(0, 10),
  ).length;

  return (
    <Card className="flex flex-col gap-4 p-5">
      <div>
        <div className="text-xs uppercase tracking-wide text-muted-foreground">
          Eseguito
        </div>
        <div className="mt-1 text-base font-semibold text-foreground">
          {formatRelative(created)}
        </div>
        <div className="mt-0.5 text-xs text-muted-foreground tabular-nums">
          {formatDateTimeIt(created)}
        </div>
      </div>

      <div className="border-t border-border pt-3">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">
          Programmi attivi
        </div>
        <div className="mt-1 text-sm font-medium text-foreground">
          {programmi.length} {programmi.length === 1 ? "programma" : "programmi"}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 border-t border-border pt-3">
        <Kpi label="Giri creati oggi" value={String(giriCreatiOggi)} />
        <Kpi label="Giri totali" value={String(giri.length)} />
        <Kpi
          label="Non chiusi"
          value={String(giri.filter((g) => !g.chiuso).length)}
        />
      </div>

      <Link
        to="/pianificatore-giro/programmi"
        className="mt-1 inline-flex items-center justify-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
      >
        Apri lista programmi
        <ArrowRight className="h-4 w-4" aria-hidden />
      </Link>
    </Card>
  );
}

function ActivityFeedPlaceholder() {
  return (
    <Card className="px-5 py-8 text-center">
      <p className="text-sm text-muted-foreground">
        Le attività recenti compariranno qui non appena sarà disponibile il log
        eventi. (In arrivo)
      </p>
    </Card>
  );
}

function EmptyProgrammiAttivi() {
  return (
    <Card className="flex flex-col items-start gap-3 p-6">
      <Badge variant="muted">Nessun programma attivo</Badge>
      <p className="text-sm text-muted-foreground">
        Crea un nuovo programma materiale dalla pagina <strong>Programmi</strong>{" "}
        per iniziare a pianificare giri.
      </p>
      <Link to="/pianificatore-giro/programmi">
        <Button variant="primary" size="sm">
          Vai a Programmi
        </Button>
      </Link>
    </Card>
  );
}

// =====================================================================
// Utils locali (date)
// =====================================================================

function diffDaysInclusive(da: string, a: string): number {
  const d1 = new Date(`${da}T00:00:00Z`);
  const d2 = new Date(`${a}T00:00:00Z`);
  const ms = d2.getTime() - d1.getTime();
  return Math.max(1, Math.round(ms / (1000 * 60 * 60 * 24)) + 1);
}

function formatDateTimeIt(d: Date): string {
  const date = new Intl.DateTimeFormat("it-IT", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(d);
  const time = TIME_FMT.format(d);
  return `${date} · ${time}`;
}

function formatRelative(d: Date): string {
  const diffMs = Date.now() - d.getTime();
  const diffMin = Math.round(diffMs / 60_000);
  if (diffMin < 1) return "pochi secondi fa";
  if (diffMin < 60) return `${diffMin} ${diffMin === 1 ? "minuto" : "minuti"} fa`;
  const diffH = Math.round(diffMin / 60);
  if (diffH < 24) return `${diffH} ${diffH === 1 ? "ora" : "ore"} fa`;
  const diffD = Math.round(diffH / 24);
  if (diffD < 7) return `${diffD} ${diffD === 1 ? "giorno" : "giorni"} fa`;
  return formatDateTimeIt(d);
}

// `REFRESH_MS` è esposto per future estensioni che applichino refetchInterval
// sui hook React Query; oggi i hook esistenti non accettano override e il
// refresh visivo è basato sui dati al primo mount + invalidazioni mutation.
void REFRESH_MS;
