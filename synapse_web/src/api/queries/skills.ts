// Skill hooks (per-agent) → Supabase agent_skills.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { Skill } from "../../types";
import { useCurrentAgent } from "../../screens/agent/context";
import { toSkill } from "../adapters/skills";

export function useSkills(): UseQueryResult<Skill[]> {
  const agentId = useCurrentAgent().id;
  return useQuery({
    queryKey: ["skills", agentId],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        const { data, error } = await supabase
          .from("agent_skills")
          .select("*")
          .eq("agent_id", agentId);
        if (error) throw error;
        return data.map(toSkill);
      }
      return mock.skills;
    },
  });
}
