/**
 * AbilitazioniPanel — "Step 0" pannello per gestire abilitazioni
 * (linee + materiale rotabile) di un deposito.
 *
 * Redesign Claude Design bundle wZp8lKDl6NNAwq9ntepASA (23/04/2026):
 *   - Stato COLLAPSED: riassunto compatto + mini coverage-bar per corridoio
 *   - Stato EXPANDED: chip materiali in alto, linee raggruppate per
 *     corridoio (Milano/Pavia/ASTI/Bergamo/Mortara/Altri), search
 *     inline con shortcut `/`, bulk toggle "Tutte"/"Nessuna" per
 *     corridoio, mini bulk "Attiva visibili"/"Azzera tutto".
 *
 * API backend invariata: getAbilitazioni / addLinea / removeLinea /
 * addMateriale / removeMateriale.
 */

import { useEffect, useMemo, useRef, useState } from "react"
import {
  ChevronDown,
  ShieldCheck,
  Loader2,
  AlertTriangle,
  Check,
  Search as SearchIcon,
  X,
} from "lucide-react"
import {
  getAbilitazioni,
  addLinea,
  removeLinea,
  addMateriale,
  removeMateriale,
  type AbilitazioniResponse,
} from "@/lib/api"
import { groupLinesByCorridor, type Corridor } from "@/lib/corridors"


export function AbilitazioniPanel({ deposito }: { deposito: string }) {
  const [open, setOpen] = useState<boolean>(false)
  const [data, setData] = useState<AbilitazioniResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [query, setQuery] = useState("")
  const searchRef = useRef<HTMLInputElement | null>(null)
  const [collapsedCorridors, setCollapsedCorridors] = useState<Set<string>>(
    () => new Set(),
  )

  useEffect(() => {
    if (!deposito) return
    setData(null)
    void reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deposito])

  useEffect(() => {
    // Shortcut "/" per focus search quando expanded
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (
        e.key === "/" &&
        document.activeElement !== searchRef.current &&
        !(document.activeElement instanceof HTMLInputElement) &&
        !(document.activeElement instanceof HTMLTextAreaElement)
      ) {
        e.preventDefault()
        searchRef.current?.focus()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open])

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

  async function setCorridorAll(
    corridorLines: AbilitazioniResponse["available_lines"],
    enable: boolean,
  ) {
    setError("")
    try {
      for (const l of corridorLines) {
        if (enable && !l.enabled) {
          await addLinea(deposito, l.station_a, l.station_b)
        } else if (!enable && l.enabled) {
          await removeLinea(deposito, l.station_a, l.station_b)
        }
      }
      await reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const enabledLines = data?.enabled_lines.length ?? 0
  const availLines = data?.available_lines.length ?? 0
  const enabledMats = data?.enabled_materials.length ?? 0
  const availMats = data?.available_materials.length ?? 0
  const fullyConfigured = !!(data && enabledLines > 0 && enabledMats > 0)

  const grouped = useMemo(() => {
    if (!data) return []
    return groupLinesByCorridor(data.available_lines)
  }, [data])

  const filteredGrouped = useMemo(() => {
    if (!query.trim()) return grouped
    const q = query.toUpperCase().trim()
    return grouped
      .map((g) => ({
        ...g,
        lines: g.lines.filter(
          (l) =>
            l.station_a.toUpperCase().includes(q) ||
            l.station_b.toUpperCase().includes(q),
        ),
      }))
      .filter((g) => g.lines.length > 0)
  }, [grouped, query])

  function toggleCorridorCollapsed(cid: string) {
    setCollapsedCorridors((prev) => {
      const next = new Set(prev)
      if (next.has(cid)) next.delete(cid)
      else next.add(cid)
      return next
    })
  }

  return (
    <div
      className="rounded-xl mb-4 overflow-hidden"
      style={{
        backgroundColor: "var(--color-surface-container-lowest)",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      {/* Header — stato collapsed vs expanded usa lo stesso layout */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-start gap-3 px-5 py-3 text-left transition-colors hover:bg-[var(--color-surface-container-low)]"
      >
        <ShieldCheck
          size={18}
          style={{
            color: fullyConfigured
              ? "var(--color-success, #16A34A)"
              : "var(--color-warning, #C76A12)",
            flexShrink: 0,
            marginTop: 2,
          }}
        />
        <div className="flex-1 min-w-0">
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
            className="text-[13px] flex items-center gap-2 flex-wrap mt-0.5"
            style={{ color: "var(--color-on-surface-strong)" }}
          >
            {!data ? (
              <span style={{ color: "var(--color-on-surface-muted)" }}>
                Caricamento…
              </span>
            ) : (
              <>
                <span>
                  <strong
                    style={{ fontFamily: "var(--font-mono, monospace)" }}
                  >
                    {enabledLines}
                  </strong>
                  <em
                    className="not-italic ml-1"
                    style={{ color: "var(--color-on-surface-muted)" }}
                  >
                    /{availLines} linee
                  </em>
                </span>
                <Dot />
                <span>
                  <strong
                    style={{ fontFamily: "var(--font-mono, monospace)" }}
                  >
                    {enabledMats}
                  </strong>
                  <em
                    className="not-italic ml-1"
                    style={{ color: "var(--color-on-surface-muted)" }}
                  >
                    /{availMats} materiali
                  </em>
                </span>
                {!open && grouped.length > 0 && (
                  <>
                    <Dot />
                    <span
                      className="text-[12px]"
                      style={{ color: "var(--color-on-surface-muted)" }}
                    >
                      {grouped.filter((g) => g.enabled > 0).length} corridoi coperti
                      {grouped
                        .filter((g) => g.enabled > 0)
                        .slice(0, 3)
                        .map((g, i) => (
                          <span key={g.corridor.id}>
                            {i === 0 ? " · " : ", "}
                            <strong
                              style={{ color: "var(--color-on-surface-strong)" }}
                            >
                              {g.corridor.name.replace(/^(Linee verso |Corridoio |Transit )/, "")}
                            </strong>
                          </span>
                        ))}
                    </span>
                  </>
                )}
                {data && !fullyConfigured && !open && (
                  <>
                    <Dot />
                    <span
                      className="text-[11.5px]"
                      style={{ color: "var(--color-warning, #C76A12)" }}
                    >
                      Configura almeno 1 linea + 1 materiale
                    </span>
                  </>
                )}
              </>
            )}
          </div>

          {/* Mini coverage bar — visibile SOLO collapsed */}
          {!open && data && grouped.length > 0 && (
            <div className="mt-2 grid grid-cols-6 gap-1.5 max-w-[520px]">
              {grouped.map((g) => {
                const ratio = g.total > 0 ? g.enabled / g.total : 0
                const empty = g.enabled === 0
                return (
                  <div
                    key={g.corridor.id}
                    className="relative rounded overflow-hidden"
                    style={{
                      backgroundColor: empty
                        ? "var(--color-surface-container)"
                        : g.corridor.badgeBg,
                      height: 24,
                    }}
                    title={`${g.corridor.name}: ${g.enabled}/${g.total}`}
                  >
                    <div
                      style={{
                        position: "absolute",
                        left: 0,
                        top: 0,
                        bottom: 0,
                        width: `${ratio * 100}%`,
                        backgroundColor: empty
                          ? "transparent"
                          : g.corridor.badgeColor,
                        opacity: 0.22,
                      }}
                    />
                    <div className="relative flex items-center justify-between px-1.5 h-full text-[9.5px] font-semibold">
                      <span
                        style={{
                          color: empty
                            ? "var(--color-on-surface-quiet)"
                            : g.corridor.badgeColor,
                        }}
                        className="truncate"
                      >
                        {g.corridor.name
                          .replace("Linee verso ", "")
                          .replace("Corridoio ", "")
                          .replace("Transit ", "")}
                      </span>
                      <span
                        style={{
                          color: empty
                            ? "var(--color-on-surface-quiet)"
                            : g.corridor.badgeColor,
                          fontFamily: "var(--font-mono, monospace)",
                        }}
                      >
                        {g.enabled}/{g.total}
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
        <ChevronDown
          size={16}
          style={{
            color: "var(--color-on-surface-muted)",
            transform: open ? "rotate(180deg)" : "rotate(0)",
            transition: "transform 0.15s",
            flexShrink: 0,
            marginTop: 4,
          }}
        />
      </button>

      {/* EXPANDED body */}
      {open && (
        <div
          className="px-5 pb-4 pt-2"
          style={{
            boxShadow: "inset 0 1px 0 var(--color-ghost)",
          }}
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

          {/* ─── Materiale rotabile (chip in alto) ─── */}
          {data && availMats > 0 && (
            <div className="mt-1">
              <SectionHead
                title="Materiale rotabile"
                count={`${enabledMats}/${availMats}`}
                right={
                  <button
                    onClick={async () => {
                      for (const m of data.available_materials) {
                        if (!m.enabled) await addMateriale(deposito, m.material_type)
                      }
                      await reload()
                    }}
                    className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px]"
                    style={{
                      color: "var(--color-on-surface-muted)",
                      backgroundColor: "transparent",
                    }}
                  >
                    <Check size={11} strokeWidth={2.2} /> Tutti
                  </button>
                }
              />
              <div className="flex flex-wrap gap-2 mt-2">
                {data.available_materials.map((m) => (
                  <MatChip
                    key={m.material_type}
                    label={m.material_type}
                    count={m.material_turn_count}
                    enabled={m.enabled}
                    onClick={() => toggleMateriale(m.material_type, m.enabled)}
                  />
                ))}
              </div>
            </div>
          )}

          {/* ─── Linee per corridoio ─── */}
          {data && availLines > 0 && (
            <div className="mt-5">
              <SectionHead
                title="Linee per corridoio"
                count={`${enabledLines}/${availLines}`}
                right={
                  <div className="flex items-center gap-2 flex-wrap">
                    {/* Search inline */}
                    <div
                      className="inline-flex items-center gap-1.5 px-2 py-1 rounded"
                      style={{
                        backgroundColor: "var(--color-surface-container-lowest)",
                        boxShadow: "inset 0 0 0 1.5px rgba(0,98,204,0.15)",
                        color: "var(--color-on-surface-muted)",
                      }}
                    >
                      <SearchIcon size={12} strokeWidth={1.8} />
                      <input
                        ref={searchRef}
                        type="text"
                        placeholder="Cerca stazione…"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        className="outline-none border-0 bg-transparent text-[11.5px] w-[130px]"
                        style={{ color: "var(--color-on-surface-strong)" }}
                      />
                      {query ? (
                        <button
                          onClick={() => setQuery("")}
                          className="opacity-60 hover:opacity-100"
                        >
                          <X size={11} />
                        </button>
                      ) : (
                        <kbd
                          className="text-[9px] font-bold px-1 rounded"
                          style={{
                            fontFamily: "var(--font-mono, monospace)",
                            color: "var(--color-on-surface-quiet)",
                            backgroundColor: "var(--color-surface-container)",
                          }}
                        >
                          /
                        </kbd>
                      )}
                    </div>
                    {/* Bulk */}
                    <BulkButton
                      label="Attiva visibili"
                      onClick={async () => {
                        for (const g of filteredGrouped) {
                          for (const l of g.lines) {
                            if (!l.enabled)
                              await addLinea(deposito, l.station_a, l.station_b)
                          }
                        }
                        await reload()
                      }}
                    />
                    <BulkButton
                      label="Azzera tutto"
                      danger
                      onClick={async () => {
                        for (const l of data.available_lines) {
                          if (l.enabled)
                            await removeLinea(deposito, l.station_a, l.station_b)
                        }
                        await reload()
                      }}
                    />
                  </div>
                }
              />

              <div className="mt-2 space-y-3">
                {filteredGrouped.length === 0 && (
                  <div
                    className="text-[12px] italic py-3 text-center"
                    style={{ color: "var(--color-on-surface-muted)" }}
                  >
                    Nessuna linea combacia con "{query}".
                  </div>
                )}
                {filteredGrouped.map((g) => (
                  <CorridorBlock
                    key={g.corridor.id}
                    corridor={g.corridor}
                    lines={g.lines}
                    enabled={g.enabled}
                    total={g.total}
                    collapsed={collapsedCorridors.has(g.corridor.id)}
                    onToggleCollapsed={() => toggleCorridorCollapsed(g.corridor.id)}
                    onToggleLine={(a, b, en) => toggleLinea(a, b, en)}
                    onAllOn={() => setCorridorAll(g.lines, true)}
                    onAllOff={() => setCorridorAll(g.lines, false)}
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


// ─────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────

function Dot() {
  return (
    <span
      className="w-1 h-1 rounded-full"
      style={{ backgroundColor: "var(--color-on-surface-quiet)", opacity: 0.5 }}
    />
  )
}

function SectionHead({
  title,
  count,
  right,
}: {
  title: string
  count: string
  right?: React.ReactNode
}) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span
        className="text-[11px] font-bold uppercase"
        style={{
          color: "var(--color-on-surface-muted)",
          letterSpacing: "0.1em",
        }}
      >
        {title}
      </span>
      <span
        className="text-[11px]"
        style={{
          color: "var(--color-on-surface-quiet)",
          fontFamily: "var(--font-mono, monospace)",
        }}
      >
        {count}
      </span>
      <span className="flex-1" />
      {right}
    </div>
  )
}

function MatChip({
  label,
  count,
  enabled,
  onClick,
}: {
  label: string
  count: number
  enabled: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md text-[12px] font-medium transition-colors"
      style={{
        backgroundColor: enabled
          ? "var(--color-success-container, rgba(34,197,94,0.12))"
          : "var(--color-surface-container-low)",
        color: enabled
          ? "var(--color-success, #16A34A)"
          : "var(--color-on-surface-strong)",
      }}
    >
      <span
        className="w-3.5 h-3.5 rounded-sm flex items-center justify-center shrink-0"
        style={{
          backgroundColor: enabled
            ? "var(--color-success, #16A34A)"
            : "transparent",
          boxShadow: enabled
            ? "none"
            : "inset 0 0 0 1.5px var(--color-on-surface-quiet)",
        }}
      >
        {enabled && <Check size={10} color="white" strokeWidth={3} />}
      </span>
      <span style={{ fontFamily: "var(--font-mono, monospace)" }}>{label}</span>
      <span
        className="text-[10px] opacity-70"
        style={{ color: "var(--color-on-surface-muted)" }}
      >
        {count} giro{count !== 1 ? "i" : ""}
      </span>
    </button>
  )
}

function BulkButton({
  label,
  onClick,
  danger,
}: {
  label: string
  onClick: () => void
  danger?: boolean
}) {
  return (
    <button
      onClick={onClick}
      className="px-2 py-1 rounded text-[11px] font-semibold transition-colors"
      style={{
        color: danger
          ? "var(--color-destructive, #C33A3A)"
          : "var(--color-on-surface-muted)",
        backgroundColor: danger
          ? "var(--color-destructive-container, rgba(220,38,38,0.09))"
          : "var(--color-surface-container-low)",
      }}
    >
      {label}
    </button>
  )
}

function CorridorBlock({
  corridor,
  lines,
  enabled,
  total,
  collapsed,
  onToggleCollapsed,
  onToggleLine,
  onAllOn,
  onAllOff,
}: {
  corridor: Corridor
  lines: Array<{
    station_a: string
    station_b: string
    material_turn_count: number
    enabled: boolean
  }>
  enabled: number
  total: number
  collapsed: boolean
  onToggleCollapsed: () => void
  onToggleLine: (a: string, b: string, wasEnabled: boolean) => void
  onAllOn: () => void
  onAllOff: () => void
}) {
  const empty = enabled === 0
  const full = enabled === total && total > 0
  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{
        backgroundColor: "var(--color-surface-container-low)",
      }}
    >
      <div
        className="flex items-center gap-2 px-3 py-2 cursor-pointer select-none flex-wrap"
        onClick={onToggleCollapsed}
      >
        <span
          className="inline-flex items-center justify-center rounded text-[10px] font-bold"
          style={{
            backgroundColor: corridor.badgeBg,
            color: corridor.badgeColor,
            width: 26,
            height: 22,
            fontFamily: "var(--font-mono, monospace)",
          }}
        >
          {corridor.id}
        </span>
        <span
          className="text-[12.5px] font-semibold"
          style={{ color: "var(--color-on-surface-strong)" }}
        >
          {corridor.name}
        </span>
        <span
          className="text-[11px]"
          style={{
            color: empty
              ? "var(--color-on-surface-quiet)"
              : full
              ? "var(--color-success, #16A34A)"
              : "var(--color-on-surface-muted)",
            fontFamily: "var(--font-mono, monospace)",
          }}
        >
          <strong>{enabled}</strong>
          <em
            className="not-italic"
            style={{ color: "var(--color-on-surface-quiet)" }}
          >
            /{total} attive
          </em>
        </span>
        <span className="flex-1" />
        <button
          onClick={(e) => {
            e.stopPropagation()
            onAllOn()
          }}
          className="text-[10.5px] font-semibold px-1.5 py-0.5 rounded"
          style={{ color: corridor.badgeColor, backgroundColor: "transparent" }}
        >
          Tutte
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation()
            onAllOff()
          }}
          className="text-[10.5px] px-1.5 py-0.5 rounded"
          style={{ color: "var(--color-on-surface-quiet)" }}
        >
          Nessuna
        </button>
        <ChevronDown
          size={14}
          style={{
            color: "var(--color-on-surface-muted)",
            transform: collapsed ? "rotate(-90deg)" : "rotate(0)",
            transition: "transform 0.15s",
          }}
        />
      </div>
      {!collapsed && (
        <div
          className="px-2 pb-2 grid gap-1"
          style={{ gridTemplateColumns: "1fr" }}
        >
          {lines.map((l) => (
            <LineRow
              key={`${l.station_a}|${l.station_b}`}
              a={l.station_a}
              b={l.station_b}
              count={l.material_turn_count}
              enabled={l.enabled}
              onToggle={() => onToggleLine(l.station_a, l.station_b, l.enabled)}
            />
          ))}
        </div>
      )}
      {collapsed && (
        <div
          className="px-3 py-1.5 text-[11px]"
          style={{ color: "var(--color-on-surface-muted)" }}
        >
          <span style={{ fontFamily: "var(--font-mono, monospace)" }}>
            {total} linee nascoste
          </span>
          {" · "}
          <span>click per espandere</span>
        </div>
      )}
    </div>
  )
}

function LineRow({
  a,
  b,
  count,
  enabled,
  onToggle,
}: {
  a: string
  b: string
  count: number
  enabled: boolean
  onToggle: () => void
}) {
  return (
    <button
      onClick={onToggle}
      className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-left transition-colors"
      style={{
        backgroundColor: enabled
          ? "var(--color-success-container, rgba(34,197,94,0.10))"
          : "transparent",
      }}
    >
      <span
        className="w-3.5 h-3.5 rounded-sm flex items-center justify-center shrink-0"
        style={{
          backgroundColor: enabled
            ? "var(--color-success, #16A34A)"
            : "transparent",
          boxShadow: enabled
            ? "none"
            : "inset 0 0 0 1.5px var(--color-on-surface-quiet)",
        }}
      >
        {enabled && <Check size={10} color="white" strokeWidth={3} />}
      </span>
      <span
        className="text-[11.5px] font-medium flex-1 truncate"
        style={{
          color: enabled
            ? "var(--color-success, #16A34A)"
            : "var(--color-on-surface-strong)",
          fontFamily: "var(--font-mono, monospace)",
        }}
      >
        {a}
        <span
          className="mx-1.5"
          style={{ color: "var(--color-on-surface-quiet)" }}
        >
          ↔
        </span>
        {b}
      </span>
      <span
        className="text-[10px]"
        style={{ color: "var(--color-on-surface-muted)" }}
      >
        {count} giro{count !== 1 ? "i" : ""}
      </span>
    </button>
  )
}
