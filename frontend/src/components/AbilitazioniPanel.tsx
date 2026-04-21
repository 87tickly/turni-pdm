/**
 * AbilitazioniPanel — pannello collassabile per gestire le abilitazioni
 * (linee + materiale rotabile) di un deposito.
 *
 * Usato dentro AutoBuilderPage come "Step 0" prima della generazione:
 * l'auto-builder usera' solo segmenti che rispettano le abilitazioni
 * del deposito selezionato.
 */

import { useEffect, useState } from "react"
import { ChevronDown, ShieldCheck, Train, Loader2, AlertTriangle, Check } from "lucide-react"
import {
  getAbilitazioni,
  addLinea,
  removeLinea,
  addMateriale,
  removeMateriale,
  type AbilitazioniResponse,
} from "@/lib/api"

export function AbilitazioniPanel({ deposito }: { deposito: string }) {
  const [open, setOpen] = useState<boolean>(false)
  const [data, setData] = useState<AbilitazioniResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    if (!deposito) return
    setData(null)
    void reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deposito])

  async function reload() {
    if (!deposito) return
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
      if (currentlyEnabled) await removeLinea(deposito, a, b)
      else await addLinea(deposito, a, b)
      await reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function toggleMateriale(mat: string, currentlyEnabled: boolean) {
    setError("")
    try {
      if (currentlyEnabled) await removeMateriale(deposito, mat)
      else await addMateriale(deposito, mat)
      await reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const enabledLines = data?.enabled_lines.length ?? 0
  const availLines = data?.available_lines.length ?? 0
  const enabledMats = data?.enabled_materials.length ?? 0
  const availMats = data?.available_materials.length ?? 0
  const fullyConfigured = data && (enabledLines > 0 && enabledMats > 0)

  return (
    <div
      className="rounded-xl mb-4 overflow-hidden"
      style={{
        backgroundColor: "var(--color-surface-container-lowest)",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-3 px-5 py-3 text-left transition-colors"
      >
        <ShieldCheck
          size={16}
          style={{
            color: fullyConfigured
              ? "var(--color-success)"
              : "var(--color-warning)",
          }}
        />
        <div className="flex-1">
          <div
            className="text-[10px] font-bold uppercase"
            style={{
              color: "var(--color-on-surface-quiet)",
              letterSpacing: "0.12em",
            }}
          >
            Step 0 — Abilitazioni {deposito}
          </div>
          <div
            className="text-[13px]"
            style={{ color: "var(--color-on-surface-strong)" }}
          >
            {data
              ? `${enabledLines}/${availLines} linee · ${enabledMats}/${availMats} materiali`
              : "Caricamento…"}
            {data && !fullyConfigured && (
              <span
                className="ml-2 text-[11px]"
                style={{ color: "var(--color-warning)" }}
              >
                Configura almeno 1 linea + 1 materiale per generare turni validi
              </span>
            )}
          </div>
        </div>
        <ChevronDown
          size={16}
          style={{
            color: "var(--color-on-surface-muted)",
            transform: open ? "rotate(180deg)" : "rotate(0)",
            transition: "transform 0.15s",
          }}
        />
      </button>

      {open && (
        <div
          className="px-5 pb-4 pt-1 border-t"
          style={{ borderColor: "var(--color-ghost)" }}
        >
          {error && (
            <div
              className="rounded-md px-3 py-2 my-3 flex items-center gap-2 text-[12px]"
              style={{
                backgroundColor: "var(--color-destructive-container)",
                color: "var(--color-destructive)",
              }}
            >
              <AlertTriangle size={12} />
              {error}
            </div>
          )}

          {loading && !data && (
            <div className="flex items-center justify-center py-6">
              <Loader2
                size={20}
                className="animate-spin"
                style={{ color: "var(--color-brand)" }}
              />
            </div>
          )}

          {data && availLines === 0 && availMats === 0 && (
            <div
              className="text-[12px] py-3"
              style={{ color: "var(--color-on-surface-muted)" }}
            >
              Nessun giro materiale tocca il deposito <strong>{deposito}</strong>.
              Importa un PDF turno materiale e ricarica.
            </div>
          )}

          {data && availLines > 0 && (
            <div className="mt-3">
              <SectionTitle icon={Train} title="Linee" sub={`${enabledLines}/${availLines}`} />
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

          {data && availMats > 0 && (
            <div className="mt-4">
              <SectionTitle icon={Train} title="Materiale rotabile" sub={`${enabledMats}/${availMats}`} />
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
      )}
    </div>
  )
}

function SectionTitle({
  icon: Icon,
  title,
  sub,
}: {
  icon: typeof Train
  title: string
  sub: string
}) {
  return (
    <div className="flex items-center gap-2 mb-2">
      <Icon size={12} style={{ color: "var(--color-on-surface-quiet)" }} />
      <h3
        className="text-[11px] font-bold uppercase"
        style={{
          color: "var(--color-on-surface-muted)",
          letterSpacing: "0.1em",
        }}
      >
        {title}
      </h3>
      <span
        className="ml-auto text-[10.5px]"
        style={{
          color: "var(--color-on-surface-quiet)",
          fontFamily: "var(--font-mono)",
        }}
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
      className="w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-md text-left transition-colors"
      style={{
        backgroundColor: enabled
          ? "var(--color-success-container)"
          : "var(--color-surface-container-low)",
      }}
    >
      <span
        className="w-3.5 h-3.5 rounded-sm flex items-center justify-center shrink-0"
        style={{
          backgroundColor: enabled ? "var(--color-success)" : "transparent",
          boxShadow: enabled
            ? "none"
            : "inset 0 0 0 1.5px var(--color-on-surface-quiet)",
        }}
      >
        {enabled && <Check size={10} color="white" strokeWidth={3} />}
      </span>
      <span
        className="text-[12px] font-medium flex-1"
        style={{
          color: enabled ? "var(--color-success)" : "var(--color-on-surface-strong)",
          fontFamily: "var(--font-mono)",
        }}
      >
        {label}
      </span>
      <span
        className="text-[10px]"
        style={{ color: "var(--color-on-surface-muted)" }}
      >
        {meta}
      </span>
    </button>
  )
}
