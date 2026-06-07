// DB row → UI view-model. label "v<version>"; current = version === currentVersion.
import type { Database } from "../../lib/database.types";
import type { Version } from "../../types";
import { relativeTime } from "../format";

type VersionRow = Database["public"]["Tables"]["agent_versions"]["Row"];

export function toVersion(
  row: VersionRow,
  currentVersion: number | null,
  authorName = "—",
): Version {
  return {
    id: `v${row.version}`,
    label: `v${row.version}`,
    author: authorName,
    when: relativeTime(row.created_at),
    msg: row.message ?? "",
    tags: row.tags ?? [],
    current: row.version === currentVersion,
  };
}
