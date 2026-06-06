// Alert hooks. Worker unit 6 fills the configured branch.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { Alert } from "../../types";

export function useAlerts(): UseQueryResult<Alert[]> {
  return useQuery({
    queryKey: ["alerts"],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        // TODO(worker:alerts): anomaly_events order created_at desc → toAlert
        return mock.alerts;
      }
      return mock.alerts;
    },
  });
}
