// Team hierarchy (teams ⋈ team_memberships) + CRUD. Org-scoped via RLS; owner/admin
// write. Mock mode returns a small static tree and the mutations no-op.
import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import type { TeamNode } from "../../types";
import { buildTeamTree } from "../adapters/teams";
import { useUI } from "../../store/ui";

const MOCK_TREE: TeamNode[] = [
  {
    id: "t-eng", name: "Engineering", parentId: null,
    members: [{ userId: "u-ak", name: "Avery Koss", init: "AK" }],
    children: [
      { id: "t-plat", name: "Platform", parentId: "t-eng",
        members: [{ userId: "u-jp", name: "Jin Park", init: "JP" }, { userId: "u-mv", name: "Mara Vance", init: "MV" }], children: [] },
      { id: "t-supp", name: "Support", parentId: "t-eng",
        members: [{ userId: "u-tl", name: "Theo Lund", init: "TL" }], children: [] },
    ],
  },
  { id: "t-ops", name: "Operations", parentId: null,
    members: [{ userId: "u-mv", name: "Mara Vance", init: "MV" }], children: [] },
];

async function currentOrgId(): Promise<string> {
  const storeOrgId = useUI.getState().activeOrgId;
  if (storeOrgId && storeOrgId !== "personal") {
    return storeOrgId;
  }
  const { data, error } = await supabase!.from("organizations").select("id").limit(1).maybeSingle();
  if (error) throw error;
  if (!data) throw new Error("No organization for the current session");
  return data.id;
}

export function useTeams(): UseQueryResult<TeamNode[]> {
  return useQuery({
    queryKey: ["teams"],
    queryFn: async () => {
      if (!isSupabaseConfigured || !supabase) return MOCK_TREE;
      const [teamsRes, tmRes] = await Promise.all([
        supabase.from("teams").select("id, name, parent_team_id"),
        supabase.from("team_memberships").select("team_id, user_id, users(display_name, email)"),
      ]);
      if (teamsRes.error) throw teamsRes.error;
      if (tmRes.error) throw tmRes.error;
      return buildTeamTree(
        teamsRes.data,
        tmRes.data as Parameters<typeof buildTeamTree>[1],
      );
    },
  });
}

function invalidateTeams(qc: ReturnType<typeof useQueryClient>) {
  if (isSupabaseConfigured) qc.invalidateQueries({ queryKey: ["teams"] });
}

export function useCreateTeam() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ name, parentId }: { name: string; parentId: string | null }) => {
      if (!isSupabaseConfigured || !supabase) return;
      const orgId = await currentOrgId();
      const { error } = await supabase
        .from("teams")
        .insert({ org_id: orgId, name, parent_team_id: parentId });
      if (error) throw error;
    },
    onSettled: () => invalidateTeams(qc),
  });
}

export function useDeleteTeam() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ teamId }: { teamId: string }) => {
      if (!isSupabaseConfigured || !supabase) return;
      const { error } = await supabase.from("teams").delete().eq("id", teamId);
      if (error) throw error;
    },
    onSettled: () => invalidateTeams(qc),
  });
}

export function useAddTeamMember() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ teamId, userId }: { teamId: string; userId: string }) => {
      if (!isSupabaseConfigured || !supabase) return;
      const orgId = await currentOrgId();
      const { error } = await supabase
        .from("team_memberships")
        .insert({ org_id: orgId, team_id: teamId, user_id: userId });
      if (error && error.code !== "23505") throw error; // ignore "already on team"
    },
    onSettled: () => invalidateTeams(qc),
  });
}

export function useRemoveTeamMember() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ teamId, userId }: { teamId: string; userId: string }) => {
      if (!isSupabaseConfigured || !supabase) return;
      const { error } = await supabase
        .from("team_memberships")
        .delete()
        .eq("team_id", teamId)
        .eq("user_id", userId);
      if (error) throw error;
    },
    onSettled: () => invalidateTeams(qc),
  });
}
