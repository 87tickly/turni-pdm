import { Link, useLocation, useParams } from "react-router-dom";
import { AlertCircle, AlertTriangle, ArrowLeft, Bed, Moon } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { useTurnoPdcDettaglio } from "@/hooks/useTurniPdc";
import { ApiError } from "@/lib/api/client";
import type {
  TurnoPdcBlocco,
  TurnoPdcDettaglio,
  TurnoPdcGiornata,
} from "@/lib/api/turniPdc";

export function TurnoPdcDettaglioRoute() {
  const { turnoId: turnoIdParam } = useParams<{ turnoId: string }>();
  const turnoId = turnoIdParam !== undefined ? Number(turnoIdParam) : undefined;
  const location = useLocation();
  // Sprint 7.3 MR 3: la stessa pagina è raggiungibile sia da
  // `/pianificatore-giro/turni-pdc/:id` (1° ruolo, drilldown da editor
  // giro) sia da `/pianificatore-pdc/turni/:id` (2° ruolo, drilldown da
  // lista turni cross-giro). Il back-link va alla lista del ruolo da
  // cui si è arrivati.
  const isPdcRoute = location.pathname.startsWith("/pianificatore-pdc");
  const query = useTurnoPdcDettaglio(turnoId);

  if (turnoId === undefined || Number.isNaN(turnoId)) {
    return <ErrorBlock message="ID turno PdC non valido nell'URL." />;
  }

  if (query.isLoading) {
    return (
      <div className="flex items-center justify-center rounded-md border border-border bg-white py-16">
        <Spinner label="Caricamento turno PdC…" />
      </div>
    );
  }

  if (query.isError) {
    const msg =
      query.error instanceof ApiError ? query.error.message : (query.error as Error).message;
    return <ErrorBlock message={msg} onRetry={() => void query.refetch()} />;
  }

  if (query.data === undefined) {
    return <ErrorBlock message="Turno PdC non trovato." />;
  }

  const turno = query.data;
  const meta = turno.generation_metadata_json;
  const giroId = meta.giro_materiale_id ?? null;
  const violazioni = meta.violazioni ?? [];
  const frGiornate = meta.fr_giornate ?? [];

  return (
    <div className="flex flex-col gap-5">
      <Link
        to={
          isPdcRoute
            ? "/pianificatore-pdc/turni"
            : giroId !== null
              ? `/pianificatore-giro/giri/${giroId}/turni-pdc`
              : "/pianificatore-giro/programmi"
        }
        className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-primary"
      >
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> Lista turni PdC
      </Link>

      <Header turno={turno} />
      <Stats turno={turno} />

      {(violazioni.length > 0 || frGiornate.length > 0) && (
        <Avvisi violazioni={violazioni} frGiornate={frGiornate} />
      )}

      <section className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold tracking-tight">
          Giornate ({turno.giornate.length})
        </h2>
        <div className="flex flex-col gap-3">
          {turno.giornate.map((g) => (
            <GiornataPanel key={g.id} giornata={g} />
          ))}
        </div>
      </section>
    </div>
  );
}

function Header({ turno }: { turno: TurnoPdcDettaglio }) {
  const meta = turno.generation_metadata_json;
  return (
    <header className="flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">{turno.codice}</h1>
        <Badge variant="outline">{turno.impianto}</Badge>
        <Badge variant="secondary">{turno.profilo}</Badge>
        {typeof meta.giro_numero_turno === "string" && (
          <span className="text-xs text-muted-foreground">
            ← derivato da {meta.giro_numero_turno}
          </span>
        )}
      </div>
      <p className="text-sm text-muted-foreground">
        #{turno.id} · ciclo {turno.ciclo_giorni} giorn{turno.ciclo_giorni === 1 ? "o" : "i"} ·
        valido da {turno.valido_da} · stato {turno.stato}
      </p>
    </header>
  );
}

function Stats({ turno }: { turno: TurnoPdcDettaglio }) {
  const totPrestazione = turno.giornate.reduce((s, g) => s + g.prestazione_min, 0);
  const totCondotta = turno.giornate.reduce((s, g) => s + g.condotta_min, 0);
  const totRefezione = turno.giornate.reduce((s, g) => s + g.refezione_min, 0);
  return (
    <div className="grid grid-cols-2 gap-3 rounded-md border border-border bg-white p-4 md:grid-cols-4">
      <Stat label="Prestazione totale" value={formatHM(totPrestazione)} />
      <Stat label="Condotta totale" value={formatHM(totCondotta)} />
      <Stat label="Refezione totale" value={formatHM(totRefezione)} />
      <Stat label="Giornate" value={String(turno.giornate.length)} />
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <span className="text-base font-semibold tabular-nums text-foreground">{value}</span>
    </div>
  );
}

function Avvisi({
  violazioni,
  frGiornate,
}: {
  violazioni: string[];
  frGiornate: { giornata: number; stazione: string; ore: number }[];
}) {
  return (
    <div className="flex flex-col gap-2">
      {violazioni.length > 0 && (
        <details className="rounded-md border border-amber-300 bg-amber-50 text-sm text-amber-900">
          <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 font-medium">
            <AlertTriangle className="h-4 w-4" aria-hidden /> {violazioni.length} violazion
            {violazioni.length === 1 ? "e" : "i"} normativa
          </summary>
          <ul className="space-y-1 px-4 pb-3 font-mono text-xs">
            {violazioni.map((v, i) => (
              <li key={i}>· {v}</li>
            ))}
          </ul>
          <p className="border-t border-amber-200 px-3 py-2 text-xs italic">
            MVP Sprint 7.2: il builder non splitta ancora i turni con CV
            intermedio. Sprint 7.4 introdurrà lo split per rispettare
            prestazione/condotta max.
          </p>
        </details>
      )}
      {frGiornate.length > 0 && (
        <div className="flex flex-col gap-1 rounded-md border border-violet-200 bg-violet-50 px-3 py-2 text-sm text-violet-900">
          <div className="flex items-center gap-2 font-medium">
            <Bed className="h-4 w-4" aria-hidden /> {frGiornate.length} dormit
            {frGiornate.length === 1 ? "a" : "e"} fuori residenza (FR)
          </div>
          <ul className="space-y-0.5 pl-6 text-xs">
            {frGiornate.map((fr, i) => (
              <li key={i}>
                Giornata {fr.giornata}: pernotto a{" "}
                <span className="font-mono">{fr.stazione}</span> · {fr.ore.toFixed(1)}h
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function GiornataPanel({ giornata }: { giornata: TurnoPdcGiornata }) {
  return (
    <div className="overflow-hidden rounded-md border border-border bg-white">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-secondary/40 px-4 py-2">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="font-semibold">Giornata {giornata.numero_giornata}</span>
          <Badge variant="outline" className="text-[10px]">
            {giornata.variante_calendario}
          </Badge>
          {giornata.is_notturno && (
            <Badge variant="secondary" className="gap-1 text-[10px]">
              <Moon className="h-3 w-3" aria-hidden /> notturno
            </Badge>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          <span className="tabular-nums">
            {giornata.inizio_prestazione ?? "?"} → {giornata.fine_prestazione ?? "?"}
          </span>
          <span>
            <span className="font-medium text-foreground">
              {formatHM(giornata.prestazione_min)}
            </span>{" "}
            prestazione
          </span>
          <span>
            <span className="font-medium text-foreground">{formatHM(giornata.condotta_min)}</span>{" "}
            condotta
          </span>
          {giornata.refezione_min > 0 && (
            <span>
              <span className="font-medium text-foreground">
                {formatHM(giornata.refezione_min)}
              </span>{" "}
              refez
            </span>
          )}
        </div>
      </div>
      <div className="flex flex-col gap-3 p-3">
        <GanttRow blocchi={giornata.blocchi} />
        <BlocchiList blocchi={giornata.blocchi} />
      </div>
    </div>
  );
}

const ORE = Array.from({ length: 24 }, (_, i) => i);
const MINUTI_GIORNO = 24 * 60;

function GanttRow({ blocchi }: { blocchi: TurnoPdcBlocco[] }) {
  return (
    <div className="overflow-x-auto">
      <div className="relative min-w-[768px]">
        <div className="grid grid-cols-24 border-b border-border text-[10px] text-muted-foreground">
          {ORE.map((h) => (
            <div key={h} className="border-l border-border/60 px-1 py-0.5 first:border-l-0">
              {h.toString().padStart(2, "0")}
            </div>
          ))}
        </div>
        <div className="relative h-9 border-b border-border bg-secondary/20">
          {blocchi.map((b) => (
            <GanttBlocco key={b.id} blocco={b} />
          ))}
        </div>
      </div>
    </div>
  );
}

function timeToMin(t: string | null): number | null {
  if (t === null || t.length === 0) return null;
  const parts = t.split(":");
  if (parts.length < 2) return null;
  const h = Number.parseInt(parts[0], 10);
  const m = Number.parseInt(parts[1], 10);
  if (Number.isNaN(h) || Number.isNaN(m)) return null;
  return h * 60 + m;
}

function colorForTipoEvento(tipo: string): string {
  switch (tipo) {
    case "CONDOTTA":
      return "bg-primary text-primary-foreground";
    case "VETTURA":
      return "bg-sky-200 text-sky-900";
    case "REFEZ":
      return "bg-emerald-200 text-emerald-900";
    case "ACCp":
    case "ACCa":
      return "bg-amber-200 text-amber-900";
    case "PK":
    case "SCOMP":
      return "bg-secondary text-secondary-foreground";
    case "PRESA":
    case "FINE":
      return "bg-slate-300 text-slate-800";
    case "CVp":
    case "CVa":
      return "bg-orange-200 text-orange-900";
    case "DORMITA":
      return "bg-violet-300 text-violet-900";
    default:
      return "bg-muted text-muted-foreground";
  }
}

function GanttBlocco({ blocco }: { blocco: TurnoPdcBlocco }) {
  const inizio = timeToMin(blocco.ora_inizio);
  const fine = timeToMin(blocco.ora_fine);
  if (inizio === null || fine === null) return null;
  const left = (inizio / MINUTI_GIORNO) * 100;
  const width = Math.max(0.5, ((fine - inizio) / MINUTI_GIORNO) * 100);
  const da = stazioneLabel(blocco.stazione_da_nome, blocco.stazione_da_codice);
  const a = stazioneLabel(blocco.stazione_a_nome, blocco.stazione_a_codice);
  const treno = blocco.numero_treno !== null ? `\nTreno ${blocco.numero_treno}` : "";
  const note = blocco.accessori_note !== null ? `\n${blocco.accessori_note}` : "";
  const tooltip = `${blocco.tipo_evento} · ${blocco.ora_inizio ?? "?"}→${blocco.ora_fine ?? "?"}\n${da} → ${a}${treno}${note}`;
  return (
    <div
      className={`absolute top-1 flex h-7 items-center overflow-hidden rounded px-1.5 text-[10px] font-medium ${colorForTipoEvento(blocco.tipo_evento)}`}
      style={{ left: `${left}%`, width: `${width}%` }}
      title={tooltip}
    >
      <span className="truncate">{bloccoLabel(blocco)}</span>
    </div>
  );
}

function bloccoLabel(b: TurnoPdcBlocco): string {
  if (b.tipo_evento === "CONDOTTA" && b.numero_treno !== null && b.numero_treno.length > 0) {
    return b.numero_treno;
  }
  if (b.tipo_evento === "DORMITA") return "FR";
  return b.tipo_evento;
}

function stazioneLabel(nome: string | null, codice: string | null): string {
  if (nome !== null && nome.length > 0) return nome;
  if (codice !== null && codice.length > 0) return codice;
  return "—";
}

function BlocchiList({ blocchi }: { blocchi: TurnoPdcBlocco[] }) {
  if (blocchi.length === 0) {
    return (
      <p className="px-3 py-2 text-xs italic text-muted-foreground">
        Nessun blocco in questa giornata.
      </p>
    );
  }
  return (
    <details className="rounded-md border border-border bg-white text-xs">
      <summary className="cursor-pointer px-3 py-2 font-medium text-muted-foreground">
        Sequenza blocchi ({blocchi.length})
      </summary>
      <table className="w-full">
        <thead className="bg-secondary/40 text-[10px] uppercase tracking-wider text-muted-foreground">
          <tr>
            <th className="px-2 py-1 text-left">#</th>
            <th className="px-2 py-1 text-left">Tipo</th>
            <th className="px-2 py-1 text-left">Treno</th>
            <th className="px-2 py-1 text-left">Da</th>
            <th className="px-2 py-1 text-left">A</th>
            <th className="px-2 py-1 text-left">Inizio</th>
            <th className="px-2 py-1 text-left">Fine</th>
            <th className="px-2 py-1 text-right">Min</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {blocchi.map((b) => (
            <tr key={b.id}>
              <td className="px-2 py-1 font-mono text-muted-foreground">{b.seq}</td>
              <td className="px-2 py-1">
                <BloccoTipoBadge tipo={b.tipo_evento} />
              </td>
              <td className="px-2 py-1">
                <TrenoCell blocco={b} />
              </td>
              <td className="px-2 py-1">
                <StazioneCell nome={b.stazione_da_nome} codice={b.stazione_da_codice} />
              </td>
              <td className="px-2 py-1">
                <StazioneCell nome={b.stazione_a_nome} codice={b.stazione_a_codice} />
              </td>
              <td className="px-2 py-1 tabular-nums">{b.ora_inizio ?? "—"}</td>
              <td className="px-2 py-1 tabular-nums">{b.ora_fine ?? "—"}</td>
              <td className="px-2 py-1 text-right tabular-nums">{b.durata_min ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

function TrenoCell({ blocco }: { blocco: TurnoPdcBlocco }) {
  if (blocco.numero_treno === null) return <span>—</span>;
  const idx = blocco.numero_treno_variante_indice;
  const tot = blocco.numero_treno_variante_totale;
  const showVariante = idx !== null && tot !== null && tot > 1;
  return (
    <div className="flex flex-col leading-tight">
      <span className="font-mono font-medium">{blocco.numero_treno}</span>
      {showVariante && (
        <span
          className="text-[10px] text-muted-foreground"
          title={`Questa corsa ha ${tot} varianti (origini/orari/periodi diversi)`}
        >
          variante {idx}/{tot}
        </span>
      )}
    </div>
  );
}

function StazioneCell({ nome, codice }: { nome: string | null; codice: string | null }) {
  if (nome === null && codice === null) return <span>—</span>;
  return (
    <div className="flex flex-col leading-tight">
      <span className="font-medium">{nome ?? codice}</span>
      {nome !== null && codice !== null && (
        <span className="font-mono text-[10px] text-muted-foreground">{codice}</span>
      )}
    </div>
  );
}

function BloccoTipoBadge({ tipo }: { tipo: string }) {
  switch (tipo) {
    case "CONDOTTA":
      return <Badge variant="default">condotta</Badge>;
    case "VETTURA":
      return <Badge variant="secondary">vettura</Badge>;
    case "REFEZ":
      return <Badge variant="success">refez</Badge>;
    case "ACCp":
      return <Badge variant="warning">ACCp</Badge>;
    case "ACCa":
      return <Badge variant="warning">ACCa</Badge>;
    case "PK":
      return <Badge variant="outline">PK</Badge>;
    case "SCOMP":
      return <Badge variant="outline">S.COMP</Badge>;
    case "PRESA":
      return <Badge variant="outline">presa</Badge>;
    case "FINE":
      return <Badge variant="outline">fine</Badge>;
    case "CVp":
      return <Badge variant="warning">CVp</Badge>;
    case "CVa":
      return <Badge variant="warning">CVa</Badge>;
    case "DORMITA":
      return <Badge variant="secondary">FR</Badge>;
    default:
      return <Badge variant="outline">{tipo}</Badge>;
  }
}

function formatHM(min: number): string {
  if (min === 0) return "0h00";
  const h = Math.floor(min / 60);
  const m = min % 60;
  return `${h}h${m.toString().padStart(2, "0")}`;
}

function ErrorBlock({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-4"
    >
      <AlertCircle className="mt-0.5 h-5 w-5 text-destructive" aria-hidden />
      <div className="flex flex-1 flex-col gap-2">
        <p className="text-sm font-medium text-destructive">{message}</p>
        {onRetry !== undefined && (
          <Button variant="outline" size="sm" onClick={onRetry} className="self-start">
            Riprova
          </Button>
        )}
      </div>
    </div>
  );
}
