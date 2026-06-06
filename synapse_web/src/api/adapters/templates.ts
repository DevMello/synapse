// DB row → UI view-model. Worker unit 11 implements; foundation stub throws.
// kicker "MARKETPLACE"; icon derived from name/kind; rating from ratings jsonb.
// The synthetic "Blank" template is prepended in the query module, not here.
import type { Database } from "../../lib/database.types";
import type { Template } from "../../types";

type ListingRow = Database["public"]["Tables"]["marketplace_listings"]["Row"];

export function toTemplate(_row: ListingRow): Template {
  throw new Error("toTemplate not implemented");
}
