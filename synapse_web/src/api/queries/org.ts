// Org hook → Supabase (the signed-in user's org + their profile).
import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { Org, OrgSummary } from "../../types";
import { toOrg } from "../adapters/org";
import { useUI } from "../../store/ui";

export function useOrg(): UseQueryResult<Org> {
  const activeOrgId = useUI((s) => s.activeOrgId);
  return useQuery({
    queryKey: ["org", activeOrgId],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        const { data: auth } = await supabase.auth.getUser();
        let query = supabase.from("organizations").select("*");
        if (activeOrgId && activeOrgId !== "personal") {
          query = query.eq("id", activeOrgId);
        } else {
          query = query.limit(1);
        }
        const { data: org, error } = await query.maybeSingle();
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

export function useOrgs(): UseQueryResult<OrgSummary[]> {
  return useQuery({
    queryKey: ["orgs"],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        const { data: auth } = await supabase.auth.getUser();
        if (!auth.user) return mock.ORGS;
        const { data, error } = await supabase
          .from("memberships")
          .select("org_id, organizations(id, name, settings)")
          .eq("user_id", auth.user.id);
        if (error) throw error;
        return (data ?? []).map((row) => {
          const org = row.organizations as { id: string; name: string; settings: unknown } | null;
          if (!org) return null;
          const settings = (org.settings ?? {}) as { plan?: string };
          return {
            id: org.id,
            name: org.name,
            plan: settings.plan ?? "Starter",
            initials: org.name.slice(0, 2).toUpperCase(),
          } satisfies OrgSummary;
        }).filter((o): o is OrgSummary => o !== null);
      }
      return mock.ORGS;
    },
  });
}

export function useCreateOrg() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ name }: { name: string }) => {
      if (!isSupabaseConfigured || !supabase) return;
      const { data: auth } = await supabase.auth.getUser();
      if (!auth.user) throw new Error("Not authenticated");
      const { data: org, error: orgError } = await supabase
        .from("organizations")
        .insert({ name, settings: { plan: "Starter" } })
        .select("id")
        .single();
      if (orgError) throw orgError;
      const { error: memberError } = await supabase
        .from("memberships")
        .insert({ org_id: org.id, user_id: auth.user.id, role: "owner" });
      if (memberError) throw memberError;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["orgs"] });
      qc.invalidateQueries({ queryKey: ["org"] });
    },
  });
}
