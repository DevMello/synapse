// DB row → UI view-model. Worker unit 12 implements; foundation stub throws.
// plugins catalog → CapabilityDef (id/name/kind/desc/builtin). kind maps
// capability_kind → "MCP server" | "plugin".
import type { Database } from "../../lib/database.types";
import type { CapabilityDef } from "../../types";

type PluginRow = Database["public"]["Tables"]["plugins"]["Row"];

export function toCapabilityDef(_row: PluginRow): CapabilityDef {
  throw new Error("toCapabilityDef not implemented");
}
