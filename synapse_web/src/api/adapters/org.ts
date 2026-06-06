// DB row → UI view-model. Worker unit 1 implements; foundation stub throws (never
// called on the mock path). initials from display_name; plan from settings->>'plan'.
import type { Database } from "../../lib/database.types";
import type { Org } from "../../types";

type OrgRow = Database["public"]["Tables"]["organizations"]["Row"];
type UserRow = Database["public"]["Tables"]["users"]["Row"];

export function toOrg(_org: OrgRow, _user: UserRow | null): Org {
  throw new Error("toOrg not implemented");
}
