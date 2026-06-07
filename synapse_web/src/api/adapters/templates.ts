// DB row → UI view-model. The synthetic "Blank" template is prepended in the query.
import type { Database } from "../../lib/database.types";
import type { Template } from "../../types";

type ListingRow = Database["public"]["Tables"]["marketplace_listings"]["Row"];

function iconFor(name: string): string {
  const n = name.toLowerCase();
  if (n.includes("review") || n.includes("pr")) return "git-pull-request";
  if (n.includes("triage") || n.includes("support") || n.includes("inbox")) return "inbox";
  if (n.includes("build") || n.includes("ticket") || n.includes("code")) return "code";
  return "file-text";
}

export function toTemplate(row: ListingRow): Template {
  const ratings = (row.ratings ?? {}) as { avg?: number };
  return {
    id: row.id,
    name: row.name,
    desc: row.description ?? "",
    kicker: "MARKETPLACE",
    icon: iconFor(row.name),
    rating: ratings.avg,
  };
}
