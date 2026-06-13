// Agent Detail — Compare tab (§10.12). Hosts the "Compare models" launcher for an API
// agent. CLI agents can't compare in v1 (E5), so the tab explains that instead.
import { useCurrentAgent } from "../context";
import CompareLauncher from "../../comparison/CompareLauncher";
import { Icon } from "../../../components/Primitives";

export default function CompareTab() {
  const agent = useCurrentAgent();
  // API agents only in v1 (E5): `model` is a first-class field for API agents.
  if (agent.type !== "API model") {
    return (
      <div className="db-callout" style={{ margin: 4 }}>
        <Icon name="alert-triangle" size={16} />
        <span>
          Model comparison is <b>API-agents-only</b> in v1 — a CLI agent's model isn't a
          first-class field, so its side effects can't be safely simulated yet (E5).
        </span>
      </div>
    );
  }
  return <CompareLauncher agentId={agent.id} agentName={agent.name} />;
}
