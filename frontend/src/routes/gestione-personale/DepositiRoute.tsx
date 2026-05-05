import { useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { ChevronDown, ChevronRight, MapPin, Search, Upload } from "lucide-react";

import { Spinner } from "@/components/ui/Spinner";
import { useDepots } from "@/hooks/useAnagrafiche";
import { useGestionePersonaleKpiDepositi } from "@/hooks/useGestionePersonale";
import { ApiError } from "@/lib/api/client";
import { EditorialHead, EditorialNum } from "@/routes/gestione-personale/_shared/EditorialHead";
import { useGestionePersonale } from "@/routes/gestione-personale/_shared/GestionePersonaleContext";

/**
 * Sprint 7.10 MR β.1 — Depositi PdC (Gestione Personale, editorial).
 *
 * Layout:
 * 1. Editorial head + actions (Esporta + Vista mappa)
 * 2. Stripe summary: Copertura media (con barra+target) + Critici +
 *    Warning + A target + PdC totali
 * 3. Toolbar: search + sort + only-under-target toggle
 * 4. Header riga mono uppercase
 * 5. Grouped table per criticità → click apre drilldown deposito
 *    (Gantt 7gg con T1/T2/T3 mock)
 */

type Tone = "ok" | "warn" | "bad";

const TARGET_PCT = 95;

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

interface DepotMerged {
  codice: string;
  display_name: string;
  attivi: number;
  in_servizio: number;
  ind_oggi: number;
  copertura_pct: number;
}

type SortKey = "criticita" | "nome" | "pdc";

const SORT_LABELS: Record<SortKey, string> = {
  criticita: "Criticità ↓",
  nome: "Nome A-Z",
  pdc: "PdC ↓",
};

export function GestionePersonaleDepositiRoute() {
  const depotsQuery = useDepots();
  const kpi = useGestionePersonaleKpiDepositi();
  const { coverageOverridePct, coverageOverrideTone, openDepositoDrilldown } =
    useGestionePersonale();

  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("criticita");
  const [onlyUnderTarget, setOnlyUnderTarget] = useState(false);
  const [openMenu, setOpenMenu] = useState<"sort" | "filter" | null>(null);

  const merged = useMemo<DepotMerged[]>(() => {
    const kpiByCodice = new Map(
      (kpi.data ?? []).map((k) => [k.depot_codice, k] as const),
    );
    return (depotsQuery.data ?? []).map((d) => {
      const k = kpiByCodice.get(d.codice);
      return {
        codice: d.codice,
        display_name: d.display_name,
        attivi: k?.persone_attive ?? 0,
        in_servizio: k?.in_servizio_oggi ?? 0,
        ind_oggi: k?.indisponibili_oggi ?? 0,
        copertura_pct: k?.copertura_pct ?? 0,
      };
    });
  }, [depotsQuery.data, kpi.data]);

  const filteredAndSorted = useMemo(() => {
    let list = merged;
    if (search.trim().length > 0) {
      const q = search.trim().toLowerCase();
      list = list.filter(
        (d) =>
          d.codice.toLowerCase().includes(q) ||
          d.display_name.toLowerCase().includes(q),
      );
    }
    if (onlyUnderTarget) {
      list = list.filter((d) => d.attivi > 0 && d.copertura_pct < TARGET_PCT);
    }
    if (sortBy === "criticita") {
      list = [...list].sort((a, b) => {
        // Vuoti in fondo
        if (a.attivi === 0 && b.attivi === 0) return a.codice.localeCompare(b.codice);
        if (a.attivi === 0) return 1;
        if (b.attivi === 0) return -1;
        return a.copertura_pct - b.copertura_pct;
      });
    } else if (sortBy === "nome") {
      list = [...list].sort((a, b) => a.codice.localeCompare(b.codice));
    } else if (sortBy === "pdc") {
      list = [...list].sort((a, b) => b.attivi - a.attivi);
    }
    return list;
  }, [merged, search, onlyUnderTarget, sortBy]);

  // Counters globali per stripe (dai dati reali, non filtrati).
  const counters = useMemo(() => {
    const c = { critici: 0, warn: 0, ok: 0, vuoti: 0, totalePdc: 0 };
    for (const d of merged) {
      c.totalePdc += d.attivi;
      if (d.attivi === 0) c.vuoti += 1;
      else c[toneOf(d.copertura_pct) === "bad" ? "critici" : toneOf(d.copertura_pct) === "warn" ? "warn" : "ok"] += 1;
    }
    return c;
  }, [merged]);

  // Media reale = somma copertura / # depositi con almeno 1 PdC.
  const realMediaPct = useMemo(() => {
    const conPersone = merged.filter((d) => d.attivi > 0);
    if (conPersone.length === 0) return 0;
    return conPersone.reduce((s, d) => s + d.copertura_pct, 0) / conPersone.length;
  }, [merged]);

  const displayedPct = coverageOverridePct ?? realMediaPct;
  const tone = coverageOverrideTone ?? toneOf(realMediaPct);
  const palette = TONE_COLORS[tone];

  const pageStyle: CSSProperties = {
    "--gp-cov": palette.color,
    "--gp-cov-bg": palette.bg,
    "--gp-cov-pct": displayedPct,
  } as CSSProperties;

  return (
    <section className="gp-page" style={pageStyle} onClick={() => setOpenMenu(null)}>
      <EditorialHead
        eyebrow="Gestione personale · Depositi"
        title={
          <>
            Depositi PdC Trenord
            <EditorialNum>{merged.length}</EditorialNum>
          </>
        }
        lede={
          <>
            Anagrafica depositi del personale di macchina con conta PdC assegnati e copertura
            giornaliera. Click su un deposito per il drilldown Gantt 7 giorni.
          </>
        }
        actions={
          <>
            <button type="button" className="gp-action-btn gp-action-btn-line">
              <Upload className="h-3.5 w-3.5" aria-hidden /> Esporta
            </button>
            <button type="button" className="gp-action-btn gp-action-btn-ink">
              <MapPin className="h-3.5 w-3.5" aria-hidden /> Vista mappa
            </button>
          </>
        }
      />

      {/* Stripe summary (5 colonne). */}
      <div
        className="gp-stripe"
        style={{
          gridTemplateColumns: "1.4fr 0.7fr 0.7fr 0.7fr 0.7fr",
        }}
      >
        <div className="gp-stripe-cell" style={{ paddingRight: 24 }}>
          <div className="gp-stripe-k">Copertura media · {merged.length} depositi</div>
          <div className="gp-stripe-v" style={{ color: palette.color }}>
            {kpi.isLoading ? "…" : kpi.isError ? "—" : displayedPct.toFixed(1)}
            <small>%</small>
          </div>
          <div className="gp-stripe-cov-bar">
            <div className="gp-stripe-cov-fill" />
            <div className="gp-stripe-cov-target" />
          </div>
          <div className="gp-stripe-scale">
            <span>0%</span>
            <span>target {TARGET_PCT}%</span>
            <span>100%</span>
          </div>
        </div>
        <div className="gp-stripe-cell">
          <div className="gp-stripe-k">Critici</div>
          <div className="gp-stripe-v" style={{ color: TONE_COLORS.bad.color }}>
            {counters.critici}
          </div>
          <div className="gp-stripe-meta">≤ 70%</div>
        </div>
        <div className="gp-stripe-cell">
          <div className="gp-stripe-k">Warning</div>
          <div className="gp-stripe-v" style={{ color: TONE_COLORS.warn.color }}>
            {counters.warn}
          </div>
          <div className="gp-stripe-meta">71-94%</div>
        </div>
        <div className="gp-stripe-cell">
          <div className="gp-stripe-k">A target</div>
          <div className="gp-stripe-v" style={{ color: TONE_COLORS.ok.color }}>
            {counters.ok}
          </div>
          <div className="gp-stripe-meta">≥ {TARGET_PCT}%</div>
        </div>
        <div className="gp-stripe-cell">
          <div className="gp-stripe-k">PdC totali</div>
          <div className="gp-stripe-v">{counters.totalePdc}</div>
          <div className="gp-stripe-meta">distribuiti</div>
        </div>
      </div>

      {/* Toolbar */}
      <div className="gp-toolbar" onClick={(e) => e.stopPropagation()}>
        <div className="gp-toolbar-search">
          <Search className="h-4 w-4 shrink-0" style={{ color: "var(--gp-ink-4)" }} aria-hidden />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Cerca deposito per codice o nome…"
            aria-label="Cerca depositi"
          />
        </div>

        <div style={{ position: "relative" }}>
          <button
            type="button"
            className="gp-select-pill"
            onClick={(e) => {
              e.stopPropagation();
              setOpenMenu(openMenu === "sort" ? null : "sort");
            }}
            aria-haspopup="menu"
            aria-expanded={openMenu === "sort"}
          >
            Ordine: {SORT_LABELS[sortBy]}
            <ChevronDown className="h-3 w-3" aria-hidden />
          </button>
          {openMenu === "sort" && (
            <div
              style={{
                position: "absolute",
                top: "calc(100% + 4px)",
                left: 0,
                zIndex: 20,
                background: "var(--gp-bg-elev)",
                border: "1px solid var(--gp-line-2)",
                borderRadius: 6,
                boxShadow: "0 12px 24px -4px rgba(14,17,22,0.18)",
                minWidth: 180,
                padding: 4,
              }}
              onClick={(e) => e.stopPropagation()}
            >
              {(Object.keys(SORT_LABELS) as SortKey[]).map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => {
                    setSortBy(k);
                    setOpenMenu(null);
                  }}
                  style={{
                    display: "flex",
                    width: "100%",
                    textAlign: "left",
                    padding: "8px 10px",
                    fontSize: 12.5,
                    background: sortBy === k ? "rgba(0,98,204,0.08)" : "transparent",
                    color: sortBy === k ? "#0062CC" : "var(--gp-ink-2)",
                    border: 0,
                    borderRadius: 4,
                    cursor: "pointer",
                    fontFamily: "inherit",
                    fontWeight: sortBy === k ? 600 : 500,
                  }}
                >
                  {SORT_LABELS[k]}
                </button>
              ))}
            </div>
          )}
        </div>

        <button
          type="button"
          className={`gp-select-pill ${onlyUnderTarget ? "gp-is-on" : ""}`}
          style={
            onlyUnderTarget
              ? { background: "rgba(0,98,204,0.08)", color: "#0062CC", borderColor: "rgba(0,98,204,0.3)" }
              : undefined
          }
          onClick={() => setOnlyUnderTarget(!onlyUnderTarget)}
          aria-pressed={onlyUnderTarget}
        >
          {onlyUnderTarget ? "✓ Solo sotto target" : "Solo sotto target"}
        </button>
      </div>

      {/* Header riga */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "36px 200px 1fr 60px 60px 220px 14px",
          gap: 18,
          padding: "14px 0 10px",
          borderBottom: "1px solid var(--gp-line-2)",
          fontSize: 9.5,
          fontWeight: 600,
          letterSpacing: ".08em",
          textTransform: "uppercase",
          color: "var(--gp-ink-4)",
        }}
      >
        <span>#</span>
        <span>Codice</span>
        <span>Nome esteso</span>
        <span style={{ textAlign: "right" }}>PdC</span>
        <span style={{ textAlign: "right" }}>Serv.</span>
        <span style={{ textAlign: "right" }}>Copertura</span>
        <span />
      </div>

      {depotsQuery.isLoading || kpi.isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Spinner label="Caricamento depositi…" />
        </div>
      ) : depotsQuery.isError ? (
        <p
          role="alert"
          className="rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
        >
          Errore caricamento depositi:{" "}
          {depotsQuery.error instanceof ApiError
            ? depotsQuery.error.message
            : (depotsQuery.error as Error).message}
        </p>
      ) : filteredAndSorted.length === 0 ? (
        <div
          style={{
            padding: "48px 24px",
            textAlign: "center",
            color: "var(--gp-ink-4)",
            fontSize: 13,
            border: "1px dashed var(--gp-line-2)",
            borderRadius: 8,
            marginTop: 16,
          }}
        >
          Nessun deposito corrisponde ai filtri selezionati.
        </div>
      ) : (
        <DepotList depots={filteredAndSorted} onClick={openDepositoDrilldown} />
      )}

      <div
        style={{
          marginTop: 18,
          padding: "10px 12px",
          borderRadius: 6,
          background: "var(--gp-bg-rule)",
          fontSize: 11,
          color: "var(--gp-ink-4)",
          lineHeight: 1.5,
        }}
      >
        Anagrafica caricata da <code>/api/depots</code> · seed Trenord (NORMATIVA-PDC §2.1) — KPI
        da <code>/api/gestione-personale/kpi-depositi</code>.
      </div>
    </section>
  );
}

interface DepotListProps {
  depots: DepotMerged[];
  onClick: (payload: { codice: string; display_name: string; copertura_pct: number; persone_attive: number }) => void;
}

function DepotList({ depots, onClick }: DepotListProps) {
  // Group by criticità per visual chunking — ma solo se sortBy=criticita.
  // Qui rendiamo sempre come una lista flat con group rows informativi
  // calcolati on the fly.
  const sottoTarget = depots.filter((d) => d.attivi > 0 && d.copertura_pct < TARGET_PCT);
  const aTarget = depots.filter((d) => d.attivi > 0 && d.copertura_pct >= TARGET_PCT);
  const vuoti = depots.filter((d) => d.attivi === 0);

  let runningIdx = 0;
  return (
    <div>
      {sottoTarget.length > 0 && (
        <GroupHeader
          label="Sotto target"
          count={sottoTarget.length}
          hint="richiede attenzione"
        />
      )}
      {sottoTarget.map((d) => (
        <DepotRow
          key={d.codice}
          d={d}
          idx={(runningIdx += 1)}
          onClick={() => onClick(toPayload(d))}
        />
      ))}

      {aTarget.length > 0 && (
        <GroupHeader
          label="A target"
          count={aTarget.length}
          hint={`≥ ${TARGET_PCT}% copertura`}
        />
      )}
      {aTarget.map((d) => (
        <DepotRow
          key={d.codice}
          d={d}
          idx={(runningIdx += 1)}
          onClick={() => onClick(toPayload(d))}
        />
      ))}

      {vuoti.length > 0 && (
        <GroupHeader label="Vuoti" count={vuoti.length} hint="nessun PdC residente" />
      )}
      {vuoti.map((d) => (
        <DepotRow
          key={d.codice}
          d={d}
          idx={(runningIdx += 1)}
          onClick={() => onClick(toPayload(d))}
        />
      ))}
    </div>
  );
}

function toPayload(d: DepotMerged) {
  return {
    codice: d.codice,
    display_name: d.display_name,
    copertura_pct: d.copertura_pct,
    persone_attive: d.attivi,
  };
}

function GroupHeader({
  label,
  count,
  hint,
}: {
  label: string;
  count: number;
  hint: string;
}) {
  return (
    <div
      style={{
        padding: "12px 0 10px",
        marginTop: 8,
        fontSize: 9.5,
        fontWeight: 700,
        letterSpacing: ".1em",
        textTransform: "uppercase",
        color: "var(--gp-ink-3)",
      }}
    >
      ▾ {label} · {count} {count === 1 ? "deposito" : "depositi"}
      <span style={{ color: "var(--gp-ink-4)", fontWeight: 500, marginLeft: 8 }}>{hint}</span>
    </div>
  );
}

function DepotRow({
  d,
  idx,
  onClick,
}: {
  d: DepotMerged;
  idx: number;
  onClick: () => void;
}) {
  const tone: Tone | null = d.attivi === 0 ? null : toneOf(d.copertura_pct);
  const color = tone === null ? null : TONE_COLORS[tone].color;
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      style={{
        display: "grid",
        gridTemplateColumns: "36px 200px 1fr 60px 60px 220px 14px",
        alignItems: "center",
        gap: 18,
        padding: "14px 0",
        borderBottom: "1px solid var(--gp-line)",
        cursor: "pointer",
        transition: "background 0.08s",
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "var(--gp-bg-rule)")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
      aria-label={`Apri drilldown deposito ${d.codice}`}
    >
      <span
        style={{
          fontSize: 11,
          color: "var(--gp-ink-5)",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {String(idx).padStart(2, "0")}
      </span>
      <span
        style={{
          fontSize: 13,
          fontWeight: 700,
          color: "var(--gp-ink)",
          letterSpacing: ".01em",
          display: "flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        {d.codice}
        <span
          aria-hidden
          style={{
            width: 4,
            height: 4,
            borderRadius: "50%",
            background: "#0062CC",
            display: "inline-block",
          }}
        />
      </span>
      <span style={{ fontSize: 13, color: "var(--gp-ink-3)" }}>{d.display_name}</span>
      <span
        style={{
          textAlign: "right",
          fontSize: 12.5,
          color: "var(--gp-ink-2)",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {d.attivi > 0 ? d.attivi : "—"}
      </span>
      <span
        style={{
          textAlign: "right",
          fontSize: 12.5,
          color: "var(--gp-ink-2)",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {d.attivi > 0 ? d.in_servizio : "—"}
      </span>
      <span>
        {tone === null || color === null ? (
          <span style={{ color: "var(--gp-ink-5)", fontSize: 11.5, textAlign: "right", display: "block" }}>
            vuoto
          </span>
        ) : (
          <div className="gp-cov-cell">
            <div className="gp-cov-cell-vis">
              <div
                className="gp-cov-cell-fill"
                style={{ width: `${d.copertura_pct}%`, background: color }}
              />
              <div className="gp-cov-cell-target" />
            </div>
            <span className={`gp-cov-cell-pct gp-is-${tone === "ok" ? "ok" : tone === "warn" ? "warn" : "bad"}`}>
              {d.copertura_pct.toFixed(1)}%
            </span>
          </div>
        )}
      </span>
      <span style={{ textAlign: "right" }}>
        <ChevronRight style={{ color: "var(--gp-ink-5)", height: 14, width: 14 }} aria-hidden />
      </span>
    </div>
  );
}
