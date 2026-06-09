// Approval hooks → Supabase hitl_requests (pending) ⋈ agents/daemons.
import { useQuery, useMutation, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { Approval } from "../../types";
import { toApproval } from "../adapters/approvals";
import { apiPost } from "../client";
import { buildCommandAuth } from "../../lib/commandAuth";

type HitlRow = Parameters<typeof toApproval>[0];

async function getActorIds(): Promise<{ userId: string; orgId: string }> {
  if (!supabase) return { userId: "", orgId: "" };
  const { data } = await supabase.auth.getUser();
  const userId = data.user?.id ?? "";
  const orgId =
    (data.user?.app_metadata?.org_id as string | undefined) ??
    (data.user?.user_metadata?.org_id as string | undefined) ??
    "";
  return { userId, orgId };
}

export function useResolveHitl() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: {
      hitl_id: string;
      decision: "approve" | "deny";
      daemon_id?: string;
      agent_id?: string;
      org_id?: string;
    }) => {
      let command_auth_token: Awaited<ReturnType<typeof buildCommandAuth>> | undefined;
      if (body.daemon_id && body.agent_id) {
        try {
          const { userId, orgId } = await getActorIds();
          const payload = { hitl_id: body.hitl_id, decision: body.decision };
          command_auth_token = await buildCommandAuth(
            "hitl.resolve",
            body.agent_id,
            body.daemon_id,
            body.org_id ?? orgId,
            userId,
            payload,
          );
        } catch { /* degrade gracefully */ }
      }
      return apiPost(`/hitl/${body.hitl_id}/resolve`, {
        decision: body.decision,
        command_auth_token,
      });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["approvals"] });
    },
  });
}

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
