// Agent hooks → Supabase agent_overview view.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { Agent } from "../../types";
import { toAgent } from "../adapters/agents";

export function useAgents(): UseQueryResult<Agent[]> {
  return useQuery({
    queryKey: ["agents"],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        const { data, error } = await supabase.from("agent_overview").select("*");
        if (error) throw error;
        return data.map(toAgent);
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
        const { data, error } = await supabase
          .from("agent_overview")
          .select("*")
          .eq("id", id!)
          .maybeSingle();
        if (error) throw error;
        return data ? toAgent(data) : undefined;
      }
      return mock.agents.find((a) => a.id === id);
    },
    enabled: id != null,
  });
}
