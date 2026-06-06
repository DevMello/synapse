// DB row → UI view-model. Worker unit 5 implements; foundation stub throws.
// severity from the new hitl_severity column; command/reason/context from the
// context jsonb; daemon name via join.
import type { Database } from "../../lib/database.types";
import type { Approval } from "../../types";

type HitlRow = Database["public"]["Tables"]["hitl_requests"]["Row"];

export function toApproval(_row: HitlRow): Approval {
  throw new Error("toApproval not implemented");
}
