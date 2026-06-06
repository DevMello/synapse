// DB row → UI view-model. Worker unit 10 implements; foundation stub throws.
// label "v<version>"; author from author_user_id (resolve display name); relativeTime
// (created_at); tags; current = (version === agent.current_version).
import type { Database } from "../../lib/database.types";
import type { Version } from "../../types";

type VersionRow = Database["public"]["Tables"]["agent_versions"]["Row"];

export function toVersion(_row: VersionRow, _currentVersion: number | null): Version {
  throw new Error("toVersion not implemented");
}
