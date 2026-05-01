/**
 * React Query hooks per la dashboard PIANIFICATORE_PDC.
 *
 * MR 1: solo overview (KPI home). Hooks per liste turni/giri arrivano
 * con MR 2.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import {
  fetchPianificatorePdcOverview,
  type PianificatorePdcOverview,
} from "@/lib/api/pianificatorePdc";

const PIANIFICATORE_PDC_KEY = ["pianificatore-pdc"] as const;

export function usePianificatorePdcOverview(): UseQueryResult<PianificatorePdcOverview> {
  return useQuery({
    queryKey: [...PIANIFICATORE_PDC_KEY, "overview"],
    queryFn: fetchPianificatorePdcOverview,
  });
}
