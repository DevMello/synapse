// Shared context for the Agent Detail tabs. The detail shell (AgentDetail.tsx)
// resolves the current agent from the route and provides it here; every tab reads
// it with useCurrentAgent() instead of re-fetching or prop-drilling.
import { createContext, useContext, type ReactNode } from "react";
import type { Agent } from "../../types";

const AgentContext = createContext<Agent | null>(null);

export function AgentProvider({ agent, children }: { agent: Agent; children: ReactNode }) {
  return <AgentContext.Provider value={agent}>{children}</AgentContext.Provider>;
}

export function useCurrentAgent(): Agent {
  const agent = useContext(AgentContext);
  if (!agent) throw new Error("useCurrentAgent must be used within an AgentProvider");
  return agent;
}
