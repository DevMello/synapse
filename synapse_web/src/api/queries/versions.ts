// Version + prompt hooks (per-agent) → Supabase agent_versions.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { Version } from "../../types";
import { useCurrentAgent } from "../../screens/agent/context";
import { toVersion } from "../adapters/versions";

export function useVersions(): UseQueryResult<Version[]> {
  const agentId = useCurrentAgent().id;
  return useQuery({
    queryKey: ["versions", agentId],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        const { data: agent } = await supabase
          .from("agents")
          .select("current_version")
          .eq("id", agentId)
          .maybeSingle();
        const { data, error } = await supabase
          .from("agent_versions")
          .select("*")
          .eq("agent_id", agentId)
          .order("version", { ascending: false });
        if (error) throw error;

        // Resolve author display names in one round-trip.
        const authorIds = [
          ...new Set(data.map((v) => v.author_user_id).filter((x): x is string => Boolean(x))),
        ];
        const names = new Map<string, string>();
        if (authorIds.length) {
          const { data: users } = await supabase
            .from("users")
            .select("id, display_name, email")
            .in("id", authorIds);
          for (const u of users ?? []) names.set(u.id, u.display_name ?? u.email ?? "—");
        }
        const current = agent?.current_version ?? null;
        return data.map((v) =>
          toVersion(v, current, v.author_user_id ? names.get(v.author_user_id) ?? "—" : "—"),
        );
      }
      return mock.versions;
    },
  });
}

export function usePrompt(): UseQueryResult<string> {
  const agentId = useCurrentAgent().id;
  return useQuery({
    queryKey: ["prompt", agentId],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        const { data, error } = await supabase
          .from("agent_versions")
          .select("prompt, version")
          .eq("agent_id", agentId)
          .order("version", { ascending: false })
          .limit(1)
          .maybeSingle();
        if (error) throw error;
        return data?.prompt ?? "";
      }
      return mock.PROMPT;
    },
  });
}
