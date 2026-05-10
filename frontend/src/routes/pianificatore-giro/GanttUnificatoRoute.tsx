import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  PlusCircle,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Label } from "@/components/ui/Label";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import {
  useCorseNonCoperte,
  useGiriProgramma,
  useInserisciCorsaManuale,
} from "@/hooks/useGiri";
import { useProgramma } from "@/hooks/useProgrammi";
import { ApiError } from "@/lib/api/client";
import type {
  CorsaNonCopertaItem,
  GiroListItem,
  InserisciCorsaManualeWarning,
} from "@/lib/api/giri";
import { formatDateIt } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Sprint 8.4 G1 — Gantt unificato modificabile.
 *
 * Vista d'insieme che combina su una sola pagina:
 *   - tutti i giri del programma (chiusi e non chiusi) come righe
 *     etichettate (numero turno, materiale, sede, motivo chiusura);
 *   - le corse non coperte come blocchi cliccabili posizionati su
 *     timeline 04→04 per ora di partenza.
 *
 * Click su una corsa scoperta → dialog con selezione giro + giornata +
 * variante → POST `/api/giri/{id}/inserisci-corsa-manuale`. La corsa
 * sparisce dalle non coperte; l'utente la trova dentro il giro target.
 *
 * Differenza vs `riempi-gap`: nessun vincolo match-esatto stazioni o
 * date subset. L'operatore conferma manualmente, accettando eventuali
 * warning (sosta non match, sovrapposizione tempo).
 */

const AXIS_START_MIN = 4 * 60;
const AXIS_TOTAL_MIN = 24 * 60;
const TIMELINE_WIDTH_PX = 1120;
const HOUR_PX = TIMELINE_WIDTH_PX / 24;

function timeToMin(t: string): number {
  const [h = "0", m = "0"] = t.split(":");
  return Number.parseInt(h, 10) * 60 + Number.parseInt(m, 10);
}

function minToPx(min: number): number {
  let rel = min - AXIS_START_MIN;
  if (rel < 0) rel += AXIS_TOTAL_MIN;
  return (rel / AXIS_TOTAL_MIN) * TIMELINE_WIDTH_PX;
}

export function GanttUnificatoRoute() {
  const { programmaId: rawId } = useParams<{ programmaId: string }>();
  const programmaId = rawId !== undefined ? Number(rawId) : undefined;
  const navigate = useNavigate();

  const programmaQ = useProgramma(programmaId);
  const giriQ = useGiriProgramma(programmaId);
  const corseQ = useCorseNonCoperte(programmaId);

  const [pickerCorsa, setPickerCorsa] =
    useState<CorsaNonCopertaItem | null>(null);

  if (programmaId === undefined) {
    return (
      <div className="p-8">
        <p className="text-sm text-rose-600">programmaId non valido.</p>
      </div>
    );
  }

  if (programmaQ.isLoading || giriQ.isLoading || corseQ.isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner />
      </div>
    );
  }

  const programma = programmaQ.data;
  const giri = giriQ.data ?? [];
  const corse = corseQ.data ?? [];

  if (programma === undefined) {
    return (
      <div className="p-8">
        <p className="text-sm text-rose-600">Programma non trovato.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4 p-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() =>
              navigate(`/pianificatore-giro/programmi/${programmaId}/giri`)
            }
          >
            <ArrowLeft className="mr-1.5 size-4" /> Torna alla lista giri
          </Button>
          <h1 className="mt-2 text-2xl font-semibold">
            Gantt unificato — {programma.nome}
          </h1>
          <p className="text-sm text-slate-500">
            {formatDateIt(programma.valido_da)} →{" "}
            {formatDateIt(programma.valido_a)} · {giri.length} giri ·{" "}
            <span className="font-medium text-amber-700">
              {corse.length} corse non coperte
            </span>
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Click su un blocco rosso → seleziona giro/giornata e inserisci
            manualmente.
          </p>
        </div>
      </div>

      {/* Corse non coperte — Gantt principale */}
      <Card className="overflow-hidden">
        <div className="border-b bg-amber-50 px-4 py-3">
          <h2 className="text-sm font-semibold text-amber-900">
            Corse non coperte ({corse.length})
          </h2>
          <p className="text-xs text-amber-800">
            Asse temporale 04:00 → 04:00 (ciclo operativo). Click per
            inserimento manuale in un giro esistente.
          </p>
        </div>

        <div className="overflow-x-auto">
          <div style={{ width: TIMELINE_WIDTH_PX + 32 }} className="px-4 py-3">
            <AxisHeader />
            <CorseNonCoperteRow
              corse={corse}
              onPick={setPickerCorsa}
            />
          </div>
        </div>
      </Card>

      {/* Lista giri esistenti (sintetica, modifica fine link a Gantt giro) */}
      <Card>
        <div className="border-b px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-900">
            Giri del programma ({giri.length})
          </h2>
          <p className="text-xs text-slate-500">
            Click su un giro per aprire il Gantt dettagliato (modifica fine
            blocchi).
          </p>
        </div>
        <div className="divide-y">
          {giri.map((g) => (
            <GiroRowSintetico key={g.id} giro={g} />
          ))}
          {giri.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm text-slate-500">
              Nessun giro generato.
            </p>
          ) : null}
        </div>
      </Card>

      {/* Dialog inserimento manuale */}
      {pickerCorsa !== null ? (
        <InserisciCorsaDialog
          corsa={pickerCorsa}
          giri={giri}
          onClose={() => setPickerCorsa(null)}
        />
      ) : null}
    </div>
  );
}

// =====================================================================
// AxisHeader — tick orari 04 → 04
// =====================================================================

function AxisHeader(): React.ReactElement {
  const ticks = useMemo(() => {
    const out: { label: string; left: number }[] = [];
    for (let i = 0; i <= 24; i++) {
      const hour = (4 + i) % 24;
      out.push({
        label: hour.toString().padStart(2, "0"),
        left: i * HOUR_PX,
      });
    }
    return out;
  }, []);
  return (
    <div
      className="relative h-6 border-b border-slate-200"
      style={{ width: TIMELINE_WIDTH_PX }}
    >
      {ticks.map((t, i) => (
        <div
          key={i}
          className="absolute top-0 -translate-x-1/2 text-[10px] tabular-nums text-slate-500"
          style={{ left: t.left }}
        >
          <div className="h-2 w-px bg-slate-300" />
          <span>{t.label}</span>
        </div>
      ))}
    </div>
  );
}

// =====================================================================
// CorseNonCoperteRow — tutte le corse residue, posizionate per ora
// =====================================================================

function CorseNonCoperteRow({
  corse,
  onPick,
}: {
  corse: CorsaNonCopertaItem[];
  onPick: (c: CorsaNonCopertaItem) => void;
}): React.ReactElement {
  if (corse.length === 0) {
    return (
      <div
        className="mt-3 flex h-12 items-center justify-center rounded border border-emerald-200 bg-emerald-50 text-sm text-emerald-800"
        style={{ width: TIMELINE_WIDTH_PX }}
      >
        <Check className="mr-2 size-4" /> Tutte le corse del perimetro sono
        coperte.
      </div>
    );
  }

  // Group by motivo per visualizzazione (linea_disgiunta vs sovrapp)
  const layeredRows = useMemo(() => {
    // Lay out blocks in rows so they don't overlap horizontally.
    const sorted = [...corse].sort(
      (a, b) => timeToMin(a.ora_partenza) - timeToMin(b.ora_partenza),
    );
    const rows: CorsaNonCopertaItem[][] = [];
    for (const c of sorted) {
      let placed = false;
      for (const row of rows) {
        const last = row[row.length - 1];
        if (last !== undefined && timeToMin(last.ora_arrivo) <= timeToMin(c.ora_partenza)) {
          row.push(c);
          placed = true;
          break;
        }
      }
      if (!placed) rows.push([c]);
    }
    return rows;
  }, [corse]);

  return (
    <div className="mt-1 space-y-1">
      {layeredRows.map((row, idx) => (
        <div
          key={idx}
          className="relative h-9 rounded border border-slate-100 bg-slate-50"
          style={{ width: TIMELINE_WIDTH_PX }}
        >
          {row.map((c) => {
            const startMin = timeToMin(c.ora_partenza);
            const endMin = timeToMin(c.ora_arrivo);
            let durMin = endMin - startMin;
            if (durMin <= 0) durMin += AXIS_TOTAL_MIN;
            const left = minToPx(startMin);
            const width = (durMin / AXIS_TOTAL_MIN) * TIMELINE_WIDTH_PX;
            const isLineaDisgiunta = c.motivo_presunto === "linea_disgiunta";
            return (
              <button
                key={c.corsa_id}
                type="button"
                onClick={() => onPick(c)}
                title={`${c.numero_treno} · ${c.stazione_da_codice} → ${c.stazione_a_codice} · ${c.ora_partenza.slice(0, 5)} → ${c.ora_arrivo.slice(0, 5)} · ${c.n_date_perimetro} date · click per inserire`}
                className={cn(
                  "absolute top-1 h-7 truncate rounded px-1.5 text-[11px] font-mono font-semibold text-white shadow transition hover:scale-105 hover:shadow-md",
                  isLineaDisgiunta
                    ? "bg-rose-500 hover:bg-rose-600"
                    : "bg-amber-500 hover:bg-amber-600",
                )}
                style={{
                  left,
                  width: Math.max(width, 36),
                }}
              >
                {c.numero_treno}
              </button>
            );
          })}
        </div>
      ))}
      <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-slate-600">
        <span className="inline-flex items-center gap-1">
          <span className="inline-block size-3 rounded bg-amber-500" />{" "}
          sovrapposizione stazioni (fillable)
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="inline-block size-3 rounded bg-rose-500" />{" "}
          linea disgiunta (serve nuovo giro)
        </span>
      </div>
    </div>
  );
}

// =====================================================================
// GiroRowSintetico — riga compatta per giro, con link a Gantt singolo
// =====================================================================

function GiroRowSintetico({
  giro,
}: {
  giro: GiroListItem;
}): React.ReactElement {
  return (
    <Link
      to={`/pianificatore-giro/giri/${giro.id}`}
      className="flex items-center gap-3 px-4 py-2 hover:bg-slate-50"
    >
      <span className="w-32 truncate text-xs font-mono font-semibold text-slate-800">
        {giro.numero_turno}
      </span>
      <span className="w-20 text-xs text-slate-600">{giro.tipo_materiale}</span>
      <span className="w-16 text-xs text-slate-500">
        {giro.numero_giornate}g
      </span>
      <span className="w-32 text-xs text-slate-500 tabular-nums">
        {giro.km_media_giornaliera === null
          ? "—"
          : `${Math.round(giro.km_media_giornaliera)} km/g`}
      </span>
      <Badge variant={giro.chiuso ? "success" : "warning"}>
        {giro.chiuso ? "naturale" : "non chiuso"}
      </Badge>
      <span className="ml-auto text-[11px] text-slate-400">
        {giro.motivo_chiusura ?? "—"}
      </span>
    </Link>
  );
}

// =====================================================================
// InserisciCorsaDialog — dialog selezione giro/giornata/variante
// =====================================================================

function InserisciCorsaDialog({
  corsa,
  giri,
  onClose,
}: {
  corsa: CorsaNonCopertaItem;
  giri: GiroListItem[];
  onClose: () => void;
}): React.ReactElement {
  const mutation = useInserisciCorsaManuale();
  const [giroId, setGiroId] = useState<number | undefined>(undefined);
  const [giornataNumero, setGiornataNumero] = useState<number>(1);
  const [varianteIndex, setVarianteIndex] = useState<number>(0);
  const [warnings, setWarnings] = useState<
    InserisciCorsaManualeWarning[] | null
  >(null);
  const [success, setSuccess] = useState(false);

  const giroSelezionato = useMemo(
    () => giri.find((g) => g.id === giroId) ?? null,
    [giroId, giri],
  );

  const handleSubmit = async (): Promise<void> => {
    if (giroId === undefined) return;
    setWarnings(null);
    setSuccess(false);
    try {
      const r = await mutation.mutateAsync({
        giroId,
        payload: {
          corsa_commerciale_id: corsa.corsa_id,
          giornata_numero: giornataNumero,
          variante_index: varianteIndex,
          seq_target: null,
        },
      });
      setWarnings(r.warnings);
      setSuccess(true);
    } catch {
      // ApiError esposto da mutation.error
    }
  };

  const errMsg = (() => {
    if (mutation.error instanceof ApiError) return mutation.error.message;
    if (mutation.error instanceof Error) return mutation.error.message;
    return null;
  })();

  return (
    <Dialog open onOpenChange={(o) => (o ? null : onClose())}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>
            Inserisci corsa {corsa.numero_treno} in un giro
          </DialogTitle>
          <DialogDescription>
            {corsa.stazione_da_codice} →{" "}
            {corsa.stazione_a_codice} ·{" "}
            {corsa.ora_partenza.slice(0, 5)} →{" "}
            {corsa.ora_arrivo.slice(0, 5)} · {corsa.n_date_perimetro} date
            nel perimetro
          </DialogDescription>
        </DialogHeader>

        {success ? (
          <div className="space-y-3 py-2">
            <div className="rounded border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
              <Check className="mr-1 inline size-4" /> Corsa inserita nel
              giro {giroSelezionato?.numero_turno ?? `#${giroId ?? "?"}`}{" "}
              giornata {giornataNumero} variante #{varianteIndex}.
            </div>
            {warnings !== null && warnings.length > 0 ? (
              <div className="rounded border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900">
                <p className="mb-1 font-semibold">
                  <AlertTriangle className="mr-1 inline size-3.5" />{" "}
                  {warnings.length} avviso{warnings.length === 1 ? "" : "i"}{" "}
                  di compatibilità:
                </p>
                <ul className="list-disc space-y-0.5 pl-5">
                  {warnings.map((w, i) => (
                    <li key={i}>
                      <span className="font-mono">{w.code}</span>:{" "}
                      {w.descrizione}
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="text-xs text-emerald-800">
                Nessun warning di compatibilità (stazioni e tempi quadrano).
              </p>
            )}
          </div>
        ) : (
          <div className="space-y-4 py-2">
            <div>
              <Label htmlFor="giro-select">Giro target</Label>
              <Select
                id="giro-select"
                value={giroId === undefined ? "" : String(giroId)}
                onChange={(e) => {
                  const v = e.target.value;
                  setGiroId(v === "" ? undefined : Number(v));
                }}
              >
                <option value="">— Seleziona —</option>
                {giri.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.numero_turno} · {g.tipo_materiale} ·{" "}
                    {g.numero_giornate}g{" "}
                    {g.chiuso ? "(naturale)" : "(non chiuso)"}
                  </option>
                ))}
              </Select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="giornata-input">Giornata-tipo</Label>
                <Select
                  id="giornata-input"
                  value={String(giornataNumero)}
                  onChange={(e) =>
                    setGiornataNumero(Number(e.target.value))
                  }
                  disabled={giroSelezionato === null}
                >
                  {Array.from(
                    { length: giroSelezionato?.numero_giornate ?? 1 },
                    (_, i) => i + 1,
                  ).map((n) => (
                    <option key={n} value={n}>
                      Giornata {n}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="variante-input">Variante</Label>
                <Select
                  id="variante-input"
                  value={String(varianteIndex)}
                  onChange={(e) =>
                    setVarianteIndex(Number(e.target.value))
                  }
                  disabled={giroSelezionato === null}
                >
                  <option value="0">canonica (#0)</option>
                  <option value="1">variante #1</option>
                  <option value="2">variante #2</option>
                  <option value="3">variante #3</option>
                </Select>
              </div>
            </div>

            <p className="text-[11px] text-slate-500">
              Il backend calcola la posizione cronologica corretta in base
              all'orario {corsa.ora_partenza.slice(0, 5)}. Se la stazione di
              partenza non coincide con la fine del blocco precedente, viene
              ritornato un warning informativo (non blocca).
            </p>

            {errMsg !== null ? (
              <div className="rounded border border-rose-300 bg-rose-50 p-2 text-xs text-rose-900">
                <X className="mr-1 inline size-3.5" /> {errMsg}
              </div>
            ) : null}
          </div>
        )}

        <DialogFooter>
          {success ? (
            <Button onClick={onClose}>Chiudi</Button>
          ) : (
            <>
              <Button variant="ghost" onClick={onClose}>
                Annulla
              </Button>
              <Button
                onClick={handleSubmit}
                disabled={giroId === undefined || mutation.isPending}
              >
                {mutation.isPending ? (
                  <>
                    <Spinner className="mr-1.5 size-4" /> Inserimento…
                  </>
                ) : (
                  <>
                    <PlusCircle className="mr-1.5 size-4" /> Inserisci
                  </>
                )}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
