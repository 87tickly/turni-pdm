/**
 * Corridors grouping — mappa deterministica delle linee (coppia stazioni A/B)
 * verso un "corridoio" logico, per il deposito ALESSANDRIA.
 *
 * Dalla chat handoff Claude Design (bundle wZp8lKDl6NNAwq9ntepASA):
 *
 *   1. ASTI in A o B                                → Transit ASTI       (AT)
 *   2. MI.* / MILANO* in A o B                      → Milano             (MI)
 *   3. BERGAMO / TREVIGLIO                          → Bergamo            (BG)
 *   4. PAVIA / BELGIOIOSO / TORTONA                 → Pavia/Po           (PV)
 *   5. MORTARA / VIGEVANO / VERCELLI / CREMONA /
 *      CASALPUSTERLENGO / BRESCIA                   → Mortara/Vigevano   (MV)
 *   6. fallback                                      → Altri             (—)
 *
 * L'ordine conta: il primo match vince. Questo risolve casi di confine come
 * PAVIA↔VERCELLI (→ Pavia/Po, non Mortara/Vig) e MILANO ROGOREDO↔MORTARA
 * (→ Milano, non Mortara/Vig).
 *
 * Se servisse granularita' per-deposito diversa, estendere come
 * `CORRIDORS_BY_DEPOT[deposito]`.
 */

export interface Corridor {
  id: string          // "MI", "PV", "AT", "BG", "MV", "OT"
  name: string
  order: number       // ordine di rendering (minore = prima)
  badgeColor: string  // hex
  badgeBg: string     // hex rgba
}

export const CORRIDORS: Record<string, Corridor> = {
  MI: {
    id: "MI",
    name: "Linee verso Milano",
    order: 1,
    badgeColor: "#0062CC",
    badgeBg: "rgba(0, 98, 204, 0.10)",
  },
  PV: {
    id: "PV",
    name: "Corridoio Pavia/Po",
    order: 2,
    badgeColor: "#0D9488",
    badgeBg: "rgba(13, 148, 136, 0.10)",
  },
  AT: {
    id: "AT",
    name: "Transit ASTI",
    order: 3,
    badgeColor: "#B45309",
    badgeBg: "rgba(180, 83, 9, 0.10)",
  },
  BG: {
    id: "BG",
    name: "Corridoio Bergamo",
    order: 4,
    badgeColor: "#7C3AED",
    badgeBg: "rgba(124, 58, 237, 0.10)",
  },
  MV: {
    id: "MV",
    name: "Mortara · Vigevano · Vercelli",
    order: 5,
    badgeColor: "#475569",
    badgeBg: "rgba(71, 85, 105, 0.10)",
  },
  OT: {
    id: "OT",
    name: "Altri",
    order: 99,
    badgeColor: "#64748B",
    badgeBg: "rgba(100, 116, 139, 0.10)",
  },
}


function _norm(s: string): string {
  return (s || "").toUpperCase().trim()
}

/** True se la stazione appartiene al set (match esatto o prefisso `prefix.*`). */
function _stationMatches(station: string, targets: string[]): boolean {
  const s = _norm(station)
  for (const t of targets) {
    if (t.endsWith("*")) {
      if (s.startsWith(t.slice(0, -1))) return true
    } else {
      if (s === t) return true
    }
  }
  return false
}

/** Classifica la coppia (A, B) in un corridoio. Prima match vince. */
export function classifyCorridor(stationA: string, stationB: string): Corridor {
  const pair = [stationA, stationB]
  const anyMatches = (targets: string[]) =>
    pair.some((s) => _stationMatches(s, targets))

  // 1. ASTI
  if (anyMatches(["ASTI"])) return CORRIDORS.AT
  // 2. MI.* / MILANO* (incluse MI.CERTOSA, MI.LAMBRATE, MI.P.GARIBALDI, MI.ROGOREDO, MILANO CENTRALE, MILANO ROGOREDO)
  if (anyMatches(["MI.*", "MILANO*", "MILANO "])) return CORRIDORS.MI
  // 3. BERGAMO / TREVIGLIO
  if (anyMatches(["BERGAMO", "TREVIGLIO"])) return CORRIDORS.BG
  // 4. PAVIA / BELGIOIOSO / TORTONA
  if (anyMatches(["PAVIA", "BELGIOIOSO", "TORTONA"])) return CORRIDORS.PV
  // 5. MORTARA / VIGEVANO / VERCELLI / CREMONA / CASALPUSTERLENGO / BRESCIA
  if (
    anyMatches([
      "MORTARA",
      "VIGEVANO",
      "VERCELLI",
      "CREMONA",
      "CASALPUSTERLENGO",
      "BRESCIA",
    ])
  )
    return CORRIDORS.MV
  // 6. Altri
  return CORRIDORS.OT
}


export interface LineWithCorridor<L> {
  corridor: Corridor
  lines: L[]
  enabled: number
  total: number
}

/** Raggruppa una lista di linee per corridoio, ordinando per `order` del corridoio. */
export function groupLinesByCorridor<
  L extends { station_a: string; station_b: string; enabled: boolean },
>(lines: L[]): LineWithCorridor<L>[] {
  const map = new Map<string, L[]>()
  for (const l of lines) {
    const c = classifyCorridor(l.station_a, l.station_b)
    if (!map.has(c.id)) map.set(c.id, [])
    map.get(c.id)!.push(l)
  }
  return Array.from(map.entries())
    .map(([cid, ls]) => ({
      corridor: CORRIDORS[cid] ?? CORRIDORS.OT,
      lines: ls,
      enabled: ls.filter((l) => l.enabled).length,
      total: ls.length,
    }))
    .sort((a, b) => a.corridor.order - b.corridor.order)
}
