// Run hooks. Worker unit 4 fills the configured branch.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { Run } from "../../types";

export function useRuns(): UseQueryResult<Run[]> {
  return useQuery({
    queryKey: ["runs"],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        // TODO(worker:runs): runs ⋈ agents (denormalize agent name), order created_at desc → toRun
        return mock.runs;
      }
      return mock.runs;
    },
  });
}
