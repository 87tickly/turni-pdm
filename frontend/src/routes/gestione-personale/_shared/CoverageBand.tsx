import type { GestionePersonaleKpiPerDepositoRead } from "@/lib/api/gestione-personale";

/**
 * Sprint 7.10 MR β.1 — Coverage band: 25 segmenti orizzontali sul
 * dashboard GP, uno per deposito, colorato per tono (verde/giallo/rosso).
 * Click → apre il drilldown deposito (gestito da `GestionePersonaleProvider`).
 *
 * Soglie: `>= 95` ok, `>= 71` warn, altrimenti bad. (Allineato al
 * design + NORMATIVA-PDC che fissa il target operativo a 95% di
 * copertura PdC giornaliera, ma con tolleranza 70-94% prima del
 * critico.)
 */

interface CoverageBandProps {
  depots: GestionePersonaleKpiPerDepositoRead[];
  /** Media per "X media · Y critici · Z warning · K ok" — già calcolata dal chiamante. */
  mediaPct: number;
  onDepotClick: (codice: string) => void;
}

function toneOf(cov: number): "ok" | "warn" | "bad" {
  if (cov >= 95) return "ok";
  if (cov >= 71) return "warn";
  return "bad";
}

export function CoverageBand({ depots, mediaPct, onDepotClick }: CoverageBandProps) {
  const counts = { ok: 0, warn: 0, bad: 0 };
  for (const d of depots) {
    counts[toneOf(d.copertura_pct)] += 1;
  }
  const cols = depots.length;

  return (
    <div className="gp-cov-band">
      <div className="gp-cov-band-head">
        <span className="gp-cov-band-label">
          Stato copertura · {cols} {cols === 1 ? "deposito" : "depositi"}
        </span>
        <span className="gp-cov-band-total">
          <b>{mediaPct.toFixed(1)}%</b> media · <b>{counts.bad}</b> critici · <b>{counts.warn}</b>{" "}
          warning · <b>{counts.ok}</b> ok
        </span>
      </div>
      <div
        className="gp-cov-segments"
        style={{ "--gp-cov-cols": cols } as React.CSSProperties}
      >
        {depots.map((d) => {
          const tone = toneOf(d.copertura_pct);
          return (
            <button
              key={d.depot_codice}
              type="button"
              className={`gp-cov-seg gp-s-${tone}`}
              title={`${d.depot_codice} · ${d.copertura_pct.toFixed(1)}%`}
              aria-label={`Deposito ${d.depot_codice}, copertura ${d.copertura_pct.toFixed(1)}%`}
              onClick={() => onDepotClick(d.depot_codice)}
            />
          );
        })}
      </div>
      <div className="gp-cov-summary">
        <span className="gp-grp">
          <span className="gp-sw gp-s-bad" /> ≤ 70% <span className="gp-n">{counts.bad}</span>
        </span>
        <span className="gp-grp">
          <span className="gp-sw gp-s-warn" /> 71-94% <span className="gp-n">{counts.warn}</span>
        </span>
        <span className="gp-grp">
          <span className="gp-sw gp-s-ok" /> ≥ 95% <span className="gp-n">{counts.ok}</span>
        </span>
        <span style={{ marginLeft: "auto" }}>click su un segmento per il drilldown</span>
      </div>
    </div>
  );
}
