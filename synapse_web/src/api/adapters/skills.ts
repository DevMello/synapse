// DB row → UI view-model. Worker unit 11 implements; foundation stub throws.
// name; scope; size from bytes (formatted "x.x KB").
import type { Database } from "../../lib/database.types";
import type { Skill } from "../../types";

type SkillRow = Database["public"]["Tables"]["agent_skills"]["Row"];

export function toSkill(_row: SkillRow): Skill {
  throw new Error("toSkill not implemented");
}
