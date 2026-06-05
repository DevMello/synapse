// Synapse Web UI — Notifications. Connect Slack / Discord / Email channels and
// define routing rules (which events from which agents reach which channel).
// Ported from the prototype's Notifications view, taken to full depth.
import { useState } from "react";
import { Icon, Button } from "../components/Primitives";
import { PageHead, SectionRow, Toggle, EmptyState } from "../components/Common";
import { useUI } from "../store/ui";
import { useAgents } from "../api/queries";

interface Channel {
  id: string;
  icon: string;
  name: string;
  detail: string;
  on: boolean;
}

interface Route {
  id: string;
  evt: string;
  scope: string;
  dest: string;
}

// Channel kinds the operator can wire up via the "Connect channel" affordance.
const CHANNEL_KINDS: { kind: string; icon: string; placeholder: string }[] = [
  { kind: "Slack", icon: "slack", placeholder: "#ops-approvals" },
  { kind: "Discord", icon: "message-square", placeholder: "guild / channel" },
  { kind: "Email", icon: "mail", placeholder: "ops@northwind.io" },
];

const SEED_CHANNELS: Channel[] = [
  { id: "ch-slack", icon: "slack", name: "Slack", detail: "#ops-approvals · #alerts", on: true },
  { id: "ch-discord", icon: "message-square", name: "Discord", detail: "northwind / agents", on: true },
  { id: "ch-email", icon: "mail", name: "Email", detail: "ops@northwind.io", on: false },
];

const SEED_ROUTES: Route[] = [
  { id: "r1", evt: "Approvals", scope: "all agents", dest: "Slack #ops-approvals" },
  { id: "r2", evt: "Alerts · prompt-injection", scope: "all agents", dest: "Slack #alerts + Email" },
  { id: "r3", evt: "Run failed", scope: "codex-builder", dest: "Discord" },
];

const EVENT_KINDS = ["Approvals", "Alerts · prompt-injection", "Run failed", "Run passed", "Budget exceeded"];

export default function Notifications() {
  const showToast = useUI((s) => s.showToast);
  const { data: agents } = useAgents();

  const [channels, setChannels] = useState<Channel[]>(SEED_CHANNELS);
  const [routes, setRoutes] = useState<Route[]>(SEED_ROUTES);

  // Add-channel affordance state.
  const [adding, setAdding] = useState(false);
  const [newKind, setNewKind] = useState(CHANNEL_KINDS[0]);
  const [newDetail, setNewDetail] = useState("");

  // Add-rule affordance state.
  const [addingRule, setAddingRule] = useState(false);
  const [ruleEvt, setRuleEvt] = useState(EVENT_KINDS[0]);
  const [ruleScope, setRuleScope] = useState("all agents");
  const [ruleDest, setRuleDest] = useState(SEED_CHANNELS[0].name);

  function toggleChannel(id: string, next: boolean) {
    setChannels((cs) => cs.map((c) => (c.id === id ? { ...c, on: next } : c)));
    const c = channels.find((x) => x.id === id);
    if (c) showToast({ text: `${c.name} ${next ? "connected" : "paused"}`, variant: next ? "ok" : "warn" });
  }

  function addChannel() {
    const detail = newDetail.trim() || newKind.placeholder;
    setChannels((cs) => [
      ...cs,
      { id: `ch-${Date.now()}`, icon: newKind.icon, name: newKind.kind, detail, on: true },
    ]);
    showToast({ text: `${newKind.kind} connected · ${detail}` });
    setAdding(false);
    setNewDetail("");
    setNewKind(CHANNEL_KINDS[0]);
  }

  function addRule() {
    setRoutes((rs) => [...rs, { id: `r-${Date.now()}`, evt: ruleEvt, scope: ruleScope, dest: ruleDest }]);
    showToast({ text: `Routing rule added · ${ruleEvt} → ${ruleDest}` });
    setAddingRule(false);
    setRuleScope("all agents");
  }

  return (
    <>
      <PageHead
        kicker="Notifications"
        title="Where the fleet"
        serif="reaches you"
        sub="Connect channels and route which events from which agents go where."
        actions={
          <Button variant="primary" icon="plus" onClick={() => setAdding((a) => !a)}>
            Connect channel
          </Button>
        }
      />

      <div className="db-channel-list">
        {channels.map((c) => (
          <div key={c.id} className="db-channel-row">
            <span className="db-channel-icon"><Icon name={c.icon} size={18} /></span>
            <div className="db-channel-meta">
              <div className="db-channel-name">{c.name}</div>
              <div className="db-channel-detail db-mono">{c.detail}</div>
            </div>
            <Toggle on={c.on} onChange={(v) => toggleChannel(c.id, v)} />
          </div>
        ))}

        {adding && (
          <div className="db-channel-row" style={{ background: "rgba(239,106,42,0.04)", alignItems: "stretch" }}>
            <span className="db-channel-icon"><Icon name={newKind.icon} size={18} /></span>
            <div className="db-channel-meta" style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <div className="db-segmented" style={{ flex: "none" }}>
                {CHANNEL_KINDS.map((k) => (
                  <button
                    key={k.kind}
                    className={"db-seg" + (newKind.kind === k.kind ? " active" : "")}
                    onClick={() => setNewKind(k)}
                  >
                    <Icon name={k.icon} size={14} />{k.kind}
                  </button>
                ))}
              </div>
              <input
                className="db-input-sm"
                placeholder={newKind.placeholder}
                value={newDetail}
                onChange={(e) => setNewDetail(e.target.value)}
              />
            </div>
            <div className="db-env-add-actions">
              <button className="db-mini-btn" onClick={() => setAdding(false)}>Cancel</button>
              <button className="db-mini-btn" style={{ borderColor: "var(--accent)", color: "var(--accent)" }} onClick={addChannel}>
                Connect
              </button>
            </div>
          </div>
        )}
      </div>

      <SectionRow title="Routing rules">
        <Button variant="outline-light" icon="plus" onClick={() => setAddingRule((a) => !a)}>
          Add rule
        </Button>
      </SectionRow>

      {addingRule && (
        <div className="db-route-row db-mono" style={{ background: "rgba(239,106,42,0.04)", marginBottom: 8 }}>
          <select className="db-input-sm" style={{ width: "auto" }} value={ruleEvt} onChange={(e) => setRuleEvt(e.target.value)}>
            {EVENT_KINDS.map((e) => <option key={e} value={e}>{e}</option>)}
          </select>
          <Icon name="arrow-right" size={13} style={{ color: "var(--mute)" }} />
          <select className="db-input-sm" style={{ width: "auto" }} value={ruleScope} onChange={(e) => setRuleScope(e.target.value)}>
            <option value="all agents">all agents</option>
            {(agents ?? []).map((a) => <option key={a.id} value={a.name}>{a.name}</option>)}
          </select>
          <Icon name="arrow-right" size={13} style={{ color: "var(--mute)" }} />
          <select className="db-input-sm" style={{ width: "auto" }} value={ruleDest} onChange={(e) => setRuleDest(e.target.value)}>
            {channels.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
          </select>
          <span style={{ flex: 1 }} />
          <button className="db-mini-btn" onClick={() => setAddingRule(false)}>Cancel</button>
          <button className="db-mini-btn" style={{ borderColor: "var(--accent)", color: "var(--accent)" }} onClick={addRule}>Save</button>
        </div>
      )}

      {routes.length === 0 ? (
        <EmptyState name="routing rules" icon="bell-ring" />
      ) : (
        <div className="db-route-list">
          {routes.map((r) => (
            <div key={r.id} className="db-route-row db-mono">
              <span className="db-route-evt">{r.evt}</span>
              <Icon name="arrow-right" size={13} style={{ color: "var(--mute)" }} />
              <span className="db-muted">{r.scope}</span>
              <Icon name="arrow-right" size={13} style={{ color: "var(--mute)" }} />
              <span className="db-accent">{r.dest}</span>
              <span style={{ flex: 1 }} />
              <button
                className="db-icon-mini danger"
                title="Remove rule"
                onClick={() => {
                  setRoutes((rs) => rs.filter((x) => x.id !== r.id));
                  showToast({ text: "Routing rule removed", variant: "warn" });
                }}
              >
                <Icon name="trash" size={15} />
              </button>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
