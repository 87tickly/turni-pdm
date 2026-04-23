/**
 * Gantt v3 · preview page — /gantt-preview
 *
 * 4 varianti dimostrative che coprono i casi principali:
 *   A · Giornata singola 4 treni (uscita auto-builder, niente refez)
 *   B · 3 varianti impilate LMXGV · S · D (PDF pag 388) con vetture sospette
 *       e warn su riga D
 *   C · S.COMP giornata intera (disponibilita')
 *   D · Dormita FR Alessandria + ripartenza multi-variante giorno dopo
 *
 * Dati hard-coded presi 1:1 dal mockup Claude Design
 * (`screen-gantt-v3.html`). Pagina dimostrativa, NON cablata al
 * backend: mostra al dispatcher come appariranno i turni reali una
 * volta che AutoBuilderGantt e PdcGanttV2 saranno riscritti.
 */
import { useState } from "react"
import { GanttSheet } from "@/components/gantt/GanttSheet"
import type { GanttRow, GanttSegment, GanttLabelsMode, GanttMinutesMode } from "@/components/gantt/types"


// ─────────────────────────────────────────────────────────────
// Dati demo (copiati dal mockup)
// ─────────────────────────────────────────────────────────────

const DEFAULT_RANGE: [number, number] = [3, 27]   // 03:00 → 03:00 (+1d)

const varA = {
  dayHead: { num: 12, pres: "06:45", end: "14:12", variant: "LMXGV" },
  range: DEFAULT_RANGE,
  metrics: { lav: "7h27", cct: "03h12", km: 168, not: "no" as const, rip: "14h48" },
  rows: [
    {
      label: "LMXGV",
      segments: [
        s("cond", "ML", "MRT", "10208", "06:52", "07:26"),
        { ...s("cond", "MRT", "ML", "10221", "07:36", "08:09"), preheat: true },
        s("dh", "ML", "VO", "(11555)", "09:10", "09:55"),
        s("cond", "VO", "AL", "2566", "10:18", "10:52"),
        s("dh", "AL", "ML", "(2598)", "12:40", "13:55"),
      ],
    },
  ] as GanttRow[],
}

const varB = {
  dayHead: { num: 8, pres: "07:18", end: "14:49", variant: "LMXGV" },
  range: DEFAULT_RANGE,
  metrics: { lav: "7h31", cct: "03h03", km: 153, not: "no" as const, rip: "14h55" },
  rows: [
    {
      label: "LMXGV",
      meta: "8  [07:18]  [14:49]",
      segments: [
        s("cond", "ML", "MRT", "10208", "07:34", "08:08"),
        { ...s("cond", "MRT", "ML", "10221", "08:15", "08:42"), preheat: true },
        s("cond", "ML", "VO", "10042", "10:10", "11:05"),
        s("refez", "VO", "VO", "REFEZ VOGH", "11:15", "11:55"),
        s("cond", "VO", "AL", "12588", "12:12", "12:56"),
        s("dh", "AL", "ML", "(2588 AL)", "13:30", "14:45"),
      ],
    },
    {
      label: "S",
      meta: "8  [07:18]  [14:49]",
      metrics_override: { lav: "7h31", cct: "03h03", km: 153, rip: "14h34" },
      segments: [
        s("cond", "ML", "MRT", "10226", "07:34", "08:08"),
        { ...s("cond", "MRT", "ML", "10231", "08:15", "08:42"), preheat: true },
        s("cond", "ML", "VO", "10042", "10:10", "11:05"),
        s("refez", "VO", "VO", "REFEZ VOGH", "11:15", "11:55"),
        s("cond", "VO", "AL", "12588", "12:12", "12:56"),
        s("dh", "AL", "ML", "(2588 AL)", "13:30", "14:45"),
      ],
    },
    {
      label: "D",
      meta: "8  [07:28]  [15:18]",
      warn: true,
      metrics_override: { lav: "7h50", cct: "02h02", km: 102, rip: "14h31" },
      segments: [
        s("cond", "ML", "MRT", "10068", "07:52", "08:26"),
        { ...s("cond", "MRT", "ML", "10301", "08:35", "09:02"), preheat: true },
        s("cond", "ML", "VO", "10042", "10:10", "11:05"),
        {
          ...s("dh", "VO", "MRT", "(10047)", "11:12", "11:48"),
          suspect_reason: "inversione direzione entro 4 min",
        },
        {
          ...s("dh", "MRT", "VO", "(11367)", "11:52", "12:25"),
          suspect_reason: "inversione direzione entro 4 min",
        },
        s("cond", "VO", "AL", "12588", "12:40", "13:24"),
        s("dh", "AL", "ML", "(2588 AL)", "14:00", "15:15"),
      ],
    },
  ] as GanttRow[],
}

const varC = {
  dayHead: { num: 5, pres: "06:00", end: "14:00", variant: "SD" },
  range: DEFAULT_RANGE,
  metrics: { lav: "8h00", cct: "00h00", km: 0, not: "no" as const, rip: "16h00" },
  rows: [
    {
      label: "SD",
      segments: [s("scomp", "ML", "ML", "S.COMP MILANO C.LE", "06:00", "14:00")],
    },
  ] as GanttRow[],
}

const varD = {
  dayHead: { num: 6, pres: "15:44", end: "21:21", variant: "LMXGV" },
  range: [15, 28] as [number, number],
  metrics: { lav: "5h37", cct: "00h00", km: 0, not: "no" as const, rip: "18h23" },
  rows: [
    {
      label: "G6 · LMXGV",
      meta: "6  [15:44]  [21:21] · AL",
      metrics_override: { lav: "5h37", cct: "00h00", km: 0, rip: "18h23" },
      segments: [
        s("cond", "ML", "AL", "10062", "16:18", "17:15"),
        s("refez", "AL", "AL", "REFEZ AL", "18:30", "19:10"),
        { ...s("cond", "AL", "AL", "10067", "19:40", "20:45"), preheat: true },
        s("sleep", "AL", "AL", "DORMITA · ALESSANDRIA", "21:21", "03:44"),
      ],
    },
    {
      label: "G7 · LMXGV",
      meta: "7  [15:44]  [23:56]",
      metrics_override: { lav: "8h12", cct: "03h12", km: 153, rip: "07h22" },
      segments: [
        { ...s("cond", "AL", "ML", "28385", "16:30", "17:04"), cvp: true },
        { ...s("cond", "ML", "MRT", "10067", "17:15", "17:49"), preheat: true },
        s("refez", "MRT", "MRT", "REFEZ MORT", "18:00", "18:30"),
        s("cond", "MRT", "ML", "10078", "19:15", "19:49"),
        s("cond", "ML", "MRT", "10083", "23:20", "23:56"),
      ],
    },
    {
      label: "G7 · S",
      meta: "7  [18:42]  [23:56]",
      metrics_override: { lav: "5h14", cct: "02h11", km: 102, rip: "07h32" },
      segments: [
        s("dh", "AL", "MRT", "(11278)", "19:22", "20:15"),
        s("cond", "MRT", "ML", "10078", "20:40", "21:14"),
        s("cond", "ML", "MRT", "10083", "23:20", "23:56"),
      ],
    },
    {
      label: "G7 · D",
      meta: "7  [17:36]  [23:56]",
      metrics_override: { lav: "6h20", cct: "02h11", km: 102, rip: "07h22" },
      segments: [
        s("cond", "AL", "VAL", "10966", "18:02", "18:34"),
        s("dh", "VAL", "MRT", "(11278)", "18:56", "19:30"),
        s("refez", "MRT", "MRT", "REFEZ MORT", "19:40", "20:10"),
        { ...s("cond", "MRT", "ML", "10066", "20:22", "20:56"), cvp: true },
        s("cond", "ML", "MRT", "10078", "21:40", "22:14"),
        s("cond", "MRT", "ML", "10083", "23:20", "23:56"),
      ],
    },
  ] as GanttRow[],
}

function s(
  kind: GanttSegment["kind"],
  from: string, to: string, train: string, dep: string, arr: string,
): GanttSegment {
  return {
    kind,
    train_id: train,
    from_station: from,
    to_station: to,
    dep_time: dep,
    arr_time: arr,
  }
}


// ─────────────────────────────────────────────────────────────
// Tweaks panel
// ─────────────────────────────────────────────────────────────

type SegSelection = { variant: string; seg: GanttSegment } | null

export function GanttPreviewPage() {
  const [barHeight, setBarHeight] = useState(20)
  const [labels, setLabels] = useState<GanttLabelsMode>("auto")
  const [minutesMode, setMinutesMode] = useState<GanttMinutesMode>("hhmm")
  const [showSuspect, setShowSuspect] = useState(true)
  const [grid30, setGrid30] = useState(false)
  const [selection, setSelection] = useState<SegSelection>(null)

  const handleClick = (variant: string) => (seg: GanttSegment) => {
    setSelection({ variant, seg })
  }

  return (
    <div
      className="min-h-screen pl-56"
      style={{ backgroundColor: "var(--color-surface)" }}
    >
      {/* Header "foglio turno" stile PDF */}
      <header
        className="flex items-center justify-between px-5 py-3"
        style={{
          backgroundColor: "var(--color-surface-container-lowest)",
          boxShadow: "inset 0 -1px 0 var(--color-ghost)",
        }}
      >
        <div className="flex items-center gap-3">
          <span
            className="font-bold text-[16px] tracking-tight"
            style={{
              color: "var(--color-on-surface-strong)",
              fontFamily: "var(--font-display, 'Exo 2', Inter)",
            }}
          >
            ARTURO·
          </span>
          <span className="w-px h-[18px]"
            style={{ backgroundColor: "var(--color-ghost)" }} />
          <span className="text-[11.5px]" style={{ color: "var(--color-on-surface-muted)" }}>
            Foglio turno · Gantt v3 preview
          </span>
        </div>
        <div className="flex items-center gap-6 text-[11.5px]"
          style={{ color: "var(--color-on-surface-strong)" }}>
          <MetaKV k="IMPIANTO" v="MILANO C.LE" />
          <MetaKV k="TURNO" v="[AROR_C] 65046" />
          <MetaKV k="PROFILO" v="Condotta" />
          <MetaKV k="DAL" v="23/02/26" kExtra="AL" vExtra="12/12/26" />
        </div>
      </header>

      <div className="px-8 pt-6 pb-24 max-w-[1520px] mx-auto">
        {/* Intro + legenda */}
        <div className="grid grid-cols-[1fr_auto] gap-8 items-start mb-7">
          <div>
            <div
              className="text-[9.5px] font-bold uppercase tracking-[0.12em]"
              style={{ color: "var(--color-brand)" }}
            >
              Redesign · Gantt v3
            </div>
            <h1
              className="text-[26px] font-semibold leading-tight mt-1.5 mb-2"
              style={{
                color: "var(--color-on-surface-strong)",
                fontFamily: "var(--font-display, 'Exo 2', Inter)",
                letterSpacing: "-0.015em",
              }}
            >
              Falsa riga del PDF Trenord, interattività del web.
            </h1>
            <p
              className="text-[13px] leading-[1.55] max-w-[760px]"
              style={{ color: "var(--color-on-surface-muted)" }}
            >
              Asse sempre <strong style={{ color: "var(--color-on-surface-strong)", fontWeight: 600 }}>
                24 ore continue
              </strong>{" "}(3 → 3 del giorno dopo, come il PDF). Barre sottili
              20 px · label verticali sotto 60 px · nessun nero puro, solo
              ink <code style={codeStyle}>#0A1322</code> dal DS. Segmenti
              cliccabili: hover → tooltip, click → drawer.
            </p>
          </div>
          <Legend />
        </div>

        {/* Tweaks */}
        <Tweaks
          barHeight={barHeight} setBarHeight={setBarHeight}
          labels={labels} setLabels={setLabels}
          minutesMode={minutesMode} setMinutesMode={setMinutesMode}
          showSuspect={showSuspect} setShowSuspect={setShowSuspect}
          grid30={grid30} setGrid30={setGrid30}
        />

        {/* Variante A */}
        <VariantSection
          tag="Variante A"
          title="Giornata singola · 4 treni"
          meta="uscita tipica dall'auto-builder, nessuna refezione"
          chips={[
            { k: "Cct", v: "03h12" },
            { k: "Prest", v: "07h05" },
            { k: "OK", v: "nessuna violazione", variant: "ok" },
          ]}
        >
          <GanttSheet
            rows={varA.rows} dayHead={varA.dayHead} metrics={varA.metrics}
            range={varA.range} barHeight={barHeight} labels={labels}
            minutes={minutesMode} suspect={showSuspect} grid30={grid30}
            onSegmentClick={handleClick("A")}
          />
        </VariantSection>

        {/* Variante B */}
        <VariantSection
          tag="Variante B"
          title="Calendario impilato · LMXGV · S · D"
          meta="asse orario unico 24h, tre strisce per le tre varianti della stessa giornata"
          chips={[
            { k: "", v: "8 · [07:18] → [14:49]", variant: "soft" },
            { k: "WARN", v: "DATA_MISMATCH · D", variant: "warn" },
          ]}
        >
          <GanttSheet
            rows={varB.rows} dayHead={varB.dayHead} metrics={varB.metrics}
            range={varB.range} barHeight={barHeight} labels={labels}
            minutes={minutesMode} suspect={showSuspect} grid30={grid30}
            onSegmentClick={handleClick("B")}
          />
        </VariantSection>

        {/* Variante C */}
        <VariantSection
          tag="Variante C"
          title="S.COMP · giornata in disponibilità"
          meta="nessun treno assegnato, barra S.COMP continua con etichetta centrale"
          chips={[
            { k: "Cct", v: "00h00" },
            { k: "Disp", v: "08h00" },
          ]}
        >
          <GanttSheet
            rows={varC.rows} dayHead={varC.dayHead} metrics={varC.metrics}
            range={varC.range} barHeight={barHeight} labels={labels}
            minutes={minutesMode} suspect={showSuspect} grid30={grid30}
            onSegmentClick={handleClick("C")}
          />
        </VariantSection>

        {/* Variante D */}
        <VariantSection
          tag="Variante D · FR"
          tagVariant="fr"
          title="Dormita fuori residenza · Alessandria"
          meta="giornata 6 arriva AL · dormita · giornata 7 riparte AL in 3 varianti (LMXGV · S · D)"
          chips={[
            { k: "", v: "6 · [15:44] → [21:21]", variant: "soft" },
            { k: "", v: "7 · [15:44] → [23:56]", variant: "soft" },
            { k: "FR", v: "notturno", variant: "fr" },
          ]}
        >
          <GanttSheet
            rows={varD.rows} dayHead={varD.dayHead} metrics={varD.metrics}
            range={varD.range} barHeight={barHeight} labels={labels}
            minutes={minutesMode} suspect={showSuspect} grid30={grid30}
            onSegmentClick={handleClick("D")}
          />
        </VariantSection>

        {/* Callout vetture sospette */}
        <section
          className="mt-8 p-5 rounded-lg"
          style={{
            backgroundColor: "rgb(220 38 38 / 0.05)",
            boxShadow: "inset 0 0 0 1px rgb(220 38 38 / 0.18)",
          }}
        >
          <div className="flex items-center gap-2 mb-2">
            <span
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: "var(--gantt-suspect, #DC2626)" }}
            />
            <h4
              className="text-[15px] font-semibold"
              style={{ color: "var(--color-on-surface-strong)" }}
            >
              Vetture sospette · viaggio in cerchio
            </h4>
          </div>
          <p className="text-[12.5px] leading-[1.55]"
            style={{ color: "var(--color-on-surface-muted)" }}>
            Euristica dispatcher: due vetture (deadhead) consecutive che
            invertono direzione entro 30 minuti, senza un treno
            produttivo tra loro. Cf. bug commit{" "}
            <code style={codeStyle}>68a2b6a</code>{" "}
            (cycle_optimizer) — il backend ora le rileva e le rimuove dal
            turno, ma il campo{" "}
            <code style={codeStyle}>segment.suspect_reason</code> non e'
            ancora esposto. L'handoff propone di mostrarle
            <strong style={{ color: "var(--gantt-suspect, #DC2626)" }}>
              {" "}rosse punteggiate con ⚠
            </strong>{" "}per permettere al dispatcher di valutare prima di
            accettare la rimozione.
          </p>
        </section>

        {/* Selection feedback (placeholder drawer) */}
        {selection && (
          <div
            className="fixed bottom-4 right-4 p-3 rounded-lg text-[11.5px] max-w-[360px]"
            style={{
              backgroundColor: "var(--color-surface-container-lowest)",
              color: "var(--color-on-surface)",
              boxShadow: "var(--shadow-md, 0 4px 12px rgba(11,28,48,0.12))",
            }}
          >
            <div className="flex items-center justify-between gap-4 mb-1">
              <div className="flex items-center gap-2">
                <span
                  className="text-[9px] font-bold uppercase tracking-wider"
                  style={{ color: "var(--color-on-surface-quiet)" }}
                >
                  click placeholder · Variante {selection.variant}
                </span>
              </div>
              <button
                onClick={() => setSelection(null)}
                className="opacity-60 hover:opacity-100 text-[12px]"
              >
                ✕
              </button>
            </div>
            <div style={{ fontFamily: "var(--font-mono, monospace)" }}>
              {selection.seg.kind.toUpperCase()} · {selection.seg.train_id} ·{" "}
              {selection.seg.from_station} {selection.seg.dep_time} →{" "}
              {selection.seg.to_station} {selection.seg.arr_time}
            </div>
            {selection.seg.suspect_reason && (
              <div className="mt-1" style={{ color: "var(--gantt-suspect, #DC2626)" }}>
                ⚠ {selection.seg.suspect_reason}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}


// ─────────────────────────────────────────────────────────────
// UI helpers
// ─────────────────────────────────────────────────────────────

const codeStyle: React.CSSProperties = {
  fontFamily: "var(--font-mono, monospace)",
  fontSize: "11.5px",
  backgroundColor: "var(--color-surface-container)",
  padding: "1px 5px",
  borderRadius: 3,
  color: "var(--color-on-surface-strong)",
}

function MetaKV({ k, v, kExtra, vExtra }: {
  k: string; v: string; kExtra?: string; vExtra?: string
}) {
  return (
    <span>
      <em
        className="not-italic font-bold text-[9.5px] uppercase tracking-wider mr-1.5"
        style={{ color: "var(--color-on-surface-quiet)" }}
      >
        {k}
      </em>
      {v}
      {kExtra && (
        <em
          className="not-italic font-bold text-[9.5px] uppercase tracking-wider mx-2.5"
          style={{ color: "var(--color-on-surface-quiet)" }}
        >
          {kExtra}
        </em>
      )}
      {vExtra}
    </span>
  )
}

function Legend() {
  const items: { label: string; swatch: React.CSSProperties }[] = [
    { label: "Condotta", swatch: { backgroundColor: "var(--gantt-bar-cond)" } },
    {
      label: "Vettura",
      swatch: {
        backgroundColor: "var(--gantt-bar-dh-bg)",
        border: "1px dashed var(--gantt-bar-dh-line)",
      },
    },
    {
      label: "Vettura sospetta ⚠",
      swatch: {
        backgroundColor: "rgba(220, 38, 38, 0.06)",
        border: "1px dashed var(--gantt-suspect)",
      },
    },
    { label: "Refezione", swatch: { backgroundColor: "var(--gantt-refez)", height: 5 } },
    {
      label: "S.COMP",
      swatch: {
        background: "repeating-linear-gradient(90deg, var(--gantt-scomp) 0 2px, transparent 2px 5px)",
        opacity: 0.6,
      },
    },
    {
      label: "Dormita FR",
      swatch: {
        backgroundColor: "var(--gantt-sleep-bg)",
        border: "1px solid var(--gantt-sleep)",
      },
    },
    {
      label: "Preriscaldo ●",
      swatch: {
        backgroundColor: "var(--gantt-bar-cond)",
        position: "relative" as const,
      },
    },
  ]
  return (
    <div
      className="flex flex-col gap-1.5 p-3 rounded-md"
      style={{
        backgroundColor: "var(--color-surface-container-lowest)",
        boxShadow: "inset 0 0 0 1px var(--color-ghost)",
      }}
    >
      <span
        className="text-[9.5px] font-bold uppercase tracking-wider mb-0.5"
        style={{ color: "var(--color-on-surface-quiet)" }}
      >
        Legenda
      </span>
      {items.map((it, i) => (
        <div key={i} className="flex items-center gap-2 text-[11.5px]"
          style={{ color: "var(--color-on-surface)" }}>
          <span
            style={{ width: 20, height: 10, borderRadius: 2, display: "inline-block", ...it.swatch }}
          />
          <span>{it.label}</span>
        </div>
      ))}
    </div>
  )
}

function VariantSection({
  tag, tagVariant, title, meta, chips, children,
}: {
  tag: string
  tagVariant?: "default" | "fr"
  title: string
  meta: string
  chips: { k: string; v: string; variant?: "default" | "ok" | "warn" | "fr" | "soft" }[]
  children: React.ReactNode
}) {
  const tagBg = tagVariant === "fr"
    ? "rgb(124 58 237 / 0.10)"
    : "var(--color-surface-container)"
  const tagColor = tagVariant === "fr"
    ? "var(--gantt-fr, #7C3AED)"
    : "var(--color-on-surface-strong)"
  return (
    <section className="mt-8">
      <header className="flex items-center justify-between mb-3 flex-wrap gap-3">
        <div className="flex items-center gap-3 flex-wrap">
          <span
            className="text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded"
            style={{ backgroundColor: tagBg, color: tagColor }}
          >
            {tag}
          </span>
          <h3
            className="text-[17px] font-semibold"
            style={{
              color: "var(--color-on-surface-strong)",
              fontFamily: "var(--font-display, 'Exo 2', Inter)",
              letterSpacing: "-0.01em",
            }}
          >
            {title}
          </h3>
          <span className="text-[11.5px]"
            style={{ color: "var(--color-on-surface-quiet)" }}>
            {meta}
          </span>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {chips.map((c, i) => (
            <Chip key={i} {...c} />
          ))}
        </div>
      </header>
      <div
        className="rounded-lg overflow-x-auto p-4"
        style={{
          backgroundColor: "var(--color-surface-container-lowest)",
          boxShadow: "var(--shadow-sm, 0 1px 2px rgba(11,28,48,0.04))",
        }}
      >
        {children}
      </div>
    </section>
  )
}

function Chip({ k, v, variant = "default" }: {
  k: string; v: string; variant?: "default" | "ok" | "warn" | "fr" | "soft"
}) {
  const styles: Record<string, React.CSSProperties> = {
    default: {
      backgroundColor: "var(--color-surface-container)",
      color: "var(--color-on-surface-strong)",
    },
    soft: {
      backgroundColor: "var(--color-surface-container-low)",
      color: "var(--color-on-surface-muted)",
    },
    ok: { backgroundColor: "rgb(4 120 87 / 0.08)", color: "#047857" },
    warn: { backgroundColor: "rgb(180 83 9 / 0.08)", color: "#B45309" },
    fr: { backgroundColor: "rgb(124 58 237 / 0.10)", color: "var(--gantt-fr, #7C3AED)" },
  }
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-semibold"
      style={styles[variant]}
    >
      {k && (
        <em
          className="not-italic text-[9.5px] uppercase tracking-wider"
          style={{ opacity: 0.65 }}
        >
          {k}
        </em>
      )}
      <span style={{ fontFamily: v.includes(":") ? "var(--font-mono, monospace)" : undefined }}>
        {v}
      </span>
    </span>
  )
}

function Tweaks({
  barHeight, setBarHeight,
  labels, setLabels,
  minutesMode, setMinutesMode,
  showSuspect, setShowSuspect,
  grid30, setGrid30,
}: {
  barHeight: number
  setBarHeight: (n: number) => void
  labels: GanttLabelsMode
  setLabels: (v: GanttLabelsMode) => void
  minutesMode: GanttMinutesMode
  setMinutesMode: (v: GanttMinutesMode) => void
  showSuspect: boolean
  setShowSuspect: (v: boolean) => void
  grid30: boolean
  setGrid30: (v: boolean) => void
}) {
  return (
    <div
      className="flex items-center gap-4 flex-wrap p-3 rounded-md mb-4"
      style={{
        backgroundColor: "var(--color-surface-container-lowest)",
        boxShadow: "inset 0 0 0 1px var(--color-ghost)",
      }}
    >
      <SegControl
        label="Label"
        value={labels}
        options={[["auto", "Auto"], ["vertical", "Verticale"], ["horizontal", "Orizzontale"]]}
        onChange={(v) => setLabels(v as GanttLabelsMode)}
      />
      <SegControl
        label="Minuti"
        value={minutesMode}
        options={[["hhmm", "HH:MM"], ["duration", "Durata"], ["off", "Off"]]}
        onChange={(v) => setMinutesMode(v as GanttMinutesMode)}
      />
      <label className="flex items-center gap-2 text-[11.5px]"
        style={{ color: "var(--color-on-surface-muted)" }}>
        <span>Altezza barra</span>
        <input
          type="range" min={16} max={28} step={2}
          value={barHeight} onChange={(e) => setBarHeight(+e.target.value)}
        />
        <span className="font-mono text-[10.5px]"
          style={{ color: "var(--color-on-surface-strong)" }}>
          {barHeight}px
        </span>
      </label>
      <label className="inline-flex items-center gap-1.5 text-[11.5px] cursor-pointer">
        <input type="checkbox" checked={showSuspect}
          onChange={(e) => setShowSuspect(e.target.checked)} />
        <span>Evidenzia sospette</span>
      </label>
      <label className="inline-flex items-center gap-1.5 text-[11.5px] cursor-pointer">
        <input type="checkbox" checked={grid30}
          onChange={(e) => setGrid30(e.target.checked)} />
        <span>Griglia 30 min</span>
      </label>
    </div>
  )
}

function SegControl({ label, value, options, onChange }: {
  label: string
  value: string
  options: [string, string][]
  onChange: (v: string) => void
}) {
  return (
    <div className="inline-flex items-center gap-2">
      <span className="text-[11.5px]"
        style={{ color: "var(--color-on-surface-muted)" }}>
        {label}
      </span>
      <div
        className="inline-flex rounded-md overflow-hidden"
        style={{ backgroundColor: "var(--color-surface-container)" }}
      >
        {options.map(([v, lab]) => (
          <button
            key={v}
            onClick={() => onChange(v)}
            className="px-2 py-1 text-[11px] font-medium"
            style={{
              backgroundColor: value === v
                ? "var(--color-surface-container-highest)"
                : "transparent",
              color: value === v
                ? "var(--color-on-surface-strong)"
                : "var(--color-on-surface-muted)",
            }}
          >
            {lab}
          </button>
        ))}
      </div>
    </div>
  )
}
