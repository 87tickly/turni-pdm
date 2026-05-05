import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  CalendarRange,
  ChevronLeft,
  ChevronRight,
  Info,
} from "lucide-react";

import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { useDepots } from "@/hooks/useAnagrafiche";
import {
  useIndisponibilita,
  usePersoneByDepot,
} from "@/hooks/useGestionePersonale";
import { cn } from "@/lib/utils";

const GIORNI_VISTA = 14;
const WEEKDAY_LABELS = ["L", "M", "M", "G", "V", "S", "D"];

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

/**
 * Sprint 7.9 MR ζ — Calendario assegnazioni Gestione Personale.
 *
 * Vista 14 giorni × persone del deposito selezionato. Le celle mostrano
 * lo stato della persona in quel giorno: turno (placeholder), ferie,
 * malattia, ROL, altro. Le assegnazioni effettive ai turni PdC saranno
 * collegate quando il builder Pianificatore PdC avrà popolato
 * `turno_pdc_giornata` su volume.
 */
export function GestionePersonaleCalendarioRoute() {
  const depots = useDepots();
  const [depotCodice, setDepotCodice] = useState<string>("");
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

  return (
    <div className="flex flex-col gap-5">
      <div className="text-xs text-muted-foreground">
        <Link to="/gestione-personale/dashboard" className="hover:text-primary">
          Home
        </Link>
        <span className="mx-1 text-muted-foreground/40">/</span>
        Calendario
      </div>

      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-primary">
            <CalendarRange className="h-6 w-6 text-primary/70" aria-hidden />
            Calendario assegnazioni
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Vista a 14 giorni per deposito. Celle: turno (placeholder),
            ferie, malattia, ROL, altre assenze.
          </p>
        </div>
      </header>

      {/* Filtri & navigazione date */}
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={depotCodice}
          onChange={(e) => setDepotCodice(e.target.value)}
          className="h-10 rounded-md border border-input bg-white px-3 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">Seleziona un deposito…</option>
          {(depots.data ?? []).map((d) => (
            <option key={d.codice} value={d.codice}>
              {d.codice} · {d.display_name}
            </option>
          ))}
        </select>

        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={() => setStartDate((d) => addDays(d, -7))}
            className="grid h-9 w-9 place-items-center rounded-md border border-border bg-white text-muted-foreground transition hover:border-primary/50 hover:text-foreground"
            aria-label="Settimana precedente"
          >
            <ChevronLeft className="h-4 w-4" aria-hidden />
          </button>
          <span className="rounded-md border border-border bg-white px-3 py-1.5 text-sm font-medium text-foreground">
            {giorni[0].toLocaleDateString("it-IT", { day: "2-digit", month: "short" })}{" "}
            →{" "}
            {giorni[giorni.length - 1].toLocaleDateString("it-IT", {
              day: "2-digit",
              month: "short",
              year: "numeric",
            })}
          </span>
          <button
            type="button"
            onClick={() => setStartDate((d) => addDays(d, 7))}
            className="grid h-9 w-9 place-items-center rounded-md border border-border bg-white text-muted-foreground transition hover:border-primary/50 hover:text-foreground"
            aria-label="Settimana successiva"
          >
            <ChevronRight className="h-4 w-4" aria-hidden />
          </button>
        </div>
      </div>

      {/* Legenda */}
      <Card className="flex items-start gap-3 p-4">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground/70" aria-hidden />
        <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          <Legend color="bg-emerald-100 border-emerald-300 text-emerald-800" label="Turno (placeholder T)" />
          <Legend color="bg-sky-100 border-sky-300 text-sky-800" label="Ferie F" />
          <Legend color="bg-red-100 border-red-300 text-red-800" label="Malattia M" />
          <Legend color="bg-violet-100 border-violet-300 text-violet-800" label="ROL R" />
          <Legend color="bg-amber-100 border-amber-300 text-amber-800" label="Altro A" />
          <Legend color="bg-muted border-border text-muted-foreground" label="Riposo (sab/dom)" />
        </div>
      </Card>

      {depotCodice.length === 0 ? (
        <Card className="flex flex-col items-center gap-3 py-12 text-center">
          <CalendarRange className="h-10 w-10 text-muted-foreground/40" aria-hidden />
          <h2 className="text-base font-semibold">Seleziona un deposito</h2>
          <p className="max-w-md text-sm text-muted-foreground">
            Scegli un deposito dal menu sopra per visualizzare il calendario
            dei PdC residenti.
          </p>
        </Card>
      ) : persone.isLoading ? (
        <div className="flex items-center justify-center rounded-md border border-border bg-white py-16">
          <Spinner label="Caricamento PdC del deposito…" />
        </div>
      ) : (persone.data ?? []).length === 0 ? (
        <Card className="flex flex-col items-center gap-3 py-12 text-center">
          <CalendarRange className="h-10 w-10 text-muted-foreground/40" aria-hidden />
          <h2 className="text-base font-semibold">Nessun PdC nel deposito</h2>
          <p className="max-w-md text-sm text-muted-foreground">
            Il deposito selezionato non ha PdC residenti.
          </p>
        </Card>
      ) : (
        <section className="overflow-hidden rounded-lg border border-border bg-white">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="sticky left-0 z-10 bg-muted/50 px-3 py-2 text-left font-semibold uppercase tracking-wider text-muted-foreground min-w-[200px]">
                    PdC
                  </th>
                  {giorni.map((d) => (
                    <th
                      key={d.toISOString()}
                      className={cn(
                        "border-l border-border px-2 py-2 text-center font-mono font-semibold",
                        isWeekend(d)
                          ? "bg-muted/70 text-muted-foreground"
                          : "text-foreground",
                      )}
                    >
                      <div className="text-[9px] font-normal uppercase tracking-wider opacity-70">
                        {WEEKDAY_LABELS[(d.getDay() + 6) % 7]}
                      </div>
                      <div className="text-[11px] tabular-nums">
                        {d.getDate().toString().padStart(2, "0")}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(persone.data ?? []).map((p) => {
                  const indispMap = indispByPersonaDate.get(p.id);
                  return (
                    <tr key={p.id} className="border-b border-border/60">
                      <td className="sticky left-0 z-10 bg-white px-3 py-1.5">
                        <Link
                          to={`/gestione-personale/persone/${p.id}`}
                          className="text-[12px] font-medium text-foreground hover:text-primary hover:underline"
                        >
                          <span className="uppercase">{p.cognome}</span>{" "}
                          <span className="text-foreground/80">{p.nome}</span>
                        </Link>
                      </td>
                      {giorni.map((d) => {
                        const iso = formatISODate(d);
                        const indispTipo = indispMap?.get(iso);
                        return (
                          <td
                            key={iso}
                            className={cn(
                              "border-l border-border/60 p-1 text-center",
                              isWeekend(d) && "bg-muted/30",
                            )}
                          >
                            <CellaStato tipo={indispTipo} weekend={isWeekend(d)} />
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="border-t border-border bg-muted/30 px-4 py-2 text-[11px] text-muted-foreground">
            Le celle "T" rappresentano un turno-placeholder: l'integrazione con{" "}
            <span className="font-mono">turno_pdc_giornata</span> arriverà
            quando il builder PdC avrà popolato i turni reali su volume.
          </div>
        </section>
      )}
    </div>
  );
}

function CellaStato({ tipo, weekend }: { tipo: string | undefined; weekend: boolean }) {
  if (tipo !== undefined) {
    const map: Record<string, { letter: string; cls: string }> = {
      ferie: { letter: "F", cls: "bg-sky-100 border-sky-300 text-sky-800" },
      malattia: { letter: "M", cls: "bg-red-100 border-red-300 text-red-800" },
      ROL: { letter: "R", cls: "bg-violet-100 border-violet-300 text-violet-800" },
      sciopero: { letter: "S", cls: "bg-amber-100 border-amber-300 text-amber-800" },
      formazione: { letter: "Fo", cls: "bg-indigo-100 border-indigo-300 text-indigo-800" },
      congedo: { letter: "C", cls: "bg-slate-100 border-slate-300 text-slate-800" },
    };
    const e = map[tipo] ?? { letter: "A", cls: "bg-amber-100 border-amber-300 text-amber-800" };
    return (
      <span
        className={cn(
          "inline-flex h-6 w-7 items-center justify-center rounded border text-[10px] font-bold",
          e.cls,
        )}
        title={tipo}
      >
        {e.letter}
      </span>
    );
  }
  if (weekend) {
    return <span className="text-muted-foreground/40">—</span>;
  }
  // Default: cella turno placeholder
  return (
    <span
      className="inline-flex h-6 w-7 items-center justify-center rounded border border-emerald-300 bg-emerald-100 text-[10px] font-bold text-emerald-800"
      title="Turno (placeholder)"
    >
      T
    </span>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={cn("inline-block h-4 w-5 rounded border", color)} aria-hidden />
      {label}
    </span>
  );
}
