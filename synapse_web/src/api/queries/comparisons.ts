// Model Comparison Runs (§10). Reads come from the Supabase data API (RLS) — run_groups +
// the variant `runs`/`tool_calls`/`hitl_requests` rows. Launch / cancel / select-winner /
// promote go through the Cloud Backend (it creates the group + pushes `agent.compare`, with
// no signed grant — §10.4). In mock mode (no Supabase env) an in-memory store backs a fully
// interactive offline demo, mirroring queries/flows.ts. The new tables aren't in the
// generated Database types yet (0020 isn't applied to live), so the Supabase path casts.
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import type { AvailableModel, RunGroup } from "../../types";
import { apiGet, apiPost, isApiConfigured } from "../client";
import { toRunGroup, toVariant } from "../adapters/comparisons";
import { seedMockComparisons, MOCK_MODELS, mockLaunch } from "../../screens/comparison/templates";

// ── in-memory mock store (offline / demo mode) ───────────────────────────────
let MOCK_GROUPS: RunGroup[] = seedMockComparisons();

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const sb = () => supabase as any;

// ── available models + estimate (§10.9) ──────────────────────────────────────
export function useComparisonModels(
  agentId: string | undefined,
): UseQueryResult<AvailableModel[]> {
  return useQuery({
    queryKey: ["comparison-models", agentId],
    queryFn: async (): Promise<AvailableModel[]> => {
      if (isApiConfigured() && agentId) {
        const res = await apiGet<{ models: Record<string, unknown>[] }>(
          `/agents/${agentId}/comparison-models`,
        );
        return res.models.map((m) => ({
          model: String(m.model),
          provider: String(m.provider),
          inputPerMtok: Number(m.input_per_mtok ?? 0),
          outputPerMtok: Number(m.output_per_mtok ?? 0),
          hasCredentials: Boolean(m.has_credentials),
          estimateUsd: Number(m.estimate_usd ?? 0),
        }));
      }
      return MOCK_MODELS;
    },
    enabled: agentId != null,
  });
}

// ── list groups (optionally for one agent) ───────────────────────────────────
export function useComparisons(agentId?: string): UseQueryResult<RunGroup[]> {
  return useQuery({
    queryKey: ["comparisons", agentId ?? "all"],
    queryFn: async (): Promise<RunGroup[]> => {
      if (isSupabaseConfigured && supabase) {
        let q = sb().from("run_groups").select("*").order("created_at", { ascending: false });
        if (agentId) q = q.eq("agent_id", agentId);
        const { data, error } = await q;
        if (error) throw error;
        return (data as Record<string, unknown>[]).map((r) => toRunGroup(r));
      }
      return MOCK_GROUPS.filter((g) => !agentId || g.agentId === agentId);
    },
  });
}

// ── one group + its variants ─────────────────────────────────────────────────
export function useComparison(groupId: string | undefined): UseQueryResult<RunGroup | undefined> {
  return useQuery({
    queryKey: ["comparison", groupId],
    queryFn: async (): Promise<RunGroup | undefined> => {
      if (isSupabaseConfigured && supabase && groupId) {
        const { data: g, error } = await sb()
          .from("run_groups")
          .select("*")
          .eq("id", groupId)
          .maybeSingle();
        if (error) throw error;
        if (!g) return undefined;
        const { data: runs } = await sb()
          .from("runs")
          .select("*")
          .eq("run_group_id", groupId)
          .eq("mode", "comparison_variant");
        const variants = await Promise.all(
          ((runs ?? []) as Record<string, unknown>[]).map(async (r) => {
            const runId = String(r.id);
            const { data: tcs } = await sb().from("tool_calls").select("*").eq("run_id", runId);
            const proposed = ((tcs ?? []) as Record<string, unknown>[])
              .filter((t) => t.proposed_action)
              .map((t) => ({ name: String(t.name ?? ""), args_redacted: t.args_redacted, hitl: false }));
            return toVariant({
              ...r,
              tool_calls: tcs ?? [],
              proposed_actions: proposed,
            });
          }),
        );
        return toRunGroup(g, variants);
      }
      return MOCK_GROUPS.find((x) => x.id === groupId);
    },
    enabled: groupId != null,
  });
}

// ── launch a comparison (§10.8) ──────────────────────────────────────────────
export interface LaunchArgs {
  agentId: string;
  models: string[];
  input?: Record<string, unknown>;
  groupCostCap?: number | null;
  maxParallelVariants?: number;
}

export function useLaunchComparison() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (args: LaunchArgs): Promise<{ id: string }> => {
      if (isApiConfigured()) {
        const res = await apiPost<{ id: string }>(`/agents/${args.agentId}/comparisons`, {
          models: args.models,
          input: args.input ?? {},
          group_cost_cap: args.groupCostCap ?? null,
          max_parallel_variants: args.maxParallelVariants ?? 3,
        });
        return res;
      }
      const group = mockLaunch(args);
      MOCK_GROUPS = [group, ...MOCK_GROUPS];
      return { id: group.id };
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["comparisons"] }),
  });
}

export function useCancelComparison() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (groupId: string) => {
      if (isApiConfigured()) await apiPost(`/comparisons/${groupId}/cancel`);
      else MOCK_GROUPS = MOCK_GROUPS.map((g) => (g.id === groupId ? { ...g, status: "closed" } : g));
    },
    onSettled: (_d, _e, groupId) => {
      qc.invalidateQueries({ queryKey: ["comparisons"] });
      qc.invalidateQueries({ queryKey: ["comparison", groupId] });
    },
  });
}

export function useSelectWinner() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ groupId, runId }: { groupId: string; runId: string }) => {
      if (isApiConfigured()) await apiPost(`/comparisons/${groupId}/winner`, { run_id: runId });
      else
        MOCK_GROUPS = MOCK_GROUPS.map((g) =>
          g.id === groupId
            ? {
                ...g,
                status: "closed",
                winnerRunId: runId,
                variants: g.variants.map((v) => ({ ...v, isWinner: v.runId === runId })),
              }
            : g,
        );
    },
    onSettled: (_d, _e, v) => {
      qc.invalidateQueries({ queryKey: ["comparisons"] });
      qc.invalidateQueries({ queryKey: ["comparison", v.groupId] });
    },
  });
}

export function usePromoteWinner() {
  return useMutation({
    mutationFn: async (groupId: string): Promise<{ id?: string }> => {
      if (isApiConfigured()) return apiPost(`/comparisons/${groupId}/promote`);
      return { id: `run_${Math.random().toString(16).slice(2, 10)}` };
    },
  });
}
