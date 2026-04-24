/**
 * BuilderV2Page — nuovo builder basato su NORMATIVA-PDC.md.
 *
 * Pipeline: turno materiale (JSON con segmenti) → POST /api/builder-v2/cover
 * → lista PdC con timeline eventi + validazioni.
 *
 * Differenze col vecchio /auto-genera:
 * - Costruito dall'algoritmo formalizzato (docs/ALGORITMO-BUILDER.md).
 * - Applica §11.8 (cap 7h se presa servizio 01:00-04:59), §4.1
 *   (soglia REFEZ 6h), §8.5 (FIOz +7' accp), §9.2 (CV stazioni
 *   ammesse), §15 (no doppioni).
 * - Input diretto di un turno materiale (non passa dal DB segments).
 */

import { useState } from "react"
import {
  Sparkles,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  Play,
  FileJson,
} from "lucide-react"
import {
  builderV2Cover,
  builderV2ExampleP1,
  type BuilderV2CoverRequest,
  type BuilderV2CoverResponse,
  type BuilderV2EventoOut,
  type BuilderV2PdCOut,
} from "@/lib/api"

const EVENT_COLOR: Record<string, string> = {
  presa_servizio: "bg-slate-200 text-slate-700",
  fine_servizio: "bg-slate-200 text-slate-700",
  taxi: "bg-amber-100 text-amber-800",
  vettura: "bg-sky-100 text-sky-800",
  mm: "bg-indigo-100 text-indigo-800",
  accp: "bg-emerald-100 text-emerald-800",
  acca: "bg-emerald-100 text-emerald-800",
  condotta: "bg-blue-500 text-white",
  pk_arrivo: "bg-purple-100 text-purple-800",
  pk_partenza: "bg-purple-100 text-purple-800",
  buco: "bg-gray-100 text-gray-600",
  refez: "bg-orange-100 text-orange-800",
  cva: "bg-pink-100 text-pink-800",
  cvp: "bg-pink-100 text-pink-800",
}

function EventoRow({ ev }: { ev: BuilderV2EventoOut }) {
  const cls = EVENT_COLOR[ev.kind] ?? "bg-gray-100 text-gray-600"
  const route = ev.stazione_a ? `${ev.stazione} → ${ev.stazione_a}` : ev.stazione
  return (
    <div className="grid grid-cols-[110px_130px_1fr_auto] items-center gap-2 py-1 text-xs border-b border-slate-100 last:border-0">
      <div className="font-mono text-slate-600">
        {ev.inizio}–{ev.fine}
      </div>
      <div>
        <span className={`px-2 py-0.5 rounded ${cls} font-medium`}>
          {ev.kind}
        </span>
      </div>
      <div className="text-slate-700">
        {ev.treno && <span className="font-mono font-semibold">{ev.treno}</span>}
        {ev.treno && route && " · "}
        <span className="text-slate-600">{route}</span>
      </div>
      <div className="text-[11px] text-slate-400">
        {ev.durata_min > 0 ? `${ev.durata_min}'` : ""}
      </div>
    </div>
  )
}

function PdCCard({ pdc, index }: { pdc: BuilderV2PdCOut; index: number }) {
  const viol = pdc.violazioni.length
  const ok = viol === 0
  return (
    <div className="border border-slate-200 rounded-lg overflow-hidden bg-white">
      <div
        className={`px-4 py-2 flex items-center justify-between ${
          ok ? "bg-emerald-50" : "bg-rose-50"
        }`}
      >
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-slate-500">PdC {index}</span>
          <span className="font-semibold text-slate-800">{pdc.deposito}</span>
          <span className="text-sm text-slate-600">
            {pdc.presa_servizio} → {pdc.fine_servizio}
          </span>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-slate-600">
            prest <span className="font-mono font-semibold">{pdc.prestazione_min}'</span>
            <span className="text-slate-400">/{pdc.cap_prestazione_min}'</span>
          </span>
          <span className="text-slate-600">
            cond <span className="font-mono font-semibold">{pdc.condotta_min}'</span>
            <span className="text-slate-400">/330'</span>
          </span>
          {ok ? (
            <span className="flex items-center gap-1 text-emerald-700 text-xs">
              <CheckCircle2 className="size-4" /> valido
            </span>
          ) : (
            <span className="flex items-center gap-1 text-rose-700 text-xs">
              <AlertTriangle className="size-4" /> {viol} violaz.
            </span>
          )}
        </div>
      </div>
      {viol > 0 && (
        <div className="px-4 py-2 bg-rose-50/60 border-t border-rose-200 text-xs text-rose-800">
          {pdc.violazioni.map((v, i) => (
            <div key={i} className="flex items-start gap-1">
              <AlertTriangle className="size-3 mt-0.5 shrink-0" />
              <span>{v}</span>
            </div>
          ))}
        </div>
      )}
      <div className="px-4 py-2">
        {pdc.eventi.map((ev, i) => (
          <EventoRow key={i} ev={ev} />
        ))}
      </div>
    </div>
  )
}

const EMPTY_INPUT: BuilderV2CoverRequest = {
  materiale: [],
  deposito_preferito: "GARIBALDI_ALE",
}

export function BuilderV2Page() {
  const [inputJson, setInputJson] = useState<string>(
    JSON.stringify(EMPTY_INPUT, null, 2)
  )
  const [result, setResult] = useState<BuilderV2CoverResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleLoadExample() {
    setError(null)
    setLoading(true)
    try {
      const ex = await builderV2ExampleP1()
      setInputJson(JSON.stringify(ex, null, 2))
      setResult(null)
    } catch (e: any) {
      setError(e.message ?? String(e))
    } finally {
      setLoading(false)
    }
  }

  async function handleGenerate() {
    setError(null)
    setResult(null)
    setLoading(true)
    try {
      const req: BuilderV2CoverRequest = JSON.parse(inputJson)
      const res = await builderV2Cover(req)
      setResult(res)
    } catch (e: any) {
      setError(e.message ?? String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-4">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Sparkles className="size-6 text-indigo-600" />
          Builder V2 — materiale → PdC
        </h1>
        <p className="text-sm text-slate-600 mt-1">
          Nuovo builder basato su <code>docs/NORMATIVA-PDC.md</code> e{" "}
          <code>docs/ALGORITMO-BUILDER.md</code>. Applica §11.8 (cap 7h
          notte), §4.1 (REFEZ &gt; 6h), §8.5 (FIOz), §9.2 (CV), §15 (no
          doppioni).
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Input */}
        <div className="border border-slate-200 rounded-lg bg-white">
          <div className="px-4 py-2 border-b border-slate-200 flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
              <FileJson className="size-4" />
              Turno materiale (JSON)
            </div>
            <button
              onClick={handleLoadExample}
              disabled={loading}
              className="text-xs px-3 py-1 rounded border border-slate-300 hover:bg-slate-50 disabled:opacity-50"
            >
              Carica esempio P1 (1130 Valtellina)
            </button>
          </div>
          <textarea
            value={inputJson}
            onChange={(e) => setInputJson(e.target.value)}
            className="w-full h-[480px] p-3 font-mono text-xs text-slate-800 outline-none resize-none"
            spellCheck={false}
          />
          <div className="px-4 py-2 border-t border-slate-200 flex justify-end">
            <button
              onClick={handleGenerate}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 rounded bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
            >
              {loading ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Play className="size-4" />
              )}
              Genera PdC
            </button>
          </div>
        </div>

        {/* Risultato — riassunto */}
        <div className="border border-slate-200 rounded-lg bg-white">
          <div className="px-4 py-2 border-b border-slate-200 text-sm font-semibold text-slate-700">
            Risultato
          </div>
          <div className="p-4 space-y-3">
            {error && (
              <div className="p-3 rounded bg-rose-50 border border-rose-200 text-sm text-rose-800">
                <AlertTriangle className="size-4 inline mr-1" />
                {error}
              </div>
            )}
            {!result && !error && (
              <div className="text-sm text-slate-500 italic">
                Carica un esempio o incolla un materiale JSON, poi
                clicca "Genera PdC".
              </div>
            )}
            {result && (
              <>
                <div className="grid grid-cols-3 gap-3 text-center">
                  <div className="p-3 rounded bg-slate-50">
                    <div className="text-2xl font-bold text-slate-800">
                      {result.pdc.length}
                    </div>
                    <div className="text-xs text-slate-500">PdC generati</div>
                  </div>
                  <div
                    className={`p-3 rounded ${
                      result.residui_count === 0
                        ? "bg-emerald-50"
                        : "bg-amber-50"
                    }`}
                  >
                    <div
                      className={`text-2xl font-bold ${
                        result.residui_count === 0
                          ? "text-emerald-700"
                          : "text-amber-700"
                      }`}
                    >
                      {result.residui_count}
                    </div>
                    <div className="text-xs text-slate-500">Segmenti residui</div>
                  </div>
                  <div
                    className={`p-3 rounded ${
                      result.violazioni_totali === 0
                        ? "bg-emerald-50"
                        : "bg-rose-50"
                    }`}
                  >
                    <div
                      className={`text-2xl font-bold ${
                        result.violazioni_totali === 0
                          ? "text-emerald-700"
                          : "text-rose-700"
                      }`}
                    >
                      {result.violazioni_totali}
                    </div>
                    <div className="text-xs text-slate-500">Violazioni</div>
                  </div>
                </div>
                {result.residui_count > 0 && (
                  <div className="text-xs text-amber-800 bg-amber-50 p-2 rounded border border-amber-200">
                    Residui: {result.residui_numeri.join(", ")}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {/* Lista PdC */}
      {result && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold text-slate-800">
            Turni PdC generati
          </h2>
          {result.pdc.map((pdc, i) => (
            <PdCCard key={i} pdc={pdc} index={i + 1} />
          ))}
        </div>
      )}
    </div>
  )
}
