// Run hooks → Supabase runs ⋈ agents (denormalize agent name).
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { Run } from "../../types";
import { toRun } from "../adapters/runs";

type RunRow = Parameters<typeof toRun>[0];

export function useRuns(): UseQueryResult<Run[]> {
  return useQuery({
    queryKey: ["runs"],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        const { data, error } = await supabase
          .from("runs")
          .select("*, agents(name)")
          .order("created_at", { ascending: false })
          .limit(100);
        if (error) throw error;
        return (data as unknown as RunRow[]).map(toRun);
      }
      return mock.runs;
    },
  });
}
