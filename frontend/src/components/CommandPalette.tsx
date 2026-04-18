/**
 * CommandPalette — hotkey ⌘K / Ctrl+K per navigazione e azioni rapide.
 *
 * Implementazione self-contained (no cmdk, no radix-dialog) per evitare
 * nuove dipendenze in produzione. Gestisce:
 *   - Apertura/chiusura globale con listener in Layout
 *   - Input con focus automatico
 *   - Filtro fuzzy semplice (case-insensitive, match di sottosequenza)
 *   - Gruppi: Suggerimenti · Navigazione · Turni · Azioni
 *   - Nav tastiera: ↑↓ Home End, Enter per selezionare, Esc per chiudere
 *   - Click su backdrop per chiudere
 *
 * Le voci "Turni" vengono caricate on-demand al primo open (una volta sola
 * per sessione, ri-fetch al cambio utente via key prop).
 */

import { useEffect, useMemo, useRef, useState, useCallback } from "react"
import { createPortal } from "react-dom"
import { useNavigate } from "react-router-dom"
import {
  LayoutDashboard,
  Search,
  ClipboardList,
  PlusCircle,
  Calendar,
  Train,
  Upload,
  Settings,
  LogOut,
  ArrowRight,
  Sparkles,
  Compass,
  Wrench,
} from "lucide-react"
import { getSavedShifts, type SavedShift } from "@/lib/api"

type IconComponent = typeof LayoutDashboard

interface Cmd {
  id: string
  group: "Suggerimenti" | "Navigazione" | "Turni" | "Azioni"
  label: string
  hint?: string
  icon: IconComponent
  run: () => void
  keywords?: string
}

interface CommandPaletteProps {
  open: boolean
  onClose: () => void
  onLogout: () => void
}

export function CommandPalette({ open, onClose, onLogout }: CommandPaletteProps) {
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const [query, setQuery] = useState("")
  const [activeIdx, setActiveIdx] = useState(0)
  const [shifts, setShifts] = useState<SavedShift[]>([])

  // Fetch saved shifts al primo open (cache per la sessione)
  const [shiftsLoaded, setShiftsLoaded] = useState(false)
  useEffect(() => {
    if (open && !shiftsLoaded) {
      getSavedShifts()
        .then((r) => setShifts(r.shifts))
        .catch(() => setShifts([]))
        .finally(() => setShiftsLoaded(true))
    }
  }, [open, shiftsLoaded])

  // Reset query / selection ogni apertura
  useEffect(() => {
    if (open) {
      setQuery("")
      setActiveIdx(0)
      setTimeout(() => inputRef.current?.focus(), 0)
    }
  }, [open])

  const go = useCallback(
    (path: string) => {
      onClose()
      navigate(path)
    },
    [onClose, navigate],
  )

  const allCommands = useMemo<Cmd[]>(() => {
    const nav: Cmd[] = [
      { id: "nav:dash", group: "Navigazione", label: "Dashboard", icon: LayoutDashboard, run: () => go("/"), keywords: "home pannello" },
      { id: "nav:trains", group: "Navigazione", label: "Cerca treni", icon: Search, run: () => go("/treni"), keywords: "treno search" },
      { id: "nav:shifts", group: "Navigazione", label: "Turni Materiale", icon: ClipboardList, run: () => go("/turni"), keywords: "turni salvati materiale" },
      { id: "nav:builder", group: "Navigazione", label: "Nuovo turno", icon: PlusCircle, run: () => go("/builder"), keywords: "create nuovo turno builder" },
      { id: "nav:calendar", group: "Navigazione", label: "Calendario", icon: Calendar, run: () => go("/calendario") },
      { id: "nav:pdc", group: "Navigazione", label: "Turni PdC", icon: Train, run: () => go("/pdc"), keywords: "personale di condotta macchinista" },
      { id: "nav:import", group: "Navigazione", label: "Import PDF", icon: Upload, run: () => go("/import"), keywords: "importa gantt trenord" },
      { id: "nav:settings", group: "Navigazione", label: "Impostazioni", icon: Settings, run: () => go("/impostazioni") },
    ]

    const actions: Cmd[] = [
      { id: "act:new", group: "Azioni", label: "Crea nuovo turno", icon: PlusCircle, run: () => go("/builder"), hint: "⌘N" },
      { id: "act:import", group: "Azioni", label: "Importa PDF turni", icon: Upload, run: () => go("/import") },
      { id: "act:logout", group: "Azioni", label: "Esci", icon: LogOut, run: () => { onClose(); onLogout() }, keywords: "logout disconnetti" },
    ]

    const turniCmds: Cmd[] = shifts.slice(0, 25).map((s) => ({
      id: `turno:${s.id}`,
      group: "Turni",
      label: s.name,
      hint: `${s.deposito} · ${s.day_type}`,
      icon: Train,
      run: () => go("/turni"),
      keywords: `${s.deposito} ${s.day_type}`,
    }))

    const suggerimenti: Cmd[] = [
      { id: "sug:builder", group: "Suggerimenti", label: "Inizia un nuovo turno PdC", icon: Sparkles, run: () => go("/builder") },
      { id: "sug:pdc", group: "Suggerimenti", label: "Apri Turni PdC", icon: Compass, run: () => go("/pdc") },
      { id: "sug:import", group: "Suggerimenti", label: "Importa un PDF Gantt", icon: Wrench, run: () => go("/import") },
    ]

    return [...suggerimenti, ...nav, ...turniCmds, ...actions]
  }, [shifts, go, onLogout, onClose])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) {
      // Quando vuoto, mostra solo i primi 3 suggerimenti + tutta la navigazione + tutte le azioni.
      return allCommands.filter((c) => c.group !== "Turni")
    }
    const match = (c: Cmd) => {
      const hay = `${c.label} ${c.keywords ?? ""} ${c.group}`.toLowerCase()
      return q.split(/\s+/).every((tok) => hay.includes(tok))
    }
    return allCommands.filter(match)
  }, [allCommands, query])

  // Ri-clamp selezione quando cambia il filtro
  useEffect(() => {
    if (activeIdx >= filtered.length) setActiveIdx(Math.max(0, filtered.length - 1))
  }, [filtered, activeIdx])

  // Scroll per tenere l'item attivo in vista
  useEffect(() => {
    const node = listRef.current?.querySelector<HTMLElement>(
      `[data-cmd-idx="${activeIdx}"]`,
    )
    node?.scrollIntoView({ block: "nearest" })
  }, [activeIdx])

  // Handler key globali del dialog
  const handleKey = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === "Escape") {
        e.preventDefault()
        onClose()
        return
      }
      if (e.key === "ArrowDown") {
        e.preventDefault()
        setActiveIdx((i) => Math.min(filtered.length - 1, i + 1))
      } else if (e.key === "ArrowUp") {
        e.preventDefault()
        setActiveIdx((i) => Math.max(0, i - 1))
      } else if (e.key === "Home") {
        e.preventDefault()
        setActiveIdx(0)
      } else if (e.key === "End") {
        e.preventDefault()
        setActiveIdx(Math.max(0, filtered.length - 1))
      } else if (e.key === "Enter") {
        e.preventDefault()
        filtered[activeIdx]?.run()
      }
    },
    [filtered, activeIdx, onClose],
  )

  if (!open) return null

  // Raggruppa per group preservando l'ordine di apparizione in `filtered`
  const groups = new Map<string, { cmd: Cmd; idx: number }[]>()
  filtered.forEach((c, idx) => {
    if (!groups.has(c.group)) groups.set(c.group, [])
    groups.get(c.group)!.push({ cmd: c, idx })
  })

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center pt-[10vh] px-4"
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      onKeyDown={handleKey}
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0"
        style={{
          backgroundColor: "rgba(15, 23, 42, 0.45)",
          backdropFilter: "blur(8px) saturate(180%)",
          WebkitBackdropFilter: "blur(8px) saturate(180%)",
        }}
        onClick={onClose}
      />

      {/* Dialog */}
      <div
        className="relative w-full max-w-2xl rounded-2xl overflow-hidden"
        style={{
          backgroundColor: "rgba(255, 255, 255, 0.94)",
          backdropFilter: "blur(24px) saturate(180%)",
          WebkitBackdropFilter: "blur(24px) saturate(180%)",
          boxShadow: "var(--shadow-lg)",
          border: "1px solid var(--color-ghost)",
        }}
      >
        {/* Input row */}
        <div
          className="flex items-center gap-3 px-4 py-3.5"
          style={{ borderBottom: "1px solid var(--color-ghost)" }}
        >
          <Search
            size={16}
            strokeWidth={1.8}
            style={{ color: "var(--color-on-surface-quiet)" }}
          />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setActiveIdx(0)
            }}
            placeholder="Cerca turno, treno o azione…"
            className="flex-1 bg-transparent outline-none text-[14px] font-medium"
            style={{
              color: "var(--color-on-surface-strong)",
              fontFamily: "var(--font-sans)",
            }}
          />
          <kbd
            className="px-1.5 py-0.5 rounded text-[10px] font-semibold"
            style={{
              fontFamily: "var(--font-mono)",
              backgroundColor: "var(--color-surface-container)",
              color: "var(--color-on-surface-muted)",
            }}
          >
            Esc
          </kbd>
        </div>

        {/* Results */}
        <div
          ref={listRef}
          className="max-h-[60vh] overflow-y-auto py-2"
        >
          {filtered.length === 0 ? (
            <div
              className="px-4 py-8 text-center text-[13px]"
              style={{ color: "var(--color-on-surface-muted)" }}
            >
              Nessun risultato per <span className="font-semibold">"{query}"</span>
            </div>
          ) : (
            Array.from(groups.entries()).map(([groupName, entries]) => (
              <div key={groupName} className="mb-1.5">
                <div
                  className="px-4 pt-2 pb-1 text-[9.5px] font-bold uppercase"
                  style={{
                    color: "var(--color-on-surface-quiet)",
                    letterSpacing: "0.12em",
                  }}
                >
                  {groupName}
                </div>
                {entries.map(({ cmd, idx }) => {
                  const isActive = idx === activeIdx
                  const Icon = cmd.icon
                  return (
                    <button
                      key={cmd.id}
                      data-cmd-idx={idx}
                      type="button"
                      onClick={() => cmd.run()}
                      onMouseEnter={() => setActiveIdx(idx)}
                      className="w-full flex items-center gap-3 px-4 py-2 text-left transition-colors"
                      style={{
                        backgroundColor: isActive
                          ? "var(--color-surface-container-high)"
                          : "transparent",
                      }}
                    >
                      <div
                        className="w-7 h-7 rounded-md grid place-items-center"
                        style={{
                          backgroundColor: isActive
                            ? "rgba(0, 98, 204, 0.10)"
                            : "var(--color-surface-container)",
                          color: "var(--color-brand)",
                        }}
                      >
                        <Icon size={14} strokeWidth={1.8} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div
                          className="text-[13px] font-medium truncate"
                          style={{ color: "var(--color-on-surface-strong)" }}
                        >
                          {cmd.label}
                        </div>
                        {cmd.hint && (
                          <div
                            className="text-[11px] truncate"
                            style={{
                              color: "var(--color-on-surface-muted)",
                              fontFamily: "var(--font-mono)",
                            }}
                          >
                            {cmd.hint}
                          </div>
                        )}
                      </div>
                      <ArrowRight
                        size={12}
                        style={{
                          color: isActive
                            ? "var(--color-brand)"
                            : "var(--color-on-surface-quiet)",
                          opacity: isActive ? 1 : 0.4,
                        }}
                      />
                    </button>
                  )
                })}
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div
          className="px-4 py-2 flex items-center gap-3 text-[10.5px]"
          style={{
            borderTop: "1px solid var(--color-ghost)",
            color: "var(--color-on-surface-quiet)",
            backgroundColor: "var(--color-surface-container-low)",
          }}
        >
          <span className="flex items-center gap-1">
            <kbd
              className="px-1 rounded"
              style={{ fontFamily: "var(--font-mono)" }}
            >
              ↑↓
            </kbd>
            naviga
          </span>
          <span className="flex items-center gap-1">
            <kbd
              className="px-1 rounded"
              style={{ fontFamily: "var(--font-mono)" }}
            >
              Enter
            </kbd>
            seleziona
          </span>
          <span className="ml-auto">{filtered.length} risultati</span>
        </div>
      </div>
    </div>,
    document.body,
  )
}
