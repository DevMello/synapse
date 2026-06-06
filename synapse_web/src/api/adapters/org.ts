// DB row → UI view-model. initials from display_name; plan from settings->>'plan'.
import type { Database } from "../../lib/database.types";
import type { Org } from "../../types";

type OrgRow = Database["public"]["Tables"]["organizations"]["Row"];
type UserRow = Database["public"]["Tables"]["users"]["Row"];

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "—";
  const letters = parts.slice(0, 2).map((p) => p[0]!.toUpperCase());
  return letters.join("");
}

export function toOrg(org: OrgRow, user: UserRow | null): Org {
  const settings = (org.settings ?? {}) as { plan?: string };
  const operator = user?.display_name ?? user?.email ?? "—";
  return {
    name: org.name,
    plan: settings.plan ?? "Team",
    operator,
    initials: initialsOf(operator),
  };
}
