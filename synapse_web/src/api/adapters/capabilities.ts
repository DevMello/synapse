// DB row → UI view-model. plugins catalog → CapabilityDef.
import type { Database } from "../../lib/database.types";
import type { CapabilityDef } from "../../types";

type PluginRow = Database["public"]["Tables"]["plugins"]["Row"];

const BUILTIN = new Set(["filesystem", "fetch", "git", "memory"]);

export function toCapabilityDef(row: PluginRow): CapabilityDef {
  return {
    id: row.id,
    name: row.name,
    kind: row.kind === "mcp" ? "MCP server" : "plugin",
    desc: "",
    builtin: BUILTIN.has(row.name),
  };
}
