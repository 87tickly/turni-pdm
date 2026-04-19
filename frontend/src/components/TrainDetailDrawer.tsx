/**
 * TrainDetailDrawer — Drawer laterale destro con cross-link PdC↔Materiale.
 *
 * Sostituisce `BlockDetailModal` (modal centrato) con il pattern drawer
 * raccomandato dal design system "Kinetic Conductor" (handoff Claude
 * Design → vedi docs/HANDOFF-claude-design.md §01 e §02).
 *
 * Signature IDENTICA a BlockDetailModal per drop-in replacement:
 *   <TrainDetailDrawer block={...} index={...} mode="detail"|"warn" onClose={...} />
 *
 * Comportamento UX:
 * - Slide-in da destra 220ms, overlay backdrop scuro 35% con blur 8px
 * - Larghezza 440px desktop, full-width < 768px
 * - Esc o click fuori → chiude
 * - Single click su un chain pill del giro materiale → naviga al treno
 *   cliccato (ricarica il drawer con quel train_id come focus)
 *
 * Sezioni (in ordine):
 * 1. Header        — numero treno mono grande, chip stato, close X
 * 2. Trip          — origine → destinazione + orari start/end
 * 3. Giro Materiale — pos X/Y, prev/curr/next cards, chain pills cliccabili
 * 4. PdC Carriers  — lista turni PdC con handoff indicator verde quando
 *                    prev.arr_time === next.dep_time (handoff perfetto)
 * 5. ARTURO Live   — solo se il triple-check trova dati real-time
 * 6. Footer        — Apri ARTURO Live, Chiudi
 *
 * Fonte dati: identica a BlockDetailModal (trainCheck + trainCrossRef
 * in parallelo). Zero nuove chiamate.
 */

import { useEffect, useState, useCallback } from "react"
import {
  X, Loader2, AlertTriangle, CheckCircle2, Link2, Train,
  ExternalLink, ArrowLeft, ArrowRight,
} from "lucide-react"
import {
  trainCheck, trainCrossRef,
  type TrainCheckResult, type TrainCrossRef, type PdcBlock,
} from "@/lib/api"
import { cn } from "@/lib/utils"

interface Props {
  block: PdcBlock
  index: number
  mode: "detail" | "warn"
  onClose: () => void
}

export function TrainDetailDrawer({ block, mode, onClose }: Props) {
  // Stato locale: il block corrente può cambiare se l'utente naviga via
  // chain pills. `focusedTrainId` override il block.train_id originale.
  const [focusedTrainId, setFocusedTrainId] = useState<string>(
    block.train_id || ""
  )
  const [check, setCheck] = useState<TrainCheckResult | null>(null)
  const [crossRef, setCrossRef] = useState<TrainCrossRef | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  // Animazione mount — parte chiuso, dopo 10ms diventa open per triggerare
  // la transition CSS.
  const [isOpen, setIsOpen] = useState(false)
  useEffect(() => {
    const t = setTimeout(() => setIsOpen(true), 10)
    return () => clearTimeout(t)
  }, [])

  // Reset focus quando il block-esterno cambia (es. utente clicca un altro
  // blocco mentre il drawer è già aperto).
  useEffect(() => {
    setFocusedTrainId(block.train_id || "")
  }, [block.train_id])

  // Carica dati per il focusedTrainId (cambia al click su chain pill).
  useEffect(() => {
    if (block.block_type !== "train" || !focusedTrainId) return
    setLoading(true)
    setError("")
    setCheck(null)
    setCrossRef(null)
    trainCrossRef(focusedTrainId)
      .then(setCrossRef)
      .catch(() => {}) // best-effort
    trainCheck(focusedTrainId)
      .then(setCheck)
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Errore triple-check")
      )
      .finally(() => setLoading(false))
  }, [block.block_type, focusedTrainId])

  // Chiusura animata: imposta isOpen=false, dopo 220ms (match CSS) chiama
  // onClose del parent.
  const handleClose = useCallback(() => {
    setIsOpen(false)
    setTimeout(onClose, 220)
  }, [onClose])

  // Esc chiude
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") handleClose()
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [handleClose])

  // Discrepanza orari per modalità warn
  const arturoDiff = computeArturoDiff(block, check)

  // Quando focusedTrainId !== block.train_id, stiamo "navigando" nella chain
  const isNavigating =
    focusedTrainId !== "" && focusedTrainId !== (block.train_id || "")

  return (
    <>
      {/* Overlay backdrop */}
      <div
        className={cn(
          "fixed inset-0 z-[900] bg-slate-900/35 backdrop-blur-sm transition-opacity duration-200",
          isOpen ? "opacity-100" : "opacity-0 pointer-events-none"
        )}
        onClick={handleClose}
        aria-hidden="true"
      />

      {/* Drawer */}
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Dettaglio treno"
        className={cn(
          "fixed top-0 right-0 z-[1000] h-screen w-full md:w-[440px]",
          "bg-[var(--color-surface-container-lowest)]",
          "shadow-[var(--shadow-lg)]",
          "flex flex-col overflow-hidden",
          "transition-transform duration-200 ease-out",
          isOpen ? "translate-x-0" : "translate-x-full"
        )}
      >
        {/* ── 1. Header ── */}
        <div
          className={cn(
            "flex items-start gap-3 px-5 py-4",
            "bg-[var(--color-surface-container-low)]"
          )}
        >
          <div
            className={cn(
              "h-9 w-9 rounded-md flex items-center justify-center shrink-0",
              mode === "warn"
                ? "bg-amber-100 text-amber-700"
                : "bg-blue-100 text-blue-700"
            )}
          >
            {mode === "warn" ? <AlertTriangle size={16} /> : <Train size={16} />}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-on-surface-muted)] mb-0.5">
              Dettaglio treno
            </div>
            <h3 className="font-semibold text-[15px] flex items-center gap-2">
              <span className="font-mono font-bold">
                {focusedTrainId ? `Treno ${focusedTrainId}` : blockHeader(block)}
              </span>
              {isNavigating && (
                <button
                  onClick={() => setFocusedTrainId(block.train_id || "")}
                  className="text-[10px] px-2 py-0.5 rounded bg-[var(--color-surface-container)] hover:bg-[var(--color-surface-container-high)] text-[var(--color-on-surface-muted)] font-normal"
                  title="Torna al treno del blocco selezionato"
                >
                  ← torna a {block.train_id}
                </button>
              )}
            </h3>
            <p className="text-[11px] text-[var(--color-on-surface-muted)] mt-0.5">
              {mode === "warn"
                ? "Verifica discrepanze con ARTURO Live e giro materiale"
                : "Continuazione giro materiale · turni PdC · real-time"}
            </p>
          </div>
          <button
            onClick={handleClose}
            className="p-1.5 rounded hover:bg-[var(--color-surface-container)] text-[var(--color-on-surface-muted)]"
            title="Chiudi (Esc)"
          >
            <X size={16} />
          </button>
        </div>

        {/* ── Body scrollable ── */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {/* ── 2. Origine/Destinazione card (stile Stitch) ── */}
          {block.block_type === "train" && !isNavigating && (
            <div
              className="rounded-md p-4"
              style={{
                backgroundColor: "var(--color-surface-container-low)",
                boxShadow: "inset 0 0 0 1px var(--color-ghost)",
              }}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div
                    className="text-[10px] font-bold uppercase mb-0.5"
                    style={{
                      color: "var(--color-on-surface-muted)",
                      letterSpacing: "0.1em",
                    }}
                  >
                    Origine
                  </div>
                  <div
                    className="font-bold truncate"
                    style={{
                      fontSize: "13px",
                      color: "var(--color-on-surface-strong)",
                    }}
                  >
                    {block.from_station || "—"}
                  </div>
                  <div
                    className="text-[11px] mt-0.5"
                    style={{
                      fontFamily: "var(--font-mono)",
                      color: "var(--color-on-surface-muted)",
                    }}
                  >
                    {block.start_time || "—"}
                  </div>
                </div>
                <ArrowRight
                  size={18}
                  strokeWidth={2}
                  style={{ color: "var(--color-brand)" }}
                  className="shrink-0"
                />
                <div className="min-w-0 text-right">
                  <div
                    className="text-[10px] font-bold uppercase mb-0.5"
                    style={{
                      color: "var(--color-on-surface-muted)",
                      letterSpacing: "0.1em",
                    }}
                  >
                    Destinazione
                  </div>
                  <div
                    className="font-bold truncate"
                    style={{
                      fontSize: "13px",
                      color: "var(--color-on-surface-strong)",
                    }}
                  >
                    {block.to_station || "—"}
                  </div>
                  <div
                    className="text-[11px] mt-0.5"
                    style={{
                      fontFamily: "var(--font-mono)",
                      color: "var(--color-on-surface-muted)",
                    }}
                  >
                    {block.end_time || "—"}
                  </div>
                </div>
              </div>
              {/* Chip info aggiuntive */}
              {(block.vettura_id ||
                block.accessori_maggiorati === 1 ||
                block.minuti_accessori) && (
                <div className="flex flex-wrap gap-1.5 mt-3 pt-3" style={{ borderTop: "1px solid var(--color-ghost)" }}>
                  {block.vettura_id && (
                    <span
                      className="text-[10px] px-2 py-0.5 rounded font-mono"
                      style={{
                        backgroundColor: "var(--color-surface-container)",
                        color: "var(--color-on-surface-muted)",
                      }}
                    >
                      Vettura {block.vettura_id}
                    </span>
                  )}
                  {block.accessori_maggiorati === 1 && (
                    <span
                      className="text-[10px] px-2 py-0.5 rounded font-semibold"
                      style={{
                        backgroundColor: "var(--color-warning-container)",
                        color: "var(--color-warning)",
                      }}
                    >
                      Accessori maggiorati
                    </span>
                  )}
                  {block.minuti_accessori && (
                    <span
                      className="text-[10px] px-2 py-0.5 rounded font-mono"
                      style={{
                        backgroundColor: "var(--color-surface-container)",
                        color: "var(--color-on-surface-muted)",
                      }}
                    >
                      {block.minuti_accessori} min acc.
                    </span>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ── Discrepanze warn ── */}
          {mode === "warn" && arturoDiff.hasDiff && (
            <div className="p-3 bg-amber-50 border-l-2 border-amber-400 rounded text-[11px] space-y-1">
              <div className="flex items-center gap-1.5 font-semibold text-amber-900">
                <AlertTriangle size={12} />
                Discrepanze rilevate
              </div>
              {arturoDiff.messages.map((m, i) => (
                <div key={i} className="pl-5 text-amber-800">· {m}</div>
              ))}
            </div>
          )}

          {/* ── 3. Giro Materiale (prev/curr/next + chain) ── */}
          {block.block_type === "train" && focusedTrainId && (
            <>
              {loading && (
                <div className="flex items-center gap-2 text-[12px] text-[var(--color-on-surface-muted)]">
                  <Loader2 size={12} className="animate-spin" />
                  Caricamento giro materiale…
                </div>
              )}

              {error && (
                <div className="text-[11px] text-destructive bg-destructive/10 p-2 rounded">
                  {error}
                </div>
              )}

              {crossRef && crossRef.material.turn_number && (
                <Section
                  title={`Giro materiale · Turno ${crossRef.material.turn_number}${
                    crossRef.material.total > 0
                      ? ` · pos ${(crossRef.material.position ?? 0) + 1}/${crossRef.material.total}`
                      : ""
                  }`}
                  accent="emerald"
                  icon={<Link2 size={12} />}
                >
                  {/* Precedente */}
                  {crossRef.material.prev && (
                    <MaterialCard
                      direction="prev"
                      train={crossRef.material.prev}
                      onClick={() =>
                        setFocusedTrainId(crossRef.material.prev!.train_id)
                      }
                    />
                  )}
                  {/* Successivo */}
                  {crossRef.material.next && (
                    <MaterialCard
                      direction="next"
                      train={crossRef.material.next}
                      onClick={() =>
                        setFocusedTrainId(crossRef.material.next!.train_id)
                      }
                    />
                  )}
                  {!crossRef.material.prev &&
                    !crossRef.material.next &&
                    crossRef.material.chain.length === 0 && (
                      <div className="text-[11px] text-[var(--color-on-surface-quiet)] italic py-1">
                        Chain non disponibile (orari/stazioni mancanti nel giro).
                      </div>
                    )}

                  {/* Chain pills cliccabili */}
                  {crossRef.material.chain.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2 pt-2">
                      {crossRef.material.chain.map((c, i) => {
                        const isCurr = c.train_id === focusedTrainId
                        return (
                          <button
                            key={i}
                            onClick={() => setFocusedTrainId(c.train_id)}
                            className={cn(
                              "px-2 py-0.5 rounded text-[10px] font-mono font-semibold transition-colors",
                              isCurr
                                ? "bg-[var(--color-brand)] text-white"
                                : "bg-[var(--color-surface-container)] hover:bg-[var(--color-surface-container-high)] text-[var(--color-on-surface)]"
                            )}
                            title={`${c.from} ${c.dep} → ${c.to} ${c.arr}`}
                          >
                            {c.train_id}
                          </button>
                        )
                      })}
                    </div>
                  )}
                </Section>
              )}

              {/* ── 4. Altri Turni Associati (Stitch: "GUIDATO DA TURNI PDC") ── */}
              {crossRef && crossRef.pdc_carriers.length > 0 && (
                <Section
                  title={`Altri turni associati (${crossRef.pdc_carriers.length})`}
                  accent="muted"
                  icon={<Link2 size={12} />}
                >
                  <div className="max-h-48 overflow-y-auto space-y-1.5">
                    {crossRef.pdc_carriers.map((c, i) => {
                      const next = crossRef.pdc_carriers[i + 1]
                      const isHandoff =
                        next && c.block_end && next.block_start === c.block_end
                      return (
                        <PdcCarrierRow
                          key={i}
                          carrier={c}
                          handoffNext={isHandoff ? next.codice : undefined}
                          isFirst={i === 0}
                        />
                      )
                    })}
                  </div>
                </Section>
              )}

              {/* ── 5. ARTURO Live ── */}
              {check && (
                <Section
                  title="ARTURO Live"
                  accent={check.arturo_live.found ? "emerald" : "muted"}
                  icon={
                    check.arturo_live.found ? <CheckCircle2 size={12} /> : undefined
                  }
                >
                  {check.arturo_live.found && check.arturo_live.data ? (
                    <>
                      <Row k="Operatore" v={check.arturo_live.data.operator} />
                      <Row k="Categoria" v={check.arturo_live.data.category} />
                      <Row
                        k="Tratta"
                        v={`${check.arturo_live.data.origin} → ${check.arturo_live.data.destination}`}
                        mono
                      />
                      <Row
                        k="Orario"
                        v={`${check.arturo_live.data.dep_time} → ${check.arturo_live.data.arr_time}`}
                        mono
                      />
                      {check.arturo_live.data.delay !== 0 && (
                        <Row
                          k="Ritardo"
                          v={`${check.arturo_live.data.delay} min`}
                          warn
                        />
                      )}
                      {check.arturo_live.data.status && (
                        <Row k="Stato" v={check.arturo_live.data.status} />
                      )}
                    </>
                  ) : (
                    <div className="text-[11px] text-[var(--color-on-surface-quiet)] italic">
                      Non trovato su ARTURO Live.
                    </div>
                  )}
                </Section>
              )}
            </>
          )}

          {/* Per blocchi non-treno */}
          {block.block_type !== "train" && (
            <Section title="Blocco" accent="muted">
              <Row k="Tipo" v={humanType(block.block_type)} />
              {block.vettura_id && <Row k="Vettura" v={block.vettura_id} mono />}
              {(block.from_station || block.to_station) && (
                <Row
                  k="Tratta"
                  v={`${block.from_station || "—"} → ${block.to_station || "—"}`}
                  mono
                />
              )}
              <Row
                k="Orario"
                v={`${block.start_time || "—"} → ${block.end_time || "—"}`}
                mono
              />
              <div className="text-[11px] text-[var(--color-on-surface-quiet)] italic mt-2">
                Cross-link disponibile solo per blocchi di tipo "treno".
              </div>
            </Section>
          )}
        </div>

        {/* ── 6. Footer ── */}
        <div className="flex items-center gap-2 px-5 py-3 bg-[var(--color-surface-container-low)]">
          {block.block_type === "train" && focusedTrainId && (
            <a
              href={`https://live.arturo.travel/treno/${encodeURIComponent(
                focusedTrainId
              )}`}
              target="_blank"
              rel="noopener"
              className="text-[11px] text-[var(--color-brand)] hover:underline flex items-center gap-1"
            >
              <ExternalLink size={11} />
              Apri su ARTURO Live
            </a>
          )}
          <button
            onClick={handleClose}
            className="ml-auto text-[12px] px-3 py-1.5 rounded-md bg-[var(--color-brand)] text-white hover:opacity-90"
          >
            Chiudi
          </button>
        </div>
      </aside>
    </>
  )
}

// ────────────────────────────────────────────────────────────────
// Sub-components
// ────────────────────────────────────────────────────────────────

function MaterialCard({
  direction,
  train,
  onClick,
}: {
  direction: "prev" | "next"
  train: {
    train_id: string
    from_station: string
    to_station: string
    dep_time: string
    arr_time: string
  }
  onClick: () => void
}) {
  const isPrev = direction === "prev"
  // Stitch: button-card con label direzionale uppercase + train_id mono bold
  // + stazione di handoff (arrivo per prev, partenza per next)
  const handoffLabel = isPrev
    ? `Arr. ${train.to_station || "?"} ${train.arr_time || ""}`
    : `Part. ${train.from_station || "?"} ${train.dep_time || ""}`
  return (
    <button
      onClick={onClick}
      className="w-full p-3 rounded-md transition-all text-left flex items-center gap-3"
      style={{
        backgroundColor: "var(--color-surface-container-lowest)",
        boxShadow: "inset 0 0 0 1px var(--color-ghost)",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.boxShadow =
          "inset 0 0 0 1px rgba(0, 98, 204, 0.4)"
        e.currentTarget.style.backgroundColor =
          "var(--color-surface-container-low)"
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.boxShadow = "inset 0 0 0 1px var(--color-ghost)"
        e.currentTarget.style.backgroundColor =
          "var(--color-surface-container-lowest)"
      }}
      title={`Apri dettaglio ${train.train_id}`}
    >
      {isPrev && (
        <ArrowLeft
          size={14}
          style={{ color: "var(--color-on-surface-muted)" }}
          className="shrink-0"
        />
      )}
      <div className={cn("flex-1 min-w-0", !isPrev && "text-right")}>
        <div
          className="text-[10px] font-bold uppercase"
          style={{
            color: "var(--color-brand)",
            letterSpacing: "0.1em",
          }}
        >
          {isPrev ? "Precedente" : "Successivo"}
        </div>
        <div
          className="font-bold truncate"
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "13px",
            color: "var(--color-on-surface-strong)",
          }}
        >
          {train.train_id}
        </div>
        <div
          className="text-[10.5px] truncate mt-0.5"
          style={{ color: "var(--color-on-surface-muted)" }}
        >
          {handoffLabel}
        </div>
      </div>
      {!isPrev && (
        <ArrowRight
          size={14}
          style={{ color: "var(--color-on-surface-muted)" }}
          className="shrink-0"
        />
      )}
    </button>
  )
}

function PdcCarrierRow({
  carrier,
  handoffNext,
  isFirst,
}: {
  carrier: TrainCrossRef["pdc_carriers"][number]
  handoffNext: string | undefined
  isFirst?: boolean
}) {
  // Stitch "Altri Turni Associati": dot verde sul primo (attivo), grigio sugli altri
  return (
    <div
      className="flex items-center justify-between py-2 px-2.5 rounded-md transition-colors"
      style={{
        backgroundColor: "var(--color-surface-container-low)",
      }}
      onMouseEnter={(e) =>
        (e.currentTarget.style.backgroundColor =
          "var(--color-surface-container)")
      }
      onMouseLeave={(e) =>
        (e.currentTarget.style.backgroundColor =
          "var(--color-surface-container-low)")
      }
    >
      <div className="flex items-center gap-2.5 min-w-0">
        <span
          className="w-2 h-2 rounded-full shrink-0"
          style={{
            backgroundColor: isFirst
              ? "var(--color-dot)"
              : "var(--color-on-surface-quiet)",
            boxShadow: isFirst ? "0 0 0 3px rgba(34, 197, 94, 0.18)" : "none",
          }}
        />
        <span
          className="text-[12px] font-medium"
          style={{ color: "var(--color-on-surface-strong)" }}
        >
          Turno PdC:
        </span>
        <span
          className="font-bold"
          style={{
            fontFamily: "var(--font-mono)",
            color: "var(--color-on-surface-strong)",
            fontSize: "12px",
          }}
        >
          {carrier.codice}
        </span>
        <span
          className="text-[10px] font-mono"
          style={{ color: "var(--color-on-surface-muted)" }}
        >
          g{carrier.day_number ?? "?"} · {carrier.periodicita}
        </span>
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        {handoffNext && (
          <span
            className="text-[9.5px] px-1.5 py-0.5 rounded font-semibold"
            style={{
              backgroundColor: "var(--color-success-container)",
              color: "var(--color-success)",
            }}
            title={`Handoff pulito verso ${handoffNext}`}
          >
            → {handoffNext}
          </span>
        )}
        <span
          className="text-[10px] font-bold uppercase"
          style={{
            color: "var(--color-on-surface-muted)",
            letterSpacing: "0.05em",
          }}
        >
          {carrier.impianto || carrier.to_station || ""}
        </span>
      </div>
      {/* Hidden legacy nodes (backward compat riferimenti orari block_start/end) */}
      <span className="hidden">
        {carrier.from_station} {carrier.to_station}
        {carrier.block_start || "--:--"}→{carrier.block_end || "--:--"}
      </span>
    </div>
  )
}

function Section({
  title,
  children,
  accent,
  icon,
}: {
  title: string
  children: React.ReactNode
  accent?: "blue" | "emerald" | "muted"
  icon?: React.ReactNode
}) {
  // DS "No-Line": niente border, shift tonale tramite bg-surface-container-*
  const bgCls =
    accent === "blue"
      ? "bg-blue-50/50"
      : accent === "emerald"
      ? "bg-emerald-50/40"
      : "bg-[var(--color-surface-container-low)]"
  return (
    <div className={cn("rounded-md p-2.5", bgCls)}>
      <div className="flex items-center gap-1.5 mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-on-surface-muted)]">
        {icon}
        {title}
      </div>
      <div className="space-y-0.5">{children}</div>
    </div>
  )
}

function Row({
  k,
  v,
  mono,
  warn,
}: {
  k: string
  v: string
  mono?: boolean
  warn?: boolean
}) {
  return (
    <div className="grid grid-cols-[110px_1fr] gap-2 text-[11px]">
      <span className="text-[var(--color-on-surface-muted)]">{k}</span>
      <span
        className={cn(
          mono && "font-mono",
          warn && "text-amber-700 font-medium",
          !warn && "text-[var(--color-on-surface)]"
        )}
      >
        {v}
      </span>
    </div>
  )
}

// ────────────────────────────────────────────────────────────────
// Helpers (identici a BlockDetailModal)
// ────────────────────────────────────────────────────────────────

function blockHeader(b: PdcBlock): string {
  if (b.block_type === "train") return `Treno ${b.train_id}`
  if (b.block_type === "coach_transfer")
    return `Vettura (${b.vettura_id || b.train_id})`
  if (b.block_type === "cv_partenza") return `CVp ${b.train_id}`
  if (b.block_type === "cv_arrivo") return `CVa ${b.train_id}`
  if (b.block_type === "meal") return "Refezione"
  if (b.block_type === "scomp") return "S.COMP"
  if (b.block_type === "available") return "Disponibile"
  return b.block_type
}

function humanType(t: string): string {
  return (
    ({
      train: "Treno commerciale",
      coach_transfer: "Vettura (deadhead)",
      cv_partenza: "Cambio Volante in Partenza",
      cv_arrivo: "Cambio Volante in Arrivo",
      meal: "Refezione",
      scomp: "S.COMP (disponibilità comparto)",
      available: "Giornata disponibile",
    } as Record<string, string>)[t] || t
  )
}

function computeArturoDiff(
  block: PdcBlock,
  check: TrainCheckResult | null
): { hasDiff: boolean; messages: string[] } {
  const msgs: string[] = []
  if (!check) return { hasDiff: false, messages: msgs }

  const arturo = check.arturo_live.data
  const db = check.db_internal.data

  if (arturo) {
    if (
      arturo.dep_time &&
      block.start_time &&
      arturo.dep_time !== block.start_time
    ) {
      msgs.push(
        `Partenza nel turno ${block.start_time}, ARTURO Live ${arturo.dep_time}`
      )
    }
    if (
      arturo.arr_time &&
      block.end_time &&
      arturo.arr_time !== block.end_time
    ) {
      msgs.push(
        `Arrivo nel turno ${block.end_time}, ARTURO Live ${arturo.arr_time}`
      )
    }
    if (arturo.delay && Math.abs(arturo.delay) >= 5) {
      msgs.push(`Ritardo corrente ${arturo.delay} min`)
    }
  }
  if (db) {
    if (
      db.dep_time &&
      block.start_time &&
      db.dep_time !== block.start_time
    ) {
      msgs.push(
        `Partenza nel turno ${block.start_time}, giro materiale ${db.dep_time}`
      )
    }
    if (
      db.arr_time &&
      block.end_time &&
      db.arr_time !== block.end_time
    ) {
      msgs.push(
        `Arrivo nel turno ${block.end_time}, giro materiale ${db.arr_time}`
      )
    }
  }
  return { hasDiff: msgs.length > 0, messages: msgs }
}
