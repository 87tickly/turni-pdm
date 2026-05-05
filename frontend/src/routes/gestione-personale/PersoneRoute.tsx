import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Search, Users } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { Spinner } from "@/components/ui/Spinner";
import { useDepots } from "@/hooks/useAnagrafiche";
import { usePersone } from "@/hooks/useGestionePersonale";
import { cn } from "@/lib/utils";

/**
 * Sprint 7.9 MR ζ — Anagrafica PdC (Gestione Personale).
 *
 * Tabella filtrabile con tutte le persone attive dell'azienda corrente,
 * arricchita con il deposito di residenza e il tipo di indisponibilità
 * in corso oggi (badge a destra del nome).
 */
export function GestionePersonalePersoneRoute() {
  const [search, setSearch] = useState("");
  const [depot, setDepot] = useState<string>("");

  const persone = usePersone({
    search: search.length > 0 ? search : undefined,
    depot: depot.length > 0 ? depot : undefined,
    only_active: true,
  });
  const depotsQuery = useDepots();

  const totale = persone.data?.length ?? 0;
  const inServizio = useMemo(
    () => (persone.data ?? []).filter((p) => p.indisponibilita_oggi === null).length,
    [persone.data],
  );

  return (
    <div className="flex flex-col gap-5">
      <div className="text-xs text-muted-foreground">
        <Link to="/gestione-personale/dashboard" className="hover:text-primary">
          Home
        </Link>
        <span className="mx-1 text-muted-foreground/40">/</span>
        Anagrafica PdC
      </div>

      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-primary">
            <Users className="h-6 w-6 text-primary/70" aria-hidden />
            Anagrafica PdC
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Personale di macchina dell'azienda. Cerca per nome/cognome/codice
            dipendente, oppure filtra per deposito di residenza.
          </p>
        </div>
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" aria-hidden />
            <span>
              <span className="font-mono tabular-nums text-foreground">{inServizio}</span> in servizio
            </span>
          </span>
          <span className="text-muted-foreground/40">|</span>
          <span>
            <span className="font-mono tabular-nums text-foreground">{totale}</span>{" "}
            {depot.length > 0 || search.length > 0 ? "trovati" : "totali"}
          </span>
        </div>
      </header>

      {/* filtri */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[260px]">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            type="search"
            placeholder="Cerca per nome, cognome o matricola…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <select
          value={depot}
          onChange={(e) => setDepot(e.target.value)}
          className="h-10 rounded-md border border-input bg-white px-3 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">Tutti i depositi</option>
          {(depotsQuery.data ?? []).map((d) => (
            <option key={d.codice} value={d.codice}>
              {d.codice} · {d.display_name}
            </option>
          ))}
        </select>
      </div>

      {persone.isLoading ? (
        <div className="flex items-center justify-center rounded-md border border-border bg-white py-16">
          <Spinner label="Caricamento PdC…" />
        </div>
      ) : persone.isError ? (
        <p className="rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive" role="alert">
          Errore caricamento PdC: {persone.error?.message ?? "errore sconosciuto"}
        </p>
      ) : (persone.data ?? []).length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 rounded-md border border-dashed border-border bg-white py-16 text-center">
          <Users className="h-10 w-10 text-muted-foreground/40" aria-hidden />
          <h2 className="text-base font-semibold">Nessun PdC trovato</h2>
          <p className="max-w-md text-sm text-muted-foreground">
            Nessuna corrispondenza con i filtri impostati.
          </p>
        </div>
      ) : (
        <section className="overflow-hidden rounded-lg border border-border bg-white">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50 text-[10px] uppercase tracking-wider text-muted-foreground">
                  <th className="w-12 px-3 py-2 text-left font-semibold">#</th>
                  <th className="w-28 px-3 py-2 text-left font-semibold">Matricola</th>
                  <th className="px-3 py-2 text-left font-semibold">Cognome e nome</th>
                  <th className="w-44 px-3 py-2 text-left font-semibold">Deposito</th>
                  <th className="w-20 px-3 py-2 text-left font-semibold">Profilo</th>
                  <th className="w-32 px-3 py-2 text-left font-semibold">Stato oggi</th>
                  <th className="w-8 px-3 py-2" aria-hidden />
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {(persone.data ?? []).map((p, i) => (
                  <tr
                    key={p.id}
                    className="transition-colors hover:bg-primary/[0.03]"
                  >
                    <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground">
                      {String(i + 1).padStart(2, "0")}
                    </td>
                    <td className="px-3 py-2.5 font-mono text-[12px] text-muted-foreground">
                      {p.codice_dipendente}
                    </td>
                    <td className="px-3 py-2.5">
                      <Link
                        to={`/gestione-personale/persone/${p.id}`}
                        className="font-medium text-foreground hover:text-primary hover:underline"
                      >
                        <span className="uppercase">{p.cognome}</span>{" "}
                        <span className="text-foreground/80">{p.nome}</span>
                      </Link>
                    </td>
                    <td className="px-3 py-2.5">
                      {p.depot_codice !== null ? (
                        <Link
                          to={`/gestione-personale/depositi/${encodeURIComponent(p.depot_codice)}`}
                          className="font-mono text-[12px] text-primary hover:underline"
                        >
                          {p.depot_codice}
                        </Link>
                      ) : (
                        <span className="text-muted-foreground/50">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-[12px] text-muted-foreground">
                      {p.profilo}
                    </td>
                    <td className="px-3 py-2.5">
                      <StatoOggiBadge tipo={p.indisponibilita_oggi} />
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <ArrowRight className="h-3 w-3 text-muted-foreground/40" aria-hidden />
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

function StatoOggiBadge({ tipo }: { tipo: string | null }) {
  if (tipo === null) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-emerald-700">
        <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" aria-hidden />
        in servizio
      </span>
    );
  }
  const map: Record<string, { label: string; cls: string }> = {
    ferie: { label: "Ferie", cls: "bg-sky-100 text-sky-800 border-sky-200" },
    malattia: { label: "Malattia", cls: "bg-red-100 text-red-800 border-red-200" },
    ROL: { label: "ROL", cls: "bg-violet-100 text-violet-800 border-violet-200" },
    sciopero: { label: "Sciopero", cls: "bg-amber-100 text-amber-800 border-amber-200" },
    formazione: { label: "Formazione", cls: "bg-indigo-100 text-indigo-800 border-indigo-200" },
    congedo: { label: "Congedo", cls: "bg-slate-100 text-slate-800 border-slate-200" },
  };
  const entry = map[tipo] ?? { label: tipo, cls: "bg-muted text-muted-foreground border-border" };
  return (
    <Badge variant="outline" className={cn("text-[10px]", entry.cls)}>
      {entry.label}
    </Badge>
  );
}
