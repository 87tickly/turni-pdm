/**
 * AbilitazioniPage — gestione abilitazioni linee + materiale per deposito.
 *
 * Per ogni deposito mostra le linee (coppie stazioni estremi del giro
 * materiale) e i materiali rotabili candidati. Toggle istantaneo:
 * checkbox -> POST/DELETE -> reload stato.
 *
 * Le abilitazioni filtrano quali segmenti l'auto-builder puo' usare per
 * i PdC del deposito (sia treni produttivi che candidati di rientro).
 */

import { useEffect, useState } from "react"
import { ShieldCheck, Building2, Train, Loader2, AlertTriangle, Check } from "lucide-react"
import {
  getConstants,
  getAbilitazioni,
  addLinea,
  removeLinea,
  addMateriale,
  removeMateriale,
  type AppConstants,
  type AbilitazioniResponse,
} from "@/lib/api"

export function AbilitazioniPage() {
  const [constants, setConstants] = useState<AppConstants | null>(null)
  const [deposito, setDeposito] = useState<string>("")
  const [data, setData] = useState<AbilitazioniResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>("")

  useEffect(() => {
    getConstants()
      .then((c) => {
        setConstants(c)
        if (c.DEPOSITI && c.DEPOSITI.length > 0 && !deposito) {
          setDeposito(c.DEPOSITI[0])
        }
      })
      .catch((e) => setError(e?.message ?? "Errore caricamento depositi"))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!deposito) return
    void reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deposito])

  async function reload() {
    setLoading(true)
    setError("")
    try {
      const r = await getAbilitazioni(deposito)
      setData(r)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  async function toggleLinea(a: string, b: string, currentlyEnabled: boolean) {
    setError("")
    try {
      if (currentlyEnabled) {
        await removeLinea(deposito, a, b)
      } else {
        await addLinea(deposito, a, b)
      }
      await reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function toggleMateriale(mat: string, currentlyEnabled: boolean) {
    setError("")
    try {
      if (currentlyEnabled) {
        await removeMateriale(deposito, mat)
      } else {
        await addMateriale(deposito, mat)
      }
      await reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const enabledLineCount = data?.enabled_lines.length ?? 0
  const enabledMatCount = data?.enabled_materials.length ?? 0
  const availLineCount = data?.available_lines.length ?? 0
  const availMatCount = data?.available_materials.length ?? 0

  return (
    <div>
      {/* Header */}
      <div className="mb-5">
        <div
          className="text-[10px] font-bold uppercase mb-1"
          style={{
            color: "var(--color-on-surface-quiet)",
            letterSpacing: "0.12em",
          }}
        >
          Configurazione PdC
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
          <ShieldCheck size={20} style={{ color: "var(--color-brand)" }} />
          Abilitazioni deposito
        </h2>
        <p
          className="text-[13px] mt-0.5"
          style={{ color: "var(--color-on-surface-muted)" }}
        >
          Linee (coppie stazioni estremi) e materiale rotabile su cui i PdC del deposito sono abilitati. L'auto-builder usera' solo treni che rispettano entrambi.
        </p>
      </div>

      {/* Selettore deposito */}
      <div
        className="rounded-xl p-4 mb-4 flex items-end gap-4"
        style={{
          backgroundColor: "var(--color-surface-container-lowest)",
          boxShadow: "var(--shadow-sm)",
        }}
      >
        <label className="flex flex-col gap-1.5 flex-1 max-w-md">
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

        {data && (
          <div className="flex items-center gap-4 ml-auto">
            <Stat label="Linee" value={`${enabledLineCount}/${availLineCount}`} />
            <Stat label="Materiali" value={`${enabledMatCount}/${availMatCount}`} />
          </div>
        )}
      </div>

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

      {loading && !data && (
        <div className="flex items-center justify-center py-12">
          <Loader2 size={24} className="animate-spin" style={{ color: "var(--color-brand)" }} />
        </div>
      )}

      {data && availLineCount === 0 && availMatCount === 0 && (
        <div
          className="rounded-xl p-6 text-center text-[13px]"
          style={{
            backgroundColor: "var(--color-surface-container-lowest)",
            boxShadow: "var(--shadow-sm)",
            color: "var(--color-on-surface-muted)",
          }}
        >
          Nessun giro materiale tocca il deposito <strong>{deposito}</strong>. Importa un PDF turno materiale e ricarica.
        </div>
      )}

      {/* Linee */}
      {data && availLineCount > 0 && (
        <div
          className="rounded-xl p-5 mb-4"
          style={{
            backgroundColor: "var(--color-surface-container-lowest)",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          <SectionHeader
            icon={Train}
            title="Linee disponibili"
            sub={`${enabledLineCount} di ${availLineCount} abilitate`}
          />
          <div className="space-y-1">
            {data.available_lines.map((l) => (
              <ToggleRow
                key={`${l.station_a}|${l.station_b}`}
                label={`${l.station_a} ↔ ${l.station_b}`}
                meta={`${l.material_turn_count} giro${l.material_turn_count !== 1 ? "i" : ""}`}
                enabled={l.enabled}
                onToggle={() => toggleLinea(l.station_a, l.station_b, l.enabled)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Materiali */}
      {data && availMatCount > 0 && (
        <div
          className="rounded-xl p-5"
          style={{
            backgroundColor: "var(--color-surface-container-lowest)",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          <SectionHeader
            icon={Train}
            title="Materiale rotabile disponibile"
            sub={`${enabledMatCount} di ${availMatCount} abilitati`}
          />
          <div className="space-y-1">
            {data.available_materials.map((m) => (
              <ToggleRow
                key={m.material_type}
                label={m.material_type}
                meta={`${m.material_turn_count} giro${m.material_turn_count !== 1 ? "i" : ""}`}
                enabled={m.enabled}
                onToggle={() => toggleMateriale(m.material_type, m.enabled)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
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
          fontSize: "16px",
          color: "var(--color-on-surface-strong)",
          letterSpacing: "-0.02em",
          lineHeight: 1.1,
        }}
      >
        {value}
      </div>
    </div>
  )
}

function SectionHeader({
  icon: Icon,
  title,
  sub,
}: {
  icon: typeof Train
  title: string
  sub: string
}) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <Icon size={14} style={{ color: "var(--color-on-surface-quiet)" }} />
      <h3
        className="font-semibold"
        style={{
          fontFamily: "var(--font-display)",
          fontSize: "14px",
          color: "var(--color-on-surface-strong)",
        }}
      >
        {title}
      </h3>
      <span
        className="ml-auto text-[11px]"
        style={{ color: "var(--color-on-surface-muted)" }}
      >
        {sub}
      </span>
    </div>
  )
}

function ToggleRow({
  label,
  meta,
  enabled,
  onToggle,
}: {
  label: string
  meta: string
  enabled: boolean
  onToggle: () => void
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-left transition-colors"
      style={{
        backgroundColor: enabled
          ? "var(--color-success-container)"
          : "var(--color-surface-container-low)",
      }}
    >
      <span
        className="w-4 h-4 rounded-sm flex items-center justify-center shrink-0"
        style={{
          backgroundColor: enabled ? "var(--color-success)" : "transparent",
          boxShadow: enabled
            ? "none"
            : "inset 0 0 0 1.5px var(--color-on-surface-quiet)",
        }}
      >
        {enabled && <Check size={11} color="white" strokeWidth={3} />}
      </span>
      <span
        className="text-[13px] font-medium flex-1"
        style={{
          color: enabled ? "var(--color-success)" : "var(--color-on-surface-strong)",
          fontFamily: "var(--font-mono)",
        }}
      >
        {label}
      </span>
      <span
        className="text-[10.5px]"
        style={{ color: "var(--color-on-surface-muted)" }}
      >
        {meta}
      </span>
    </button>
  )
}
