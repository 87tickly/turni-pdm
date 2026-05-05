import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  BedDouble,
  Building2,
  CalendarDays,
  Heart,
  PencilLine,
  Plane,
  ShieldCheck,
} from "lucide-react";

import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { useIndisponibilita } from "@/hooks/useGestionePersonale";
import { cn } from "@/lib/utils";

type TabId = "tutte" | "ferie" | "malattia" | "rol" | "altre";

interface TabDef {
  id: TabId;
  label: string;
  tipos: string[]; // se vuoto = "tutte"
}

const TABS: TabDef[] = [
  { id: "tutte", label: "Tutte", tipos: [] },
  { id: "ferie", label: "Ferie", tipos: ["ferie"] },
  { id: "malattia", label: "Malattia", tipos: ["malattia"] },
  { id: "rol", label: "ROL", tipos: ["ROL"] },
  { id: "altre", label: "Altre", tipos: ["sciopero", "formazione", "congedo"] },
];

/**
 * Sprint 7.9 MR ζ — Indisponibilità (ferie/malattia/ROL/altro).
 *
 * Lista delle indisponibilità con tab di filtro per categoria. Per
 * ognuna mostra persona, deposito, periodo, durata, stato approvazione.
 */
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
    list.forEach((i) => {
      if (i.tipo === "ferie") c.ferie += 1;
      else if (i.tipo === "malattia") c.malattia += 1;
      else if (i.tipo === "ROL") c.rol += 1;
      else c.altre += 1;
    });
    return c;
  }, [all.data]);

  return (
    <div className="flex flex-col gap-5">
      <div className="text-xs text-muted-foreground">
        <Link to="/gestione-personale/dashboard" className="hover:text-primary">
          Home
        </Link>
        <span className="mx-1 text-muted-foreground/40">/</span>
        Indisponibilità
      </div>

      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-primary">
            <CalendarDays className="h-6 w-6 text-primary/70" aria-hidden />
            Ferie · Malattia · ROL · Altre
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Tutte le indisponibilità delle matricole attive. Usa i tab per
            filtrare per tipo, attiva il toggle per vedere solo quelle in
            corso oggi.
          </p>
        </div>
        <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
          <input
            type="checkbox"
            checked={soloAttiveOggi}
            onChange={(e) => setSoloAttiveOggi(e.target.checked)}
            className="h-4 w-4 rounded border-input text-primary focus:ring-2 focus:ring-ring"
          />
          Solo in corso oggi
        </label>
      </header>

      {/* Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-border">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={cn(
              "relative -mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors",
              tab === t.id
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            <span className="flex items-center gap-1.5">
              <TabIcon id={t.id} />
              {t.label}
              <span
                className={cn(
                  "rounded-full px-1.5 py-0.5 text-[10px] font-mono tabular-nums",
                  tab === t.id ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground",
                )}
              >
                {counts[t.id]}
              </span>
            </span>
          </button>
        ))}
      </div>

      {all.isLoading ? (
        <div className="flex items-center justify-center rounded-md border border-border bg-white py-16">
          <Spinner label="Caricamento indisponibilità…" />
        </div>
      ) : all.isError ? (
        <p className="rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive" role="alert">
          Errore: {all.error?.message ?? "errore sconosciuto"}
        </p>
      ) : filtered.length === 0 ? (
        <Card className="flex flex-col items-center gap-3 py-12 text-center">
          <CalendarDays className="h-10 w-10 text-muted-foreground/40" aria-hidden />
          <h2 className="text-base font-semibold">Nessuna voce</h2>
          <p className="max-w-md text-sm text-muted-foreground">
            Nessuna indisponibilità trovata per questo filtro.
          </p>
        </Card>
      ) : (
        <section className="overflow-hidden rounded-lg border border-border bg-white">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50 text-[10px] uppercase tracking-wider text-muted-foreground">
                  <th className="px-3 py-2 text-left font-semibold">Persona</th>
                  <th className="w-32 px-3 py-2 text-left font-semibold">Deposito</th>
                  <th className="w-28 px-3 py-2 text-left font-semibold">Tipo</th>
                  <th className="px-3 py-2 text-left font-semibold">Periodo</th>
                  <th className="w-20 px-3 py-2 text-right font-semibold">Giorni</th>
                  <th className="w-28 px-3 py-2 text-left font-semibold">Stato</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {filtered.map((i) => (
                  <tr key={i.id} className="transition-colors hover:bg-primary/[0.03]">
                    <td className="px-3 py-2.5">
                      <Link
                        to={`/gestione-personale/persone/${i.persona_id}`}
                        className="font-medium text-foreground hover:text-primary hover:underline"
                      >
                        <span className="uppercase">{i.persona_cognome}</span>{" "}
                        <span className="text-foreground/80">{i.persona_nome}</span>
                      </Link>
                      <div className="font-mono text-[10px] text-muted-foreground">
                        {i.persona_codice_dipendente}
                      </div>
                    </td>
                    <td className="px-3 py-2.5">
                      {i.depot_codice !== null ? (
                        <Link
                          to={`/gestione-personale/depositi/${encodeURIComponent(i.depot_codice)}`}
                          className="inline-flex items-center gap-1 font-mono text-[12px] text-primary hover:underline"
                        >
                          <Building2 className="h-3 w-3 opacity-70" aria-hidden />
                          {i.depot_codice}
                        </Link>
                      ) : (
                        <span className="text-muted-foreground/50">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5">
                      <TipoIcon tipo={i.tipo} />
                      <span className="ml-1.5 text-[12px] capitalize">{i.tipo}</span>
                    </td>
                    <td className="px-3 py-2.5 text-[12px] text-muted-foreground">
                      {formatRange(i.data_inizio, i.data_fine)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono tabular-nums">
                      {i.giorni_totali}
                    </td>
                    <td className="px-3 py-2.5">
                      {i.is_approvato ? (
                        <span className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-emerald-700">
                          <ShieldCheck className="h-3 w-3" aria-hidden />
                          approvata
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-amber-700">
                          <PencilLine className="h-3 w-3" aria-hidden />
                          in attesa
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

function TabIcon({ id }: { id: TabId }) {
  switch (id) {
    case "ferie":
      return <Plane className="h-3.5 w-3.5" aria-hidden />;
    case "malattia":
      return <Heart className="h-3.5 w-3.5" aria-hidden />;
    case "rol":
      return <BedDouble className="h-3.5 w-3.5" aria-hidden />;
    case "altre":
      return <CalendarDays className="h-3.5 w-3.5" aria-hidden />;
    default:
      return <CalendarDays className="h-3.5 w-3.5" aria-hidden />;
  }
}

function TipoIcon({ tipo }: { tipo: string }) {
  if (tipo === "ferie") return <Plane className="inline h-3 w-3 text-sky-600" aria-hidden />;
  if (tipo === "malattia") return <Heart className="inline h-3 w-3 text-red-600" aria-hidden />;
  if (tipo === "ROL") return <BedDouble className="inline h-3 w-3 text-violet-600" aria-hidden />;
  return <CalendarDays className="inline h-3 w-3 text-amber-600" aria-hidden />;
}

function formatRange(from: string, to: string): string {
  const f = new Date(from).toLocaleDateString("it-IT", { day: "2-digit", month: "short" });
  const t = new Date(to).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
  return `${f} → ${t}`;
}
