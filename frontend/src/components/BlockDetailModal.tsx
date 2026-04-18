/**
 * BlockDetailModal — Modal dettaglio di un blocco Gantt con triple-check.
 *
 * Per i blocchi di tipo "train" esegue /train-check/{train_id}:
 *   - DB interno (giro materiale)
 *   - turni PdC che lo citano
 *   - ARTURO Live (real-time)
 *
 * Due modalita' di apertura:
 *   mode="detail"  → panoramica neutra con tutti gli elementi
 *   mode="warn"    → evidenzia discrepanze tra orari del blocco e ARTURO Live
 *
 * Per i blocchi non-treno (vettura, refez, CVp, CVa, scomp) mostra
 * solo le info del blocco senza chiamare /train-check.
 */

import { useEffect, useState } from "react"
import { X, Loader2, AlertTriangle, CheckCircle2, Link2, Train, ExternalLink, Clock, ArrowLeft, ArrowRight } from "lucide-react"
import { trainCheck, trainCrossRef, type TrainCheckResult, type TrainCrossRef, type PdcBlock } from "@/lib/api"
import { cn } from "@/lib/utils"

interface Props {
  block: PdcBlock
  index: number
  mode: "detail" | "warn"
  onClose: () => void
}

export function BlockDetailModal({ block, mode, onClose }: Props) {
  const [check, setCheck] = useState<TrainCheckResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  // Cross-ref: continuazione materiale (prev/next/chain) + PdC carriers completi.
  // Caricato in parallelo al triple-check. Errore non blocca il render del modal:
  // se /train/{id}/cross-ref fallisce, la sezione viene semplicemente omessa.
  const [crossRef, setCrossRef] = useState<TrainCrossRef | null>(null)

  // Esegui triple-check solo per i treni
  useEffect(() => {
    if (block.block_type !== "train" || !block.train_id) return
    setLoading(true)
    setError("")
    setCrossRef(null)
    // Chiamate in parallelo: il triple-check e' piu' lento (ARTURO Live),
    // cross-ref e' solo DB quindi istantaneo -> appare per primo
    trainCrossRef(block.train_id)
      .then(setCrossRef)
      .catch(() => {}) // best-effort, non blocca il modal
    trainCheck(block.train_id)
      .then(setCheck)
      .catch((e) => setError(e instanceof Error ? e.message : "Errore triple-check"))
      .finally(() => setLoading(false))
  }, [block.block_type, block.train_id])

  // Esc per chiudere
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [onClose])

  // Calcolo discrepanza orari (solo in mode="warn" con train_id)
  const arturoDiff = computeArturoDiff(block, check)

  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-slate-900/60 backdrop-blur-sm"
         onClick={onClose}>
      <div className="bg-card rounded-xl shadow-2xl border border-border-subtle w-[560px] max-w-[92vw] max-h-[90vh] overflow-y-auto"
           onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-start gap-3 p-4 border-b border-border-subtle">
          <div className={cn(
            "h-9 w-9 rounded-lg flex items-center justify-center shrink-0",
            mode === "warn" ? "bg-amber-100 text-amber-700" : "bg-blue-100 text-blue-700"
          )}>
            {mode === "warn" ? <AlertTriangle size={16} /> : <Train size={16} />}
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-[14px]">
              {blockHeader(block)}
            </h3>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              {mode === "warn"
                ? "Verifica discrepanze con ARTURO Live e giro materiale"
                : "Dettaglio blocco + triple-check (DB interno / PdC / ARTURO Live)"}
            </p>
          </div>
          <button onClick={onClose}
                  className="p-1 rounded hover:bg-muted"
                  title="Chiudi (Esc)">
            <X size={16} />
          </button>
        </div>

        <div className="p-4 space-y-4">
          {/* Info blocco */}
          <Section title="Blocco nel turno">
            <Row k="Tipo" v={humanType(block.block_type)} />
            {block.train_id && <Row k="Numero treno" v={block.train_id} mono />}
            {block.vettura_id && <Row k="Numero vettura" v={block.vettura_id} mono />}
            {(block.from_station || block.to_station) && (
              <Row k="Tratta" v={`${block.from_station || "—"} → ${block.to_station || "—"}`} mono />
            )}
            <Row k="Orario" v={`${block.start_time || "—"} → ${block.end_time || "—"}`} mono />
            {block.accessori_maggiorati === 1 && (
              <Row k="Accessori" v="Maggiorati (preriscaldo)" warn />
            )}
            {block.minuti_accessori && (
              <Row k="Minuti accessori" v={block.minuti_accessori} mono />
            )}
            {block.fonte_orario && (
              <Row k="Fonte orario" v={block.fonte_orario} mono />
            )}
          </Section>

          {/* Triple-check (solo treni) */}
          {block.block_type === "train" && block.train_id && (
            <>
              {loading && (
                <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
                  <Loader2 size={12} className="animate-spin" />
                  Controllo su DB interno, PdC e ARTURO Live...
                </div>
              )}

              {error && (
                <div className="text-[11px] text-destructive bg-destructive/10 p-2 rounded">
                  {error}
                </div>
              )}

              {!loading && !error && check && (
                <>
                  {/* Warning discrepanze (solo in mode warn + discrepanze presenti) */}
                  {mode === "warn" && arturoDiff.hasDiff && (
                    <div className="p-3 bg-amber-50 border border-amber-300 rounded text-[11px] space-y-1">
                      <div className="flex items-center gap-1.5 font-semibold text-amber-900">
                        <AlertTriangle size={12} />
                        Discrepanze rilevate
                      </div>
                      {arturoDiff.messages.map((m, i) => (
                        <div key={i} className="pl-5 text-amber-800">· {m}</div>
                      ))}
                    </div>
                  )}

                  {/* DB interno (giro materiale) */}
                  <Section
                    title="Giro materiale (DB interno)"
                    accent={check.db_internal.found ? "emerald" : "muted"}
                    icon={check.db_internal.found ? <CheckCircle2 size={12} /> : undefined}
                  >
                    {check.db_internal.found && check.db_internal.data ? (
                      <>
                        <Row k="Tratta" v={`${check.db_internal.data.from_station} → ${check.db_internal.data.to_station}`} mono />
                        <Row k="Orario" v={`${check.db_internal.data.dep_time} → ${check.db_internal.data.arr_time}`} mono />
                        {check.db_internal.data.is_deadhead && (
                          <Row k="Tipo" v="Vettura (deadhead)" />
                        )}
                        {check.db_internal.data.material_turn_id !== undefined && (
                          <Row k="Giro #" v={String(check.db_internal.data.material_turn_id)} mono />
                        )}
                      </>
                    ) : (
                      <div className="text-[11px] text-muted-foreground italic">
                        Treno non presente nei giri materiale caricati
                      </div>
                    )}
                  </Section>

                  {/* Continuazione giro materiale (Fase 2b cross-link).
                      Mostra prev/next treno nello stesso turno materiale +
                      chain compatta. Dati da /train/{id}/cross-ref. */}
                  {crossRef && crossRef.material.turn_number && (
                    <Section
                      title={`Continuazione giro · Turno ${crossRef.material.turn_number}${crossRef.material.total > 0 ? ` · pos ${(crossRef.material.position ?? 0) + 1}/${crossRef.material.total}` : ""}`}
                      accent="emerald"
                      icon={<Link2 size={12} />}
                    >
                      {crossRef.material.prev && (
                        <div className="flex items-center gap-2 text-[11px] font-mono py-1">
                          <ArrowLeft size={11} className="text-emerald-700 shrink-0" />
                          <span className="font-bold">{crossRef.material.prev.train_id}</span>
                          <span className="text-muted-foreground">
                            {crossRef.material.prev.from_station || "?"} → {crossRef.material.prev.to_station || "?"}
                          </span>
                          {crossRef.material.prev.dep_time && (
                            <span className="text-muted-foreground ml-auto">
                              {crossRef.material.prev.dep_time}
                              {crossRef.material.prev.arr_time && ` → ${crossRef.material.prev.arr_time}`}
                            </span>
                          )}
                        </div>
                      )}
                      {crossRef.material.next && (
                        <div className="flex items-center gap-2 text-[11px] font-mono py-1">
                          <ArrowRight size={11} className="text-emerald-700 shrink-0" />
                          <span className="font-bold">{crossRef.material.next.train_id}</span>
                          <span className="text-muted-foreground">
                            {crossRef.material.next.from_station || "?"} → {crossRef.material.next.to_station || "?"}
                          </span>
                          {crossRef.material.next.dep_time && (
                            <span className="text-muted-foreground ml-auto">
                              {crossRef.material.next.dep_time}
                              {crossRef.material.next.arr_time && ` → ${crossRef.material.next.arr_time}`}
                            </span>
                          )}
                        </div>
                      )}
                      {!crossRef.material.prev && !crossRef.material.next && crossRef.material.chain.length === 0 && (
                        <div className="text-[11px] text-muted-foreground italic">
                          Chain non disponibile (orari/stazioni mancanti nel giro materiale).
                        </div>
                      )}
                      {crossRef.material.chain.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1.5 pt-1.5 border-t border-emerald-200">
                          {crossRef.material.chain.map((c, i) => {
                            const isCurr = c.train_id === crossRef.train_id
                            return (
                              <span
                                key={i}
                                className={cn(
                                  "px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold",
                                  isCurr
                                    ? "bg-emerald-600 text-white"
                                    : "bg-white border border-emerald-200 text-emerald-900"
                                )}
                                title={`${c.from} ${c.dep} → ${c.to} ${c.arr}`}
                              >
                                {c.train_id}
                              </span>
                            )
                          })}
                        </div>
                      )}
                    </Section>
                  )}

                  {/* Tutti i PdC carriers (lista completa dal cross-ref).
                      Usa crossRef.pdc_carriers al posto di check.pdc.results
                      quando disponibile, perche' piu' completo e con piu' campi. */}
                  {crossRef && crossRef.pdc_carriers.length > 0 && (
                    <Section
                      title={`Guidato da turni PdC (${crossRef.pdc_carriers.length})`}
                      accent="blue"
                      icon={<Link2 size={12} />}
                    >
                      <div className="max-h-36 overflow-y-auto space-y-1 text-[11px]">
                        {crossRef.pdc_carriers.map((c, i) => (
                          <div
                            key={i}
                            className="grid grid-cols-[auto_auto_1fr_auto] gap-2 py-0.5 font-mono"
                          >
                            <span className="font-bold">{c.codice}</span>
                            <span className="text-muted-foreground">
                              g{c.day_number ?? "?"} {c.periodicita}
                            </span>
                            <span className="truncate">
                              {c.from_station || "?"} → {c.to_station || "?"}
                            </span>
                            <span className="text-muted-foreground">
                              {c.block_start || "--:--"}→{c.block_end || "--:--"}
                            </span>
                          </div>
                        ))}
                      </div>
                    </Section>
                  )}

                  {/* PdC (altre giornate) */}
                  {!crossRef && check.pdc.found && check.pdc.results.length > 0 && (
                    <Section title={`Presente in altri turni PdC (${check.pdc.results.length})`} accent="blue" icon={<Link2 size={12} />}>
                      <div className="max-h-28 overflow-y-auto space-y-1 text-[11px] font-mono">
                        {check.pdc.results.slice(0, 8).map((r, i) => (
                          <div key={i} className="grid grid-cols-[auto_auto_1fr_auto] gap-2 py-0.5">
                            <span className="font-bold">{r.codice}</span>
                            <span className="text-muted-foreground">g{r.day_number} {r.periodicita}</span>
                            <span>{r.from_station} → {r.to_station}</span>
                            <span className="text-muted-foreground">{r.block_start}</span>
                          </div>
                        ))}
                        {check.pdc.results.length > 8 && (
                          <div className="text-[10px] text-muted-foreground italic">
                            +{check.pdc.results.length - 8} altri...
                          </div>
                        )}
                      </div>
                    </Section>
                  )}

                  {/* ARTURO Live */}
                  <Section
                    title="ARTURO Live (real-time)"
                    accent={check.arturo_live.found ? "emerald" : "muted"}
                    icon={check.arturo_live.found ? <CheckCircle2 size={12} /> : undefined}
                  >
                    {check.arturo_live.found && check.arturo_live.data ? (
                      <>
                        <Row k="Operatore" v={check.arturo_live.data.operator} />
                        <Row k="Categoria" v={check.arturo_live.data.category} />
                        <Row k="Tratta" v={`${check.arturo_live.data.origin} → ${check.arturo_live.data.destination}`} mono />
                        <Row k="Orario" v={`${check.arturo_live.data.dep_time} → ${check.arturo_live.data.arr_time}`} mono />
                        <Row k="Fermate" v={String(check.arturo_live.data.num_stops)} mono />
                        {check.arturo_live.data.delay !== 0 && (
                          <Row k="Ritardo" v={`${check.arturo_live.data.delay} min`} warn />
                        )}
                        {check.arturo_live.data.status && (
                          <Row k="Stato" v={check.arturo_live.data.status} />
                        )}
                      </>
                    ) : (
                      <div className="text-[11px] text-muted-foreground italic">
                        Treno non trovato su ARTURO Live (o offline)
                      </div>
                    )}
                  </Section>
                </>
              )}
            </>
          )}

          {/* Per blocchi non-treno: nessun triple-check, solo nota */}
          {block.block_type !== "train" && (
            <div className="text-[11px] text-muted-foreground italic">
              Il triple-check ARTURO Live è disponibile solo per blocchi "treno".
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center gap-2 p-3 border-t border-border-subtle bg-muted/20">
          {block.block_type === "train" && block.train_id && (
            <a
              href={`https://live.arturo.travel/treno/${encodeURIComponent(block.train_id)}`}
              target="_blank"
              rel="noopener"
              className="text-[11px] text-primary hover:underline flex items-center gap-1"
            >
              <ExternalLink size={11} />
              Apri su ARTURO Live
            </a>
          )}
          <button
            onClick={onClose}
            className="ml-auto text-[12px] px-3 py-1.5 rounded bg-primary text-primary-foreground hover:bg-primary/90"
          >
            Chiudi
          </button>
        </div>
      </div>
    </div>
  )
}

// ── helpers ─────────────────────────────────────────────────────
function blockHeader(b: PdcBlock): string {
  if (b.block_type === "train") return `Treno ${b.train_id}`
  if (b.block_type === "coach_transfer") return `Vettura (${b.vettura_id || b.train_id})`
  if (b.block_type === "cv_partenza") return `CVp ${b.train_id}`
  if (b.block_type === "cv_arrivo") return `CVa ${b.train_id}`
  if (b.block_type === "meal") return "Refezione"
  if (b.block_type === "scomp") return "S.COMP"
  if (b.block_type === "available") return "Disponibile"
  return b.block_type
}

function humanType(t: string): string {
  return ({
    train: "Treno commerciale",
    coach_transfer: "Vettura (deadhead)",
    cv_partenza: "Cambio Volante in Partenza",
    cv_arrivo: "Cambio Volante in Arrivo",
    meal: "Refezione",
    scomp: "S.COMP (disponibilità comparto)",
    available: "Giornata disponibile",
  } as Record<string, string>)[t] || t
}

function computeArturoDiff(block: PdcBlock, check: TrainCheckResult | null) {
  const msgs: string[] = []
  if (!check) return { hasDiff: false, messages: msgs }

  const arturo = check.arturo_live.data
  const db = check.db_internal.data

  if (arturo) {
    if (arturo.dep_time && block.start_time && arturo.dep_time !== block.start_time) {
      msgs.push(`Partenza nel turno ${block.start_time}, ARTURO Live ${arturo.dep_time}`)
    }
    if (arturo.arr_time && block.end_time && arturo.arr_time !== block.end_time) {
      msgs.push(`Arrivo nel turno ${block.end_time}, ARTURO Live ${arturo.arr_time}`)
    }
    if (arturo.delay && Math.abs(arturo.delay) >= 5) {
      msgs.push(`Ritardo corrente ${arturo.delay} min`)
    }
  }
  if (db) {
    if (db.dep_time && block.start_time && db.dep_time !== block.start_time) {
      msgs.push(`Partenza nel turno ${block.start_time}, giro materiale ${db.dep_time}`)
    }
    if (db.arr_time && block.end_time && db.arr_time !== block.end_time) {
      msgs.push(`Arrivo nel turno ${block.end_time}, giro materiale ${db.arr_time}`)
    }
  }
  return { hasDiff: msgs.length > 0, messages: msgs }
}

// ── sub components ─────────────────────────────────────────────
function Section({
  title, children, accent, icon,
}: {
  title: string
  children: React.ReactNode
  accent?: "blue" | "emerald" | "muted"
  icon?: React.ReactNode
}) {
  const borderCls = accent === "blue" ? "border-blue-300 bg-blue-50/50"
    : accent === "emerald" ? "border-emerald-300 bg-emerald-50/50"
    : accent === "muted" ? "border-border-subtle bg-muted/10"
    : "border-border-subtle"
  return (
    <div className={cn("rounded-md border p-2.5", borderCls)}>
      <div className="flex items-center gap-1.5 mb-1 text-[10px] font-semibold uppercase tracking-wider text-foreground/80">
        {icon}
        {title}
      </div>
      <div className="space-y-0.5">{children}</div>
    </div>
  )
}

function Row({ k, v, mono, warn }: { k: string; v: string; mono?: boolean; warn?: boolean }) {
  return (
    <div className="grid grid-cols-[110px_1fr] gap-2 text-[11px]">
      <span className="text-muted-foreground">{k}</span>
      <span className={cn(
        mono && "font-mono",
        warn && "text-amber-700 font-medium",
      )}>
        {v}
      </span>
    </div>
  )
}

// Suppress unused-warning su Clock (reserved for future use)
void Clock
