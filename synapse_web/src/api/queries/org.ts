// Org hook → Supabase (the signed-in user's org + their profile).
import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { Org, OrgSummary } from "../../types";
import { toOrg } from "../adapters/org";

export function useOrg(): UseQueryResult<Org> {
  return useQuery({
    queryKey: ["org"],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        const { data: auth } = await supabase.auth.getUser();
        const { data: org, error } = await supabase
          .from("organizations")
          .select("*")
          .limit(1)
          .maybeSingle();
        if (error) throw error;
        if (!org) return mock.ORG;
        let user = null;
        if (auth.user) {
          const { data: u } = await supabase
            .from("users")
            .select("*")
            .eq("id", auth.user.id)
            .maybeSingle();
          user = u;
        }
        return toOrg(org, user);
      }
      return mock.ORG;
    },
  });
}

// ── Multi-org list ────────────────────────────────────────────────────────────
// Returns all orgs the current user belongs to. Falls back to a mock list
// (containing just the current org) until a real multi-org API is wired.
const MOCK_ORG_SUMMARY: OrgSummary = {
  id: "org_8f3a91c2",
  name: mock.ORG.name,
  plan: mock.ORG.plan,
  initials: mock.ORG.initials,
  isPersonal: false,
};

export function useOrgs(): UseQueryResult<OrgSummary[]> {
  return useQuery({
    queryKey: ["orgs"],
    queryFn: async (): Promise<OrgSummary[]> => {
      if (isSupabaseConfigured && supabase) {
        // When the real multi-org schema lands, query organizations + memberships here.
        // For now fall back to the single-org mock so the screen compiles and renders.
        const { data: org, error } = await supabase
          .from("organizations")
          .select("id, name")
          .limit(1)
          .maybeSingle();
        if (error) throw error;
        if (!org) return [MOCK_ORG_SUMMARY];
        return [
          {
            id: org.id,
            name: org.name,
            plan: mock.ORG.plan, // plan not yet in schema; use mock until migration adds it
            initials: org.name.slice(0, 2).toUpperCase(),
            isPersonal: false,
          },
        ];
      }
      return [MOCK_ORG_SUMMARY];
    },
  });
}

// ── Create org mutation ───────────────────────────────────────────────────────
// Returns the new org's ID on success (so the caller can navigate to its settings).
export function useCreateOrg() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ name }: { name: string }): Promise<string | null> => {
      if (isSupabaseConfigured && supabase) {
        // Real implementation: POST to the cloud API or insert via Supabase RPC.
        // Placeholder until the multi-org schema is in place.
        void name;
        return null;
      }
      // Mock: simulate a short delay and return a generated ID.
      await new Promise((r) => setTimeout(r, 400));
      return `org_${Math.random().toString(36).slice(2, 10)}`;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["orgs"] });
    },
  });
}
