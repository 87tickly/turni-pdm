import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { useThreadDettaglio } from "@/hooks/useGiri";
import { ApiError } from "@/lib/api/client";
import type { MaterialeThreadEvento } from "@/lib/api/giri";
import { cn } from "@/lib/utils";

function ErrorBlock({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <Card className="flex flex-col items-center gap-3 p-8 text-center">
      <p className="text-sm text-destructive">{message}</p>
      {onRetry !== undefined && (
        <Button variant="outline" size="md" onClick={onRetry}>
          Riprova
        </Button>
      )}
    </Card>
  );
}

/**
 * Sprint 7.9 MR β2-6 — Thread Viewer.
 *
 * Visualizza la timeline cronologica di un singolo `MaterialeThread`:
 * lista di eventi (corsa singolo/doppia/tripla, vuoto, sosta,
 * aggancio, sgancio, uscita/rientro deposito) con orario, stazioni,
 * km e numero treno.
 *
 * Pagina semplice (lista + KPI) — il rendering Gantt-style del thread
 * è scope futuro (richiede asse temporale dedicato per visualizzare
 * giorni multipli).
 */
export function MaterialeThreadRoute() {
  const { threadId: threadIdParam } = useParams<{ threadId: string }>();
  const threadId = threadIdParam !== undefined ? Number(threadIdParam) : undefined;
  const query = useThreadDettaglio(threadId);

  if (threadId === undefined || Number.isNaN(threadId)) {
    return <ErrorBlock message="ID thread non valido nell'URL." />;
  }

  if (query.isLoading) {
    return (
      <Card className="grid place-items-center p-16">
        <Spinner label="Caricamento thread…" />
      </Card>
    );
  }

  if (query.isError) {
    const msg =
      query.error instanceof ApiError ? query.error.message : (query.error as Error).message;
    return <ErrorBlock message={msg} onRetry={() => void query.refetch()} />;
  }

  if (query.data === undefined) {
    return <ErrorBlock message="Thread non trovato." />;
  }

  const thread = query.data;
  const matricolaLabel =
    thread.matricola_id !== null ? `#${thread.matricola_id}` : "non assegnata";

  return (
    <div className="flex flex-col gap-4">
      <Link
        to={`/pianificatore-giro/giri/${thread.giro_materiale_id_origine}`}
        className="inline-flex w-fit items-center gap-1 text-xs text-muted-foreground hover:text-primary"
      >
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> Torna al giro materiale
      </Link>

      <Card className="p-6">
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <span className="font-mono text-xs text-muted-foreground">
                Thread #{thread.id}
              </span>
              <span className="inline-flex items-center rounded bg-muted px-2 py-0.5 font-mono text-[11px] text-foreground">
                {thread.tipo_materiale_codice}
              </span>
            </div>
            <h1 className="font-mono text-2xl font-semibold tracking-tight text-foreground">
              {thread.tipo_materiale_codice} · matricola {matricolaLabel}
            </h1>
          </div>
          <div className="grid grid-cols-3 gap-x-8 gap-y-2 text-sm">
            <Stat label="km totali" value={formatNumber(Math.round(thread.km_totali))} />
            <Stat
              label="minuti servizio"
              value={formatNumber(thread.minuti_servizio)}
            />
            <Stat
              label="corse commerciali"
              value={String(thread.n_corse_commerciali)}
            />
          </div>
        </div>
      </Card>

      <Card className="overflow-hidden">
        <div className="border-b border-border bg-muted/40 px-4 py-2.5 text-xs">
          <span className="font-medium uppercase tracking-wide text-foreground">
            Timeline eventi
          </span>
          <span className="ml-3 text-muted-foreground">
            {thread.eventi.length} event{thread.eventi.length === 1 ? "o" : "i"}
          </span>
        </div>
        {thread.eventi.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            Nessun evento. Il thread è stato proiettato senza partecipazioni
            tracciabili (verifica composizione del giro origine).
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/20">
              <tr>
                <Th>#</Th>
                <Th>Tipo</Th>
                <Th>Data</Th>
                <Th>Treno</Th>
                <Th>Da</Th>
                <Th>A</Th>
                <Th>Inizio</Th>
                <Th>Fine</Th>
                <Th align="right">Km</Th>
              </tr>
            </thead>
            <tbody>
              {thread.eventi.map((ev) => (
                <EventoRow key={ev.id} evento={ev} />
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <span className="font-mono tabular-nums text-foreground">{value}</span>
    </div>
  );
}

function Th({
  children,
  align = "left",
}: {
  children: React.ReactNode;
  align?: "left" | "right";
}) {
  return (
    <th
      className={cn(
        "px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground",
        align === "right" ? "text-right" : "text-left",
      )}
    >
      {children}
    </th>
  );
}

const TIPO_LABELS: Record<string, { label: string; bg: string; text: string }> = {
  corsa_singolo: { label: "Corsa singolo", bg: "bg-emerald-100", text: "text-emerald-800" },
  corsa_doppia_pos1: { label: "Corsa doppia (pos 1)", bg: "bg-blue-100", text: "text-blue-800" },
  corsa_doppia_pos2: { label: "Corsa doppia (pos 2)", bg: "bg-blue-100", text: "text-blue-800" },
  corsa_tripla_pos1: { label: "Corsa tripla (pos 1)", bg: "bg-indigo-100", text: "text-indigo-800" },
  corsa_tripla_pos2: { label: "Corsa tripla (pos 2)", bg: "bg-indigo-100", text: "text-indigo-800" },
  corsa_tripla_pos3: { label: "Corsa tripla (pos 3)", bg: "bg-indigo-100", text: "text-indigo-800" },
  vuoto_solo: { label: "Vuoto solo", bg: "bg-rose-100", text: "text-rose-800" },
  uscita_deposito: { label: "Uscita deposito", bg: "bg-blue-200", text: "text-blue-900" },
  rientro_deposito: { label: "Rientro deposito", bg: "bg-violet-200", text: "text-violet-900" },
  aggancio: { label: "+ Aggancio", bg: "bg-emerald-200", text: "text-emerald-900" },
  sgancio: { label: "− Sgancio", bg: "bg-amber-200", text: "text-amber-900" },
};

function EventoRow({ evento }: { evento: MaterialeThreadEvento }) {
  const tipo = TIPO_LABELS[evento.tipo] ?? {
    label: evento.tipo,
    bg: "bg-muted",
    text: "text-muted-foreground",
  };
  return (
    <tr className="border-b border-border/40 hover:bg-muted/20">
      <Td>{evento.ordine}</Td>
      <Td>
        <span
          className={cn(
            "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium",
            tipo.bg,
            tipo.text,
          )}
        >
          {tipo.label}
        </span>
      </Td>
      <Td>{evento.data_giorno ?? "—"}</Td>
      <Td className="font-mono">{evento.numero_treno ?? "—"}</Td>
      <Td className="font-mono">{evento.stazione_da_codice ?? "—"}</Td>
      <Td className="font-mono">{evento.stazione_a_codice ?? "—"}</Td>
      <Td className="font-mono tabular-nums">{formatTime(evento.ora_inizio)}</Td>
      <Td className="font-mono tabular-nums">{formatTime(evento.ora_fine)}</Td>
      <Td align="right" className="font-mono tabular-nums">
        {evento.km_tratta !== null ? Math.round(evento.km_tratta) : "—"}
      </Td>
    </tr>
  );
}

function Td({
  children,
  align = "left",
  className,
}: {
  children: React.ReactNode;
  align?: "left" | "right";
  className?: string;
}) {
  return (
    <td
      className={cn(
        "px-3 py-2 text-foreground",
        align === "right" ? "text-right" : "text-left",
        className,
      )}
    >
      {children}
    </td>
  );
}

function formatTime(t: string | null): string {
  if (t === null) return "—";
  const m = t.match(/^(\d{2}):(\d{2})/);
  return m === null ? t : `${m[1]}:${m[2]}`;
}

function formatNumber(n: number): string {
  return n.toLocaleString("it-IT");
}
