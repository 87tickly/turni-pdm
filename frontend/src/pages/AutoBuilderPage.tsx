/**
 * AutoBuilderPage — genera turni PdC automaticamente dal materiale.
 *
 * Pipeline: PDF materiale Trenord -> parser -> 5281 segmenti in DB ->
 * AutoBuilder (genetic + simulated annealing) -> 5-7 giornate PdC con
 * validazione rules (max prestazione, condotta, refezione, riposo).
 *
 * Flusso UX:
 *   1. Utente sceglie deposito + N giornate + tipo (LV/SAB/DOM)
 *   2. Click "Genera" -> chiamata POST /build-auto
 *   3. Preview: lista giornate stacked con chip violazioni, condotta,
 *      prestazione, lista treni per giornata
 *   4. Opzione "Salva come turno" per ciascun giorno o per l'intero blocco
 */

import { useState, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import {
  Sparkles,
  Loader2,
  ChevronRight,
  AlertTriangle,
  CheckCircle2,
  Train,
  Moon,
  Play,
  Building2,
  Calendar,
} from "lucide-react"
import {
  buildAuto,
  getConstants,
  type BuildAutoResponse,
  type BuildAutoEntry,
  type AppConstants,
} from "@/lib/api"

export function AutoBuilderPage() {
  const navigate = useNavigate()
  const [constants, setConstants] = useState<AppConstants | null>(null)
  const [deposito, setDeposito] = useState<string>("")
  const [days, setDays] = useState<number>(5)
  const [loading, setLoading] = useState(false)
  const [elapsed, setElapsed] = useState<number | null>(null)
  const [result, setResult] = useState<BuildAutoResponse | null>(null)
  const [error, setError] = useState<string>("")

  useEffect(() => {
    getConstants()
      .then((c) => {
        setConstants(c)
        if (c.DEPOSITI && c.DEPOSITI.length > 0 && !deposito) {
          setDeposito(c.DEPOSITI[0])
        }
      })
      .catch((e) => setError(e?.message ?? "Errore caricamento costanti"))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleGenerate() {
    if (!deposito) {
      setError("Seleziona un deposito")
      return
    }
    if (!Number.isFinite(days) || days < 1 || days > 14) {
      setError("Numero giornate non valido (1–14)")
      return
    }
    setLoading(true)
    setError("")
    setResult(null)
    const t0 = performance.now()
    try {
      // day_type omesso: il backend usa il default e in futuro lo dedurra'
      // automaticamente dal calendario interno + giro materiale.
      const res = await buildAuto({ deposito, days })
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
      setElapsed((performance.now() - t0) / 1000)
    }
  }

  const turns: BuildAutoEntry[] = result?.calendar.filter((e) => e.type === "TURN") ?? []
  const rests = result?.calendar.filter((e) => e.type === "REST") ?? []
  const hasViolations = (result?.total_violations ?? 0) > 0

  return (
    <div className="flex flex-col h-full">
      {/* ── Header ── */}
      <div className="mb-5 flex items-start justify-between">
        <div>
          <div
            className="text-[10px] font-bold uppercase mb-1"
            style={{
              color: "var(--color-on-surface-quiet)",
              letterSpacing: "0.12em",
            }}
          >
            Auto-builder AI
          </div>
          <h2
            className="font-bold tracking-tight flex items-center gap-2"
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "22px",
              letterSpacing: "-0.02em",
              color: "var(--color-on-surface-strong)",
            }}
          >
            <Sparkles size={20} style={{ color: "var(--color-brand)" }} />
            Genera turni PdC dal materiale
          </h2>
          <p
            className="text-[13px] mt-0.5"
            style={{ color: "var(--color-on-surface-muted)" }}
          >
            Pipeline: PDF turno materiale → 5281 segmenti → AI Engine (genetic + simulated annealing) → turni PdC validati
          </p>
        </div>
      </div>

      {/* ── Form ── */}
      <div
        className="rounded-xl p-5 mb-4"
        style={{
          backgroundColor: "var(--color-surface-container-lowest)",
          boxShadow: "var(--shadow-sm)",
        }}
      >
        <div className="grid grid-cols-1 md:grid-cols-[1fr_160px_auto] gap-3 items-end">
          {/* Deposito */}
          <label className="flex flex-col gap-1.5">
            <span
              className="text-[10px] font-bold uppercase flex items-center gap-1"
              style={{
                color: "var(--color-on-surface-muted)",
                letterSpacing: "0.08em",
              }}
            >
              <Building2 size={10} />
              Deposito
            </span>
            <select
              value={deposito}
              onChange={(e) => setDeposito(e.target.value)}
              disabled={!constants}
              className="px-3 py-2 rounded-md text-[13px] outline-none"
              style={{
                backgroundColor: "var(--color-surface-container-low)",
                color: "var(--color-on-surface-strong)",
                boxShadow: "inset 0 0 0 1px var(--color-ghost)",
                fontFamily: "var(--font-sans)",
              }}
            >
              {!constants && <option value="">Caricamento…</option>}
              {constants?.DEPOSITI.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>

          {/* Giornate (input libero 1-14) */}
          <label className="flex flex-col gap-1.5">
            <span
              className="text-[10px] font-bold uppercase flex items-center gap-1"
              style={{
                color: "var(--color-on-surface-muted)",
                letterSpacing: "0.08em",
              }}
            >
              <Calendar size={10} />
              Giornate
            </span>
            <input
              type="number"
              min={1}
              max={14}
              value={days}
              onChange={(e) => {
                const n = parseInt(e.target.value, 10)
                setDays(Number.isFinite(n) ? n : 0)
              }}
              className="px-3 py-2 rounded-md text-[13px] outline-none"
              style={{
                backgroundColor: "var(--color-surface-container-low)",
                color: "var(--color-on-surface-strong)",
                boxShadow: "inset 0 0 0 1px var(--color-ghost)",
                fontFamily: "var(--font-mono)",
              }}
            />
          </label>

          {/* Generate CTA */}
          <button
            onClick={handleGenerate}
            disabled={loading || !deposito}
            className="text-[13px] font-bold px-5 py-2.5 rounded-md text-white uppercase flex items-center justify-center gap-2 transition-opacity disabled:opacity-40"
            style={{
              background: "var(--gradient-primary)",
              boxShadow: "var(--shadow-sm)",
              letterSpacing: "0.05em",
              minWidth: "160px",
            }}
          >
            {loading ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                Generazione…
              </>
            ) : (
              <>
                <Play size={13} strokeWidth={2.5} />
                Genera turno
              </>
            )}
          </button>
        </div>
      </div>

      {/* ── Error ── */}
      {error && (
        <div
          className="rounded-md px-4 py-2.5 mb-4 flex items-center gap-2 text-[13px]"
          style={{
            backgroundColor: "var(--color-destructive-container)",
            color: "var(--color-destructive)",
          }}
        >
          <AlertTriangle size={14} />
          {error}
        </div>
      )}

      {/* ── Result summary bar ── */}
      {result && (
        <div
          className="rounded-xl px-5 py-3 mb-4 flex items-center gap-5 flex-wrap"
          style={{
            backgroundColor: "var(--color-surface-container-low)",
          }}
        >
          <ResultStat
            label="Giornate"
            value={turns.length.toString()}
            sub={`+ ${rests.length} riposi`}
          />
          <div
            className="h-8 w-px"
            style={{ backgroundColor: "var(--color-ghost)" }}
          />
          <ResultStat
            label="Violazioni"
            value={result.total_violations.toString()}
            tone={hasViolations ? "warning" : "success"}
          />
          <div
            className="h-8 w-px"
            style={{ backgroundColor: "var(--color-ghost)" }}
          />
          <ResultStat
            label="Treni utilizzati"
            value={result.train_dedup.unique_trains.toString()}
            sub={
              result.train_dedup.clean
                ? "nessun duplicato"
                : `${Object.keys(result.train_dedup.duplicates).length} duplicati!`
            }
          />
          <div
            className="h-8 w-px"
            style={{ backgroundColor: "var(--color-ghost)" }}
          />
          <ResultStat
            label="Zona"
            value={`${result.reachable_stations.length}`}
            sub="stazioni"
          />
          {elapsed != null && (
            <>
              <div
                className="h-8 w-px"
                style={{ backgroundColor: "var(--color-ghost)" }}
              />
              <ResultStat
                label="Tempo"
                value={elapsed.toFixed(1) + "s"}
                sub="AI engine"
              />
            </>
          )}
          <button
            onClick={() => navigate("/builder")}
            className="ml-auto text-[12px] font-semibold px-3 py-1.5 rounded-md flex items-center gap-1.5 transition-colors"
            style={{
              color: "var(--color-brand)",
              backgroundColor: "rgba(0, 98, 204, 0.08)",
            }}
          >
            Modifica nel Builder <ChevronRight size={12} />
          </button>
        </div>
      )}

      {/* ── Giornate preview ── */}
      {result && turns.length > 0 && (
        <div className="space-y-3">
          {turns.map((entry) => (
            <DayPreview key={`turn-${entry.day}`} entry={entry} />
          ))}
        </div>
      )}

      {/* ── Empty initial state ── */}
      {!result && !loading && !error && (
        <div
          className="rounded-xl px-6 py-10 text-center"
          style={{
            backgroundColor: "var(--color-surface-container-lowest)",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          <Sparkles
            size={32}
            className="mx-auto mb-3 opacity-40"
            style={{ color: "var(--color-brand)" }}
          />
          <h3
            className="font-semibold mb-1"
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "16px",
              color: "var(--color-on-surface-strong)",
            }}
          >
            Pronto per generare
          </h3>
          <p
            className="text-[12.5px] max-w-md mx-auto"
            style={{ color: "var(--color-on-surface-muted)" }}
          >
            Seleziona un deposito, il numero di giornate e il tipo. L'AI
            Engine costruisce turni validi rispettando tutte le regole
            operative (max prestazione 8h30, max condotta 5h30, refezione
            obbligatoria, riposi minimi).
          </p>
        </div>
      )}
    </div>
  )
}

function ResultStat({
  label,
  value,
  sub,
  tone,
}: {
  label: string
  value: string
  sub?: string
  tone?: "success" | "warning"
}) {
  const valueColor =
    tone === "warning"
      ? "var(--color-warning)"
      : tone === "success"
      ? "var(--color-success)"
      : "var(--color-on-surface-strong)"
  return (
    <div>
      <div
        className="text-[9.5px] font-bold uppercase"
        style={{
          color: "var(--color-on-surface-quiet)",
          letterSpacing: "0.12em",
        }}
      >
        {label}
      </div>
      <div
        className="font-bold"
        style={{
          fontFamily: "var(--font-display)",
          fontSize: "18px",
          color: valueColor,
          letterSpacing: "-0.02em",
          lineHeight: 1.1,
        }}
      >
        {value}
      </div>
      {sub && (
        <div
          className="text-[10px] mt-0.5"
          style={{ color: "var(--color-on-surface-muted)" }}
        >
          {sub}
        </div>
      )}
    </div>
  )
}

function DayPreview({ entry }: { entry: BuildAutoEntry }) {
  const s = entry.summary
  if (!s) return null
  const segments = s.segments ?? []
  const hasViolations = s.violations.length > 0
  const firstFrom = segments[0]?.from_station ?? "—"
  const lastTo = segments[segments.length - 1]?.to_station ?? "—"
  const condottaHours = (s.condotta_min / 60).toFixed(1)
  const prestazioneHours = (s.prestazione_min / 60).toFixed(1)

  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{
        backgroundColor: "var(--color-surface-container-lowest)",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      {/* Day header */}
      <div
        className="px-4 py-3 flex items-center gap-4"
        style={{ backgroundColor: "var(--color-surface-container-low)" }}
      >
        <div
          className="font-bold"
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "16px",
            color: "var(--color-on-surface-strong)",
          }}
        >
          Giornata {entry.day}
        </div>
        <div
          className="text-[11.5px]"
          style={{
            fontFamily: "var(--font-mono)",
            color: "var(--color-on-surface-muted)",
          }}
        >
          {s.presentation_time} → {s.end_time}
        </div>
        <div
          className="text-[11.5px] truncate max-w-[280px]"
          style={{ color: "var(--color-on-surface-muted)" }}
        >
          {firstFrom} → {lastTo}
        </div>
        {s.is_fr && (
          <span
            className="text-[10px] px-1.5 py-0.5 rounded font-semibold"
            style={{
              backgroundColor: "rgba(124, 58, 237, 0.12)",
              color: "#6D28D9",
            }}
          >
            FR
          </span>
        )}
        {s.night_minutes > 0 && (
          <Moon
            size={12}
            style={{ color: "var(--color-on-surface-muted)" }}
          />
        )}
        <div className="ml-auto flex items-center gap-3">
          <InlineMetric label="Cct" value={`${condottaHours}h`} />
          <InlineMetric label="Prest" value={`${prestazioneHours}h`} />
          <InlineMetric label="Refez" value={`${s.meal_min}'`} />
          {hasViolations ? (
            <span
              className="inline-flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-full"
              style={{
                backgroundColor: "var(--color-warning-container)",
                color: "var(--color-warning)",
              }}
            >
              <AlertTriangle size={11} />
              {s.violations.length}
            </span>
          ) : (
            <span
              className="inline-flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-full"
              style={{
                backgroundColor: "var(--color-success-container)",
                color: "var(--color-success)",
              }}
            >
              <CheckCircle2 size={11} />
              OK
            </span>
          )}
        </div>
      </div>

      {/* Segments list */}
      <div className="px-4 py-3 space-y-1">
        {segments.map((seg, i) => (
          <div
            key={`${entry.day}-${i}`}
            className="grid grid-cols-[24px_auto_1fr_auto] items-center gap-3 px-2 py-1.5 rounded-md transition-colors hover:bg-[var(--color-surface-container-low)]"
            style={{ fontFamily: "var(--font-mono)", fontSize: "11.5px" }}
          >
            <Train size={14} style={{ color: "var(--color-brand)" }} />
            <span
              className="font-bold"
              style={{ color: "var(--color-brand)" }}
            >
              {seg.train_id}
            </span>
            <div
              className="flex items-center gap-1 truncate"
              style={{ color: "var(--color-on-surface-muted)" }}
            >
              <span className="truncate">{seg.from_station || "?"}</span>
              <span>→</span>
              <span className="truncate">{seg.to_station || "?"}</span>
            </div>
            <div
              style={{ color: "var(--color-on-surface-strong)", fontWeight: 600 }}
            >
              {seg.dep_time} → {seg.arr_time}
            </div>
          </div>
        ))}
      </div>

      {/* Violations detail */}
      {hasViolations && (
        <div
          className="px-4 py-2.5"
          style={{
            backgroundColor: "var(--color-warning-container)",
            color: "var(--color-warning)",
          }}
        >
          <div
            className="text-[10px] font-bold uppercase mb-1"
            style={{ letterSpacing: "0.08em" }}
          >
            Violazioni ({s.violations.length})
          </div>
          <div className="space-y-1 text-[12px]">
            {s.violations.map((v, i) => (
              <div key={i} className="flex items-start gap-2">
                <span
                  className="shrink-0 text-[9.5px] font-bold uppercase mt-0.5 px-1 rounded"
                  style={{
                    backgroundColor: "rgba(234, 88, 12, 0.15)",
                    letterSpacing: "0.05em",
                  }}
                >
                  {v.severity}
                </span>
                <div className="flex-1">
                  <span className="font-semibold">{v.rule}</span>
                  <span className="ml-1.5 opacity-80">{v.message}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function InlineMetric({ label, value }: { label: string; value: string }) {
  return (
    <span
      className="inline-flex items-center gap-1 text-[11px]"
      style={{ fontFamily: "var(--font-mono)" }}
    >
      <span
        className="text-[9.5px] font-bold uppercase"
        style={{
          color: "var(--color-on-surface-quiet)",
          letterSpacing: "0.08em",
        }}
      >
        {label}
      </span>
      <span
        style={{ color: "var(--color-on-surface-strong)", fontWeight: 600 }}
      >
        {value}
      </span>
    </span>
  )
}
