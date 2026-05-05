import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronRight, Plus, Search, Upload } from "lucide-react";

import { Spinner } from "@/components/ui/Spinner";
import { useDepots } from "@/hooks/useAnagrafiche";
import { usePersone } from "@/hooks/useGestionePersonale";
import type { PersonaWithDepositoRead } from "@/lib/api/gestione-personale";
import { EditorialHead, EditorialNum } from "@/routes/gestione-personale/_shared/EditorialHead";

/**
 * Sprint 7.10 MR β.1 — Anagrafica PdC (Gestione Personale, editorial).
 *
 * Layout:
 * 1. Editorial head con conteggio totale + lede ("X in servizio oggi")
 * 2. Toolbar compatta: search live + select-pill deposito + select-pill
 *    profilo + select-pill stato
 * 3. Header riga mono uppercase
 * 4. Card-list rows: index · cognome+nome+matr · profilo · deposito ·
 *    anni servizio · tag stato → click va al dettaglio persona
 */

type StatusFilter = "all" | "ok" | "ferie" | "malattia" | "rol" | "altro";

const STATUS_OPTIONS: Array<{ id: StatusFilter; label: string }> = [
  { id: "all", label: "Tutti gli stati" },
  { id: "ok", label: "In servizio" },
  { id: "ferie", label: "In ferie" },
  { id: "malattia", label: "In malattia" },
  { id: "rol", label: "ROL" },
  { id: "altro", label: "Altro" },
];

function statusOf(p: PersonaWithDepositoRead): StatusFilter {
  if (p.indisponibilita_oggi === null) return "ok";
  const t = p.indisponibilita_oggi.toLowerCase();
  if (t === "ferie") return "ferie";
  if (t === "malattia") return "malattia";
  if (t === "rol") return "rol";
  return "altro";
}

const STATUS_TAG_CLASS: Record<StatusFilter, string> = {
  all: "gp-tag-muted",
  ok: "gp-tag-ok",
  ferie: "gp-tag-warn",
  malattia: "gp-tag-bad",
  rol: "gp-tag-ink",
  altro: "gp-tag-muted",
};

const STATUS_LABEL: Record<StatusFilter, string> = {
  all: "tutti",
  ok: "in servizio",
  ferie: "in ferie",
  malattia: "malattia",
  rol: "ROL",
  altro: "altro",
};

export function GestionePersonalePersoneRoute() {
  const [search, setSearch] = useState("");
  const [depot, setDepot] = useState<string>("");
  const [profilo, setProfilo] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [openMenu, setOpenMenu] = useState<"depot" | "profilo" | "status" | null>(null);

  const persone = usePersone({
    search: search.length > 0 ? search : undefined,
    depot: depot.length > 0 ? depot : undefined,
    profilo: profilo.length > 0 ? profilo : undefined,
    only_active: true,
  });
  const depotsQuery = useDepots();

  const filtered = useMemo(() => {
    const list = persone.data ?? [];
    if (statusFilter === "all") return list;
    return list.filter((p) => statusOf(p) === statusFilter);
  }, [persone.data, statusFilter]);

  const totale = persone.data?.length ?? 0;
  const inServizio = useMemo(
    () => (persone.data ?? []).filter((p) => p.indisponibilita_oggi === null).length,
    [persone.data],
  );

  const yearsExperience = (p: PersonaWithDepositoRead): number | null => {
    if (p.data_assunzione === null) return null;
    return Math.max(
      0,
      Math.floor((Date.now() - new Date(p.data_assunzione).getTime()) / (365.25 * 24 * 3600 * 1000)),
    );
  };

  const profileOptions = useMemo(() => {
    const set = new Set<string>();
    for (const p of persone.data ?? []) set.add(p.profilo);
    return Array.from(set).sort();
  }, [persone.data]);

  return (
    <section className="gp-page" onClick={() => setOpenMenu(null)}>
      <EditorialHead
        eyebrow="Gestione personale · Anagrafica"
        title={
          <>
            Anagrafica PdC
            <EditorialNum>{totale}</EditorialNum>
          </>
        }
        lede={
          <>
            Personale di macchina dell'azienda. Cerca per nome, cognome o matricola; filtra per
            deposito di residenza o stato di servizio.{" "}
            <b>{inServizio} in servizio</b> oggi.
          </>
        }
        actions={
          <>
            <button type="button" className="gp-action-btn gp-action-btn-line">
              <Upload className="h-3.5 w-3.5" aria-hidden /> Esporta CSV
            </button>
            <button type="button" className="gp-action-btn gp-action-btn-ink">
              <Plus className="h-3.5 w-3.5" aria-hidden /> Nuovo PdC
            </button>
          </>
        }
      />

      <div className="gp-toolbar" onClick={(e) => e.stopPropagation()}>
        <div className="gp-toolbar-search">
          <Search className="h-4 w-4 shrink-0" style={{ color: "var(--gp-ink-4)" }} aria-hidden />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Cerca per cognome, nome o matricola…"
            aria-label="Cerca persone"
          />
          <span className="gp-toolbar-kbd">/</span>
        </div>

        <PillMenu
          label={depot.length > 0 ? `Deposito: ${depot}` : "Tutti i depositi"}
          isOpen={openMenu === "depot"}
          onToggle={() => setOpenMenu(openMenu === "depot" ? null : "depot")}
        >
          <PillMenuItem
            active={depot === ""}
            onClick={() => {
              setDepot("");
              setOpenMenu(null);
            }}
          >
            Tutti i depositi
          </PillMenuItem>
          {(depotsQuery.data ?? []).map((d) => (
            <PillMenuItem
              key={d.codice}
              active={depot === d.codice}
              onClick={() => {
                setDepot(d.codice);
                setOpenMenu(null);
              }}
            >
              <span style={{ fontWeight: 600 }}>{d.codice}</span>{" "}
              <span style={{ color: "var(--gp-ink-4)" }}>· {d.display_name}</span>
            </PillMenuItem>
          ))}
        </PillMenu>

        <PillMenu
          label={profilo.length > 0 ? `Profilo: ${profilo}` : "Profilo PdC"}
          isOpen={openMenu === "profilo"}
          onToggle={() => setOpenMenu(openMenu === "profilo" ? null : "profilo")}
        >
          <PillMenuItem
            active={profilo === ""}
            onClick={() => {
              setProfilo("");
              setOpenMenu(null);
            }}
          >
            Tutti i profili
          </PillMenuItem>
          {profileOptions.map((p) => (
            <PillMenuItem
              key={p}
              active={profilo === p}
              onClick={() => {
                setProfilo(p);
                setOpenMenu(null);
              }}
            >
              {p}
            </PillMenuItem>
          ))}
        </PillMenu>

        <PillMenu
          label={STATUS_OPTIONS.find((s) => s.id === statusFilter)?.label ?? "Stato oggi"}
          isOpen={openMenu === "status"}
          onToggle={() => setOpenMenu(openMenu === "status" ? null : "status")}
        >
          {STATUS_OPTIONS.map((s) => (
            <PillMenuItem
              key={s.id}
              active={statusFilter === s.id}
              onClick={() => {
                setStatusFilter(s.id);
                setOpenMenu(null);
              }}
            >
              {s.label}
            </PillMenuItem>
          ))}
        </PillMenu>
      </div>

      {/* Header riga mono. */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "36px 1fr 100px 140px 60px 110px 14px",
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
        <span>Cognome e nome · Matricola</span>
        <span>Profilo</span>
        <span>Deposito</span>
        <span>Anni</span>
        <span>Stato oggi</span>
        <span />
      </div>

      {persone.isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Spinner label="Caricamento persone…" />
        </div>
      ) : persone.isError ? (
        <p
          role="alert"
          className="rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
        >
          Errore caricamento persone: {persone.error?.message ?? "errore sconosciuto"}
        </p>
      ) : filtered.length === 0 ? (
        <div
          style={{
            padding: "48px 24px",
            textAlign: "center",
            color: "var(--gp-ink-4)",
            fontSize: 13,
            border: "1px dashed var(--gp-line-2)",
            borderRadius: 8,
            marginTop: 16,
            background: "var(--gp-bg-rule)",
          }}
        >
          Nessuna persona corrisponde ai filtri selezionati.
        </div>
      ) : (
        <div>
          {filtered.map((p, i) => {
            const status = statusOf(p);
            const ye = yearsExperience(p);
            return (
              <Link
                key={p.id}
                to={`/gestione-personale/persone/${p.id}`}
                className="gp-person-row"
                aria-label={`Apri scheda di ${p.cognome} ${p.nome}`}
              >
                <span className="gp-idx">{String(i + 1).padStart(2, "0")}</span>
                <div>
                  <span className="gp-person-name">
                    <span className="gp-surname">{p.cognome}</span> {p.nome}
                  </span>
                  <div className="gp-person-meta">matr. {p.codice_dipendente}</div>
                </div>
                <span className="gp-person-role">{p.profilo}</span>
                <span className="gp-person-deposit">
                  {p.depot_codice ?? "—"}
                </span>
                <span className="gp-person-years">{ye !== null ? `${ye}y` : "—"}</span>
                <span className={`gp-tag ${STATUS_TAG_CLASS[status]}`}>{STATUS_LABEL[status]}</span>
                <ChevronRight className="h-3.5 w-3.5" style={{ color: "var(--gp-ink-5)" }} aria-hidden />
              </Link>
            );
          })}
        </div>
      )}
    </section>
  );
}

interface PillMenuProps {
  label: string;
  isOpen: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}

function PillMenu({ label, isOpen, onToggle, children }: PillMenuProps) {
  return (
    <div style={{ position: "relative" }}>
      <button
        type="button"
        className="gp-select-pill"
        onClick={(e) => {
          e.stopPropagation();
          onToggle();
        }}
        aria-haspopup="menu"
        aria-expanded={isOpen}
      >
        {label}
        <ChevronDown className="h-3 w-3" aria-hidden />
      </button>
      {isOpen && (
        <div
          role="menu"
          onClick={(e) => e.stopPropagation()}
          style={{
            position: "absolute",
            top: "calc(100% + 4px)",
            left: 0,
            zIndex: 20,
            background: "var(--gp-bg-elev)",
            border: "1px solid var(--gp-line-2)",
            borderRadius: 6,
            boxShadow: "0 12px 24px -4px rgba(14,17,22,0.18)",
            minWidth: 220,
            maxHeight: 320,
            overflowY: "auto",
            padding: 4,
          }}
        >
          {children}
        </div>
      )}
    </div>
  );
}

function PillMenuItem({
  children,
  active,
  onClick,
}: {
  children: React.ReactNode;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      style={{
        display: "flex",
        width: "100%",
        textAlign: "left",
        padding: "8px 10px",
        fontSize: 12.5,
        background: active ? "rgba(0,98,204,0.08)" : "transparent",
        color: active ? "#0062CC" : "var(--gp-ink-2)",
        border: 0,
        borderRadius: 4,
        cursor: "pointer",
        fontFamily: "inherit",
        fontWeight: active ? 600 : 500,
      }}
      onMouseEnter={(e) => {
        if (!active) e.currentTarget.style.background = "var(--gp-bg-rule)";
      }}
      onMouseLeave={(e) => {
        if (!active) e.currentTarget.style.background = "transparent";
      }}
    >
      {children}
    </button>
  );
}
