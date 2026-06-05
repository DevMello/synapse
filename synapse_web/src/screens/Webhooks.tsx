// Synapse Web UI — Webhooks. Signed inbound trigger URLs that start agents on
// external events, each with a delivery history. Ported from the prototype's
// Webhooks view, taken to full depth (new-webhook affordance + delivery table).
import { useState } from "react";
import { Icon, Button, Chip } from "../components/Primitives";
import { PageHead, SectionRow, EmptyState } from "../components/Common";
import { useUI } from "../store/ui";
import { useAgents } from "../api/queries";

interface Hook {
  id: string;
  name: string;
  agent: string;
  url: string;
  secret: string;
  created: string;
  deliveries: number;
  last: string;
  status: string;
}

interface Delivery {
  id: string;
  hookId: string;
  when: string;
  status: string;
  code: number;
  response: string;
}

const SEED_HOOKS: Hook[] = [
  {
    id: "wh-pr",
    name: "pr-opened",
    agent: "pr-reviewer",
    url: "https://hooks.synapse.sh/in/9f2a7c41e8",
    secret: "whsec_9f2a7c41e8b3d6a0f1c2",
    created: "Apr 12",
    deliveries: 1284,
    last: "2 min ago",
    status: "passed",
  },
  {
    id: "wh-ticket",
    name: "ticket-created",
    agent: "support-triage",
    url: "https://hooks.synapse.sh/in/4c7b1a90d2",
    secret: "whsec_4c7b1a90d2e5f8c3b6a1",
    created: "Mar 28",
    deliveries: 5821,
    last: "12 sec ago",
    status: "running",
  },
];

const SEED_DELIVERIES: Delivery[] = [
  { id: "d1", hookId: "wh-ticket", when: "12 sec ago", status: "running", code: 202, response: "queued · run rn_8841" },
  { id: "d2", hookId: "wh-pr", when: "2 min ago", status: "passed", code: 200, response: "run rn_8839 started" },
  { id: "d3", hookId: "wh-ticket", when: "4 min ago", status: "passed", code: 200, response: "run rn_8835 started" },
  { id: "d4", hookId: "wh-pr", when: "9 min ago", status: "blocked", code: 401, response: "signature mismatch" },
  { id: "d5", hookId: "wh-ticket", when: "17 min ago", status: "passed", code: 200, response: "run rn_8829 started" },
  { id: "d6", hookId: "wh-pr", when: "31 min ago", status: "blocked", code: 429, response: "rate limited · retry" },
];

// Random hex segment for a freshly-minted signed URL / secret.
function hex(n: number): string {
  let s = "";
  for (let i = 0; i < n; i++) s += "0123456789abcdef"[Math.floor(Math.random() * 16)];
  return s;
}

export default function Webhooks() {
  const showToast = useUI((s) => s.showToast);
  const { data: agents } = useAgents();

  const [hooks, setHooks] = useState<Hook[]>(SEED_HOOKS);
  const [deliveries] = useState<Delivery[]>(SEED_DELIVERIES);
  const [revealed, setRevealed] = useState<Record<string, boolean>>({});

  // New-webhook affordance.
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [agent, setAgent] = useState("");

  function copy(text: string, label: string) {
    void navigator.clipboard?.writeText(text);
    showToast({ text: label });
  }

  function createHook() {
    const slug = name.trim() || "new-trigger";
    const target = agent || agents?.[0]?.name || "pr-reviewer";
    const seg = hex(10);
    setHooks((hs) => [
      {
        id: `wh-${Date.now()}`,
        name: slug,
        agent: target,
        url: `https://hooks.synapse.sh/in/${seg}`,
        secret: `whsec_${seg}${hex(10)}`,
        created: "just now",
        deliveries: 0,
        last: "—",
        status: "idle",
      },
      ...hs,
    ]);
    showToast({ text: `Signed webhook created · ${slug}` });
    setCreating(false);
    setName("");
    setAgent("");
  }

  const hookName = (id: string) => hooks.find((h) => h.id === id)?.name ?? id;

  return (
    <>
      <PageHead
        kicker="Webhooks"
        title="Inbound"
        serif="triggers"
        sub="Signed URLs that start agents on external events. View delivery history per hook."
        actions={
          <Button variant="primary" icon="plus" onClick={() => setCreating((c) => !c)}>
            New webhook
          </Button>
        }
      />

      {creating && (
        <div className="db-route-row" style={{ background: "rgba(239,106,42,0.04)", marginBottom: 14 }}>
          <Icon name="webhook" size={15} style={{ color: "var(--accent)" }} />
          <input
            className="db-input-sm"
            style={{ width: "auto", flex: 1 }}
            placeholder="trigger name · e.g. deploy-finished"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <select className="db-input-sm" style={{ width: "auto" }} value={agent} onChange={(e) => setAgent(e.target.value)}>
            <option value="">target agent…</option>
            {(agents ?? []).map((a) => <option key={a.id} value={a.name}>{a.name}</option>)}
          </select>
          <button className="db-mini-btn" onClick={() => setCreating(false)}>Cancel</button>
          <button className="db-mini-btn" style={{ borderColor: "var(--accent)", color: "var(--accent)" }} onClick={createHook}>
            Create
          </button>
        </div>
      )}

      {hooks.length === 0 ? (
        <EmptyState name="webhooks" icon="webhook" />
      ) : (
        <div className="db-table-wrap">
          <table className="db-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Endpoint</th>
                <th>Agent</th>
                <th>Secret</th>
                <th>Deliveries</th>
                <th>Created</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {hooks.map((h) => (
                <tr key={h.id}>
                  <td className="db-cell-primary db-mono">{h.name}</td>
                  <td>
                    <span className="db-secret-mask">
                      <span className="db-mono db-muted">{h.url}</span>
                      <button className="db-icon-mini" title="Copy URL" onClick={() => copy(h.url, "Webhook URL copied")}>
                        <Icon name="copy" size={14} />
                      </button>
                    </span>
                  </td>
                  <td>{h.agent}</td>
                  <td>
                    <span className="db-secret-mask">
                      <span className="db-mono">{revealed[h.id] ? h.secret : "whsec_•••••••••••••"}</span>
                      <button
                        className="db-icon-mini"
                        title={revealed[h.id] ? "Hide secret" : "Reveal secret"}
                        onClick={() => setRevealed((r) => ({ ...r, [h.id]: !r[h.id] }))}
                      >
                        <Icon name={revealed[h.id] ? "eye-off" : "eye"} size={14} />
                      </button>
                      <button className="db-icon-mini" title="Copy secret" onClick={() => copy(h.secret, "Signing secret copied")}>
                        <Icon name="copy" size={14} />
                      </button>
                    </span>
                  </td>
                  <td className="db-mono">{h.deliveries.toLocaleString()}</td>
                  <td className="db-mono db-muted">{h.created}</td>
                  <td><Chip s={h.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <SectionRow title="Delivery history" />
      <div className="db-table-wrap">
        <table className="db-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Webhook</th>
              <th>Status</th>
              <th>Code</th>
              <th>Response</th>
            </tr>
          </thead>
          <tbody>
            {deliveries.map((d) => (
              <tr key={d.id}>
                <td className="db-mono db-muted">{d.when}</td>
                <td className="db-mono">{hookName(d.hookId)}</td>
                <td><Chip s={d.status} label={d.status === "blocked" ? "failed" : undefined} /></td>
                <td className="db-mono">{d.code}</td>
                <td className="db-muted">{d.response}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
