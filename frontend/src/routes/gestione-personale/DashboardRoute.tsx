import { useMemo } from "react";
import type { CSSProperties } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Plus,
  Upload,
  Workflow,
} from "lucide-react";

import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { useAuth } from "@/lib/auth/AuthContext";
import {
  useGestionePersonaleKpi,
  useGestionePersonaleKpiDepositi,
} from "@/hooks/useGestionePersonale";
import { useProgrammi } from "@/hooks/useProgrammi";
import type { GestionePersonaleKpiPerDepositoRead } from "@/lib/api/gestione-personale";
import type {
  ProgrammaMaterialeRead,
  StatoPipelinePdc,
} from "@/lib/api/programmi";
import { CoverageBand } from "@/routes/gestione-personale/_shared/CoverageBand";
import { EditorialHead, EditorialNum } from "@/routes/gestione-personale/_shared/EditorialHead";
import { useGestionePersonale } from "@/routes/gestione-personale/_shared/GestionePersonaleContext";

/**
 * Sprint 7.10 MR β.1 — Dashboard Gestione Personale (editorial-dense).
 *
 * Layout:
 * 1. Editorial head (eyebrow + h1 grande + lede + cluster azioni)
 * 2. KPI stripe orizzontale: Copertura PdC (largo, con barra+target),
 *    PdC attivi, In servizio, Ferie, Malattia
 * 3. Callout di stato copertura (border-left tinto, sfondo gradient).
 *    Reagisce al `coverageTweak` (verde/giallo/rosso/current)
 * 4. Coverage band: 25 segmenti, uno per deposito → drilldown click
 * 5. Section "Copertura per deposito" → tabella raggruppata per
 *    criticità (sotto target / a target / vuoti). Ogni riga apre il
 *    drilldown deposito (Gantt 7gg)
 * 6. Note keyboard shortcuts in footer
 */

const TARGET_PCT = 95;

type Tone = "ok" | "warn" | "bad";

const TONE_COLORS: Record<Tone, { color: string; bg: string }> = {
  ok: { color: "#1F8A4C", bg: "rgba(31, 138, 76, 0.10)" },
  warn: { color: "#C76A12", bg: "rgba(199, 106, 18, 0.10)" },
  bad: { color: "#B33636", bg: "rgba(179, 54, 54, 0.10)" },
};

function toneOf(pct: number): Tone {
  if (pct >= TARGET_PCT) return "ok";
  if (pct >= 71) return "warn";
  return "bad";
}

export function GestionePersonaleDashboardRoute() {
  const { user } = useAuth();
  const kpi = useGestionePersonaleKpi();
  const kpiDepositi = useGestionePersonaleKpiDepositi();
  const { coverageOverridePct, coverageOverrideTone, openDepositoDrilldown } =
    useGestionePersonale();

  const data = kpi.data;
  const realPct = data?.copertura_pct ?? 0;

  // Quando il tweak è attivo, sostituisce % e tono per stripe + callout.
  const displayedPct = coverageOverridePct ?? realPct;
  const tone = coverageOverrideTone ?? toneOf(realPct);
  const palette = TONE_COLORS[tone];

  // Counters per il callout.
  const depositi = kpiDepositi.data ?? [];
  const counts = useMemo(() => {
    const c = { ok: 0, warn: 0, bad: 0, vuoti: 0, totale: depositi.length };
    for (const d of depositi) {
      if (d.persone_attive === 0) c.vuoti += 1;
      else c[toneOf(d.copertura_pct)] += 1;
    }
    return c;
  }, [depositi]);

  // Inline CSS variables propagate to descendants under `.gp-page`.
  const pageStyle: CSSProperties = {
    "--gp-cov": palette.color,
    "--gp-cov-bg": palette.bg,
    "--gp-cov-pct": displayedPct,
  } as CSSProperties;

  return (
    <section className="gp-page" style={pageStyle}>
      <EditorialHead
        eyebrow={`Gestione personale · ${new Date().toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" })}`}
        title={
          <>
            Dashboard PdC
            <EditorialNum>azienda #{user?.azienda_id ?? "—"}</EditorialNum>
          </>
        }
        lede={
          <>
            Benvenuto{user !== null ? `, ${user.username}` : ""}. Stato in tempo reale di anagrafica,
            depositi, copertura turni e indisponibilità. Coordini con i Pianificatori PdC le
            sostituzioni quando la copertura scende sotto il target del{" "}
            <b>{TARGET_PCT}%</b>.
          </>
        }
        actions={
          <>
            <button type="button" className="gp-action-btn gp-action-btn-line">
              <Upload className="h-3.5 w-3.5" aria-hidden /> Esporta stato
            </button>
            <Link
              to="/gestione-personale/indisponibilita"
              className="gp-action-btn gp-action-btn-ink"
            >
              <Plus className="h-3.5 w-3.5" aria-hidden /> Apri indisponibilità
            </Link>
          </>
        }
      />

      {/* PIPELINE PROGRAMMI (Sprint 8.0 MR 2, entry 167) */}
      <PipelineProgrammiSection />

      {/* KPI STRIPE — orizzontale, monospaziata, una sola riga. */}
      <div
        className="gp-stripe"
        style={{
          gridTemplateColumns: "1.6fr 0.9fr 0.7fr 0.7fr 0.7fr",
        }}
      >
        <div className="gp-stripe-cell" style={{ paddingRight: 24, gridColumn: "1 / span 1" }}>
          <div className="gp-stripe-k">Copertura PdC · oggi</div>
          <div className="gp-stripe-v" style={{ color: palette.color }}>
            {kpi.isLoading ? "…" : kpi.isError ? "—" : displayedPct.toFixed(1)}
            <small>%</small>
            {coverageOverrideTone !== null && (
              <span style={{ marginLeft: 8, fontSize: 10.5, color: "var(--gp-ink-3)" }}>
                ⌃ tweak attivo
              </span>
            )}
          </div>
          <div className="gp-stripe-cov-bar">
            <div className="gp-stripe-cov-fill" />
            <div className="gp-stripe-cov-target" />
          </div>
          <div className="gp-stripe-scale">
            <span>0%</span>
            <span>50%</span>
            <span className="gp-target-lbl">{TARGET_PCT}% target</span>
            <span>100%</span>
          </div>
        </div>
        <KpiCell
          label="PdC attivi"
          value={data?.persone_attive}
          loading={kpi.isLoading}
          error={kpi.isError}
          meta="matricole in azienda"
        />
        <KpiCell
          label="In servizio"
          value={data?.in_servizio_oggi}
          loading={kpi.isLoading}
          error={kpi.isError}
          meta={
            data !== undefined && data.persone_attive > 0
              ? `${realPct.toFixed(1)}% del totale`
              : ""
          }
        />
        <KpiCell
          label="Ferie"
          value={data?.in_ferie}
          loading={kpi.isLoading}
          error={kpi.isError}
          meta="approvate, in corso"
        />
        <KpiCell
          label="Malattia"
          value={data?.in_malattia}
          loading={kpi.isLoading}
          error={kpi.isError}
          meta="certificate oggi"
        />
      </div>

      {/* CALLOUT (sostituisce banner giallo). Reagisce al tono di copertura. */}
      <CalloutBlock
        tone={tone}
        displayedPct={displayedPct}
        counts={counts}
        loading={kpi.isLoading}
      />

      {/* COVERAGE BAND — la metafora del deposito (25 segmenti). */}
      {kpiDepositi.isLoading ? (
        <div className="flex items-center justify-center py-8">
          <Spinner label="Caricamento depositi…" />
        </div>
      ) : kpiDepositi.isError ? (
        <p className="rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive" role="alert">
          Errore caricamento depositi: {kpiDepositi.error?.message ?? "errore sconosciuto"}
        </p>
      ) : depositi.length > 0 ? (
        <CoverageBand
          depots={depositi}
          mediaPct={realPct}
          onDepotClick={(codice) => {
            const d = depositi.find((x) => x.depot_codice === codice);
            if (d !== undefined) {
              openDepositoDrilldown({
                codice: d.depot_codice,
                display_name: d.depot_display_name,
                copertura_pct: d.copertura_pct,
                persone_attive: d.persone_attive,
              });
            }
          }}
        />
      ) : null}

      {/* SECTION: Copertura per deposito (tabella raggruppata) */}
      <div className="gp-section">
        <div className="gp-section-head">
          <h2 className="gp-section-title">
            Copertura per deposito
            <span className="gp-num">
              {depositi.length} {depositi.length === 1 ? "deposito" : "depositi"} · ord. criticità
            </span>
          </h2>
          <div className="gp-section-meta">
            <Link to="/gestione-personale/depositi" className="hover:text-[color:var(--gp-ink)]" style={{ color: "var(--gp-ink-3)" }}>
              Apri elenco completo →
            </Link>
          </div>
        </div>

        {kpiDepositi.isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Spinner label="Caricamento depositi…" />
          </div>
        ) : depositi.length === 0 ? (
          <div className="py-12 text-center text-sm text-muted-foreground">
            Nessun deposito caricato.
          </div>
        ) : (
          <DepositiGroupedTable
            depositi={depositi}
            onRowClick={(d) =>
              openDepositoDrilldown({
                codice: d.depot_codice,
                display_name: d.depot_display_name,
                copertura_pct: d.copertura_pct,
                persone_attive: d.persone_attive,
              })
            }
          />
        )}

        <div
          style={{
            fontSize: 11.5,
            color: "var(--gp-ink-4)",
            marginTop: 14,
            display: "flex",
            gap: 24,
            flexWrap: "wrap",
          }}
        >
          <span>
            <span className="gp-toolbar-kbd">⌘K</span> apri palette
          </span>
          <span>
            <span className="gp-toolbar-kbd">↵</span> apri deposito
          </span>
          <span>
            <span className="gp-toolbar-kbd">F</span> filtra solo critici
          </span>
        </div>
      </div>
    </section>
  );
}

interface KpiCellProps {
  label: string;
  value: number | undefined;
  loading: boolean;
  error: boolean;
  meta: string;
}

function KpiCell({ label, value, loading, error, meta }: KpiCellProps) {
  const display = loading ? "…" : error ? "—" : String(value ?? 0);
  return (
    <div className="gp-stripe-cell">
      <div className="gp-stripe-k">{label}</div>
      <div className="gp-stripe-v">{display}</div>
      <div className="gp-stripe-meta">{meta}</div>
    </div>
  );
}

interface CalloutProps {
  tone: Tone;
  displayedPct: number;
  counts: { ok: number; warn: number; bad: number; vuoti: number; totale: number };
  loading: boolean;
}

function CalloutBlock({ tone, displayedPct, counts, loading }: CalloutProps) {
  const titles: Record<Tone, string> = {
    ok: "Copertura ottima — sopra il target",
    warn: "Copertura sotto target",
    bad: "Copertura critica",
  };
  const desc =
    tone === "ok" ? (
      <>
        Tutti i depositi tengono il target del {TARGET_PCT}%.{" "}
        <b>{counts.ok}</b> a target, <b>{counts.warn}</b> warning, <b>{counts.bad}</b> critici.
      </>
    ) : tone === "warn" ? (
      <>
        <b>{counts.bad}</b> depositi sono in stato <b>critico</b> (≤ 70%) e altri{" "}
        <b>{counts.warn}</b> in <b>warning</b>. Coordina con i Pianificatori PdC per riassegnare
        turni o approvare straordinari.
      </>
    ) : (
      <>
        <b>{counts.bad}</b> depositi sono in stato <b>critico</b> (≤ 70%). Ferie/malattie superano
        la soglia. Verifica i depositi più colpiti via drilldown.
      </>
    );

  const titleSuffix = loading
    ? ""
    : ` — ${displayedPct.toFixed(1)}% (${(TARGET_PCT - displayedPct).toFixed(1)} pt sotto al ${TARGET_PCT}%)`;

  return (
    <div className="gp-callout" role={tone === "bad" ? "alert" : undefined}>
      <div className="gp-callout-ic">
        <AlertTriangle className="h-5 w-5" aria-hidden />
      </div>
      <div className="gp-callout-body">
        <div className="gp-callout-title">
          {titles[tone]}
          {tone !== "ok" && titleSuffix}
        </div>
        <div className="gp-callout-desc">{desc}</div>
      </div>
      <div className="gp-callout-cta">
        <Link
          to="/pianificatore-pdc/dashboard"
          className="gp-action-btn gp-action-btn-line"
        >
          Apri Pianificatore PdC <ChevronRight className="h-3 w-3" aria-hidden />
        </Link>
      </div>
    </div>
  );
}

interface DepositiTableProps {
  depositi: GestionePersonaleKpiPerDepositoRead[];
  onRowClick: (d: GestionePersonaleKpiPerDepositoRead) => void;
}

function DepositiGroupedTable({ depositi, onRowClick }: DepositiTableProps) {
  const sorted = useMemo(
    () => [...depositi].sort((a, b) => a.copertura_pct - b.copertura_pct),
    [depositi],
  );
  const sottoTarget = sorted.filter((d) => d.persone_attive > 0 && d.copertura_pct < TARGET_PCT);
  const aTarget = sorted.filter((d) => d.persone_attive > 0 && d.copertura_pct >= TARGET_PCT);
  const vuoti = sorted.filter((d) => d.persone_attive === 0);

  let runningIdx = 0;

  return (
    <table className="gp-tbl">
      <colgroup>
        <col style={{ width: 36 }} />
        <col style={{ width: 160 }} />
        <col />
        <col style={{ width: 60 }} />
        <col style={{ width: 60 }} />
        <col style={{ width: 60 }} />
        <col style={{ width: 280 }} />
        <col style={{ width: 14 }} />
      </colgroup>
      <thead>
        <tr>
          <th>#</th>
          <th>Codice</th>
          <th>Nome esteso</th>
          <th className="gp-num">PdC</th>
          <th className="gp-num">Serv.</th>
          <th className="gp-num">Ass.</th>
          <th className="gp-num">Copertura</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {sottoTarget.length > 0 && (
          <tr className="gp-tbl-group">
            <td colSpan={8}>
              ▾ Sotto target · {sottoTarget.length} {sottoTarget.length === 1 ? "deposito" : "depositi"}
              <span className="gp-count">richiede attenzione</span>
            </td>
          </tr>
        )}
        {sottoTarget.map((d) => (
          <DepositiRow
            key={d.depot_codice}
            d={d}
            idx={(runningIdx += 1)}
            onClick={() => onRowClick(d)}
          />
        ))}

        {aTarget.length > 0 && (
          <tr className="gp-tbl-group">
            <td colSpan={8}>
              ▾ A target · {aTarget.length} {aTarget.length === 1 ? "deposito" : "depositi"}
              <span className="gp-count">≥ {TARGET_PCT}% copertura</span>
            </td>
          </tr>
        )}
        {aTarget.map((d) => (
          <DepositiRow
            key={d.depot_codice}
            d={d}
            idx={(runningIdx += 1)}
            onClick={() => onRowClick(d)}
          />
        ))}

        {vuoti.length > 0 && (
          <tr className="gp-tbl-group">
            <td colSpan={8}>
              ▾ Vuoti · {vuoti.length} {vuoti.length === 1 ? "deposito" : "depositi"}
              <span className="gp-count">nessun PdC residente</span>
            </td>
          </tr>
        )}
        {vuoti.map((d) => (
          <DepositiRow
            key={d.depot_codice}
            d={d}
            idx={(runningIdx += 1)}
            onClick={() => onRowClick(d)}
          />
        ))}
      </tbody>
    </table>
  );
}

function DepositiRow({
  d,
  idx,
  onClick,
}: {
  d: GestionePersonaleKpiPerDepositoRead;
  idx: number;
  onClick: () => void;
}) {
  const tone: Tone | null = d.persone_attive === 0 ? null : toneOf(d.copertura_pct);
  const palette = tone !== null ? TONE_COLORS[tone] : null;
  return (
    <tr onClick={onClick} aria-label={`Apri drilldown deposito ${d.depot_codice}`}>
      <td className="gp-idx">{String(idx).padStart(2, "0")}</td>
      <td>
        <span className="gp-cell-code">{d.depot_codice}</span>
      </td>
      <td>
        <div className="gp-cell-name">{d.depot_display_name}</div>
      </td>
      <td className="gp-num">{d.persone_attive}</td>
      <td className="gp-num">{d.persone_attive > 0 ? d.in_servizio_oggi : "—"}</td>
      <td className="gp-num">{d.persone_attive > 0 ? d.indisponibili_oggi : "—"}</td>
      <td>
        {tone === null || palette === null ? (
          <span style={{ color: "var(--gp-ink-5)", fontSize: 11.5 }}>—</span>
        ) : (
          <div className="gp-cov-cell">
            <div className="gp-cov-cell-vis">
              <div
                className="gp-cov-cell-fill"
                style={{ width: `${d.copertura_pct}%`, background: palette.color }}
              />
              <div className="gp-cov-cell-target" />
            </div>
            <span className={`gp-cov-cell-pct gp-is-${tone === "ok" ? "ok" : tone === "warn" ? "warn" : "bad"}`}>
              {d.copertura_pct.toFixed(1)}%
            </span>
          </div>
        )}
      </td>
      <td className="gp-num">
        <ChevronRight style={{ color: "var(--gp-ink-5)", height: 14, width: 14 }} aria-hidden />
      </td>
    </tr>
  );
}

// =====================================================================
// Pipeline programmi — vista GESTIONE_PERSONALE (Sprint 8.0 MR 2)
// =====================================================================
//
// Lista programmi visibili a GESTIONE_PERSONALE (filter list-route MR 0
// = ``>= PDC_CONFERMATO``). Per scope MR 2 è una vista informativa:
// l'azione "Conferma assegnazioni personale" entrerà nel flusso UI in
// MR 2.bis (algoritmo assegnazione + delta% mancanze) o MR 3.

const PIPELINE_PERSONALE_LABEL: Record<StatoPipelinePdc, string> = {
  PDE_IN_LAVORAZIONE: "PdE in lavorazione",
  PDE_CONSOLIDATO: "PdE consolidato",
  MATERIALE_GENERATO: "Materiale generato",
  MATERIALE_CONFERMATO: "Materiale confermato",
  PDC_GENERATO: "PdC generato",
  PDC_CONFERMATO: "PdC confermato — pronto per assegnazione",
  PERSONALE_ASSEGNATO: "Personale assegnato",
  VISTA_PUBBLICATA: "Vista pubblicata al personale",
};

function PipelineProgrammiSection() {
  const programmiQuery = useProgrammi();
  const programmi = useMemo(() => {
    const data = programmiQuery.data;
    return Array.isArray(data) ? data : [];
  }, [programmiQuery.data]);

  if (programmiQuery.isLoading) {
    return (
      <Card className="flex items-center justify-center p-3">
        <Spinner label="Caricamento programmi…" />
      </Card>
    );
  }
  if (programmi.length === 0) {
    return (
      <Card className="border-border bg-muted/30 p-3 text-sm text-muted-foreground">
        Nessun programma con turni PdC confermati. Aspetta che il
        Pianificatore PdC confermi i turni di un programma.
      </Card>
    );
  }

  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-baseline gap-2">
        <Workflow className="h-4 w-4 text-primary" aria-hidden />
        <h2 className="text-sm font-semibold uppercase tracking-wide text-foreground">
          Pipeline programmi
        </h2>
        <span className="text-xs text-muted-foreground">
          {programmi.length} programmi pronti per assegnazione personale
        </span>
      </div>
      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {programmi.map((p) => (
          <PersonalePipelineCard key={p.id} programma={p} />
        ))}
      </div>
    </section>
  );
}

function PersonalePipelineCard({
  programma,
}: {
  programma: ProgrammaMaterialeRead;
}) {
  const stato = programma.stato_pipeline_pdc;
  const isPubblicato = stato === "VISTA_PUBBLICATA";
  return (
    <Card
      className={cnGp(
        "flex items-center justify-between gap-3 p-3",
        stato === "PDC_CONFERMATO" && "border-blue-300 bg-blue-50",
        isPubblicato && "border-emerald-300 bg-emerald-50",
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold truncate text-foreground">
          {programma.nome}
        </div>
        <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
          {PIPELINE_PERSONALE_LABEL[stato]}
        </div>
      </div>
      {isPubblicato ? (
        <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" aria-hidden />
      ) : null}
    </Card>
  );
}

function cnGp(...classes: Array<string | false | undefined | null>): string {
  return classes.filter(Boolean).join(" ");
}
