// Log hooks (per-agent). Worker unit 9 fills the configured branch.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { LogLine } from "../../types";
import { useCurrentAgent } from "../../screens/agent/context";

export function useLogLines(): UseQueryResult<LogLine[]> {
  const agentId = useCurrentAgent().id;
  return useQuery({
    queryKey: ["logs", agentId],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        // TODO(worker:logs): logs for agentId, order created_at → toLogLine
        return mock.logLines;
      }
      return mock.logLines;
    },
  });
}
