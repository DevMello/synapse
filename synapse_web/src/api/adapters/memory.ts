// DB row → UI view-model. Worker unit 8 implements; foundation stub throws.
// key/ns(namespace)/val(text_redacted)/tags; size from bytes; relativeTime(updated_at).
import type { Database } from "../../lib/database.types";
import type { MemoryEntry } from "../../types";

type MemoryRow = Database["public"]["Tables"]["agent_memory"]["Row"];

export function toMemoryEntry(_row: MemoryRow): MemoryEntry {
  throw new Error("toMemoryEntry not implemented");
}
