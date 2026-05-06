/**
 * Pagina "PdE Annuale" del Pianificatore Giro Materiale (Sub-MR 5.bis-d,
 * entry 178).
 *
 * 2 pannelli verticalmente impilati:
 * - PdE Base 2026: ultimo run BASE caricato + bottone "Sostituisci"
 * - Variazioni: timeline cronologica + bottone "Carica variazione"
 *
 * Il PdE base resta come record originale: le variazioni si accumulano
 * cronologicamente e modificano lo stato delle corse per le date
 * specifiche dichiarate. Decisione utente 2026-05-06.
 */

import { useState } from "react";
import type { FormEvent } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ClipboardCheck,
  ClipboardList,
  Database,
  FileSpreadsheet,
  Plus,
  RefreshCw,
  Upload,
} from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Spinner } from "@/components/ui/Spinner";
import { Textarea } from "@/components/ui/Textarea";
import {
  useApplicaVariazione,
  useCaricaPdEBase,
  usePdEStatus,
  useRegistraVariazione,
  useVariazioniGlobali,
} from "@/hooks/usePde";
import { ApiError } from "@/lib/api/client";
import type {
  CorsaImportRun,
  PdEStatus,
  TipoVariazione,
} from "@/lib/api/pde";

const VALID_EXT = [".numbers", ".xlsx"] as const;

const TIPO_VARIAZIONE_LABELS: Record<TipoVariazione, string> = {
  INTEGRAZIONE: "Integrazione (corse nuove)",
  VARIAZIONE_ORARIO: "Variazione orario",
  VARIAZIONE_INTERRUZIONE: "Interruzione linea (rimuove date)",
  VARIAZIONE_CANCELLAZIONE: "Cancellazione corse",
};

export function PdEAnnualeRoute() {
  const statusQuery = usePdEStatus();
  const variazioniQuery = useVariazioniGlobali({ limit: 50 });

  const [baseDialogOpen, setBaseDialogOpen] = useState(false);
  const [variazioneDialogOpen, setVariazioneDialogOpen] = useState(false);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            PdE Annuale
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Programma di Esercizio dell&apos;azienda. Il file base si carica
            una volta a inizio stagione; le variazioni infrannuali si
            accumulano nel tempo e modificano lo stato delle corse per le
            date specifiche.
          </p>
        </div>
      </div>

      <PdEBasePanel
        statusQuery={statusQuery}
        onCarica={() => setBaseDialogOpen(true)}
      />

      <VariazioniTimelinePanel
        statusQuery={statusQuery}
        variazioniQuery={variazioniQuery}
        onCarica={() => setVariazioneDialogOpen(true)}
      />

      <CaricaPdEBaseDialog
        open={baseDialogOpen}
        onOpenChange={setBaseDialogOpen}
      />

      <CaricaVariazioneDialog
        open={variazioneDialogOpen}
        onOpenChange={setVariazioneDialogOpen}
      />
    </div>
  );
}

// =====================================================================
// Pannello PdE Base
// =====================================================================

interface PdEBasePanelProps {
  statusQuery: ReturnType<typeof usePdEStatus>;
  onCarica: () => void;
}

function PdEBasePanel({ statusQuery, onCarica }: PdEBasePanelProps) {
  const status = statusQuery.data;

  if (statusQuery.isLoading) {
    return <PanelSkeleton title="PdE Base" />;
  }
  if (statusQuery.error !== null && statusQuery.error !== undefined) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/[0.04] p-4">
        <div className="flex items-center gap-2 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" aria-hidden />
          Errore caricamento stato PdE
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          {String((statusQuery.error as Error).message)}
        </p>
      </div>
    );
  }
  if (status === undefined) return null;

  const baseRun = status.base_run;
  const hasBase = baseRun !== null;

  return (
    <section className="rounded-lg border border-border bg-white">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-primary" aria-hidden />
          <h2 className="text-sm font-semibold uppercase tracking-wider text-foreground/80">
            PdE Base
          </h2>
          {hasBase ? (
            <Badge className="ml-1 bg-emerald-100 text-emerald-800">
              Caricato
            </Badge>
          ) : (
            <Badge className="ml-1 bg-amber-100 text-amber-800">
              Non caricato
            </Badge>
          )}
        </div>
        <Button
          onClick={onCarica}
          variant={hasBase ? "outline" : "primary"}
          className={
            hasBase
              ? "border-destructive/40 text-destructive hover:bg-destructive/[0.06]"
              : ""
          }
        >
          <Upload className="mr-2 h-4 w-4" aria-hidden />
          {hasBase ? "Sostituisci PdE base" : "Carica PdE base"}
        </Button>
      </header>

      <div className="px-5 py-5">
        {hasBase ? (
          <PdEBaseDettaglio status={status} />
        ) : (
          <div className="flex flex-col items-center gap-3 py-8 text-center">
            <FileSpreadsheet
              className="h-10 w-10 text-muted-foreground/40"
              aria-hidden
            />
            <p className="max-w-md text-sm text-muted-foreground">
              Nessun PdE base caricato per questa azienda. Carica il file
              annuale Trenord (.numbers o .xlsx) per iniziare.
            </p>
          </div>
        )}
      </div>
    </section>
  );
}

function PdEBaseDettaglio({ status }: { status: PdEStatus }) {
  const baseRun = status.base_run;
  if (baseRun === null) return null;

  const importedAt = baseRun.completed_at ?? baseRun.started_at;
  const importedDate = new Date(importedAt);

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Stat label="File" value={baseRun.source_file} mono small />
      <Stat
        label="Caricato il"
        value={importedDate.toLocaleDateString("it-IT", {
          day: "2-digit",
          month: "short",
          year: "numeric",
        })}
      />
      <Stat
        label="Corse attive"
        value={`${status.n_corse_attive.toLocaleString("it-IT")}`}
        sub={
          status.n_corse_totali !== status.n_corse_attive
            ? `(${status.n_corse_totali.toLocaleString("it-IT")} totali · ${(status.n_corse_totali - status.n_corse_attive).toLocaleString("it-IT")} cancellate)`
            : undefined
        }
      />
      <Stat
        label="Validità"
        value={
          status.validity_da !== null && status.validity_a !== null
            ? `${formatDateIt(status.validity_da)} → ${formatDateIt(status.validity_a)}`
            : "—"
        }
        small
      />
      {baseRun.source_hash !== null && (
        <Stat
          label="SHA-256 file"
          value={baseRun.source_hash.slice(0, 16) + "…"}
          mono
          small
        />
      )}
    </div>
  );
}

// =====================================================================
// Pannello Variazioni
// =====================================================================

interface VariazioniTimelinePanelProps {
  statusQuery: ReturnType<typeof usePdEStatus>;
  variazioniQuery: ReturnType<typeof useVariazioniGlobali>;
  onCarica: () => void;
}

function VariazioniTimelinePanel({
  statusQuery,
  variazioniQuery,
  onCarica,
}: VariazioniTimelinePanelProps) {
  const status = statusQuery.data;
  const hasBase = status?.base_run !== null && status?.base_run !== undefined;

  const variazioni = variazioniQuery.data ?? [];

  return (
    <section className="rounded-lg border border-border bg-white">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
        <div className="flex items-center gap-2">
          <ClipboardList className="h-4 w-4 text-primary" aria-hidden />
          <h2 className="text-sm font-semibold uppercase tracking-wider text-foreground/80">
            Variazioni applicate
          </h2>
          <Badge className="ml-1 bg-muted text-muted-foreground">
            {variazioni.length}
          </Badge>
        </div>
        <Button onClick={onCarica} disabled={!hasBase}>
          <Plus className="mr-2 h-4 w-4" aria-hidden />
          Carica variazione
        </Button>
      </header>

      <div className="px-5 py-5">
        {!hasBase ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Carica prima il PdE base per registrare variazioni.
          </p>
        ) : variazioniQuery.isLoading ? (
          <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <Spinner className="h-4 w-4" /> Caricamento timeline…
          </div>
        ) : variazioni.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Nessuna variazione applicata. Le interruzioni linee, integrazioni
            e modifiche orari arriveranno qui durante l&apos;anno.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {variazioni.map((v) => (
              <VariazioneItem key={v.id} variazione={v} />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function VariazioneItem({ variazione }: { variazione: CorsaImportRun }) {
  const isApplicata = variazione.completed_at !== null;
  const dateStr = new Date(
    variazione.completed_at ?? variazione.started_at,
  ).toLocaleDateString("it-IT", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });

  return (
    <li
      className={`flex flex-wrap items-center gap-3 rounded-md border px-4 py-3 ${
        isApplicata
          ? "border-emerald-200 bg-emerald-50/40"
          : "border-amber-200 bg-amber-50/40"
      }`}
    >
      {isApplicata ? (
        <CheckCircle2
          className="h-4 w-4 shrink-0 text-emerald-600"
          aria-hidden
        />
      ) : (
        <ClipboardCheck
          className="h-4 w-4 shrink-0 text-amber-600"
          aria-hidden
        />
      )}
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-foreground">
            {dateStr}
          </span>
          <span className="text-xs text-muted-foreground">·</span>
          <Badge
            className={
              isApplicata
                ? "bg-emerald-100 text-emerald-800"
                : "bg-amber-100 text-amber-800"
            }
          >
            {tipoLabel(variazione.tipo)}
          </Badge>
          {isApplicata && (
            <span className="text-xs text-muted-foreground">
              {variazione.n_corse_create > 0 &&
                `+${variazione.n_corse_create} create`}
              {variazione.n_corse_create > 0 &&
                variazione.n_corse_update > 0 &&
                " · "}
              {variazione.n_corse_update > 0 &&
                `${variazione.n_corse_update} modificate`}
            </span>
          )}
        </div>
        <div className="mt-0.5 truncate font-mono text-xs text-muted-foreground">
          {variazione.source_file}
        </div>
        {variazione.note !== null && variazione.note !== "" && (
          <div className="mt-1 line-clamp-2 text-xs text-muted-foreground/80">
            {variazione.note}
          </div>
        )}
      </div>
      {!isApplicata && (
        <Badge className="bg-amber-100 text-amber-800">
          Da applicare
        </Badge>
      )}
    </li>
  );
}

function tipoLabel(tipo: string): string {
  if (tipo in TIPO_VARIAZIONE_LABELS) {
    return TIPO_VARIAZIONE_LABELS[tipo as TipoVariazione];
  }
  return tipo;
}

// =====================================================================
// Dialog: Carica PdE Base
// =====================================================================

interface CaricaPdEBaseDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function CaricaPdEBaseDialog({ open, onOpenChange }: CaricaPdEBaseDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [force, setForce] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const mutation = useCaricaPdEBase();

  function reset() {
    setFile(null);
    setForce(false);
    setError(null);
    setSuccess(null);
  }

  function handleClose(next: boolean) {
    if (!next) reset();
    onOpenChange(next);
  }

  function isValidExt(name: string): boolean {
    const lower = name.toLowerCase();
    return VALID_EXT.some((ext) => lower.endsWith(ext));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    if (file === null) {
      setError("Seleziona un file PdE (.numbers o .xlsx)");
      return;
    }
    if (!isValidExt(file.name)) {
      setError("Estensione non supportata. Usa .numbers o .xlsx");
      return;
    }
    try {
      const res = await mutation.mutateAsync({ file, force });
      if (res.skipped) {
        setSuccess(
          `File già caricato in precedenza (run #${res.run_id ?? "?"}). ` +
            `Nessuna modifica al DB. ${res.skip_reason ?? ""}`,
        );
      } else {
        setSuccess(
          `PdE caricato in ${res.duration_s.toFixed(1)}s · ` +
            `${res.n_create.toLocaleString("it-IT")} create · ` +
            `${res.n_kept.toLocaleString("it-IT")} invariate · ` +
            `${res.n_delete.toLocaleString("it-IT")} rimosse · ` +
            `${res.n_total.toLocaleString("it-IT")} totali`,
        );
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Errore sconosciuto durante il caricamento");
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Carica PdE base</DialogTitle>
          <DialogDescription>
            File annuale completo Trenord (.numbers o .xlsx, ~10.000 corse).
            Il caricamento è idempotente: se il file è già stato importato
            (stesso SHA-256), il sistema lo segnala senza duplicare nulla.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <Label htmlFor="pde-file" className="text-sm">
              File PdE
            </Label>
            <Input
              id="pde-file"
              type="file"
              accept=".numbers,.xlsx"
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null;
                setFile(f);
                setError(null);
                setSuccess(null);
              }}
              className="mt-1"
            />
            {file !== null && (
              <p className="mt-1 text-xs text-muted-foreground">
                Selezionato: <span className="font-mono">{file.name}</span> (
                {(file.size / 1024 / 1024).toFixed(2)} MB)
              </p>
            )}
          </div>

          <label className="flex items-start gap-2 text-xs">
            <input
              type="checkbox"
              checked={force}
              onChange={(e) => setForce(e.target.checked)}
              className="mt-0.5"
            />
            <span className="text-muted-foreground">
              <strong className="text-foreground">Forza re-import</strong> — salta il
              check di idempotenza e re-importa anche se il file è già stato
              caricato. Da usare solo dopo bug fix nel parser.
            </span>
          </label>

          {error !== null && (
            <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/[0.04] p-3 text-sm text-destructive">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <span>{error}</span>
            </div>
          )}
          {success !== null && (
            <div className="flex items-start gap-2 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <span>{success}</span>
            </div>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleClose(false)}
              disabled={mutation.isPending}
            >
              {success !== null ? "Chiudi" : "Annulla"}
            </Button>
            {success === null && (
              <Button type="submit" disabled={file === null || mutation.isPending}>
                {mutation.isPending ? (
                  <>
                    <Spinner className="mr-2 h-4 w-4" /> Caricamento (~30s)…
                  </>
                ) : (
                  <>
                    <Upload className="mr-2 h-4 w-4" aria-hidden /> Carica
                  </>
                )}
              </Button>
            )}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// =====================================================================
// Dialog: Carica Variazione
// =====================================================================

interface CaricaVariazioneDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function CaricaVariazioneDialog({
  open,
  onOpenChange,
}: CaricaVariazioneDialogProps) {
  const [tipo, setTipo] = useState<TipoVariazione>("INTEGRAZIONE");
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const registraMutation = useRegistraVariazione();
  const applicaMutation = useApplicaVariazione();

  function reset() {
    setTipo("INTEGRAZIONE");
    setFile(null);
    setNote("");
    setError(null);
    setSuccess(null);
  }

  function handleClose(next: boolean) {
    if (!next) reset();
    onOpenChange(next);
  }

  function isValidExt(name: string): boolean {
    const lower = name.toLowerCase();
    return VALID_EXT.some((ext) => lower.endsWith(ext));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    if (file === null) {
      setError("Seleziona un file di variazione (.numbers o .xlsx)");
      return;
    }
    if (!isValidExt(file.name)) {
      setError("Estensione non supportata. Usa .numbers o .xlsx");
      return;
    }
    try {
      // 1) Registra metadati
      const run = await registraMutation.mutateAsync({
        tipo,
        source_file: file.name,
        note: note.trim() === "" ? null : note.trim(),
      });
      // 2) Applica concretamente
      const res = await applicaMutation.mutateAsync({
        runId: run.id,
        file,
      });
      const parts: string[] = [];
      if (res.n_corse_create > 0)
        parts.push(`${res.n_corse_create} create`);
      if (res.n_corse_update > 0)
        parts.push(`${res.n_corse_update} modificate`);
      if (res.n_warnings > 0) parts.push(`${res.n_warnings} warning`);
      const summary = parts.length > 0 ? parts.join(" · ") : "nessuna modifica";
      setSuccess(
        `Variazione applicata: ${summary}. ` +
          `${res.n_corse_lette_da_file} corse lette dal file.`,
      );
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Errore sconosciuto");
      }
    }
  }

  const isPending = registraMutation.isPending || applicaMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Carica variazione PdE</DialogTitle>
          <DialogDescription>
            File di variazione infrannuale: integrazione, interruzione,
            modifica orari, cancellazione. Le variazioni si accumulano e
            modificano lo stato corrente delle corse senza sostituire il
            PdE base.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <Label htmlFor="var-tipo" className="text-sm">
              Tipo variazione
            </Label>
            <select
              id="var-tipo"
              value={tipo}
              onChange={(e) => setTipo(e.target.value as TipoVariazione)}
              className="mt-1 w-full rounded-md border border-border bg-white px-3 py-2 text-sm shadow-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            >
              {(Object.keys(TIPO_VARIAZIONE_LABELS) as TipoVariazione[]).map(
                (t) => (
                  <option key={t} value={t}>
                    {TIPO_VARIAZIONE_LABELS[t]}
                  </option>
                ),
              )}
            </select>
          </div>

          <div>
            <Label htmlFor="var-file" className="text-sm">
              File variazione
            </Label>
            <Input
              id="var-file"
              type="file"
              accept=".numbers,.xlsx"
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null;
                setFile(f);
                setError(null);
                setSuccess(null);
              }}
              className="mt-1"
            />
            {file !== null && (
              <p className="mt-1 text-xs text-muted-foreground">
                Selezionato: <span className="font-mono">{file.name}</span> (
                {(file.size / 1024).toFixed(0)} KB)
              </p>
            )}
          </div>

          <div>
            <Label htmlFor="var-note" className="text-sm">
              Note (opzionale)
            </Label>
            <Textarea
              id="var-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="es. Lavori RFI linea S6, interruzione 15-30/06"
              className="mt-1 min-h-20"
              maxLength={1000}
            />
          </div>

          {error !== null && (
            <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/[0.04] p-3 text-sm text-destructive">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <span>{error}</span>
            </div>
          )}
          {success !== null && (
            <div className="flex items-start gap-2 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <span>{success}</span>
            </div>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleClose(false)}
              disabled={isPending}
            >
              {success !== null ? "Chiudi" : "Annulla"}
            </Button>
            {success === null && (
              <Button type="submit" disabled={file === null || isPending}>
                {isPending ? (
                  <>
                    <Spinner className="mr-2 h-4 w-4" />{" "}
                    {registraMutation.isPending
                      ? "Registrazione…"
                      : "Applicazione…"}
                  </>
                ) : (
                  <>
                    <RefreshCw className="mr-2 h-4 w-4" aria-hidden /> Carica e applica
                  </>
                )}
              </Button>
            )}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// =====================================================================
// Helpers UI
// =====================================================================

interface StatProps {
  label: string;
  value: string;
  sub?: string;
  mono?: boolean;
  small?: boolean;
}

function Stat({ label, value, sub, mono, small }: StatProps) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div
        className={`${small === true ? "text-sm" : "text-base"} font-medium text-foreground ${mono === true ? "font-mono" : ""} truncate`}
        title={value}
      >
        {value}
      </div>
      {sub !== undefined && (
        <div className="text-[11px] text-muted-foreground">{sub}</div>
      )}
    </div>
  );
}

function PanelSkeleton({ title }: { title: string }) {
  return (
    <section className="rounded-lg border border-border bg-white">
      <header className="flex items-center justify-between border-b border-border px-5 py-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-foreground/80">
          {title}
        </h2>
      </header>
      <div className="flex items-center gap-2 px-5 py-6 text-sm text-muted-foreground">
        <Spinner className="h-4 w-4" /> Caricamento…
      </div>
    </section>
  );
}

function formatDateIt(iso: string): string {
  return new Date(iso).toLocaleDateString("it-IT", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}
