// Trace hooks (per-agent live trace). Worker unit 9 fills the configured branch.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { TraceLine } from "../../types";
import { useCurrentAgent } from "../../screens/agent/context";

export function useTraceLines(): UseQueryResult<TraceLine[]> {
  const agentId = useCurrentAgent().id;
  return useQuery({
    queryKey: ["traceLines", agentId],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        // TODO(worker:trace): reasoning_traces for the agent's latest run, order seq → toTraceLine
        return mock.traceLines;
      }
      return mock.traceLines;
    },
  });
}
