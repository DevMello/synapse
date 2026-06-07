// DB row → UI view-model for org members (memberships ⋈ users).
import type { Database } from "../../lib/database.types";
import type { Member, Role } from "../../types";
import { relativeTime } from "../format";

type MembershipRow = Pick<
  Database["public"]["Tables"]["memberships"]["Row"],
  "role" | "created_at" | "user_id"
> & { users: { email: string | null; display_name: string | null } | null };

function initialsFor(name: string, email: string): string {
  const base = name.trim() || email.split("@")[0] || "";
  const parts = base.split(/[\s.\-_]+/).filter(Boolean);
  const letters = parts.length >= 2 ? parts[0][0]! + parts[1][0]! : base.slice(0, 2);
  return letters.toUpperCase();
}

export function toMember(row: MembershipRow): Member {
  const email = row.users?.email ?? "";
  const name = row.users?.display_name ?? email.split("@")[0] ?? "—";
  return {
    userId: row.user_id,
    name,
    email,
    role: row.role as Role,
    init: initialsFor(name, email),
    active: relativeTime(row.created_at),
  };
}

type InvitationRow = Pick<
  Database["public"]["Tables"]["org_invitations"]["Row"],
  "id" | "email" | "role"
>;

// Pending invitation → a Member row flagged `pending` (userId = invitation id).
export function toInvite(row: InvitationRow): Member {
  const name = row.email.split("@")[0].replace(/[.\-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  return {
    userId: row.id,
    name,
    email: row.email,
    role: row.role as Role,
    init: initialsFor(name, row.email),
    active: "invited",
    pending: true,
  };
}
