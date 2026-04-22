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
  buildAutoWeekly,
  getConstants,
  type BuildAutoWeeklyResponse,
  type BuildAutoWeeklyDay,
  type AutoWeeklyVariant,
  type AppConstants,
} from "@/lib/api"
import { AbilitazioniPanel } from "@/components/AbilitazioniPanel"
import { AutoBuilderGantt } from "@/components/AutoBuilderGantt"

export function AutoBuilderPage() {
  const navigate = useNavigate()
  const [constants, setConstants] = useState<AppConstants | null>(null)
  const [deposito, setDeposito] = useState<string>("")
  const [nDays, setNDays] = useState<number>(5)
  const [loading, setLoading] = useState(false)
  const [elapsed, setElapsed] = useState<number | null>(null)
  const [result, setResult] = useState<BuildAutoWeeklyResponse | null>(null)
  const [error, setError] = useState<string>("")
  const [progress, setProgress] = useState<number>(0)
  const [progressPhase, setProgressPhase] = useState<string>("")

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

  // Barra di progresso simulata: nessun feedback reale dal backend, ma la
  // curva e' calibrata sui tempi tipici del builder (~25-35s per 5 giornate
  // x 3 varianti). Fasi a soglie temporali basate sui log backend.
  useEffect(() => {
    if (!loading) {
      setProgress(0)
      setProgressPhase("")
      return
    }
    const t0 = performance.now()
    // Tempo atteso ~35-40s per 5 gg * 3 varianti (1 chiamata LV completa
    // + N chiamate SAB/DOM quick). Scala con nDays.
    const expectedMs = Math.max(20000, nDays * 8000)
    const phases: Array<{ at: number; label: string }> = [
      { at: 0, label: "Caricamento pool ARTURO + DB material" },
      { at: 0.15, label: "Fase 2 · Multi-restart (25 tentativi)" },
      { at: 0.45, label: "Fase 3 · Genetic crossover" },
      { at: 0.65, label: "Fase 4 · Simulated annealing" },
      { at: 0.80, label: "Ricerca varianti SAB/DOM" },
      { at: 0.93, label: "Verifica orari via live.arturo.travel" },
    ]
    const id = window.setInterval(() => {
      const elapsed = (performance.now() - t0) / expectedMs // 0..inf
      // Curva: lineare fino 0.9, poi asymptotic verso 0.98 (mai raggiunto)
      let pct: number
      if (elapsed < 0.9) {
        pct = elapsed * 95 // 0..85.5
      } else {
        // Asymptotic: l'extra tempo non supera 98%
        const over = elapsed - 0.9
        pct = 85.5 + (1 - Math.exp(-over * 2)) * 12.5
      }
      pct = Math.min(98, Math.max(0, pct))
      setProgress(pct)
      // Fase corrente
      const normalized = Math.min(1, elapsed)
      let current = phases[0].label
      for (const p of phases) {
        if (normalized >= p.at) current = p.label
      }
      setProgressPhase(current)
    }, 150)
    return () => window.clearInterval(id)
  }, [loading, nDays])

  async function handleGenerate() {
    if (!deposito) {
      setError("Seleziona un deposito")
      return
    }
    if (!Number.isFinite(nDays) || nDays < 1 || nDays > 60) {
      setError("Numero giornate non valido (1–60)")
      return
    }
    setLoading(true)
    setError("")
    setResult(null)
    setProgress(0)
    setProgressPhase("Avvio…")
    const t0 = performance.now()
    try {
      // build-auto-weekly: ritorna N giornate del turno materiale, ciascuna
      // con le 3 varianti LMXGV/S/D come nel PDF originale Trenord
      const res = await buildAutoWeekly({ deposito, days: nDays })
      setProgress(100)
      setProgressPhase("Completato")
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      // Breve delay per mostrare 100% prima di nascondere
      setTimeout(() => setLoading(false), 250)
      setElapsed((performance.now() - t0) / 1000)
    }
  }

  const days: BuildAutoWeeklyDay[] = result?.days ?? []
  // Conta totali delle violazioni su tutte le varianti (escluse info)
  const totalViolations = days.reduce(
    (acc, d) => acc + d.variants.reduce(
      (a, v) => a + (v.summary?.violations.filter(x => x.severity !== "info").length ?? 0),
      0,
    ),
    0,
  )
  const hasViolations = totalViolations > 0
  // Treni unici usati tra tutte le varianti
  const allTrainIds = new Set<string>()
  days.forEach((d) => {
    d.variants.forEach((v) => {
      v.summary?.segments.forEach((seg) => {
        if (seg.train_id && !seg.is_deadhead) allTrainIds.add(seg.train_id)
      })
    })
  })

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

      {/* ── Step 0: Abilitazioni del deposito (collassabile) ── */}
      {deposito && <AbilitazioniPanel deposito={deposito} />}

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
              max={60}
              value={nDays}
              onChange={(e) => {
                const n = parseInt(e.target.value, 10)
                setNDays(Number.isFinite(n) ? n : 0)
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
                {Math.floor(progress)}%
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

      {/* ── Progress bar durante generazione ── */}
      {loading && (
        <div
          className="rounded-xl px-5 py-3 mb-4"
          style={{
            backgroundColor: "var(--color-surface-container-lowest)",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          <div className="flex items-center justify-between mb-2">
            <span
              className="text-[11px] font-semibold uppercase"
              style={{
                fontFamily: "var(--font-display)",
                color: "var(--color-on-surface-muted)",
                letterSpacing: "0.08em",
              }}
            >
              {progressPhase || "Avvio…"}
            </span>
            <span
              className="text-[13px] font-bold"
              style={{
                fontFamily: "var(--font-mono)",
                color: "var(--color-brand)",
              }}
            >
              {Math.floor(progress)}%
            </span>
          </div>
          <div
            className="h-1.5 rounded-full overflow-hidden"
            style={{ backgroundColor: "var(--color-surface-container-high)" }}
          >
            <div
              className="h-full rounded-full transition-all duration-300 ease-out"
              style={{
                width: `${progress}%`,
                background: "var(--gradient-primary)",
              }}
            />
          </div>
        </div>
      )}

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
            label="Giornate materiale"
            value={days.length.toString()}
            sub="con 3 varianti LMXGV/S/D"
          />
          <div
            className="h-8 w-px"
            style={{ backgroundColor: "var(--color-ghost)" }}
          />
          <ResultStat
            label="Violazioni"
            value={totalViolations.toString()}
            tone={hasViolations ? "warning" : "success"}
          />
          <div
            className="h-8 w-px"
            style={{ backgroundColor: "var(--color-ghost)" }}
          />
          <ResultStat
            label="Treni utilizzati"
            value={allTrainIds.size.toString()}
            sub="unici (no duplicati tra varianti)"
          />
          <div
            className="h-8 w-px"
            style={{ backgroundColor: "var(--color-ghost)" }}
          />
          <ResultStat
            label="Ore pesate"
            value={
              result.weekly_stats.weighted_hours_per_day != null
                ? `${result.weekly_stats.weighted_hours_per_day.toFixed(1)}h/gg`
                : "—"
            }
            sub="media settimanale"
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

      {/* ── Giornate materiale con 3 varianti LMXGV/S/D impilate ── */}
      {result && days.length > 0 && (
        <div className="space-y-5">
          {days.map((day) => (
            <DayBlock key={`day-${day.day_number}`} day={day} />
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

function variantLabel(vt: string): string {
  if (vt === "LMXGV") return "Feriale (Lun–Ven)"
  if (vt === "S") return "Sabato"
  if (vt === "D") return "Domenica"
  return vt
}

function variantColors(vt: string): { bg: string; fg: string } {
  if (vt === "LMXGV") return { bg: "rgba(37, 99, 235, 0.12)", fg: "#1D4ED8" }
  if (vt === "S") return { bg: "rgba(234, 88, 12, 0.14)", fg: "#C2410C" }
  if (vt === "D") return { bg: "rgba(220, 38, 38, 0.14)", fg: "#B91C1C" }
  return { bg: "var(--color-surface-container-high)", fg: "var(--color-on-surface-muted)" }
}

function DayBlock({ day }: { day: BuildAutoWeeklyDay }) {
  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{
        backgroundColor: "var(--color-surface-container-lowest)",
        boxShadow: "var(--shadow-md)",
      }}
    >
      {/* Giornata header (un'unica volta per le 3 varianti) */}
      <div
        className="px-4 py-3 flex items-center gap-4 border-b"
        style={{
          backgroundColor: "var(--color-surface-container-low)",
          borderColor: "var(--color-ghost)",
        }}
      >
        <div
          className="font-bold"
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "17px",
            color: "var(--color-on-surface-strong)",
          }}
        >
          Giornata {day.day_number}
        </div>
        <span
          className="text-[10.5px]"
          style={{ color: "var(--color-on-surface-muted)" }}
        >
          3 varianti del turno materiale
        </span>
      </div>

      <div>
        {day.variants.map((v, i) => (
          <VariantRow
            key={`day${day.day_number}-${v.variant_type}-${i}`}
            dayNum={day.day_number}
            variant={v}
          />
        ))}
      </div>
    </div>
  )
}

function VariantRow({ dayNum, variant }: { dayNum: number; variant: AutoWeeklyVariant }) {
  const vt = variant.variant_type
  const colors = variantColors(vt)
  const label = variantLabel(vt)

  // S.COMP: disponibilita', nessun servizio
  if (variant.is_scomp) {
    return (
      <div
        className="px-4 py-3 flex items-center gap-3 border-b last:border-b-0"
        style={{ borderColor: "var(--color-ghost)" }}
      >
        <span
          className="text-[10px] px-1.5 py-0.5 rounded font-bold"
          style={{
            backgroundColor: colors.bg,
            color: colors.fg,
            fontFamily: "var(--font-mono)",
            minWidth: "50px",
            textAlign: "center",
          }}
        >
          {vt}
        </span>
        <span
          className="text-[11.5px]"
          style={{ color: "var(--color-on-surface-muted)" }}
        >
          {label}
        </span>
        <span
          className="text-[10px] px-1.5 py-0.5 rounded font-semibold"
          style={{
            backgroundColor: "var(--color-surface-container-high)",
            color: "var(--color-on-surface-muted)",
            fontFamily: "var(--font-mono)",
            letterSpacing: "0.05em",
          }}
        >
          S.COMP
        </span>
        <span
          className="text-[12px]"
          style={{ color: "var(--color-on-surface-muted)" }}
        >
          Disponibilita' ({Math.round((variant.scomp_duration_min ?? 0) / 60)}h) —
          il materiale non prevede servizio per questo giorno
        </span>
      </div>
    )
  }

  const s = variant.summary
  if (!s || !s.segments || s.segments.length === 0) {
    return (
      <div
        className="px-4 py-3 flex items-center gap-3 border-b last:border-b-0"
        style={{ borderColor: "var(--color-ghost)" }}
      >
        <span
          className="text-[10px] px-1.5 py-0.5 rounded font-bold"
          style={{
            backgroundColor: colors.bg,
            color: colors.fg,
            fontFamily: "var(--font-mono)",
            minWidth: "50px",
            textAlign: "center",
          }}
        >
          {vt}
        </span>
        <span
          className="text-[11.5px]"
          style={{ color: "var(--color-on-surface-muted)" }}
        >
          {label}
        </span>
        <span
          className="text-[12px]"
          style={{ color: "var(--color-on-surface-muted)" }}
        >
          Nessun seed trovato nel materiale per questo giorno
        </span>
      </div>
    )
  }

  const segments = s.segments
  const hasErrors = s.violations.some((v) => v.severity === "error")
  const hasWarnings = s.violations.some((v) => v.severity === "warning")
  const nViolNonInfo = s.violations.filter((v) => v.severity !== "info").length
  const firstFrom = segments[0]?.from_station ?? "—"
  const lastTo = segments[segments.length - 1]?.to_station ?? "—"
  const condottaHours = (s.condotta_min / 60).toFixed(1)
  const prestazioneHours = (s.prestazione_min / 60).toFixed(1)

  return (
    <div
      className="border-b last:border-b-0"
      style={{ borderColor: "var(--color-ghost)" }}
    >
      {/* Variant header */}
      <div
        className="px-4 py-2.5 flex items-center gap-3 flex-wrap"
        style={{ backgroundColor: "var(--color-surface-container-lowest)" }}
      >
        <span
          className="text-[10px] px-1.5 py-0.5 rounded font-bold"
          style={{
            backgroundColor: colors.bg,
            color: colors.fg,
            fontFamily: "var(--font-mono)",
            minWidth: "50px",
            textAlign: "center",
          }}
        >
          {vt}
        </span>
        <span
          className="text-[11.5px]"
          style={{ color: "var(--color-on-surface-muted)" }}
        >
          {label}
        </span>
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
          className="text-[11.5px] truncate max-w-[260px]"
          style={{ color: "var(--color-on-surface-muted)" }}
        >
          {firstFrom} → {lastTo}
        </div>
        {s.is_fr && (
          <span
            className="text-[10px] px-1.5 py-0.5 rounded font-semibold"
            style={{ backgroundColor: "rgba(124, 58, 237, 0.12)", color: "#6D28D9" }}
          >
            FR
          </span>
        )}
        {s.night_minutes > 0 && (
          <Moon size={12} style={{ color: "var(--color-on-surface-muted)" }} />
        )}
        <div className="ml-auto flex items-center gap-3">
          <InlineMetric label="Cct" value={`${condottaHours}h`} />
          <InlineMetric label="Prest" value={`${prestazioneHours}h`} />
          <InlineMetric label="Refez" value={`${s.meal_min}'`} />
          {nViolNonInfo > 0 ? (
            <span
              className="inline-flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-full"
              style={{
                backgroundColor: hasErrors
                  ? "var(--color-destructive-container)"
                  : "var(--color-warning-container)",
                color: hasErrors ? "var(--color-destructive)" : "var(--color-warning)",
              }}
            >
              <AlertTriangle size={11} />
              {nViolNonInfo}
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

      {/* Gantt */}
      <div className="px-4 pt-2">
        <AutoBuilderGantt
          segments={segments}
          presentationTime={s.presentation_time}
          endTime={s.end_time}
          mealStart={s.meal_start}
          mealEnd={s.meal_end}
        />
      </div>

      {/* Segments list */}
      <div className="px-4 py-2.5 space-y-1">
        {segments.map((seg, i) => (
          <div
            key={`${dayNum}-${vt}-${i}`}
            className="grid grid-cols-[24px_auto_1fr_auto] items-center gap-3 px-2 py-1 rounded-md transition-colors hover:bg-[var(--color-surface-container-low)]"
            style={{ fontFamily: "var(--font-mono)", fontSize: "11.5px" }}
          >
            <Train
              size={14}
              style={{
                color: seg.is_deadhead
                  ? "var(--color-on-surface-muted)"
                  : "var(--color-brand)",
              }}
            />
            <span
              className="font-bold"
              style={{
                color: seg.is_deadhead
                  ? "var(--color-on-surface-muted)"
                  : "var(--color-brand)",
              }}
            >
              {seg.train_id}
              {seg.is_deadhead && " (v)"}
            </span>
            <div
              className="flex items-center gap-1 truncate"
              style={{ color: "var(--color-on-surface-muted)" }}
            >
              <span className="truncate">{seg.from_station || "?"}</span>
              <span>→</span>
              <span className="truncate">{seg.to_station || "?"}</span>
            </div>
            <div style={{ color: "var(--color-on-surface-strong)", fontWeight: 600 }}>
              {seg.dep_time} → {seg.arr_time}
            </div>
          </div>
        ))}
      </div>

      {/* Violations */}
      {s.violations.length > 0 && (
        <div
          className="px-4 py-2"
          style={{
            backgroundColor: hasErrors
              ? "var(--color-destructive-container)"
              : hasWarnings
              ? "var(--color-warning-container)"
              : "var(--color-surface-container-low)",
          }}
        >
          <div className="space-y-1 text-[12px]">
            {s.violations.map((v, i) => (
              <div key={i} className="flex items-start gap-2">
                <span
                  className="shrink-0 text-[9.5px] font-bold uppercase mt-0.5 px-1 rounded"
                  style={{
                    backgroundColor:
                      v.severity === "error"
                        ? "rgba(220, 38, 38, 0.15)"
                        : v.severity === "warning"
                        ? "rgba(234, 88, 12, 0.15)"
                        : "rgba(59, 130, 246, 0.15)",
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
