// Approval hooks. Worker unit 5 fills the configured branch.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { Approval } from "../../types";

export function useApprovals(): UseQueryResult<Approval[]> {
  return useQuery({
    queryKey: ["approvals"],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        // TODO(worker:approvals): hitl_requests status=pending ⋈ agents/daemons → toApproval
        return mock.approvals;
      }
      return mock.approvals;
    },
  });
}
