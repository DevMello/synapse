// Orchestration grants (§2.3): list via the Supabase data API (RLS); mint/revoke via
// the Cloud Backend (server signs the grant). Mock mode returns a static fallback and
// the mutations no-op.
import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import type { Grant, GrantVerb } from "../../types";
import { apiPost, isApiConfigured } from "../client";
import { toGrant } from "../adapters/grants";

const MOCK_GRANTS: Grant[] = [];

export function useOrchestrationGrants(agentId: string | undefined): UseQueryResult<Grant[]> {
  return useQuery({
    queryKey: ["grants", agentId],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase && agentId) {
        const { data, error } = await supabase
          .from("agent_orchestration_grants")
          .select("*")
          .eq("agent_id", agentId)
          .order("created_at", { ascending: false });
        if (error) throw error;
        return data.map(toGrant);
      }
      return MOCK_GRANTS;
    },
    enabled: agentId != null,
  });
}

export interface MintGrantInput {
  verbs: GrantVerb[];
  targetAllow: string[];
  maxDepth: number;
  maxFanOut: number;
  treeBudgetUsd: number;
  expiresInSeconds: number;
}

export function useMintGrant(agentId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: MintGrantInput) => {
      if (!isApiConfigured() || !agentId) return;
      await apiPost(`/agents/${agentId}/orchestration-grants`, {
        verbs: input.verbs,
        target_allow: input.targetAllow,
        max_depth: input.maxDepth,
        max_fan_out: input.maxFanOut,
        tree_budget_usd: input.treeBudgetUsd,
        expires_in_seconds: input.expiresInSeconds,
      });
    },
    onSettled: () => {
      if (isSupabaseConfigured) qc.invalidateQueries({ queryKey: ["grants", agentId] });
    },
  });
}

export function useRevokeGrant(agentId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ grantId }: { grantId: string }) => {
      if (!isApiConfigured()) return;
      await apiPost(`/orchestration-grants/${grantId}/revoke`);
    },
    onSettled: () => {
      if (isSupabaseConfigured) qc.invalidateQueries({ queryKey: ["grants", agentId] });
    },
  });
}
