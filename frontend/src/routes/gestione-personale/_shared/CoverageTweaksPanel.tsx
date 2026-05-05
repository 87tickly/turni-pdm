import { useState } from "react";

import { type CoverageTweak, useGestionePersonale } from "./GestionePersonaleContext";

/**
 * Sprint 7.10 MR β.1 — Tweaks panel flottante per simulare lo stato
 * di copertura (verde/giallo/rosso). Utility design+demo, NON di
 * produzione: serve a far vedere come reagiscono callout, KPI stripe
 * e coverage band ai cambi di tono. Collassabile dal pulsante "—".
 */

const OPTIONS: Array<{ value: CoverageTweak; label: string; hint: string }> = [
  { value: "current", label: "Attuale", hint: "dato reale dei KPI" },
  { value: "green", label: "Verde", hint: "≈ 96.5%" },
  { value: "yellow", label: "Giallo", hint: "≈ 88.4%" },
  { value: "red", label: "Rosso", hint: "≈ 62.1%" },
];

export function CoverageTweaksPanel() {
  const { coverageTweak, setCoverageTweak } = useGestionePersonale();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className="gp-tweaks"
      role="region"
      aria-label="Simulatore stato copertura"
    >
      <div className="gp-tweaks-head">
        <span>Tweak · stato copertura</span>
        <button
          type="button"
          className="gp-tweaks-toggle"
          onClick={() => setCollapsed((v) => !v)}
          aria-label={collapsed ? "Espandi pannello tweak" : "Riduci pannello tweak"}
          aria-expanded={!collapsed}
        >
          {collapsed ? "+" : "—"}
        </button>
      </div>
      {!collapsed && (
        <>
          <div className="gp-tweaks-radios" role="radiogroup">
            {OPTIONS.map((o) => (
              <button
                key={o.value}
                type="button"
                role="radio"
                aria-checked={coverageTweak === o.value}
                title={o.hint}
                className={`gp-tweaks-radio ${coverageTweak === o.value ? "gp-is-on" : ""}`}
                onClick={() => setCoverageTweak(o.value)}
              >
                {o.label}
              </button>
            ))}
          </div>
          <div className="gp-tweaks-help">
            Cambia lo stato per vedere come reagiscono stripe KPI, callout
            e coverage band.
          </div>
        </>
      )}
    </aside>
  );
}
