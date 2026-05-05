/**
 * Hooks React Query per `/api/personale-pdc/*` — Sprint 8.0 MR 3.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { getMioTurno, type MioTurnoGiornata } from "@/lib/api/personalePdc";

const PERSONALE_PDC_KEY = ["personale-pdc"] as const;

export function useMioTurno(): UseQueryResult<MioTurnoGiornata[]> {
  return useQuery({
    queryKey: [...PERSONALE_PDC_KEY, "mio-turno"],
    queryFn: getMioTurno,
  });
}
