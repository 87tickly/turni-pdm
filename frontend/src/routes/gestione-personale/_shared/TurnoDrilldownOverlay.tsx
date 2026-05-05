import { List, Route as RouteIcon, Upload, X } from "lucide-react";

import { useGestionePersonale } from "./GestionePersonaleContext";

/**
 * Sprint 7.10 MR β.1 — Drilldown turno: overlay modale al centro che
 * mostra il Gantt orario "treno-style" del turno cliccato dal
 * `DepositoDrilldownOverlay`. Asse 04:00 → 13:00, 5 viaggi rossi a
 * pillola + 1 segmento di preparazione macchina, 4 pause con minuti
 * annotati.
 *
 * **Tutti i tempi sono placeholder**: il data model `turno_pdc_giornata`
 * ha blocchi reali ma con semantica diversa (CONDOTTA/REFEZ/ACCp/CV…
 * vs viaggi-passeggeri MiPG↔Lc del prototipo). Banner di stato lo
 * dichiara in legenda.
 */

const HOUR_START = 4;
const HOUR_END = 13;
const HOUR_RANGE = HOUR_END - HOUR_START; // 9 hours

function tickLeftPct(hour: number): number {
  return ((hour - HOUR_START) / HOUR_RANGE) * 100;
}

function timeToPct(hh: number, mm: number): number {
  return tickLeftPct(hh + mm / 60);
}

interface Trip {
  num: string;
  startH: number;
  startM: number;
  endH: number;
  endM: number;
  /** Stazione di partenza (ad inizio segmento). */
  fromStat: string;
  toStat: string;
}

const TRIPS: Trip[] = [
  { num: "24814", startH: 5, startM: 22, endH: 6, endM: 24, fromStat: "MiPG", toStat: "Lc" },
  { num: "24825", startH: 7, startM: 6, endH: 8, endM: 8, fromStat: "Lc", toStat: "MiPG" },
  { num: "24828", startH: 8, startM: 52, endH: 9, endM: 54, fromStat: "MiPG", toStat: "Lc" },
  { num: "24837", startH: 10, startM: 6, endH: 11, endM: 8, fromStat: "Lc", toStat: "MiPG" },
  { num: "24846", startH: 11, startM: 52, endH: 12, endM: 54, fromStat: "MiPG", toStat: "Lc" },
];

const PREP = { startH: 4, startM: 30, endH: 5, endM: 22 };

const PAUSES = [
  { fromH: 6, fromM: 24, toH: 7, toM: 6, label: "42′" },
  { fromH: 8, fromM: 8, toH: 8, toM: 52, label: "44′" },
  { fromH: 9, fromM: 54, toH: 10, toM: 6, label: "12′" },
  { fromH: 11, fromM: 8, toH: 11, toM: 52, label: "44′" },
];

function fmt(h: number, m: number): string {
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

export function TurnoDrilldownOverlay() {
  const { drilldownTurno, closeTurnoDrilldown } = useGestionePersonale();
  if (drilldownTurno === null) return null;

  return (
    <div
      className="gp-shift-overlay gp-page"
      role="dialog"
      aria-modal="true"
      aria-label={`Drilldown turno ${drilldownTurno.codice}`}
      onClick={closeTurnoDrilldown}
    >
      <div className="gp-shift-panel" onClick={(e) => e.stopPropagation()}>
        <div className="gp-shift-head">
          <div className="min-w-0 flex-1">
            <div className="gp-eyebrow">
              Drilldown turno · {drilldownTurno.codice} · {new Date().toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" })}
            </div>
            <h2 className="gp-title" style={{ fontSize: 30, marginTop: 4 }}>
              {drilldownTurno.codice} · {drilldownTurno.pdc_label}
              <span className="gp-num">
                {drilldownTurno.deposito} · {drilldownTurno.durata_label}
              </span>
            </h2>
            <p className="gp-lede" style={{ marginTop: 8, maxWidth: "64ch" }}>
              Turno mattino — 5 viaggi MiPG↔Lc con un trasferimento iniziale di
              preparazione macchina, 4 pause regolamentari e tempi di percorrenza
              inclusi. <b>Tutti i tempi sono placeholder.</b>
            </p>
          </div>
          <button
            type="button"
            className="gp-dd-close"
            onClick={closeTurnoDrilldown}
            aria-label="Chiudi drilldown turno"
          >
            <X className="h-3 w-3" aria-hidden />
            Chiudi · Esc
          </button>
        </div>

        <div className="gp-shift-body">
          <div className="gp-shift-time">
            <div className="gp-ax" />

            {Array.from({ length: HOUR_RANGE + 1 }, (_, i) => {
              const h = HOUR_START + i;
              const left = tickLeftPct(h);
              return (
                <span key={`tick-${h}`}>
                  <span className="gp-shift-tick" style={{ left: `${left}%` }} />
                  <span className="gp-shift-tick-l" style={{ left: `${left}%` }}>
                    {fmt(h, 0)}
                  </span>
                </span>
              );
            })}

            {/* Stazione di partenza */}
            <div className="gp-shift-seg-stat" style={{ left: "0.5%" }}>
              {TRIPS[0].fromStat}
            </div>

            {/* Preparazione macchina (tratteggiata) */}
            <div
              className="gp-shift-seg-prep"
              style={{
                left: `${timeToPct(PREP.startH, PREP.startM)}%`,
                width: `${timeToPct(PREP.endH, PREP.endM) - timeToPct(PREP.startH, PREP.startM)}%`,
              }}
              aria-label="Preparazione macchina"
            >
              <RouteIcon className="h-3 w-3 mr-1" aria-hidden />→ prep
            </div>

            {TRIPS.map((t, i) => {
              const left = timeToPct(t.startH, t.startM);
              const right = timeToPct(t.endH, t.endM);
              return (
                <span key={`trip-${i}`}>
                  {/* Stazione arrivo subito sopra l'inizio del segmento successivo */}
                  <div className="gp-shift-seg-stat" style={{ left: `${right + 0.4}%` }}>
                    {t.toStat}
                  </div>
                  <div
                    className="gp-shift-seg-trip"
                    style={{ left: `${left}%`, width: `${right - left}%` }}
                    title={`${t.num} · ${fmt(t.startH, t.startM)}→${fmt(t.endH, t.endM)}`}
                  >
                    <span className="gp-arr">→</span>
                    <span>{t.num}</span>
                  </div>
                </span>
              );
            })}

            {PAUSES.map((p, i) => {
              const left = timeToPct(p.fromH, p.fromM);
              const right = timeToPct(p.toH, p.toM);
              return (
                <div
                  key={`pause-${i}`}
                  className="gp-shift-seg-pause"
                  style={{ left: `${left}%`, width: `${right - left}%` }}
                >
                  {p.label}
                </div>
              );
            })}

            {/* Stop labels — alternati alto/basso per evitare collisioni */}
            <div className="gp-shift-stops" style={{ left: `${timeToPct(PREP.startH, PREP.startM)}%` }}>
              {fmt(PREP.startH, PREP.startM)}
              <br />
              {TRIPS[0].fromStat}
            </div>
            {TRIPS.map((t, i) => (
              <span key={`stop-${i}`}>
                <div className="gp-shift-stops" style={{ left: `${timeToPct(t.startH, t.startM)}%` }}>
                  {fmt(t.startH, t.startM)}
                </div>
                <div className="gp-shift-stops" style={{ left: `${timeToPct(t.endH, t.endM)}%` }}>
                  {fmt(t.endH, t.endM)}
                  <br />
                  {t.toStat}
                </div>
              </span>
            ))}
          </div>

          <div className="gp-shift-summary">
            <div className="gp-cell">
              <span className="gp-k">Inizio</span>
              <span className="gp-v">
                04:30 <small>{TRIPS[0].fromStat}</small>
              </span>
            </div>
            <div className="gp-cell">
              <span className="gp-k">Fine</span>
              <span className="gp-v">
                12:54 <small>{TRIPS[TRIPS.length - 1].toStat}</small>
              </span>
            </div>
            <div className="gp-cell">
              <span className="gp-k">Viaggi</span>
              <span className="gp-v">
                {TRIPS.length} <small>+ 1 prep</small>
              </span>
            </div>
            <div className="gp-cell">
              <span className="gp-k">Pause</span>
              <span className="gp-v">
                2h 22m <small>{PAUSES.length} pause</small>
              </span>
            </div>
          </div>

          <div className="gp-gantt-legend" style={{ marginTop: 0 }}>
            <span><span className="gp-sw" style={{ background: "var(--gp-bad)" }} /> Tratta passeggeri</span>
            <span>
              <span className="gp-sw" style={{ background: "rgba(179,54,54,0.06)", border: "2px dashed var(--gp-bad)" }} />
              Preparazione macchina
            </span>
            <span>
              <span className="gp-sw" style={{ background: "transparent", border: "1px dashed var(--gp-line-2)" }} />
              Pausa
            </span>
            <span style={{ marginLeft: "auto" }}>
              <b style={{ color: "var(--gp-ink-3)" }}>Tutti i tempi sono placeholder</b>
            </span>
          </div>

          <div style={{ marginTop: 24, display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button
              type="button"
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-[var(--gp-line-2)] bg-white px-3 text-[12.5px] text-[color:var(--gp-ink-2)] transition hover:border-[var(--gp-ink-3)]"
            >
              <Upload className="h-3 w-3" aria-hidden />
              Esporta turno
            </button>
            <button
              type="button"
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-[var(--gp-line-2)] bg-white px-3 text-[12.5px] text-[color:var(--gp-ink-2)] transition hover:border-[var(--gp-ink-3)]"
            >
              <List className="h-3 w-3" aria-hidden />
              Vedi tutti i turni del PdC
            </button>
            <button
              type="button"
              style={{ marginLeft: "auto" }}
              className="inline-flex h-8 items-center gap-1.5 rounded-md bg-[#0062CC] px-3 text-[12.5px] font-medium text-white transition hover:bg-[#004FA6]"
            >
              <RouteIcon className="h-3 w-3" aria-hidden />
              Apri in Pianificatore PdC
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
