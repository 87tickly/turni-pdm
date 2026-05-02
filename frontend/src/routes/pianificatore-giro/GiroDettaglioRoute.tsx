import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AlertCircle, ArrowLeft, Users } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { useGiroDettaglio } from "@/hooks/useGiri";
import { useTurniPdcGiro } from "@/hooks/useTurniPdc";
import { ApiError } from "@/lib/api/client";
import type {
  GiroBlocco,
  GiroDettaglio,
  GiroGiornata,
  GiroVariante,
} from "@/lib/api/giri";
import { formatNumber } from "@/lib/format";
import { GeneraTurnoPdcDialog } from "@/routes/pianificatore-giro/GeneraTurnoPdcDialog";

export function GiroDettaglioRoute() {
  const { giroId: giroIdParam } = useParams<{ giroId: string }>();
  const giroId = giroIdParam !== undefined ? Number(giroIdParam) : undefined;
  const query = useGiroDettaglio(giroId);

  if (giroId === undefined || Number.isNaN(giroId)) {
    return <ErrorBlock message="ID giro non valido nell'URL." />;
  }

  if (query.isLoading) {
    return (
      <div className="flex items-center justify-center rounded-md border border-border bg-white py-16">
        <Spinner label="Caricamento giro…" />
      </div>
    );
  }

  if (query.isError) {
    const msg =
      query.error instanceof ApiError ? query.error.message : (query.error as Error).message;
    return <ErrorBlock message={msg} onRetry={() => void query.refetch()} />;
  }

  if (query.data === undefined) {
    return <ErrorBlock message="Giro non trovato." />;
  }

  const giro = query.data;
  const meta = giro.generation_metadata_json as Record<string, unknown>;
  const programmaId = typeof meta.programma_id === "number" ? meta.programma_id : null;
  const nVariantiTotale = giro.giornate.reduce((s, g) => s + g.varianti.length, 0);

  return (
    <div className="flex flex-col gap-5">
      <Link
        to={
          programmaId !== null
            ? `/pianificatore-giro/programmi/${programmaId}/giri`
            : "/pianificatore-giro/programmi"
        }
        className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-primary"
      >
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> Lista giri
      </Link>

      <HeaderRow giro={giro} nVariantiTotale={nVariantiTotale} />
      <Stats giro={giro} nVariantiTotale={nVariantiTotale} />

      <section className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold tracking-tight">Giornate ({giro.numero_giornate})</h2>
        <div className="flex flex-col gap-3">
          {giro.giornate.map((g) => (
            <GiornataPanel key={g.id} giornata={g} />
          ))}
        </div>
      </section>
    </div>
  );
}

function HeaderRow({ giro, nVariantiTotale }: { giro: GiroDettaglio; nVariantiTotale: number }) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const turniQuery = useTurniPdcGiro(giro.id);
  const turni = turniQuery.data ?? [];

  return (
    <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">{giro.numero_turno}</h1>
          <Badge variant="outline">{giro.tipo_materiale}</Badge>
          {nVariantiTotale > giro.numero_giornate && (
            <Badge
              variant="secondary"
              title="Almeno una giornata del giro ha varianti calendariali multiple (PDF Trenord-style)."
            >
              {nVariantiTotale} varianti
            </Badge>
          )}
        </div>
        <p className="text-sm text-muted-foreground">
          #{giro.id} · {giro.numero_giornate} giornate · stato {giro.stato}
        </p>
      </div>
      <div className="flex flex-col items-end gap-2">
        <Button onClick={() => setDialogOpen(true)} className="gap-2">
          <Users className="h-4 w-4" aria-hidden /> Genera turno PdC
        </Button>
        {turni.length > 0 && (
          <Link
            to={`/pianificatore-giro/giri/${giro.id}/turni-pdc`}
            className="text-xs text-muted-foreground hover:text-primary"
          >
            {turni.length} turn{turni.length === 1 ? "o" : "i"} PdC già generat
            {turni.length === 1 ? "o" : "i"} →
          </Link>
        )}
      </div>
      <GeneraTurnoPdcDialog
        giroId={giro.id}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      />
    </header>
  );
}

function Stats({ giro, nVariantiTotale }: { giro: GiroDettaglio; nVariantiTotale: number }) {
  return (
    <div className="grid grid-cols-2 gap-3 rounded-md border border-border bg-white p-4 md:grid-cols-4">
      <Stat
        label="km/giorno (canonica)"
        value={
          giro.km_media_giornaliera !== null
            ? formatNumber(Math.round(giro.km_media_giornaliera))
            : "—"
        }
      />
      <Stat
        label="km/anno"
        value={giro.km_media_annua !== null ? formatNumber(Math.round(giro.km_media_annua)) : "—"}
      />
      <Stat label="Materiale" value={giro.materiale_tipo_codice ?? "—"} />
      <Stat
        label="Varianti totali"
        value={`${nVariantiTotale} su ${giro.numero_giornate} giornate`}
      />
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

/**
 * Sprint 7.7 MR 5: una giornata può avere N varianti calendariali.
 * UI a tab: 1 tab per variante con etichetta parlante. Comportamento
 * equivalente al PDF Trenord turno 1134 (giornata 9 con 4 varianti
 * "LV 1:5", "F", "LV 6 escl. 21-28/3, 11/4", "Si eff. 21-28/3, 11/4").
 */
function GiornataPanel({ giornata }: { giornata: GiroGiornata }) {
  const [activeIdx, setActiveIdx] = useState(0);
  const varianti = giornata.varianti;
  const hasMultiple = varianti.length > 1;
  const active = varianti[activeIdx] ?? varianti[0];

  return (
    <div className="overflow-hidden rounded-md border border-border bg-white">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-secondary/40 px-4 py-2">
        <div className="flex items-baseline gap-3">
          <span className="text-sm font-semibold">Giornata {giornata.numero_giornata}</span>
          {giornata.km_giornata !== null && (
            <span
              className="text-xs text-muted-foreground tabular-nums"
              title="Km della variante canonica (somma km_tratta delle corse commerciali)"
            >
              {formatNumber(Math.round(giornata.km_giornata))} km
            </span>
          )}
        </div>
        <span className="text-xs text-muted-foreground">
          {hasMultiple
            ? `${varianti.length} varianti calendariali`
            : "1 variante"}
        </span>
      </div>
      {hasMultiple && (
        <div
          className="flex flex-wrap gap-1 border-b border-border bg-secondary/20 px-3 py-1.5"
          role="tablist"
          aria-label={`Varianti calendariali giornata ${giornata.numero_giornata}`}
        >
          {varianti.map((v, idx) => {
            const isActive = idx === activeIdx;
            return (
              <button
                key={v.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => setActiveIdx(idx)}
                title={`${v.etichetta_parlante}${idx === 0 ? " (canonica)" : ""}`}
                className={
                  "rounded px-2 py-1 text-[11px] font-medium transition-colors " +
                  (isActive
                    ? "bg-primary text-primary-foreground"
                    : "bg-white text-muted-foreground hover:bg-secondary")
                }
              >
                {truncateLabel(v.etichetta_parlante)}
              </button>
            );
          })}
        </div>
      )}
      <div className="flex flex-col gap-2 p-3">
        {active !== undefined && <VariantePanel variante={active} />}
      </div>
    </div>
  );
}

function truncateLabel(testo: string): string {
  const MAX = 32;
  return testo.length <= MAX ? testo : testo.substring(0, MAX - 1) + "…";
}

function VariantePanel({ variante }: { variante: GiroVariante }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs italic text-muted-foreground">
        Validità: <span className="font-medium not-italic">{variante.etichetta_parlante}</span>
      </p>
      <GanttRow blocchi={variante.blocchi} />
      <BlocchiList blocchi={variante.blocchi} />
    </div>
  );
}

const ORE = Array.from({ length: 24 }, (_, i) => i);
const MINUTI_GIORNO = 24 * 60;

function GanttRow({ blocchi }: { blocchi: GiroBlocco[] }) {
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

function colorForTipo(tipo: string): string {
  switch (tipo) {
    case "corsa_commerciale":
      return "bg-primary text-primary-foreground";
    case "materiale_vuoto":
      return "bg-amber-200 text-amber-900";
    case "cambio_composizione":
    case "evento_composizione":
      return "bg-emerald-200 text-emerald-900";
    case "sosta_notturna":
    case "sosta":
      return "bg-secondary text-secondary-foreground";
    default:
      return "bg-muted text-muted-foreground";
  }
}

function GanttBlocco({ blocco }: { blocco: GiroBlocco }) {
  const inizio = timeToMin(blocco.ora_inizio);
  const fine = timeToMin(blocco.ora_fine);
  if (inizio === null || fine === null) return null;
  const left = (inizio / MINUTI_GIORNO) * 100;
  const width = Math.max(0.5, ((fine - inizio) / MINUTI_GIORNO) * 100);
  const label = bloccoLabel(blocco);
  const da = stazioneLabel(blocco.stazione_da_nome, blocco.stazione_da_codice);
  const a = stazioneLabel(blocco.stazione_a_nome, blocco.stazione_a_codice);
  const tipoLabel = tipoBloccoLabel(blocco.tipo_blocco);
  const trenoLine =
    blocco.numero_treno !== null ? `\nTreno ${blocco.numero_treno}` : "";
  const tooltip = `${tipoLabel} · ${blocco.ora_inizio ?? "?"}→${blocco.ora_fine ?? "?"}\n${da} → ${a}${trenoLine}`;
  return (
    <div
      className={`absolute top-1 flex h-7 items-center overflow-hidden rounded px-1.5 text-[10px] font-medium ${colorForTipo(blocco.tipo_blocco)}`}
      style={{ left: `${left}%`, width: `${width}%` }}
      title={tooltip}
    >
      <span className="truncate">{label}</span>
    </div>
  );
}

function bloccoLabel(b: GiroBlocco): string {
  if (b.numero_treno !== null && b.numero_treno.length > 0) return b.numero_treno;
  const meta =
    typeof b.metadata_json?.numero_treno === "string"
      ? (b.metadata_json.numero_treno as string)
      : null;
  if (meta !== null) return meta;
  const da = b.stazione_da_nome ?? b.stazione_da_codice ?? "?";
  const a = b.stazione_a_nome ?? b.stazione_a_codice ?? "?";
  return `${da}→${a}`;
}

function stazioneLabel(nome: string | null, codice: string | null): string {
  if (nome !== null && nome.length > 0) return nome;
  if (codice !== null && codice.length > 0) return codice;
  return "—";
}

function tipoBloccoLabel(tipo: string): string {
  switch (tipo) {
    case "corsa_commerciale":
      return "Commerciale";
    case "materiale_vuoto":
      return "Vuoto";
    case "cambio_composizione":
    case "evento_composizione":
      return "Composizione";
    case "sosta_notturna":
      return "Sosta notturna";
    case "sosta":
      return "Sosta";
    default:
      return tipo;
  }
}

function BlocchiList({ blocchi }: { blocchi: GiroBlocco[] }) {
  if (blocchi.length === 0) {
    return (
      <p className="px-3 py-2 text-xs italic text-muted-foreground">
        Nessun blocco in questa variante.
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
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {blocchi.map((b) => (
            <tr key={b.id}>
              <td className="px-2 py-1 font-mono text-muted-foreground">{b.seq}</td>
              <td className="px-2 py-1">
                <BloccoTipoBadge tipo={b.tipo_blocco} />
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
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

function TrenoCell({ blocco }: { blocco: GiroBlocco }) {
  if (blocco.numero_treno === null) return <span>—</span>;
  return <span className="font-mono font-medium">{blocco.numero_treno}</span>;
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
  if (tipo === "corsa_commerciale") return <Badge variant="default">commerciale</Badge>;
  if (tipo === "materiale_vuoto") return <Badge variant="warning">vuoto</Badge>;
  if (tipo === "cambio_composizione" || tipo === "evento_composizione")
    return <Badge variant="success">comp.</Badge>;
  if (tipo === "sosta_notturna" || tipo === "sosta")
    return <Badge variant="secondary">sosta</Badge>;
  return <Badge variant="outline">{tipo}</Badge>;
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
