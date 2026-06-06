// Memory hooks (per-agent). Worker unit 8 fills the configured branch.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { MemoryEntry } from "../../types";
import { useCurrentAgent } from "../../screens/agent/context";

export function useMemory(): UseQueryResult<MemoryEntry[]> {
  const agentId = useCurrentAgent().id;
  return useQuery({
    queryKey: ["memory", agentId],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        // TODO(worker:memory): agent_memory (+ agent_memory_rollups) for agentId → toMemoryEntry
        return mock.memory;
      }
      return mock.memory;
    },
  });
}
