import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  CalendarDays,
  Check,
  ChevronRight,
  GraduationCap,
  Heart,
  Info,
  Plane,
  Plus,
} from "lucide-react";
import type { ComponentType, SVGProps } from "react";

import { Spinner } from "@/components/ui/Spinner";
import { useIndisponibilita } from "@/hooks/useGestionePersonale";
import { EditorialHead } from "@/routes/gestione-personale/_shared/EditorialHead";

/**
 * Sprint 7.10 MR β.1 — Indisponibilità (Gestione Personale, editorial).
 *
 * Layout:
 * 1. Editorial head + toggle "Solo in corso oggi" + bottone "Nuova
 *    indisponibilità"
 * 2. Tabs: Tutte / Ferie / Malattia / ROL / Altre (con counter inline)
 * 3. Header riga mono uppercase
 * 4. Card-list rows: index · persona+matr · deposito · tipo · periodo ·
 *    giorni · stato approvazione → click va al dettaglio persona
 */

type TabId = "tutte" | "ferie" | "malattia" | "rol" | "altre";

interface TabDef {
  id: TabId;
  label: string;
  tipos: string[];
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}

const TABS: TabDef[] = [
  { id: "tutte", label: "Tutte", tipos: [], icon: Info },
  { id: "ferie", label: "Ferie", tipos: ["ferie"], icon: Plane },
  { id: "malattia", label: "Malattia", tipos: ["malattia"], icon: Heart },
  { id: "rol", label: "ROL", tipos: ["ROL"], icon: CalendarDays },
  { id: "altre", label: "Altre", tipos: ["sciopero", "formazione", "congedo"], icon: GraduationCap },
];

interface TipoMeta {
  letter: string;
  cls: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  label: string;
}

const TIPO_META: Record<string, TipoMeta> = {
  ferie: { letter: "F", cls: "gp-tag-warn", icon: Plane, label: "ferie" },
  malattia: { letter: "M", cls: "gp-tag-bad", icon: Heart, label: "malattia" },
  ROL: { letter: "R", cls: "gp-tag-ink", icon: CalendarDays, label: "ROL" },
  rol: { letter: "R", cls: "gp-tag-ink", icon: CalendarDays, label: "ROL" },
  sciopero: { letter: "S", cls: "gp-tag-warn", icon: AlertTriangle, label: "sciopero" },
  formazione: { letter: "Fo", cls: "gp-tag-ink", icon: GraduationCap, label: "formazione" },
  congedo: { letter: "C", cls: "gp-tag-muted", icon: Info, label: "congedo" },
};

function formatRange(from: string, to: string): string {
  const f = new Date(from).toLocaleDateString("it-IT", { day: "2-digit", month: "short" });
  const t = new Date(to).toLocaleDateString("it-IT", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
  return `${f} → ${t}`;
}

export function GestionePersonaleIndisponibilitaRoute() {
  const [tab, setTab] = useState<TabId>("tutte");
  const [soloAttiveOggi, setSoloAttiveOggi] = useState(false);

  const all = useIndisponibilita({ attive_oggi: soloAttiveOggi });

  const tabDef = TABS.find((t) => t.id === tab) ?? TABS[0];
  const filtered = useMemo(() => {
    const list = all.data ?? [];
    if (tabDef.tipos.length === 0) return list;
    return list.filter((i) => tabDef.tipos.includes(i.tipo));
  }, [all.data, tabDef]);

  const counts = useMemo(() => {
    const list = all.data ?? [];
    const c = { tutte: list.length, ferie: 0, malattia: 0, rol: 0, altre: 0 };
    for (const i of list) {
      if (i.tipo === "ferie") c.ferie += 1;
      else if (i.tipo === "malattia") c.malattia += 1;
      else if (i.tipo === "ROL" || i.tipo === "rol") c.rol += 1;
      else c.altre += 1;
    }
    return c;
  }, [all.data]);

  return (
    <section className="gp-page">
      <EditorialHead
        eyebrow="Gestione personale · Indisponibilità"
        title="Ferie · Malattia · ROL · Altre"
        lede={
          <>
            Tutte le indisponibilità delle matricole attive. Usa i tab per filtrare per tipo,
            attiva il toggle per vedere solo quelle in corso oggi.
          </>
        }
        actions={
          <>
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                fontSize: 12,
                color: "var(--gp-ink-3)",
                cursor: "pointer",
              }}
            >
              <input
                type="checkbox"
                checked={soloAttiveOggi}
                onChange={(e) => setSoloAttiveOggi(e.target.checked)}
                style={{ accentColor: "#0062CC" }}
              />
              Solo in corso oggi
            </label>
            <button type="button" className="gp-action-btn gp-action-btn-ink">
              <Plus className="h-3.5 w-3.5" aria-hidden /> Nuova indisponibilità
            </button>
          </>
        }
      />

      {/* Tabs */}
      <div className="gp-tabs">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`gp-tab ${tab === t.id ? "gp-is-active" : ""}`}
            >
              <Icon className="h-3.5 w-3.5" aria-hidden />
              {t.label}
              <span className="gp-tab-count">{counts[t.id]}</span>
            </button>
          );
        })}
      </div>

      {/* Header riga */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "36px 1fr 140px 110px 200px 60px 110px 14px",
          gap: 16,
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
        <span>Persona · matricola</span>
        <span>Deposito</span>
        <span>Tipo</span>
        <span>Periodo</span>
        <span style={{ textAlign: "right" }}>Giorni</span>
        <span>Stato</span>
        <span />
      </div>

      {all.isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Spinner label="Caricamento indisponibilità…" />
        </div>
      ) : all.isError ? (
        <p
          role="alert"
          className="rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
        >
          Errore: {all.error?.message ?? "errore sconosciuto"}
        </p>
      ) : filtered.length === 0 ? (
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
          <CalendarDays className="h-9 w-9" style={{ color: "var(--gp-ink-5)" }} aria-hidden />
          <h2 className="gp-section-title">Nessuna voce</h2>
          <p style={{ fontSize: 13, color: "var(--gp-ink-4)" }}>
            Nessuna indisponibilità trovata per questo filtro.
          </p>
        </div>
      ) : (
        <div>
          {filtered.map((i, idx) => {
            const meta = TIPO_META[i.tipo] ?? TIPO_META.congedo;
            const Icon = meta.icon;
            return (
              <Link
                key={i.id}
                to={`/gestione-personale/persone/${i.persona_id}`}
                style={{
                  display: "grid",
                  gridTemplateColumns: "36px 1fr 140px 110px 200px 60px 110px 14px",
                  alignItems: "center",
                  gap: 16,
                  padding: "13px 0",
                  borderBottom: "1px solid var(--gp-line)",
                  textDecoration: "none",
                  color: "inherit",
                  cursor: "pointer",
                  transition: "background 0.08s",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "var(--gp-bg-rule)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                aria-label={`Apri scheda di ${i.persona_cognome} ${i.persona_nome}`}
              >
                <span
                  style={{
                    fontSize: 11,
                    color: "var(--gp-ink-5)",
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {String(idx + 1).padStart(2, "0")}
                </span>
                <div>
                  <span
                    style={{
                      fontWeight: 600,
                      color: "var(--gp-ink)",
                      fontSize: 13.5,
                    }}
                  >
                    <span style={{ textTransform: "uppercase", letterSpacing: ".02em", fontWeight: 700 }}>
                      {i.persona_cognome}
                    </span>{" "}
                    {i.persona_nome}
                  </span>
                  <div
                    style={{
                      fontSize: 10.5,
                      color: "var(--gp-ink-4)",
                      marginTop: 2,
                      fontVariantNumeric: "tabular-nums",
                    }}
                  >
                    matr. {i.persona_codice_dipendente}
                  </div>
                </div>
                <span
                  style={{
                    fontSize: 11.5,
                    fontWeight: 600,
                    color: i.depot_codice !== null ? "#0062CC" : "var(--gp-ink-5)",
                    letterSpacing: ".02em",
                  }}
                >
                  {i.depot_codice ?? "—"}
                </span>
                <span
                  className={`gp-tag ${meta.cls}`}
                  style={{ display: "inline-flex", alignItems: "center", gap: 5 }}
                >
                  <Icon className="h-3 w-3" aria-hidden />
                  {meta.label}
                </span>
                <span
                  style={{
                    fontSize: 12,
                    color: "var(--gp-ink-3)",
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  <span>{formatRange(i.data_inizio, i.data_fine).split(" → ")[0]}</span>
                  <span style={{ color: "var(--gp-ink-5)" }}>→</span>
                  <span>{formatRange(i.data_inizio, i.data_fine).split(" → ")[1]}</span>
                </span>
                <span
                  style={{
                    textAlign: "right",
                    fontWeight: 600,
                    fontSize: 14,
                    color: "var(--gp-ink)",
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {i.giorni_totali}
                </span>
                <span
                  className={`gp-tag ${i.is_approvato ? "gp-tag-ok" : "gp-tag-warn"}`}
                  style={{ display: "inline-flex", alignItems: "center", gap: 5 }}
                >
                  <Check className="h-3 w-3" aria-hidden />
                  {i.is_approvato ? "approvata" : "in attesa"}
                </span>
                <ChevronRight
                  className="h-3.5 w-3.5"
                  style={{ color: "var(--gp-ink-5)" }}
                  aria-hidden
                />
              </Link>
            );
          })}
        </div>
      )}
    </section>
  );
}
