// Memory hooks (per-agent) → Supabase agent_memory.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { MemoryEntry } from "../../types";
import { useCurrentAgent } from "../../screens/agent/context";
import { toMemoryEntry } from "../adapters/memory";

export function useMemory(): UseQueryResult<MemoryEntry[]> {
  const agentId = useCurrentAgent().id;
  return useQuery({
    queryKey: ["memory", agentId],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        const { data, error } = await supabase
          .from("agent_memory")
          .select("*")
          .eq("agent_id", agentId)
          .order("updated_at", { ascending: false });
        if (error) throw error;
        return data.map(toMemoryEntry);
      }
      return mock.memory;
    },
  });
}
