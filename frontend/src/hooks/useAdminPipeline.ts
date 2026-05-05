/**
 * Hook React Query per l'overview pipeline trasversale (admin).
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import {
  getPipelineOverview,
  type PipelineOverviewResponse,
} from "@/lib/api/adminPipeline";

const ADMIN_PIPELINE_KEY = ["admin", "pipeline-overview"] as const;

export function useAdminPipelineOverview(): UseQueryResult<PipelineOverviewResponse> {
  return useQuery({
    queryKey: ADMIN_PIPELINE_KEY,
    queryFn: getPipelineOverview,
  });
}
