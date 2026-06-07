// Alert hooks → Supabase anomaly_events ⋈ agents/daemons.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { Alert } from "../../types";
import { toAlert } from "../adapters/alerts";

type AnomalyRow = Parameters<typeof toAlert>[0];

export function useAlerts(): UseQueryResult<Alert[]> {
  return useQuery({
    queryKey: ["alerts"],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        const { data, error } = await supabase
          .from("anomaly_events")
          .select("*, agents(name), daemons(name)")
          .order("created_at", { ascending: false })
          .limit(50);
        if (error) throw error;
        return (data as unknown as AnomalyRow[]).map(toAlert);
      }
      return mock.alerts;
    },
  });
}
