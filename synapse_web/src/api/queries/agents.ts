// Agent hooks. Worker unit 3 fills the configured branch.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { Agent } from "../../types";

export function useAgents(): UseQueryResult<Agent[]> {
  return useQuery({
    queryKey: ["agents"],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        // TODO(worker:agents): agent_overview view → toAgent
        return mock.agents;
      }
      return mock.agents;
    },
  });
}

export function useAgent(id: string | undefined): UseQueryResult<Agent | undefined> {
  return useQuery({
    queryKey: ["agent", id],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        // TODO(worker:agents): agent_overview where id = $id → toAgent
        return mock.agents.find((a) => a.id === id);
      }
      return mock.agents.find((a) => a.id === id);
    },
    enabled: id != null,
  });
}
