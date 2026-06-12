// Left rail — the node palette. Click a structural node or an agent to drop it on the
// canvas (added at the current viewport centre). Agents are grouped by daemon; once a
// flow has agents on one daemon, agents on other daemons are disabled (H2).
import { Icon } from "../../../components/Primitives";
import type { Agent, FlowNodeKind } from "../../../types";

const STRUCT: { kind: FlowNodeKind; icon: string; label: string; hint: string }[] = [
  { kind: "start", icon: "play", label: "Start", hint: "Seeds the first agent" },
  { kind: "router", icon: "git-branch", label: "Router", hint: "Conditional branch (one path)" },
  { kind: "return", icon: "rotate-ccw", label: "Return", hint: "Critic loop marker" },
  { kind: "end", icon: "flag", label: "End", hint: "Chain terminates" },
];

interface Props {
  agents: Agent[];
  activeDaemon?: string;
  onAddStruct: (kind: FlowNodeKind, label: string) => void;
  onAddAgent: (agent: Agent) => void;
}

export default function NodePalette({ agents, activeDaemon, onAddStruct, onAddAgent }: Props) {
  const byDaemon = new Map<string, Agent[]>();
  for (const a of agents) {
    const arr = byDaemon.get(a.daemonId) ?? [];
    arr.push(a);
    byDaemon.set(a.daemonId, arr);
  }

  return (
    <aside className="fc-palette">
      <div className="fc-palette-sec">
        <div className="fc-palette-label">Structure</div>
        {STRUCT.map((s) => (
          <button
            key={s.kind}
            className="fc-palette-item fc-palette-item--struct"
            onClick={() => onAddStruct(s.kind, s.label)}
            title={s.hint}
          >
            <span className="fc-palette-ico"><Icon name={s.icon} size={15} /></span>
            <span className="fc-palette-text">
              <span className="fc-palette-name">{s.label}</span>
              <span className="fc-palette-hint">{s.hint}</span>
            </span>
          </button>
        ))}
      </div>

      <div className="fc-palette-sec">
        <div className="fc-palette-label">Agents</div>
        {[...byDaemon.entries()].map(([daemon, list]) => {
          const locked = activeDaemon != null && daemon !== activeDaemon;
          return (
            <div key={daemon} className="fc-palette-group">
              <div className="fc-palette-daemon">
                <Icon name="server" size={11} /> {daemon}
                {locked && <span className="fc-palette-lock"><Icon name="lock" size={10} /></span>}
              </div>
              {list.map((a) => {
                const prod = (a.tags ?? []).includes("production");
                const disabled = locked || prod;
                return (
                  <button
                    key={a.id}
                    className={"fc-palette-item" + (disabled ? " is-disabled" : "")}
                    disabled={disabled}
                    onClick={() => onAddAgent(a)}
                    title={
                      prod
                        ? "Production-tagged — excluded from chains (§4)"
                        : locked
                          ? "Different daemon — a chain is daemon-local (H2)"
                          : `Add ${a.name}`
                    }
                  >
                    <span className="fc-palette-dot" data-status={a.status} />
                    <span className="fc-palette-text">
                      <span className="fc-palette-name">{a.name}</span>
                      <span className="fc-palette-hint">{a.engine}</span>
                    </span>
                    {prod && <span className="fc-tag-prod">prod</span>}
                  </button>
                );
              })}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
