// Org members (memberships ⋈ users) + RBAC mutations. RLS: members read all
// memberships in their org; owner/admin may write. Mock mode returns a static
// fallback and the mutations no-op (the Settings tab keeps optimistic local state).
import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import type { Member, Role } from "../../types";
import { toMember, toInvite } from "../adapters/members";

const MOCK_MEMBERS: Member[] = [
  { userId: "u-ak", name: "Avery Koss", email: "avery@northwind.io", role: "owner", init: "AK", active: "just now" },
  { userId: "u-jp", name: "Jin Park", email: "jin@northwind.io", role: "admin", init: "JP", active: "4 min ago" },
  { userId: "u-mv", name: "Mara Vance", email: "mara@northwind.io", role: "operator", init: "MV", active: "1 h ago" },
  { userId: "u-tl", name: "Theo Lund", email: "theo@northwind.io", role: "viewer", init: "TL", active: "yesterday" },
  { userId: "u-pn", name: "Priya Nair", email: "priya@northwind.io", role: "operator", init: "PN", active: "2 days ago" },
];

const ROLE_RANK: Record<Role, number> = { owner: 0, admin: 1, operator: 2, viewer: 3 };

async function currentOrgId(): Promise<string> {
  const { data, error } = await supabase!
    .from("organizations")
    .select("id")
    .limit(1)
    .maybeSingle();
  if (error) throw error;
  if (!data) throw new Error("No organization for the current session");
  return data.id;
}

export function useMembers(): UseQueryResult<Member[]> {
  return useQuery({
    queryKey: ["members"],
    queryFn: async () => {
      if (!isSupabaseConfigured || !supabase) return MOCK_MEMBERS;
      const { data, error } = await supabase
        .from("memberships")
        .select("role, created_at, user_id, users(email, display_name)");
      if (error) throw error;
      return data
        .map((r) => toMember(r as Parameters<typeof toMember>[0]))
        .sort((a, b) => ROLE_RANK[a.role] - ROLE_RANK[b.role] || a.name.localeCompare(b.name));
    },
  });
}

// Pending invitations (invite-by-email). Surfaced alongside members in the UI.
export function useInvitations(): UseQueryResult<Member[]> {
  return useQuery({
    queryKey: ["invitations"],
    queryFn: async () => {
      if (!isSupabaseConfigured || !supabase) return [];
      const { data, error } = await supabase
        .from("org_invitations")
        .select("id, email, role")
        .eq("status", "pending")
        .order("created_at", { ascending: false });
      if (error) throw error;
      return data.map(toInvite);
    },
  });
}

export function useInviteMember() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ email, role }: { email: string; role: Role }) => {
      if (!isSupabaseConfigured || !supabase) return;
      const orgId = await currentOrgId();
      const { data: auth } = await supabase.auth.getUser();
      const { error } = await supabase
        .from("org_invitations")
        .insert({ org_id: orgId, email, role, invited_by: auth.user?.id ?? null });
      if (error) {
        if (error.code === "23505") throw new Error("That email already has a pending invite.");
        throw error;
      }
    },
    onSettled: () => {
      if (isSupabaseConfigured) qc.invalidateQueries({ queryKey: ["invitations"] });
    },
  });
}

export function useRevokeInvitation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ inviteId }: { inviteId: string }) => {
      if (!isSupabaseConfigured || !supabase) return;
      const { error } = await supabase
        .from("org_invitations")
        .update({ status: "revoked" })
        .eq("id", inviteId);
      if (error) throw error;
    },
    onSettled: () => {
      if (isSupabaseConfigured) qc.invalidateQueries({ queryKey: ["invitations"] });
    },
  });
}

export function useUpdateMemberRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ userId, role }: { userId: string; role: Role }) => {
      if (!isSupabaseConfigured || !supabase) return;
      const orgId = await currentOrgId();
      const { error } = await supabase
        .from("memberships")
        .update({ role })
        .eq("org_id", orgId)
        .eq("user_id", userId);
      if (error) throw error;
    },
    // Reconcile with the server after success OR error (auto-rollback of optimistic
    // UI). In mock mode there's nothing to reconcile, so keep the optimistic state.
    onSettled: () => {
      if (isSupabaseConfigured) qc.invalidateQueries({ queryKey: ["members"] });
    },
  });
}

export function useRemoveMember() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ userId }: { userId: string }) => {
      if (!isSupabaseConfigured || !supabase) return;
      const orgId = await currentOrgId();
      const { error } = await supabase
        .from("memberships")
        .delete()
        .eq("org_id", orgId)
        .eq("user_id", userId);
      if (error) throw error;
    },
    // Reconcile with the server after success OR error (auto-rollback of optimistic
    // UI). In mock mode there's nothing to reconcile, so keep the optimistic state.
    onSettled: () => {
      if (isSupabaseConfigured) qc.invalidateQueries({ queryKey: ["members"] });
    },
  });
}
