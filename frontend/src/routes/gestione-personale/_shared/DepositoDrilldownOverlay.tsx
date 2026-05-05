import { useMemo } from "react";
import { Link } from "react-router-dom";
import { Plus, Route as RouteIcon, Upload, X } from "lucide-react";

import { usePersoneByDepot } from "@/hooks/useGestionePersonale";
import type { PersonaWithDepositoRead } from "@/lib/api/gestione-personale";

import { useGestionePersonale } from "./GestionePersonaleContext";

/**
 * Sprint 7.10 MR β.1 — Drilldown deposito: overlay laterale che mostra
 * il Gantt 7gg dei PdC del deposito, aperto da click su una riga
 * deposito (sia in Dashboard che in Lista Depositi).
 *
 * **Dati**: i PdC sono **reali** (`usePersoneByDepot`), così l'overlay
 * mostra cognomi+matricole+anzianità reali del deposito. **I turni
 * T1/T2/T3 sono mock**: il data model attuale di Gestione Personale
 * non ha turni assegnati alle persone (quelli arrivano dal builder
 * Pianificatore PdC, mappati a `turno_pdc_giornata` per id e non per
 * codice T1/T2/T3 → preview-only). Banner in calce dichiara lo stato.
 *
 * **Click su una pillola turno T1/T2/T3** → apre il 2° livello
 * (`TurnoDrilldownOverlay`).
 */

const GIORNI_VISTA = 7;
const WEEKDAY_LABELS = ["LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM"];

interface MockTurno {
  codice: "T1" | "T2" | "T3";
  start: string; // HH:MM
  end: string;
  durata_min: number;
  /** PM = pomeridiano (turno blu), AM = mattutino (verde). */
  variant: "am" | "pm";
}

const PATTERNS: Record<number, MockTurno[]> = {
  // Pattern usato nella griglia: 5 giorni lavorativi + 2 weekend riposo.
  // Ogni persona ne riceve uno diverso per varietà visiva.
  0: [
    { codice: "T1", start: "05:30", end: "13:30", durata_min: 480, variant: "am" },
    { codice: "T2", start: "13:00", end: "21:00", durata_min: 480, variant: "pm" },
    { codice: "T1", start: "06:00", end: "14:00", durata_min: 480, variant: "am" },
    { codice: "T3", start: "14:00", end: "22:00", durata_min: 480, variant: "pm" },
  ],
  1: [
    { codice: "T2", start: "13:30", end: "21:30", durata_min: 480, variant: "pm" },
    { codice: "T1", start: "05:30", end: "13:30", durata_min: 480, variant: "am" },
    { codice: "T1", start: "06:00", end: "14:00", durata_min: 480, variant: "am" },
    { codice: "T3", start: "14:00", end: "22:00", durata_min: 480, variant: "pm" },
  ],
  2: [
    { codice: "T1", start: "05:00", end: "13:00", durata_min: 480, variant: "am" },
    { codice: "T2", start: "12:00", end: "20:00", durata_min: 480, variant: "pm" },
    { codice: "T3", start: "14:30", end: "22:30", durata_min: 480, variant: "pm" },
    { codice: "T1", start: "06:00", end: "14:00", durata_min: 480, variant: "am" },
  ],
};

function dateAtOffset(offset: number): { day: number; weekend: boolean; today: boolean; dow: string } {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + offset);
  const dow = d.getDay(); // 0=Sun, 6=Sat
  const isoDow = (dow + 6) % 7; // 0=Mon
  return {
    day: d.getDate(),
    weekend: dow === 0 || dow === 6,
    today: offset === 0,
    dow: WEEKDAY_LABELS[isoDow],
  };
}

export function DepositoDrilldownOverlay() {
  const { drilldownDeposito, closeDepositoDrilldown, openTurnoDrilldown } = useGestionePersonale();

  const enabled = drilldownDeposito !== null;
  const persone = usePersoneByDepot(enabled ? drilldownDeposito.codice : undefined);

  const giorni = useMemo(
    () => Array.from({ length: GIORNI_VISTA }, (_, i) => dateAtOffset(i)),
    [],
  );

  if (!enabled) return null;

  // Massimo 3 PdC nel drilldown (la griglia diventa illeggibile oltre).
  const personeShown: PersonaWithDepositoRead[] = (persone.data ?? []).slice(0, 3);
  const violazioniCount = personeShown.reduce(
    (acc, _p, idx) => acc + (idx === 2 ? 1 : 0),
    0,
  );
  const inFerie = personeShown.filter((p) => p.indisponibilita_oggi === "ferie");

  // Toni descrittivi callout principale, in funzione della copertura.
  const toneCls =
    drilldownDeposito.copertura_pct >= 95
      ? "var(--gp-ok)"
      : drilldownDeposito.copertura_pct >= 71
        ? "var(--gp-warn)"
        : "var(--gp-bad)";

  return (
    <div
      className="gp-dd-overlay gp-page"
      role="dialog"
      aria-modal="true"
      aria-label={`Drilldown deposito ${drilldownDeposito.display_name}`}
      onClick={closeDepositoDrilldown}
    >
      <div className="gp-dd-panel" onClick={(e) => e.stopPropagation()}>
        <div className="gp-dd-head">
          <div className="min-w-0 flex-1">
            <div className="gp-eyebrow">
              Drilldown deposito · {new Date().toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" })}
            </div>
            <h2 className="gp-title" style={{ fontSize: 30, marginTop: 4 }}>
              {drilldownDeposito.display_name}
              <span className="gp-num">{drilldownDeposito.persone_attive} PdC · {GIORNI_VISTA}gg</span>
            </h2>
            <p className="gp-lede" style={{ marginTop: 8, maxWidth: "64ch" }}>
              Gantt settimanale dei turni placeholder.{" "}
              <b style={{ color: toneCls }}>
                Copertura {drilldownDeposito.copertura_pct.toFixed(1)}%
              </b>
              {inFerie.length > 0 ? (
                <>
                  {" "}
                  — <b>{inFerie[0].cognome} {inFerie[0].nome}</b> in ferie tutta la settimana, da
                  coprire con straordinari o trasferta da deposito limitrofo.
                </>
              ) : (
                <> — copertura nominale, nessuna sostituzione richiesta sui PdC visibili.</>
              )}
            </p>
          </div>
          <button
            type="button"
            className="gp-dd-close"
            onClick={closeDepositoDrilldown}
            aria-label="Chiudi drilldown deposito"
          >
            <X className="h-3 w-3" aria-hidden />
            Chiudi · Esc
          </button>
        </div>

        <div className="gp-dd-body">
          {persone.isLoading ? (
            <div style={{ padding: 24, color: "var(--gp-ink-4)", fontSize: 13 }}>
              Caricamento PdC del deposito…
            </div>
          ) : personeShown.length === 0 ? (
            <div style={{ padding: 24, color: "var(--gp-ink-4)", fontSize: 13 }}>
              Nessun PdC residente in questo deposito.
            </div>
          ) : (
            <div className="gp-gantt" style={{ "--gp-days": GIORNI_VISTA } as React.CSSProperties}>
              <div className="gp-gantt-axis">PdC · matricola</div>
              <div className="gp-gantt-days">
                {giorni.map((g, i) => (
                  <div
                    key={i}
                    className={`gp-gantt-d-cell ${g.today ? "gp-today" : ""} ${g.weekend ? "gp-weekend" : ""}`}
                  >
                    <span className="gp-dow">{g.dow}</span>
                    <span className="gp-d">{String(g.day).padStart(2, "0")}</span>
                  </div>
                ))}
              </div>

              {personeShown.map((p, rowIdx) => {
                const inFerieFull = p.indisponibilita_oggi === "ferie";
                const pattern = PATTERNS[rowIdx % 3] ?? PATTERNS[0];
                return (
                  <RowFragment
                    key={p.id}
                    persona={p}
                    rowIdx={rowIdx}
                    giorni={giorni}
                    pattern={pattern}
                    inFerieFull={inFerieFull}
                    hasViolation={rowIdx === 2 && !inFerieFull}
                    onTurnoClick={(t) =>
                      openTurnoDrilldown({
                        codice: t.codice,
                        pdc_label: `${p.cognome} ${p.nome}`,
                        matricola: p.codice_dipendente,
                        deposito: drilldownDeposito.display_name,
                        durata_label: `${Math.floor(t.durata_min / 60)}h ${String(t.durata_min % 60).padStart(2, "0")}m`,
                      })
                    }
                  />
                );
              })}
            </div>
          )}

          <div className="gp-gantt-legend">
            <span><span className="gp-sw" style={{ background: "var(--gp-ok)" }} /> Turno mattino</span>
            <span><span className="gp-sw" style={{ background: "#0062CC" }} /> Turno pomeriggio</span>
            <span><span className="gp-sw" style={{ background: "#B88B5C" }} /> Ferie</span>
            <span><span className="gp-sw" style={{ background: "var(--gp-bad)" }} /> Malattia</span>
            <span><span className="gp-sw" style={{ background: "transparent", border: "1px dashed var(--gp-line-2)" }} /> Riposo</span>
            {violazioniCount > 0 && (
              <span style={{ marginLeft: "auto" }}>
                <b style={{ color: "var(--gp-bad)" }}>
                  {violazioniCount} violazione{violazioniCount === 1 ? "" : "i"} CCNL
                </b>{" "}
                · riposo &lt; 11h
              </span>
            )}
          </div>

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
            <b style={{ color: "var(--gp-ink-3)" }}>Preview · dati simulati.</b>{" "}
            I PdC visibili sono reali dell'azienda (deposito{" "}
            <span style={{ fontWeight: 600 }}>{drilldownDeposito.codice}</span>); i turni
            T1/T2/T3 e le violazioni CCNL sono placeholder a scopo dimostrativo. I turni reali
            arriveranno dal builder Pianificatore PdC (collegamento previsto a{" "}
            <span style={{ fontFamily: "ui-monospace, monospace" }}>turno_pdc_giornata</span>).
          </div>

          <div style={{ marginTop: 24, display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button
              type="button"
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-[var(--gp-line-2)] bg-white px-3 text-[12.5px] text-[color:var(--gp-ink-2)] transition hover:border-[var(--gp-ink-3)]"
            >
              <Upload className="h-3 w-3" aria-hidden />
              Esporta Gantt
            </button>
            <Link
              to="/pianificatore-pdc/turni"
              onClick={closeDepositoDrilldown}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-[var(--gp-line-2)] bg-white px-3 text-[12.5px] text-[color:var(--gp-ink-2)] transition hover:border-[var(--gp-ink-3)]"
            >
              <RouteIcon className="h-3 w-3" aria-hidden />
              Apri in Pianificatore PdC
            </Link>
            <button
              type="button"
              style={{ marginLeft: "auto" }}
              className="inline-flex h-8 items-center gap-1.5 rounded-md bg-[#0062CC] px-3 text-[12.5px] font-medium text-white transition hover:bg-[#004FA6]"
            >
              <Plus className="h-3 w-3" aria-hidden />
              Richiedi sostituzione
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

interface RowFragmentProps {
  persona: PersonaWithDepositoRead;
  rowIdx: number;
  giorni: ReturnType<typeof dateAtOffset>[];
  pattern: MockTurno[];
  inFerieFull: boolean;
  hasViolation: boolean;
  onTurnoClick: (t: MockTurno) => void;
}

function RowFragment({
  persona: p,
  rowIdx: _rowIdx,
  giorni,
  pattern,
  inFerieFull,
  hasViolation,
  onTurnoClick,
}: RowFragmentProps) {
  // Posizioni hardcoded per i 5 giorni feriali + banda riposo weekend.
  // 7 colonne uguali → larghezza giorno = 100/7 ≈ 14.286%.
  // Bar width ~13.5% (un po' meno della cella per gap visivo).
  const dayPct = 100 / giorni.length;
  const barWidthPct = dayPct * 0.95;
  const restWidthPct = dayPct * 1.95; // 2 giorni weekend

  // Trova posizione weekend (per banda riposo).
  let weekendStart = -1;
  for (let i = 0; i < giorni.length; i += 1) {
    if (giorni[i].weekend && weekendStart === -1) weekendStart = i;
  }

  const yearsExperience =
    p.data_assunzione !== null
      ? Math.max(0, Math.floor((Date.now() - new Date(p.data_assunzione).getTime()) / (365.25 * 24 * 3600 * 1000)))
      : null;

  return (
    <>
      <div className="gp-gantt-row-label">
        <span className="gp-cell-name">
          <span style={{ textTransform: "uppercase", letterSpacing: ".02em", fontWeight: 700 }}>
            {p.cognome}
          </span>{" "}
          {p.nome}
        </span>
        <span style={{ fontSize: 10.5, color: "var(--gp-ink-4)", fontVariantNumeric: "tabular-nums" }}>
          matr. {p.codice_dipendente}
          {yearsExperience !== null && ` · ${yearsExperience}y`}
        </span>
      </div>
      <div className="gp-gantt-row-cells">
        {giorni.map((g, ci) => (
          <div
            key={ci}
            className={`gp-gantt-cell ${g.today ? "gp-today" : ""} ${g.weekend ? "gp-weekend" : ""}`}
          >
            {hasViolation && ci === 0 && (
              <div className="gp-gantt-violation" aria-label="Violazione CCNL">
                CCNL · 11h
              </div>
            )}
          </div>
        ))}

        {inFerieFull ? (
          <button
            type="button"
            className="gp-gantt-bar gp-f"
            style={{ left: `${dayPct * 0.05}%`, width: `${dayPct * giorni.length * 0.99 - dayPct * 0.05}%` }}
            onClick={() =>
              onTurnoClick({
                codice: "T1",
                start: "00:00",
                end: "23:59",
                durata_min: 14 * 24 * 60,
                variant: "am",
              })
            }
          >
            FERIE · settimana intera <span className="gp-bar-meta">approvata</span>
          </button>
        ) : (
          <>
            {pattern.slice(0, 4).map((t, ti) => {
              const turnIdx = ti; // posizioni 0,1,2,3
              const left = dayPct * (turnIdx + 0.05);
              return (
                <button
                  key={ti}
                  type="button"
                  className={`gp-gantt-bar ${t.variant === "pm" ? "gp-pm" : ""}`}
                  style={{ left: `${left}%`, width: `${barWidthPct}%` }}
                  onClick={() => onTurnoClick(t)}
                  title={`${t.codice} · ${t.start}→${t.end}`}
                >
                  {t.codice} · {t.start}→{t.end}
                  <span className="gp-bar-meta">8h</span>
                </button>
              );
            })}
            {weekendStart >= 0 && (
              <div
                className="gp-gantt-bar gp-rest"
                style={{
                  left: `${dayPct * (weekendStart + 0.05)}%`,
                  width: `${restWidthPct - dayPct * 0.1}%`,
                }}
              >
                — riposo weekend
              </div>
            )}
            {/* turno extra dopo il weekend, se c'è uno slot */}
            {pattern[4] !== undefined && weekendStart >= 0 && weekendStart + 2 < giorni.length && (
              <button
                type="button"
                className={`gp-gantt-bar ${pattern[4].variant === "pm" ? "gp-pm" : ""}`}
                style={{
                  left: `${dayPct * (weekendStart + 2 + 0.05)}%`,
                  width: `${barWidthPct}%`,
                }}
                onClick={() => onTurnoClick(pattern[4])}
              >
                {pattern[4].codice} · {pattern[4].start}→{pattern[4].end}
                <span className="gp-bar-meta">8h</span>
              </button>
            )}
          </>
        )}
      </div>
    </>
  );
}
