/**
 * Sub-MR 2.bis-b (Sprint 8.0) — Drilldown auto-assegna persone PdC.
 *
 * Route protetta `GESTIONE_PERSONALE`:
 * `/gestione-personale/programmi/:id/assegna`
 *
 * Workflow:
 *  1. L'utente apre la pagina dal click su PersonalePipelineCard
 *     (programma in `PDC_CONFERMATO`).
 *  2. Bottone "Auto-assegna persone" → dialog con date_da/data_a
 *     opzionali (default = programma.valido_da..valido_a). Submit chiama
 *     `POST /api/programmi/{id}/auto-assegna-persone` (sub-MR 2.bis-a).
 *  3. La response viene tenuta in stato React e renderizzata in 4 sezioni:
 *     KPI (delta_copertura_pct + counters), tabella mancanze (con bottone
 *     "Override" per riga), tabella warning soft, tabella assegnazioni
 *     create (riepilogo).
 *  4. Click "Override" → dialog con dropdown persone (tutte i PdC
 *     dell'azienda — la sede non è vincolante in override). Submit
 *     chiama `POST /api/programmi/{id}/assegna-manuale` (sub-MR 2.bis-b).
 *     In caso di 201, la riga mancanza viene rimossa localmente
 *     dall'UI e i counters aggiornati.
 *
 * Le response sono **transienti** (React state). Se l'utente
 * naviga via, perde il report; per re-vedere basta cliccare di nuovo
 * "Auto-assegna" — l'algoritmo è idempotente e le assegnazioni
 * esistenti non vengono sovrascritte.
 */

import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  CalendarRange,
  CheckCircle2,
  Info,
  Wand2,
} from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Spinner } from "@/components/ui/Spinner";
import { usePersone } from "@/hooks/useGestionePersonale";
import {
  useAssegnaManuale,
  useAutoAssegnaPersone,
  useProgramma,
} from "@/hooks/useProgrammi";
import type {
  AutoAssegnaPersoneResponse,
  MancanzaAuto,
  MotivoMancanza,
  TipoWarningSoft,
  WarningSoft,
} from "@/lib/api/programmi";
import { cn } from "@/lib/utils";

const MOTIVO_LABEL: Record<MotivoMancanza, string> = {
  nessun_pdc_deposito: "Nessun PdC nel deposito del turno",
  tutti_indisponibili: "Tutti i PdC del deposito sono indisponibili",
  tutti_gia_assegnati: "Tutti i PdC del deposito sono già assegnati per quella data",
  tutti_riposo_intraturno_violato:
    "Tutti i PdC del deposito violerebbero il riposo intraturno (§11.5)",
  nessun_pdc_candidato: "Nessun candidato compatibile (cause miste)",
};

const WARNING_LABEL: Record<TipoWarningSoft, string> = {
  fr_cap_settimana_superato: "FR cap settimana ISO superato (§10.6)",
  fr_cap_28gg_superato: "FR cap 3/28gg superato (§10.6)",
  riposo_settimanale_violato: "Riposo settimanale ≥62h non rispettabile (§11.4)",
  primo_giorno_post_riposo_mattina:
    "Primo giorno post-riposo inizia mattina (§11.2 preferenziale)",
};

export function GestionePersonaleAssegnaPersoneRoute() {
  const { programmaId: programmaIdParam } = useParams<{ programmaId: string }>();
  const programmaId =
    programmaIdParam !== undefined ? Number(programmaIdParam) : undefined;
  const programma = useProgramma(programmaId);

  // Risultato transiente dell'ultimo run auto-assegna (in-memory, non persistito).
  const [risultato, setRisultato] = useState<AutoAssegnaPersoneResponse | null>(
    null,
  );
  const [autoDialogOpen, setAutoDialogOpen] = useState(false);
  const [overrideTarget, setOverrideTarget] = useState<MancanzaAuto | null>(
    null,
  );

  const handleAutoSuccess = (data: AutoAssegnaPersoneResponse) => {
    setRisultato(data);
    setAutoDialogOpen(false);
  };

  const handleOverrideSuccess = (mancanza: MancanzaAuto) => {
    if (!risultato) return;
    // Rimuovo la mancanza chiusa + bumpo counters
    setRisultato({
      ...risultato,
      n_giornate_coperte: risultato.n_giornate_coperte + 1,
      n_assegnazioni_create: risultato.n_assegnazioni_create + 1,
      delta_copertura_pct:
        risultato.n_giornate_totali > 0
          ? Math.round(
              ((risultato.n_giornate_coperte + 1) /
                risultato.n_giornate_totali) *
                1000,
            ) / 10
          : 100,
      mancanze: risultato.mancanze.filter(
        (m) =>
          !(
            m.turno_pdc_giornata_id === mancanza.turno_pdc_giornata_id &&
            m.data === mancanza.data
          ),
      ),
    });
    setOverrideTarget(null);
  };

  if (programmaId === undefined) {
    return (
      <Card className="p-4 text-sm text-muted-foreground">
        ID programma non valido.
      </Card>
    );
  }

  if (programma.isLoading) {
    return (
      <Card className="flex items-center justify-center p-6">
        <Spinner label="Caricamento programma…" />
      </Card>
    );
  }

  if (programma.isError || programma.data === undefined) {
    return (
      <Card className="p-4 text-sm text-red-700">
        Programma non trovato o errore di rete.
      </Card>
    );
  }

  const p = programma.data;
  const stato = p.stato_pipeline_pdc;
  const isPdcConfermato = stato === "PDC_CONFERMATO";

  return (
    <div className="flex flex-col gap-5">
      {/* Breadcrumb */}
      <div className="text-xs text-muted-foreground">
        <Link to="/gestione-personale/dashboard" className="hover:text-primary">
          Home
        </Link>
        <span className="mx-1 text-muted-foreground/40">/</span>
        Programma <span className="font-medium text-foreground">{p.nome}</span>
        <span className="mx-1 text-muted-foreground/40">/</span>
        Assegnazione persone
      </div>

      {/* Header card */}
      <Card className="flex flex-col gap-2 p-4">
        <div className="flex items-baseline justify-between gap-3">
          <h1 className="text-xl font-semibold tracking-tight text-foreground">
            {p.nome}
          </h1>
          <span
            className={cn(
              "rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide",
              isPdcConfermato
                ? "border-blue-300 bg-blue-50 text-blue-700"
                : "border-amber-300 bg-amber-50 text-amber-700",
            )}
          >
            {stato}
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <CalendarRange className="h-3.5 w-3.5" aria-hidden />
          Validità {p.valido_da} → {p.valido_a}
        </div>
        {!isPdcConfermato ? (
          <div className="mt-2 rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-800">
            <AlertTriangle className="mr-1 inline h-3.5 w-3.5" aria-hidden />
            L'auto-assegna è abilitato solo da <strong>PDC_CONFERMATO</strong>.
            Aspetta che il Pianificatore PdC confermi i turni.
          </div>
        ) : null}
      </Card>

      {/* Action: auto-assegna */}
      <Card className="flex items-center justify-between gap-3 p-3">
        <div className="flex items-start gap-2">
          <Wand2 className="mt-0.5 h-4 w-4 text-primary" aria-hidden />
          <div>
            <div className="text-sm font-semibold text-foreground">
              Auto-assegna persone
            </div>
            <div className="text-xs text-muted-foreground">
              Greedy first-fit con vincoli HARD + warning SOFT (§10.6, §11.4,
              §11.5). Idempotente: rispetta le assegnazioni esistenti.
            </div>
          </div>
        </div>
        <Dialog open={autoDialogOpen} onOpenChange={setAutoDialogOpen}>
          <DialogTrigger asChild>
            <Button disabled={!isPdcConfermato}>Esegui auto-assegna…</Button>
          </DialogTrigger>
          <DialogContent>
            <AutoAssegnaDialog
              programmaId={programmaId}
              defaultDataDa={p.valido_da}
              defaultDataA={p.valido_a}
              onSuccess={handleAutoSuccess}
              onCancel={() => setAutoDialogOpen(false)}
            />
          </DialogContent>
        </Dialog>
      </Card>

      {/* Risultato dell'ultimo run */}
      {risultato !== null ? (
        <RisultatoSection
          risultato={risultato}
          onOverride={setOverrideTarget}
        />
      ) : (
        <Card className="border-border bg-muted/30 p-3 text-sm text-muted-foreground">
          Nessun run effettuato. Clicca "Esegui auto-assegna" per iniziare.
        </Card>
      )}

      {/* Dialog override */}
      <Dialog
        open={overrideTarget !== null}
        onOpenChange={(open) => {
          if (!open) setOverrideTarget(null);
        }}
      >
        <DialogContent>
          {overrideTarget !== null ? (
            <OverrideDialog
              programmaId={programmaId}
              mancanza={overrideTarget}
              onSuccess={() => handleOverrideSuccess(overrideTarget)}
              onCancel={() => setOverrideTarget(null)}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}

// =====================================================================
// Auto-assegna dialog
// =====================================================================

function AutoAssegnaDialog({
  programmaId,
  defaultDataDa,
  defaultDataA,
  onSuccess,
  onCancel,
}: {
  programmaId: number;
  defaultDataDa: string;
  defaultDataA: string;
  onSuccess: (data: AutoAssegnaPersoneResponse) => void;
  onCancel: () => void;
}) {
  const [dataDa, setDataDa] = useState(defaultDataDa);
  const [dataA, setDataA] = useState(defaultDataA);
  const mutation = useAutoAssegnaPersone();

  const submit = () => {
    mutation.mutate(
      { id: programmaId, payload: { data_da: dataDa, data_a: dataA } },
      { onSuccess },
    );
  };

  const errore =
    mutation.error instanceof Error ? mutation.error.message : null;

  return (
    <>
      <DialogHeader>
        <DialogTitle>Auto-assegna persone PdC</DialogTitle>
      </DialogHeader>
      <div className="flex flex-col gap-3 text-sm">
        <p className="text-xs text-muted-foreground">
          Finestra calendariale: l'algoritmo espande le giornate dei turni del
          programma sui giorni che matchano la <code>variante_calendario</code>
          {" "}(LMXGV/S/D/F/GG) e assegna persone PdC compatibili.
        </p>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label htmlFor="data-da">Data da (incluso)</Label>
            <Input
              id="data-da"
              type="date"
              value={dataDa}
              onChange={(e) => setDataDa(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="data-a">Data a (inclusa)</Label>
            <Input
              id="data-a"
              type="date"
              value={dataA}
              onChange={(e) => setDataA(e.target.value)}
            />
          </div>
        </div>
        {errore !== null ? (
          <div className="rounded border border-red-300 bg-red-50 p-2 text-xs text-red-800">
            {errore}
          </div>
        ) : null}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onCancel} disabled={mutation.isPending}>
            Annulla
          </Button>
          <Button onClick={submit} disabled={mutation.isPending}>
            {mutation.isPending ? "In corso…" : "Esegui"}
          </Button>
        </div>
      </div>
    </>
  );
}

// =====================================================================
// Risultato (KPI + tabelle)
// =====================================================================

function RisultatoSection({
  risultato,
  onOverride,
}: {
  risultato: AutoAssegnaPersoneResponse;
  onOverride: (mancanza: MancanzaAuto) => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      <KpiRow risultato={risultato} />
      <MancanzeTable mancanze={risultato.mancanze} onOverride={onOverride} />
      {risultato.warning_soft.length > 0 ? (
        <WarningTable warning={risultato.warning_soft} />
      ) : null}
      {risultato.assegnazioni.length > 0 ? (
        <AssegnazioniSummary count={risultato.assegnazioni.length} />
      ) : null}
    </div>
  );
}

function KpiRow({ risultato }: { risultato: AutoAssegnaPersoneResponse }) {
  const tone =
    risultato.delta_copertura_pct >= 95
      ? "ok"
      : risultato.delta_copertura_pct >= 71
        ? "warn"
        : "bad";
  const toneClass =
    tone === "ok"
      ? "border-emerald-300 bg-emerald-50 text-emerald-800"
      : tone === "warn"
        ? "border-amber-300 bg-amber-50 text-amber-800"
        : "border-red-300 bg-red-50 text-red-800";
  return (
    <Card className={cn("flex items-center justify-between gap-3 p-3", toneClass)}>
      <div className="flex items-center gap-2">
        <CheckCircle2 className="h-4 w-4" aria-hidden />
        <div>
          <div className="text-2xl font-semibold leading-none">
            {risultato.delta_copertura_pct}%
          </div>
          <div className="text-[11px] uppercase tracking-wide opacity-80">
            Copertura
          </div>
        </div>
      </div>
      <div className="flex gap-4 text-xs">
        <Kpi label="Coperte" value={risultato.n_giornate_coperte} />
        <Kpi label="Totali" value={risultato.n_giornate_totali} />
        <Kpi label="Nuove" value={risultato.n_assegnazioni_create} />
        <Kpi label="Mancanze" value={risultato.mancanze.length} />
        <Kpi label="Warning" value={risultato.warning_soft.length} />
      </div>
    </Card>
  );
}

function Kpi({ label, value }: { label: string; value: number }) {
  return (
    <div className="text-right">
      <div className="text-base font-semibold leading-none">{value}</div>
      <div className="text-[10px] uppercase tracking-wide opacity-70">
        {label}
      </div>
    </div>
  );
}

function MancanzeTable({
  mancanze,
  onOverride,
}: {
  mancanze: MancanzaAuto[];
  onOverride: (m: MancanzaAuto) => void;
}) {
  if (mancanze.length === 0) {
    return (
      <Card className="border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-800">
        <CheckCircle2 className="mr-1 inline h-4 w-4" aria-hidden />
        Nessuna mancanza: tutte le giornate del periodo sono coperte.
      </Card>
    );
  }
  return (
    <Card className="overflow-hidden">
      <div className="border-b border-border bg-muted/30 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-foreground">
        Mancanze ({mancanze.length})
      </div>
      <table className="w-full text-sm">
        <thead className="bg-muted/20 text-[11px] uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="px-3 py-2 text-left">Data</th>
            <th className="px-3 py-2 text-left">Turno</th>
            <th className="px-3 py-2 text-left">Giornata</th>
            <th className="px-3 py-2 text-left">Motivo</th>
            <th className="px-3 py-2 text-right">Azione</th>
          </tr>
        </thead>
        <tbody>
          {mancanze.map((m) => (
            <tr
              key={`${m.turno_pdc_giornata_id}-${m.data}`}
              className="border-t border-border"
            >
              <td className="px-3 py-2 font-mono text-xs">{m.data}</td>
              <td className="px-3 py-2 text-xs">#{m.turno_pdc_id}</td>
              <td className="px-3 py-2 text-xs">#{m.turno_pdc_giornata_id}</td>
              <td className="px-3 py-2 text-xs text-muted-foreground">
                {MOTIVO_LABEL[m.motivo]}
              </td>
              <td className="px-3 py-2 text-right">
                <Button size="sm" variant="outline" onClick={() => onOverride(m)}>
                  Override <ArrowRight className="ml-1 h-3 w-3" aria-hidden />
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function WarningTable({ warning }: { warning: WarningSoft[] }) {
  return (
    <Card className="overflow-hidden">
      <div className="border-b border-border bg-amber-50 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-amber-800">
        <Info className="mr-1 inline h-3.5 w-3.5" aria-hidden />
        Warning soft ({warning.length})
      </div>
      <table className="w-full text-sm">
        <thead className="bg-muted/20 text-[11px] uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="px-3 py-2 text-left">Data</th>
            <th className="px-3 py-2 text-left">Persona</th>
            <th className="px-3 py-2 text-left">Tipo</th>
            <th className="px-3 py-2 text-left">Descrizione</th>
          </tr>
        </thead>
        <tbody>
          {warning.map((w, idx) => (
            <tr key={idx} className="border-t border-border">
              <td className="px-3 py-2 font-mono text-xs">{w.data}</td>
              <td className="px-3 py-2 text-xs">#{w.persona_id}</td>
              <td className="px-3 py-2 text-xs">{WARNING_LABEL[w.tipo]}</td>
              <td className="px-3 py-2 text-xs text-muted-foreground">
                {w.descrizione}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function AssegnazioniSummary({ count }: { count: number }) {
  return (
    <Card className="border-emerald-300 bg-emerald-50 p-3 text-xs text-emerald-800">
      <CheckCircle2 className="mr-1 inline h-3.5 w-3.5" aria-hidden />
      {count}{" "}
      {count === 1 ? "nuova assegnazione persistita" : "nuove assegnazioni persistite"}
      {" "}su <code>assegnazione_giornata</code> (stato="pianificato").
    </Card>
  );
}

// =====================================================================
// Override dialog
// =====================================================================

function OverrideDialog({
  programmaId,
  mancanza,
  onSuccess,
  onCancel,
}: {
  programmaId: number;
  mancanza: MancanzaAuto;
  onSuccess: () => void;
  onCancel: () => void;
}) {
  const persone = usePersone({ profilo: "PdC", only_active: true });
  const mutation = useAssegnaManuale();
  const [personaId, setPersonaId] = useState<number | null>(null);

  const personeList = useMemo(() => persone.data ?? [], [persone.data]);

  const submit = () => {
    if (personaId === null) return;
    mutation.mutate(
      {
        id: programmaId,
        payload: {
          persona_id: personaId,
          turno_pdc_giornata_id: mancanza.turno_pdc_giornata_id,
          data: mancanza.data,
        },
      },
      { onSuccess },
    );
  };

  const errore =
    mutation.error instanceof Error ? mutation.error.message : null;

  return (
    <>
      <DialogHeader>
        <DialogTitle>Override manuale</DialogTitle>
      </DialogHeader>
      <div className="flex flex-col gap-3 text-sm">
        <div className="rounded border border-border bg-muted/30 p-2 text-xs">
          <div>
            <strong>Data:</strong> {mancanza.data}
          </div>
          <div>
            <strong>Turno:</strong> #{mancanza.turno_pdc_id} · Giornata #
            {mancanza.turno_pdc_giornata_id}
          </div>
          <div className="mt-1 text-muted-foreground">
            Motivo originale:{" "}
            {MOTIVO_LABEL[mancanza.motivo as MotivoMancanza]}
          </div>
        </div>
        <div className="rounded border border-amber-300 bg-amber-50 p-2 text-[11px] text-amber-800">
          <AlertTriangle className="mr-1 inline h-3 w-3" aria-hidden />
          L'override bypassa i vincoli HARD del greedy (sede, indisp, riposo
          intraturno). Il backend valida solo che persona/giornata non siano
          già assegnate sulla stessa data.
        </div>
        <div>
          <Label htmlFor="persona">Persona PdC da assegnare</Label>
          {persone.isLoading ? (
            <Spinner label="Caricamento PdC…" />
          ) : (
            <select
              id="persona"
              className="block w-full rounded border border-border bg-white px-2 py-1 text-sm"
              value={personaId ?? ""}
              onChange={(e) =>
                setPersonaId(e.target.value === "" ? null : Number(e.target.value))
              }
            >
              <option value="">— seleziona —</option>
              {personeList.map((pp) => (
                <option key={pp.id} value={pp.id}>
                  {pp.cognome} {pp.nome} ({pp.codice_dipendente})
                  {pp.depot_codice !== null ? ` · ${pp.depot_codice}` : ""}
                </option>
              ))}
            </select>
          )}
        </div>
        {errore !== null ? (
          <div className="rounded border border-red-300 bg-red-50 p-2 text-xs text-red-800">
            {errore}
          </div>
        ) : null}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onCancel} disabled={mutation.isPending}>
            Annulla
          </Button>
          <Button
            onClick={submit}
            disabled={personaId === null || mutation.isPending}
          >
            {mutation.isPending ? "Assegnando…" : "Conferma override"}
          </Button>
        </div>
      </div>
    </>
  );
}
