/**
 * PdcUploadFlow — Flusso upload Turno PdC con anteprima e conferma.
 *
 * Step 1: utente seleziona PDF → chiamata ?dry_run=true
 * Step 2: mostra diff (nuovi / aggiornati / non più presenti) + lista turni
 * Step 3: utente clicca "Conferma e salva" → chiamata vera → inserimento
 *         versionato. I turni precedenti con stesso (codice, impianto)
 *         vengono marcati superseded.
 *
 * Accanto al flusso mostra lo storico degli import (pdc_import records)
 * con il conteggio dei turni ancora attivi per ciascuno.
 */

import { useCallback, useEffect, useRef, useState } from "react"
import { Layers, Upload, Loader2, CheckCircle2, XCircle, ArrowRight, Clock, AlertTriangle } from "lucide-react"
import {
  uploadTurnoPdc,
  uploadTurnoPdcPreview,
  listPdcImports,
  type TurnoPdcResult,
  type TurnoPdcPreviewResult,
  type PdcImportRecord,
} from "@/lib/api"
import { cn } from "@/lib/utils"

interface Props {
  pdcResult: TurnoPdcResult | null
  setPdcResult: (r: TurnoPdcResult | null) => void
}

type Stage = "idle" | "previewing" | "preview" | "committing" | "error"

export function PdcUploadFlow({ pdcResult, setPdcResult }: Props) {
  const [stage, setStage] = useState<Stage>("idle")
  const [pending, setPending] = useState<File | null>(null)
  const [preview, setPreview] = useState<TurnoPdcPreviewResult | null>(null)
  const [error, setError] = useState("")
  const [imports, setImports] = useState<PdcImportRecord[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  const refreshImports = useCallback(async () => {
    try {
      const res = await listPdcImports()
      setImports(res.imports)
    } catch {
      // silenzioso
    }
  }, [])

  useEffect(() => {
    refreshImports()
  }, [refreshImports])

  const onFileSelected = useCallback(async (file: File) => {
    setPending(file)
    setPreview(null)
    setError("")
    setPdcResult(null)
    setStage("previewing")
    try {
      const p = await uploadTurnoPdcPreview(file)
      setPreview(p)
      setStage("preview")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Errore preview")
      setStage("error")
    }
  }, [setPdcResult])

  const onConfirm = useCallback(async () => {
    if (!pending) return
    setStage("committing")
    setError("")
    try {
      const res = await uploadTurnoPdc(pending)
      setPdcResult(res)
      setStage("idle")
      setPending(null)
      setPreview(null)
      refreshImports()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Errore caricamento")
      setStage("error")
    }
  }, [pending, setPdcResult, refreshImports])

  const onCancel = useCallback(() => {
    setPending(null)
    setPreview(null)
    setError("")
    setStage("idle")
    if (inputRef.current) inputRef.current.value = ""
  }, [])

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault()
  }
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const file = e.dataTransfer.files?.[0]
    if (file) onFileSelected(file)
  }

  return (
    <div className="border border-border-subtle rounded-lg overflow-hidden bg-card">
      {/* Header */}
      <div className="p-4 flex items-start gap-3 border-b border-border-subtle">
        <div className="h-10 w-10 rounded-lg bg-warning/10 text-warning flex items-center justify-center shrink-0">
          <Layers size={18} />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-[14px]">Turno PdC (RFI)</h3>
          <p className="text-[11px] text-muted-foreground mt-0.5 leading-snug">
            PDF turni Posto di Condotta. <strong>Prima anteprima</strong> con il diff vs turni attivi,
            poi conferma per salvare. I turni precedenti vengono archiviati automaticamente.
          </p>
        </div>
      </div>

      {/* Stage: idle → selezione file */}
      {stage === "idle" && (
        <div
          className="p-6 text-center border-2 border-dashed border-border-subtle m-3 rounded-md cursor-pointer hover:border-primary/50 transition-colors"
          onClick={() => inputRef.current?.click()}
          onDragOver={onDragOver}
          onDrop={onDrop}
        >
          <Upload size={22} className="mx-auto text-muted-foreground mb-2" />
          <p className="text-[12px] font-medium">Trascina il PDF o clicca per scegliere</p>
          <p className="text-[10px] text-muted-foreground mt-1">
            Compatibile col modello MDL-PdC (SGI Turni del Personale Mobile)
          </p>
          <input
            ref={inputRef}
            type="file"
            accept=".pdf"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) onFileSelected(f)
            }}
          />
        </div>
      )}

      {/* Stage: previewing → spinner */}
      {stage === "previewing" && (
        <div className="p-6 text-center">
          <Loader2 size={22} className="mx-auto animate-spin text-primary mb-2" />
          <p className="text-[12px]">Analisi PDF in corso...</p>
          <p className="text-[10px] text-muted-foreground">
            {pending?.name}
          </p>
        </div>
      )}

      {/* Stage: preview → mostra diff + summary + bottoni */}
      {stage === "preview" && preview && (
        <div className="p-4 space-y-3">
          <div className="text-[12px]">
            <span className="text-muted-foreground">File: </span>
            <span className="font-mono">{preview.filename}</span>
            <span className="text-muted-foreground">
              {" "}· {preview.n_pagine_pdf} pagine · {preview.turni_parsed} turni estratti
            </span>
          </div>

          {/* Diff summary */}
          <DiffPanel diff={preview.diff} />

          {/* Lista compatta turni */}
          <details className="text-[11px]">
            <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
              Mostra lista turni ({preview.summary.length})
            </summary>
            <div className="mt-2 grid grid-cols-2 md:grid-cols-3 gap-1 max-h-40 overflow-y-auto">
              {preview.summary.map((t) => (
                <div key={`${t.codice}-${t.impianto}`}
                     className="font-mono text-[10px] bg-muted/50 px-2 py-1 rounded">
                  <span className="font-bold">{t.codice}</span>
                  <span className="text-muted-foreground"> · {t.impianto}</span>
                </div>
              ))}
            </div>
          </details>

          {/* Azioni */}
          <div className="flex items-center gap-2 pt-2 border-t border-border-subtle">
            <button
              onClick={onConfirm}
              className="flex-1 px-3 py-2 bg-primary text-primary-foreground rounded text-[12px] font-medium hover:bg-primary/90 flex items-center justify-center gap-2"
            >
              <CheckCircle2 size={13} />
              Conferma e salva
              <ArrowRight size={12} />
            </button>
            <button
              onClick={onCancel}
              className="px-3 py-2 bg-muted text-muted-foreground rounded text-[12px] hover:bg-muted/80"
            >
              Annulla
            </button>
          </div>
        </div>
      )}

      {/* Stage: committing → spinner */}
      {stage === "committing" && (
        <div className="p-6 text-center">
          <Loader2 size={22} className="mx-auto animate-spin text-primary mb-2" />
          <p className="text-[12px]">Salvataggio import + archiviazione turni precedenti...</p>
        </div>
      )}

      {/* Stage: error */}
      {stage === "error" && (
        <div className="p-4">
          <div className="p-3 rounded bg-destructive/10 border border-destructive/30 flex items-start gap-2">
            <XCircle size={14} className="text-destructive mt-0.5 shrink-0" />
            <div className="text-[12px] text-destructive flex-1">
              <div className="font-semibold mb-0.5">Errore</div>
              <div>{error}</div>
            </div>
            <button
              onClick={onCancel}
              className="text-[11px] px-2 py-1 rounded hover:bg-destructive/20"
            >
              Riprova
            </button>
          </div>
        </div>
      )}

      {/* Risultato ultimo commit (successo) */}
      {pdcResult && stage === "idle" && (
        <div className="mx-3 mb-3 p-3 rounded bg-success/10 border border-success/30 text-[11px]">
          <div className="flex items-center gap-2 mb-1 text-success font-semibold">
            <CheckCircle2 size={13} />
            Import #{pdcResult.import_id} completato
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-1 text-foreground">
            <Stat label="Turni importati" value={pdcResult.turni_imported} />
            <Stat label="Archiviati" value={pdcResult.turni_superseded ?? 0} />
            <Stat label="Giornate" value={pdcResult.days_imported} />
            <Stat label="Blocchi" value={pdcResult.blocks_imported} />
          </div>
        </div>
      )}

      {/* Storico import */}
      {imports.length > 0 && stage === "idle" && !pdcResult && (
        <div className="border-t border-border-subtle bg-muted/20 p-3">
          <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground mb-2">
            <Clock size={11} />
            <span className="font-medium">Storico import ({imports.length})</span>
          </div>
          <div className="space-y-1">
            {imports.slice(0, 3).map((imp) => (
              <div key={imp.id}
                   className="text-[10px] font-mono grid grid-cols-[auto_1fr_auto_auto] gap-2 items-center">
                <span className="px-1.5 py-0.5 bg-card rounded border border-border-subtle">
                  #{imp.id}
                </span>
                <span className="truncate" title={imp.filename}>
                  {imp.filename}
                </span>
                <span className="text-muted-foreground">
                  {imp.valido_dal} → {imp.valido_al}
                </span>
                <span className={cn(
                  "px-1.5 py-0.5 rounded text-[9px]",
                  imp.turni_attivi > 0
                    ? "bg-success/15 text-success"
                    : "bg-muted text-muted-foreground"
                )}>
                  {imp.turni_attivi} / {imp.n_turni} attivi
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Sottocomponenti ────────────────────────────────────────────

function DiffPanel({ diff }: { diff: TurnoPdcPreviewResult["diff"] }) {
  const { counts } = diff
  const hasOnlyOld = counts.only_in_old > 0
  return (
    <div className="grid grid-cols-3 gap-2">
      <DiffCell
        label="Nuovi"
        count={counts.new}
        accent="bg-primary/10 text-primary border-primary/30"
        hint="Mai visti prima"
      />
      <DiffCell
        label="Aggiornati"
        count={counts.updated}
        accent="bg-amber-500/10 text-amber-700 border-amber-400/30"
        hint="Sostituiscono l'esistente"
      />
      <DiffCell
        label="Non più presenti"
        count={counts.only_in_old}
        accent={hasOnlyOld
          ? "bg-destructive/10 text-destructive border-destructive/30"
          : "bg-muted text-muted-foreground border-border-subtle"}
        hint="Rimangono attivi, vanno archiviati manualmente"
        warningIcon={hasOnlyOld}
      />
    </div>
  )
}

function DiffCell({
  label, count, accent, hint, warningIcon,
}: {
  label: string
  count: number
  accent: string
  hint: string
  warningIcon?: boolean
}) {
  return (
    <div className={cn("rounded-md border p-2.5", accent)}>
      <div className="flex items-center gap-1.5">
        {warningIcon && <AlertTriangle size={11} />}
        <div className="text-[10px] font-medium uppercase tracking-wider">{label}</div>
      </div>
      <div className="text-2xl font-mono font-bold tabular-nums mt-0.5">{count}</div>
      <div className="text-[9px] opacity-75 mt-0.5 leading-tight">{hint}</div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="bg-card rounded px-2 py-1 border border-border-subtle">
      <div className="text-[9px] text-muted-foreground uppercase tracking-wider">{label}</div>
      <div className="font-mono font-bold">{value}</div>
    </div>
  )
}
