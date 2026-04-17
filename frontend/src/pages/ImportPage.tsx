import { useState, useRef, useCallback, useEffect } from "react"
import {
  Upload,
  FileText,
  CheckCircle,
  AlertTriangle,
  Loader2,
  Database,
  Train,
  Info,
} from "lucide-react"
import { cn } from "@/lib/utils"
import {
  uploadTurnoMateriale,
  uploadTurnoPersonale,
  uploadTurnoPdc,
  getDbInfo,
  type UploadResult,
  type TurnoPersonaleResult,
  type TurnoPdcResult,
  type DbInfo,
} from "@/lib/api"
import { PdcUploadFlow } from "@/components/PdcUploadFlow"

// ── Upload card component ───────────────────────────────────────

type UploadStatus = "idle" | "uploading" | "success" | "error"

function UploadCard({
  title,
  description,
  accent,
  icon: Icon,
  onUpload,
  children,
}: {
  title: string
  description: string
  accent: string
  icon: typeof Upload
  onUpload: (file: File) => Promise<void>
  children?: React.ReactNode
}) {
  const [status, setStatus] = useState<UploadStatus>("idle")
  const [error, setError] = useState("")
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = useCallback(
    async (file: File) => {
      if (!file.name.toLowerCase().endsWith(".pdf")) {
        setError("Solo file PDF accettati")
        setStatus("error")
        return
      }
      setStatus("uploading")
      setError("")
      try {
        await onUpload(file)
        setStatus("success")
      } catch (e) {
        setError(e instanceof Error ? e.message : "Errore upload")
        setStatus("error")
      }
    },
    [onUpload]
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragOver(false)
      const file = e.dataTransfer.files[0]
      if (file) handleFile(file)
    },
    [handleFile]
  )

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) handleFile(file)
      // Reset per permettere re-upload dello stesso file
      e.target.value = ""
    },
    [handleFile]
  )

  return (
    <div className="bg-card rounded-lg border border-border-subtle">
      {/* Header */}
      <div className="px-4 py-3 flex items-center gap-3 border-b border-border-subtle">
        <div
          className={cn(
            "w-8 h-8 rounded-lg flex items-center justify-center shrink-0",
            accent
          )}
        >
          <Icon size={16} />
        </div>
        <div>
          <h3 className="text-[13px] font-semibold">{title}</h3>
          <p className="text-[11px] text-muted-foreground">{description}</p>
        </div>
      </div>

      {/* Drop zone */}
      <div className="p-4">
        <input
          ref={inputRef}
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={handleInputChange}
        />
        <button
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault()
            setDragOver(true)
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          disabled={status === "uploading"}
          className={cn(
            "w-full flex flex-col items-center justify-center gap-2 py-6 rounded-lg border-2 border-dashed transition-colors cursor-pointer",
            dragOver
              ? "border-primary bg-primary/5"
              : status === "uploading"
                ? "border-muted cursor-wait"
                : "border-border hover:border-primary/50 hover:bg-muted/30"
          )}
        >
          {status === "uploading" ? (
            <>
              <Loader2 size={20} className="animate-spin text-primary" />
              <span className="text-[12px] text-muted-foreground">
                Caricamento in corso...
              </span>
            </>
          ) : (
            <>
              <Upload size={20} className="text-muted-foreground" />
              <span className="text-[12px] text-muted-foreground">
                Trascina un PDF qui o clicca per selezionare
              </span>
            </>
          )}
        </button>

        {/* Status messages */}
        {status === "success" && (
          <div className="flex items-center gap-2 mt-3 text-[12px] text-success bg-success/10 p-2 rounded-lg border border-success/20">
            <CheckCircle size={14} />
            Import completato
          </div>
        )}

        {status === "error" && error && (
          <div className="flex items-center gap-2 mt-3 text-[12px] text-destructive bg-destructive/10 p-2 rounded-lg border border-destructive/20">
            <AlertTriangle size={14} />
            {error}
          </div>
        )}

        {/* Result details (injected by parent) */}
        {children}
      </div>
    </div>
  )
}

// ── Materiale result ────────────────────────────────────────────

function MaterialeResult({ data }: { data: UploadResult }) {
  return (
    <div className="mt-3 space-y-2">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <StatPill label="Segmenti" value={data.segments_imported} />
        <StatPill label="Treni unici" value={data.unique_trains_count} />
        <StatPill label="Turni" value={data.turn_numbers.length} />
        <StatPill
          label="Confidenza alta"
          value={`${data.confidence.high}`}
          accent={data.confidence.high > data.confidence.low}
        />
      </div>

      {data.warnings.length > 0 && (
        <div className="space-y-1">
          {data.warnings.map((w, i) => (
            <p key={i} className="text-[11px] text-warning flex items-start gap-1">
              <Info size={11} className="shrink-0 mt-0.5" />
              {w}
            </p>
          ))}
        </div>
      )}

      {data.saved_shift_warnings.length > 0 && (
        <div className="space-y-1">
          <p className="text-[11px] text-muted-foreground font-medium">
            Turni salvati interessati:
          </p>
          {data.saved_shift_warnings.map((w, i) => (
            <p key={i} className="text-[11px] text-warning flex items-start gap-1">
              <AlertTriangle size={11} className="shrink-0 mt-0.5" />
              {w}
            </p>
          ))}
        </div>
      )}

      {data.previous_data_cleared && (
        <p className="text-[11px] text-muted-foreground">
          Dati precedenti rimossi ({data.previous_segments_cleared} segmenti)
        </p>
      )}
    </div>
  )
}

// ── Personale result ────────────────────────────────────────────

function PersonaleResult({ data }: { data: TurnoPersonaleResult }) {
  return (
    <div className="mt-3 space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <StatPill label="Pagine parsed" value={data.pages_parsed} />
        <StatPill label="Giorni trovati" value={data.days.length} />
      </div>
      {data.parse_warning && (
        <p className="text-[11px] text-warning flex items-start gap-1">
          <Info size={11} className="shrink-0 mt-0.5" />
          {data.parse_warning}
        </p>
      )}
      <p className="text-[10px] text-muted-foreground italic">
        Solo visualizzazione — i dati non vengono salvati nel database
      </p>
    </div>
  )
}

// ── Stat pill ───────────────────────────────────────────────────

function StatPill({
  label,
  value,
  accent,
}: {
  label: string
  value: string | number
  accent?: boolean
}) {
  return (
    <div className="bg-muted/50 rounded-lg px-3 py-2">
      <p className="text-[10px] text-muted-foreground">{label}</p>
      <p
        className={cn(
          "text-[14px] font-semibold font-mono",
          accent ? "text-success" : "text-foreground"
        )}
      >
        {value}
      </p>
    </div>
  )
}

// ── Main page ───────────────────────────────────────────────────

export function ImportPage() {
  // Results
  const [materialeResult, setMaterialeResult] = useState<UploadResult | null>(null)
  const [personaleResult, setPersonaleResult] = useState<TurnoPersonaleResult | null>(null)
  const [pdcResult, setPdcResult] = useState<TurnoPdcResult | null>(null)

  // DB stats
  const [dbInfo, setDbInfo] = useState<DbInfo | null>(null)

  useEffect(() => {
    getDbInfo()
      .then(setDbInfo)
      .catch(() => {})
  }, [materialeResult]) // refresh after import

  const handleMateriale = useCallback(async (file: File) => {
    const result = await uploadTurnoMateriale(file)
    setMaterialeResult(result)
  }, [])

  const handlePersonale = useCallback(async (file: File) => {
    const result = await uploadTurnoPersonale(file)
    setPersonaleResult(result)
  }, [])

  // handlePdc rimosso: il flusso PdC usa ora PdcUploadFlow (anteprima + conferma)
  void uploadTurnoPdc // tenuto importato per retro-compatibilita' (usato in futuro da CLI)

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h2 className="text-lg font-semibold tracking-tight">Importa dati</h2>
        <p className="text-[13px] text-muted-foreground mt-0.5">
          Carica PDF per popolare il database treni e turni
        </p>
      </div>

      {/* Upload cards */}
      <div className="space-y-4">
        {/* Turno Materiale — primary */}
        <UploadCard
          title="Turno materiale"
          description="PDF Gantt con i turni materiale (rotazione treni). Sovrascrive i dati precedenti."
          accent="bg-primary/10 text-primary"
          icon={Train}
          onUpload={handleMateriale}
        >
          {materialeResult && <MaterialeResult data={materialeResult} />}
        </UploadCard>

        {/* Grid for secondary imports */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Turno Personale */}
          <UploadCard
            title="Turno personale"
            description="PDF turno personale macchinista. Solo lettura, non salva nel DB."
            accent="bg-success/10 text-success"
            icon={FileText}
            onUpload={handlePersonale}
          >
            {personaleResult && <PersonaleResult data={personaleResult} />}
          </UploadCard>

          {/* Turno PdC: flusso a 2 step (anteprima → conferma) */}
          <PdcUploadFlow
            pdcResult={pdcResult}
            setPdcResult={setPdcResult}
          />
        </div>
      </div>

      {/* Current DB stats */}
      {dbInfo && (
        <div className="mt-8">
          <div className="flex items-center gap-2 mb-3">
            <Database size={14} className="text-muted-foreground" />
            <h3 className="text-[13px] font-semibold text-muted-foreground">
              Stato database corrente
            </h3>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <StatPill label="Segmenti" value={dbInfo.total_segments} />
            <StatPill label="Treni unici" value={dbInfo.unique_trains_count} />
            <StatPill
              label="Turni materiale"
              value={dbInfo.material_turns.length}
            />
            <StatPill
              label="Varianti giorno"
              value={dbInfo.day_indices.length}
            />
          </div>
        </div>
      )}
    </div>
  )
}
