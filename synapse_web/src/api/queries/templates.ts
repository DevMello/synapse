// Template hooks → Supabase marketplace_listings (kind=agent) + a synthetic Blank.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { Template } from "../../types";
import { toTemplate } from "../adapters/templates";

const BLANK: Template = {
  id: "blank",
  name: "Blank agent",
  desc: "Start from an empty prompt.",
  kicker: "TEMPLATE",
  icon: "file-text",
};

export function useTemplates(): UseQueryResult<Template[]> {
  return useQuery({
    queryKey: ["templates"],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        const { data, error } = await supabase
          .from("marketplace_listings")
          .select("*")
          .eq("kind", "agent");
        if (error) throw error;
        return [BLANK, ...data.map(toTemplate)];
      }
      return mock.templates;
    },
  });
}
