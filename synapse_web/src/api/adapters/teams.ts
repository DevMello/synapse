// Build the nested team tree from flat teams + team_memberships rows.
import type { Database } from "../../lib/database.types";
import type { TeamNode } from "../../types";

type TeamRow = Pick<Database["public"]["Tables"]["teams"]["Row"], "id" | "name" | "parent_team_id">;
type TeamMembershipRow = Pick<
  Database["public"]["Tables"]["team_memberships"]["Row"],
  "team_id" | "user_id"
> & { users: { display_name: string | null; email: string | null } | null };

function initials(name: string): string {
  const parts = name.trim().split(/[\s.\-_]+/).filter(Boolean);
  const letters = parts.length >= 2 ? parts[0][0]! + parts[1][0]! : name.slice(0, 2);
  return letters.toUpperCase();
}

export function buildTeamTree(teams: TeamRow[], memberships: TeamMembershipRow[]): TeamNode[] {
  const byId = new Map<string, TeamNode>();
  for (const t of teams) {
    byId.set(t.id, { id: t.id, name: t.name, parentId: t.parent_team_id, members: [], children: [] });
  }
  for (const tm of memberships) {
    const node = byId.get(tm.team_id);
    if (!node) continue;
    const name = tm.users?.display_name ?? tm.users?.email?.split("@")[0] ?? "—";
    node.members.push({ userId: tm.user_id, name, init: initials(name) });
  }
  const roots: TeamNode[] = [];
  for (const node of byId.values()) {
    const parent = node.parentId ? byId.get(node.parentId) : undefined;
    if (parent) parent.children.push(node);
    else roots.push(node);
  }
  const sortRec = (nodes: TeamNode[]) => {
    nodes.sort((a, b) => a.name.localeCompare(b.name));
    nodes.forEach((n) => sortRec(n.children));
  };
  sortRec(roots);
  return roots;
}
