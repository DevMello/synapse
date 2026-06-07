// DB row → UI view-model.
import type { Database } from "../../lib/database.types";
import type { Skill } from "../../types";

type SkillRow = Database["public"]["Tables"]["agent_skills"]["Row"];

export function toSkill(row: SkillRow): Skill {
  return {
    name: row.name,
    scope: row.scope ?? "",
    size: `${((row.bytes ?? 0) / 1024).toFixed(1)} KB`,
  };
}
