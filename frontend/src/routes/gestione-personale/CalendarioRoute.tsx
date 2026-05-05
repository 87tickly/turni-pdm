import { useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { CalendarRange, ChevronDown, ChevronLeft, ChevronRight, Info } from "lucide-react";

import { Spinner } from "@/components/ui/Spinner";
import { useDepots } from "@/hooks/useAnagrafiche";
import {
  useIndisponibilita,
  usePersoneByDepot,
} from "@/hooks/useGestionePersonale";
import { EditorialHead } from "@/routes/gestione-personale/_shared/EditorialHead";

/**
 * Sprint 7.10 MR β.1 — Calendario assegnazioni (Gestione Personale,
 * editorial Cal.com vertical).
 *
 * Layout:
 * 1. Editorial head + selector deposito + navigatore date (← 14gg → )
 * 2. Inline legend (T/F/M/R/A/Riposo)
 * 3. Grid verticale: col 1 = giorni (etichetta L 05), col 2..4 = persone
 *
 * I "T" turno-placeholder vengono mostrati per default sui giorni
 * lavorativi non coperti da indisponibilità reale; il prefisso ricalca
 * il design del prototipo.
 */

const GIORNI_VISTA = 14;
const WEEKDAY_LABELS = ["L", "M", "M", "G", "V", "S", "D"];
const WEEKDAY_LABELS_FULL = ["LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM"];

function addDays(d: Date, days: number): Date {
  const r = new Date(d);
  r.setDate(r.getDate() + days);
  return r;
}

function formatISODate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function isWeekend(d: Date): boolean {
  const wd = d.getDay();
  return wd === 0 || wd === 6;
}

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

type CellKind = "t" | "f" | "m" | "r" | "a" | "rest";

interface LegendItem {
  kind: CellKind;
  letter: string;
  label: string;
}

const LEGEND: LegendItem[] = [
  { kind: "t", letter: "T", label: "Turno (placeholder)" },
  { kind: "f", letter: "F", label: "Ferie" },
  { kind: "m", letter: "M", label: "Malattia" },
  { kind: "r", letter: "R", label: "ROL" },
  { kind: "a", letter: "A", label: "Altro" },
  { kind: "rest", letter: "—", label: "Riposo" },
];

const TIPO_TO_KIND: Record<string, CellKind> = {
  ferie: "f",
  malattia: "m",
  rol: "r",
  ROL: "r",
  sciopero: "a",
  formazione: "a",
  congedo: "a",
};

export function GestionePersonaleCalendarioRoute() {
  const depots = useDepots();
  const [depotCodice, setDepotCodice] = useState<string>("");
  const [depotMenuOpen, setDepotMenuOpen] = useState(false);
  const [startDate, setStartDate] = useState<Date>(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  });

  const persone = usePersoneByDepot(depotCodice.length > 0 ? depotCodice : undefined);
  const indisp = useIndisponibilita({
    depot: depotCodice.length > 0 ? depotCodice : undefined,
  });

  const giorni = useMemo(
    () => Array.from({ length: GIORNI_VISTA }, (_, i) => addDays(startDate, i)),
    [startDate],
  );

  const today = useMemo(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  }, []);

  // Map persona_id → { dataISO → tipo }
  const indispByPersonaDate = useMemo(() => {
    const m = new Map<number, Map<string, string>>();
    (indisp.data ?? []).forEach((i) => {
      const di = new Date(i.data_inizio);
      const df = new Date(i.data_fine);
      let cur = di;
      while (cur <= df) {
        const iso = formatISODate(cur);
        if (!m.has(i.persona_id)) m.set(i.persona_id, new Map());
        const inner = m.get(i.persona_id);
        if (inner !== undefined) inner.set(iso, i.tipo);
        cur = addDays(cur, 1);
      }
    });
    return m;
  }, [indisp.data]);

  // Mostriamo al più 6 persone per non sovraccaricare la griglia.
  const personeShown = (persone.data ?? []).slice(0, 6);
  const cols = personeShown.length;

  const depotSelected = depots.data?.find((d) => d.codice === depotCodice);

  return (
    <section
      className="gp-page"
      style={{ maxWidth: "none" }}
      onClick={() => setDepotMenuOpen(false)}
    >
      <EditorialHead
        eyebrow="Gestione personale · Calendario"
        title="Calendario assegnazioni"
        lede={
          <>
            Vista a {GIORNI_VISTA} giorni per deposito. Ogni colonna è un PdC, ogni riga un giorno. Le
            celle <span className="gp-cal-pill gp-t" style={{ verticalAlign: "middle" }}>T</span>{" "}
            sono turni-placeholder: si aggiornano quando il Pianificatore PdC li popola.
          </>
        }
        actions={
          <div
            style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ position: "relative" }}>
              <button
                type="button"
                className="gp-select-pill"
                onClick={() => setDepotMenuOpen(!depotMenuOpen)}
                aria-haspopup="menu"
                aria-expanded={depotMenuOpen}
                style={{ height: 36 }}
              >
                {depotSelected !== undefined
                  ? `${depotSelected.display_name} · ${depotSelected.codice}`
                  : "Seleziona deposito"}
                <ChevronDown className="h-3 w-3" aria-hidden />
              </button>
              {depotMenuOpen && (
                <div
                  role="menu"
                  style={{
                    position: "absolute",
                    top: "calc(100% + 4px)",
                    right: 0,
                    zIndex: 20,
                    background: "var(--gp-bg-elev)",
                    border: "1px solid var(--gp-line-2)",
                    borderRadius: 6,
                    boxShadow: "0 12px 24px -4px rgba(14,17,22,0.18)",
                    minWidth: 280,
                    maxHeight: 360,
                    overflowY: "auto",
                    padding: 4,
                  }}
                  onClick={(e) => e.stopPropagation()}
                >
                  {(depots.data ?? []).map((d) => (
                    <button
                      key={d.codice}
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setDepotCodice(d.codice);
                        setDepotMenuOpen(false);
                      }}
                      style={{
                        display: "block",
                        width: "100%",
                        textAlign: "left",
                        padding: "8px 10px",
                        fontSize: 12.5,
                        background: depotCodice === d.codice ? "rgba(0,98,204,0.08)" : "transparent",
                        color: depotCodice === d.codice ? "#0062CC" : "var(--gp-ink-2)",
                        border: 0,
                        borderRadius: 4,
                        cursor: "pointer",
                        fontFamily: "inherit",
                        fontWeight: depotCodice === d.codice ? 600 : 500,
                      }}
                    >
                      <span style={{ fontWeight: 600 }}>{d.codice}</span>{" "}
                      <span style={{ color: "var(--gp-ink-4)" }}>· {d.display_name}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 4,
                border: "1px solid var(--gp-line-2)",
                borderRadius: 6,
                padding: 2,
                background: "var(--gp-bg-elev)",
                height: 36,
              }}
            >
              <button
                type="button"
                onClick={() => setStartDate((d) => addDays(d, -GIORNI_VISTA))}
                aria-label="Periodo precedente"
                style={{
                  width: 28,
                  height: 28,
                  border: 0,
                  background: "transparent",
                  cursor: "pointer",
                  color: "var(--gp-ink-3)",
                  display: "grid",
                  placeItems: "center",
                  borderRadius: 4,
                }}
              >
                <ChevronLeft className="h-3.5 w-3.5" aria-hidden />
              </button>
              <span
                style={{
                  fontSize: 11.5,
                  fontWeight: 600,
                  padding: "0 10px",
                  whiteSpace: "nowrap",
                  fontVariantNumeric: "tabular-nums",
                  color: "var(--gp-ink)",
                }}
              >
                {giorni[0].toLocaleDateString("it-IT", { day: "2-digit", month: "short" })} →{" "}
                {giorni[giorni.length - 1].toLocaleDateString("it-IT", {
                  day: "2-digit",
                  month: "short",
                  year: "numeric",
                })}
              </span>
              <button
                type="button"
                onClick={() => setStartDate((d) => addDays(d, GIORNI_VISTA))}
                aria-label="Periodo successivo"
                style={{
                  width: 28,
                  height: 28,
                  border: 0,
                  background: "transparent",
                  cursor: "pointer",
                  color: "var(--gp-ink-3)",
                  display: "grid",
                  placeItems: "center",
                  borderRadius: 4,
                }}
              >
                <ChevronRight className="h-3.5 w-3.5" aria-hidden />
              </button>
            </div>
          </div>
        }
      />

      {/* Legend inline */}
      <div
        style={{
          display: "flex",
          gap: 24,
          padding: "14px 0",
          borderTop: "1px solid var(--gp-line-2)",
          borderBottom: "1px solid var(--gp-line)",
          fontSize: 11,
          color: "var(--gp-ink-3)",
          flexWrap: "wrap",
        }}
      >
        {LEGEND.map((l) => (
          <span key={l.kind} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span className={`gp-cal-pill gp-${l.kind}`}>{l.letter}</span>
            {l.label}
          </span>
        ))}
        <span style={{ marginLeft: "auto" }}>
          {cols} PdC · {GIORNI_VISTA} giorni · {cols * GIORNI_VISTA} celle
        </span>
      </div>

      {depotCodice.length === 0 ? (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 8,
            padding: "60px 20px",
            border: "1px dashed var(--gp-line-2)",
            borderRadius: 8,
            marginTop: 16,
            background: "var(--gp-bg-rule)",
          }}
        >
          <CalendarRange className="h-9 w-9" style={{ color: "var(--gp-ink-5)" }} aria-hidden />
          <h2 className="gp-section-title">Seleziona un deposito</h2>
          <p style={{ fontSize: 13, color: "var(--gp-ink-4)", maxWidth: "44ch", textAlign: "center" }}>
            Scegli un deposito dal menu in alto a destra per visualizzare il calendario dei PdC
            residenti.
          </p>
        </div>
      ) : persone.isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Spinner label="Caricamento PdC del deposito…" />
        </div>
      ) : personeShown.length === 0 ? (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 8,
            padding: "60px 20px",
            border: "1px dashed var(--gp-line-2)",
            borderRadius: 8,
            marginTop: 16,
          }}
        >
          <CalendarRange className="h-9 w-9" style={{ color: "var(--gp-ink-5)" }} aria-hidden />
          <h2 className="gp-section-title">Nessun PdC nel deposito</h2>
          <p style={{ fontSize: 13, color: "var(--gp-ink-4)" }}>
            Il deposito selezionato non ha PdC residenti.
          </p>
        </div>
      ) : (
        <div
          className="gp-cal-vertical"
          style={{ "--gp-cal-cols": cols } as CSSProperties}
        >
          <div className="gp-cal-h">Giorno</div>
          {personeShown.map((p) => (
            <div key={p.id} className="gp-cal-h gp-cal-person-h">
              <span style={{ fontWeight: 600 }}>
                <span style={{ textTransform: "uppercase", letterSpacing: ".02em" }}>
                  {p.cognome}
                </span>{" "}
                {p.nome}
              </span>
              <span className="gp-cal-person-h-matr">{p.codice_dipendente}</span>
            </div>
          ))}

          {giorni.map((d) => {
            const todayCls = isSameDay(d, today) ? "gp-today" : "";
            const wknd = isWeekend(d) ? "gp-weekend" : "";
            const dowIdx = (d.getDay() + 6) % 7;
            return (
              <span key={d.toISOString()} style={{ display: "contents" }}>
                <div className={`gp-cal-day-cell ${todayCls} ${wknd}`}>
                  <span className="gp-dow">
                    {WEEKDAY_LABELS[dowIdx]} · {WEEKDAY_LABELS_FULL[dowIdx]}
                  </span>
                  <span className="gp-d">{String(d.getDate()).padStart(2, "0")}</span>
                  {todayCls && <span className="gp-today-tag">oggi</span>}
                </div>
                {personeShown.map((p) => {
                  const indispMap = indispByPersonaDate.get(p.id);
                  const tipo = indispMap?.get(formatISODate(d));
                  let kind: CellKind;
                  if (tipo !== undefined) {
                    kind = TIPO_TO_KIND[tipo] ?? "a";
                  } else if (isWeekend(d)) {
                    kind = "rest";
                  } else {
                    kind = "t";
                  }
                  const letter = LEGEND.find((l) => l.kind === kind)?.letter ?? "—";
                  return (
                    <div
                      key={`${p.id}-${d.toISOString()}`}
                      className={`gp-cal-slot ${todayCls} ${wknd}`}
                    >
                      <span className={`gp-cal-pill gp-${kind}`} title={tipo ?? "turno"}>
                        {letter}
                      </span>
                    </div>
                  );
                })}
              </span>
            );
          })}
        </div>
      )}

      {depotCodice.length > 0 && personeShown.length > 0 && (
        <p
          style={{
            fontSize: 11.5,
            color: "var(--gp-ink-4)",
            marginTop: 14,
            maxWidth: "80ch",
            lineHeight: 1.6,
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          <Info className="h-3.5 w-3.5 shrink-0" style={{ color: "var(--gp-ink-4)" }} aria-hidden />
          Le celle T rappresentano turni-placeholder: l'integrazione con{" "}
          <code style={{ background: "var(--gp-bg-rule)", padding: "1px 4px", borderRadius: 3 }}>
            turno_pdc_giornata
          </code>{" "}
          avverrà quando il Visualizzatore PdC verrà popolato. I turni reali sovrascrivono i
          placeholder.
        </p>
      )}
    </section>
  );
}
