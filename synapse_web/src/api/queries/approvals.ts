// Approval hooks → Supabase hitl_requests (pending) ⋈ agents/daemons.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { Approval } from "../../types";
import { toApproval } from "../adapters/approvals";

type HitlRow = Parameters<typeof toApproval>[0];

export function useApprovals(): UseQueryResult<Approval[]> {
  return useQuery({
    queryKey: ["approvals"],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        const { data, error } = await supabase
          .from("hitl_requests")
          .select("*, agents(name), daemons(name)")
          .eq("status", "pending")
          .order("created_at", { ascending: false });
        if (error) throw error;
        return (data as unknown as HitlRow[]).map(toApproval);
      }
      return mock.approvals;
    },
  });
}
