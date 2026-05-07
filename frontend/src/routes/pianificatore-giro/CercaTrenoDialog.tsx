import { useEffect, useState } from "react";
import { Search, Train, ArrowRight } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { Spinner } from "@/components/ui/Spinner";
import { useCercaTreno } from "@/hooks/useGiri";
import type { CercaTrenoBloccoRef, CercaTrenoItem } from "@/lib/api/giri";

interface CercaTrenoDialogProps {
  programmaId: number | undefined;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /**
   * Callback per click su un blocco nel popup. Il padre decide la
   * navigazione: tipicamente `navigate(\`/giri/${blocco.giro_id}?focusBlocco=${blocco.blocco_id}\`)`.
   */
  onSelect: (item: CercaTrenoItem, blocco: CercaTrenoBloccoRef) => void;
}

const DEBOUNCE_MS = 250;

function formatOra(s: string): string {
  // "08:00:00" -> "08:00"
  return s.length >= 5 ? s.slice(0, 5) : s;
}

/**
 * Sprint 8.0 MR-1 (entry 214) — popup cerca treno.
 *
 * Input testuale + lista risultati raggruppati per ``(tipo, corsa_id)``.
 * Match partial case-insensitive su ``numero_treno`` (commerciale o
 * vuoto, es. ``28`` matcha ``28335`` e ``92811``). Ogni risultato
 * mostra i blocchi giro che usano quel treno; click su un blocco
 * triggera ``onSelect`` per la navigazione (gestita dal padre).
 */
export function CercaTrenoDialog({
  programmaId,
  open,
  onOpenChange,
  onSelect,
}: CercaTrenoDialogProps) {
  const [input, setInput] = useState("");
  const [debounced, setDebounced] = useState("");

  // Debounce locale (~250ms) per non spammare l'API a ogni tasto.
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(input), DEBOUNCE_MS);
    return () => window.clearTimeout(t);
  }, [input]);

  // Reset query quando il dialog si chiude (UX: riapertura pulita).
  useEffect(() => {
    if (!open) {
      setInput("");
      setDebounced("");
    }
  }, [open]);

  const { data, isLoading, isError, error } = useCercaTreno(programmaId, debounced);

  const showResults = debounced.trim().length >= 1;
  const items = data ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[80vh] max-w-2xl flex-col overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Search className="h-5 w-5" />
            Cerca treno
          </DialogTitle>
          <DialogDescription>
            Digita un numero treno (anche parziale, es.{" "}
            <code className="rounded bg-muted px-1">28</code>). Cerca tra
            i treni commerciali e i materiali vuoti dei giri di questo
            programma.
          </DialogDescription>
        </DialogHeader>

        <div className="px-1 pb-2">
          <Input
            autoFocus
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Numero treno..."
            className="font-mono"
          />
        </div>

        <div className="-mx-2 flex-1 min-h-0 overflow-y-auto px-2">
          {!showResults && (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Inizia a digitare per cercare.
            </p>
          )}
          {showResults && isLoading && (
            <div className="flex items-center justify-center py-6">
              <Spinner />
            </div>
          )}
          {showResults && isError && (
            <p className="py-6 text-center text-sm text-destructive">
              Errore: {error instanceof Error ? error.message : "richiesta fallita"}
            </p>
          )}
          {showResults && !isLoading && !isError && items.length === 0 && (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Nessun treno trovato per "{debounced}".
            </p>
          )}
          {showResults && !isLoading && items.length > 0 && (
            <ul className="space-y-2">
              {items.map((it) => (
                <li
                  key={`${it.tipo}-${it.corsa_id}`}
                  className="rounded-md border p-3"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 font-mono text-sm font-semibold">
                      <Train className="h-4 w-4" />
                      {it.numero_treno}
                      {it.tipo === "vuoto" && (
                        <Badge variant="secondary" className="text-xs">
                          vuoto
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-1 text-xs text-muted-foreground">
                      <span>{it.stazione_da_codice}</span>
                      <ArrowRight className="h-3 w-3" />
                      <span>{it.stazione_a_codice}</span>
                      <span className="ml-2 font-mono">
                        {formatOra(it.ora_partenza)} → {formatOra(it.ora_arrivo)}
                      </span>
                    </div>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {it.blocchi.map((b) => (
                      <button
                        key={b.blocco_id}
                        onClick={() => onSelect(it, b)}
                        className="rounded border bg-background px-2 py-1 text-xs hover:bg-accent hover:text-accent-foreground"
                        title={
                          b.variante_etichetta
                            ? `Variante: ${b.variante_etichetta}`
                            : undefined
                        }
                      >
                        <span className="font-mono">{b.numero_turno}</span>
                        <span className="text-muted-foreground">
                          {" · "}G{b.giornata}
                        </span>
                        {b.variante_index > 0 && (
                          <span className="text-muted-foreground">
                            {" · "}V{b.variante_index}
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
